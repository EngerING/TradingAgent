"""Illustrative assumptions only: these are not an operational cost policy."""
from dataclasses import replace
from decimal import Decimal as D, localcontext
import unittest

from test_r20_v2_profiles import AT, profile
from trading_agent.r20_economics import DailyState, equity
from trading_agent.r20_sizing import CostModel, Limits, Stress, size


def costs(**changes):
    c=dict(open_min=D('1'),close_min=D('1'),open_per_unit=D('0'),close_per_unit=D('0'),
           entry_spread=D('0'),exit_spread=D('0'),entry_slippage=D('0'),exit_slippage=D('0'),
           financing_fixed=D('0'),financing_per_unit=D('0'),evidence='SYNTHETIC_TEST_ONLY')
    c.update(changes); return CostModel(**c)


def limits(**changes):
    p=dict(min_quantity=D('1'),quantity_step=D('1'),initial_margin_fraction=D('.1'),
           initial_margin_buffer=D('0'),h_min=D('.05'),hard_exposure_limit=D('10000'),
           risk_pct_ceiling=D('100'),leverage_ceiling=D('10'),position_ceiling=10,
           max_grid_points=100000,evidence='SYNTHETIC_TEST_ONLY')
    p.update(changes); return Limits(**p)


def stresses(side='LONG',distance=D('.02'),**changes):
    result=[]
    for multiplier in (1,2):
        v=dict(name='stress'+str(multiplier),price_move=(-1 if side=='LONG' else 1)*distance*multiplier,
               existing_loss=D('0'),existing_exposure_change=D('0'),existing_maintenance=D('0'),
               maintenance_fraction=D('.05'),equity_buffer=D('0'),margin_buffer=D('0'),
               extra_fixed_cost=D('0'),extra_unit_cost=D('0'),evidence='SYNTHETIC_TEST_ONLY')
        v.update(changes);result.append(Stress(**v))
    return tuple(result)


def arguments(**changes):
    c=costs(); l=limits(); p=profile(cost_policy_hash=c.policy_hash,operational_policy_hash=l.policy_hash)
    day=DailyState.begin(p,D('100'),AT,boundary_verified=True).observe(p,AT,D('100'),(),())
    v=dict(profile=p,at=AT,side='LONG',price=D('1'),stop_distance=D('.02'),economic_equity=D('100'),
           pending_costs=D('0'),existing_exposure=D('0'),committed_margin=D('0'),free_margin=D('100'),
           liquidity_quantity=D('10000'),open_positions=0,pending_positions=0,daily=day,
           costs=c,limits=l,stresses=stresses())
    v.update(changes)
    # Tests changing a profile also update the daily snapshot, not bypass its identity.
    return v


class SizingTests(unittest.TestCase):
    def test_greatest_quantity_under_allocation(self):
        a=size(**arguments()); self.assertTrue(a.admitted,a.reasons)
        self.assertEqual(D('250'),a.quantity)
        self.assertEqual(D('5'),a.price_risk)
        self.assertEqual(D('8'),a.net_target)
        self.assertFalse(a.paper_execution_eligible)

    def test_risk_allocation_and_leverage_independent(self):
        for change,expected in [({'risk_per_trade_pct':D('2')},D('100')),
                                ({'capital_allocation_pct':D('20')},D('100')),
                                ({'max_leverage':D('3')},D('150'))]:
            v=arguments(); p=replace(v['profile'],**change);v['profile']=p
            v['daily']=DailyState.begin(p,D('100'),AT,boundary_verified=True).observe(p,AT,D('100'),(),())
            self.assertEqual(expected,size(**v).quantity)

    def test_fee_minimum_creates_nonmonotone_admission(self):
        v=arguments(liquidity_quantity=D('50'))
        self.assertFalse(size(**v).admitted)  # target 2 - fees 2 == 0
        v['liquidity_quantity']=D('51')
        self.assertEqual(D('51'),size(**v).quantity)

    def test_leverage_haircut_and_short_nominal_exposure(self):
        l=limits(h_min=D('.5'));v=arguments(limits=l)
        p=replace(v['profile'],operational_policy_hash=l.policy_hash);v['profile']=p
        v['daily']=DailyState.begin(p,D('100'),AT,boundary_verified=True).observe(p,AT,D('100'),(),())
        self.assertEqual(D('245'),size(**v).quantity)
        results=[]
        for side in ('LONG','SHORT'):
            v=arguments(side=side,stop_distance=D('.01'),stresses=stresses(side,D('.01')))
            p=replace(v['profile'],capital_allocation_pct=D('100'),max_leverage=D('10'))
            v['profile']=p;v['daily']=DailyState.begin(p,D('100'),AT,boundary_verified=True).observe(p,AT,D('100'),(),())
            results.append(size(**v))
        self.assertTrue(all(a.admitted for a in results))
        self.assertLess(results[1].quantity,results[0].quantity)

    def test_margin_liquidity_and_daily_limits(self):
        self.assertEqual(D('200'),size(**arguments(liquidity_quantity=D('200'))).quantity)
        self.assertFalse(size(**arguments(free_margin=D('3'))).admitted)
        self.assertLess(size(**arguments(stresses=stresses(maintenance_fraction=D('.99')))).quantity,D('250'))
        v=arguments();p=replace(v['profile'],daily_loss_limit_pct=D('5'));v['profile']=p
        v['daily']=DailyState.begin(p,D('100'),AT,boundary_verified=True).observe(p,AT,D('100'),(),())
        self.assertEqual(D('75'),size(**v).quantity)

    def test_profile_policy_and_day_mismatch_fail_closed(self):
        v=arguments(); v['profile']=None
        self.assertIn('PROFILE_REQUIRED',size(**v).reasons)
        v=arguments();v['costs']=costs(open_min=D('2'))
        self.assertIn('POLICY_MISMATCH',size(**v).reasons)
        v=arguments(economic_equity=D('99'))
        self.assertIn('DAILY_SNAPSHOT_MISMATCH',size(**v).reasons)
        v=arguments();v['at']=v['profile'].effective_until
        self.assertIn('PROFILE_EXPIRED',size(**v).reasons)

    def test_missing_adverse_gap_and_invalid_stress(self):
        self.assertIn('STRESS_COVERAGE_REQUIRED',size(**arguments(stresses=stresses()[:1])).reasons)
        self.assertIn('STRESS_COVERAGE_REQUIRED',size(**arguments(stresses=stresses('SHORT'))).reasons)
        with self.assertRaises(ValueError): stresses(maintenance_fraction=D('-1'))
        with self.assertRaises(ValueError): costs(entry_spread=D('NaN'))

    def test_cup_and_emergency_blocks(self):
        self.assertIn('POSITION_LIMIT',size(**arguments(open_positions=3)).reasons)
        v=arguments();v['daily']=replace(v['daily'],operational_blocks=('EMERGENCY_STOP',))
        self.assertIn('DAILY_OR_OPERATIONAL_BLOCK',size(**v).reasons)

    def test_bounded_search_fails_without_guess(self):
        v=arguments();l=limits(max_grid_points=10);v['limits']=l
        p=replace(v['profile'],operational_policy_hash=l.policy_hash);v['profile']=p
        v['daily']=DailyState.begin(p,D('100'),AT,boundary_verified=True).observe(p,AT,D('100'),(),())
        self.assertIn('SIZING_UNRESOLVED',size(**v).reasons)

    def test_rounding_and_decimal_context(self):
        with localcontext() as c:
            c.prec=4
            a=size(**arguments(liquidity_quantity=D('123.99')))
        self.assertEqual(D('123'),a.quantity)
        self.assertEqual(D('2.92'),a.net_target)

    def test_two_positions_and_pending_snapshot(self):
        from trading_agent.r20_economics import OpenRisk, PendingRisk
        v=arguments(economic_equity=D('95'),pending_costs=D('2'),existing_exposure=D('80'),
                    committed_margin=D('8'),open_positions=2,pending_positions=1)
        p=replace(v['profile'],max_open_positions=4);v['profile']=p
        v['daily']=DailyState.begin(p,D('100'),AT,boundary_verified=True).observe(p,AT,D('95'),
            (OpenRisk('long',D('-2'),D('-4')),OpenRisk('short',D('-3'),D('-6'))),
            (PendingRisk('pending',D('4')),))
        a=size(**v)
        self.assertTrue(a.admitted,a.reasons)
        self.assertEqual(D('100'),a.quantity)  # 6 remaining; new gap loss .04q + 2
        v['daily']=DailyState.from_json(v['daily'].to_json())
        self.assertEqual(a,size(**v))

    def test_reduced_administrative_limit_does_not_emit_exit(self):
        from trading_agent.r20_economics import OpenRisk
        v=arguments(existing_exposure=D('600'),open_positions=1)
        v['daily']=v['daily'].observe(v['profile'],AT,D('100'),(OpenRisk('old',D('0'),D('-1')),),())
        before=v['daily'].to_json(); a=size(**v)
        self.assertFalse(a.admitted);self.assertIn('ADMIN_LEVERAGE_HEADROOM',a.reasons)
        self.assertEqual(before,v['daily'].to_json())
        self.assertFalse(hasattr(a,'exit_order'))

    def test_independent_fraction_oracle_for_long_and_short(self):
        from fractions import Fraction as F
        for side in ('LONG','SHORT'):
            v=arguments(side=side,stresses=stresses(side))
            allowed=[]
            for q in range(1,251):
                E=F(98); X=F(q); L=F(5)
                if F(q,25)-2<=0 or F(q,25)+2>20: continue
                if F(q,10)+2>100 or X>L*E*F(95,100): continue
                ok=True
                for loss in (F(1,50),F(1,25)):
                    px=1-loss if side=='LONG' else 1+loss
                    eq=E-q*loss
                    if q*px>L*eq or q*px*F(1,20)>eq: ok=False
                if ok: allowed.append(q)
            self.assertEqual(D(max(allowed)),size(**v).quantity)

    def test_cost_breakdown_and_hard_guard(self):
        c=costs(open_min=D('2'),close_min=D('2'),entry_spread=D('.0014'),exit_spread=D('.0014'),
                entry_slippage=D('.00045'),exit_slippage=D('.00045'),financing_fixed=D('.25'))
        self.assertEqual(D('6.180091'),c.total(D('839.17')))
        self.assertEqual(D('1.174838'),c.breakdown(D('839.17'))['spread'])
        v=arguments(); l=limits(hard_exposure_limit=D('40'));v['limits']=l
        p=replace(v['profile'],operational_policy_hash=l.policy_hash);v['profile']=p
        v['daily']=DailyState.begin(p,D('100'),AT,boundary_verified=True).observe(p,AT,D('100'),(),())
        self.assertIn('HARD_EXPOSURE',size(**v).reasons)

    def test_arbitrary_cost_precision_does_not_trigger_false_input_error(self):
        d=D('0.001416239476565055862979893344')
        v=arguments(side='SHORT',price=D('1.118005'),stop_distance=d,stresses=stresses('SHORT',d),
                    liquidity_quantity=D('600'))
        # Actual audit cost assumptions make every permitted size unviable.
        c=costs(open_min=D('2'),close_min=D('2'),entry_spread=D('.0014'),exit_spread=D('.0014'),
                entry_slippage=D('.00045'),exit_slippage=D('.00045'),financing_fixed=D('.25'))
        v['costs']=c;p=replace(v['profile'],cost_policy_hash=c.policy_hash);v['profile']=p
        v['daily']=DailyState.begin(p,D('100'),AT,boundary_verified=True).observe(p,AT,D('100'),(),())
        self.assertFalse(size(**v).admitted)


if __name__=='__main__': unittest.main()
