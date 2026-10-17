"""Proposal evidence and arithmetic, never broker charges or operational policy."""
from dataclasses import FrozenInstanceError
from decimal import Decimal as D
import json,unittest
from pathlib import Path
from trading_agent.r20_cost_policy import CostPolicy

class PolicyTests(unittest.TestCase):
    def setUp(self):self.p=CostPolicy.from_json(Path('config/r20-v2-cost-policy.proposed.json').read_text(encoding='utf-8'))
    def test_unknowns_do_not_become_zero_or_permission(self):
        self.assertEqual(('COST_POLICY_NOT_APPROVED','SLIPPAGE_COST_UNBOUNDED','FINANCING_COST_UNBOUNDED'),self.p.normal_entry_blockers)
        self.assertEqual('0.00045',self.p.components[2].assumption)
        self.assertEqual('UNBOUNDED_ASSUMPTION',self.p.components[2].status)
    def test_published_tariff_is_estimate_even_with_full_arithmetic(self):
        self.assertEqual((D('2'),D('2')),self.p.commission_estimate(D('839.17'),D('1.118005'),D('1.1151725'),entry_orders=1,exit_orders=1))
        self.assertEqual((D('22'),D('20')),self.p.commission_estimate(D('1000000'),D('1.1'),D('1'),entry_orders=1,exit_orders=1))
        self.assertEqual((D('4'),D('2')),self.p.commission_estimate(D('100'),D('1'),D('1'),entry_orders=2,exit_orders=1))
        self.assertEqual((D('44'),D('20')),self.p.commission_estimate(D('1000000'),D('1.1'),D('1'),entry_orders=2,exit_orders=1))
    def test_profile_evidence_is_immutable_and_tampering_rejected(self):
        with self.assertRaises(FrozenInstanceError):self.p.version=2
        obj=json.loads(self.p.to_json());obj['components'][2]['status']='EVIDENCE_BOUND'
        with self.assertRaisesRegex(ValueError,'HASH'):CostPolicy.from_json(json.dumps(obj))
        self.assertEqual(self.p,CostPolicy.from_json(self.p.to_json()))

if __name__=='__main__':unittest.main()
