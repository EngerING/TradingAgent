"""Authenticated Paper read boundary. No store, permissions, reservations or fills."""
from datetime import datetime,timezone,timedelta
from pathlib import Path
from .r20_profiles import digest,decimal_text,utc


def assess_market(root,raw,now,*,identity_verified):
    from .research_calendar import ForexCalendar,normalize
    from .aggressive_growth import configuration,signal
    from .aggressive_growth_runner import engine_hashes
    if identity_verified is not True:raise ValueError('EXACT_ACCOUNT_REQUIRED')
    now=utc(now);q=raw['quote'];at=utc(datetime.fromisoformat(q['at']))
    if q['source']!='IBKR_PAPER' or q['type']!='LIVE' or q['market_data_type']!=1:
        raise ValueError('AUTHENTIC_PAPER_LIVE_DATA_REQUIRED')
    if q['market_status']!='OPEN' or q.get('adapter_errors'):raise ValueError('MARKET_UNAVAILABLE')
    if not 0<=(now-at).total_seconds()<=30:raise ValueError('QUOTE_STALE_OR_FUTURE')
    bid,ask=decimal_text(q['bid']),decimal_text(q['ask'])
    if bid<=0 or ask<bid:raise ValueError('QUOTE_INVALID')
    calendar=ForexCalendar(raw['calendar']);signals={};quality={}
    if calendar.session(now) is None:raise ValueError('CALENDAR_SESSION_UNVERIFIED')
    for m in (60,240):
        original=raw['bars'][str(m)];_,audit=normalize(original,m,now,calendar)
        included={x['opened_at'] for x in audit['bars'] if x['status']=='INCLUDED_NATIVE'}
        rows=[r for r in original if r['opened_at'] in included]
        if len(rows)<50 or audit['missing_expected_openings']:raise ValueError('BARS_INCOMPLETE')
        expected=list(calendar.expected(m,datetime.fromisoformat(rows[-1]['opened_at']),now-timedelta(minutes=m)))
        if expected and expected[-1]>datetime.fromisoformat(rows[-1]['opened_at']):raise ValueError('LATEST_CLOSED_BAR_MISSING')
        signals[str(m)]=signal(configuration(root),rows,m,now)
        quality[str(m)]=dict(count=len(rows),lastClose=(datetime.fromisoformat(rows[-1]['opened_at'])+timedelta(minutes=m)).isoformat(),
            missing=audit['missing_expected_openings'],method=audit['method'])
    return dict(classification='AUTHENTIC_IBKR_READ_ONLY_DIAGNOSTIC',status='VERIFIED_AT_CUTOFF',
        at=now.isoformat(),quote=q,sourceHash=digest(raw),engineHash=engine_hashes(root),signals=signals,bars=quality,
        timestampBasis='CALLBACK_RECEIPT' if q.get('source_timestamp') is None else 'SOURCE_AND_RECEIPT',
        sourceTimestamp=q.get('source_timestamp'),entryEligible=False,brokerOrders=0,cohortStarted=False,
        blockers=['OPERATIONAL_STORE_NOT_ENABLED','COST_POLICY_NOT_APPROVED','SLIPPAGE_UNBOUNDED',
                  'FINANCING_UNBOUNDED','INCREMENTAL_MARGIN_UNKNOWN'])


def _quote_time_iso(value):
    """Normalize broker quote timestamps without accepting naive dates."""
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        parsed = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
    else:
        raise ValueError("QUOTE_TIMESTAMP_TYPE_INVALID")

    # Existing R20 UTC contract rejects naive timestamps.
    return utc(parsed).isoformat()


class PaperReadSource:
    """Reuses the protected read-only transport, with a separate diagnostic ID.

    Any failure disconnects. A subsequent poll creates a fresh session and
    verifies exact managedAccounts again. It never reuses stale cached quotes.
    """
    def __init__(self,root,client_id=195):
        if type(client_id) is not int or not 195<=client_id<=199:raise ValueError('DIAGNOSTIC_CLIENT_REQUIRED')
        self.root,self.client_id,self.wire=Path(root),client_id,None

    def close(self):
        if self.wire is not None:self.wire.disconnect();self.wire=None

    def poll(self):
        from .eurusd_exploratory_runner import ExploratoryReadIdentity
        from .ibkr_session import ExecutionMode,session_guard
        from .paper_execution_wire import execution_wire
        auth=ExploratoryReadIdentity(self.root,self.client_id)
        def deny(*a,**kw):raise PermissionError('R20_V2_READ_ONLY_NO_ORDERS')
        self.close()
        self.wire=execution_wire(auth,deny,read_only=True,session=session_guard(self.root,ExecutionMode.Research))
        try:
            identity=auth.read(management=True)
            if self.wire.connect(identity)!=[identity['account']]:raise ValueError('EXACT_ACCOUNT_REQUIRED')
            contract=self.wire.contract_details();calendar=self.wire.calendar()
            bars={str(m):self.wire.history(m) for m in (60,240)}
            quote=dict(self.wire.observe_quote())
            quote['at']=_quote_time_iso(quote.get('at'))
            at=datetime.now(timezone.utc)
            raw=dict(contract=contract,calendar=calendar,bars=bars,quote=quote,at=at.isoformat(),
                     classification='AUTHENTIC_IBKR_READ_ONLY_DIAGNOSTIC')
            view=assess_market(self.root,raw,at,identity_verified=True)
            view.update(account=auth.binding.masked_account,exactAccountMatch=True,readOnly=True,
                        requestTrace=self.wire.request_trace,clientId=self.client_id)
            return raw,view
        finally:self.close()
