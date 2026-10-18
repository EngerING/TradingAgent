"""Declarative wire boundary: closed data, never executable source."""
from dataclasses import FrozenInstanceError, replace
import unittest

from test_core_v3_contracts import eurusd
from trading_agent.core_v3.contracts import ContractError, content_hash
from trading_agent.core_v3.strategy_v34.contracts import Indicator, Operand, Operator, Rule, Timeframe


def close(lag=0):
    return Operand(Indicator.CLOSE, 1, lag)


def sma(period=3, lag=0):
    return Operand(Indicator.SMA, period, lag)


class DeclarativeContractTests(unittest.TestCase):
    def test_roundtrip_and_frozen(self):
        value = Rule(close(), Operator.CROSS_ABOVE, sma())
        self.assertEqual(value, Rule.from_json(value.to_json()))
        with self.assertRaises(FrozenInstanceError):
            value.left = sma()

    def test_unknown_fields_versions_and_executable_strings_rejected(self):
        value = Rule(close(), Operator.GT, sma()).to_dict()
        for key, content in [('code', '__import__("os")'), ('schema_version', 2),
                             ('execution_authority', True), ('operator', 'eval')]:
            data = dict(value, **{key: content})
            with self.subTest(key=key), self.assertRaises(ContractError):
                Rule.from_dict(data)
        data = Rule(close(), Operator.GT, sma()).to_dict()
        data['left']['indicator'] = 'lambda: 1'
        with self.assertRaises(ContractError):
            Rule.from_dict(data)

    def test_parameters_are_bounded_strict_integers(self):
        for args in [(Indicator.SMA, True, 0), (Indicator.SMA, 1, 0),
                     (Indicator.SMA, 201, 0), (Indicator.CLOSE, 2, 0),
                     (Indicator.CLOSE, 1, -1), (Indicator.CLOSE, 1, 33),
                     (Indicator.CLOSE, 1, False), ('SMA', 3, 0)]:
            with self.subTest(args=args), self.assertRaises(ContractError):
                Operand(*args)

    def test_json_duplicate_nonfinite_depth_and_size_limits(self):
        raw = Rule(close(), Operator.GT, sma()).to_json()
        for bad in [raw[:-1] + ',"schema_version":1}', '{"x":NaN}',
                    '{"x":' + '[' * 40 + '0' + ']' * 40 + '}', '{"x":"' + 'a'*131072 + '"}']:
            with self.subTest(length=len(bad)), self.assertRaises(ContractError):
                Rule.from_json(bad)

    def test_content_hash_covers_rules_and_instrument_specification(self):
        a = Rule(close(), Operator.GT, sma())
        self.assertNotEqual(content_hash(a), content_hash(replace(a, right=sma(4))))
        self.assertNotEqual(content_hash(eurusd()), content_hash(replace(eurusd(), specification_version=2)))

    def test_timeframes_are_closed(self):
        self.assertEqual([60, 300, 3600], [v.seconds for v in Timeframe])


if __name__ == '__main__':
    unittest.main()
