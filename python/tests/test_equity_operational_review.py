import copy
import unittest
from trading_agent.equity_operational_review import cash_geometry, matrix


class EquityOperationalReviewTests(unittest.TestCase):
    def observation(self):
        return dict(identity_verified=True, environment='PAPER_TRADING', queries={},
            completed_at='2026-10-06T00:00:00Z', symbols={s:dict(
                quote=dict(bid=p-.01,ask=p,data_type=3),
                contract=dict(minimum_size='.0001',size_increment='.0001',order_types='LMT,STP,STPLMT,OCA'))
                for s,p in [('SCHX',30),('SPY',775),('F',12)]})

    def test_affordable_whole_share_is_not_execution_permission(self):
        rows={r['symbol']:r for r in matrix(self.observation())}
        self.assertEqual(3,rows['SCHX']['theoretical_max_whole_quantity'])
        self.assertEqual(8,rows['F']['theoretical_max_whole_quantity'])
        self.assertEqual(0,rows['SPY']['theoretical_max_whole_quantity'])
        for row in rows.values():
            self.assertEqual('EXECUTION_CONSTRAINT_BLOCKED',row['status'])
            self.assertFalse(row['execution_authorized'])

    def test_fractional_metadata_cannot_enable_fractional_spy(self):
        row=matrix(self.observation())[1]
        self.assertEqual('UNKNOWN',row['fraction_status'])
        self.assertEqual('UNKNOWN',row['permission_status'])
        self.assertEqual('UNKNOWN',row['protection_effective_status'])
        self.assertEqual('VERIFIED',row['minimum_declared']['status'])

    def test_live_or_unverified_observation_cannot_prove_any_price(self):
        for field,value in [('identity_verified',False),('environment','LIVE_TRADING')]:
            o=self.observation();o[field]=value
            for row in matrix(o):
                self.assertEqual('UNKNOWN',row['price_observation']['status'])
                self.assertEqual(0,row['theoretical_max_whole_quantity'])

    def test_reserves_both_sides_slippage_and_spread_without_using_account_million(self):
        g=cash_geometry('11.99','12',8,'TIERED_BASE')
        self.assertGreater(g['roundtrip_cost_usd'],g['roundtrip_fees_usd'])
        self.assertGreater(g['funds_with_exit_reserve_usd'],g['notional_usd'])
        self.assertFalse(cash_geometry('99.99','100',1,'TIERED_BASE')['fits_virtual_usd100'])
        self.assertEqual('UNKNOWN_NO_SIGNAL_OR_STOP_EVALUATED',g['stop_risk_status'])

    def test_invalid_quote_and_quantity_are_rejected(self):
        for bid,ask,q in [('2','1',1),('NaN','1',1),('0','1',1),('1','1',0),('1','1',.5),('1','1',True)]:
            with self.assertRaises(ValueError):cash_geometry(bid,ask,q,'TIERED_BASE')
        o=self.observation();o['symbols']['F']['quote']['bid']=13
        self.assertEqual('UNKNOWN',matrix(o)[2]['price_observation']['status'])

    def test_complete_settled_cash_is_reported_but_never_grants_permission(self):
        o=self.observation();before=copy.deepcopy(o)
        self.assertEqual('UNKNOWN',matrix(o)[0]['settled_funds_status']);self.assertEqual(before,o)
        o['queries']['summary']=dict(complete=True,callback='accountSummaryEnd',rows=[
            dict(tag='SettledCash',currency='USD',value='100',received_at='2026-10-06T00:00:00Z')])
        row=matrix(o)[0];self.assertEqual('VERIFIED',row['settled_funds_status'])
        self.assertEqual('UNKNOWN',row['permission_status']);self.assertFalse(row['execution_authorized'])
