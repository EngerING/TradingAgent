"""No dynamic strategies, no mutators, no trusted caller approvals and no silent tampering."""
import ast
from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_core_v35_contracts import budget
from test_core_v36_binding import registered, bound
from test_core_v36_engine import trade_data
from trading_agent.core_v3.contracts import ContractError
from trading_agent.core_v3.research_journal import ResearchJournal
from trading_agent.core_v3.research_designer import SimulatedDesigner
from trading_agent.core_v3.strategy_catalog.service import Catalog
from trading_agent.core_v3.strategy_v34.designer import SimulatedStrategyDesigner
from trading_agent.core_v3.event_backtest.contracts import Status
from trading_agent.core_v3.event_backtest.engine import run


class BacktestSecurityTests(unittest.TestCase):
    def test_result_evidence_and_all_nested_records_reject_authority_extras_and_versions(self):
        with registered() as (_, cmd, catalog, journal):
            value, data, rules = bound(catalog, journal, trade_data(cmd))
            result = run(value, catalog, journal, data, rules)
            records = [result, result.evidence, result.metrics, result.trades[0], result.trades[0].costs,
                       result.fills[0], result.orders[0], result.events[0], result.equity[0]]
            for record in records:
                self.assertEqual(record, type(record).from_json(record.to_json()))
                for field, content in [('execution_authority', True), ('paper_execution_eligible', True),
                                       ('live_enabled', True), ('statistically_validated', True),
                                       ('trading_decision', 'BUY'), ('code', 'ignored'), ('schema_version', 2)]:
                    raw = record.to_dict()
                    raw[field] = content
                    with self.subTest(record=type(record).__name__, field=field), self.assertRaises(ContractError):
                        type(record).from_dict(raw)

    def test_no_catalog_research_provider_budget_or_file_mutation_during_simulation(self):
        with registered() as (_, cmd, catalog, journal):
            value, data, rules = bound(catalog, journal, trade_data(cmd))
            histories = catalog.history(), journal.history(), journal.budget_status()
            with ExitStack() as guards:
                for cls, methods in [(Catalog, ('register', 'reconcile', 'diagnose')),
                                     (ResearchJournal, ('receive', 'admit', 'start', 'record_reply', 'begin_postflight', 'finish', 'fail', 'recover')),
                                     (SimulatedDesigner, ('propose',)), (SimulatedStrategyDesigner, ('propose',))]:
                    for method in methods:
                        guards.enter_context(patch.object(cls, method, side_effect=AssertionError('NO_MUTATION')))
                guards.enter_context(patch('builtins.open', side_effect=AssertionError('NO_FILE_OPEN')))
                result = run(value, catalog, journal, data, rules)
            self.assertEqual(Status.COMPLETE, result.status)
            self.assertEqual(histories, (catalog.history(), journal.history(), journal.budget_status()))

    def test_real_research_corruption_or_source_substitution_rejects_cached_request(self):
        with registered() as (_, cmd, catalog, journal), tempfile.TemporaryDirectory() as other:
            value, data, rules = bound(catalog, journal, trade_data(cmd))
            with ResearchJournal(other, budget()) as replacement:
                rejected = run(value, catalog, replacement, data, rules)
                self.assertEqual(Status.REJECTED, rejected.status)
                self.assertIsNone(rejected.metrics)
            journal.db.execute('DROP TRIGGER immutable_events_update')
            journal.db.execute("UPDATE events SET payload='{}' WHERE sequence=(SELECT MAX(sequence) FROM events)")
            rejected = run(value, catalog, journal, data, rules)
            self.assertEqual(Status.REJECTED, rejected.status)
            self.assertIsNone(rejected.metrics)

    def test_catalog_tail_loss_is_detected_without_repairing_the_catalog(self):
        with registered() as (_, cmd, catalog, journal):
            value, data, rules = bound(catalog, journal, trade_data(cmd))
            db = catalog._store.db
            db.execute('DROP TRIGGER immutable_events_delete')
            db.execute('DELETE FROM events WHERE sequence=(SELECT MAX(sequence) FROM events)')
            count = db.execute('SELECT COUNT(*) FROM events').fetchone()[0]
            result = run(value, catalog, journal, data, rules)
            self.assertEqual(Status.REJECTED, result.status)
            self.assertEqual(count, db.execute('SELECT COUNT(*) FROM events').fetchone()[0])

    def test_source_change_during_simulation_discards_the_unverifiable_result(self):
        from trading_agent.core_v3.event_backtest import engine
        original = engine.load
        calls = []
        def fail_second(*args):
            calls.append(1)
            if len(calls) == 2:
                raise ContractError('BACKTEST_SOURCE_CHANGED')
            return original(*args)
        with registered() as (_, cmd, catalog, journal):
            value, data, rules = bound(catalog, journal, trade_data(cmd))
            with patch.object(engine, 'load', side_effect=fail_second):
                result = engine.run(value, catalog, journal, data, rules)
            self.assertEqual((Status.REJECTED, 'BACKTEST_SOURCE_CHANGED'), (result.status, result.reason))
            self.assertIsNone(result.metrics)
            self.assertFalse(result.trades)

    def test_result_rejects_duplicate_fills_events_and_inconsistent_cross_references(self):
        with registered() as (_, cmd, catalog, journal):
            value, data, rules = bound(catalog, journal, trade_data(cmd))
            result = run(value, catalog, journal, data, rules)
            duplicate_event = replace(next(e for e in result.events if e.kind.value == 'FILL'),
                                      sequence=len(result.events)+1, at=result.events[-1].at)
            last_fill_index = max(i for i, e in enumerate(result.events) if e.kind.value == 'FILL')
            repeated = result.events[:last_fill_index+1]+(result.events[last_fill_index],)+result.events[last_fill_index+1:]
            repeated = tuple(replace(e, sequence=i+1) for i, e in enumerate(repeated))
            for changes in [dict(events=result.events[:1]*2), dict(fills=result.fills[:1]*2),
                            dict(events=result.events+(duplicate_event,)),
                            dict(events=repeated),
                            dict(fills=(replace(result.fills[0], order_id='unknown'),)+result.fills[1:]),
                            dict(metrics=replace(result.metrics, closed_trades=0, winners=0)),
                            dict(metrics=replace(result.metrics, final_realized_capital=replace(result.metrics.final_realized_capital,
                                                                                              amount=result.metrics.initial_capital.amount))),
                            dict(evidence=replace(result.evidence, request=replace(value, dataset_sha256='0'*64)))]:
                with self.subTest(changes=changes), self.assertRaises(ContractError):
                    replace(result, **changes)

    def test_entire_subpackage_has_static_closed_dependencies_and_no_effectful_entrypoint(self):
        root = Path(__file__).resolve().parents[1] / 'trading_agent/core_v3/event_backtest'
        standard = {'dataclasses', 'datetime', 'decimal', 'enum', 'typing'}
        parent = {'contracts', 'economic_contracts', 'research_contracts', 'research_journal',
                  'strategy_v34.contracts', 'strategy_v34.signals', 'strategy_catalog.contracts',
                  'strategy_catalog.research_link', 'strategy_catalog.service'}
        local = {'contracts', 'accounting', 'reader', 'simulation'}
        forbidden = {'eval', 'exec', 'compile', '__import__', 'open'}
        mutators = {'register', 'reconcile', 'diagnose', 'propose', 'receive', 'admit', 'start',
                    'record_reply', 'begin_postflight', 'finish', 'fail', 'recover', 'execute', 'connect'}
        # Simulation.execute is the bounded in-memory fold, not an SQL/OS call.
        for path in root.rglob('*.py'):
            tree = ast.parse(path.read_text(encoding='utf-8'))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    self.assertTrue(all(alias.name in standard for alias in node.names), path.name)
                if isinstance(node, ast.ImportFrom):
                    self.assertIn(node.level, (0, 1, 2), path.name)
                    allowed = standard if node.level == 0 else local if node.level == 1 else parent
                    self.assertIn(node.module, allowed, path.name)
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    self.assertNotIn(node.func.id, forbidden, path.name)
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    if node.func.attr == 'execute' and path.name == 'engine.py':
                        continue
                    self.assertNotIn(node.func.attr, mutators, path.name)
            self.assertFalse(any(isinstance(n, (ast.With, ast.Try)) for n in tree.body), path.name)
