"""Closed research contracts and explicit resource accounting."""
from dataclasses import FrozenInstanceError, replace
from decimal import Decimal
import unittest

from test_core_v3_economic_contracts import AT, fixture
from trading_agent.core_v3.contracts import ContractError, Money
from trading_agent.core_v3.research_contracts import (
    BudgetPolicy, BudgetStatus, ResearchAllowance, ResearchCharge, ResearchInputs, ResearchRequest, InstrumentIdentity,
)


def request(*, name='request-1', stock=False, direction=None, account_currency=None):
    options = {'stock': stock}
    if direction is not None:
        options['direction'] = direction
    if account_currency is not None:
        options['account_currency'] = account_currency
    context, policy = fixture(**options)
    return ResearchRequest(name, 'key-' + name, InstrumentIdentity.of(context.market.instrument),
        ResearchInputs(context, policy), ResearchAllowance(100, 100, Money(Decimal('.01'), 'USD')))


def budget(*, requests=2, tokens=400, funds='.02'):
    return BudgetPolicy('budget-1', 1, requests, tokens, Money(Decimal(funds), 'USD'))


class ResearchContractTests(unittest.TestCase):
    def test_requests_and_budgets_are_immutable_closed_and_roundtrip(self):
        req = request()
        self.assertEqual(req, ResearchRequest.from_json(req.to_json()))
        self.assertEqual(budget(), BudgetPolicy.from_json(budget().to_json()))
        with self.assertRaises(FrozenInstanceError):
            req.request_id = 'other'
        for key, value in [('execution_authority', True), ('schema_version', 2), ('code', 'eval(x)')]:
            data = req.to_dict()
            data[key] = value
            with self.subTest(key=key), self.assertRaises(ContractError):
                ResearchRequest.from_dict(data)

    def test_ids_resources_and_financial_capital_cannot_be_confused(self):
        req = request()
        for value in ('../escape', 'C:/orders', '.local', ''):
            with self.subTest(value=value), self.assertRaises(ContractError):
                replace(req, request_id=value)
        for changes in ({'max_requests': True}, {'max_requests': 257}, {'max_tokens': -1},
                        {'max_cost': Money(Decimal('1'), 'EUR')}):
            with self.subTest(changes=changes), self.assertRaises(ContractError):
                replace(budget(), **changes)
        self.assertEqual(Decimal('100'), req.inputs.context.portfolio.equity.amount)
        self.assertEqual(Decimal('.01'), req.allowance.max_cost.amount)

    def test_fixed_designer_is_deterministic_and_modified_geometry_or_permissions_are_invalid(self):
        from trading_agent.core_v3.economics import preflight
        from trading_agent.core_v3.research_contracts import DesignRequest
        from trading_agent.core_v3.research_designer import SimulatedDesigner, receipt
        req = request()
        before = preflight(req.inputs.context, req.inputs.policy, now=AT)
        design = DesignRequest(req, before)
        raw = SimulatedDesigner().propose(design)
        self.assertEqual(raw, SimulatedDesigner().propose(design))
        valid = receipt(raw, design)
        self.assertEqual(before.witness, valid.proposal.scenario)
        changed = valid.proposal.to_dict()
        changed['execution_authority'] = True
        from trading_agent.core_v3.contracts import canonical_bytes
        self.assertIsNone(receipt(canonical_bytes(changed).decode(), design).proposal)
        changed = valid.proposal.to_dict()
        changed['scenario']['quantity']['amount'] = '27'
        self.assertIsNone(receipt(canonical_bytes(changed).decode(), design).proposal)
        self.assertIsNone(receipt('{bad', design).proposal)

    def test_budget_wire_cannot_claim_inconsistent_remaining_resources(self):
        zero = Money(Decimal('0'), 'USD')
        status = BudgetStatus(budget(), 0, 0, 2, 0, 0, 400, zero, zero, Money(Decimal('.02'), 'USD'))
        for changes in ({'remaining_requests': 3}, {'remaining_tokens': 399},
                        {'remaining_cost': Money(Decimal('.01'), 'USD')}):
            with self.subTest(changes=changes), self.assertRaises(ContractError):
                replace(status, **changes)
        with self.assertRaises(ContractError):
            ResearchCharge(0, 0, 1, zero)
