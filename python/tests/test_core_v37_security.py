"""Validation has no provider, mutation, transport or authority route."""
import ast
from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_core_v35_contracts import budget
from test_core_v36_binding import registered
from test_core_v37_planning import example
from trading_agent.core_v3.contracts import ContractError
from trading_agent.core_v3.research_journal import ResearchJournal
from trading_agent.core_v3.research_designer import SimulatedDesigner
from trading_agent.core_v3.strategy_catalog.service import Catalog
from trading_agent.core_v3.strategy_v34.designer import SimulatedStrategyDesigner
from trading_agent.core_v3.strategy_v34.contracts import Timeframe
from trading_agent.core_v3.statistical_validation.contracts import Status
from trading_agent.core_v3.statistical_validation.coordinator import Coordinator


class StatisticalSecurityTests(unittest.TestCase):
    def test_no_provider_budget_catalog_or_python_file_open_during_validation(self):
        with registered(timeframe=Timeframe.H1) as (_, cmd, catalog, journal):
            plan, rules, chunks = example(cmd, catalog)
            host = Coordinator()
            req = host.prepare('protected', plan, rules, chunks, catalog, journal)
            before = catalog.history(), journal.history(), journal.budget_status()
            with ExitStack() as guards:
                for cls, methods in ((Catalog, ('register', 'reconcile', 'diagnose')),
                    (ResearchJournal, ('receive', 'admit', 'start', 'record_reply', 'begin_postflight', 'finish', 'fail', 'recover')),
                    (SimulatedDesigner, ('propose',)), (SimulatedStrategyDesigner, ('propose',))):
                    for method in methods:
                        guards.enter_context(patch.object(cls, method, side_effect=AssertionError('MUTATION_FORBIDDEN')))
                guards.enter_context(patch('builtins.open', side_effect=AssertionError('FILE_OPEN_FORBIDDEN')))
                result = host.run(req, plan, rules, chunks, catalog, journal).result
            self.assertEqual(Status.COMPLETE, result.status)
            self.assertEqual(before, (catalog.history(), journal.history(), journal.budget_status()))

    def test_real_fixture_corruption_and_substitution_are_rejected(self):
        with registered(timeframe=Timeframe.H1) as (_, cmd, catalog, journal), tempfile.TemporaryDirectory() as other:
            plan, rules, chunks = example(cmd, catalog)
            host = Coordinator()
            req = host.prepare('integrity', plan, rules, chunks, catalog, journal)
            with ResearchJournal(other, budget()) as replacement:
                self.assertEqual(Status.REJECTED, host.run(req, plan, rules, chunks, catalog, replacement).result.status)
            journal.db.execute('DROP TRIGGER immutable_events_update')
            journal.db.execute("UPDATE events SET payload='{}' WHERE sequence=(SELECT MAX(sequence) FROM events)")
            result = host.run(req, plan, rules, chunks, catalog, journal).result
            self.assertEqual(Status.REJECTED, result.status)
            self.assertEqual((), result.groups)

    def test_fake_source_and_incompatible_instrument_are_rejected(self):
        with registered(timeframe=Timeframe.H1) as (_, cmd, catalog, journal):
            plan, rules, chunks = example(cmd, catalog)
            host = Coordinator()
            req = host.prepare('source', plan, rules, chunks, catalog, journal)
            self.assertEqual(Status.REJECTED, host.run(req, plan, rules, chunks, object(), journal).result.status)
            from test_core_v36_contracts import dataset
            from trading_agent.core_v3.statistical_validation.planning import manifest
            foreign = (dataset(stock=True, timeframe=Timeframe.H1),)
            changed = replace(plan, manifest=manifest('other', foreign))
            with self.assertRaises(ContractError):
                host.prepare('incompatible', changed, rules, foreign, catalog, journal)

    def test_static_dependencies_have_no_effectful_entrypoint_or_dynamic_code(self):
        root = Path(__file__).resolve().parents[1] / 'trading_agent/core_v3/statistical_validation'
        standard = {'dataclasses', 'datetime', 'decimal', 'enum', 're', 'hashlib', 'sqlite3', 'threading'}
        parent = {'contracts', 'economic_contracts', 'research_contracts', 'research_journal',
                  'event_backtest', 'event_backtest.contracts', 'event_backtest.reader',
                  'event_backtest.accounting', 'event_backtest.simulation',
                  'strategy_catalog.contracts', 'strategy_catalog.service', 'strategy_v34.contracts'}
        local = {'contracts', 'planning', 'evidence', 'statistics', 'aggregation', 'robustness'}
        forbidden = {'eval', 'exec', 'compile', '__import__', 'open'}
        mutators = {'connect', 'register', 'reconcile', 'diagnose', 'propose', 'receive', 'admit',
                    'start', 'record_reply', 'begin_postflight', 'finish', 'fail', 'recover', 'execute'}
        for path in root.glob('*.py'):
            tree = ast.parse(path.read_text(encoding='utf-8'))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    self.assertTrue(all(alias.name in standard for alias in node.names), path.name)
                if isinstance(node, ast.ImportFrom):
                    allowed = standard if node.level == 0 else local if node.level == 1 else parent
                    self.assertIn(node.module, allowed, path.name)
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    self.assertNotIn(node.func.id, forbidden, path.name)
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    self.assertNotIn(node.func.attr, mutators, path.name)
            self.assertFalse(any(isinstance(n, (ast.With, ast.Try)) for n in tree.body), path.name)
