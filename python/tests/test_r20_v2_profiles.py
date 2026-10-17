"""Synthetic in-memory contracts only; no operational configuration or broker."""
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D
import json
import unittest

from trading_agent.r20_profiles import EconomicProfile, economic_day

AT = datetime(2026, 10, 12, 12, tzinfo=timezone.utc)


def profile(**changes):
    values = dict(configuration_version=1, scope_id='r20-v2-test',
                  capital_base_usd=D('100'), equity_cap_usd=None,
                  risk_per_trade_pct=D('20'), capital_allocation_pct=D('50'),
                  max_leverage=D('5'), daily_loss_limit_pct=D('20'), max_open_positions=3,
                  effective_from=AT, effective_until=AT.replace(day=13, hour=4),
                  created_at=AT, cost_policy_hash='a'*64, operational_policy_hash='b'*64)
    values.update(changes)
    return EconomicProfile(**values)


class ProfileTests(unittest.TestCase):
    def test_frozen_and_roundtrip(self):
        p = profile()
        with self.assertRaises(FrozenInstanceError): p.max_leverage = D('10')
        self.assertEqual(p, EconomicProfile.from_json(p.to_json()))
        self.assertEqual(64, len(p.configuration_hash))

    def test_canonical_decimal_hash(self):
        self.assertEqual(profile().configuration_hash,
                         profile(risk_per_trade_pct=D('20.00')).configuration_hash)
        self.assertNotEqual(profile().configuration_hash,
                            profile(equity_cap_usd=D('110')).configuration_hash)

    def test_bad_numbers_and_limits(self):
        for field, value in [('risk_per_trade_pct',D('0')),('capital_allocation_pct',D('101')),
                             ('max_leverage',D('.9')),('daily_loss_limit_pct',D('NaN')),
                             ('capital_base_usd',D('Infinity')),('equity_cap_usd',D('-1')),
                             ('max_open_positions',True),('configuration_version',0),
                             ('risk_per_trade_pct',20.0)]:
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                profile(**{field:value})

    def test_strict_json_and_tampering(self):
        for change in ({'max_leverage':'7'}, {'extra':True}, {'max_open_positions':True},
                       {'configuration_hash':'f'*64}):
            obj=json.loads(profile().to_json()); obj.update(change)
            with self.assertRaises(ValueError): EconomicProfile.from_json(json.dumps(obj))

    def test_duplicate_json_keys(self):
        text=profile().to_json().replace('"scope_id":', '"scope_id":"duplicate","scope_id":')
        with self.assertRaises(ValueError): EconomicProfile.from_json(text)

    def test_timezone_and_midnight(self):
        day,start,end=economic_day(AT)
        self.assertEqual('2026-10-12',day)
        self.assertEqual(4,start.hour)
        self.assertEqual(start+timedelta(days=1),end)
        self.assertEqual('2026-10-11',economic_day(start-timedelta(microseconds=1))[0])
        self.assertEqual('America/Santo_Domingo',profile().economic_timezone)

    def test_temporal_contract_and_freshness(self):
        p=profile()
        self.assertTrue(p.valid_at(AT)); self.assertFalse(p.valid_at(p.effective_until))
        for changes in ({'effective_from':AT.replace(tzinfo=None)},
                        {'created_at':AT+timedelta(seconds=1)},
                        {'effective_until':AT+timedelta(days=2)}):
            with self.assertRaises(ValueError): profile(**changes)

    def test_indicator_precision_decimal_contract(self):
        from trading_agent.r20_profiles import number, decimal_text
        value=D('0.001416239476565055862979893344')
        self.assertEqual(value,number(value))
        self.assertEqual(value,decimal_text(str(value)))


if __name__ == '__main__': unittest.main()
