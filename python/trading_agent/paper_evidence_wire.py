"""Paper observer transport, separate from AI workers. All mutations remain blocked."""
from datetime import datetime, timezone
from decimal import Decimal
from .paper_account_capabilities import capabilities_wire
from .tws import finite


def observer_wire(options, sdk_types=None):
    base=capabilities_wire(options,sdk_types)

    class Observer(type(base)):
        def historicalSchedule(self,reqId,startDateTime,endDateTime,timeZone,sessions):
            if reqId==self.request_id and self.active=='stock_schedule':
                self.schedule_bounds=dict(start=startDateTime,end=endDateTime,time_zone=timeZone)
            super().historicalSchedule(reqId,startDateTime,endDateTime,timeZone,sessions)

        def recent_schedule(self):
            with self.lock:
                self.paced();req=self._begin('stock_schedule')
                try:
                    self._client.reqHistoricalData(req,self.contract('F'),'','30 D','1 day','SCHEDULE',1,2,False,[])
                    rows=self._wait()
                    return dict(sessions=rows,coverage=self.schedule_bounds)
                finally:self.active=None;self._client.cancelHistoricalData(req)

        def sample(self):
            with self.lock:
                req=self._begin('quote');self.symbol='F';self.quote_fields={};self.quote_times={};self.data_type=0
                self.sizes={};self.size_times={};self.last_trade_at=None
                try:
                    self._client.reqMarketDataType(3) # delayed fallback; callback labels actual entitlement
                    self._client.reqMktData(req,self.contract('F'),'',False,False,[])
                    # Bounded collection window: include sizes arriving after the first BID/ASK.
                    error=None
                    try:
                        self._wait()
                        import time
                        until=time.monotonic()+min(2,options.timeout)
                        while self.connected and time.monotonic()<until:time.sleep(.05)
                    except (TimeoutError,RuntimeError,PermissionError) as exc:
                        if not self.connected:raise
                        error=type(exc).__name__
                    return dict(bid=str(self.quote_fields['bid']) if 'bid' in self.quote_fields else None,
                        ask=str(self.quote_fields['ask']) if 'ask' in self.quote_fields else None,
                        received_at=datetime.now(timezone.utc).isoformat(),field_received_at=dict(self.quote_times),
                        market_data_type=self.data_type,last_trade_at=self.last_trade_at,
                        sizes=dict(self.sizes),size_received_at=dict(self.size_times),size_unit='UNKNOWN',
                        source='IBKR_TWS_REQ_MKT_DATA',quote_source_timestamp=None,error=error)
                finally:self.active=None;self._client.cancelMktData(req)

        def marketDataType(self,reqId,kind):
            if reqId==self.request_id and self.active=='quote' and self.data_type!=kind:
                self.sizes={};self.size_times={};self.last_trade_at=None
            super().marketDataType(reqId,kind)

        def tickSize(self,reqId,kind,size):
            if reqId!=self.request_id or self.active!='quote':return
            key={0:'bid_size',3:'ask_size',8:'volume',69:'bid_size',70:'ask_size',74:'volume'}.get(kind)
            if key is None or ((kind>=69)!=(self.data_type in (3,4))):return
            try:
                value=finite(size)
                if value<0:return
                self.sizes[key]=str(value);self.size_times[key]=datetime.now(timezone.utc).isoformat()
            except (ValueError,ArithmeticError):self._invalid('INVALID_OBSERVER_SIZE')

        def tickString(self,reqId,kind,value):
            if reqId==self.request_id and self.active=='quote' and kind in (45,88):
                if (kind==88)!=(self.data_type in (3,4)):return
                try:self.last_trade_at=datetime.fromtimestamp(float(Decimal(value)),timezone.utc).isoformat()
                except (ValueError,ArithmeticError,OverflowError):self._invalid('INVALID_TRADE_TIMESTAMP')

    return Observer()
