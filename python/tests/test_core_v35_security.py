"""Offline boundaries, forged evidence and economic identity mutations."""
import ast
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_core_v35_contracts import AT, budget, command, request
from test_core_v35_catalog import complete
from trading_agent.core_v3.contracts import ContractError, Price
from trading_agent.core_v3.research_designer import SimulatedDesigner
from trading_agent.core_v3.research_journal import ResearchJournal
from trading_agent.core_v3.strategy_v34.designer import SimulatedStrategyDesigner
from trading_agent.core_v3.strategy_v34.contracts import Timeframe
from trading_agent.core_v3.economic_contracts import Direction
from trading_agent.core_v3.strategy_catalog.contracts import CatalogOutcome, CatalogRequest, SourceProof, State
from trading_agent.core_v3.strategy_catalog.service import Catalog


class CatalogSecurityTests(unittest.TestCase):
    def test_registration_uses_neither_designers_nor_budget_mutation_methods(self):
        from contextlib import ExitStack
        with tempfile.TemporaryDirectory() as root, ResearchJournal(root, budget()) as journal, Catalog(root) as catalog:
            req = complete(journal)
            cmd = command(req=req)
            before = journal.history()
            with ExitStack() as guards:
                for cls, method in [(SimulatedDesigner, 'propose'), (SimulatedStrategyDesigner, 'propose')]:
                    guards.enter_context(patch.object(cls, method, side_effect=AssertionError('NO_DESIGNER')))
                for method in ('receive', 'admit', 'start', 'record_reply', 'begin_postflight', 'finish', 'fail', 'recover'):
                    guards.enter_context(patch.object(ResearchJournal, method, side_effect=AssertionError('NO_BUDGET_MUTATION')))
                result = catalog.register(cmd, journal, req.inputs, now=AT)
                self.assertEqual(State.VALIDATED, result.state)
                self.assertEqual(result, CatalogOutcome.from_json(result.to_json()))
            self.assertEqual(before, journal.history())

    def test_catalog_outcomes_and_source_wire_cannot_inject_authority_or_code(self):
        with tempfile.TemporaryDirectory() as root, ResearchJournal(root, budget()) as journal, Catalog(root) as catalog:
            req = complete(journal)
            cmd = command(req=req)
            result = catalog.register(cmd, journal, req.inputs, now=AT)
            proof = catalog.version(cmd.catalog_id, 1).source
            for cls, value in ((CatalogOutcome, result), (SourceProof, proof), (CatalogRequest, cmd)):
                for key, data in [('execution_authority', True), ('paper_execution_eligible', True),
                                  ('live_enabled', True), ('statistically_validated', True),
                                  ('code', 'arbitrary'), ('schema_version', 2)]:
                    raw = value.to_dict()
                    raw[key] = data
                    with self.subTest(cls=cls, key=key), self.assertRaises(ContractError):
                        cls.from_dict(raw)
                with self.assertRaises(ContractError):
                    cls.from_json('{"schema":1,"schema":2}')

    def test_geometry_specification_timeframe_and_request_mutations_do_not_register(self):
        with tempfile.TemporaryDirectory() as root, ResearchJournal(root, budget()) as journal, Catalog(root) as catalog:
            req = complete(journal)
            cmd = command(req=req)
            strategy, scenario = cmd.strategy, cmd.strategy.scenario
            scenarios = [replace(scenario, quantity=replace(scenario.quantity, amount=scenario.quantity.amount + 1)),
                         replace(scenario, entry=Price(Decimal('1.11'), 'USD', 'EUR')),
                         replace(scenario, stop=Price(Decimal('1.08'), 'USD', 'EUR')),
                         replace(scenario, target=Price(Decimal('1.15'), 'USD', 'EUR')),
                         replace(scenario, direction=Direction.SHORT, stop=scenario.target, target=scenario.stop),
                         replace(scenario, context_sha256='a' * 64), replace(scenario, policy_sha256='b' * 64)]
            values = [replace(strategy, scenario=s) for s in scenarios]
            values.extend([replace(strategy, scenario=replace(scenario, horizon_hours=2), max_holding_bars=120),
                           replace(strategy, timeframe=Timeframe.M5, max_holding_bars=12),
                           replace(strategy, instrument=replace(strategy.instrument, specification_version=2)),
                           replace(strategy, request_sha256='c' * 64)])
            for index, value in enumerate(values):
                altered = command(name='mutation-' + str(index), req=req, strategy=value)
                self.assertEqual(State.INVALIDATED, catalog.register(altered, journal, req.inputs, now=AT).state)
            self.assertEqual(0, len(catalog.versions()))
            self.assertEqual(1, journal.budget_status().consumed_requests)

    def test_forged_journal_object_and_uncertain_terminal_cannot_supply_an_approval(self):
        class Fake:
            def history(self):
                raise AssertionError('MUST_NOT_READ')
        with tempfile.TemporaryDirectory() as root, ResearchJournal(root, budget()) as journal, Catalog(root) as catalog:
            req = request()
            cmd = command(req=req)
            with self.assertRaisesRegex(ContractError, 'VERIFIED_RESEARCH_JOURNAL_REQUIRED'):
                catalog.register(cmd, Fake(), req.inputs, now=AT)
            journal.receive(req, now=AT)
            journal.admit(req.request_id, now=AT)
            journal.start(req.request_id, now=AT)
            journal.recover(req.request_id, now=AT)
            result = catalog.register(cmd, journal, req.inputs, now=AT)
            self.assertEqual(State.REJECTED, result.state)
            self.assertEqual(0, len(catalog.versions()))
            self.assertEqual(1, journal.budget_status().reserved_requests)

    def test_private_roots_and_paths_in_identifiers_are_rejected_before_io(self):
        with self.assertRaisesRegex(ContractError, 'PRIVATE_ROOT_FORBIDDEN'):
            Catalog(Path.cwd() / '.local')
        cmd = command()
        for value in ('../escape', 'C:/private', '.local', ''):
            with self.assertRaises(ContractError):
                replace(cmd, catalog_id=value)

    def test_new_package_has_a_closed_static_dependency_surface(self):
        root = Path(__file__).resolve().parents[1] / 'trading_agent/core_v3/strategy_catalog'
        standard = {'dataclasses', 'datetime', 'enum', 're', 'contextlib', 'hashlib', 'pathlib', 'sqlite3'}
        parent = {'contracts', 'economic_contracts', 'research_contracts', 'research_journal',
                  'strategy_v34.contracts', 'strategy_v34.validation', 'strategy_v34.signals'}
        local = {'contracts', 'research_link', 'store'}
        forbidden = {'eval', 'exec', 'compile', '__import__', 'open', 'getattr', 'setattr'}
        mutators = {'propose', 'receive', 'admit', 'start', 'record_reply', 'begin_postflight', 'finish', 'fail', 'recover'}
        for path in root.rglob('*.py'):
            tree = ast.parse(path.read_text(encoding='utf-8'))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    self.assertTrue(all(alias.name in standard for alias in node.names), path.name)
                if isinstance(node, ast.ImportFrom):
                    self.assertIn(node.level, (0, 1, 2), path.name)
                    allowed = standard if node.level == 0 else local if node.level == 1 else parent
                    self.assertIn(node.module, allowed, path.name)
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name):
                        self.assertNotIn(node.func.id, forbidden, path.name)
                    if isinstance(node.func, ast.Attribute):
                        self.assertNotIn(node.func.attr, mutators, path.name)
            self.assertFalse(any(isinstance(n, (ast.With, ast.Try)) for n in tree.body), path.name)
