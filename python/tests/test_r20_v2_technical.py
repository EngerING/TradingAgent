"""Explicit synthetic lab parameters, never user-selected operating limits."""
from dataclasses import replace
from decimal import Decimal as D
import unittest
from test_r20_v2_sizing import arguments
from trading_agent.r20_sizing import size, AllocationRequest
from trading_agent.r20_preparation import validate_purpose


class TechnicalMathTests(unittest.TestCase):
    def test_negative_target_exception_is_explicit_and_hashed(self):
        args=arguments(liquidity_quantity=D(10))
        self.assertFalse(size(**args).admitted)
        result=size(**args,purpose='TECHNICAL_VALIDATION')
        self.assertTrue(result.admitted,result.reasons)
        self.assertLess(result.net_target,0)
        self.assertNotEqual(size(**args).input_hash,result.input_hash)
        self.assertFalse(result.paper_execution_eligible)

    def test_exception_preserves_margin_daily_risk_and_data_guards(self):
        for changes in (dict(free_margin=D(0)),dict(economic_equity=D(0)),
                        dict(open_positions=10),dict(price=D(0))):
            with self.subTest(changes=changes):
                try:result=size(**arguments(**changes),purpose='TECHNICAL_VALIDATION')
                except ValueError:continue
                self.assertFalse(result.admitted)

    def test_normal_hash_and_allocation_unchanged(self):
        self.assertEqual(size(**arguments()),size(**arguments(),purpose='NORMAL'))
        a=size(**arguments(),purpose='TECHNICAL_VALIDATION',allocation_request=AllocationRequest(D(20),D(20)))
        self.assertLessEqual(a.exposure,D(400))
        self.assertLessEqual(a.initial_margin+a.estimated_costs,D(20))

    def test_technical_purpose_is_shadow_only_and_explicit(self):
        self.assertEqual('TECHNICAL_VALIDATION',validate_purpose('TECHNICAL_VALIDATION','SHADOW'))
        for purpose,environment in [('TECHNICAL_VALIDATION','IBKR_PAPER'),('UNKNOWN','SHADOW'),(None,'SHADOW')]:
            with self.assertRaises(ValueError):validate_purpose(purpose,environment)
        with self.assertRaises(ValueError):size(**arguments(),purpose='UNKNOWN')
