"""EUR/USD adapter facet, retaining the existing guarded official SDK transport."""
from .paper_execution_wire import execution_wire

def capability_summary(w):
    """Additional read only. Its completion does not invent missing tags or permissions."""
    req=w.request();w.active_summary=req;w.summary_done.clear()
    from .tws import finite
    from .paper_lab import stamp
    rows=[];original=w.accountSummary;errors_before=len(w.account_errors)
    tags={'SettledCash','AvailableFunds','BuyingPower','AccountType','FullInitMarginReq','FullMaintMarginReq','DayTradesRemaining'}
    def capture(request,account,tag,value,currency):
        # The historical EUR ledger parser intentionally excludes these tags.
        # Capture this separate query before that parser, without changing it.
        if request==req and account==w.expected and tag in tags:
            try:
                parsed=str(value) if tag=='AccountType' else str(finite(value))
                rows.append(dict(source='SUMMARY_'+str(req),tag=tag,value=parsed,currency=currency,received_at=stamp()))
            except (ValueError,TypeError,ArithmeticError):w.account_errors.append('INVALID_CAPABILITY_VALUE')
        return original(request,account,tag,value,currency)
    w.accountSummary=capture
    try:
        w.client.reqAccountSummary(req,'All','SettledCash,AvailableFunds,BuyingPower,AccountType,FullInitMarginReq,FullMaintMarginReq,DayTradesRemaining')
        w.wait(w.summary_done)
        return dict(status='COMPLETE' if w.connected and not w.request_errors.get(req) and len(w.account_errors)==errors_before else 'UNKNOWN',source='IBKR_REQ_ACCOUNT_SUMMARY',rows=rows,error_codes=w.request_errors.get(req,[]))
    finally:
        w.active_summary=None;w.accountSummary=original;w.client.cancelAccountSummary(req)

def exploratory_wire(auth,gate,guard,session):
    w=execution_wire(auth,gate,intent_guard=guard,session=session)
    # Existing historical wire records limit prices but lacks auxPrice. Capture
    # it from the actual SDK callback rather than substituting the requested stop.
    stops={};original_open=w.openOrder;original_put=w.events.put
    def put(event,*args,**kw):
        if event.get('kind')=='open_order':event['stop_price']=stops.get(event['order_id'])
        return original_put(event,*args,**kw)
    def opened(oid,contract,order,state):
        stops[oid]=str(order.auxPrice)
        return original_open(oid,contract,order,state)
    w.events.put=put;w.openOrder=opened
    return w
