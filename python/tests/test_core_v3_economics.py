"""Bounded economic search on explicit synthetic assumptions."""
from dataclasses import replace
from decimal import Inexact, ROUND_UP, localcontext
import unittest

from test_core_v3_economic_contracts import AT, D, fixture, sealed
from trading_agent.core_v3.contracts import Money, Price, Quantity, content_hash
from trading_agent.core_v3.economic_contracts import Direction, EconomicStatus, UnitAmount
from trading_agent.core_v3.economics import preflight


class EconomicSearchTests(unittest.TestCase):
    def test_forex_and_eur_equity_long_short_have_conditional_witnesses(self):
        for stock in (False, True):
            for direction in Direction:
                with self.subTest(stock=stock, direction=direction):
                    context, policy = fixture(stock=stock, direction=direction)
                    result = preflight(context, policy, now=AT)
                    self.assertEqual(EconomicStatus.FEASIBLE, result.status, result.rejections)
                    self.assertEqual(direction, result.witness.direction)
                    self.assertGreater(result.evaluation.net_target.amount, 0)
                    self.assertEqual(context.portfolio.account_currency, result.evaluation.net_target.currency)
                    self.assertFalse(result.execution_authority)
                    self.assertFalse(result.paper_execution_eligible)
                    self.assertFalse(result.live_enabled)
                    self.assertFalse(result.statistically_validated)
                    self.assertEqual('NO_TRADE', result.trading_decision)

    def test_each_cost_charged_once_with_mid_geometry(self):
        context, policy = fixture()
        context = replace(context, costs=sealed(replace(context.costs,
            opening_per_unit=UnitAmount(Money(D('0.02'), 'USD'), 'EUR'),
            financing_fixed=Money(D('0.10'), 'USD'),
            financing_per_unit_per_hour=UnitAmount(Money(D('0.001'), 'USD'), 'EUR'))))
        result = preflight(context, policy, now=AT)
        self.assertEqual(EconomicStatus.FEASIBLE, result.status)
        q, e = result.witness.quantity.amount, result.evaluation
        self.assertEqual(max(D('.50'), q * D('.02')), e.opening_commission.amount)
        self.assertEqual(D('.50'), e.closing_commission.amount)
        self.assertEqual(q * D('.0002'), e.spread_cost.amount)
        self.assertEqual(q * D('.0001'), e.slippage_cost.amount)
        self.assertEqual(D('.10') + q * D('.001'), e.financing_cost.amount)
        self.assertEqual(q * D('.04') - e.round_trip_cost.amount, e.net_target.amount)

    def test_high_commissions_exhaust_domain_not_a_profitable_strategy(self):
        context, policy = fixture()
        context = replace(context, costs=sealed(replace(context.costs, opening_minimum=Money(D('100'), 'USD'))))
        result = preflight(context, policy, now=AT)
        self.assertEqual(EconomicStatus.INFEASIBLE, result.status)
        self.assertTrue(result.search_complete)
        self.assertIsNone(result.witness)
        self.assertIn('NONPOSITIVE_NET_TARGET', {r.reason for r in result.rejections})

    def test_unknown_information_never_becomes_zero(self):
        context, policy = fixture()
        variants = [replace(context, costs=None), replace(context, margin=None),
                    replace(context, costs=sealed(replace(context.costs, closing_minimum=None))),
                    replace(context, margin=sealed(replace(context.margin, initial_fraction=None))),
                    replace(context, portfolio=sealed(replace(context.portfolio, free_margin=None)))]
        for variant in variants:
            with self.subTest(variant=variant):
                result = preflight(variant, policy, now=AT)
                self.assertEqual(EconomicStatus.UNKNOWN, result.status)
                self.assertEqual(0, result.evaluated)

    def test_account_currency_requires_correct_documented_fx(self):
        context, policy = fixture(stock=True, account_currency='USD')
        valid = preflight(context, policy, now=AT)
        self.assertEqual(EconomicStatus.FEASIBLE, valid.status)
        self.assertEqual('USD', valid.evaluation.round_trip_cost.currency)
        self.assertEqual(EconomicStatus.UNKNOWN, preflight(replace(context, fx=None), policy, now=AT).status)
        wrong = sealed(replace(context.fx, from_currency='USD', to_currency='EUR'))
        self.assertEqual(EconomicStatus.UNKNOWN, preflight(replace(context, fx=wrong), policy, now=AT).status)

    def test_instrument_multiplier_and_account_fx_are_explicit_in_the_breakdown(self):
        context, policy = fixture(stock=True, account_currency='USD')
        instrument = replace(context.market.instrument, multiplier=D('10'))
        context = replace(context, market=sealed(replace(context.market, instrument=instrument)),
            hypotheses=(sealed(replace(context.hypotheses[0], instrument_sha256=content_hash(instrument))),),
            portfolio=sealed(replace(context.portfolio, remaining_exposure=Money(D('1000'), 'USD'))),
            margin=sealed(replace(context.margin, initial_fraction=D('.01'), maintenance_fraction=D('.005'))))
        result = preflight(context, policy, now=AT)
        self.assertEqual(EconomicStatus.FEASIBLE, result.status)
        self.assertEqual(D('2'), result.witness.quantity.amount)
        self.assertEqual(D('240'), result.evaluation.notional.amount)
        self.assertEqual(D('2.16'), result.evaluation.round_trip_cost.amount)
        self.assertEqual(D('7.44'), result.evaluation.net_target.amount)

    def test_reduced_assignment_margin_exposure_and_risk_reject(self):
        context, policy = fixture()
        for name, amount in [('equity', '0'), ('allocation_available', '1'), ('free_margin', '1'),
                             ('remaining_exposure', '1'), ('remaining_risk', '0.10')]:
            portfolio = sealed(replace(context.portfolio, **{name: Money(D(amount), 'USD')}))
            if name == 'equity':
                portfolio = sealed(replace(portfolio, allocation_available=Money(D('0'), 'USD')))
            with self.subTest(name=name):
                result = preflight(replace(context, portfolio=portfolio), policy, now=AT)
                self.assertEqual(EconomicStatus.INFEASIBLE, result.status)

    def test_spread_and_stress_cannot_be_ignored(self):
        context, policy = fixture()
        spread_limit = replace(policy, maximum_spread=UnitAmount(Money(D('.0001'), 'USD'), 'EUR'))
        self.assertEqual(EconomicStatus.INFEASIBLE, preflight(context, spread_limit, now=AT).status)
        stress = replace(policy.stresses[0], adverse_gap=UnitAmount(Money(D('1'), 'USD'), 'EUR'))
        self.assertEqual(EconomicStatus.INFEASIBLE, preflight(context, replace(policy, stresses=(stress,)), now=AT).status)

    def test_technical_target_bound_is_not_increased_to_pay_fees(self):
        context, policy = fixture()
        hypothesis = sealed(replace(context.hypotheses[0], target_distance=Price(D('.05'), 'USD', 'EUR')))
        result = preflight(replace(context, hypotheses=(hypothesis,)), policy, now=AT)
        self.assertEqual(EconomicStatus.INFEASIBLE, result.status)
        self.assertIn('TARGET_OUTSIDE_TECHNICAL_DOMAIN', {r.reason for r in result.rejections})

    def test_incomplete_search_is_unresolved_complete_search_is_infeasible(self):
        context, policy = fixture()
        limited = preflight(context, replace(policy, max_evaluations=1), now=AT)
        self.assertEqual(EconomicStatus.UNRESOLVED, limited.status)
        self.assertEqual(1, limited.evaluated)
        self.assertFalse(limited.search_complete)
        self.assertGreater(limited.domain_size, limited.evaluated)

    def test_reproducible_hashes_and_arithmetic_ignore_ambient_precision(self):
        context, policy = fixture()
        result = preflight(context, policy, now=AT)
        with localcontext() as arithmetic:
            arithmetic.prec = 2
            again = preflight(context, policy, now=AT)
        self.assertEqual(result.to_json(), again.to_json())
        self.assertEqual(content_hash(result), content_hash(again))

    def test_ambient_rounding_traps_and_exponent_limits_cannot_change_result(self):
        context, policy = fixture()
        result = preflight(context, policy, now=AT)
        with localcontext() as arithmetic:
            arithmetic.prec = 2
            arithmetic.rounding = ROUND_UP
            arithmetic.Emax = 0
            arithmetic.traps[Inexact] = True
            again = preflight(context, policy, now=AT)
        self.assertEqual(result, again)

    def test_zero_net_target_is_rejected_even_when_policy_minimum_is_zero(self):
        context, policy = fixture()
        costs = sealed(replace(context.costs, opening_minimum=Money(D('.02'), 'USD'),
            closing_minimum=Money(D('.02'), 'USD'), slippage_per_side=UnitAmount(Money(D('0'), 'USD'), 'EUR')))
        market = sealed(replace(context.market, bid=context.hypotheses[0].entry, ask=context.hypotheses[0].entry))
        policy = replace(policy, max_quantity=Quantity(D('1'), 'EUR'), minimum_net_target=Money(D('0'), 'USD'))
        result = preflight(replace(context, costs=costs, market=market), policy, now=AT)
        self.assertEqual(EconomicStatus.INFEASIBLE, result.status)
        self.assertIn('NONPOSITIVE_NET_TARGET', {r.reason for r in result.rejections})

    def test_equity_growth_does_not_expand_assignment_and_higher_assignment_is_explicit(self):
        context, policy = fixture()
        small = sealed(replace(context.portfolio, equity=Money(D('1000'), 'USD'),
            allocation_available=Money(D('10'), 'USD')))
        self.assertEqual(EconomicStatus.INFEASIBLE, preflight(replace(context, portfolio=small), policy, now=AT).status)
        larger = sealed(replace(small, allocation_available=Money(D('100'), 'USD')))
        self.assertEqual(EconomicStatus.FEASIBLE, preflight(replace(context, portfolio=larger), policy, now=AT).status)

    def test_financing_assumptions_must_cover_the_requested_directions(self):
        context, policy = fixture(direction=Direction.SHORT)
        costs = sealed(replace(context.costs, directions=(Direction.LONG,)))
        result = preflight(replace(context, costs=costs), policy, now=AT)
        self.assertEqual(EconomicStatus.UNKNOWN, result.status)
        self.assertIn('DIRECTION_COSTS_UNKNOWN', {r.reason for r in result.rejections})

    def test_stress_checks_remaining_margin_and_added_slippage(self):
        context, policy = fixture(stock=True, direction=Direction.SHORT)
        portfolio = sealed(replace(context.portfolio, free_margin=Money(D('42'), 'EUR')))
        stress = replace(policy.stresses[0], maintenance_fraction=D('1'))
        result = preflight(replace(context, portfolio=portfolio), replace(policy, stresses=(stress,)), now=AT)
        self.assertEqual(EconomicStatus.INFEASIBLE, result.status)
        self.assertIn('STRESS_MAINTENANCE_INSUFFICIENT', {r.reason for r in result.rejections})
        stress = replace(stress, extra_slippage_per_side=UnitAmount(Money(D('2'), 'EUR'), 'SHARE'))
        result = preflight(context, replace(policy, stresses=(stress,)), now=AT)
        self.assertEqual(EconomicStatus.INFEASIBLE, result.status)
        self.assertIn('STRESS_RISK_BUDGET_EXCEEDED', {r.reason for r in result.rejections})
