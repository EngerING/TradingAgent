"""Separate official IBKR Paper order adapter. Every mutation requires the protected grant and a durable intent."""
from decimal import Decimal
from datetime import datetime,timezone,timedelta
import logging
import queue
import threading
import time
from zoneinfo import ZoneInfo
from .paper_lab import num,stamp,utc,date,key
from .paper_data_diagnostics import account_value,currency_cash,session_status,quote_observation

def broker_timestamp(raw):
    try:
        day,hour,zone=raw.split()
        if len(day)!=8 or not day.isdigit():return None
        local=datetime.strptime(day+' '+hour,'%Y%m%d %H:%M:%S').replace(tzinfo=ZoneInfo(zone))
        if local.utcoffset()!=local.replace(fold=1).utcoffset():return None
        return stamp(local.astimezone(timezone.utc))
    except (ValueError,TypeError,KeyError):return None


class PaperOrderBuilder:
    """Serialize approved geometry/quantity unchanged. Has no sizing authority."""
    def __init__(self,order_type):self.order_type=order_type
    def build(self,o,index,a,quantity=None,close_price=None):
        r=self.order_type();r.account=a['account'];r.totalQuantity=num(quantity or o['quantity']);r.action='BUY' if index==0 else 'SELL'
        r.orderType='STP' if index==2 else 'LMT';r.tif='GTC' if index else 'DAY';r.orderRef=o['intent']
        r.parentId=0 if index==0 else o['order_ids'][0];r.transmit=index==2
        if index==2:r.auxPrice=float(num(o['stop']))
        else:r.lmtPrice=float(num(close_price if close_price is not None else o['entry'] if index==0 else o['target']))
        if index:r.ocaGroup=o['intent'];r.ocaType=2
        fields={f:getattr(r,f) for f in ('account','totalQuantity','action','orderType','tif','orderRef','parentId','transmit','lmtPrice','auxPrice','ocaGroup','ocaType')}
        return r,fields


def execution_wire(authorization,gate,sdk_types=None,*,read_only=False,intent_guard=None,session=None):
    logging.getLogger('ibapi').setLevel(logging.CRITICAL)
    if sdk_types is None:
        from ibapi.client import EClient
        from ibapi.wrapper import EWrapper
        from ibapi.contract import Contract
        from ibapi.order import Order
        from ibapi.order_cancel import OrderCancel
        from ibapi.execution import ExecutionFilter
    else:EClient,EWrapper,Contract,Order,OrderCancel,ExecutionFilter=sdk_types
    from ibapi.message import OUT
    def blocked(*args,**kwargs):raise PermissionError('UNSCOPED_MUTATION_DISABLED')
    class Client(EClient):
        def useProtoBuf(self,msg_id):
            # Observed with API 226 / SDK 10.50.2: protobuf summary cancellation
            # leaves subscriptions active; the official legacy cancellation releases them.
            # Keep every other request and all order transport on its negotiated protocol.
            if msg_id==OUT.CANCEL_ACCOUNT_SUMMARY and self.serverVersion()==226:return False
            return super().useProtoBuf(msg_id)
        reqGlobalCancel=reqGlobalCancelProtoBuf=exerciseOptions=exerciseOptionsProtoBuf=blocked
        replaceFA=replaceFAProtoBuf=reqAutoOpenOrders=reqAutoOpenOrdersProtoBuf=blocked
        updateDisplayGroup=updateConfig=blocked
        def logRequest(self,*args,**kwargs):pass  # Official request logs can contain complete account IDs.
        def placeOrder(self,order_id,contract,order):
            if read_only:raise PermissionError('READ_ONLY_DIAGNOSTIC_NO_ORDERS')
            wire.guard(order_id,contract,order)
            self._approved_place=True
            previous_errors=len(wire.request_errors.get(order_id,[]))
            try:
                result=super().placeOrder(order_id,contract,order)
                # EClient catches serializer/socket exceptions and calls error()
                # instead of raising. Do not send remaining bracket legs blindly.
                if getattr(wire,'read_only_detected',False):raise PermissionError('PAPER_AUTO_BLOCKED: TWS API is read-only.')
                if len(wire.request_errors.get(order_id,[]))>previous_errors or not wire.connected:
                    raise ConnectionError('PAPER_SDK_SEND_UNCERTAIN_RECONCILE_REQUIRED')
                wire.session.event('ORDER_SUBMITTED',order_id=order_id)
                return result
            finally:self._approved_place=False
        def placeOrderProtoBuf(self,request):
            if read_only:raise PermissionError('READ_ONLY_DIAGNOSTIC_NO_ORDERS')
            if not getattr(self,'_approved_place',False):raise PermissionError('RAW_PROTOBUF_ORDER_DISABLED')
            return super().placeOrderProtoBuf(request)
        def cancelOrder(self,order_id,order_cancel):
            if read_only:raise PermissionError('READ_ONLY_DIAGNOSTIC_NO_ORDERS')
            wire.guard_cancel(order_id);self._approved_cancel=True
            try:return super().cancelOrder(order_id,order_cancel)
            finally:self._approved_cancel=False
        def cancelOrderProtoBuf(self,request):
            if read_only:raise PermissionError('READ_ONLY_DIAGNOSTIC_NO_ORDERS')
            if not getattr(self,'_approved_cancel',False):raise PermissionError('RAW_PROTOBUF_CANCEL_DISABLED')
            return super().cancelOrderProtoBuf(request)
    class Wire(EWrapper):
        def __init__(self):
            super().__init__();self.client=Client(self);self.events=queue.Queue();self.ready=threading.Event();self.accounts_ready=threading.Event()
            self.positions_done=threading.Event();self.orders_done=threading.Event();self.exec_done=threading.Event();self.completed_done=threading.Event();self.summary_done=threading.Event();self.contract_done=threading.Event()
            self.verified=False;self.next_order_id=0;self.approved={};self.cancel_approved=set();self.quote_data={};self.data_type=0;self.thread=None
            self.request_id=6000;self.active_execution=None;self.active_summary=None;self.active_contract=None;self.active_quote=None
            self.unavailable_fees=set()
            self.account_rows=[];self.account_completed=set();self.account_errors=[];self.active_updates=False;self.active_multi=None
            self.updates_done=threading.Event();self.multi_done=threading.Event();self.request_errors={};self.trading_session=None
            self.quote_adapter_errors=[];self.quote_tick_count=0;self.quote_family={};self.api_events=[];self.position_rows=[]
            self.market_farm_down=False
            self.request_trace=[]
            self.bracket_attempts=set();self.close_attempts=set();self.cancel_attempts=set();self.mutation_records={}
            self.history_done=threading.Event();self.active_history=None;self.history_rows=[];self.last_history_request=0
            self.schedule_done=threading.Event();self.active_schedule=None;self.schedule_rows=[];self.schedule_received_at=None
            self.portfolio_rows=[];self.account_expected=set();self.positions_multi_done=threading.Event();self.active_positions_multi=None;self.multi_positions=[];self.exposure_errors=[]
            self.session=session
            self.session_events=[]
            if self.session:
                audit=self.session.emit
                def emit(event):
                    audit(event);self.session_events.append(event)
                    self.session_events=self.session_events[-100:]
                self.session.emit=emit
            self.order_builder=PaperOrderBuilder(Order)
        def ensure_session(self,a):
            if self.session is None:
                from .ibkr_session import AccountBinding,IbkrSessionGuard,SessionConfiguration,ExecutionMode
                self.session=IbkrSessionGuard(AccountBinding.from_attestation(a),
                    SessionConfiguration(a.get('host','127.0.0.1'),a['port']),
                    ExecutionMode.Research if read_only else ExecutionMode.PaperAuto,
                    emit=self.session_events.append)
                # Compatibility for SDK serialization fakes with an already
                # verified transport. Production establishes this in connect.
                if self.connected:self.session.verify_connected(a,[self.expected])
            return self.session
        def assert_mutation_allowed(self,a,management=False):
            self.ensure_session(a).authorize_mutation(a,connected=self.connected,management=management)
        def request(self):
            self.request_id+=1;return self.request_id
        @property
        def connected(self):return self.verified and self.client.isConnected()
        def connect(self,a):
            session=self.ensure_session(a);session.validate_grant(a)
            if not self.client.isConnected():
                self.ready.clear();self.client.connect(session.configuration.host,session.configuration.port,a['client_id'])
                self.thread=threading.Thread(target=self.client.run,daemon=True);self.thread.start();self.wait(self.ready)
            self.verified=False;self.accounts_ready.clear();self.expected=a['account'];self.client.reqManagedAccts();self.wait(self.accounts_ready)
            try:session.verify_connected(a,self.accounts)
            except PermissionError:self.disconnect();raise
            self.verified=True;return self.accounts
        def disconnect(self):
            self.verified=False;self.client.disconnect()
            if self.session:self.session.disconnected()
            if self.thread and self.thread is not threading.current_thread():self.thread.join(timeout=2)
        def wait(self,event):
            names={'ready':('CONNECT','nextValidId',None),'accounts_ready':('reqManagedAccts','managedAccounts',None),
                'orders_done':('reqAllOpenOrders','openOrderEnd',None),'positions_done':('reqPositions','positionEnd',None),
                'exec_done':('reqExecutions','execDetailsEnd',self.active_execution),'completed_done':('reqCompletedOrders','completedOrdersEnd',None),
                'summary_done':('reqAccountSummary','accountSummaryEnd',self.active_summary),'updates_done':('reqAccountUpdates','accountDownloadEnd',None),
                'multi_done':('reqAccountUpdatesMulti','accountUpdateMultiEnd',self.active_multi),
                'positions_multi_done':('reqPositionsMulti','positionMultiEnd',self.active_positions_multi),
                'contract_done':('reqContractDetails','contractDetailsEnd',self.active_contract),'history_done':('reqHistoricalData','historicalDataEnd',self.active_history),
                'schedule_done':('reqHistoricalData_SCHEDULE','historicalSchedule',self.active_schedule)}
            request,callback,req=next((v for k,v in names.items() if getattr(self,k) is event),('UNKNOWN','UNKNOWN',None))
            record={'request':request,'callback_expected':callback,'request_id':req,'started_at':stamp(),'result':'WAITING'}
            self.request_trace.append(record);self.request_trace=self.request_trace[-100:];started=time.monotonic()
            remaining=10
            deadline=getattr(self,'operation_deadline_at',None)
            if deadline:remaining=min(remaining,max(0,(date(deadline)-utc()).total_seconds()))
            try:
                finished=event.wait(remaining)
                codes=self.request_errors.get(req,[]) if req is not None else []
                if event is self.summary_done and codes:
                    record.update(result='BROKER_ERROR',error_codes=list(codes));raise PermissionError('PAPER_ACCOUNT_SUMMARY_REQUEST_FAILED')
                if not finished:
                    record['result']='TIMEOUT';raise TimeoutError('PAPER_API_TIMEOUT')
                record['result']='COMPLETE'
            finally:
                record.update(finished_at=stamp(),elapsed_seconds=round(time.monotonic()-started,4),
                    socket_connected=self.client.isConnected(),identity_verified=self.verified)
        def read_diagnostics(self):
            return {'request_trace':[dict(r) for r in self.request_trace],'api_events':[dict(e) for e in self.api_events],
                'session_events':[dict(e) for e in self.session_events],
                'socket_connected':self.client.isConnected(),'identity_verified':self.verified}
        def nextValidId(self,orderId):self.next_order_id=max(self.next_order_id,orderId);self.ready.set()
        def managedAccounts(self,value):
            self.accounts=[v.strip() for v in value.split(',') if v.strip()];self.accounts_ready.set()
            if hasattr(self,'expected') and self.accounts!=[self.expected]:
                self.verified=False
                if self.session:
                    self.session.event('ACCOUNT_BINDING_FAILED');self.session.disconnected()
        def connectionClosed(self):
            self.verified=False
            if self.session:self.session.disconnected()
            self.events.put({'kind':'disconnect','at':stamp()})
        def error(self,reqId,*args):
            code=args[1] if len(args)>=3 and isinstance(args[1],int) else args[0]
            message=args[2] if len(args)>=3 else args[1] if len(args)>1 else ''
            self.api_events.append({'request_id':reqId,'code':int(code),'received_at':stamp()});self.api_events=self.api_events[-100:]
            self.request_errors.setdefault(reqId,[]).append(int(code))
            # A rejected summary will never deliver accountSummaryEnd; surface the error now.
            if reqId==self.active_summary:self.summary_done.set()
            if code==2103:self.market_farm_down=True
            elif code==2104:self.market_farm_down=False
            if code==2101 and self.active_updates:self.account_errors.append('ACCOUNT_SUBSCRIPTION_CONFLICT');self.updates_done.set()
            active_read=reqId in {self.active_quote,self.active_summary,self.active_contract,self.active_multi,self.active_positions_multi,self.active_history,self.active_schedule} or self.active_updates and reqId==-1
            if 'read-only' in str(message).lower() or 'read only' in str(message).lower():
                if self.session:self.session.detected_read_only()
                self.read_only_detected=True;self.events.put({'kind':'readonly','at':stamp()})
            if code in (1100,1101,1102,1300,502,504,326):
                self.verified=False
                if self.session:self.session.disconnected()
                self.events.put({'kind':'disconnect','at':stamp()})
            elif not active_read and code not in (2100,2103,2104,2106,2107,2108,2158):self.events.put({'kind':'reject','order_id':reqId,'code':int(code),'at':stamp()})
        def contract(self):
            c=Contract();c.conId=12087792;c.symbol='EUR';c.currency='USD';c.secType='CASH';c.exchange='IDEALPRO';return c
        def guard(self,order_id,contract,order):
            permit=self.approved.get(order_id)
            if permit is None:raise PermissionError('ORDER_NOT_DURABLY_REGISTERED')
            a=authorization.read(management=permit['management']);gate(management=permit['management'])
            if getattr(self,'read_only_detected',False):raise PermissionError('PAPER_AUTO_BLOCKED: TWS API is read-only.')
            self.assert_mutation_allowed(a,permit['management'])
            if intent_guard is None:raise PermissionError('UNBOUND_EXECUTION_INTENT')
            intent_guard(permit['order'],permit['role'],order_id,permit['remaining_quantity'])
            if not self.connected or a['account']!=self.expected or order.account!=a['account'] or (contract.conId,contract.symbol,contract.currency,contract.secType,contract.exchange)!=(12087792,'EUR','USD','CASH','IDEALPRO'):
                raise PermissionError('PAPER_ORDER_SCOPE_MISMATCH')
            if permit['role']=='RECOVERY_CLOSE':
                if a.get('mode')!='RecoveryClose' or a.get('scope')!='RECOVERY_CLOSE_ONLY':raise PermissionError('RECOVERY_AUTHORIZATION_REQUIRED')
                self.validate_quote(permit['order']['quote'])
                if order.action!='SELL' or order.orderType!='LMT' or order.tif!='IOC' or order.parentId!=0 or not order.transmit or order.ocaGroup:
                    raise PermissionError('RECOVERY_REDUCE_ONLY_SCOPE_INVALID')
                for field,value in permit['fields'].items():
                    if getattr(order,field,None)!=value:raise PermissionError('RECOVERY_PAYLOAD_CHANGED')
                if not 0<num(order.totalQuantity)<=num(a['max_quantity']):raise PermissionError('RECOVERY_QUANTITY_OUTSIDE_AUTHORIZATION')
                return
            if a.get('mode')=='RecoveryClose':raise PermissionError('RECOVERY_CLOSE_ONLY')
            o=permit['order'];index=o['order_ids'].index(order_id)
            if order.action!=('BUY' if index==0 else 'SELL') or order.orderType!=('STP' if index==2 else 'LMT') or order.orderRef!=o['intent'] or order.parentId!=(0 if index==0 else o['order_ids'][0]):
                raise PermissionError('ORDER_ROLE_OR_PARENT_CHANGED')
            if index and (order.ocaGroup!=o['intent'] or order.ocaType!=2):raise PermissionError('PROTECTION_LINK_CHANGED')
            self.validate_quote(o['closing_quote'] if permit['role']=='OWNED_CLOSE' else o['quote'])
            already=sum((num(e['quantity']) for e in o['fills'].values() if e['order_id']==order_id),Decimal(0))
            expected_quantity=num(o['quantity']) if permit['role']!='OWNED_CLOSE' else num(permit['remaining_quantity'])+already
            expected_price=num(o['stop'] if index==2 else o['entry'] if index==0 else o['target'])
            if permit['role']=='OWNED_CLOSE':expected_price=num(o['closing_quote']['bid'])//Decimal('0.00005')*Decimal('0.00005')
            if (num(order.totalQuantity)!=expected_quantity or
                (order.auxPrice if index==2 else order.lmtPrice)!=float(expected_price) or
                order.transmit!=(index==2 or permit['role']=='OWNED_CLOSE')):
                raise PermissionError('ORDER_QUANTITY_PRICE_OR_TRANSMISSION_CHANGED')
            expected=permit['fields']
            for field,value in expected.items():
                if getattr(order,field,None)!=value:raise PermissionError('ORDER_PAYLOAD_CHANGED')
            if order.orderType not in a['order_types'] or not 0<num(order.totalQuantity)<=num(a['max_quantity']):raise PermissionError('ORDER_LIMIT_EXCEEDED')
        def guard_cancel(self,order_id):
            a=authorization.read(management=True);gate(management=True)
            self.assert_mutation_allowed(a,management=True)
            if not self.connected or order_id not in self.cancel_approved:raise PermissionError('PROTECTIVE_OR_FOREIGN_CANCEL_DISABLED')
            if intent_guard is None:raise PermissionError('UNBOUND_EXECUTION_INTENT')
            intent_guard(self.mutation_records[order_id],'CANCEL_PARENT',order_id)
        def make_order(self,o,index,a,quantity=None,close_price=None):
            return self.order_builder.build(o,index,a,quantity,close_price)
        def bracket(self,o,a):
            if o['intent'] in self.bracket_attempts:raise PermissionError('BRACKET_ALREADY_ATTEMPTED')
            if len(o['order_ids'])!=3 or len(set(o['order_ids']))!=3 or o.get('fills'):
                raise PermissionError('BRACKET_SCOPE_INVALID')
            self.bracket_attempts.add(o['intent'])
            for i,order_id in enumerate(o['order_ids']):
                r,fields=self.make_order(o,i,a)
                self.approved[order_id]={'management':False,'fields':fields,'order':o,
                    'role':'BRACKET_ENTRY' if i==0 else 'BRACKET_PROTECTION','remaining_quantity':num(o['quantity'])}
                try:self.client.placeOrder(order_id,self.contract(),r)
                finally:self.approved.pop(order_id,None)
        def cancel_parent(self,o):
            if o['intent'] in self.cancel_attempts:raise PermissionError('CANCEL_ALREADY_ATTEMPTED_RECONCILE_REQUIRED')
            self.cancel_attempts.add(o['intent'])
            order_id=o['order_ids'][0];self.cancel_approved.add(order_id);self.mutation_records[order_id]=o
            try:self.client.cancelOrder(order_id,OrderCancel())
            finally:self.cancel_approved.discard(order_id);self.mutation_records.pop(order_id,None)
        def close_owned(self,o,quantity,quote,a):
            self.validate_quote(quote)
            buys=num(0);sells=num(0)
            for e in o['fills'].values():
                if (e['client_id']!=82 or e['contract_id']!=12087792 or e['order_id'] not in o['order_ids'] or
                    e['side']!=('BUY' if e['order_id']==o['order_ids'][0] else 'SELL')):
                    raise PermissionError('UNRECOGNIZED_CLOSE_INVENTORY')
                if e['side']=='BUY':buys+=num(e['quantity'])
                else:sells+=num(e['quantity'])
            if quantity<=0 or quantity!=buys-sells or buys>num(o['quantity']):raise PermissionError('NO_EXACT_OWNED_POSITION_TO_CLOSE')
            if o['statuses'].get(str(o['order_ids'][0])) not in ('Filled','Cancelled','ApiCancelled'):
                raise PermissionError('PARENT_REMAINDER_UNRESOLVED')
            if o['intent'] in self.close_attempts:raise PermissionError('CLOSE_ALREADY_ATTEMPTED_RECONCILE_REQUIRED')
            self.close_attempts.add(o['intent'])
            # Existing TP modification retains parent and OCA linkage; no additional sell order is created.
            already=sum((num(e['quantity']) for e in o['fills'].values() if e['order_id']==o['order_ids'][1]),Decimal(0))
            order_id=o['order_ids'][1];r,fields=self.make_order(o,1,a,quantity+already,num(quote['bid'])//Decimal('0.00005')*Decimal('0.00005'));r.transmit=True;fields['transmit']=True
            o.setdefault('closing_quote',quote) # The persisted intent guard checks production close authorization.
            self.approved[order_id]={'management':True,'fields':fields,'order':o,'role':'OWNED_CLOSE','remaining_quantity':quantity}
            try:self.client.placeOrder(order_id,self.contract(),r)
            finally:self.approved.pop(order_id,None)
        def recovery_close(self,record,a):
            """One authorized IOC exit; never replace cancelled diagnostic children."""
            token=record['authorization_id']
            if token in self.close_attempts:raise PermissionError('RECOVERY_ALREADY_ATTEMPTED_RECONCILE_REQUIRED')
            self.close_attempts.add(token)
            r=Order();r.account=a['account'];r.action='SELL';r.orderType='LMT';r.tif='IOC'
            r.totalQuantity=num(record['quantity']);r.lmtPrice=float(num(record['price']))
            r.parentId=0;r.orderRef=record['reference'];r.transmit=True;r.ocaGroup='';r.ocaType=0
            fields={f:getattr(r,f) for f in ('account','totalQuantity','action','orderType','tif','orderRef','parentId','transmit','lmtPrice','auxPrice','ocaGroup','ocaType')}
            order_id=record['order_id']
            self.approved[order_id]={'management':False,'fields':fields,'order':record,'role':'RECOVERY_CLOSE','remaining_quantity':num(record['quantity'])}
            try:self.client.placeOrder(order_id,self.contract(),r)
            finally:self.approved.pop(order_id,None)
        def openOrder(self,orderId,contract,order,orderState):
            if order.account!=self.expected:self.events.put({'kind':'disconnect','at':stamp()});self.verified=False;return
            e={'kind':'open_order','order_id':orderId,'perm_id':order.permId,'client_id':order.clientId,'contract_id':contract.conId,
                'status':orderState.status,'side':order.action,'quantity':str(order.totalQuantity),'order_type':order.orderType,
                'parent_id':order.parentId,'oca_group':order.ocaGroup,'oca_type':order.ocaType,'reference':order.orderRef,'at':stamp(),
                'tif':getattr(order,'tif',''),'limit_price':str(getattr(order,'lmtPrice','')),
                'initial_margin_change':str(getattr(orderState,'initMarginChange',''))}
            if getattr(self,'collect_open',False):self.open_orders.append(e)
            self.events.put(e);self.next_order_id=max(self.next_order_id,orderId+1)
            if self.session:self.session.event('ORDER_ACKNOWLEDGED',order_id=orderId,perm_id=order.permId)
        def openOrderEnd(self):self.orders_done.set()
        def orderStatus(self,orderId,status,filled,remaining,avgFillPrice,permId,parentId,lastFillPrice,clientId,whyHeld,mktCapPrice):
            self.events.put({'kind':'status','order_id':orderId,'status':status,'filled':str(filled),'remaining':str(remaining),'perm_id':permId,'why_held':bool(whyHeld),'at':stamp()})
            if self.session:
                event='ORDER_CANCELLED' if status in ('Cancelled','ApiCancelled') else 'ORDER_FILLED' if status=='Filled' else 'ORDER_PARTIALLY_FILLED' if num(filled)>0 and num(remaining)>0 else 'ORDER_ACKNOWLEDGED'
                self.session.event(event,order_id=orderId,perm_id=permId,filled=str(filled),remaining=str(remaining))
        def execDetails(self,reqId,contract,execution):
            if execution.acctNumber!=self.expected:self.verified=False;self.events.put({'kind':'disconnect','at':stamp()});return
            self.events.put({'kind':'fill','exec_id':execution.execId,'order_id':execution.orderId,'perm_id':execution.permId,'client_id':execution.clientId,
                'contract_id':contract.conId,'side':{'BOT':'BUY','SLD':'SELL'}.get(execution.side,execution.side),'quantity':str(num(execution.shares)),
                'price':str(num(execution.price)),'broker_time_raw':execution.time,'broker_at':broker_timestamp(execution.time),'at':stamp()})
        def execDetailsEnd(self,reqId):
            if reqId==self.active_execution:self.exec_done.set()
        def commissionAndFeesReport(self,r):self.fee(r.execId,r.commissionAndFees,r.currency)
        def commissionAndFeesReportProtoBuf(self,r):
            if not r.HasField('commissionAndFees') or not r.HasField('currency'):
                self.unavailable_fees.add(r.execId)
                self.events.put({'kind':'commission_unavailable','exec_id':r.execId,'at':stamp()})
            else:self.unavailable_fees.discard(r.execId)
        def commissionReport(self,r):self.fee(r.execId,r.commission,r.currency)
        def fee(self,execution_id,amount,currency):
            if execution_id in self.unavailable_fees:return
            try:value=num(amount)
            except (ValueError,ArithmeticError):
                self.events.put({'kind':'commission_unavailable','exec_id':execution_id,'at':stamp()});return
            self.events.put({'kind':'commission','exec_id':execution_id,'amount':str(value),'currency':currency,'at':stamp()})
        def position(self,account,contract,pos,avgCost):
            self.position_rows.append({'contract_id':contract.conId,'security_type':contract.secType,'currency':contract.currency,'quantity':str(num(pos)),'received_at':stamp()})
            if account!=self.expected or (num(pos)!=0 and (contract.conId!=12087792 or contract.secType!='CASH')):self.foreign_positions.append({'contract_id':contract.conId,'quantity':str(num(pos))})
        def positionEnd(self):self.positions_done.set()
        def updatePortfolio(self,contract,position,marketPrice,marketValue,averageCost,unrealizedPNL,realizedPNL,accountName):
            if not self.active_updates:return
            if accountName!=self.expected:self.verified=False;self.account_errors.append('ACCOUNT_MISMATCH');return
            try:
                self.portfolio_rows.append({'contract_id':contract.conId,'security_type':contract.secType,'symbol':contract.symbol,
                    'currency':contract.currency,'quantity':str(num(position)),'source':'ACCOUNT_UPDATES_PORTFOLIO','received_at':stamp()})
            except (ValueError,ArithmeticError):self.account_errors.append('INVALID_PORTFOLIO_VALUE')
        def positionMulti(self,reqId,account,modelCode,contract,pos,avgCost):
            if reqId!=self.active_positions_multi:return
            if account!=self.expected or modelCode:self.verified=False;self.exposure_errors.append('POSITION_SCOPE_MISMATCH');return
            try:
                self.multi_positions.append({'contract_id':contract.conId,'security_type':contract.secType,'symbol':contract.symbol,
                    'currency':contract.currency,'quantity':str(num(pos)),'source':'POSITIONS_MULTI','received_at':stamp()})
            except (ValueError,ArithmeticError):self.exposure_errors.append('INVALID_POSITION_VALUE')
        def positionMultiEnd(self,reqId):
            if reqId==self.active_positions_multi:self.positions_multi_done.set()
        def additional_exposure(self):
            if not self.connected:raise ConnectionError('PAPER_DISCONNECTED')
            req=self.request();self.active_positions_multi=req;self.multi_positions=[];self.exposure_errors=[];self.positions_multi_done.clear()
            try:
                self.client.reqPositionsMulti(req,self.expected,'');self.wait(self.positions_multi_done)
                self.exposure_errors.extend('POSITION_QUERY_ERROR_'+str(c) for c in self.request_errors.get(req,[]))
                if not self.connected:self.exposure_errors.append('ACCOUNT_IDENTITY_UNVERIFIED')
                return {'status':'ERROR' if self.exposure_errors else 'COMPLETE','positions':self.multi_positions,'errors':self.exposure_errors,'received_at':stamp()}
            except TimeoutError:
                return {'status':'INCOMPLETE','positions':self.multi_positions,'errors':['POSITION_QUERY_TIMEOUT'],'received_at':stamp()}
            finally:self.active_positions_multi=None;self.client.cancelPositionsMulti(req)
        def completedOrder(self,contract,order,state):
            if order.account!=self.expected:return
            raw=getattr(state,'completedStatus',state.status)
            status='Filled' if raw.startswith('Filled') else 'Cancelled' if raw.startswith('Cancelled') else raw
            self.events.put({'kind':'completed_order','order_id':order.orderId,'status':status,'completed_status_raw':raw,
                'perm_id':order.permId,'client_id':order.clientId,'contract_id':contract.conId,'side':order.action,
                'parent_id':order.parentId,'reference':order.orderRef,'oca_group':order.ocaGroup,'oca_type':order.ocaType,'at':stamp()})
        def completedOrdersEnd(self):self.completed_done.set()
        def accountSummary(self,reqId,account,tag,value,currency):
            if reqId!=self.active_summary:return
            self.account_field('SUMMARY_'+str(reqId),account,tag,value,currency)
        def accountSummaryEnd(self,reqId):
            if reqId==self.active_summary:self.account_completed.add('SUMMARY_'+str(reqId));self.summary_done.set()
        def account_field(self,source,account,tag,value,currency):
            if account!=self.expected:
                self.verified=False;self.account_errors.append('ACCOUNT_MISMATCH');return
            if tag.removeprefix('$LEDGER-') in ('AccountCode','AccountOrGroup'):
                if value!=self.expected:self.verified=False;self.account_errors.append('ACCOUNT_MISMATCH')
                return
            try:
                row=account_value(source,tag,value,currency)
                if row:self.account_rows.append(row)
                if row and row['tag']=='InitMarginReq':self.initial_margin={'value':row['value'],'currency':currency,'at':row['received_at']}
            except (ValueError,ArithmeticError):self.account_errors.append('INVALID_ACCOUNT_VALUE')
        def updateAccountValue(self,tag,value,currency,account):
            if self.active_updates:self.account_field('ACCOUNT_UPDATES',account,tag,value,currency)
        def accountDownloadEnd(self,account):
            if self.active_updates:
                if account==self.expected:self.account_completed.add('ACCOUNT_UPDATES');self.updates_done.set()
                else:self.verified=False;self.account_errors.append('ACCOUNT_MISMATCH')
        def accountUpdateMulti(self,reqId,account,modelCode,tag,value,currency):
            if reqId==self.active_multi:
                if modelCode:self.account_errors.append('UNEXPECTED_ACCOUNT_MODEL');return
                self.account_field('ACCOUNT_UPDATES_MULTI',account,tag,value,currency)
        def accountUpdateMultiEnd(self,reqId):
            if reqId==self.active_multi:self.account_completed.add('ACCOUNT_UPDATES_MULTI');self.multi_done.set()
        def account_snapshot(self):
            self.account_rows=[];self.account_completed=set();self.account_errors=[];self.initial_margin=None;self.portfolio_rows=[]
            self.account_expected={'ACCOUNT_UPDATES','ACCOUNT_UPDATES_MULTI'}
            for tags in ('$LEDGER:EUR','NetLiquidation,TotalCashValue,InitMarginReq,MaintMarginReq,$LEDGER'):
                req=self.request();self.active_summary=req;self.account_expected.add('SUMMARY_'+str(req));self.summary_done.clear();self.client.reqAccountSummary(req,'All',tags)
                try:self.wait(self.summary_done)
                finally:self.active_summary=None;self.client.cancelAccountSummary(req)
                self.account_errors.extend('SUMMARY_ERROR_'+str(c) for c in self.request_errors.get(req,[]))
            self.active_updates=True;self.updates_done.clear();self.client.reqAccountUpdates(True,self.expected)
            try:self.wait(self.updates_done)
            except TimeoutError:
                self.disconnect();raise
            finally:self.active_updates=False;self.client.reqAccountUpdates(False,self.expected)
            req=self.request();self.active_multi=req;self.multi_done.clear();self.client.reqAccountUpdatesMulti(req,self.expected,'',True)
            try:self.wait(self.multi_done)
            finally:self.active_multi=None;self.client.cancelAccountUpdatesMulti(req)
            self.account_errors.extend('MULTI_ERROR_'+str(c) for c in self.request_errors.get(req,[]))
            result=currency_cash(self.account_rows,self.account_completed,errors=self.account_errors,expected_sources=self.account_expected)
            self.eur_cash=result['value'];self.base_currency=result['base_currency']
            return {**result,'observations':self.account_rows,'errors':self.account_errors}
        def snapshot(self,*,diagnostic=False):
            if not self.connected:raise ConnectionError('PAPER_DISCONNECTED')
            self.open_orders=[];self.collect_open=True;self.orders_done.clear();self.client.reqAllOpenOrders();self.wait(self.orders_done);self.collect_open=False
            self.foreign_positions=[];self.position_rows=[];self.positions_done.clear();self.client.reqPositions()
            try:self.wait(self.positions_done)
            finally:self.client.cancelPositions()
            f=ExecutionFilter();f.acctCode=self.expected;f.clientId=82
            self.active_execution=self.request();self.exec_done.clear();self.client.reqExecutions(self.active_execution,f);self.wait(self.exec_done);self.active_execution=None
            self.completed_done.clear();self.client.reqCompletedOrders(True);self.wait(self.completed_done)
            cash=self.account_snapshot()
            if not self.connected:raise PermissionError('ACCOUNT_IDENTITY_UNVERIFIED')
            if not diagnostic and self.eur_cash is None:raise PermissionError('EUR_CASH_RECONCILIATION_UNAVAILABLE')
            if not diagnostic and self.base_currency!='USD':raise PermissionError('USD_BASE_ACCOUNT_REQUIRED_FOR_INITIAL_LAB')
            if any(num(p['quantity'])!=0 and (p['contract_id']!=12087792 or p['security_type']!='CASH') for p in self.portfolio_rows):
                self.foreign_positions.extend(p for p in self.portfolio_rows if num(p['quantity'])!=0 and (p['contract_id']!=12087792 or p['security_type']!='CASH'))
            return {'orders':self.open_orders,'events':self.drain(),'eur_cash':self.eur_cash,'cash_reconciliation':cash,'foreign_currency_balances':cash['other_currency_exposure'],'positions':self.position_rows,'portfolio':self.portfolio_rows,'foreign_positions':self.foreign_positions,'initial_margin':self.initial_margin,'exposure_reads_complete':True,'received_at':stamp()}
        def drain(self):
            result=[]
            while not self.events.empty():result.append(self.events.get_nowait())
            return result
        def contractDetails(self,reqId,details):
            if reqId==self.active_contract:self.details.append(details)
        def contractDetailsEnd(self,reqId):
            if reqId==self.active_contract:self.contract_done.set()
        def contract_details(self):
            self.details=[];self.active_contract=self.request();self.contract_done.clear()
            try:self.client.reqContractDetails(self.active_contract,self.contract());self.wait(self.contract_done)
            finally:self.active_contract=None
            if len(self.details)!=1:raise PermissionError('CONTRACT_UNVERIFIED')
            d=self.details[0];c=d.contract
            if (c.conId,c.symbol,c.currency,c.secType)!=(12087792,'EUR','USD','CASH') or 'IDEALPRO' not in d.validExchanges.split(',') or not {'LMT','STP'}<=set(d.orderTypes.split(',')) or num(d.minTick)!=Decimal('0.00005'):
                raise PermissionError('CONTRACT_OR_PROTECTION_UNVERIFIED')
            self.trading_session={'hours':d.tradingHours,'timezone':d.timeZoneId,'received_at':stamp()}
            return {'contract_id':c.conId,'min_tick':str(num(d.minTick)),'minimum_size_metadata':str(getattr(d,'minSize','')),
                    'size_increment_metadata':str(getattr(d,'sizeIncrement','')),'account_restrictions_verified':False,'at':stamp()}
        def marketDataType(self,reqId,marketDataType):
            if reqId==self.active_quote:
                if self.data_type and self.data_type!=marketDataType:self.quote_data={};self.quote_family={}
                self.data_type=marketDataType
        def tickPrice(self,reqId,tickType,price,attrib):
            if reqId!=self.active_quote:return
            self.quote_tick_count+=1
            if tickType not in (1,2,66,67):return
            field='bid' if tickType in (1,66) else 'ask';family='DELAYED' if tickType in (66,67) else 'LIVE'
            if self.data_type in (1,2) and family!='LIVE' or self.data_type in (3,4) and family!='DELAYED':return
            try:
                value=num(price)
                if value in (-1,0):self.quote_data.pop(field,None);self.quote_family.pop(field,None);return
                if value<0:raise ValueError()
                self.quote_data[field]=(str(value),stamp());self.quote_family[field]=family
                if getattr(attrib,'preOpen',False):self.quote_adapter_errors.append('PRE_OPEN_PRICE')
            except (ValueError,ArithmeticError):self.quote_adapter_errors.append('INVALID_PRICE');self.quote_data.pop(field,None)
        def observe_quote(self,*,market_type=1,timeout=10):
            if not self.connected:raise ConnectionError('PAPER_DISCONNECTED')
            if market_type not in (1,2,3,4):raise ValueError('INVALID_MARKET_DATA_TYPE')
            if self.trading_session is None or (utc()-date(self.trading_session['received_at'])).total_seconds()>300:self.contract_details()
            req=self.request();self.active_quote=req
            self.quote_data={};self.quote_family={};self.quote_adapter_errors=[];self.quote_tick_count=0;self.data_type=0
            self.client.reqMarketDataType(market_type);self.client.reqMktData(req,self.contract(),'',False,False,[])
            try:
                until=time.monotonic()+timeout
                while time.monotonic()<until:
                    if self.data_type in (1,2,3,4) and all(k in self.quote_data for k in ('bid','ask')):break
                    if any(c in (354,10089,200,320,321,322,420) for c in self.request_errors.get(req,[])):break
                    time.sleep(.05)
                now=utc();status=session_status(self.trading_session['hours'],self.trading_session['timezone'],now)
                expected_family='DELAYED' if self.data_type in (3,4) else 'LIVE'
                fields={k:v for k,v in self.quote_data.items() if self.quote_family.get(k)==expected_family}
                errors=self.request_errors.get(req,[])+([2103] if self.market_farm_down else [])
                return quote_observation(self.data_type,fields,status,errors,now,self.quote_adapter_errors,self.quote_tick_count)
            finally:self.active_quote=None;self.client.cancelMktData(req)
        def quote(self):
            result=self.observe_quote()
            if not result['available_for_execution']:raise PermissionError('QUOTE_'+result['reasons'][0])
            return result
        def history(self,minutes,days=30):
            if minutes not in (15,60,240) or not 1<=days<=30:raise ValueError('HISTORY_SCOPE_INVALID')
            authorization.read(management=True)
            if not self.connected:raise ConnectionError('PAPER_DISCONNECTED')
            delay=16-(time.monotonic()-self.last_history_request)
            if delay>0:time.sleep(delay)
            req=self.request();self.active_history=req;self.history_minutes=minutes;self.history_rows=[];self.history_done.clear()
            try:
                self.last_history_request=time.monotonic()
                self.client.reqHistoricalData(req,self.contract(),'',str(days)+' D',
                    {15:'15 mins',60:'1 hour',240:'4 hours'}[minutes],'MIDPOINT',0,2,False,[])
                self.wait(self.history_done)
                if self.request_errors.get(req):raise PermissionError('HISTORY_REQUEST_FAILED')
                return self.history_rows[:]
            finally:self.active_history=None;self.client.cancelHistoricalData(req)
        def historicalData(self,reqId,bar):
            if reqId!=self.active_history:return
            try:
                opened=datetime.fromtimestamp(int(bar.date),timezone.utc)
                if opened+timedelta(minutes=self.history_minutes)>utc():return
                values=[num(getattr(bar,k)) for k in ('open','high','low','close')]
                o,h,l,c=values
                if min(values)<=0 or h<max(o,l,c) or l>min(o,h,c):raise ValueError()
                self.history_rows.append({'opened_at':stamp(opened),'minutes':self.history_minutes,
                    **{k:str(v) for k,v in zip(('open','high','low','close'),values)},'volume':None,'spread':None})
            except (ValueError,ArithmeticError,OverflowError):self.request_errors.setdefault(reqId,[]).append(320)
        def historicalDataEnd(self,reqId,start,end):
            if reqId==self.active_history:self.history_done.set()
        def schedule(self,days=30):
            if not 1<=days<=30:raise ValueError('SCHEDULE_SCOPE_INVALID')
            authorization.read(management=True)
            if not self.connected:raise ConnectionError('PAPER_DISCONNECTED')
            delay=16-(time.monotonic()-self.last_history_request)
            if delay>0:time.sleep(delay)
            req=self.request();self.active_schedule=req;self.schedule_rows=[];self.schedule_done.clear()
            try:
                self.last_history_request=time.monotonic()
                self.client.reqHistoricalData(req,self.contract(),'',str(days)+' D','1 day','SCHEDULE',0,2,False,[])
                self.wait(self.schedule_done)
                if self.request_errors.get(req) or not self.schedule_rows:raise PermissionError('IBKR_SCHEDULE_UNAVAILABLE')
                self.schedule_received_at=stamp();return self.schedule_rows[:]
            finally:self.active_schedule=None;self.client.cancelHistoricalData(req)
        def historicalSchedule(self,reqId,startDateTime,endDateTime,timeZone,sessions):
            if reqId!=self.active_schedule:return
            self.schedule_rows=[{'start':startDateTime,'end':endDateTime,'time_zone':timeZone,
                'sessions':[{'start':s.startDateTime,'end':s.endDateTime,'reference_date':s.refDate} for s in sessions]}]
            self.schedule_done.set()
        def calendar(self):
            from .paper_calendar import broker_calendar
            if self.schedule_received_at is None or (utc()-date(self.schedule_received_at)).total_seconds()>3600:self.schedule()
            if self.trading_session is None or (utc()-date(self.trading_session['received_at'])).total_seconds()>300:self.contract_details()
            return broker_calendar(self.schedule_rows,self.trading_session,utc())
        @staticmethod
        def validate_quote(q):
            if q['type']!='LIVE' or q.get('market_status','OPEN')!='OPEN' or q.get('available_for_execution',True) is not True or not 0< num(q['bid'])<=num(q['ask']) or not 0<=(utc()-date(q['at'])).total_seconds()<=5:raise PermissionError('QUOTE_UNUSABLE')
    wire=Wire();return wire
