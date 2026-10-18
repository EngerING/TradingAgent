"""End-to-end simulated research, including replays and boundary failures."""
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
import tempfile
import unittest
from unittest.mock import patch

from test_core_v3_research_contracts import AT, budget, request
from test_core_v3_economic_contracts import sealed
from trading_agent.core_v3.contracts import ContractError, Money, canonical_bytes
from trading_agent.core_v3.economic_contracts import Direction, EconomicStatus
from trading_agent.core_v3.research_contracts import ResearchInputs, ResearchState
from trading_agent.core_v3.research_designer import OfflineInputSource, SimulatedDesigner
from trading_agent.core_v3.research_journal import ResearchJournal
from trading_agent.core_v3.research_runner import run


def changed(req, **fields):
    return replace(req, inputs=replace(req.inputs, context=replace(req.inputs.context, **fields)))


class ResearchRunnerTests(unittest.TestCase):
    def test_success_for_both_assets_and_directions_replays_without_a_second_call(self):
        original = SimulatedDesigner.propose
        for stock in (False, True):
            for direction in Direction:
                with self.subTest(stock=stock, direction=direction), tempfile.TemporaryDirectory() as root:
                    req = request(stock=stock, direction=direction)
                    with patch.object(SimulatedDesigner, 'propose', autospec=True, side_effect=original) as designer:
                        with ResearchJournal(root, budget()) as journal:
                            result = run(journal, req, SimulatedDesigner(), clock=lambda: AT)
                            self.assertEqual(ResearchState.CANDIDATE_RECORDED, result.state)
                            self.assertEqual(req.instrument, result.instrument)
                            self.assertEqual(EconomicStatus.FEASIBLE, result.postflight.status)
                            self.assertEqual('NO_TRADE', result.trading_decision)
                            self.assertEqual(1, result.charge.consumed_requests)
                        with ResearchJournal(root, budget()) as journal:
                            self.assertEqual(result, run(journal, req, SimulatedDesigner(), clock=lambda: AT))
                            self.assertEqual(1, designer.call_count)

    def test_all_nonfeasible_preflights_block_before_reservation_or_design(self):
        req = request()
        expensive = sealed(replace(req.inputs.context.costs, opening_minimum=Money(Decimal('100'), 'USD')))
        variants = [(changed(req, costs=expensive), EconomicStatus.INFEASIBLE),
                    (changed(req, costs=None), EconomicStatus.UNKNOWN),
                    (replace(req, inputs=replace(req.inputs, policy=replace(req.inputs.policy, max_evaluations=1))),
                     EconomicStatus.UNRESOLVED)]
        for variant, status in variants:
            with tempfile.TemporaryDirectory() as root, ResearchJournal(root, budget()) as journal:
                with patch.object(SimulatedDesigner, 'propose', side_effect=AssertionError('DESIGN_FORBIDDEN')):
                    result = run(journal, variant, SimulatedDesigner(), clock=lambda: AT)
                self.assertEqual(ResearchState.ECONOMIC_BLOCKED, result.state)
                self.assertEqual(status, result.preflight.status)
                self.assertEqual(0, journal.budget_status().reserved_requests)
                self.assertEqual(0, journal.budget_status().consumed_requests)

    def test_research_budget_requests_tokens_and_funds_are_enforced_separately(self):
        for plan in (budget(requests=0), budget(tokens=199), budget(funds='.009')):
            with tempfile.TemporaryDirectory() as root, ResearchJournal(root, plan) as journal:
                result = run(journal, request(), SimulatedDesigner(), clock=lambda: AT)
                self.assertEqual(ResearchState.BUDGET_BLOCKED, result.state)
                self.assertIsNone(result.receipt)

    def test_failed_designer_is_terminal_with_uncertain_reservation_and_sanitized_reason(self):
        with tempfile.TemporaryDirectory() as root, ResearchJournal(root, budget()) as journal:
            with patch.object(SimulatedDesigner, 'propose', side_effect=RuntimeError('PRIVATE-ERROR-CONTENT')):
                result = run(journal, request(), SimulatedDesigner(), clock=lambda: AT)
            self.assertEqual(ResearchState.FAILED, result.state)
            self.assertEqual('DESIGNER_FAILED', result.reason)
            self.assertEqual(1, result.charge.reserved_requests)
            self.assertNotIn('PRIVATE-ERROR-CONTENT', str(journal.history()))
            self.assertEqual(result, run(journal, request(), SimulatedDesigner(), clock=lambda: AT))

    def test_interruption_and_explicit_recovery_never_repeat_uncertain_design(self):
        with tempfile.TemporaryDirectory() as root:
            with ResearchJournal(root, budget()) as journal:
                with patch.object(SimulatedDesigner, 'propose', side_effect=KeyboardInterrupt):
                    with self.assertRaises(KeyboardInterrupt):
                        run(journal, request(), SimulatedDesigner(), clock=lambda: AT)
            with ResearchJournal(root, budget()) as journal:
                with patch.object(SimulatedDesigner, 'propose', side_effect=AssertionError('NO_RETRY')):
                    pending = run(journal, request(), SimulatedDesigner(), clock=lambda: AT)
                    self.assertEqual(ResearchState.DESIGNING, pending.state)
                    recovered = journal.recover(request().request_id, now=AT)
                    self.assertEqual(ResearchState.INTERRUPTED, recovered.state)
                    self.assertEqual(recovered, run(journal, request(), SimulatedDesigner(), clock=lambda: AT))

    def test_expiry_during_design_is_a_safe_terminal_postflight_rejection(self):
        times = iter([AT, AT, AT, AT + timedelta(seconds=31), AT + timedelta(seconds=31), AT + timedelta(seconds=31)])
        with tempfile.TemporaryDirectory() as root, ResearchJournal(root, budget()) as journal:
            result = run(journal, request(), SimulatedDesigner(), clock=lambda: next(times))
            self.assertEqual(ResearchState.FAILED, result.state)
            self.assertEqual('POSTFLIGHT_BLOCKED', result.reason)
            self.assertEqual(EconomicStatus.UNKNOWN, result.postflight.status)
            self.assertEqual(1, result.charge.consumed_requests)

    def test_identity_and_untrusted_designer_are_rejected_without_consumption(self):
        with tempfile.TemporaryDirectory() as root, ResearchJournal(root, budget()) as journal:
            req = request()
            forged = replace(req, instrument=replace(req.instrument, content_sha256='a' * 64))
            result = run(journal, forged, SimulatedDesigner(), clock=lambda: AT)
            self.assertEqual(ResearchState.VALIDATION_REJECTED, result.state)
            class Untrusted:
                def propose(self, req):
                    raise AssertionError('MUST_NOT_RUN')
            for designer in (Untrusted(), object()):
                with self.assertRaisesRegex(ContractError, 'OFFLINE_DESIGNER_REQUIRED'):
                    run(journal, request(name='new'), designer, clock=lambda: AT)
            self.assertEqual(0, journal.budget_status().consumed_requests)

    def test_changed_snapshot_capital_cost_margin_fx_and_policy_are_rechecked_after_design(self):
        req = request(stock=True, account_currency='USD')
        original = SimulatedDesigner.propose
        context = req.inputs.context
        variants = [replace(req.inputs, context=replace(context, market=sealed(replace(context.market, revision=2)))),
                    replace(req.inputs, context=replace(context, portfolio=sealed(replace(context.portfolio,
                        revision=2, allocation_available=Money(Decimal('90'), 'USD'))))),
                    replace(req.inputs, context=replace(context, costs=sealed(replace(context.costs,
                        financing_fixed=Money(Decimal('.1'), 'EUR'))))),
                    replace(req.inputs, context=replace(context, margin=sealed(replace(context.margin,
                        initial_fraction=Decimal('1.1'))))),
                    replace(req.inputs, context=replace(context, fx=sealed(replace(context.fx, rate=Decimal('1.3'))))),
                    replace(req.inputs, policy=replace(req.inputs.policy, revision=2))]
        for refreshed in variants:
            with tempfile.TemporaryDirectory() as root, ResearchJournal(root, budget()) as journal:
                source = OfflineInputSource(req.inputs)
                def propose(designer, design):
                    source.inputs = refreshed
                    return original(designer, design)
                with patch.object(SimulatedDesigner, 'propose', autospec=True, side_effect=propose):
                    result = run(journal, req, SimulatedDesigner(), clock=lambda: AT, source=source)
                self.assertEqual(ResearchState.FAILED, result.state)
                self.assertEqual('POSTFLIGHT_BLOCKED', result.reason)
                self.assertEqual(EconomicStatus.UNKNOWN, result.postflight.status)
                self.assertNotIn('CANDIDATE_RECORDED', [r['state'] for r in journal.history()])

    def test_output_mutations_code_duplicates_and_authority_never_register_a_candidate(self):
        from trading_agent.core_v3.contracts import Price, Quantity
        from trading_agent.core_v3.economics import preflight
        from trading_agent.core_v3.research_contracts import DesignRequest
        from trading_agent.core_v3.research_designer import proposal_for
        req = request()
        before = preflight(req.inputs.context, req.inputs.policy, now=AT)
        valid = proposal_for(DesignRequest(req, before))
        bad = [replace(valid, request_sha256='a' * 64).to_json(),
               replace(valid, instrument_sha256='a' * 64).to_json(),
               replace(valid, scenario=replace(valid.scenario, quantity=Quantity(Decimal('27'), 'EUR'))).to_json(),
               replace(valid, scenario=replace(valid.scenario, entry=Price(Decimal('1.11'), 'USD', 'EUR'))).to_json(),
               replace(valid, scenario=replace(valid.scenario, stop=Price(Decimal('1.08'), 'USD', 'EUR'))).to_json(),
               replace(valid, scenario=replace(valid.scenario, target=Price(Decimal('1.15'), 'USD', 'EUR'))).to_json(),
               '{"code":"__import__(something)"}', '{"x":1,"x":2}', 'PRIVATE-RAW-REPLY']
        reversed_direction = valid.to_dict()
        reversed_direction['scenario']['direction'] = 'SHORT'
        bad.append(canonical_bytes(reversed_direction).decode())
        for key in ('execution_authority', 'paper_execution_eligible', 'live_enabled'):
            data = valid.to_dict()
            data[key] = True
            bad.append(canonical_bytes(data).decode())
        for raw in bad:
            with self.subTest(raw=raw[:45]), tempfile.TemporaryDirectory() as root, ResearchJournal(root, budget()) as journal:
                result = run(journal, req, SimulatedDesigner(raw), clock=lambda: AT)
                self.assertEqual(ResearchState.FAILED, result.state)
                self.assertEqual('PROPOSAL_INVALID', result.reason)
                self.assertIsNone(result.receipt.proposal)
                self.assertNotIn('PRIVATE-RAW-REPLY', str(journal.history()))

    def test_postflight_persistence_failure_is_pending_and_explicit_finish_does_not_redesign(self):
        original = ResearchJournal.finish
        with tempfile.TemporaryDirectory() as root:
            with ResearchJournal(root, budget()) as journal:
                def failing_finish(store, name, *, now):
                    store.db.execute("CREATE TRIGGER fail_terminal BEFORE INSERT ON events WHEN NEW.state='CANDIDATE_RECORDED' BEGIN SELECT RAISE(ABORT,'INJECTED_FAILURE'); END")
                    return original(store, name, now=now)
                with patch.object(ResearchJournal, 'finish', autospec=True, side_effect=failing_finish):
                    with self.assertRaisesRegex(ContractError, 'RESEARCH_PERSISTENCE_FAILED'):
                        run(journal, request(), SimulatedDesigner(), clock=lambda: AT)
                self.assertEqual(ResearchState.POSTFLIGHT_PENDING, journal.read(request().request_id).state)
                journal.db.execute('DROP TRIGGER fail_terminal')
            with ResearchJournal(root, budget()) as journal:
                with patch.object(SimulatedDesigner, 'propose', side_effect=AssertionError('NO_REDESIGN')):
                    pending = run(journal, request(), SimulatedDesigner(), clock=lambda: AT)
                    self.assertEqual(ResearchState.POSTFLIGHT_PENDING, pending.state)
                    self.assertEqual(ResearchState.CANDIDATE_RECORDED, journal.finish(request().request_id, now=AT).state)
                    self.assertEqual(1, journal.budget_status().consumed_requests)

    def test_pre_reservation_persistence_failure_does_not_invoke_designer_or_spend(self):
        with tempfile.TemporaryDirectory() as root, ResearchJournal(root, budget()) as journal:
            with patch.object(ResearchJournal, 'admit', side_effect=ContractError('INJECTED_FAILURE')):
                with patch.object(SimulatedDesigner, 'propose', side_effect=AssertionError('NO_DESIGN')):
                    with self.assertRaises(ContractError):
                        run(journal, request(), SimulatedDesigner(), clock=lambda: AT)
            self.assertEqual(ResearchState.RECEIVED, journal.read(request().request_id).state)
            self.assertEqual(0, journal.budget_status().reserved_requests)

    def test_identical_research_is_reproducible_and_budget_namespaces_do_not_collide(self):
        results = []
        for plan in (budget(), budget(), replace(budget(), budget_id='other-budget')):
            with tempfile.TemporaryDirectory() as root, ResearchJournal(root, plan) as journal:
                result = run(journal, request(), SimulatedDesigner(), clock=lambda: AT)
                results.append((result.to_json(), result.operation_id, journal.history()))
        self.assertEqual(results[0], results[1])
        self.assertNotEqual(results[0][1], results[2][1])

    def test_financial_allocation_and_forged_evidence_never_expand_research_budget(self):
        from trading_agent.core_v3.contracts import SourceKind
        req = request()
        ctx = req.inputs.context
        limited = changed(req, portfolio=sealed(replace(ctx.portfolio, allocation_available=Money(Decimal('1'), 'USD'))))
        fake = changed(req, market=replace(ctx.market, evidence=replace(ctx.market.evidence, content_sha256='f' * 64)))
        real_label = changed(req, market=replace(ctx.market, evidence=replace(ctx.market.evidence,
                            source_kind=SourceKind.AUTHENTIC_CAPTURE)))
        for variant in (limited, fake, real_label):
            with tempfile.TemporaryDirectory() as root, ResearchJournal(root, budget()) as journal:
                result = run(journal, variant, SimulatedDesigner(), clock=lambda: AT)
                self.assertEqual(ResearchState.ECONOMIC_BLOCKED, result.state)
                self.assertEqual(0, journal.budget_status().consumed_requests)
                self.assertEqual(2, journal.budget_status().remaining_requests)

    def test_clock_expiry_before_invocation_stops_designer_and_releases_unused_reservation(self):
        times = iter([AT, AT, AT + timedelta(seconds=31)])
        with tempfile.TemporaryDirectory() as root, ResearchJournal(root, budget()) as journal:
            with patch.object(SimulatedDesigner, 'propose', side_effect=AssertionError('NO_DESIGN')):
                result = run(journal, request(), SimulatedDesigner(), clock=lambda: next(times))
            self.assertEqual(ResearchState.FAILED, result.state)
            self.assertEqual('PREDESIGN_EVIDENCE_BLOCKED', result.reason)
            self.assertEqual(0, result.charge.reserved_requests)

    def test_invalid_refresh_source_is_a_safe_failure_with_known_usage(self):
        req = request()
        source = OfflineInputSource(None)
        with tempfile.TemporaryDirectory() as root, ResearchJournal(root, budget()) as journal:
            result = run(journal, req, SimulatedDesigner(), clock=lambda: AT, source=source)
            self.assertEqual(ResearchState.FAILED, result.state)
            self.assertEqual('INPUT_REFRESH_FAILED', result.reason)
            self.assertEqual(1, result.charge.consumed_requests)
