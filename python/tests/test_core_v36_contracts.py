"""Closed synthetic data and simulation policy boundaries."""
from dataclasses import FrozenInstanceError, replace
from datetime import timedelta
from decimal import Decimal
import unittest

from test_core_v3_economic_contracts import AT, fixture
from trading_agent.core_v3.contracts import ContractError, SourceKind
from trading_agent.core_v3.research_contracts import InstrumentIdentity
from trading_agent.core_v3.strategy_v34.contracts import Timeframe
from trading_agent.core_v3.event_backtest.contracts import SyntheticBar, SyntheticDataset, BacktestPolicy


def dataset(*, stock=False, timeframe=Timeframe.M1, offsets=(0, -2, -2, 2, 2, 2)):
    context, _ = fixture(stock=stock)
    instrument = context.market.instrument
    base = context.hypotheses[0].entry
    bars = []
    for index, offset in enumerate(offsets):
        start = AT + timedelta(seconds=index*timeframe.seconds)
        end = start + timedelta(seconds=timeframe.seconds)
        price = replace(base, amount=base.amount + instrument.tick.amount*offset)
        bars.append(SyntheticBar('bar-' + str(index), start, end, end, price, price, price, price))
    return SyntheticDataset('synthetic-1', InstrumentIdentity.of(instrument), timeframe, tuple(bars))


def policy(**changes):
    return BacktestPolicy(**dict(dict(policy_id='simulation-1', close_at_end=False, max_bars=128,
        max_events=1024, max_trades=16, max_duration_hours=720, max_result_bytes=131072), **changes))


class BacktestContractTests(unittest.TestCase):
    def test_dataset_and_policy_are_closed_immutable_versioned_roundtrips(self):
        for value in (dataset(), policy()):
            self.assertEqual(value, type(value).from_json(value.to_json()))
            with self.assertRaises(FrozenInstanceError):
                if type(value) is BacktestPolicy:
                    value.policy_id = 'changed'
                else:
                    value.dataset_id = 'changed'
            for key, content in [('code', 'ignored'), ('schema_version', 2), ('execution_authority', True)]:
                raw = value.to_dict()
                raw[key] = content
                with self.subTest(key=key), self.assertRaises(ContractError):
                    type(value).from_dict(raw)

    def test_dataset_rejects_duplicate_ids_gaps_wrong_units_and_real_provenance(self):
        value = dataset()
        for changes in [dict(bars=value.bars[:1]*2), dict(bars=value.bars[::2]),
                        dict(source_kind=SourceKind.AUTHENTIC_CAPTURE), dict(bars=list(value.bars))]:
            with self.subTest(changes=changes), self.assertRaises(ContractError):
                replace(value, **changes)
        bar = value.bars[0]
        with self.assertRaises(ContractError):
            replace(bar, available_at=bar.closed_at-timedelta(seconds=1))
        with self.assertRaises(ContractError):
            replace(bar, high=replace(bar.high, currency='EUR'))

    def test_policy_has_hard_resource_bounds_and_fixed_execution_semantics(self):
        for changes in [dict(max_bars=129), dict(max_events=1025), dict(max_trades=17),
                        dict(max_duration_hours=721), dict(max_result_bytes=131073), dict(max_bars=True),
                        dict(intrabar='TARGET_FIRST'), dict(engine_version='unknown')]:
            with self.subTest(changes=changes), self.assertRaises(ContractError):
                policy(**changes)
        self.assertEqual('STOP_FIRST', policy().intrabar)

    def test_financial_data_reject_float_boolean_nonfinite_and_duplicate_json(self):
        bar = dataset().bars[0]
        for amount in [1.1, True, 'NaN', '1e2']:
            raw = bar.to_dict()
            raw['close']['amount'] = amount
            with self.subTest(amount=amount), self.assertRaises(ContractError):
                SyntheticBar.from_dict(raw)
        with self.assertRaises(ContractError):
            BacktestPolicy.from_json('{"schema":1,"schema":2}')
