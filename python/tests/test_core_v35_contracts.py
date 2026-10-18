"""Closed catalog wire and deliberately bounded semantic equivalence."""
from dataclasses import FrozenInstanceError, replace
import unittest

from test_core_v3_research_contracts import AT, budget, request
from trading_agent.core_v3.contracts import ContractError, content_hash
from trading_agent.core_v3.strategy_v34.contracts import Operator, Rule, Timeframe
from trading_agent.core_v3.strategy_v34.designer import SimulatedStrategyDesigner, design
from trading_agent.core_v3.strategy_catalog.contracts import Action, CatalogRequest, semantic_hash


def command(*, name='registration-1', catalog_id='catalog-1', version=1, parent=None,
            req=None, strategy=None, action=Action.REGISTER):
    req = request() if req is None else req
    strategy = design(req, Timeframe.M1, SimulatedStrategyDesigner(), now=AT) if strategy is None else strategy
    return CatalogRequest(name, 'key-' + name, action, catalog_id, version, parent,
                          'research-1', req.request_id, Timeframe.M1, strategy)


class CatalogContractTests(unittest.TestCase):
    def test_closed_immutable_roundtrip_and_no_authority_fields(self):
        cmd = command()
        self.assertEqual(cmd, CatalogRequest.from_json(cmd.to_json()))
        with self.assertRaises(FrozenInstanceError):
            cmd.version = 2
        for key, value in [('execution_authority', True), ('code', 'arbitrary'), ('schema_version', 2)]:
            data = cmd.to_dict()
            data[key] = value
            with self.subTest(key=key), self.assertRaises(ContractError):
                CatalogRequest.from_dict(data)
        for changes in ({'operation_id': '../outside'}, {'catalog_id': '.local'}, {'version': True}, {'version': 0}):
            with self.assertRaises(ContractError):
                replace(cmd, **changes)

    def test_semantics_ignore_names_provenance_and_conjunction_order_but_preserve_behavior(self):
        strategy = command().strategy
        rename = replace(strategy, strategy_id='renamed', request_sha256='a' * 64,
                         scenario=replace(strategy.scenario, hypothesis_id='other', context_sha256='b' * 64,
                                          policy_sha256='c' * 64))
        self.assertEqual(semantic_hash(strategy), semantic_hash(rename))
        rule = strategy.entry_rules[0]
        inverse = Rule(rule.right, Operator.CROSS_BELOW, rule.left)
        self.assertEqual(semantic_hash(strategy), semantic_hash(replace(strategy, entry_rules=(inverse,))))
        extra = Rule(rule.left, Operator.GT, rule.right)
        two = replace(strategy, entry_rules=(rule, extra))
        self.assertEqual(semantic_hash(two), semantic_hash(replace(two, entry_rules=(extra, rule))))
        for altered in (replace(strategy, entry_rules=(extra,)),
                        replace(strategy, scenario=replace(strategy.scenario, quantity=replace(strategy.scenario.quantity,
                            amount=strategy.scenario.quantity.amount + 1)))):
            self.assertNotEqual(semantic_hash(strategy), semantic_hash(altered))
