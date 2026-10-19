"""Closed, frozen statistical boundaries and deterministic byte identities."""
from dataclasses import FrozenInstanceError, replace
from decimal import Decimal as D
import unittest

from test_core_v36_contracts import dataset, policy
from trading_agent.core_v3.contracts import ContractError, Money, content_hash
from trading_agent.core_v3.statistical_validation.contracts import (
    RobustnessScenario, Status, TemporalSplit, Partition, ValidationPolicy, ValidationResult)
from trading_agent.core_v3.statistical_validation.planning import manifest
from trading_agent.core_v3.statistical_validation.statistics import describe


class StatisticalContractTests(unittest.TestCase):
    def values(self):
        return (ValidationPolicy('policy', policy()), manifest('data', (dataset(),)),
                TemporalSplit('train', 1, Partition.TRAIN, 0, 3, 6),
                RobustnessScenario('costs', extra_opening_fee=Money(D('.1'), 'USD')),
                describe((D('1'), D('-2')), (D('2'), D('-1')), 'USD'),
                ValidationResult('0'*64, Status.REJECTED, ('EVIDENCE_CHANGED',), None))

    def test_roundtrip_nested_fields_and_copies(self):
        for value in self.values():
            self.assertEqual(value, type(value).from_json(value.to_json()))
            raw = value.to_dict()
            raw['schema_version'] = 99
            self.assertEqual(value, type(value).from_json(value.to_json()))
            self.assertEqual(content_hash(value), content_hash(type(value).from_json(value.to_json())))

    def test_frozen_and_unknown_fields_versions_duplicates(self):
        for value in self.values():
            with self.assertRaises((FrozenInstanceError, TypeError)):
                value.code = 'anything'
            for key, item in (('schema_version', 2), ('code', 'eval'), ('execution_authority', True)):
                if key in value.to_dict() and key != 'schema_version':
                    continue
                raw = value.to_dict()
                raw[key] = item
                with self.assertRaises(ContractError):
                    type(value).from_dict(raw)
            raw = value.to_json()
            with self.assertRaises(ContractError):
                type(value).from_json('{"schema_version":1,'+raw[1:])

    def test_policy_hard_caps_bool_and_incompatible_semantics(self):
        original = ValidationPolicy('policy', policy())
        for key, value in (('max_windows', 13), ('max_datasets', 5), ('max_candidates', 5),
            ('max_backtests', 65), ('max_trades', 257), ('max_scenarios', 5), ('bootstrap_replicas', 513),
            ('max_input_bytes', 524289), ('max_result_bytes', 131073), ('seed', True),
            ('capital_policy', 'CHAIN'), ('engine_version', 'other')):
            with self.subTest(key=key), self.assertRaises(ContractError):
                replace(original, **{key: value})

    def test_authority_cannot_be_activated_by_any_result_field(self):
        original = ValidationResult('0'*64, Status.REJECTED, ('EVIDENCE_CHANGED',), None)
        for field in ('execution_authority', 'paper_execution_eligible', 'live_enabled', 'statistically_validated'):
            with self.assertRaises(ContractError):
                replace(original, **{field: True})
        with self.assertRaises(ContractError):
            replace(original, trading_decision='ALLOW')

    def test_financial_float_bool_nonfinite_and_mixed_scenarios_rejected(self):
        for amount in (1.0, True, D('NaN'), D('Infinity')):
            with self.assertRaises(ContractError):
                Money(amount, 'USD')
        with self.assertRaises(ContractError):
            RobustnessScenario('invalid', extra_opening_fee=Money(D('-1'), 'USD'))
        with self.assertRaises(ContractError):
            RobustnessScenario('invalid', extra_slippage_ticks=1, close_at_end=False)
