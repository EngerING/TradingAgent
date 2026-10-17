"""US STK F / USD / SMART adapter. Read-only unless a durable guarded intent is bound."""
from datetime import datetime, timezone
from datetime import timedelta
from dataclasses import replace
from decimal import Decimal
import logging
import queue
import threading
from .paper_evidence_wire import observer_wire
from .paper_evidence_observer import sessions_from
from .paper_execution_wire import broker_timestamp
from .tws import finite

def stock_forward_wire(options,sdk_types=None):
    if sdk_types is None:
        from ibapi.client import EClient
        from ibapi.order import Order
        from ibapi.order_cancel import OrderCancel
        from ibapi.execution import ExecutionFilter
        base=observer_wire(replace(options,read_only=True))
    else:
        EClient,wrapper,contract,Order,OrderCancel,ExecutionFilter=sdk_types
        base=observer_wire(replace(options,read_only=True),(EClient,wrapper,contract))
    logging.getLogger('ibapi').setLevel(logging.CRITICAL)
    logging.getLogger('trading_agent.tws').setLevel(logging.CRITICAL) # retain numeric events in evidence
    ReadOnlyClient=type(base._client)
    def denied(*a,**kw):raise PermissionError('UNSCOPED_STOCK_MUTATION_DISABLED')
    class Client(ReadOnlyClient):
        def logRequest(self,*a,**kw):pass
        def useProtoBuf(self,msg_id):
            from ibapi.message import OUT
            if msg_id==OUT.CANCEL_ACCOUNT_SUMMARY and self.serverVersion()==226:return False
            return super().useProtoBuf(msg_id)
        def placeOrder(self,order_id,contract,order):
            wire.guard_order(order_id,contract,order);self._approved_place=True
            count=len(wire.order_errors)
            try:
                result=EClient.placeOrder(self,order_id,contract,order)
                if not wire.connected or len(wire.order_errors)!=count:raise ConnectionError('STOCK_SEND_UNCERTAIN_RECONCILE_REQUIRED')
                return result
            finally:self._approved_place=False
        def placeOrderProtoBuf(self,request):
            if not getattr(self,'_approved_place',False):denied()
            return EClient.placeOrderProtoBuf(self,request)
        def cancelOrder(self,order_id,cancel):
            wire.guard_cancel(order_id);self._approved_cancel=True
            try:return EClient.cancelOrder(self,order_id,cancel)
            finally:self._approved_cancel=False
        def cancelOrderProtoBuf(self,request):
            if not getattr(self,'_approved_cancel',False):denied()
            return EClient.cancelOrderProtoBuf(self,request)

    class StockForward(type(base)):
        def __init__(self):
            super().__init__();self._client=Client(self);self.guard=None;self.ledger=None
            self.next_order_id=0;self.callback_events=queue.Queue();self.order_errors=[]
            self.execution_rows={};self.fee_rows={};self._permits={};self._cancel_permits=set()
            self.orders_done=threading.Event();self.completed_done=threading.Event();self.exec_done=threading.Event()
            self.order_rows=[];self.completed_rows=[];self.ack_rows={}
        def nextValidId(self,orderId):
            self.next_order_id=max(self.next_order_id,int(orderId));super().nextValidId(orderId)
        def bind_execution(self,guard,ledger):
            if options.read_only:raise PermissionError('READ_ONLY_STOCK_INSPECTION')
            self.guard=guard;self.ledger=ledger
        def guard_order(self,order_id,contract,order):
            if options.read_only or not self.guard or not self.ledger or order_id not in self._permits:denied()
            expected,management=self._permits.pop(order_id);self.guard.grant(management=management)
            if not self.connected:raise ConnectionError('BROKER_DISCONNECTED')
            i=self.ledger.state['intent']
            if not i or i['uncertain'] or contract.conId!=i['con_id'] or (contract.symbol,contract.secType,contract.currency,contract.exchange)!=('F','STK','USD','SMART'):
                raise PermissionError('STOCK_CONTRACT_OR_INTENT_MISMATCH')
            fields=('account','action','totalQuantity','orderType','lmtPrice','auxPrice','parentId','ocaGroup','ocaType','tif','goodTillDate','orderRef','transmit','outsideRth','whatIf')
            if any(getattr(order,k,None)!=expected[k] for k in fields):raise PermissionError('STOCK_SERIALIZATION_CHANGED')
            if order.whatIf or order.outsideRth or order.account!=options.account:denied()
            self.ledger.pre_send(order_id)
        def guard_cancel(self,order_id):
            if options.read_only or not self.guard or order_id not in self._cancel_permits:denied()
            self._cancel_permits.remove(order_id);self.guard.grant(management=True)
            i=self.ledger.state['intent']
            if not self.connected or not i or i.get('last_reconciled_at') is None or str(order_id) not in i['orders']:
                raise PermissionError('CANCEL_RECONCILIATION_REQUIRED')
            self.ledger.write('CANCEL_REQUESTED',dict(order_id=order_id))
        def build(self,i,index,quantity=None,price=None):
            o=Order();o.account=options.account;o.action='BUY' if index==0 else 'SELL'
            o.totalQuantity=finite(quantity or i['quantity'],True);o.orderType='STP' if index==2 else 'LMT'
            o.tif='GTD' if index==0 else 'DAY' if index==3 else 'GTC';o.parentId=i['order_ids'][0] if index in (1,2) else 0
            if index==0:
                from .ai_strategy_researcher.contracts import at
                o.goodTillDate=(at(i['entry_session'])+timedelta(seconds=60)).strftime('%Y%m%d-%H:%M:%S')
            o.transmit=index in (2,3);o.orderRef=i['intent'];o.outsideRth=False;o.whatIf=False
            if index==2:o.auxPrice=float(finite(i['stop'],True))
            else:o.lmtPrice=float(finite(price if index==3 else i['entry'] if index==0 else i['target'],True))
            if index in (1,2):o.ocaGroup=i['intent'];o.ocaType=2
            fields=('account','action','totalQuantity','orderType','lmtPrice','auxPrice','parentId','ocaGroup','ocaType','tif','goodTillDate','orderRef','transmit','outsideRth','whatIf')
            return o,{k:getattr(o,k) for k in fields}
        def bracket(self,snapshot,plan):
            # Every admission gate has passed BEFORE reserve/SEND_PENDING.
            self.guard.admission(snapshot,plan)
            self.ledger.reserve(plan);i=self.ledger.state['intent'];contract=self.contract('F');contract.conId=i['con_id']
            try:
                for index,order_id in enumerate(i['order_ids']):
                    order,fields=self.build(i,index);self._permits[order_id]=(fields,False)
                    self._client.placeOrder(order_id,contract,order)
            except BaseException:
                i['uncertain']=True;self.ledger.suspend('BRACKET_SEND_UNCERTAIN_RECONCILE_REQUIRED');raise
        def cancel_owned(self,order_id):
            self._cancel_permits.add(order_id)
            try:self._client.cancelOrder(order_id,OrderCancel())
            finally:self._cancel_permits.discard(order_id)
        def close_owned(self,snapshot,price,reason):
            self.ledger.reconcile(snapshot);i=self.ledger.state['intent']
            if not i or finite(i['position'])==0:return
            if snapshot['open_orders'] or not i['last_reconciled_at'] or i['sell_attempted']:
                raise PermissionError('CLOSE_REQUIRES_CANCELLED_ORDERS_AND_RECONCILIATION')
            q=finite(i['position'],True)
            # Only a fresh, unequivocally owned long permits this independent
            # SELL. Children have been confirmed terminal; no concurrent exits.
            if q>finite(i['quantity']) or any(p['con_id']!=i['con_id'] and finite(p['quantity']) for p in snapshot['positions']):denied()
            from .ai_strategy_researcher.contracts import at
            stamp=datetime.now(timezone.utc);quote=snapshot.get('quote',{});session=snapshot.get('active_session')
            if not session or not at(session['start'])<=stamp<at(session['end']) or quote.get('market_data_type')!=1 or finite(price,True)!=finite(quote.get('bid'),True) or any(not 0<=(stamp-at(quote['field_received_at'][k])).total_seconds()<=15 for k in ('bid','ask')):
                raise PermissionError('CLOSE_LIVE_QUOTE_AND_AUTHENTIC_SESSION_REQUIRED')
            # Re-read positions immediately at the mutation boundary, after all
            # siblings were reconciled terminal. A changed/foreign position
            # invalidates the close rather than resizing a stale SELL silently.
            positions=[p for p in self.positions() if finite(p['quantity'])!=0]
            if not positions:return
            if len(positions)!=1 or positions[0]['con_id']!=i['con_id'] or (positions[0]['symbol'],positions[0]['security_type'],positions[0]['currency'])!=('F','STK','USD') or finite(positions[0]['quantity'])!=q:
                raise PermissionError('CLOSE_POSITION_CHANGED_RECONCILE_REQUIRED')
            if self.all_orders():raise PermissionError('CLOSE_NEW_OPEN_ORDER_RECONCILE_REQUIRED')
            i['close_id']=max(self.next_order_id,self.ledger.state['next_order_id']);self.ledger.state['next_order_id']=i['close_id']+1
            i['sell_attempted']=True;i['close_reason']=reason;self.ledger.write('OWNED_REDUCING_EXIT_PREPARED',dict(quantity=str(q)))
            o,fields=self.build(i,3,q,price);c=self.contract('F');c.conId=i['con_id'];self._permits[i['close_id']]=(fields,True)
            try:self._client.placeOrder(i['close_id'],c,o)
            except BaseException:i['uncertain']=True;self.ledger.suspend('CLOSE_SEND_UNCERTAIN_RECONCILE_REQUIRED');raise
        def error(self,reqId,*args):
            code=args[1] if len(args)>=3 and isinstance(args[1],int) else args[0]
            if reqId in self._permits or self.ledger and self.ledger.state.get('intent') and reqId in self.ledger.state['intent']['attempted']:
                if int(code) not in (2104,2106,2107,2108,2158):
                    self.order_errors.append(dict(order_id=reqId,code=int(code)));self.callback_events.put(('error',dict(order_id=reqId,code=int(code))))
            super().error(reqId,*args)
        def openOrder(self,orderId,contract,order,orderState):
            if not self._check_account(order.account):return
            row=dict(order_id=orderId,perm_id=order.permId,client_id=order.clientId,con_id=contract.conId,
                symbol=contract.symbol,security_type=contract.secType,currency=contract.currency,status=orderState.status,
                side=order.action,quantity=str(order.totalQuantity),order_ref=order.orderRef,parent_id=order.parentId,
                order_type=order.orderType,oca_group=order.ocaGroup,oca_type=order.ocaType,at=datetime.now(timezone.utc).isoformat())
            self.ack_rows[orderId]=row;self.next_order_id=max(self.next_order_id,orderId+1)
            if self.active=='stock_orders':self.order_rows.append(row)
            else:self.callback_events.put(('order',row))
        def openOrderEnd(self):self.orders_done.set()
        def orderStatus(self,orderId,status,filled,remaining,avgFillPrice,permId,parentId,lastFillPrice,clientId,whyHeld,mktCapPrice=0):
            row=self.ack_rows.get(orderId)
            if row:
                row={**row,'status':status,'filled':str(filled),'remaining':str(remaining),'perm_id':permId or row['perm_id']}
                self.ack_rows[orderId]=row;self.callback_events.put(('order',row))
            else:self.callback_events.put(('status_without_contract',dict(order_id=orderId,status=status)))
        def completedOrder(self,contract,order,orderState):
            if not self._check_account(order.account):return
            # Reuse the exact ACK serialization without treating a completed
            # response as an active order. Old unrelated historical orders are
            # retained in the inspection; runner filters only its owned refs.
            self.openOrder(order.orderId,contract,order,orderState)
            self.completed_rows.append(dict(self.ack_rows[order.orderId]))
        def completedOrdersEnd(self):self.completed_done.set()
        def execDetails(self,reqId,contract,execution):
            if not self._check_account(execution.acctNumber):return
            stamp=broker_timestamp(execution.time)
            row=dict(order_id=execution.orderId,perm_id=execution.permId,exec_id=execution.execId,order_ref=execution.orderRef,
                con_id=contract.conId,side={'BOT':'BUY','SLD':'SELL'}.get(execution.side,'UNKNOWN'),
                quantity=str(finite(execution.shares,True)),price=str(finite(execution.price,True)),at=stamp)
            if not stamp:self._invalid('EXECUTION_TIMESTAMP_UNKNOWN');return
            self.execution_rows[row['exec_id']]=row;self.callback_events.put(('fill',row))
        def execDetailsEnd(self,reqId):
            if reqId==self.request_id:self.exec_done.set()
        def commissionReport(self,r):self.fee(r.execId,r.commission,r.currency)
        def commissionAndFeesReport(self,r):self.fee(r.execId,r.commissionAndFees,r.currency)
        def fee(self,exec_id,amount,currency):
            try:amount=finite(amount)
            except (ValueError,ArithmeticError):self.callback_events.put(('commission_pending',dict(exec_id=exec_id)));return
            row=dict(exec_id=exec_id,commission=str(amount),currency=currency)
            self.fee_rows[exec_id]=row;self.callback_events.put(('fee',row))
        def all_orders(self):
            with self.lock:
                self._begin('stock_orders');self.orders_done.clear();self.order_rows=[]
                try:
                    self._client.reqAllOpenOrders()
                    if not self.orders_done.wait(options.timeout):raise TimeoutError('OPEN_ORDER_END_TIMEOUT')
                    if self.error_value:raise self.error_value
                    if not self.connected:raise ConnectionError('BROKER_DISCONNECTED')
                    return list(self.order_rows)
                finally:self.active=None
        def history(self,duration='1 Y',kind='1 day'):
            if duration!='1 Y' or kind!='1 day':raise ValueError('H40_DAILY_HISTORY_SCOPE_REQUIRED')
            with self.lock:
                self.paced();req=self._begin('stock_history');self.bar_minutes=1440
                try:
                    self._client.reqHistoricalData(req,self.contract('F'),'','1 Y','1 day','TRADES',1,2,False,[])
                    return self._wait()
                finally:self.active=None;self._client.cancelHistoricalData(req)
        def daily_context(self):
            from .ai_strategy_researcher.contracts import at
            from zoneinfo import ZoneInfo
            raw=self.history()
            with self.lock:
                self.paced();req=self._begin('stock_schedule')
                try:
                    self._client.reqHistoricalData(req,self.contract('F'),'','1 Y','1 day','SCHEDULE',1,2,False,[])
                    schedule=self._wait()
                finally:self.active=None;self._client.cancelHistoricalData(req)
            sessions={s['day']:s for s in schedule};rows=[];current=datetime.now(timezone.utc)
            for b in raw:
                session=sessions.get(b['broker_date'])
                if not session:raise PermissionError('DAILY_BAR_AUTHENTIC_SESSION_MISSING')
                zone=ZoneInfo(session['time_zone'])
                start=datetime.strptime(session['start'],'%Y%m%d-%H:%M:%S').replace(tzinfo=zone).astimezone(timezone.utc)
                end=datetime.strptime(session['end'],'%Y%m%d-%H:%M:%S').replace(tzinfo=zone).astimezone(timezone.utc)
                if current<=start:continue
                rows.append(dict(opened_at=start.isoformat(),closed_at=min(end,current).isoformat(),
                    **{k:b[k] for k in ('open','high','low','close','volume')}))
            return rows
        def snapshot(self):
            from .stock_paper_forward import CAPABILITIES
            value=dict(at=datetime.now(timezone.utc).isoformat(),identity_verified=self.connected,connected=self.connected,
                complete=False,positions=self.positions(),open_orders=self.all_orders(),completed_orders=[],executions=[],commissions=[])
            with self.lock:
                self._begin('stock_completed');self.completed_done.clear();self.completed_rows=[]
                self._client.reqCompletedOrders(False)
                if not self.completed_done.wait(options.timeout):raise TimeoutError('COMPLETED_ORDERS_END_TIMEOUT')
                if self.error_value or not self.connected:raise ConnectionError('COMPLETED_ORDERS_UNCERTAIN')
                value['completed_orders']=list(self.completed_rows);self.active=None
            with self.lock:
                req=self._begin('stock_executions');self.exec_done.clear();f=ExecutionFilter();f.acctCode=options.account
                self._client.reqExecutions(req,f)
                if not self.exec_done.wait(options.timeout):raise TimeoutError('EXEC_DETAILS_END_TIMEOUT')
                if self.error_value or not self.connected:raise ConnectionError('EXECUTIONS_UNCERTAIN')
                value['executions']=list(self.execution_rows.values());value['commissions']=list(self.fee_rows.values());self.active=None
            value['account_queries']={};rows=[]
            for mode in ('summary','ledger','updates','multi'):
                r=self.values(mode);rows.extend(r);value['account_queries'][mode]=dict(complete=True,rows=r,request_id=self.request_id)
            contract=self.contract_details('F');value['contract']=contract
            schedule=self.recent_schedule();sessions=sessions_from(contract,schedule['sessions'],datetime.now(timezone.utc))
            value['sessions']=sessions;current=datetime.now(timezone.utc)
            from .ai_strategy_researcher.contracts import at
            value['active_session']=next((s for s in sessions if at(s['start'])<=current<at(s['end'])),None)
            value['next_session_start']=next((s['start'] for s in sessions if at(s['start'])>current),None)
            value['capabilities']={k:dict(status='UNKNOWN',compatible=False,source='NOT_EXPOSED_BY_TWS_API',observed_at=current.isoformat()) for k in CAPABILITIES}
            for key,tag in (('settled_cash','SettledCash'),('available_funds','AvailableFunds')):
                matches={r['value'] for r in rows if r['tag']==tag and r['currency']=='USD'}
                if len(matches)==1:
                    amount=finite(next(iter(matches)));value['capabilities'][key]=dict(status='VERIFIED',compatible=amount>=100,value=str(amount),
                        source='IBKR_PAPER_ACCOUNT_CALLBACK',observed_at=current.isoformat(),sizing_capital=False)
            for key,field in (('whole_share_minimum','minimum_size'),('quantity_increment','size_increment')):
                v=contract[field]
                if v is not None:
                    n=finite(v,True)
                    compatible=n<=1 if field=='minimum_size' else (Decimal(1)/n)%1==0
                    value['capabilities'][key]=dict(status='VERIFIED',compatible=compatible,value=v,source='IBKR_CONTRACT_DETAILS',observed_at=current.isoformat(),fractional_permission='UNKNOWN')
            value['declared_protection']=dict(status='VERIFIED',order_types=contract['order_types'],effective_acceptance='UNKNOWN')
            value['quote']=self.sample();value.update(complete=self.connected,connected=self.connected,identity_verified=self.connected,at=datetime.now(timezone.utc).isoformat())
            return value
    wire=StockForward();return wire
