"""M03-A synthetic contracts and exchange-calendar adversaries; never TWS."""
from datetime import datetime, timedelta, timezone
from dataclasses import replace
from decimal import Decimal
import unittest

from trading_agent.core_v3.contracts import ContractError
from trading_agent.core_v3.market_observation.contracts import CapturePolicy
from trading_agent.market_data.contracts import CollectorConfig
from trading_agent.market_data.calendar import TradingCalendar

AT = datetime(2026, 10, 23, 12, tzinfo=timezone.utc)


class ContractTests(unittest.TestCase):
    def test_configuration_closed_offline_and_bounded(self):
        value = CollectorConfig('collector-1', CapturePolicy('m03a', max_duration_seconds=120))
        self.assertEqual(value, CollectorConfig.from_json(value.to_json()))
        self.assertFalse(value.enabled)
        for changes in ({'max_segments': 17}, {'max_total_bytes': 1}, {'retry_seconds': 0}):
            with self.assertRaises(ContractError): replace(value, **changes)
        with self.assertRaises(ContractError):
            CollectorConfig.from_json(value.to_json().replace('"schema_version":1', '"schema_version":2'))

    def test_explicit_holiday_interruptions_and_coverage(self):
        cal = TradingCalendar('UTC', '20261023:0900-20261023:1200,1300-20261023:1700;20261024:CLOSED', AT)
        self.assertEqual('CLOSED', cal.state(AT))
        self.assertEqual(AT+timedelta(hours=1), cal.next_open(AT))
        self.assertEqual('OPEN', cal.state(AT+timedelta(hours=2)))
        self.assertEqual('CLOSED', cal.state(AT+timedelta(days=1)))
        self.assertEqual('UNKNOWN', cal.state(AT+timedelta(days=2)))

    def test_dst_nonexistent_and_ambiguous_rejected(self):
        for text in ('20260308:0230-20260308:0400', '20261101:0130-20261101:0400'):
            with self.assertRaises(ContractError): TradingCalendar('America/New_York', text, AT)
        cal = TradingCalendar('America/New_York', '20261023:0900-20261023:1700', AT)
        self.assertEqual('OPEN', cal.state(AT+timedelta(hours=2)))

    def test_invalid_empty_overlap_unknown_zone_and_stale_calendar(self):
        for zone, text in (('Unknown/Zone', '20261023:CLOSED'), ('EST', '20261023:CLOSED'), ('UTC', ''),
                ('UTC', '20261023:0900-20261023:1300,1200-20261023:1700')):
            with self.assertRaises(ContractError): TradingCalendar(zone, text, AT)
        cal = TradingCalendar('UTC', '20261023:0000-20261024:0000', AT)
        self.assertEqual('UNKNOWN', cal.state(AT-timedelta(seconds=1)))


if __name__ == '__main__': unittest.main()
