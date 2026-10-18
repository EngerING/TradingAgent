"""Boundary abuse cases and declared offline dependency surface."""
import ast
from dataclasses import replace
import json
from pathlib import Path
import unittest

from test_core_v3_research_contracts import AT
from test_core_v34_signals import case
from trading_agent.core_v3.contracts import ContractError, content_hash
from trading_agent.core_v3.economic_contracts import Direction
from trading_agent.core_v3.strategy_v34.contracts import Strategy, Timeframe
from trading_agent.core_v3.strategy_v34.designer import SimulatedStrategyDesigner
from trading_agent.core_v3.strategy_v34.signals import CandleSeries, evaluate
from trading_agent.core_v3.strategy_v34.validation import validate


class StrategySecurityTests(unittest.TestCase):
    def test_nested_unknown_fields_and_permissions_rejected_at_each_boundary(self):
        req, strategy, series = case()
        for cls, data in [(Strategy, strategy.to_dict()), (CandleSeries, series.to_dict())]:
            for payload in [dict(data, path='.local'), dict(data, schema_version=True)]:
                with self.subTest(cls=cls), self.assertRaises(ContractError):
                    cls.from_dict(payload)
        for field in ('instrument', 'scenario'):
            data = strategy.to_dict()
            data[field]['code'] = 'exec("side effect")'
            with self.assertRaises(ContractError):
                Strategy.from_dict(data)

    def test_opposite_direction_and_currency_unit_tampering_rejected(self):
        req, strategy, _ = case()
        scenario = strategy.scenario
        variants = [replace(scenario, direction=Direction.SHORT, stop=scenario.target, target=scenario.stop),
                    replace(scenario, quantity=replace(scenario.quantity, unit='SHARE')),
                    replace(scenario, entry=replace(scenario.entry, currency='EUR'))]
        for value in variants:
            with self.subTest(value=value), self.assertRaises(ContractError):
                validate(replace(strategy, scenario=value), req, Timeframe.M1, now=AT)

    def test_instrument_specification_hash_prevents_same_symbol_substitution(self):
        req, strategy, _ = case()
        identity = replace(strategy.instrument, specification_version=2)
        with self.assertRaises(ContractError):
            validate(replace(strategy, instrument=identity), req, Timeframe.M1, now=AT)

    def test_validation_rejects_non_request_before_accessing_attributes(self):
        req, strategy, _ = case()
        for bad in (None, {}, object(), True):
            forged_binding = replace(strategy, request_sha256=content_hash(None))
            with self.subTest(bad=bad), self.assertRaises(ContractError):
                validate(forged_binding, bad, Timeframe.M1, now=AT)

    def test_simulated_response_size_is_limited_before_parsing(self):
        for raw in (' ' * 32769, b'{}', 1):
            with self.assertRaises(ContractError):
                SimulatedStrategyDesigner(raw)

    def test_import_surface_has_no_transports_persistence_or_dynamic_execution(self):
        root = Path(__file__).resolve().parents[1] / 'trading_agent/core_v3/strategy_v34'
        allowed = {'dataclasses', 'datetime', 'decimal', 'enum', 'contracts', 'economic_contracts',
                   'research_contracts', 'economics', 'validation'}
        forbidden = {'eval', 'exec', 'compile', '__import__', 'open', 'getattr', 'setattr'}
        for path in root.glob('*.py'):
            tree = ast.parse(path.read_text(encoding='utf-8'))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    self.assertTrue(all(v.name in allowed for v in node.names), path.name)
                if isinstance(node, ast.ImportFrom):
                    self.assertIn(node.module, allowed, path.name)
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    self.assertNotIn(node.func.id, forbidden, path.name)
            self.assertFalse(any(isinstance(n, (ast.With, ast.Try)) for n in tree.body), path.name)

    def test_schema_definitions_are_closed_and_match_recursive_wire_examples(self):
        root = Path(__file__).resolve().parents[2]
        schema = json.loads((root / 'contracts/core-v3/strategy-v34/v1/strategy.schema.json').read_text(encoding='utf-8'))
        self.assertEqual('urn:trading:core-v3:strategy-v34:v1', schema['$id'])
        definitions = schema['$defs']
        for definition in definitions.values():
            self.assertFalse(definition['additionalProperties'])
            self.assertEqual(set(definition['properties']), set(definition['required']))

        def check(value, definition):
            if '$ref' in definition:
                definition = definitions[definition['$ref'].rsplit('/', 1)[-1]]
            if 'const' in definition:
                self.assertEqual(definition['const'], value)
            if definition.get('type') == 'object':
                self.assertEqual(set(definition['properties']), set(value))
                for key, child in definition['properties'].items():
                    check(value[key], child)
            if definition.get('type') == 'array':
                self.assertLessEqual(len(value), definition['maxItems'])
                for child in value:
                    check(child, definition['items'])
        req, strategy, series = case()
        for value, name in [(strategy, 'Strategy'), (series, 'CandleSeries'),
                            (evaluate(strategy, req, series, as_of=AT), 'SignalResult')]:
            check(value.to_dict(), definitions[name])
