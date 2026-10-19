"""Counterfactual costs require a proof; execution changes require an actual rerun."""
from dataclasses import replace
from decimal import Decimal as D, localcontext
from hashlib import sha256
import unittest

from test_core_v36_binding import registered
from test_core_v37_planning import example
from trading_agent.core_v3.contracts import Money, content_hash, strict_json
from trading_agent.core_v3.strategy_v34.contracts import Timeframe
from trading_agent.core_v3.statistical_validation.contracts import RobustnessScenario
from trading_agent.core_v3.statistical_validation.evidence import observe
from trading_agent.core_v3.statistical_validation.planning import windows
from trading_agent.core_v3.statistical_validation.robustness import evaluate


class RobustnessTests(unittest.TestCase):
    def test_spread_slippage_fees_financing_and_fragility_have_independent_proofs(self):
        with registered(timeframe=Timeframe.H1) as (_, cmd, catalog, journal):
            plan, rules, chunks = example(cmd, catalog)
            split, data, warmup = windows(plan, rules, (catalog.version('catalog-1', 1),), chunks)[0]
            base = observe(plan.candidates[0], split, data, warmup, rules.backtest,
                           content_hash(plan.manifest), catalog, journal, 'base')
            original = base.to_json()
            scenarios = (RobustnessScenario('spread', extra_half_spread_ticks=1),
                RobustnessScenario('slippage', extra_slippage_ticks=1),
                RobustnessScenario('commission', extra_opening_fee=Money(D('.1'), 'USD')),
                RobustnessScenario('finance', extra_financing_fixed=Money(D('.1'), 'USD')),
                RobustnessScenario('finance-rate', extra_financing_per_unit_hour=Money(D('.001'), 'USD')))
            for scenario in scenarios:
                value, extra, proof = evaluate(base, scenario, plan.candidates[0], split, warmup,
                    catalog, journal, rules, content_hash(plan.manifest), 2)
                self.assertEqual('PROVEN_SINGLE_TRADE_EQUIVALENCE', value.method)
                self.assertIsNone(extra)
                self.assertEqual(value.proof_sha256, sha256(proof.encode('utf-8')).hexdigest())
                self.assertLess(value.net.amount, base.result.metrics.net.amount)
                if scenario.scenario_id == 'commission':
                    self.assertEqual(D('-.0678'), value.net.amount)
                    self.assertTrue(value.fragile)
            self.assertEqual(original, base.to_json())

    def test_changed_admission_and_wrong_currency_never_get_posthoc_cost_metrics(self):
        with registered(timeframe=Timeframe.H1) as (_, cmd, catalog, journal):
            plan, rules, chunks = example(cmd, catalog)
            split, data, warmup = windows(plan, rules, (catalog.version('catalog-1', 1),), chunks)[0]
            base = observe(plan.candidates[0], split, data, warmup, rules.backtest,
                           content_hash(plan.manifest), catalog, journal, 'base')
            for scenario in (RobustnessScenario('expensive', extra_opening_fee=Money(D('100'), 'USD')),
                             RobustnessScenario('currency', extra_opening_fee=Money(D('.1'), 'EUR'))):
                value, _, proof = evaluate(base, scenario, plan.candidates[0], split, warmup,
                    catalog, journal, rules, content_hash(plan.manifest), 2)
                self.assertEqual('NOT_ESTABLISHED', value.method)
                self.assertIsNone(value.net)
                self.assertIsNone(proof)

    def test_execution_policy_is_rerun_and_decimal_context_is_fixed(self):
        with registered(timeframe=Timeframe.H1) as (research, cmd, catalog, journal):
            plan, rules, chunks = example(cmd, catalog)
            split, data, warmup = windows(plan, rules, (catalog.version('catalog-1', 1),), chunks)[0]
            base = observe(plan.candidates[0], split, data, warmup, rules.backtest,
                           content_hash(plan.manifest), catalog, journal, 'base')
            catalog.register(replace(cmd, operation_id='unrelated', idempotency_key='unrelated',
                                     catalog_id='unrelated'), journal, research.inputs,
                             now=plan.candidates[0].research_cutoff)
            value, extra, _ = evaluate(base, RobustnessScenario('execution', close_at_end=False),
                plan.candidates[0], split, warmup, catalog, journal, rules, content_hash(plan.manifest), 2)
            self.assertEqual('RERUN_V36', value.method)
            self.assertNotEqual(base.request.policy_sha256, extra.request.policy_sha256)
            self.assertEqual(base.request.catalog_sequence, extra.request.catalog_sequence)
            self.assertEqual(base.request.catalog_sha256, extra.request.catalog_sha256)
            shock = RobustnessScenario('commission', extra_opening_fee=Money(D('.1'), 'USD'))
            expected = evaluate(base, shock, plan.candidates[0], split, warmup,
                                catalog, journal, rules, content_hash(plan.manifest), 3)[0]
            with localcontext() as context:
                context.prec = 3
                actual = evaluate(base, shock, plan.candidates[0], split, warmup,
                                  catalog, journal, rules, content_hash(plan.manifest), 3)[0]
            self.assertEqual(expected, actual)
