"""Binding, provenance and bounded-search regressions for V3.2."""
from dataclasses import replace
from datetime import timedelta
from decimal import getcontext, localcontext
import ast
from pathlib import Path
import sys
import unittest

from test_core_v3_economic_contracts import AT, D, fixture, sealed
from trading_agent.core_v3.contracts import (
    ContractError, Environment, Money, Price, Quantity, SourceKind,
)
from trading_agent.core_v3.economic_contracts import EconomicContext, EconomicResult, EconomicStatus
from trading_agent.core_v3.economics import postflight, preflight


class EvidenceTests(unittest.TestCase):
    def test_stale_future_unknown_time_and_oversized_validity_do_not_make_current_data(self):
        context, policy = fixture()
        original = context.market.evidence
        variants = [replace(original, observed_at=AT - timedelta(seconds=60), valid_until=AT + timedelta(days=1)),
                    replace(original, observed_at=AT + timedelta(microseconds=1)),
                    replace(original, observed_at=None, valid_until=None)]
        for ref in variants:
            result = preflight(replace(context, market=replace(context.market, evidence=ref)), policy, now=AT)
            self.assertEqual(EconomicStatus.UNKNOWN, result.status)
        self.assertEqual(EconomicStatus.UNKNOWN, preflight(context, policy, now=AT + timedelta(seconds=30)).status)

    def test_source_labels_hashes_and_paper_live_cannot_self_authenticate(self):
        context, policy = fixture()
        for changes in ({'source_kind': SourceKind.CALLER_UNVERIFIED},
                        {'source_kind': SourceKind.AUTHENTIC_CAPTURE}, {'content_sha256': None},
                        {'environment': Environment.PAPER}, {'environment': Environment.LIVE}):
            ref = replace(context.market.evidence, **changes)
            with self.subTest(changes=changes):
                self.assertEqual(EconomicStatus.UNKNOWN, preflight(
                    replace(context, market=replace(context.market, evidence=ref)), policy, now=AT).status)
        self.assertEqual(EconomicStatus.UNKNOWN, preflight(context, replace(policy, allow_synthetic=False), now=AT).status)

    def test_material_changes_require_matching_evidence_hashes(self):
        context, policy = fixture()
        portfolio = replace(context.portfolio, equity=Money(D('101'), 'USD'))
        result = preflight(replace(context, portfolio=portfolio), policy, now=AT)
        self.assertEqual(EconomicStatus.UNKNOWN, result.status)
        self.assertIn('EVIDENCE_HASH_MISMATCH', {r.reason for r in result.rejections})

    def test_cost_fx_margin_and_hypothesis_evidence_are_all_checked(self):
        context, policy = fixture(stock=True, account_currency='USD')
        for field in ('costs', 'margin', 'fx'):
            record = getattr(context, field)
            expired = replace(record, evidence=replace(record.evidence,
                              observed_at=AT - timedelta(minutes=1), valid_until=AT))
            self.assertEqual(EconomicStatus.UNKNOWN, preflight(replace(context, **{field: expired}), policy, now=AT).status)
        h = context.hypotheses[0]
        h = replace(h, evidence=replace(h.evidence, source_kind=SourceKind.HISTORICAL_VERIFIED))
        self.assertEqual(EconomicStatus.UNKNOWN, preflight(replace(context, hypotheses=(h,)), policy, now=AT).status)

    def test_wrong_units_and_currency_are_unknown_inputs_never_implicitly_converted(self):
        context, policy = fixture()
        h = sealed(replace(context.hypotheses[0], target_distance=Price(D('.04'), 'EUR', 'EUR')))
        self.assertEqual(EconomicStatus.UNKNOWN, preflight(replace(context, hypotheses=(h,)), policy, now=AT).status)
        costs = sealed(replace(context.costs, closing_minimum=Money(D('0.50'), 'EUR')))
        self.assertEqual(EconomicStatus.UNKNOWN, preflight(replace(context, costs=costs), policy, now=AT).status)
        self.assertEqual(EconomicStatus.UNKNOWN, preflight(context,
            replace(policy, max_quantity=Quantity(D('10'), 'SHARE')), now=AT).status)


class PostflightTests(unittest.TestCase):
    def test_same_witness_is_recomputed_and_roundtrips_without_authority(self):
        context, policy = fixture()
        previous = preflight(context, policy, now=AT)
        result = postflight(context, policy, previous.witness, previous, now=AT + timedelta(seconds=1))
        self.assertEqual(EconomicStatus.FEASIBLE, result.status)
        self.assertEqual('POSTFLIGHT', result.stage)
        self.assertEqual(previous.evaluation, result.evaluation)
        self.assertEqual(result, EconomicResult.from_json(result.to_json()))
        for key in ('execution_authority', 'paper_execution_eligible', 'live_enabled', 'statistically_validated'):
            data = result.to_dict()
            data[key] = True
            with self.subTest(key=key), self.assertRaises(ContractError):
                EconomicResult.from_dict(data)

    def test_snapshot_portfolio_cost_fx_and_policy_changes_invalidate_preflight(self):
        context, policy = fixture(stock=True, account_currency='USD')
        previous = preflight(context, policy, now=AT)
        variants = [replace(context, market=sealed(replace(context.market, revision=2))),
                    replace(context, portfolio=sealed(replace(context.portfolio, revision=2,
                                        allocation_available=Money(D('90'), 'USD')))),
                    replace(context, costs=sealed(replace(context.costs, financing_fixed=Money(D('.10'), 'EUR')))),
                    replace(context, fx=sealed(replace(context.fx, rate=D('1.3'))))]
        for variant in variants:
            self.assertEqual(EconomicStatus.UNKNOWN,
                postflight(variant, policy, previous.witness, previous, now=AT).status)
        self.assertEqual(EconomicStatus.UNKNOWN, postflight(context, replace(policy, revision=2),
            previous.witness, previous, now=AT).status)

    def test_changed_direction_quantity_stop_target_and_horizon_are_rejected(self):
        context, policy = fixture()
        previous = preflight(context, policy, now=AT)
        for changes in ({'quantity': Quantity(previous.witness.quantity.amount + 1, 'EUR')},
                        {'stop': Price(D('1.08'), 'USD', 'EUR')},
                        {'target': Price(D('1.15'), 'USD', 'EUR')}, {'horizon_hours': 2}):
            candidate = replace(previous.witness, **changes)
            result = postflight(context, policy, candidate, previous, now=AT)
            self.assertEqual(EconomicStatus.UNKNOWN, result.status)
        short_context, _ = fixture(direction=type(previous.witness.direction).SHORT)
        short = preflight(short_context, policy, now=AT).witness
        self.assertEqual(EconomicStatus.UNKNOWN, postflight(context, policy, short, previous, now=AT).status)

    def test_forged_witness_and_history_never_bypass_geometry_or_calculation(self):
        context, policy = fixture()
        previous = preflight(context, policy, now=AT)
        changed = replace(previous.witness, quantity=Quantity(D('0.5'), 'EUR'))
        forged = replace(previous, witness=changed)
        result = postflight(context, policy, changed, forged, now=AT)
        self.assertEqual(EconomicStatus.INFEASIBLE, result.status)
        self.assertEqual(EconomicStatus.UNKNOWN, postflight(context, policy, previous.witness,
            {'schema': 'FOREX_ECONOMIC_ASSESSMENT_V1', 'admitted': True}, now=AT).status)

    def test_postflight_rejects_expired_inputs_and_a_preflight_from_the_future(self):
        context, policy = fixture()
        previous = preflight(context, policy, now=AT + timedelta(seconds=10))
        result = postflight(context, policy, previous.witness, previous, now=AT)
        self.assertEqual(EconomicStatus.UNKNOWN, result.status)
        self.assertEqual(EconomicStatus.UNKNOWN, postflight(context, policy, previous.witness,
            previous, now=AT + timedelta(seconds=31)).status)

    def test_forged_feasible_result_cannot_skip_spread_or_actual_costs(self):
        from trading_agent.core_v3.contracts import content_hash
        from trading_agent.core_v3.economic_contracts import UnitAmount
        context, policy = fixture()
        previous = preflight(context, policy, now=AT)
        tighter = replace(policy, maximum_spread=UnitAmount(Money(D('.0001'), 'USD'), 'EUR'))
        candidate = replace(previous.witness, policy_sha256=content_hash(tighter))
        forged = replace(previous, policy_sha256=content_hash(tighter), witness=candidate)
        result = postflight(context, tighter, candidate, forged, now=AT)
        self.assertEqual(EconomicStatus.INFEASIBLE, result.status)
        self.assertIn('SPREAD_POLICY_EXCEEDED', {r.reason for r in result.rejections})
        costs = sealed(replace(context.costs, opening_minimum=Money(D('100'), 'USD')))
        expensive = replace(context, costs=costs)
        candidate = replace(previous.witness, context_sha256=content_hash(expensive))
        forged = replace(previous, context_sha256=content_hash(expensive), witness=candidate)
        result = postflight(expensive, policy, candidate, forged, now=AT)
        self.assertEqual(EconomicStatus.INFEASIBLE, result.status)
        self.assertIn('NONPOSITIVE_NET_TARGET', {r.reason for r in result.rejections})

    def test_postflight_does_not_claim_infeasibility_for_an_unreached_valid_quantity(self):
        from trading_agent.core_v3.contracts import content_hash
        context, policy = fixture()
        previous = preflight(context, policy, now=AT)
        limited = replace(policy, max_evaluations=1)
        candidate = replace(previous.witness, policy_sha256=content_hash(limited))
        forged = replace(previous, policy_sha256=content_hash(limited), witness=candidate)
        result = postflight(context, limited, candidate, forged, now=AT)
        self.assertEqual(EconomicStatus.UNRESOLVED, result.status)


class DomainAndIsolationTests(unittest.TestCase):
    def test_lazy_generator_does_not_leak_its_decimal_context_to_the_caller(self):
        from trading_agent.core_v3.contracts import content_hash
        from trading_agent.core_v3.economic_scenarios import prepare_domain, scenarios
        context, policy = fixture()
        domain = prepare_domain(context, policy)
        with localcontext() as arithmetic:
            arithmetic.prec = 2
            trials = scenarios(domain, context, policy, content_hash(context), content_hash(policy))
            next(trials)
            self.assertEqual(2, getcontext().prec)
            trials.close()

    def test_long_and_short_share_bounded_domain_and_never_claim_exhaustion_after_witness(self):
        from trading_agent.core_v3.economic_contracts import Direction
        context, policy = fixture()
        short, _ = fixture(direction=Direction.SHORT)
        h = sealed(replace(short.hypotheses[0], hypothesis_id='idea-short'))
        context = replace(context, hypotheses=(context.hypotheses[0], h),
                          costs=sealed(replace(context.costs, directions=(Direction.LONG, Direction.SHORT))))
        result = preflight(context, policy, now=AT)
        self.assertEqual(100, result.domain_size)
        self.assertFalse(result.search_complete)
        self.assertEqual(EconomicStatus.FEASIBLE, result.status)

    def test_off_tick_geometry_horizon_and_empty_grid_are_proven_domain_rejections(self):
        context, policy = fixture()
        for h in (sealed(replace(context.hypotheses[0], horizon_hours=5)),
                  sealed(replace(context.hypotheses[0], stop_distance=Price(D('.009999'), 'USD', 'EUR')))):
            result = preflight(replace(context, hypotheses=(h,)), policy, now=AT)
            self.assertEqual(EconomicStatus.INFEASIBLE, result.status)
        self.assertEqual(EconomicStatus.INFEASIBLE, preflight(context,
            replace(policy, max_quantity=Quantity(D('.5'), 'EUR')), now=AT).status)
        self.assertEqual(EconomicStatus.UNKNOWN, preflight(replace(context, hypotheses=()), policy, now=AT).status)

    def test_numeric_precision_failure_does_not_fabricate_infeasibility(self):
        context, policy = fixture(stock=True, account_currency='USD')
        fx = sealed(replace(context.fx, rate=D('1.123456789012')))
        result = preflight(replace(context, fx=fx), policy, now=AT)
        self.assertEqual(EconomicStatus.UNRESOLVED, result.status)
        self.assertFalse(result.search_complete)
        self.assertNotIn('SEARCH_LIMIT_REACHED', {r.reason for r in result.rejections})

    def test_unrepresentable_geometry_is_unresolved_not_off_tick_or_infeasible(self):
        context, policy = fixture()
        entry = Price(D('999999999999999999'), 'USD', 'EUR')
        market = sealed(replace(context.market, bid=entry, ask=entry))
        h = sealed(replace(context.hypotheses[0], entry=entry, target_distance=Price(D('1'), 'USD', 'EUR'),
                           plausible_move=Price(D('1'), 'USD', 'EUR')))
        result = preflight(replace(context, market=market, hypotheses=(h,)),
                           replace(policy, max_target_distance=Price(D('1'), 'USD', 'EUR')), now=AT)
        self.assertEqual(EconomicStatus.UNRESOLVED, result.status)
        self.assertEqual(50, result.domain_size)
        self.assertEqual(0, result.evaluated)
        self.assertFalse(result.search_complete)

    def test_huge_quantity_grid_stays_bounded_and_precision_failure_is_unresolved(self):
        context, policy = fixture()
        instrument = replace(context.market.instrument,
            minimum_quantity=Quantity(D('100000000000000000'), 'EUR'),
            quantity_step=Quantity(D('.000000000001'), 'EUR'))
        from trading_agent.core_v3.contracts import content_hash
        market = sealed(replace(context.market, instrument=instrument))
        h = sealed(replace(context.hypotheses[0], instrument_sha256=content_hash(instrument)))
        context = replace(context, market=market, hypotheses=(h,))
        policy = replace(policy, max_quantity=Quantity(D('100000000000000001'), 'EUR'), max_evaluations=3)
        result = preflight(context, policy, now=AT)
        self.assertEqual(EconomicStatus.UNRESOLVED, result.status)
        self.assertEqual(3, result.evaluated)
        self.assertGreater(result.domain_size, 10**12)

    def test_engine_calls_have_no_io_or_network_and_do_not_import_execution_modules(self):
        context, policy = fixture()
        enabled = [True]
        def guard(event, args):
            if enabled[0] and event in ('open', 'socket.connect', 'socket.bind', 'socket.getaddrinfo', 'subprocess.Popen'):
                raise AssertionError('ECONOMIC_ENGINE_IO_FORBIDDEN')
        sys.addaudithook(guard)
        try:
            result = preflight(context, policy, now=AT)
            self.assertEqual(EconomicStatus.FEASIBLE,
                             postflight(context, policy, result.witness, result, now=AT).status)
        finally:
            enabled[0] = False
        root = Path(__file__).resolve().parents[2] / 'python/trading_agent/core_v3'
        for name in ('economics.py', 'economic_contracts.py', 'economic_scenarios.py', 'economic_calculation.py'):
            tree = ast.parse((root / name).read_text(encoding='utf-8'))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    self.assertFalse(node.level > 1, name)
