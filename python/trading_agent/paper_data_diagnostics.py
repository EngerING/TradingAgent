"""Interpret authentic account/market observations; missing values never become prices or cash."""
from datetime import datetime,time
from zoneinfo import ZoneInfo
from .paper_lab import num,date,stamp

ACCOUNT_FIELDS={'CashBalance','TotalCashBalance','TotalCashValue','NetLiquidation','InitMarginReq','MaintMarginReq','Currency','RealCurrency','AccountReady','SettledCash','ExchangeRate'}

def account_value(source,tag,value,currency):
    canonical=tag.removeprefix('$LEDGER-')
    if canonical not in ACCOUNT_FIELDS:return None # Includes identity-bearing AccountCode/AccountOrGroup.
    if canonical=='AccountReady':
        if value.lower() not in ('true','false'):raise ValueError('INVALID_ACCOUNT_READY')
        parsed=value.lower()
    elif canonical in ('Currency','RealCurrency'):
        if value!='BASE' and (len(value)!=3 or not value.isascii() or not value.isupper() or not value.isalpha()):raise ValueError('INVALID_CURRENCY')
        parsed=value
    else:parsed=str(num(value))
    if currency and currency!='BASE' and (len(currency)!=3 or not currency.isascii() or not currency.isupper() or not currency.isalpha()):raise ValueError('INVALID_CURRENCY')
    return {'source':source,'raw_tag':tag,'tag':canonical,'value':parsed,'currency':currency,'received_at':stamp()}

def currency_cash(rows,completed,currency='EUR',errors=(),expected_sources=None):
    completed=set(completed)
    expected=set(completed if expected_sources is None else expected_sources)
    missing=expected-completed
    complete=bool(expected) and not missing
    # Account-level valuation currency resolves BASE; ledger Currency USD is not proof of base currency.
    bases={r['currency'] for r in rows if r['source'] in completed and r['tag'] in ('NetLiquidation','TotalCashValue','InitMarginReq') and r['currency'] not in ('','BASE')}
    base=next(iter(bases)) if len(bases)==1 else None
    ready_values={r['value'] for r in rows if r['tag']=='AccountReady' and r['source'] in completed}
    ready=False if 'false' in ready_values else True if 'true' in ready_values else None
    evidence=[]
    for r in rows:
        effective=base if r['currency']=='BASE' else r['currency']
        if r['source'] in completed and effective==currency and r['tag'] in ('CashBalance','TotalCashBalance'):
            evidence.append({**r,'resolved_currency':effective})
    values={num(r['value']) for r in evidence}
    currency_rows=[r for r in rows if r['source'] in completed and
        ((base if r['currency']=='BASE' else r['currency'])==currency or r['tag'] in ('Currency','RealCurrency') and r['value']==currency)]
    result={'currency':currency,'base_currency':base,'state':'UNKNOWN','value':None,'evidence':evidence,
            'completed_sources':sorted(completed),'expected_sources':sorted(expected),'missing_sources':sorted(missing),
            'query_status':'COMPLETE' if complete and not errors else 'ERROR' if errors else 'INCOMPLETE',
            'row_status':'QUERY_INCOMPLETE' if not complete else 'ROW_PRESENT' if currency_rows else currency+'_ROW_ABSENT',
            'account_ready':ready,'reason':'CURRENCY_BALANCE_NOT_REPORTED' if currency_rows else 'CURRENCY_NOT_REPORTED'}
    if not complete:result['reason']='ACCOUNT_QUERY_INCOMPLETE'
    elif ready is False:result['reason']='ACCOUNT_NOT_READY'
    elif errors:result['reason']='ACCOUNT_DATA_ERROR'
    elif len(values)>1:result['reason']='CONFLICTING_CURRENCY_CASH'
    elif len(values)==1:
        value=next(iter(values));result.update(value=str(value),state='CONFIRMED_ZERO' if value==0 else 'EXISTING_EXPOSURE',reason='EXPLICIT_BROKER_VALUE')
    result['other_currency_exposure']=[r for r in rows if r['source'] in completed and r['currency'] not in ('','BASE',currency,base) and r['tag'] in ('CashBalance','TotalCashBalance') and num(r['value'])!=0]
    result['balance_classification']=currency+'_ZERO_CONFIRMED' if result['state']=='CONFIRMED_ZERO' else currency+'_NONZERO_CONFIRMED' if result['state']=='EXISTING_EXPOSURE' else currency+'_ROW_ABSENT' if result['row_status']==currency+'_ROW_ABSENT' and result['query_status']=='COMPLETE' and result['reason']=='CURRENCY_NOT_REPORTED' else currency+'_BALANCE_UNKNOWN'
    return result

def exposure_check(snapshot,additional,journal_orders):
    """An empty portfolio is supporting evidence, never an inferred currency cash balance."""
    cash=snapshot['cash_reconciliation'];reasons=[]
    if cash.get('query_status')!='COMPLETE':reasons.append('ACCOUNT_QUERY_INCOMPLETE')
    if cash['state']!='CONFIRMED_ZERO':reasons.append('EUR_CASH_RECONCILIATION_UNAVAILABLE')
    if cash['base_currency']!='USD':reasons.append('USD_BASE_ACCOUNT_REQUIRED_FOR_INITIAL_LAB')
    if additional.get('status')!='COMPLETE' or additional.get('errors'):reasons.append('EXPOSURE_QUERY_INCOMPLETE')
    if snapshot['orders']:reasons.append('OPEN_ORDERS_PRESENT')
    if snapshot['foreign_positions'] or snapshot.get('foreign_currency_balances'):reasons.append('FOREIGN_EXPOSURE_PRESENT')
    positions=snapshot['positions']+snapshot.get('portfolio',[])+additional.get('positions',[])
    if any(num(p['quantity'])!=0 for p in positions):reasons.append('POSITION_EXPOSURE_PRESENT')
    if journal_orders:reasons.append('JOURNAL_RECONCILIATION_REQUIRED')
    return {'status':'BLOCKED' if reasons else 'FLAT_CONFIRMED','reasons':reasons,
            'cash_row_status':cash.get('row_status','QUERY_INCOMPLETE'),'eur_balance':cash['value'],
            'automatic_cash_certification':cash['state']=='CONFIRMED_ZERO' and cash.get('query_status')=='COMPLETE'}

def session_status(hours,timezone,at):
    """Finite broker tradingHours only. No provisional weekly template or unbounded extrapolation."""
    try:
        zone=ZoneInfo(timezone);intervals=[];covered=set()
        def point(text,default_day):
            day,clock=text.split(':') if ':' in text else (default_day,text)
            local=datetime.strptime(day+clock,'%Y%m%d%H%M')
            # Fail closed for a DST-ambiguous/nonexistent wall time.
            a,b=local.replace(tzinfo=zone,fold=0),local.replace(tzinfo=zone,fold=1)
            if a.utcoffset()!=b.utcoffset() or a.astimezone(at.tzinfo).astimezone(zone).replace(tzinfo=None)!=local:raise ValueError()
            return a
        for row in hours.split(';'):
            if not row:continue
            day,periods=row.split(':',1);covered.add(datetime.strptime(day,'%Y%m%d').date())
            if periods=='CLOSED':continue
            for interval in periods.split(','):
                start,end=interval.split('-');opening,closing=point(start,day),point(end,day)
                if closing<=opening:raise ValueError()
                intervals.append((opening,closing))
                if closing.timetz().replace(tzinfo=None)!=time(0):covered.add(closing.date())
        if any(start<=at<end for start,end in intervals):return 'OPEN'
        return 'CLOSED' if at.astimezone(zone).date() in covered else 'UNKNOWN'
    except (ValueError,KeyError,TypeError):return 'UNKNOWN'

def quote_observation(data_type,fields,market_status,errors,now,adapter_errors=(),tick_count=0):
    kind={1:'LIVE',2:'FROZEN',3:'DELAYED',4:'DELAYED_FROZEN'}.get(data_type,'UNAVAILABLE')
    bid,ask=fields.get('bid'),fields.get('ask')
    reasons=[]
    if market_status=='CLOSED':reasons.append('MARKET_CLOSED')
    elif market_status!='OPEN':reasons.append('SESSION_UNVERIFIED')
    if any(c in (354,10089,10167) for c in errors):reasons.append('SUBSCRIPTION_MISSING')
    if any(c in (10168,10186) for c in errors):reasons.append('DELAYED_DATA_NOT_ENABLED')
    if 10197 in errors:reasons.append('COMPETING_SESSION')
    if kind!='LIVE':reasons.append(kind if data_type in (2,3,4) else 'DATA_TYPE_UNCONFIRMED')
    if adapter_errors or any(c in (200,320,321,322,420) for c in errors):reasons.append('ADAPTER_ERROR')
    if any(c in (2103,1100,1101,1102,1300,502,504) for c in errors):reasons.append('DATA_CONNECTION_ERROR')
    classified={354,10089,10167,10168,10186,10197,200,320,321,322,420,2103,1100,1101,1102,1300,502,504}
    if any(c not in classified for c in errors):reasons.append('BROKER_DATA_ERROR')
    if not bid or not ask:reasons.append('NO_BID_ASK_TICKS' if tick_count else 'NO_TICKS')
    elif not 0<num(bid[0])<=num(ask[0]):reasons.append('INVALID_OR_CROSSED_QUOTE')
    elif not all(0<=(now-date(v[1])).total_seconds()<=5 for v in (bid,ask)):reasons.append('STALE_TICKS')
    return {'type':kind,'market_data_type':data_type,'market_status':market_status,'bid':bid[0] if bid else None,'ask':ask[0] if ask else None,
            'at':min(bid[1],ask[1]) if bid and ask else None,'observed_at':stamp(now),'source':'IBKR_PAPER','source_timestamp':None,
            'available_for_execution':not reasons,'reasons':reasons,'error_codes':list(errors),'adapter_errors':list(adapter_errors),'tick_count':tick_count}
