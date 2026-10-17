"""Paper-only credit preview. This transport cannot place market orders or cancel.

IB's SDK spells the credit check placeOrder(whatIf=True, transmit=True). These
two flags must not be confused with an untransmitted ordinary TWS order.
"""
from dataclasses import replace
from decimal import Decimal
import threading
import re
from .stock_paper_forward_wire import stock_forward_wire
from .tws import finite

MARGIN_FIELDS=('initMarginBefore','initMarginChange','initMarginAfter',
    'maintMarginBefore','maintMarginChange','maintMarginAfter',
    'equityWithLoanBefore','equityWithLoanChange','equityWithLoanAfter')

def numeric(value):
    try:return str(finite(value))
    except (ValueError,ArithmeticError,TypeError):return None

def order_state(state,account=None):
    result={k:numeric(getattr(state,k,None)) for k in MARGIN_FIELDS}
    for new,old in (('commissionAndFees','commission'),('minCommissionAndFees','minCommission'),('maxCommissionAndFees','maxCommission')):
        result[new]=numeric(getattr(state,new,getattr(state,old,None)))
    result['commission_currency']=getattr(state,'commissionAndFeesCurrency',getattr(state,'commissionCurrency','')) or None
    result['margin_currency']=getattr(state,'marginCurrency','') or None
    result['status']=getattr(state,'status','UNKNOWN')
    result['warning_present']=bool(getattr(state,'warningText',''))
    warning=getattr(state,'warningText','') or ''
    if account:warning=warning.replace(account,'[PAPER_ACCOUNT]')
    result['warning_sanitized']=re.sub(r'\b(?:DU|U)\d+\b','[ACCOUNT]',warning)[:500] or None
    result['reject_reason_present']=bool(getattr(state,'rejectReason',''))
    result['margin_estimates_usable']=all(result[k] is not None for k in MARGIN_FIELDS) and not result['warning_present'] and not result['reject_reason_present']
    result['commission_estimate_usable']=result['commissionAndFees'] is not None and result['commission_currency']=='USD' and not result['warning_present'] and not result['reject_reason_present']
    result['classification']='ESTIMATED_IBKR_WHAT_IF_NOT_AN_EXECUTION'
    return result

def whatif_wire(options,sdk_types=None):
    if sdk_types is None:
        from ibapi.client import EClient
        from ibapi.order import Order
    else:EClient,_,_,Order,_,_=sdk_types
    base=stock_forward_wire(replace(options,read_only=True),sdk_types)
    def deny(*a,**kw):raise PermissionError('ONLY_PAPER_FORD_BUY_WHAT_IF_ALLOWED')
    class Client(type(base._client)):
        def placeOrder(self,oid,contract,order):
            wire.verify(oid,contract,order);wire._sdk_preview=True
            try:return EClient.placeOrder(self,oid,contract,order)
            finally:wire._sdk_preview=False
        def placeOrderProtoBuf(self,r):
            if not wire._sdk_preview:deny()
            # The normal SDK conversion is the only route into protobuf.
            # Explicit true is required; omitted/default whatIf is unsafe.
            if not r.HasField('order') or not r.order.whatIf or not r.order.transmit:deny()
            return EClient.placeOrderProtoBuf(self,r)
        cancelOrder=cancelOrderProtoBuf=deny
    class Preview(type(base)):
        def __init__(self):
            super().__init__();self._client=Client(self);self.preview_id=None
            self._sdk_preview=False;self._permit=None;self.preview_done=threading.Event()
            self.preview_result=None;self.preview_error=None;self.preview_calls=0
        def bind_execution(self,*a):deny()
        def verify(self,oid,contract,order):
            if self._permit is None or not self.connected or set(self.accounts)!={options.account}:deny()
            expected=self._permit;self._permit=None
            if oid!=self.preview_id or (contract.conId,contract.symbol,contract.secType,contract.currency,contract.exchange)!=(9599491,'F','STK','USD','SMART'):deny()
            if any(getattr(order,k,None)!=v for k,v in expected.items()):deny()
            self.preview_calls+=1
            if self.preview_calls!=1:deny()
        def preview(self,snapshot,price,record_attempt):
            if self.preview_id is not None:deny()
            if not self.connected or not snapshot.get('identity_verified') or not snapshot.get('complete') or snapshot['positions'] or snapshot['open_orders']:
                raise PermissionError('WHAT_IF_REQUIRES_EXACT_PAPER_COMPLETE_FLAT_SNAPSHOT')
            p=finite(price,True)
            if p>100:raise PermissionError('WHAT_IF_VIRTUAL_CAPITAL_EXCEEDED')
            self.preview_id=max(1,self.next_order_id);self.next_order_id=self.preview_id+1
            o=Order();o.account=options.account;o.action='BUY';o.totalQuantity=Decimal(1)
            o.orderType='LMT';o.lmtPrice=float(p);o.tif='DAY';o.whatIf=True;o.transmit=True
            o.outsideRth=False;o.parentId=0;o.orderRef='F-WHATIF-CREDIT-PREVIEW'
            fields=('account','action','totalQuantity','orderType','lmtPrice','tif','whatIf','transmit','outsideRth','parentId','orderRef')
            self._permit={k:getattr(o,k) for k in fields}
            c=self.contract('F');c.conId=9599491
            record_attempt(dict(request_id=self.preview_id,side='BUY',quantity=1,limit=str(p),what_if=True,
                sdk_transmit_flag=True,market_submission=False))
            self._client.placeOrder(self.preview_id,c,o)
            if not self.preview_done.wait(options.timeout):raise TimeoutError('WHAT_IF_OPEN_ORDER_TIMEOUT_NO_RETRY')
            if self.preview_error:raise self.preview_error
            if not self.connected:raise ConnectionError('WHAT_IF_CONNECTION_LOST_NO_RETRY')
            return self.preview_result
        def openOrder(self,oid,c,o,state):
            if oid!=self.preview_id:return super().openOrder(oid,c,o,state)
            if not self._check_account(o.account) or not o.whatIf or o.action!='BUY' or o.totalQuantity!=1 or (c.conId,c.symbol,c.secType,c.currency)!=(9599491,'F','STK','USD'):
                self.preview_error=PermissionError('WHAT_IF_CALLBACK_IDENTITY_OR_FLAG_CHANGED')
            else:self.preview_result={**order_state(state,options.account),'request_id':oid,'quantity':1,'side':'BUY'}
            self.preview_done.set()
        def error(self,reqId,*args):
            code=args[1] if len(args)>=3 and isinstance(args[1],int) else args[0]
            if reqId==self.preview_id:
                self.preview_error=RuntimeError('IBKR_WHAT_IF_'+str(int(code)));self.preview_done.set()
            super().error(reqId,*args)
        def connectionClosed(self):
            self.preview_error=ConnectionError('WHAT_IF_CONNECTION_LOST_NO_RETRY');self.preview_done.set()
            super().connectionClosed()
    wire=Preview();return wire
