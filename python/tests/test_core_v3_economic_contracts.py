"""Economic research on explicit synthetic inputs, never broker account facts."""
from dataclasses import FrozenInstanceError, replace
from datetime import timedelta
from decimal import Decimal
import unittest

from test_core_v3_contracts import AT, eurusd, synthetic_equity
from trading_agent.core_v3.contracts import (
    ContractError, Environment, EvidenceRef, Money, Price, Quantity, SourceKind, content_hash,
)
from trading_agent.core_v3.economic_contracts import (
    CostSchedule, Direction, EconomicContext, EconomicStatus, FxConversion,
    MarginModel, MarketSnapshot, PortfolioSnapshot, ResearchPolicy, StressCase,
    TechnicalHypothesis, UnitAmount,
)


D = Decimal


def evidence(name):
    return EvidenceRef(name, SourceKind.SYNTHETIC, Environment.RESEARCH, 'a' * 64,
                       AT, AT + timedelta(seconds=30))


def sealed(record):
    return replace(record, evidence=replace(record.evidence, content_sha256=record.material_hash()))


def fixture(*, stock=False, direction=Direction.LONG, account_currency=None):
    instrument = synthetic_equity() if stock else eurusd()
    curr, unit = instrument.quote_currency, instrument.quantity_unit
    m = lambda amount: Money(D(amount), curr)
    price = lambda amount: Price(D(amount), curr, unit)
    ua = lambda amount: UnitAmount(m(amount), unit)
    entry, distance, target = ('10', '0.10', '0.40') if stock else ('1.10', '0.01', '0.04')
    bid, ask = ('9.99', '10.01') if stock else ('1.0999', '1.1001')
    account_currency = account_currency or curr
    account = lambda amount: Money(D(amount), account_currency)
    market = sealed(MarketSnapshot('market-1', 1, instrument, price(bid), price(ask), evidence('market')))
    portfolio = sealed(PortfolioSnapshot('portfolio-1', 1, account_currency, account('100'),
        account('100'), account('100'), account('100'), account('10'), evidence('portfolio')))
    costs = sealed(CostSchedule('costs-1', (direction,), m('0.50'), ua('0'), m('0.50'), ua('0'),
                               m('0'), ua('0'), ua('0.00005' if not stock else '0.01'), evidence('costs')))
    margin = sealed(MarginModel(D('1'), D('0.25'), evidence('margin')))
    hypothesis = sealed(TechnicalHypothesis('idea-1', content_hash(instrument), direction,
        price(entry), price(distance), price(target), price(target), 1, evidence('idea')))
    stress = StressCase('gap', ua('0.001' if not stock else '0.10'), ua('0'), D('0.30'))
    policy = ResearchPolicy('research-1', 1, AT, AT + timedelta(minutes=5),
        Quantity(D('8' if stock else '50'), unit), account('0.01'), account('10'),
        price(target), price(distance), ua('0'), ua('0.1'), 4, 30, 100, True, (stress,))
    fx = None if account_currency == curr else sealed(FxConversion(curr, account_currency, D('1.2'), evidence('fx')))
    return EconomicContext(market, portfolio, costs, margin, (hypothesis,), fx), policy


class EconomicContractTests(unittest.TestCase):
    def test_roundtrip_closed_versions_and_immutable_nested_inputs(self):
        context, policy = fixture()
        self.assertEqual(context, EconomicContext.from_json(context.to_json()))
        self.assertEqual(policy, ResearchPolicy.from_json(policy.to_json()))
        with self.assertRaises(FrozenInstanceError):
            context.costs.opening_minimum = Money(D('0'), 'USD')
        for key, value in [('execution_authority', True), ('purpose', 'TECHNICAL_VALIDATION'), ('schema_version', 2)]:
            data = policy.to_dict()
            data[key] = value
            with self.subTest(key=key), self.assertRaises(ContractError):
                ResearchPolicy.from_dict(data)

    def test_bad_numbers_collections_and_non_frozen_fields_rejected(self):
        context, policy = fixture()
        for changes in ({'max_evaluations': True}, {'max_evaluations': 10001},
                        {'stresses': []}, {'allow_synthetic': 1}):
            with self.subTest(changes=changes), self.assertRaises(ContractError):
                replace(policy, **changes)
        with self.assertRaises(ContractError):
            replace(context.costs, opening_minimum=0)

    def test_margin_can_exceed_notional_and_reserved_stress_names_are_rejected(self):
        context, policy = fixture()
        margin = replace(context.margin, initial_fraction=D('1.5'), maintenance_fraction=D('1.3'))
        self.assertEqual(D('1.5'), margin.initial_fraction)
        with self.assertRaises(ContractError):
            replace(policy.stresses[0], stress_id='BASE_STOP')
