import copy
from decimal import Decimal as D
import unittest
from trading_agent.ai_strategy_researcher.costs import commission_details,commission
from trading_agent.ai_strategy_researcher.simulation import simulate,evaluate
from ai_research_fixtures import candidate,bars


class AIStrategyAccountingTests(unittest.TestCase):
    def pending(self, rows=None, end='2023-01-01', extra_signal=False):
        c=candidate();c.update(pattern='MEAN_REVERSION',max_hold_bars=40)
        r=rows or bars(3,'2022-06-28T14:30:00+00:00')
        s=dict(index=0,signal_at=r[0]['opened_at'],stop=9,target=13,indicators={})
        signals=[s]
        if extra_signal:signals.append(dict(s,index=1,signal_at=r[1]['opened_at']))
        return simulate(r,c,'TIERED_BASE','2022-01-01',end,prepared=(signals,[{}]*len(r)))

    def test_buy_and_sell_regulatory_sides_are_explicit(self):
        buy=commission_details(2,12,'TIERED_BASE','BUY')
        sell=commission_details(2,12,'TIERED_BASE','SELL')
        self.assertEqual(D(0),buy['components']['sec_sell'])
        self.assertEqual(D(0),buy['components']['taf_sell_reserve'])
        self.assertGreater(sell['components']['sec_sell'],0)
        self.assertGreater(sell['components']['taf_sell_reserve'],0)
        self.assertEqual(sell['total'],sum(sell['components'].values()))
        self.assertGreaterEqual(sell['total'],buy['total'])

    def test_minimum_and_cap_override_at_low_trade_value(self):
        for model,minimum in [('TIERED_BASE',D('.35')),('FIXED_FEE_STRESS',D(1))]:
            tiny=commission_details(1,10,model,'BUY')
            self.assertEqual(D('.10'),tiny['components']['base_commission'])
            self.assertEqual(minimum,tiny['minimum'])
        self.assertEqual(D('.35'),commission_details(1,100,'TIERED_BASE','BUY')['components']['base_commission'])
        self.assertEqual(D(1),commission_details(1,100,'FIXED_FEE_STRESS','BUY')['components']['base_commission'])

    def test_fixed_and_tiered_differ_without_double_charging_fixed_clearing(self):
        fixed=commission_details(200,25,'FIXED_FEE_STRESS','BUY')
        tiered=commission_details(200,25,'TIERED_BASE','BUY')
        self.assertEqual(D(1),fixed['components']['base_commission'])
        self.assertEqual(D('.7'),tiered['components']['base_commission'])
        self.assertEqual(D(0),fixed['components']['clearing'])
        self.assertEqual(D(0),fixed['components']['pass_through'])
        self.assertGreater(tiered['components']['clearing'],0)
        self.assertNotEqual(fixed['total'],tiered['total'])

    def test_unknown_fees_keep_allowance_and_cannot_be_presented_as_verified(self):
        d=commission_details(1,10,'FIXED_FEE_STRESS','SELL')
        self.assertEqual('UNKNOWN',d['effective_account_fees'])
        self.assertEqual(D('.03'),d['components']['unallocated_fee_allowance'])
        self.assertIn('NOT_A_GUARANTEED',d['allowance_status'])
        self.assertIn('NOT_CURRENT_INVOICE',d['taf_policy'])
        self.assertEqual(d['total'],d['total'].quantize(D('.01')))

    def test_fee_rejects_indeterminate_side_or_fractional_inventory(self):
        for args in [(1,10,'TIERED_BASE','SHORT'),(.5,10,'TIERED_BASE','BUY'),(0,10,'TIERED_BASE','BUY')]:
            with self.assertRaises(ValueError):commission_details(*args)

    def test_pending_buy_cost_and_nav_reconcile_cash_without_counting_win(self):
        out=self.pending();m=out['metrics'];p=out['inventory']['positions'][0]
        expected=p['quantity']*(p['market_price']-p['entry_fill'])-p['opening_commission']
        self.assertAlmostEqual(expected,m['portfolio_net_pnl'])
        self.assertAlmostEqual(100+expected,m['equity'])
        self.assertEqual(0,m['net_pnl']);self.assertEqual(0,m['admitted'])
        self.assertIsNone(m['win_rate']);self.assertIsNone(m['profit_factor'])
        self.assertEqual(p['opening_commission'],m['commissions_incurred'])
        self.assertEqual(0,m['closing_commissions']);self.assertFalse(p['definitive'])
        self.assertEqual('PREVIOUS_RESULT_NOT_DEFINITIVE',p['decision'])
        nav=out['inventory']
        self.assertAlmostEqual(nav['cash_book']+nav['unsettled_proceeds']+p['market_value'],m['equity'])
        self.assertTrue(nav['asset_nav_reconciled'])

    def test_profitable_open_mark_does_not_become_win_or_restore_consumed_budget(self):
        r=bars(3,'2022-06-28T14:30:00+00:00');r[-1].update(high=12,close=11)
        out=self.pending(r);m=out['metrics']
        self.assertGreater(m['portfolio_net_pnl'],0);self.assertEqual(0,m['admitted'])
        self.assertIsNone(m['win_rate']);self.assertEqual(0,m['consumed_loss'])
        self.assertFalse(out['inventory']['portfolio_definitive'])

    def test_pending_risk_and_liquidation_costs_remain_reserves_not_fills(self):
        out=self.pending();p=out['inventory']['positions'][0];m=out['metrics']
        self.assertGreater(p['remaining_stop_risk'],0)
        self.assertGreater(p['estimated_closing_commission'],0)
        self.assertLess(m['estimated_liquidation_equity'],m['equity'])
        self.assertEqual(0,m['closing_commissions'])
        self.assertEqual(0,m['commissions'])

    def test_no_second_entry_when_inventory_is_unresolved(self):
        m=self.pending(extra_signal=True)['metrics']
        self.assertEqual(1,m['rejection_reasons']['ONE_POSITION_OR_UNCERTAIN_CLOSE'])
        self.assertEqual(1,m['rejection_reasons']['UNRESOLVED_PARTITION_POSITION'])
        self.assertTrue(m['pending_position'])

    def test_window_valuation_and_exit_ignore_future_prices(self):
        r=bars(3,'2022-06-30T20:00:00+00:00')
        a=self.pending(r,'2022-07-01');changed=copy.deepcopy(r)
        for b in changed[2:]:b.update(open=50,high=60,low=1,close=55)
        b=self.pending(changed,'2022-07-01')
        self.assertEqual(a,b)
        self.assertLess(a['inventory']['positions'][0]['mark_at'],'2022-07-01')

    def test_bar_closing_at_end_is_not_used_as_a_mark(self):
        r=bars(2,'2022-06-30T21:00:00+00:00')
        r[-1].update(closed_at='2022-07-01T00:00:00+00:00',high=12,close=11)
        out=self.pending(r,'2022-07-01');p=out['inventory']['positions'][0]
        self.assertEqual(r[0]['closed_at'],p['mark_at']);self.assertEqual(10,p['market_price'])

    def test_closed_trade_charges_each_side_once_and_separates_price_costs(self):
        r=bars(2,'2022-06-28T14:30:00+00:00');r[-1].update(high=14)
        out=self.pending(r);m=out['metrics'];t=out['trades'][0];q=t['quantity']
        self.assertAlmostEqual(t['commissions'],t['opening_commission']+t['closing_commission'])
        self.assertEqual(float(commission(q,t['entry_fill'],'TIERED_BASE','BUY')),t['opening_commission'])
        self.assertEqual(float(commission(q,t['exit_fill'],'TIERED_BASE','SELL')),t['closing_commission'])
        self.assertAlmostEqual(t['gross_pnl']-t['net_pnl'],t['commissions']+t['spread_slippage'])
        self.assertAlmostEqual(t['spread_slippage'],t['spread_cost']+t['slippage_cost']+t['price_rounding_cost'])
        self.assertAlmostEqual(m['commissions'],m['commissions_incurred'])
        self.assertAlmostEqual(m['portfolio_net_pnl'],m['net_pnl'])
        self.assertFalse(m['pending_position']);self.assertEqual([],out['inventory']['positions'])

    def test_pending_drawdown_includes_marked_losses(self):
        r=bars(3,'2022-06-28T14:30:00+00:00');r[-1].update(low=9.2,close=9.4)
        m=self.pending(r)['metrics']
        self.assertGreater(m['marked_drawdown'],0)
        self.assertGreaterEqual(m['maximum_drawdown'],m['marked_drawdown'])

    def test_formal_evaluation_retains_unknown_account_cost_block(self):
        out=evaluate(dict(candidate=candidate(),rows=bars(100),family_comparisons=222,limitations=[]))
        self.assertIn('EFFECTIVE_ACCOUNT_FEES_AND_EXECUTION_UNKNOWN',out['rejection_reasons'])
        self.assertFalse(out['execution_authorized']);self.assertFalse(out['final_holdout_evaluated'])
