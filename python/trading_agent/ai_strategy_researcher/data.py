"""Export only already-used development prices and bounded numeric loss summaries."""
import hashlib
from statistics import mean
from pathlib import Path
from .contracts import at,encoded,number,strict_json,digest,SYMBOLS

FOLDER='artifacts/research/ai-strategy-research'
EVIDENCE_END='2024-01-01T00:00:00+00:00'
BAR_FIELDS=('opened_at','closed_at','open','high','low','close','volume')


def safe_path(root,relative):
    root=Path(root).resolve();p=root/relative
    if not p.resolve().is_relative_to(root):raise ValueError('WORKSPACE_PATH_REQUIRED')
    current=p
    while current!=root:
        if current.is_symlink():raise ValueError('LINKED_PATH_REJECTED')
        current=current.parent
    return p


def read(root,relative,verify=False,maximum=50_000_000):
    p=safe_path(root,relative)
    if p.stat().st_size>maximum:raise ValueError('ARCHIVE_TOO_LARGE')
    raw=p.read_bytes();sha=hashlib.sha256(raw).hexdigest()
    if verify and sha!=safe_path(root,str(Path(relative).with_suffix('.sha256'))).read_text().strip():
        raise ValueError('AUTHENTIC_ARCHIVE_HASH_MISMATCH')
    return strict_json(raw),sha


def write(root,relative,value):
    p=safe_path(root,relative);p.parent.mkdir(parents=True,exist_ok=True)
    raw=encoded(value)
    if p.exists() and p.read_bytes()==raw:return hashlib.sha256(raw).hexdigest()
    temp=safe_path(root,relative+'.tmp');temp.write_bytes(raw);temp.replace(p)
    sha=hashlib.sha256(raw).hexdigest();safe_path(root,str(Path(relative).with_suffix('.sha256'))).write_text(sha,encoding='ascii')
    return sha


def prepare(root):
    data,sha=read(root,'artifacts/research/equity-evidence/readonly.json',True)
    integrity,quality_sha=read(root,'artifacts/research/equity-operational/data-integrity.json')
    if data.get('identity_verified') is not True or data.get('orders_sent')!=0 or integrity.get('source_sha256')!=sha:
        raise ValueError('AUTHENTIC_PAPER_PRICE_ARCHIVE_REQUIRED')
    if integrity.get('schx_quarantined') is not True:raise ValueError('REVIEW_CURRENT_DATA_POLICY')
    old,old_sha=read(root,'artifacts/research/equity-evidence/report.json')
    series={};spreads={}
    for symbol in SYMBOLS:
        s=data['symbols'][symbol];series[symbol]={}
        for tf in ('60','1440'):
            if integrity['instruments'][symbol][tf]['invalid_bars']:
                raise ValueError('INVALID_DEVELOPMENT_BARS')
            series[symbol][tf]=[{k:b[k] for k in BAR_FIELDS} for b in s['bars'][tf]
                if at('2021-01-01T00:00:00Z')<=at(b['opened_at']) and at(b['closed_at'])<at(EVIDENCE_END)]
            if not 100<=len(series[symbol][tf])<=20000:raise ValueError('DEVELOPMENT_COVERAGE_REQUIRED')
        quote=s.get('quote',{})
        try:
            bid,ask=number(quote['bid']),number(quote['ask'])
            if not 0<bid<=ask:raise ValueError('QUOTE_INVALID')
            spreads[symbol]=float((ask-bid)/((ask+bid)/2))
        except (KeyError,ValueError,TypeError):spreads[symbol]=None
    failures=[]
    allowed={'EQ_TREND_R0','EQ_PULLBACK_R0','EQ_BREAKOUT_R0','EQ_MEAN_REVERSION_R0'}
    for row in old['rows']:
        if row['strategy'] in allowed and row['cost_model']=='TIERED_BASE' and row['risk_percent']==15:
            m=row['selection_result']['metrics']
            fields=('admitted','gross_pnl','net_pnl','net_expectancy','win_rate','average_profit','average_loss',
                'commissions','spread_slippage','maximum_drawdown','risk_budget_breaches')
            failures.append(dict(evidence_id=f"previous_{row['strategy']}_{row['minutes']}",
                version=row['version'],partition='PREVIOUSLY_EXAMINED_SELECTION_2024',
                metrics={k:float(number(m[k])) if m.get(k) is not None else None for k in fields},
                reliable_for_new_validation=False))
    package=dict(schema_version=1,mode='SIMULATION_ONLY',series=series,spread_ratios=spreads,
        source_hashes=dict(prices=sha,quality=quality_sha,previous_research=old_sha),
        development_start='2021-01-01T00:00:00+00:00',development_end=EVIDENCE_END,
        final_holdout_sealed=True,final_data_exported=False,quarantined_symbols=['SCHX'],
        corporate_action_coverage='INCOMPLETE_NO_DIVIDEND_CREDIT',
        broker_constraints={k:'UNKNOWN' for k in ('permissions','fractional','effective_fees','settled_cash',
            'margin_intraday','effective_protection','historical_liquidity')},
        limitations=['ALREADY_EXAMINED_DEVELOPMENT_NOT_INDEPENDENT_OOS',
            'FIXED_SURVIVING_UNIVERSE','CORPORATE_ACTIONS_INCOMPLETE','IBKR_CAPABILITIES_UNKNOWN',
            'NO_FRACTIONAL_FALLBACK','DIVIDENDS_TAX_INTEREST_NOT_CREDITED','PRODUCTION_STOCK_EXECUTOR_ABSENT'],
        previous_failures=failures)
    write(root,FOLDER+'/dataset.json',package)
    return package


def load_dataset(root):
    p,sha=read(root,FOLDER+'/dataset.json',True,20_000_000)
    if p.get('mode')!='SIMULATION_ONLY' or p.get('final_holdout_sealed') is not True or p.get('final_data_exported') is not False:
        raise ValueError('SEALED_DEVELOPMENT_PACKAGE_REQUIRED')
    if set(p['series'])!=set(SYMBOLS):raise ValueError('QUARANTINE_SCOPE_REQUIRED')
    for symbol,tfs in p['series'].items():
        if set(tfs)!={'60','1440'}:raise ValueError('TIMEFRAME_SCOPE_REQUIRED')
        for rows in tfs.values():
            if not 100<=len(rows)<=20000:raise ValueError('DATA_SIZE_REQUIRED')
            for b in rows:
                if set(b)!=set(BAR_FIELDS) or not at(p['development_start'])<=at(b['opened_at'])<at(b['closed_at'])<at(EVIDENCE_END):
                    raise ValueError('FINAL_OR_SELECTION_DATA_FORBIDDEN')
    # Also prevent stale, quietly regenerated source evidence from resuming a bound session.
    expected={'prices':'artifacts/research/equity-evidence/readonly.json',
        'quality':'artifacts/research/equity-operational/data-integrity.json',
        'previous_research':'artifacts/research/equity-evidence/report.json'}
    for kind,path in expected.items():
        if hashlib.sha256(safe_path(root,path).read_bytes()).hexdigest()!=p['source_hashes'][kind]:
            raise ValueError('SOURCE_EVIDENCE_CHANGED_REPREPARE_REQUIRED')
    return p,sha


def context(package,history,memory=None):
    prices={}
    for symbol,tfs in package['series'].items():
        prices[symbol]={tf:dict(bars=len(rows),first_at=rows[0]['opened_at'],last_at=rows[-1]['closed_at'],
            first_close=rows[0]['close'],last_close=rows[-1]['close'],
            annual_summary={year:dict(
                first_close=float(number(part[0]['close'])),last_close=float(number(part[-1]['close'])),
                closing_return=float(number(part[-1]['close'])/number(part[0]['close'])-1),
                mean_intrabar_range_ratio=mean(float((number(b['high'])-number(b['low']))/number(b['close'])) for b in part))
                for year in ('2021','2022','2023') if (part:=[b for b in rows if b['opened_at'].startswith(year)])})
                for tf,rows in tfs.items()}
    result=dict(mode='SIMULATION_ONLY',capital_usd=100,exposure=1,loss_budget_usd=20,
        risk_percent_grid=[1,2,3,5,7.5,10,12.5,15],policy='WIN_TO_CONTINUE / FIRST_LOSS_STOPS_DAY',
        prices=prices,previous_failures=package['previous_failures'],
        limitations=package['limitations'],broker_constraints=package['broker_constraints'],
        evidence_ids=['authentic_development_prices','data_integrity_773']+
            [x['evidence_id'] for x in package['previous_failures']],
        prior_experiments=history[-5:],final_holdout='SEALED_NOT_ACCESSIBLE')
    if memory is not None:
        result['research_memory']=memory
        result['evidence_ids'] += [r['evidence_id'] for r in memory['records']]
        result['evidence_ids'] += [r['evidence_id'] for r in memory.get('specifications',[])]
        result['evidence_ids'] += [r['evidence_id'] for r in memory.get('deferred_decisions',[])]
        result['evidence_ids'] += [r['evidence_id'] for r in memory.get('execution_observations',[])]
        result['evidence_ids'] += [r['evidence_id'] for r in memory.get('simulation_observations',[])]
        result['evidence_ids']=list(dict.fromkeys(result['evidence_ids']))
    return result
