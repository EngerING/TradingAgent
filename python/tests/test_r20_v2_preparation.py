"""Phase 2 contracts: no activation and no broker calls."""
from dataclasses import replace
from decimal import Decimal as D
import unittest
from test_r20_v2_sizing import arguments
from trading_agent.r20_economics import DailyState
from trading_agent.r20_sizing import AllocationRequest, size
from trading_agent.r20_preparation import validate_values, theoretical

VALUES=dict(logical_capital_usd='100',allocation_usd='20',requested_allocation_leverage='20',
    risk_per_trade_pct='1',daily_loss_limit_pct='5',max_open_positions='1',environment='SHADOW')

class PreparationMathTests(unittest.TestCase):
    def test_reference_and_changes(self):
        self.assertEqual('400',theoretical(VALUES)['exposure_target_usd'])
        self.assertEqual('4',theoretical(VALUES)['target_account_leverage'])
        self.assertEqual('200',theoretical(dict(VALUES,allocation_usd='10'))['exposure_target_usd'])
        self.assertEqual('100',theoretical(dict(VALUES,requested_allocation_leverage='5'))['exposure_target_usd'])
        self.assertEqual('2',theoretical(dict(VALUES,logical_capital_usd='200'))['target_account_leverage'])

    def test_missing_limits_are_never_defaults(self):
        v=dict(VALUES,risk_per_trade_pct='',daily_loss_limit_pct='',max_open_positions='')
        self.assertEqual('400',theoretical(v)['exposure_target_usd'])
        with self.assertRaisesRegex(ValueError,'REQUIRED'):validate_values(v)

    def test_invalid_fields_and_environments(self):
        for k,value in [('allocation_usd','NaN'),('requested_allocation_leverage','0'),
                        ('logical_capital_usd','-1'),('risk_per_trade_pct','101'),
                        ('daily_loss_limit_pct','0'),('max_open_positions','1.5'),('environment','LIVE')]:
            with self.subTest(k=k),self.assertRaises(ValueError):validate_values(dict(VALUES,**{k:value}))
        with self.assertRaises(ValueError):validate_values(dict(VALUES,ordersSupported=True))

    def test_fixed_allocation_reuses_solver_without_raising_account_cap(self):
        args=arguments()
        # Explicit synthetic margin assumption; not a broker requirement.
        args['limits']=replace(args['limits'],initial_margin_fraction=D('.04'))
        args['profile']=replace(args['profile'],operational_policy_hash=args['limits'].policy_hash)
        args['daily']=DailyState.begin(args['profile'],D(100),args['at'],boundary_verified=True).observe(args['profile'],args['at'],D(100),(),())
        request=AllocationRequest(D('20'),D('20'))
        result=size(**args,allocation_request=request)
        self.assertTrue(result.admitted,result.reasons)
        self.assertEqual(D('400'),result.exposure)
        self.assertEqual(D('20'),result.allocation)
        self.assertEqual(D('5'),args['profile'].max_leverage)
        limited=size(**args,allocation_request=AllocationRequest(D('20'),D('100')))
        self.assertLess(limited.exposure,D('500'))

    def test_assigned_capital_bounds_margin_and_cost_not_only_nominal_target(self):
        result=size(**arguments(),allocation_request=AllocationRequest(D('20'),D('20')))
        self.assertTrue(result.admitted)
        self.assertLessEqual(result.initial_margin+result.estimated_costs,D('20'))
        self.assertLess(result.exposure,D('400'))

    def test_rounding_never_exceeds_target_and_unknown_typed_input_rejected(self):
        result=size(**arguments(price=D('1.13')),allocation_request=AllocationRequest(D('20'),D('20')))
        self.assertTrue(result.admitted,result.reasons)
        self.assertLessEqual(result.exposure,D('400'))
        with self.assertRaises(ValueError):size(**arguments(),allocation_request={'allocation_usd':'20'})

    def test_existing_solver_hash_unchanged_without_allocation(self):
        first=size(**arguments())
        self.assertEqual(first,size(**arguments(),allocation_request=None))
        self.assertNotEqual(first.input_hash,size(**arguments(),allocation_request=AllocationRequest(D('20'),D('20'))).input_hash)

if __name__=='__main__':unittest.main()
