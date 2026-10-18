"""Historical compatibility on JSON in memory, never operational stores."""
import ast
from dataclasses import FrozenInstanceError, replace
from datetime import timedelta
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import unittest

from test_core_v3_contracts import eurusd, synthetic_equity
from test_forex_research_economics import AT, context, plan
from test_forex_research_runner import proposal
from trading_agent.ai_strategy_researcher.strategy_bundle_v2 import build_bundle
from trading_agent.forex_research.economics import assess
from trading_agent.core_v3.contracts import ContractError, Environment, SourceKind, content_hash, strict_json
from trading_agent.core_v3.legacy_import import (
    ImportedEconomicAssessment, ImportedStrategy, import_forex_assessment, import_forex_bundle,
)


def bundle_text(direction='SHORT'):
    value = json.loads(proposal(direction))
    return json.dumps(build_bundle(value['candidate'], value['rules']), indent=2) + '\n'


def assessment_inputs(direction='SHORT'):
    c, p = context(), plan(direction)
    return dict(raw=json.dumps(assess(c, p, now=AT)), context_json=json.dumps(c),
                plan_json=json.dumps(p), assessed_at=AT, instrument=eurusd())


class BundleImportTests(unittest.TestCase):
    def test_preserves_utf8_bom_and_windows_line_endings(self):
        raw = b'\xef\xbb\xbf' + bundle_text().replace('\n', '\r\n').encode('utf-8')
        imported = import_forex_bundle(raw, instrument=eurusd())
        self.assertEqual(raw, imported.original_json.encode('utf-8'))
        self.assertEqual(hashlib.sha256(raw).hexdigest(), imported.to_dict()['original_sha256'])
        self.assertEqual(imported, ImportedStrategy.from_json(imported.to_json()))

    def test_absent_import_metadata_is_a_controlled_error(self):
        with self.assertRaises(ContractError):
            import_forex_bundle(bundle_text())
        with self.assertRaises(ContractError):
            import_forex_assessment(assessment_inputs()['raw'])

    def test_preserves_original_bytes_all_hashes_direction_and_unknown_statistics(self):
        raw = bundle_text()
        original = json.loads(raw)
        imported = import_forex_bundle(raw.encode(), instrument=eurusd())
        self.assertEqual(raw, imported.original_json)
        self.assertEqual(hashlib.sha256(raw.encode()).hexdigest(), imported.to_dict()['original_sha256'])
        self.assertEqual({name: original[name] for name in
                          ('candidate_sha256', 'rules_sha256', 'bundle_sha256')},
                         imported.to_dict()['original_hashes'])
        self.assertEqual('SHORT', imported.direction)
        self.assertEqual(60, imported.timeframe_minutes)
        self.assertIsNone(imported.to_dict()['statistically_validated'])
        self.assertFalse(imported.to_dict()['economically_approved'])
        self.assertFalse(imported.to_dict()['execution_authority'])
        self.assertEqual('NO_TRADE', imported.to_dict()['trading_decision'])
        self.assertEqual(SourceKind.CALLER_UNVERIFIED, imported.provenance.source_kind)
        self.assertIsNone(imported.provenance.observed_at)
        self.assertEqual(imported, ImportedStrategy.from_json(imported.to_json()))

    def test_never_broadens_direction_and_preserves_risk_category_initial_capital(self):
        for direction in ('LONG', 'SHORT'):
            imported = import_forex_bundle(bundle_text(direction), instrument=eurusd())
            self.assertEqual(direction, imported.direction)
            self.assertEqual('MODERATE', imported.to_dict()['risk_profile'])
            self.assertEqual({'amount': '100', 'currency': 'USD'}, imported.to_dict()['research_capital'])

    def test_tampered_original_or_forged_v3_derived_fields_rejected(self):
        original = json.loads(bundle_text())
        original['rules']['entry']['all'][0]['right'] = 99
        with self.assertRaisesRegex(ContractError, 'LEGACY_BUNDLE_INVALID'):
            import_forex_bundle(json.dumps(original), instrument=eurusd())
        imported = import_forex_bundle(bundle_text(), instrument=eurusd())
        for field, value in (('direction', 'LONG'), ('economically_approved', True),
                             ('statistically_validated', True), ('execution_authority', True),
                             ('live_enabled', True), ('paper_execution_eligible', True),
                             ('schema_version', 2), ('schema_version', True), ('unexpected', 0)):
            data = imported.to_dict()
            data[field] = value
            with self.subTest(field=field), self.assertRaises(ContractError):
                ImportedStrategy.from_dict(data)

    def test_bool_zero_substitution_and_duplicate_keys_cannot_exploit_legacy_equality(self):
        for field in ('backtested', 'rules_compiled', 'execution_authority', 'live_enabled'):
            value = json.loads(bundle_text())
            value[field] = 0
            with self.subTest(field=field), self.assertRaises(ContractError):
                import_forex_bundle(json.dumps(value), instrument=eurusd())
        with self.assertRaises(ContractError):
            import_forex_bundle(bundle_text().replace('"version": 1', '"version": 1, "version": 1'),
                                instrument=eurusd())

    def test_missing_wrong_instrument_or_units_never_receive_inferred_metadata(self):
        for instrument in (None, synthetic_equity(), replace(eurusd(), quantity_unit='LOT',
                           tick=replace(eurusd().tick, per_unit='LOT'),
                           minimum_quantity=replace(eurusd().minimum_quantity, unit='LOT'),
                           quantity_step=replace(eurusd().quantity_step, unit='LOT'))):
            with self.subTest(instrument=instrument), self.assertRaises(ContractError):
                import_forex_bundle(bundle_text(), instrument=instrument)

    def test_import_is_deeply_immutable_and_original_views_are_detached(self):
        imported = import_forex_bundle(bundle_text(), instrument=eurusd())
        prior = content_hash(imported)
        copy = imported.original_value()
        copy['candidate']['direction'] = 'LONG'
        with self.assertRaises(FrozenInstanceError):
            imported.original_json = '{}'
        self.assertEqual('SHORT', imported.direction)
        self.assertEqual(prior, content_hash(imported))


class AssessmentImportTests(unittest.TestCase):
    def test_preserves_bom_in_each_original_document(self):
        inputs = assessment_inputs()
        for name in ('raw', 'context_json', 'plan_json'):
            inputs[name] = '\ufeff' + inputs[name]
        imported = import_forex_assessment(**inputs)
        self.assertEqual(inputs['raw'], imported.original_json)
        self.assertEqual(inputs['context_json'], imported.context_json)
        self.assertEqual(inputs['plan_json'], imported.plan_json)
        self.assertEqual(imported, ImportedEconomicAssessment.from_json(imported.to_json()))

    def test_unverified_source_is_preserved_without_claiming_authentic_capture(self):
        inputs = assessment_inputs()
        c, p = json.loads(inputs['context_json']), json.loads(inputs['plan_json'])
        c['source'] = 'CALLER_SUPPLIED_UNVERIFIED'
        inputs.update(raw=json.dumps(assess(c, p, now=AT)), context_json=json.dumps(c))
        imported = import_forex_assessment(**inputs)
        self.assertEqual(SourceKind.CALLER_UNVERIFIED, imported.provenance.source_kind)

    def test_import_preserves_conditional_admission_and_input_hash_without_promotion(self):
        inputs = assessment_inputs()
        original = json.loads(inputs['raw'])
        imported = import_forex_assessment(**inputs)
        self.assertTrue(imported.source_admitted)
        self.assertEqual(inputs['raw'], imported.original_json)
        self.assertEqual(original['input_sha256'], imported.to_dict()['original_hashes']['input_sha256'])
        self.assertEqual(original['metrics'], imported.original_value()['metrics'])
        self.assertEqual(SourceKind.SYNTHETIC, imported.provenance.source_kind)
        self.assertEqual(Environment.RESEARCH, imported.provenance.environment)
        for flag in ('statistically_validated', 'broker_executability_verified', 'economically_approved',
                     'execution_authority', 'paper_execution_eligible', 'live_enabled'):
            self.assertIs(False, imported.to_dict()[flag])
        self.assertEqual(imported, ImportedEconomicAssessment.from_json(imported.to_json()))

    def test_expired_historical_evidence_can_be_archived_but_never_used_as_current(self):
        imported = import_forex_assessment(**assessment_inputs())
        imported.provenance.require_current(AT)
        with self.assertRaisesRegex(ContractError, 'EVIDENCE_NOT_CURRENT'):
            imported.provenance.require_current(AT + timedelta(days=1))
        inputs = assessment_inputs()
        inputs['assessed_at'] = AT + timedelta(days=1)
        with self.assertRaisesRegex(ContractError, 'LEGACY_ASSESSMENT_MISMATCH'):
            import_forex_assessment(**inputs)

    def test_unknown_cost_rejection_preserves_absence_of_metrics_and_hash(self):
        inputs = assessment_inputs()
        c, p = json.loads(inputs['context_json']), json.loads(inputs['plan_json'])
        c['costs']['status'] = 'UNKNOWN'
        inputs.update(raw=json.dumps(assess(c, p, now=AT)), context_json=json.dumps(c))
        imported = import_forex_assessment(**inputs)
        self.assertFalse(imported.source_admitted)
        self.assertEqual({}, imported.original_value()['metrics'])
        self.assertIsNone(imported.to_dict()['original_hashes']['input_sha256'])

    def test_invalid_missing_or_changed_context_geometry_and_hash_fail_closed(self):
        for field, value in (('context_json', '{}'), ('plan_json', '{}'),
                             ('assessed_at', None), ('instrument', None)):
            inputs = assessment_inputs()
            inputs[field] = value
            with self.subTest(field=field), self.assertRaises(ContractError):
                import_forex_assessment(**inputs)
        inputs = assessment_inputs()
        c = json.loads(inputs['context_json'])
        c['equity_usd'] = '99'
        inputs['context_json'] = json.dumps(c)
        with self.assertRaises(ContractError):
            import_forex_assessment(**inputs)

    def test_original_authority_wrong_types_and_forged_wrapper_rejected(self):
        for field, value in (('admitted', 1), ('statistically_validated', 0),
                             ('execution_authority', True), ('live_enabled', True),
                             ('paper_execution_eligible', True), ('scope', 'APPROVED'),
                             ('schema', 'FOREX_ECONOMIC_ASSESSMENT_V2')):
            inputs = assessment_inputs()
            original = json.loads(inputs['raw'])
            original[field] = value
            inputs['raw'] = json.dumps(original)
            with self.subTest(field=field), self.assertRaises(ContractError):
                import_forex_assessment(**inputs)
        imported = import_forex_assessment(**assessment_inputs())
        data = imported.to_dict()
        data['source_admitted'] = False
        with self.assertRaises(ContractError):
            ImportedEconomicAssessment.from_dict(data)

    def test_metadata_conflict_is_rejected_instead_of_unit_or_currency_conversion(self):
        inputs = assessment_inputs()
        inputs['instrument'] = synthetic_equity()
        with self.assertRaises(ContractError):
            import_forex_assessment(**inputs)
        inputs['instrument'] = replace(eurusd(), minimum_quantity=replace(eurusd().minimum_quantity,
                                                                       amount=Decimal('2')))
        with self.assertRaises(ContractError):
            import_forex_assessment(**inputs)


class IsolationTests(unittest.TestCase):
    def test_imports_and_calls_work_when_io_network_and_processes_are_forbidden(self):
        # Calls use preloaded fixtures under an audit hook; no files may be opened.
        import sys
        raw, inputs, instrument = bundle_text(), assessment_inputs(), eurusd()
        enabled = [True]

        def deny(event, args):
            if enabled[0] and event in ('open', 'socket.connect', 'socket.getaddrinfo', 'socket.bind', 'subprocess.Popen'):
                raise AssertionError('V3_IMPORT_MUST_BE_PURE')
        sys.addaudithook(deny)
        try:
            import_forex_bundle(raw, instrument=instrument)
            import_forex_assessment(**inputs)
        finally:
            enabled[0] = False

    def test_versioned_schema_matches_imported_record_fields(self):
        path = Path(__file__).resolve().parents[2] / 'contracts/core-v3/v1/core.schema.json'
        schema = strict_json(path.read_bytes())
        cases = [('importedStrategy', import_forex_bundle(bundle_text(), instrument=eurusd())),
                 ('importedAssessment', import_forex_assessment(**assessment_inputs()))]
        for name, value in cases:
            definition = schema['$defs'][name]
            self.assertFalse(definition['additionalProperties'])
            self.assertEqual(set(value.to_dict()), set(definition['properties']))
            self.assertEqual(set(value.to_dict()), set(definition['required']))

    def test_core_modules_have_no_operational_dependencies_or_import_side_effects(self):
        root = Path(__file__).resolve().parents[2] / 'python/trading_agent/core_v3'
        allowed = {'dataclasses', 'datetime', 'decimal', 'enum', 'hashlib', 'json', 'math', 're',
                   'contracts', 'ai_strategy_researcher.strategy_bundle_v2', 'forex_research.economics',
                   'types', 'typing', 'economic_contracts', 'economic_scenarios', 'economic_calculation'}
        for path in root.glob('*.py'):
            tree = ast.parse(path.read_text(encoding='utf-8'))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    self.assertTrue(all(n.name in allowed for n in node.names), path.name)
                elif isinstance(node, ast.ImportFrom):
                    self.assertIn(node.module, allowed, path.name)
            self.assertFalse(any(isinstance(n, (ast.With, ast.Try)) for n in tree.body), path.name)
