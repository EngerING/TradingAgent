from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timezone
from decimal import Decimal
import json
import unittest

from trading_agent.market_analyst.contracts import (
    AnalystError, Authority, Indicator, Instrument, Policy, SupplementaryEvidenceRef,
)


class ContractTests(unittest.TestCase):
    def test_policy_is_immutable_versioned_and_canonical(self):
        policy = Policy()
        self.assertEqual(Policy.from_json(policy.to_json()), policy)
        self.assertEqual(policy.sha256(), Policy().sha256())
        self.assertNotEqual(policy.sha256(), replace(policy, ema_fast=19).sha256())
        with self.assertRaises(FrozenInstanceError):
            policy.ema_fast = 1

    def test_unknown_fields_versions_duplicates_and_numeric_decimals_rejected(self):
        doc = Policy().to_dict()
        for change in ({'extra': 1}, {'schema_version': True}, {'schema_version': 2},
                       {'trend_gap_atr': .25}, {'ema_fast': True}):
            with self.subTest(change=change), self.assertRaises(AnalystError):
                Policy.from_json(json.dumps({**doc, **change}))
        with self.assertRaises(AnalystError):
            Policy.from_json('{"schema_version":1,"schema_version":1}')
        for raw in ('NaN', '{}', '[]', 'x' * 131073):
            with self.assertRaises(AnalystError):
                Policy.from_json(raw)

    def test_policy_validation_rejects_ambiguous_or_unbounded_settings(self):
        for change in ({'ema_fast': 50}, {'rsi': 0}, {'max_bars': 4097},
                       {'high_volatility_atr_ratio': Decimal('NaN')},
                       {'trend_gap_atr': Decimal('-1')}, {'version': ''}):
            with self.subTest(change=change), self.assertRaises(AnalystError):
                replace(Policy(), **change)

    def test_authority_cannot_be_promoted(self):
        authority = Authority()
        self.assertEqual(authority.decision, 'NO_TRADE')
        for field in ('execution_authorized', 'paper_eligible', 'live_approved'):
            with self.assertRaises(AnalystError):
                replace(authority, **{field: True})

    def test_warmup_and_units_are_explicit(self):
        value = Indicator('rsi', None, 'INDEX_0_100', 15, 3, 'WARMUP')
        self.assertIsNone(Indicator.from_json(value.to_json()).value)
        with self.assertRaises(AnalystError):
            replace(value, value=Decimal('0'))
        self.assertEqual(Instrument().price_unit, 'USD_PER_EUR')

    def test_supplementary_evidence_is_a_reference_without_probability_or_authority(self):
        at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        ref = SupplementaryEvidenceRef('KRONOS', 'future-v1', 'a' * 64, at, at, None)
        self.assertEqual(ref, SupplementaryEvidenceRef.from_json(ref.to_json()))
        self.assertFalse(ref.execution_authorized)
        self.assertNotIn('probability', ref.to_dict())


if __name__ == '__main__':
    unittest.main()
