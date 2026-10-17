"""Corporate-action sidecars and structural quality only. Never evaluates final strategies."""
from collections import Counter
from datetime import datetime, date, timedelta, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import statistics
import zipfile
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo
from .equity_research_data import UNIVERSE
from .equity_evidence_extension import HISTORY_START, HISTORY_END, FINAL_START, SPLIT_DATE, save
from .tws import finite

NY=ZoneInfo('America/New_York')
NS={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
SCHX_SPLIT_2022=datetime(2022,3,11,14,30,tzinfo=timezone.utc)


def stamp(value):
    result=datetime.fromisoformat(value.replace('Z','+00:00'))
    if result.tzinfo is None:raise ValueError('UTC_TIMESTAMP_REQUIRED')
    return result.astimezone(timezone.utc)


def file_hash(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verified_archive(path):
    path=Path(path)
    if file_hash(path)!=path.with_suffix('.sha256').read_text(encoding='utf-8').strip():
        raise ValueError('AUTHENTIC_ARCHIVE_HASH_MISMATCH')
    return json.loads(path.read_bytes())


def event(symbol,ex_date,pay_date,amount,source,source_sha,kind='CASH_DIVIDEND'):
    if symbol not in UNIVERSE:raise ValueError('CORPORATE_UNIVERSE_REQUIRED')
    ex=date.fromisoformat(ex_date);pay=date.fromisoformat(pay_date);amount=finite(amount,True)
    if pay<ex or not (HISTORY_START.date()<=ex<HISTORY_END.date()):raise ValueError('CORPORATE_DATE_OUT_OF_SCOPE')
    if not source.startswith('https://') or len(source_sha)!=64:raise ValueError('CORPORATE_PROVENANCE_REQUIRED')
    key=f'{symbol}|{ex}|{pay}|{kind}'
    return dict(event_id=hashlib.sha256(key.encode()).hexdigest(),symbol=symbol,ex_date=str(ex),
        pay_date=str(pay),amount_usd=str(amount),kind=kind,source=source,source_sha256=source_sha,
        amount_status='VERIFIED',currency='USD',net_after_tax=None,withholding_status='UNKNOWN')


def unique_events(events):
    result={}
    for e in events:
        key=e['event_id']
        if key in result and any(result[key][f]!=e[f] for f in ('amount_usd','symbol','ex_date','pay_date','kind')):
            raise ValueError('CONFLICTING_CORPORATE_ACTION')
        result[key]=e
    return sorted(result.values(),key=lambda e:(e['symbol'],e['ex_date'],e['kind']))


def issuer_date(value):
    text=str(value).strip()
    for pattern in ('%m/%d/%Y','%Y-%m-%d'):
        try:return datetime.strptime(text,pattern).date()
        except ValueError:pass
    # Excel date serial, not arbitrary timestamp conversion.
    number=finite(text)
    if number!=number.to_integral_value() or not 30000<=number<=50000:raise ValueError('ISSUER_DATE_INVALID')
    return date(1899,12,30)+timedelta(days=int(number))


def spy_events(path,source):
    """Bounded read-only OpenXML parser: exact ticker and columns, no formulas/macros."""
    sha=file_hash(path)
    with zipfile.ZipFile(path) as z:
        if sum(x.file_size for x in z.infolist())>50_000_000:raise ValueError('ISSUER_WORKBOOK_TOO_LARGE')
        def xml(name):
            raw=z.read(name)
            if len(raw)>20_000_000 or b'<!DOCTYPE' in raw or b'<!ENTITY' in raw:raise ValueError('ISSUER_XML_UNSAFE')
            return ET.fromstring(raw)
        strings=[''.join(n.itertext()) for n in xml('xl/sharedStrings.xml')]
        sheet=xml('xl/worksheets/sheet1.xml');rows=sheet.findall('.//m:row',NS)
        if len(rows)>25000:raise ValueError('ISSUER_WORKBOOK_TOO_MANY_ROWS')
        def cells(row):
            values={}
            for c in row:
                column=''.join(x for x in c.attrib['r'] if x.isalpha())
                v=c.find('m:v',NS)
                if c.find('m:f',NS) is not None:raise ValueError('ISSUER_FORMULA_NOT_EVIDENCE')
                if v is not None:values[column]=strings[int(v.text)] if c.attrib.get('t')=='s' else v.text
            return values
        header=cells(rows[0])
        if any(header.get(k)!=v for k,v in {'B':'TICKER','D':'EX-DATE','F':'PAYABLE DATE','G':'DIVIDEND ($)'}.items()):
            raise ValueError('ISSUER_WORKBOOK_SCHEMA_CHANGED')
        result=[]
        for row in rows[1:]:
            values=cells(row)
            if values.get('B')!='SPY':continue
            ex=issuer_date(values['D'])
            if HISTORY_START.date()<=ex<HISTORY_END.date():
                result.append(event('SPY',str(ex),str(issuer_date(values['F'])),values['G'].strip(),source,sha))
    return unique_events(result)


def load_corporate_events(root):
    folder=Path(root)/'artifacts/research/equity-operational/sources'
    result=[];coverage={}
    p=folder/'schx-web-extract.json'
    if p.exists():
        r=json.loads(p.read_bytes());sha=file_hash(p)
        result.extend(event('SCHX',x['ex_date'],x['pay_date'],x['amount'],r['source_url'],sha) for x in r['events'])
        coverage['SCHX']=dict(status='VERIFIED_REPORTED_EVENTS',source=r['source_url'],
            access=r['access'],independent_completeness='UNKNOWN',historical_amount_basis=r['amount_basis'])
    p=folder/'spy-distributions.xlsx'
    if p.exists():
        url='https://www.ssga.com/library-content/products/fund-data/etfs/us/spdr-etf-historical-distributions.xlsx'
        result.extend(spy_events(p,url))
        coverage['SPY']=dict(status='VERIFIED_REPORTED_EVENTS',source=url,
            independent_completeness='UNKNOWN',capital_gain_components='NOT_IMPUTED_FROM_BLANK_CELLS')
    p=folder/'ford-verified-extract.json'
    if p.exists():
        r=json.loads(p.read_bytes());sha=file_hash(p)
        result.extend(event('F',x['ex_date'],x['pay_date'],x['amount'],r['source_url'],sha,x['kind']) for x in r['events'])
    coverage['F']=dict(status='PARTIAL' if p.exists() else 'UNKNOWN',
        reason='PUBLIC_FEED_EMPTY_IS_NOT_NO_DIVIDENDS; LOOKUP_HTTP_403; BROWSER_RUNTIME_UNAVAILABLE',
        independent_completeness='UNKNOWN')
    return unique_events(result),coverage


def historical_prices(symbol,rows):
    """Derived executable-price units; originals untouched, volume basis remains unknown."""
    result=[]
    for b in rows:
        restored=symbol=='SCHX' and stamp(b['opened_at'])<SPLIT_DATE
        scale=Decimal(3) if restored else Decimal(1)
        result.append({**b,**{k:float(finite(b[k],True)*scale) for k in ('open','high','low','close')}})
    return result


def scan(symbol,rows,events):
    flags=[];seen=set();prior=None;returns=[];zero_volume=0;invalid=0
    dividend_dates={e['ex_date'] for e in events if e['symbol']==symbol}
    for b in rows:
        opened=stamp(b['opened_at']);closed=stamp(b['closed_at']);day=str(opened.astimezone(NY).date())
        key=(opened,closed)
        if key in seen or (prior and opened<stamp(prior['closed_at'])):raise ValueError('DUPLICATE_OR_OVERLAPPING_BAR')
        seen.add(key)
        o,h,l,c=[finite(b[k],True) for k in ('open','high','low','close')]
        if opened>=closed or h<max(o,c,l) or l>min(o,c,h):invalid+=1
        volume=finite(b['volume'])
        if volume<0:invalid+=1
        if volume==0:zero_volume+=1
        if prior:
            prev=float(prior['close']);ratio=float(o)/prev
            split=symbol=='SCHX' and stamp(prior['opened_at'])<SPLIT_DATE<=opened
            economic_ratio=ratio*3 if split else ratio
            gap=economic_ratio-1
            threshold=max(.1,8*statistics.median(returns[-20:])) if returns else .1
            if split or abs(gap)>threshold:
                flags.append(dict(opened_at=b['opened_at'],raw_gap=ratio-1,economic_gap=gap,
                    category='KNOWN_SPLIT_3_TO_1' if split else 'DISCONTINUITY_REQUIRES_REVIEW',
                    dividend_on_date=day in dividend_dates,threshold=threshold,
                    final_partition=opened>=FINAL_START,removed=False,correction='NONE'))
            if symbol=='SCHX' and stamp(prior['opened_at'])<SCHX_SPLIT_2022<=opened:
                flags.append(dict(opened_at=b['opened_at'],raw_gap=ratio-1,economic_gap=None,
                    category='DECLARED_20220311_SPLIT_2_TO_1_BASIS_REQUIRES_CORROBORATION',
                    dividend_on_date=day in dividend_dates,threshold=threshold,final_partition=False,
                    removed=False,correction='NONE; NEVER_SHIFT_SPLIT_TO_FEBRUARY'))
            returns.append(abs(gap))
        prior=b
    return dict(bar_count=len(rows),invalid_bars=invalid,zero_volume_bars=zero_volume,
        flags=flags,price_basis='SCHX_PRE_SPLIT_RESTORED_ESTIMATED' if symbol=='SCHX' else 'IBKR_TRADES_SPLITS_ONLY',
        original_volume_unchanged=True,volume_share_units='UNKNOWN',anomalies_removed=0)


def dividend_entitlements(trades,events,price_basis,as_of=None):
    """Gross receivable sidecar only: never updates strategy P&L, equity or available cash."""
    if price_basis not in ('UNADJUSTED','SPLIT_RESTORED'):
        raise ValueError('DIVIDEND_DOUBLE_COUNT_OR_UNKNOWN_PRICE_BASIS')
    as_of=date.fromisoformat(as_of) if as_of else None
    result=[]
    for t in trades:
        if t['side']!='LONG':raise ValueError('DIVIDEND_LONG_SCOPE_REQUIRED')
        start,end=stamp(t['entryAt']),stamp(t['exitAt']);q=finite(t['quantity'],True)
        if start>end:raise ValueError('DIVIDEND_POSITION_INTERVAL_INVALID')
        symbol=t['symbol'].split('_PRE_')[0].split('_POST_')[0]
        if symbol=='SCHX' and any(start<s<=end for s in (SCHX_SPLIT_2022,SPLIT_DATE)):
            raise ValueError('SPLIT_INVENTORY_ACCOUNTING_REQUIRED')
        for e in unique_events(events):
            ex=datetime.combine(date.fromisoformat(e['ex_date']),datetime.min.time(),NY).replace(hour=9,minute=30).astimezone(timezone.utc)
            # Must own before ex-date opening. Selling at that opening retains entitlement.
            if e['symbol']==symbol and start<ex<=end:
                gross=q*finite(e['amount_usd'],True)
                result.append(dict(event_id=e['event_id'],position_key=f"{t['symbol']}|{t['entryAt']}|{t['quantity']}",
                    symbol=symbol,quantity=str(q),ex_date=e['ex_date'],pay_date=e['pay_date'],
                    gross_receivable_usd=str(gross),net_receivable_usd=None,withholding_status='UNKNOWN',
                    payable_date_passed=as_of>=date.fromisoformat(e['pay_date']) if as_of else None,
                    available_cash_credit=0,broker_payment_verified=False,strategy_pnl_updated=False))
    keys=[(x['event_id'],x['position_key']) for x in result]
    if len(keys)!=len(set(keys)):raise ValueError('DUPLICATE_DIVIDEND_ENTITLEMENT')
    return result


def integrity_report(root):
    root=Path(root);folder=root/'artifacts/research/equity-operational'
    original=root/'artifacts/research/equity-evidence/readonly.json'
    data=verified_archive(original);adjusted=verified_archive(root/'artifacts/research/equity-evidence/adjusted-quality.json')
    events,coverage=load_corporate_events(root);details={};total=0
    manifest=json.loads((folder/'sources/receipts.json').read_bytes())
    for receipt in manifest:
        if receipt.get('file'):
            path=(root/receipt['file']).resolve()
            if not path.is_relative_to((folder/'sources').resolve()):raise ValueError('SOURCE_MANIFEST_PATH_OUT_OF_SCOPE')
            if file_hash(path)!=receipt['sha256']:raise ValueError('ISSUER_SOURCE_HASH_MISMATCH')
    for symbol in UNIVERSE:
        details[symbol]={}
        for tf in ('60','1440'):
            rows=data['symbols'][symbol]['bars'][tf];canonical=historical_prices(symbol,rows)
            scan_result=scan(symbol,canonical,events);total+=len(rows)
            path=folder/f'{symbol}-{tf}-split-restored.json'
            sha=save(path,dict(rows=canonical,source_sha256=file_hash(original),
                transformation='SCHX_BEFORE_20241011_OHLC_TIMES_3; VOLUME_UNCHANGED',
                transformation_status='ESTIMATED',used_for_strategy_or_final=False,
                quarantined=symbol=='SCHX',eligible_for_research=False if symbol=='SCHX' else None))
            details[symbol][tf]={**scan_result,'derived_sha256':sha,'derived_path':str(path)}
        raw={b['opened_at']:b for b in data['symbols'][symbol]['bars']['1440']}
        pairs=[(b,raw[b['opened_at']]) for b in adjusted['symbols'][symbol]['bars'] if b['opened_at'] in raw]
        details[symbol]['adjusted_comparison']=dict(paired_days=len(pairs),
            different_prices=sum(finite(a['close'])!=finite(b['close']) for a,b in pairs),
            used_for_signals_or_pnl=False,adjusted_basis='ADJUSTED_LAST_SPLITS_AND_DIVIDENDS',
            unadjusted_basis='TRADES_SPLITS_ONLY; SCHX_UNIT_RECONSTRUCTION_IS_DERIVED',
            reason='FUTURE_ADJUSTMENTS_NEVER_FEED_CAUSAL_FEATURES')
    followup=folder/'split-verification.json';split_check=None
    if followup.exists():
        check=verified_archive(followup)
        if check.get('identity_verified') is not True or check.get('account')!=data.get('account') or check['orders_sent']!=0:
            raise ValueError('SPLIT_RECHECK_PAPER_IDENTITY_REQUIRED')
        comparisons=[]
        for query in check['queries']:
            original_rows={x['opened_at']:x for x in data['symbols']['SCHX']['bars'][str(query['minutes'])]}
            paired=[(b,original_rows[b['opened_at']]) for b in query['rows'] if b['opened_at'] in original_rows]
            comparisons.append(dict(minutes=query['minutes'],paired_bars=len(paired),
                changed_ohlc=sum(any(finite(a[k])!=finite(b[k]) for k in ('open','high','low','close')) for a,b in paired),
                callback=query['callback']))
        split_check=dict(source_sha256=file_hash(followup),comparisons=comparisons,errors=check['errors'])
    # Existing, already examined selection trades ONLY; never rerun simulation or alter daily gates.
    old=json.loads((root/'artifacts/research/equity-evidence/report.json').read_bytes());entitlements=[]
    for row in old['rows']:
        if row['cost_model']=='TIERED_BASE' and row['risk_percent']==15:
            receipts=dividend_entitlements(row['selection_result']['trades'],events,'SPLIT_RESTORED',as_of='2025-01-01')
            entitlements.append(dict(strategy=row['strategy'],minutes=row['minutes'],partition='SELECTION_2024',receipts=receipts))
    report=dict(observed_at=datetime.now(timezone.utc).isoformat(),reviewed_bar_count=total,
        source_sha256=file_hash(original),adjusted_sha256=file_hash(root/'artifacts/research/equity-evidence/adjusted-quality.json'),
        instruments=details,events=events,corporate_source_coverage=coverage,
        dividend_receivable_audit=entitlements,withholding_and_broker_payments='UNKNOWN',
        economic_corporate_action_accounting_complete=False,final_holdout_sealed=True,
        schx_quarantined=True,prior_training_evidence_reliable=False,
        reason='SCHX_50_PERCENT_JUMP_20220211_PRECEDES_ISSUER_SPLIT_20220311; NO_ASSUMED_FIX',
        split_followup=split_check,
        final_strategy_outcomes_evaluated=0,strategies_recomputed=0,parameters_changed=False,
        raw_sources_manifest=manifest,orders_sent=0)
    save(folder/'data-integrity.json',report);return report
