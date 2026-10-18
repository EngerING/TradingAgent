"""Durable research binding and catalog integration."""
from dataclasses import replace
from datetime import timedelta
import tempfile
import unittest
from unittest.mock import patch

from test_core_v35_contracts import AT, budget, command, request
from trading_agent.core_v3.contracts import ContractError
from trading_agent.core_v3.research_journal import ResearchJournal
from trading_agent.core_v3.research_runner import run
from trading_agent.core_v3.research_designer import SimulatedDesigner
from trading_agent.core_v3.strategy_catalog.research_link import capture, verify, check_binding, SourcePending
from trading_agent.core_v3.strategy_catalog.contracts import Action, State
from trading_agent.core_v3.strategy_v34.contracts import Operand, Indicator, Rule, Timeframe
from trading_agent.core_v3.economic_contracts import Direction
from trading_agent.core_v3.research_contracts import DesignRequest
from test_core_v3_economic_contracts import sealed


def complete(journal, req=None):
    req = request() if req is None else req
    run(journal, req, SimulatedDesigner(), clock=lambda: AT)
    return req


class ResearchLinkTests(unittest.TestCase):
    def test_terminal_evidence_is_read_only_roundtrips_and_accepts_future_appends(self):
        with tempfile.TemporaryDirectory() as root, ResearchJournal(root, budget()) as journal:
            req = complete(journal)
            cmd = command(req=req)
            original = journal.history()
            proof = capture(journal, cmd)
            self.assertEqual(proof, type(proof).from_json(proof.to_json()))
            self.assertTrue(check_binding(cmd, proof, req.inputs, now=AT).valid)
            self.assertFalse(check_binding(cmd, proof, req.inputs, now=AT + timedelta(seconds=31)).valid)
            self.assertEqual(original, journal.history())
            complete(journal, request(name='other'))
            verify(journal, proof)

    def test_pending_or_forged_source_is_never_an_approval(self):
        with tempfile.TemporaryDirectory() as root, ResearchJournal(root, budget()) as journal:
            req = request()
            journal.receive(req, now=AT)
            journal.admit(req.request_id, now=AT)
            with self.assertRaises(SourcePending):
                capture(journal, command(req=req))
            with self.assertRaises(ContractError):
                capture({'state': 'CANDIDATE_RECORDED'}, command(req=req))


class CatalogIntegrationTests(unittest.TestCase):
    def test_registration_restart_and_replay_preserve_research_and_budget(self):
        from trading_agent.core_v3.strategy_catalog.service import Catalog
        with tempfile.TemporaryDirectory() as root:
            with ResearchJournal(root, budget()) as journal:
                req = complete(journal)
                cmd = command(req=req)
                original = journal.history()
                balance = journal.budget_status()
                with Catalog(root) as catalog:
                    result = catalog.register(cmd, journal, req.inputs, now=AT)
                    self.assertEqual(State.VALIDATED, result.state)
                    value = catalog.version(cmd.catalog_id, 1)
                    self.assertEqual(cmd.strategy, value.registration.strategy)
                    self.assertEqual(value.record_sha256, result.target.record_sha256)
                    self.assertEqual('NO_TRADE', result.trading_decision)
                with Catalog(root) as catalog:
                    self.assertEqual(result, catalog.register(cmd, journal, req.inputs, now=AT))
                    self.assertEqual(1, len(catalog.versions()))
                self.assertEqual(original, journal.history())
                self.assertEqual(balance, journal.budget_status())

    def test_both_assets_directions_and_h1_are_bound_to_completed_research(self):
        from trading_agent.core_v3.strategy_catalog.service import Catalog
        from trading_agent.core_v3.strategy_v34.designer import design, SimulatedStrategyDesigner
        for stock in (False, True):
            for direction in Direction:
                with self.subTest(stock=stock, direction=direction), tempfile.TemporaryDirectory() as root:
                    with ResearchJournal(root, budget()) as journal, Catalog(root) as catalog:
                        req = complete(journal, request(stock=stock, direction=direction))
                        strategy = design(req, Timeframe.H1, SimulatedStrategyDesigner(), now=AT)
                        cmd = replace(command(req=req, strategy=strategy), timeframe=Timeframe.H1)
                        outcome = catalog.register(cmd, journal, req.inputs, now=AT)
                        self.assertEqual(State.VALIDATED, outcome.state)
                        self.assertEqual(1, journal.budget_status().consumed_requests)

    def test_renamed_semantic_duplicate_does_not_create_a_version(self):
        from trading_agent.core_v3.strategy_catalog.service import Catalog
        with tempfile.TemporaryDirectory() as root, ResearchJournal(root, budget()) as journal, Catalog(root) as catalog:
            req = complete(journal)
            first = command(req=req)
            original = catalog.register(first, journal, req.inputs, now=AT)
            clone = command(name='clone', catalog_id='clone-id', req=req,
                            strategy=replace(first.strategy, strategy_id='renamed'))
            duplicate = catalog.register(clone, journal, req.inputs, now=AT)
            self.assertEqual(State.DUPLICATE, duplicate.state)
            self.assertEqual(original.target, duplicate.target)
            self.assertEqual(1, len(catalog.versions()))
            self.assertEqual(1, journal.budget_status().consumed_requests)

    def test_revisions_are_immutable_and_identity_reuse_conflicts_are_durable(self):
        from trading_agent.core_v3.strategy_catalog.service import Catalog
        with tempfile.TemporaryDirectory() as root, ResearchJournal(root, budget()) as journal, Catalog(root) as catalog:
            req = complete(journal)
            first = command(req=req)
            initial = catalog.register(first, journal, req.inputs, now=AT)
            rule = first.strategy.entry_rules[0]
            updated = replace(first.strategy, entry_rules=(Rule(rule.left, rule.operator, Operand(Indicator.SMA, 4, 0)),))
            revision = command(name='revision', version=2, parent=initial.target.record_sha256, req=req, strategy=updated)
            self.assertEqual(State.VALIDATED, catalog.register(revision, journal, req.inputs, now=AT).state)
            self.assertEqual(first.strategy, catalog.version(first.catalog_id, 1).registration.strategy)
            conflict = command(name='conflict', req=req, strategy=updated)
            self.assertEqual(State.REJECTED, catalog.register(conflict, journal, req.inputs, now=AT).state)
            with self.assertRaisesRegex(ContractError, 'CATALOG_IDEMPOTENCY_CONFLICT'):
                catalog.register(replace(first, strategy=updated), journal, req.inputs, now=AT)
            self.assertEqual(2, len(catalog.versions()))

    def test_new_research_can_explicitly_revise_same_behavior_without_losing_prior_bindings(self):
        from trading_agent.core_v3.strategy_catalog.service import Catalog
        with tempfile.TemporaryDirectory() as root, ResearchJournal(root, budget()) as journal, Catalog(root) as catalog:
            req = complete(journal)
            first = catalog.register(command(req=req), journal, req.inputs, now=AT)
            other = complete(journal, request(name='new-research'))
            revision = command(name='revision', version=2, parent=first.target.record_sha256, req=other)
            self.assertEqual(State.VALIDATED, catalog.register(revision, journal, other.inputs, now=AT).state)
            self.assertEqual(catalog.version('catalog-1', 1).semantic_sha256, catalog.version('catalog-1', 2).semantic_sha256)
            self.assertNotEqual(catalog.version('catalog-1', 1).source.request, catalog.version('catalog-1', 2).source.request)
            self.assertEqual(2, journal.budget_status().consumed_requests)

    def test_changed_evidence_invalidates_new_context_without_erasing_history(self):
        from trading_agent.core_v3.strategy_catalog.service import Catalog
        from decimal import Decimal
        from trading_agent.core_v3.contracts import Money
        with tempfile.TemporaryDirectory() as root, ResearchJournal(root, budget()) as journal, Catalog(root) as catalog:
            req = complete(journal, request(stock=True, account_currency='USD'))
            cmd = command(req=req)
            initial = catalog.register(cmd, journal, req.inputs, now=AT)
            ctx = req.inputs.context
            variants = [replace(req.inputs, context=replace(ctx, market=sealed(replace(ctx.market, revision=2)))),
                        replace(req.inputs, context=replace(ctx, portfolio=sealed(replace(ctx.portfolio, revision=2,
                            allocation_available=Money(Decimal('90'), 'USD'))))),
                        replace(req.inputs, context=replace(ctx, costs=sealed(replace(ctx.costs, financing_fixed=Money(Decimal('.1'), 'EUR'))))),
                        replace(req.inputs, context=replace(ctx, margin=sealed(replace(ctx.margin, initial_fraction=Decimal('1.1'))))),
                        replace(req.inputs, context=replace(ctx, fx=sealed(replace(ctx.fx, rate=Decimal('1.3'))))),
                        replace(req.inputs, policy=replace(req.inputs.policy, revision=2))]
            for index, current in enumerate(variants):
                validation = replace(cmd, operation_id='validation-' + str(index), idempotency_key='validation-key-' + str(index), action=Action.REVALIDATE)
                result = catalog.register(validation, journal, current, now=AT)
                self.assertEqual(State.INVALIDATED, result.state)
                self.assertEqual(initial.target, result.target)
            expired = replace(cmd, operation_id='expired', idempotency_key='expired-key', action=Action.REVALIDATE)
            self.assertEqual(State.INVALIDATED, catalog.register(expired, journal, req.inputs, now=AT + timedelta(seconds=31)).state)
            self.assertEqual(initial, catalog.outcome(cmd.operation_id))
            self.assertEqual(1, len(catalog.versions()))

    def test_pending_research_waits_for_explicit_host_completion_without_reserving_again(self):
        from trading_agent.core_v3.strategy_catalog.service import Catalog
        with tempfile.TemporaryDirectory() as root, ResearchJournal(root, budget()) as journal, Catalog(root) as catalog:
            req = request()
            journal.receive(req, now=AT)
            admitted = journal.admit(req.request_id, now=AT)
            cmd = command(req=req)
            result = catalog.register(cmd, journal, req.inputs, now=AT)
            self.assertEqual(State.RECOVERY_REQUIRED, result.state)
            self.assertEqual(1, journal.budget_status().reserved_requests)
            self.assertEqual(0, len(catalog.versions()))
            journal.start(req.request_id, now=AT)
            raw = SimulatedDesigner().propose(DesignRequest(req, admitted.preflight))
            journal.record_reply(req.request_id, raw, now=AT)
            journal.begin_postflight(req.request_id, req.inputs, now=AT)
            journal.finish(req.request_id, now=AT)
            with patch.object(SimulatedDesigner, 'propose', side_effect=AssertionError('NO_PROVIDER')):
                self.assertEqual(State.VALIDATED, catalog.reconcile(cmd.operation_id, journal, req.inputs, now=AT).state)
            self.assertEqual(1, journal.budget_status().consumed_requests)

    def test_causal_signal_diagnosis_uses_a_new_validated_catalog_operation(self):
        from trading_agent.core_v3.strategy_catalog.service import Catalog
        from test_core_v34_signals import case
        req, strategy, series = case()
        with tempfile.TemporaryDirectory() as root, ResearchJournal(root, budget()) as journal, Catalog(root) as catalog:
            complete(journal, req)
            cmd = command(req=req, strategy=strategy)
            catalog.register(cmd, journal, req.inputs, now=AT)
            validation = replace(cmd, operation_id='diagnosis', idempotency_key='diagnosis-key', action=Action.REVALIDATE)
            result = catalog.diagnose(validation, journal, req.inputs, series, now=AT)
            self.assertTrue(result.entry_rules_met)
            self.assertEqual('NO_TRADE', result.trading_decision)

    def test_validation_and_revision_cannot_predate_the_version_they_reference(self):
        from trading_agent.core_v3.strategy_catalog.service import Catalog
        with tempfile.TemporaryDirectory() as root, ResearchJournal(root, budget()) as journal, Catalog(root) as catalog:
            req = complete(journal)
            cmd = command(req=req)
            first = catalog.register(cmd, journal, req.inputs, now=AT + timedelta(seconds=1))
            retrospective = replace(cmd, operation_id='past-check', idempotency_key='past-check-key', action=Action.REVALIDATE)
            self.assertEqual(State.INVALIDATED, catalog.register(retrospective, journal, req.inputs, now=AT).state)
            rule = cmd.strategy.entry_rules[0]
            changed = replace(cmd.strategy, entry_rules=(Rule(rule.left, rule.operator, Operand(Indicator.SMA, 4, 0)),))
            revision = command(name='past-revision', version=2, parent=first.target.record_sha256, req=req, strategy=changed)
            self.assertEqual(State.REJECTED, catalog.register(revision, journal, req.inputs, now=AT).state)
