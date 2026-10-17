from dataclasses import replace
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from unittest.mock import patch
import threading
import unittest
from trading_agent.broker import PaperOptions,PaperDataBroker
from trading_agent.tws import official_wire


class Client:
    def __init__(self,wrapper):self.wrapper=wrapper;self.online=False;self.calls=[];self.accounts='DU123';self.handshake=True
    def connect(self,*args):self.online=True
    def run(self):
        if self.handshake:self.wrapper.nextValidId(1)
    def isConnected(self):return self.online
    def serverVersion(self):return 226
    def disconnect(self):self.online=False
    def reqManagedAccts(self):self.wrapper.managedAccounts(self.accounts)
    def reqAccountSummary(self,req,*args):
        for tag,value,currency in [('NetLiquidation','1000000','USD'),('TotalCashValue','1000000','USD'),
                                   ('AvailableFunds','1000000','USD'),('BuyingPower','4000000','USD'),('Currency','USD','')]:
            self.wrapper.accountSummary(req,'DU123',tag,value,currency)
        self.wrapper.accountSummaryEnd(req)
    def cancelAccountSummary(self,*args):pass
    def reqPositions(self):self.wrapper.positionEnd()
    def cancelPositions(self):pass
    def reqMarketDataType(self,value):self.requested_type=value
    def reqMktData(self,req,*args):
        self.wrapper.marketDataType(req,2);self.wrapper.tickPrice(req,1,1.1,None);self.wrapper.tickPrice(req,2,1.1002,None)
    def cancelMktData(self,*args):pass
    def reqContractDetails(self,req,c):
        c.conId=12087792
        d=SimpleNamespace(contract=c,validExchanges='IDEALPRO',minTick=.00005,marketRuleIds='1',tradingHours='',
                          liquidHours='',timeZoneId='US/Eastern',orderTypes='MKT,LMT',minSize=20000,sizeIncrement=1)
        self.wrapper.contractDetails(req,d);self.wrapper.contractDetailsEnd(req)
    def reqHistoricalData(self,req,c,end,duration,size,*args):
        self.calls.append((req,end,duration,size))
        minutes={'15 mins':15,'1 hour':60,'4 hours':240}[size]
        opened=datetime.strptime(end,'%Y%m%d-%H:%M:%S').replace(tzinfo=timezone.utc)-timedelta(hours=8)
        self.wrapper.historicalData(req,SimpleNamespace(date=str(int(opened.timestamp())),open=1.1,high=1.2,low=1,close=1.15,volume=-1))
        self.wrapper.historicalDataEnd(req,'','')
    def cancelHistoricalData(self,*args):pass


class TwsTests(unittest.TestCase):
    def wire(self):
        options=PaperOptions('DU123',paper_mode_attested=True,timeout=.05)
        return official_wire(options,(Client,object,SimpleNamespace))
    def test_handshake_and_exact_account_are_required(self):
        w=self.wire();w.connect();self.assertTrue(w.connected);self.assertEqual(w.server_version,226)
        w.managedAccounts('DU123,U999');self.assertFalse(w.connected)
        with self.assertRaises(ConnectionError):w.balance()
    def test_dur_transport_requires_exact_identity_and_keeps_orders_blocked(self):
        options=PaperOptions('DUR12345678',paper_mode_attested=True,timeout=.05)
        w=official_wire(options,(Client,object,SimpleNamespace));w._client.accounts=options.account
        try:
            self.assertEqual(w.connect(),[options.account]);self.assertTrue(w.connected)
            with self.assertRaisesRegex(PermissionError,'ORDERS_DISABLED'):w._client.placeOrder(object())
            w.managedAccounts('DUR99995678');self.assertFalse(w.connected)
            with self.assertRaises(ConnectionError):w.positions()
        finally:w.disconnect()
    def test_incomplete_handshake(self):
        w=self.wire();w._client.handshake=False
        with self.assertRaisesRegex(TimeoutError,'HANDSHAKE'):w.connect()
        w.disconnect();self.assertFalse(w.connected)
    def test_incomplete_protocol_negotiation_is_bounded(self):
        w=self.wire();released=threading.Event()
        w._client.connect=lambda *_:released.wait(1)
        try:
            with self.assertRaisesRegex(TimeoutError,'PROTOCOL'):w.connect()
        finally:released.set();w.disconnect()
    def test_unknown_and_live_accounts_rejected_by_transport(self):
        for account in ('DU456','U123','DU123,U999',''):
            w=self.wire();w._client.accounts=account
            with self.assertRaises(PermissionError):w.connect()
            w.disconnect();self.assertFalse(w.connected)
    def test_wrong_port_and_read_only_disabled(self):
        for options in (PaperOptions('DU123',port=7496,verified_tws_port=7496,paper_mode_attested=True),
                        PaperOptions('DU123',paper_mode_attested=True,read_only=False)):
            w=official_wire(options,(Client,object,SimpleNamespace))
            with self.assertRaises(PermissionError):w.connect()
            self.assertFalse(w._client.online)
    def test_balances_and_text_currency_remain_separate(self):
        w=self.wire();w.connect();balance=w.balance()
        self.assertEqual(balance['base_currency'],'USD')
        self.assertEqual(next(v['value'] for v in balance['values'] if v['tag']=='NetLiquidation'),'1000000')
        self.assertNotIn('DU123',str(balance));self.assertEqual(w.positions(),[])
    def test_missing_or_nonfinite_balance_rejected(self):
        w=self.wire();w.connect()
        def incomplete(req,*_):w.accountSummary(req,'DU123','NetLiquidation','NaN','USD');w.accountSummaryEnd(req)
        w._client.reqAccountSummary=incomplete
        with self.assertRaisesRegex(ValueError,'INVALID_BALANCE'):w.balance()
        w._client.reqAccountSummary=lambda req,*_:w.accountSummaryEnd(req)
        with self.assertRaisesRegex(ValueError,'INCOMPLETE_BALANCE'):w.balance()
    def test_prefixed_ledger_base_alias_uses_only_received_summary_currency(self):
        w=self.wire();w.connect()
        def summary(req,*_):
            for tag,value,currency in [('NetLiquidation','1000185.90','USD'),('AvailableFunds','1000000.00','USD'),
                                       ('TotalCashValue','1000000.00','USD'),('$LEDGER-Currency','BASE','BASE'),
                                       ('$LEDGER-CashBalance','1000000.00','BASE'),('$LEDGER-TotalCashBalance','1000000.00','BASE'),
                                       ('$LEDGER-AccountOrGroup','DU123','BASE'),('$LEDGER-RealCurrency','USD','BASE'),
                                       ('$LEDGER-StockMarketValue','0.00','BASE')]:
                w.accountSummary(req,'DU123',tag,value,currency)
            w.accountSummaryEnd(req)
        w._client.reqAccountSummary=summary
        try:
            balance=w.balance();self.assertEqual(balance['base_currency'],'USD')
            values={r['tag']:r for r in balance['values']}
            self.assertEqual(values['NetLiquidation']['value'],'1000185.90')
            self.assertEqual(values['Currency'],{'tag':'Currency','value':'USD','currency':'USD'})
            self.assertEqual(values['CashBalance']['currency'],'USD')
            self.assertEqual(values['CashBalance']['value'],'1000000.00')
            self.assertNotIn('DU123',str(balance));self.assertEqual(len(values),6)
        finally:w.disconnect()
    def test_ledger_identity_metadata_cannot_bypass_exact_account_check(self):
        w=self.wire();w.connect()
        def summary(req,*_):
            w.accountSummary(req,'DU123','$LEDGER-AccountOrGroup','DUR123','BASE');w.accountSummaryEnd(req)
        w._client.reqAccountSummary=summary
        try:
            with self.assertRaisesRegex(PermissionError,'UNAUTHORIZED_ACCOUNT'):w.balance()
            self.assertFalse(w.connected);self.assertEqual(w.data,[])
        finally:w.disconnect()
    def test_ledger_alias_never_guesses_missing_or_conflicting_base_currency(self):
        for currencies,ledger in ((('USD','EUR','USD'),'BASE'),(('BASE','BASE','BASE'),'BASE'),
                                  (('USD','USD','USD'),'EUR'),(('USD','USD','USD'),'usd')):
            with self.subTest(currencies=currencies,ledger=ledger):
                w=self.wire();w.connect()
                def summary(req,*_):
                    for tag,currency in zip(('NetLiquidation','AvailableFunds','TotalCashValue'),currencies):
                        w.accountSummary(req,'DU123',tag,'100',currency)
                    w.accountSummary(req,'DU123','$LEDGER-Currency',ledger,'BASE');w.accountSummaryEnd(req)
                w._client.reqAccountSummary=summary
                try:
                    with self.assertRaises(ValueError):w.balance()
                finally:w.disconnect()
    def test_forex_contract_fields_and_constraints(self):
        w=self.wire();w.connect();c=w.contract_details('EUR/USD')
        self.assertEqual((c['symbol'],c['currency'],c['security_type'],c['exchange']),('EUR','USD','CASH','IDEALPRO'))
        self.assertEqual(c['minimum_size'],'20000');self.assertFalse(c['restrictions_verified'])
    def test_frozen_delayed_realtime_and_missing_quotes_never_execute(self):
        for dtype,ticks,kind in ((1,(1,2),'REALTIME'),(2,(1,2),'FROZEN'),(3,(66,67),'DELAYED'),(4,(66,67),'FROZEN')):
            w=self.wire();w.connect()
            def quote(req,*_):
                w.marketDataType(req,dtype);w.tickPrice(req,ticks[0],1.1,None);w.tickPrice(req,ticks[1],1.1002,None)
            w._client.reqMktData=quote
            q=w.quote('EUR/USD');self.assertEqual(q['data_type'],kind);self.assertFalse(q['executable']);self.assertIsNone(q['source_timestamp'])
        w=self.wire();w.connect();w._client.reqMktData=lambda req,*_:w.marketDataType(req,1)
        q=w.quote('EUR/USD');self.assertEqual(q['data_type'],'UNAVAILABLE');self.assertIsNone(q['bid'])
    def test_market_type_change_discards_prior_prices(self):
        w=self.wire();w.connect();req=w._begin('quote')
        w.marketDataType(req,2);w.tickPrice(req,1,1.1,None);w.marketDataType(req,1)
        self.assertEqual(w.quote_fields,{})
        w.tickPrice(req-1,2,1.2,None);self.assertEqual(w.quote_fields,{})
    def test_unavailable_price_sentinels_never_become_quotes(self):
        w=self.wire();w.connect()
        def quote(req,*_):
            w.marketDataType(req,1);w.tickPrice(req,1,-1,None);w.tickPrice(req,2,-1,None);w.tickPrice(req,4,0,None)
        w._client.reqMktData=quote
        try:
            q=w.quote('EUR/USD');self.assertEqual(q['data_type'],'UNAVAILABLE')
            self.assertIsNone(q['bid']);self.assertIsNone(q['ask']);self.assertIsNone(q['last'])
            self.assertEqual(q['market_data_type'],1);self.assertFalse(q['executable']);self.assertTrue(w.connected)
        finally:w.disconnect()
    def test_sentinel_removes_previous_price_but_invalid_numbers_are_rejected(self):
        w=self.wire();w.connect();req=w._begin('quote');w.marketDataType(req,1)
        w.tickPrice(req,1,1.1,None);w.tickPrice(req,1,-1,None)
        self.assertNotIn('bid',w.quote_fields);self.assertNotIn('bid',w.quote_times)
        w.tickPrice(req,2,float('nan'),None)
        try:
            with self.assertRaisesRegex(ValueError,'INVALID_QUOTE'):w._wait()
        finally:w.disconnect()
    def test_closed_history_pagination_and_pacing(self):
        w=self.wire();w.connect()
        with patch('trading_agent.tws.time.sleep') as sleep:
            rows=w.history('EUR/USD',15,days=14)
        self.assertEqual(len(rows),2);self.assertEqual(len(w._client.calls),2);self.assertNotEqual(w._client.calls[0][1],w._client.calls[1][1])
        self.assertTrue(sleep.called);self.assertTrue(all(r['volume'] is None for r in rows))
    def test_session_boundary_short_intervals_are_excluded_without_resampling(self):
        base=datetime.now(timezone.utc).replace(hour=0,minute=0,second=0,microsecond=0)-timedelta(days=2)
        for minutes,offsets,kept in ((60,(1275,1320,1380),(1320,1380)),(240,(1200,1275,1440,1680),(1440,1680))):
            with self.subTest(minutes=minutes):
                w=self.wire();w.connect()
                def history(req,*_):
                    for offset in offsets:
                        w.historicalData(req,SimpleNamespace(date=str(int((base+timedelta(minutes=offset)).timestamp())),
                            open=1.1,high=1.2,low=1,close=1.15,volume=-1))
                    w.historicalDataEnd(req,'','')
                w._client.reqHistoricalData=history
                try:
                    rows=w.history('EUR/USD',minutes)
                    self.assertEqual([datetime.fromisoformat(r['opened_at']) for r in rows],[base+timedelta(minutes=x) for x in kept])
                    self.assertTrue(all(r['close']=='1.15' and r['volume'] is None for r in rows))
                    self.assertEqual(w.history_stats,{'minutes':minutes,'received':len(offsets),'retained':len(kept),'short_interval':len(offsets)-len(kept)})
                finally:w.disconnect()
    def test_incomplete_or_open_bars_and_late_callbacks(self):
        w=self.wire();w.connect();req=w._begin('history');w.bar_minutes=15
        w.historicalData(req,SimpleNamespace(date=str(int(datetime.now(timezone.utc).timestamp())),open=1,high=2,low=1,close=1))
        self.assertEqual(w.data,[])
        w.historicalData(req-1,SimpleNamespace());self.assertEqual(w.data,[])
        w.historicalData(req,SimpleNamespace(date='bad',open=1,high=2,low=1,close=1))
        with self.assertRaisesRegex(ValueError,'INVALID_CANDLE'):w._wait()
    def test_connectivity_loss_blocks_reads_and_requires_new_handshake(self):
        w=self.wire();w.connect();w.error(-1,0,1100,'sensitive account DU123')
        self.assertFalse(w.connected)
        with self.assertRaises(ConnectionError):w.balance()
        self.assertNotIn('DU123',str(w.events))
    def test_client_id_collision_is_permission_failure(self):
        w=self.wire();w.connect();w._begin('balance');w.error(-1,0,326,'collision')
        with self.assertRaises(PermissionError):w._wait()
    def test_all_sdk_mutations_block_before_any_send(self):
        w=self.wire()
        for method in ('placeOrder','placeOrderProtoBuf','cancelOrder','cancelOrderProtoBuf','reqGlobalCancel',
                       'reqGlobalCancelProtoBuf','exerciseOptions','exerciseOptionsProtoBuf','replaceFA','replaceFAProtoBuf',
                       'reqAutoOpenOrders','reqAutoOpenOrdersProtoBuf','updateConfig','updateDisplayGroup'):
            with self.subTest(method=method),self.assertRaisesRegex(PermissionError,'ORDERS_DISABLED'):
                getattr(w._client,method)(object())
        self.assertFalse(hasattr(w,'client'));self.assertFalse(hasattr(w,'placeOrder'))
    def test_official_installed_sdk_has_same_mutation_guards_without_connecting(self):
        try:import ibapi
        except ImportError:self.skipTest('Official SDK not installed in this interpreter')
        w=official_wire(PaperOptions('DU123',paper_mode_attested=True))
        for method in ('placeOrder','placeOrderProtoBuf','cancelOrder','cancelOrderProtoBuf','reqGlobalCancel',
                       'reqGlobalCancelProtoBuf','exerciseOptions','exerciseOptionsProtoBuf'):
            with self.subTest(method=method),self.assertRaisesRegex(PermissionError,'ORDERS_DISABLED'):
                getattr(w._client,method)(object())
        self.assertFalse(w.connected)


if __name__=='__main__':unittest.main()
