"""The simulation consumes verified catalog/research reads, without mutating either."""
from contextlib import contextmanager
from dataclasses import replace
import tempfile
import unittest

from test_core_v35_catalog import complete
from test_core_v35_contracts import AT, budget, command, request
from test_core_v36_contracts import dataset, policy
from trading_agent.core_v3.contracts import ContractError
from trading_agent.core_v3.research_journal import ResearchJournal
from trading_agent.core_v3.strategy_catalog.contracts import Action, State
from trading_agent.core_v3.strategy_catalog.service import Catalog
from trading_agent.core_v3.strategy_v34.contracts import Timeframe
from trading_agent.core_v3.strategy_v34.designer import design, SimulatedStrategyDesigner
from trading_agent.core_v3.event_backtest.reader import prepare, load


@contextmanager
def registered(*, stock=False, direction=None, timeframe=Timeframe.M1, req=None):
    req = request(stock=stock, direction=direction) if req is None else req
    with tempfile.TemporaryDirectory() as root, ResearchJournal(root, budget()) as journal, Catalog(root) as catalog:
        complete(journal, req)
        strategy = design(req, timeframe, SimulatedStrategyDesigner(), now=AT)
        cmd = replace(command(req=req, strategy=strategy), timeframe=timeframe)
        outcome = catalog.register(cmd, journal, req.inputs, now=AT)
        assert outcome.state is State.VALIDATED
        yield req, cmd, catalog, journal


def bound(catalog, journal, data=None, rules=None):
    data = dataset() if data is None else data
    rules = policy() if rules is None else rules
    value = prepare('backtest-1', catalog, journal, 'catalog-1', 1, 'registration-1', data, rules, research_cutoff=AT)
    return value, data, rules


class BacktestBindingTests(unittest.TestCase):
    def test_controlled_catalog_read_preserves_both_histories_and_budget(self):
        with registered() as (req, cmd, catalog, journal):
            histories = catalog.history(), journal.history(), journal.budget_status()
            value, data, rules = bound(catalog, journal)
            version, evidence = load(value, catalog, journal, data, rules)
            self.assertEqual(cmd.strategy, version.registration.strategy)
            self.assertEqual(value, evidence.request)
            self.assertEqual(histories, (catalog.history(), journal.history(), journal.budget_status()))
            self.assertEqual(value, type(value).from_json(value.to_json()))

    def test_every_identity_hash_and_dataset_or_policy_change_is_rejected(self):
        with registered() as (_, _, catalog, journal):
            value, data, rules = bound(catalog, journal)
            for field in ('catalog_sha256', 'research_request_sha256', 'scenario_sha256', 'economic_sha256',
                          'dataset_sha256', 'policy_sha256'):
                with self.subTest(field=field), self.assertRaises(ContractError):
                    load(replace(value, **{field: '0'*64}), catalog, journal, data, rules)
            with self.assertRaises(ContractError):
                load(replace(value, catalog_ref=replace(value.catalog_ref, record_sha256='0'*64)), catalog, journal, data, rules)
            with self.assertRaises(ContractError):
                load(value, catalog, journal, data, replace(rules, close_at_end=True))

    def test_future_cutoff_expired_validation_and_fake_catalog_are_rejected(self):
        from datetime import timedelta
        with registered() as (_, _, catalog, journal):
            value, data, rules = bound(catalog, journal)
            for shift in (-1, 31):
                with self.assertRaises(ContractError):
                    load(replace(value, research_cutoff=AT+timedelta(seconds=shift)), catalog, journal, data, rules)
            with self.assertRaises(ContractError):
                load(value, object(), journal, data, rules)
            with self.assertRaises(ContractError):
                load(value, catalog, object(), data, rules)

    def test_later_catalog_invalidation_blocks_cached_request(self):
        with registered() as (req, cmd, catalog, journal):
            value, data, rules = bound(catalog, journal)
            changed = replace(req.inputs, context=replace(req.inputs.context, costs=None))
            invalid = replace(cmd, operation_id='invalidate', idempotency_key='invalidate', action=Action.REVALIDATE)
            self.assertEqual(State.INVALIDATED, catalog.register(invalid, journal, changed, now=AT).state)
            with self.assertRaises(ContractError):
                load(value, catalog, journal, data, rules)
