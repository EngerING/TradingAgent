import unittest
from types import SimpleNamespace
from trading_agent.broker import PaperOptions
from trading_agent.paper_account_capabilities import capabilities_wire, observed, account_facts
from test_equity_research_data import StockClient


class CapClient(StockClient):
    def reqAccountSummary(self,req,group,tags):
        for tag,value,currency in (('$LEDGER-AccountOrGroup','DU123',''),('$LEDGER-CashBalance','123.45','USD'),
            ('$LEDGER-SettledCash','0','USD'),('AvailableFunds','1000000','USD')):
            self.wrapper.accountSummary(req,'DU123',tag,value,currency)
        self.wrapper.accountSummaryEnd(req)
    def reqAccountUpdatesMulti(self,req,account,model,ledger):
        self.wrapper.accountUpdateMulti(req,account,model,'DayTradesRemaining','-1','')
        self.wrapper.accountUpdateMultiEnd(req)
    def cancelAccountUpdatesMulti(self,*args):pass


class PaperAccountCapabilitiesTests(unittest.TestCase):
    def wire(self):
        return capabilities_wire(PaperOptions('DU123',paper_mode_attested=True,timeout=.02),
            (CapClient,object,SimpleNamespace))

    def test_every_order_mutation_and_what_if_stays_blocked(self):
        w=self.wire();w.connect()
        for name in ('placeOrder','placeOrderProtoBuf','cancelOrder','reqGlobalCancel','exerciseOptions','reqAutoOpenOrders'):
            with self.assertRaises(PermissionError):getattr(w._client,name)(1)
        w.disconnect()

    def test_prefixed_ledger_preserves_currency_and_actual_zero(self):
        w=self.wire();w.connect();rows=w.values('ledger')
        self.assertEqual('0',next(x['value'] for x in rows if x['tag']=='SettledCash'))
        self.assertEqual('$LEDGER-CashBalance',rows[0]['original_tag'])
        self.assertNotIn('DU123',str(rows));w.disconnect()

    def test_foreign_identity_inside_ledger_metadata_invalidates_connection(self):
        w=self.wire();w.connect();req=w._begin('cap_ledger')
        w.accountSummary(req,'DU123','$LEDGER-AccountOrGroup','U123','')
        self.assertFalse(w.connected);self.assertEqual([],w.data);w.disconnect()

    def test_foreign_account_and_late_callbacks_do_not_supply_data(self):
        w=self.wire();w.connect();req=w._begin('cap_summary')
        w.accountSummary(req-1,'DU123','SettledCash','50','USD');self.assertEqual([],w.data)
        w.accountSummaryEnd(req-1);self.assertFalse(w.done.is_set())
        w.accountSummary(req,'U123','SettledCash','50','USD');self.assertFalse(w.connected);w.disconnect()

    def test_missing_callback_is_timeout_not_completed_empty(self):
        w=self.wire();w.connect();w._client.reqAccountSummary=lambda *a:None
        with self.assertRaises(TimeoutError):w.values('summary')
        self.assertIsNone(w.active);w.disconnect()

    def test_multimodel_scope_cannot_be_account_funds(self):
        w=self.wire();w.connect();req=w._begin('cap_multi')
        w.accountUpdateMulti(req,'DU123','Other','SettledCash','50','USD')
        with self.assertRaisesRegex(ValueError,'ACCOUNT_MODEL_UNCERTAIN'):w._wait()
        w.disconnect()

    def test_nonfinite_or_sentinel_numeric_fails_closed(self):
        for value in ('NaN','Infinity','1e308'):
            w=self.wire();w.connect();w._begin('cap_ledger');w.accept_value('CashBalance',value,'USD')
            with self.assertRaises(ValueError):w._wait()
            w.disconnect()

    def observation(self):
        return dict(identity_verified=True,environment='PAPER_TRADING',completed_at='2026-10-06T00:00:00Z',
            queries={'ledger':dict(complete=True,callback='accountSummaryEnd',rows=[dict(tag='SettledCash',
                value='0',currency='USD',received_at='2026-10-06T00:00:00Z')])})

    def test_missing_incomplete_conflicting_or_base_currency_is_unknown(self):
        o=self.observation();self.assertEqual('0',observed(o,'SettledCash','USD')['value'])
        o['queries']['ledger']['complete']=False;self.assertIsNone(observed(o,'SettledCash','USD'))
        o['queries']['ledger']['complete']=True;o['queries']['ledger']['rows'][0]['currency']='BASE'
        self.assertIsNone(observed(o,'SettledCash','USD'))
        o=self.observation();o['queries']['ledger']['rows'].append(dict(tag='SettledCash',value='1',currency='USD',received_at='2026-10-06T00:00:00Z'))
        self.assertIsNone(observed(o,'SettledCash','USD'))

    def test_live_or_unverified_observation_never_becomes_paper_evidence(self):
        o=self.observation();o['environment']='LIVE_TRADING';self.assertIsNone(observed(o,'SettledCash','USD'))
        o['environment']='PAPER_TRADING';o['identity_verified']=False;self.assertIsNone(observed(o,'SettledCash','USD'))

    def test_balance_contract_or_fractional_minimum_cannot_verify_permissions_or_fees(self):
        o=self.observation();o['symbols']={'SPY':dict(contract=dict(minimum_size='.0001',order_types='LMT,STP,OCA'))}
        f={x['name']:x for x in account_facts(o)}
        for name in ('fractional_permissions','stock_etf_permissions','effective_fee_plan','effective_bracket_acceptance'):
            self.assertEqual('UNKNOWN',f[name]['status']);self.assertIsNone(f[name]['value'])
        self.assertEqual('VERIFIED',f['SettledCash_USD']['status']);self.assertTrue(f['SettledCash_USD']['observed_at'])

    def test_negative_daytrade_value_is_literal_not_unlimited_permission(self):
        w=self.wire();w.connect();rows=w.values('multi');self.assertEqual('-1',rows[0]['value']);w.disconnect()

    def test_unknown_query_and_identity_bearing_fields_are_rejected(self):
        w=self.wire()
        with self.assertRaises(ValueError):w.values('what_if')
        w.connect();w._begin('cap_updates');w.accept_value('AccountName','Private Name','')
        w.accept_value('AccountType','Private Name','');self.assertEqual([],w.data);w.disconnect()
