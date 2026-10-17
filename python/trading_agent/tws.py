"""Optional official ibapi transport. Imported only on an explicit Paper data command.

Requires a compatible official TWS Python SDK, not the obsolete PyPI package.
No order submission, cancellation or what-if path is implemented.
"""
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import logging
import threading
import time
import os
from .broker import PaperDataBroker, PaperOptions


def finite(value, positive=False):
    result=Decimal(str(value))
    if not result.is_finite() or abs(result)>=Decimal('1e100') or (positive and result<=0):raise ValueError('INVALID_NUMERIC_DATA')
    return result


def options_from_environment():
    return PaperOptions(account=os.environ.get('IBKR_PAPER_ACCOUNT',''),host=os.environ.get('IBKR_HOST','127.0.0.1'),port=int(os.environ.get('IBKR_PORT','7497')),
        verified_tws_port=int(os.environ.get('IBKR_VERIFIED_TWS_PORT','0')),
        paper_mode_attested=os.environ.get('IBKR_PAPER_ATTESTED')=='true',
        read_only=os.environ.get('IBKR_READ_ONLY_ATTESTED')=='true',client_id=int(os.environ.get('IBKR_CLIENT_ID','73')),
        configured_endpoint=os.environ.get('IBKR_CONFIGURED_ENDPOINT')=='true',
        live_enabled=os.environ.get('LIVE_TRADING','false').lower()!='false')


def official_wire(options, sdk_types=None, diagnostic=False):
    if sdk_types is None:
        from ibapi.client import EClient
        from ibapi.wrapper import EWrapper
        from ibapi.contract import Contract
    else:EClient,EWrapper,Contract=sdk_types

    def blocked(*args,**kwargs):raise PermissionError('ORDERS_DISABLED_READ_ONLY')
    class ReadOnlyClient(EClient):
        placeOrder=placeOrderProtoBuf=cancelOrder=cancelOrderProtoBuf=blocked
        reqGlobalCancel=reqGlobalCancelProtoBuf=exerciseOptions=exerciseOptionsProtoBuf=blocked
        replaceFA=replaceFAProtoBuf=reqAutoOpenOrders=reqAutoOpenOrdersProtoBuf=blocked
        updateDisplayGroup=updateConfig=blocked

    class Wire(EWrapper):
        def __init__(self):
            EWrapper.__init__(self)
            self._client=ReadOnlyClient(self)
            self.ready=threading.Event();self.accounts_ready=threading.Event();self.done=threading.Event()
            self.accounts=[];self.data=[];self.error_value=None;self.request_id=100
            self.lock=threading.Lock();self.worker=None;self.connector=None;self.quote_fields={}
            self.active=None;self.account_verified=False;self.events=[];self.last_history=0
            self.data_type=0;self.quote_times={}
            self.history_stats={}

        @property
        def connected(self):return self._client.isConnected() and self.ready.is_set() and self.account_verified
        @property
        def server_version(self):return self._client.serverVersion()
        def connect(self):
            if diagnostic:
                if options.account or options.host not in ('127.0.0.1','::1') or options.port!=options.verified_tws_port or not 1<=options.port<=65535 or (not options.configured_endpoint and options.port!=7497) or options.live_enabled or options.environment!='PAPER_TRADING':raise PermissionError('DIAGNOSTIC_CONFIGURATION_REJECTED')
            else:options.validate()
            complete=threading.Event();errors=[]
            def connect_sdk():
                try:self._client.connect(options.host,options.port,options.client_id)
                except Exception as exc:errors.append(type(exc).__name__)
                finally:complete.set()
            self.connector=threading.Thread(target=connect_sdk,daemon=True);self.connector.start()
            if not complete.wait(options.timeout):
                self.disconnect();raise TimeoutError('TWS_PROTOCOL_TIMEOUT')
            if errors or not self._client.isConnected():raise ConnectionError('TWS_CONNECT_FAILED')
            self.worker=threading.Thread(target=self._client.run,daemon=True);self.worker.start()
            if not self.ready.wait(options.timeout):raise TimeoutError('TWS_HANDSHAKE_TIMEOUT')
            self._client.reqManagedAccts()
            if not self.accounts_ready.wait(options.timeout):raise TimeoutError('ACCOUNT_VERIFICATION_TIMEOUT')
            if self.error_value:raise self.error_value
            return self.accounts
        def disconnect(self):
            self.account_verified=False;self.ready.clear();self._client.disconnect();self.done.set()
            for worker in (self.worker,self.connector):
                if worker and worker is not threading.current_thread():worker.join(timeout=2)
        def nextValidId(self,orderId):self.ready.set()  # handshake only; never used to place an order
        def managedAccounts(self,accountsList):
            self.accounts=[x.strip() for x in accountsList.split(',') if x.strip()]
            self.account_verified=bool(options.account) and set(self.accounts)=={options.account}
            if options.account and not self.account_verified:
                self.error_value=PermissionError('UNAUTHORIZED_ACCOUNT');self.ready.clear();self.done.set()
            self.accounts_ready.set()
        def connectionClosed(self):
            self.account_verified=False;self.ready.clear();self.error_value=ConnectionError('BROKER_DISCONNECTED');self.done.set()
        def error(self,reqId,*args):
            errorCode=args[1] if len(args)>=3 and isinstance(args[1],int) else args[0]
            self.events.append({'code':int(errorCode),'received_at':datetime.now(timezone.utc).isoformat()});self.events=self.events[-100:]
            logging.getLogger(__name__).warning('broker_event',extra={'request_id':reqId,'error_code':errorCode})
            if errorCode in (2104,2106,2107,2108,2158):return  # informational farm states
            if errorCode in (1100,1101,1102,1300,502,504):
                self.account_verified=False;self.ready.clear();self.error_value=ConnectionError(f'IBKR_{errorCode}');self.done.set()
            elif errorCode in (326,501,503) or reqId == self.request_id:
                self.error_value=PermissionError(f'IBKR_{errorCode}') if errorCode in (326,354,10167,10168,10186) else RuntimeError(f'IBKR_{errorCode}')
                self.done.set()
        def _begin(self,kind):
            if not self.connected:raise ConnectionError('BROKER_DISCONNECTED')
            self.request_id+=1;self.active=kind;self.data=[];self.error_value=None;self.done.clear()
            return self.request_id
        def _wait(self):
            if not self.done.wait(options.timeout):raise TimeoutError('IBKR_READ_TIMEOUT')
            if self.error_value:raise self.error_value
            if not self.connected:raise ConnectionError('BROKER_DISCONNECTED')
            return list(self.data)
        def _invalid(self,code):self.error_value=ValueError(code);self.done.set()
        def _check_account(self,account):
            if account==options.account:return True
            self.account_verified=False;self.ready.clear();self.error_value=PermissionError('UNAUTHORIZED_ACCOUNT');self.done.set();return False
        def balance(self):
            with self.lock:
                req=self._begin('balance')
                try:
                    self._client.reqAccountSummary(req,'All','NetLiquidation,AvailableFunds,ExcessLiquidity,TotalCashValue,BuyingPower,$LEDGER')
                    rows=self._wait()
                    required={'NetLiquidation','AvailableFunds','TotalCashValue'}
                    if not required <= {r['tag'] for r in rows}:raise ValueError('INCOMPLETE_BALANCE')
                    bases={r['value'] for r in rows if r['tag']=='Currency'}
                    if len(bases)!=1:raise ValueError('MISSING_BASE_CURRENCY')
                    base=next(iter(bases))
                    if base=='BASE':
                        # TWS reports ledger BASE as an alias, not an ISO currency.
                        # Resolve it exclusively from the required account-level values received from IBKR.
                        summary_currencies={r['currency'] for r in rows if r['tag'] in required}
                        if len(summary_currencies)!=1:raise ValueError('MISSING_BASE_CURRENCY')
                        base=next(iter(summary_currencies))
                        if len(base)!=3 or not base.isascii() or not base.isalpha() or not base.isupper():
                            raise ValueError('MISSING_BASE_CURRENCY')
                    rows=[{**r,'currency':base if r['currency']=='BASE' else r['currency'],
                           'value':base if r['tag']=='Currency' and r['value']=='BASE' else r['value']} for r in rows]
                    if any(not any(r['tag']==t and r['currency']==base for r in rows) for t in required):raise ValueError('INCOMPLETE_BASE_BALANCE')
                    return {'base_currency':base,'values':rows,'received_at':datetime.now(timezone.utc).isoformat()}
                finally:self.active=None;self._client.cancelAccountSummary(req) # data subscription only
        def accountSummary(self,reqId,account,tag,value,currency):
            if reqId!=self.request_id or self.active!='balance' or not self._check_account(account):return
            try:
                # Current TWS can prepend $LEDGER- to the requested per-currency fields.
                if tag.startswith('$LEDGER-'):tag=tag[len('$LEDGER-'):]
                if tag=='AccountOrGroup':
                    self._check_account(value);return  # identity-bearing metadata never enters data or logs
                if tag not in {'Currency','NetLiquidation','AvailableFunds','ExcessLiquidity','TotalCashValue',
                               'BuyingPower','CashBalance','SettledCash','AccruedCash','FutureOptionValue','FuturesPNL',
                               'NetLiquidationByCurrency','ExchangeRate','RealizedPnL','UnrealizedPnL','TotalCashBalance'}:
                    return  # $LEDGER also delivers text and fields outside our persisted account schema
                if tag=='Currency':
                    if value!='BASE' and (len(value)!=3 or not value.isascii() or not value.isalpha() or not value.isupper()):raise ValueError()
                    self.data.append({'tag':tag,'value':value,'currency':value})
                else:self.data.append({'tag':tag,'value':str(finite(value)),'currency':currency})
            except (ValueError,ArithmeticError):self._invalid('INVALID_BALANCE')
        def accountSummaryEnd(self,reqId):
            if reqId==self.request_id and self.active=='balance':self.done.set()
        def positions(self):
            with self.lock:
                self._begin('positions')
                try:self._client.reqPositions();return self._wait()
                finally:self.active=None;self._client.cancelPositions()
        def position(self,account,contract,position,avgCost):
            if self.active!='positions' or not self._check_account(account):return
            try:
                if contract.conId<=0:raise ValueError()
                self.data.append({'con_id':contract.conId,'symbol':contract.symbol,'security_type':contract.secType,
                    'currency':contract.currency,'quantity':str(finite(position)),'average_cost':str(finite(avgCost))})
            except (ValueError,ArithmeticError):self._invalid('INVALID_POSITION')
        def positionEnd(self):
            if self.active=='positions':self.done.set()
        @staticmethod
        def contract(instrument):
            if instrument!='EUR/USD':raise ValueError('Only EUR/USD is enabled for initial data research')
            c=Contract();c.symbol='EUR';c.secType='CASH';c.currency='USD';c.exchange='IDEALPRO';return c
        def contract_details(self,instrument):
            with self.lock:
                req=self._begin('contract')
                try:
                    self._client.reqContractDetails(req,self.contract(instrument));rows=self._wait()
                    if len(rows)!=1:raise ValueError('AMBIGUOUS_OR_MISSING_CONTRACT')
                    return rows[0]
                finally:self.active=None
        def contractDetails(self,reqId,details):
            if reqId!=self.request_id or self.active!='contract':return
            c=details.contract
            try:
                if c.conId<=0 or (c.symbol,c.currency,c.secType)!=('EUR','USD','CASH') or 'IDEALPRO' not in details.validExchanges.split(','):raise ValueError()
                row={'con_id':c.conId,'symbol':c.symbol,'currency':c.currency,'security_type':c.secType,
                    'exchange':c.exchange,'valid_exchanges':details.validExchanges,'min_tick':str(finite(details.minTick,True)),
                    'market_rule_ids':details.marketRuleIds,'trading_hours':details.tradingHours,'liquid_hours':details.liquidHours,
                    'time_zone':details.timeZoneId,'order_types':details.orderTypes,'minimum_size':None,'size_increment':None,
                    'restrictions_verified':False,'received_at':datetime.now(timezone.utc).isoformat()}
                for field,attr in (('minimum_size','minSize'),('size_increment','sizeIncrement')):
                    value=getattr(details,attr,None)
                    if value is not None and Decimal(str(value)).is_finite() and 0<Decimal(str(value))<Decimal('1e100'):row[field]=str(value)
                self.data.append(row)
            except (ValueError,ArithmeticError):self._invalid('INVALID_CONTRACT')
        def contractDetailsEnd(self,reqId):
            if reqId==self.request_id and self.active=='contract':self.done.set()
        def quote(self,instrument):
            with self.lock:
                req=self._begin('quote');self.quote_fields={};self.quote_times={};self.data_type=0
                try:
                    self._client.reqMarketDataType(4) # explicitly labelled observation; never execution
                    self._client.reqMktData(req,self.contract(instrument),'',False,False,[])
                    try:self._wait()
                    except (TimeoutError,PermissionError,RuntimeError) as exc:
                        if not self.connected:raise
                        return self._quote_result(str(exc))
                    return self._quote_result(None)
                finally:self.active=None;self._client.cancelMktData(req)
        def _quote_result(self,reason):
            bid,ask=self.quote_fields.get('bid'),self.quote_fields.get('ask')
            valid=self.data_type in (1,2,3,4) and bid is not None and ask is not None and bid>0 and ask>=bid
            kind={1:'REALTIME',2:'FROZEN',3:'DELAYED',4:'FROZEN'}.get(self.data_type,'UNAVAILABLE') if valid else 'UNAVAILABLE'
            return {'instrument':'EUR/USD','bid':str(bid) if valid else None,'ask':str(ask) if valid else None,
                'last':str(self.quote_fields['last']) if 'last' in self.quote_fields else None,'spread':str(ask-bid) if valid else None,
                'received_at':datetime.now(timezone.utc).isoformat(),'bid_received_at':self.quote_times.get('bid'),
                'ask_received_at':self.quote_times.get('ask'),'source':'IBKR_TWS','data_type':kind,'market_data_type':self.data_type,
                'source_timestamp':None,'executable':False,'reason':reason}
        def marketDataType(self,reqId,marketDataType):
            if reqId==self.request_id and self.active=='quote':
                if self.data_type!=marketDataType:self.quote_fields={};self.quote_times={}
                self.data_type=marketDataType;self._quote_complete()
        def _quote_complete(self):
            if self.data_type in (1,2,3,4) and {'bid','ask'}<=self.quote_fields.keys():self.done.set()
        def tickPrice(self,reqId,tickType,price,attrib):
            if reqId!=self.request_id or self.active!='quote':return
            key={1:'bid',2:'ask',4:'last',66:'bid',67:'ask',68:'last'}.get(tickType)
            if key is None:return
            try:
                if tickType in (66,67,68) and self.data_type not in (3,4):return
                if tickType in (1,2,4) and self.data_type in (3,4):return
                value=finite(price)
                if value in (-1,0):
                    # IBKR uses unavailable-price sentinels. EUR/USD cannot have a zero quote.
                    self.quote_fields.pop(key,None);self.quote_times.pop(key,None);return
                if value<0:raise ValueError('INVALID_QUOTE')
                self.quote_fields[key]=value;self.quote_times[key]=datetime.now(timezone.utc).isoformat();self._quote_complete()
            except (ValueError,ArithmeticError):self._invalid('INVALID_QUOTE')
        def history(self,instrument,minutes,days=7):
            sizes={15:'15 mins',60:'1 hour',240:'4 hours'}
            if minutes not in sizes or not 1<=days<=30:raise ValueError('Invalid timeframe/range')
            with self.lock:
                end=datetime.now(timezone.utc);start=end-timedelta(days=days);rows={}
                while end>start:
                    delay=16-(time.monotonic()-self.last_history)
                    if delay>0:time.sleep(delay)
                    req=self._begin('history');self.bar_minutes=minutes
                    try:
                        self.last_history=time.monotonic()
                        self._client.reqHistoricalData(req,self.contract(instrument),end.strftime('%Y%m%d-%H:%M:%S'),
                            '7 D',sizes[minutes],'MIDPOINT',0,2,False,[])
                        for row in self._wait():
                            if datetime.fromisoformat(row['opened_at'])>=start:
                                key=row['opened_at']
                                if key in rows and rows[key]!=row:raise ValueError('CONFLICTING_CANDLE')
                                rows[key]=row
                    finally:self.active=None;self._client.cancelHistoricalData(req)
                    end-=timedelta(days=7)
                ordered=[rows[k] for k in sorted(rows)]
                # IBKR includes shorter session-boundary bars in nominal 1h/4h series.
                # Keep original prices/timestamps, but exclude rows whose nominal duration overlaps the next opening.
                kept=[row for index,row in enumerate(ordered) if index==len(ordered)-1 or
                      datetime.fromisoformat(row['opened_at'])+timedelta(minutes=minutes)<=datetime.fromisoformat(ordered[index+1]['opened_at'])]
                self.history_stats={'minutes':minutes,'received':len(ordered),'retained':len(kept),'short_interval':len(ordered)-len(kept)}
                return kept
        def historicalData(self,reqId,bar):
            if reqId!=self.request_id or self.active!='history':return
            try:
                opened=datetime.fromtimestamp(int(bar.date),timezone.utc)
                if opened+timedelta(minutes=self.bar_minutes)>datetime.now(timezone.utc):return
                o,h,l,c=[finite(v,True) for v in (bar.open,bar.high,bar.low,bar.close)]
                if h<max(o,l,c) or l>min(o,h,c):raise ValueError()
                self.data.append({'opened_at':opened.isoformat(),'minutes':self.bar_minutes,'open':str(o),'high':str(h),
                    'low':str(l),'close':str(c),'volume':None,'spread':None}) # MIDPOINT FX has no traded volume
            except (ValueError,ArithmeticError,OverflowError):self._invalid('INVALID_CANDLE')
        def historicalDataEnd(self,reqId,start,end):
            if reqId==self.request_id and self.active=='history':self.done.set()
    return Wire()


if __name__=='__main__':
    import argparse,json,os
    p=argparse.ArgumentParser(description='Explicit read-only Paper probe. Never submits orders.')
    p.add_argument('operation',choices=['diagnose','status','balance','positions','contract_details','quote','history'])
    p.add_argument('--minutes',type=int,default=15,choices=[15,60,240])
    p.add_argument('--days',type=int,default=7,choices=range(1,31));args=p.parse_args()
    options=options_from_environment()
    logging.getLogger('ibapi').setLevel(logging.CRITICAL)
    if args.operation=='diagnose':
        from dataclasses import replace
        wire=official_wire(replace(options,account='',host='127.0.0.1',port=7497),diagnostic=True)
        try:
            accounts=wire.connect()
            print(json.dumps({'handshake':wire.ready.is_set(),'server_version':wire.server_version,
                'accounts':[{'masked':'***'+a[-4:],'internal_id':replace(options,account=a).internal_id} for a in accounts],
                'sdk_version':__import__('ibapi').get_version_string(),'port':7497,'client_id':options.client_id,
                'event_codes':[event['code'] for event in wire.events],
                'operationally_authorized':False,'orders_supported':False}))
        finally:wire.disconnect()
        raise SystemExit(0)
    broker=PaperDataBroker(options,official_wire)
    try:
        broker.connect()
        result={'connected':broker.connected,'account_id':options.internal_id,'server_version':broker.wire.server_version} if args.operation=='status' else broker.history(minutes=args.minutes,days=args.days) if args.operation=='history' else getattr(broker,args.operation)()
        print(json.dumps(result,allow_nan=False))
    finally:broker.disconnect()
