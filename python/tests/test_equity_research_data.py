from datetime import datetime, timezone
from types import SimpleNamespace
import unittest
from test_tws import Client
from trading_agent.broker import PaperOptions
from trading_agent.equity_research_data import stock_wire, normalize


class StockClient(Client):
    def reqAccountUpdates(self,subscribe,account):
        if subscribe:
            self.wrapper.updateAccountValue('SettledCash','1000000','USD',account)
            self.wrapper.updateAccountValue('TradingType-S','CASH','',account)
            self.wrapper.accountDownloadEnd(account)

    def reqContractDetails(self, req, c):
        c.conId = 123
        self.wrapper.contractDetails(req, SimpleNamespace(contract=c, validExchanges='SMART,ARCA',
            minTick=.01, marketRuleIds='26', tradingHours='', liquidHours='', timeZoneId='US/Eastern',
            orderTypes='LMT,STP', minSize=1, sizeIncrement=1))
        self.wrapper.contractDetailsEnd(req)


class EquityResearchDataTests(unittest.TestCase):
    def wire(self):
        return stock_wire(PaperOptions('DU123', paper_mode_attested=True, timeout=.05),
                          (StockClient, object, SimpleNamespace))

    def test_all_mutations_remain_blocked_in_separate_stock_reader(self):
        w = self.wire(); w.connect()
        for method in ('placeOrder', 'placeOrderProtoBuf', 'cancelOrder', 'cancelOrderProtoBuf',
                       'reqGlobalCancel', 'exerciseOptions', 'reqAutoOpenOrders'):
            with self.assertRaisesRegex(PermissionError, 'ORDERS_DISABLED_READ_ONLY'):
                getattr(w._client, method)(1)
        w.disconnect()

    def test_exact_account_required_and_live_options_rejected(self):
        w = self.wire(); w._client.accounts = 'U123'
        with self.assertRaises(PermissionError): w.connect()
        w.disconnect()
        with self.assertRaises(PermissionError):
            stock_wire(PaperOptions('DU123', paper_mode_attested=True, live_enabled=True),
                       (StockClient, object, SimpleNamespace)).connect()

    def test_contract_resolution_does_not_establish_permission_or_fraction_support(self):
        w = self.wire(); w.connect(); row = w.contract_details('SCHX')
        self.assertEqual('STK', row['security_type']); self.assertEqual('1', row['minimum_size'])
        self.assertIsNone(row['fractional_permission']); self.assertIsNone(row['trading_permission'])
        with self.assertRaises(ValueError): w.contract('EUR/USD')
        w.disconnect()

    def test_unknown_account_fields_are_not_zero_or_pricing_plan(self):
        w = self.wire(); w.connect(); rows = w.account_observation()
        self.assertFalse(any(x['tag'] == 'SettledCash' for x in rows))
        self.assertNotIn('DU123', str(rows)); w.disconnect()

    def test_quote_names_instrument_and_delayed_frozen_is_never_executable(self):
        w = self.wire(); w.connect(); q = w.quote('SCHX')
        self.assertEqual('SCHX', q['instrument']); self.assertFalse(q['executable'])
        w.data_type=4; self.assertEqual('DELAYED_FROZEN', w._quote_result(None)['data_type'])
        w.disconnect()

    def test_authentic_early_close_truncates_last_hour(self):
        sessions=[dict(start='20260702-09:30:00', end='20260702-13:00:00', day='20260702', time_zone='US/Eastern')]
        opened=datetime(2026,7,2,16,30,tzinfo=timezone.utc)
        row=dict(broker_date=str(int(opened.timestamp())), minutes=60, open='20', high='21', low='19', close='20',volume='100')
        result=normalize([row],sessions)
        self.assertEqual('2026-07-02T17:00:00+00:00',result[0]['closed_at'])
        row['minutes']=1440;row['broker_date']='20260702'
        self.assertEqual('2026-07-02T13:30:00+00:00',normalize([row],sessions)[0]['opened_at'])

    def test_missing_session_and_conflicting_duplicate_fail_closed(self):
        row=dict(broker_date='20260702',minutes=1440,open='20',high='21',low='19',close='20',volume='100')
        with self.assertRaisesRegex(ValueError, 'DAILY_SESSION'):normalize([row],[])
        sessions=[dict(start='20260702-09:30:00',end='20260702-16:00:00',day='20260702',time_zone='US/Eastern')]
        with self.assertRaisesRegex(ValueError,'CONFLICTING'):normalize([row,{**row,'close':'20.5'}],sessions)

    def test_archived_history_advisory_is_recorded_but_does_not_complete_query(self):
        w=self.wire();w.connect();req=w._begin('stock_history')
        w.error(req,2188,'subscription notice')
        self.assertFalse(w.done.is_set());self.assertIsNone(w.error_value)
        self.assertEqual(2188,w.events[-1]['code'])
        with self.assertRaises(TimeoutError):w._wait()
        w.historicalDataEnd(req,'','');self.assertEqual([],w._wait());w.disconnect()

    def test_short_first_hour_keeps_authentic_ohlc_and_causal_closing_time(self):
        sessions=[dict(start='20260702-09:30:00',end='20260702-16:00:00',day='20260702',time_zone='US/Eastern')]
        base=dict(minutes=60,open='20',high='21',low='19',close='20',volume='100')
        stamps=[datetime(2026,7,2,13,30,tzinfo=timezone.utc),datetime(2026,7,2,14,tzinfo=timezone.utc)]
        rows=normalize([{**base,'broker_date':str(int(t.timestamp()))} for t in stamps],sessions)
        self.assertEqual(rows[0]['closed_at'],rows[1]['opened_at']);self.assertEqual('21',rows[0]['high'])

    def test_account_download_records_settled_cash_separately_without_sizing(self):
        w=self.wire();w.connect();r=w.account_details()
        self.assertEqual('1000000',next(x['value'] for x in r['values'] if x['tag']=='SettledCash'))
        self.assertNotIn('DU123',str(r));self.assertEqual([],r['portfolio']);w.disconnect()

    def test_account_download_requires_end_and_rejects_foreign_identity(self):
        w=self.wire();w.connect();w._client.reqAccountUpdates=lambda *a:None
        with self.assertRaises(TimeoutError):w.account_details()
        w._begin('stock_account_details');w.updateAccountValue('SettledCash','0','USD','U999')
        self.assertFalse(w.connected);w.disconnect()

    def test_readonly_history_refuses_current_or_out_of_scope_endpoints(self):
        w=self.wire()
        for end in (datetime.now(timezone.utc),datetime(2025,1,1,tzinfo=timezone.utc)):
            with self.assertRaisesRegex(ValueError,'ARCHIVED_HISTORY_ONLY'):w.chunk('SCHX',60,end)
