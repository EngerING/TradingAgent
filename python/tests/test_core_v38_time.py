from datetime import datetime, timezone
from importlib.resources import files
import unittest

from trading_agent.core_v3.contracts import ContractError
from trading_agent.core_v3.historical_ingestion.contracts import Session, SessionCalendar
from trading_agent.core_v3.historical_ingestion.time_rules import load_zone, parse_timestamp, expected_intervals


def tzif(name='UTC'):
    return files('tzdata.zoneinfo').joinpath(*name.split('/')).read_bytes()


def dt(text):
    return datetime.fromisoformat(text.replace('Z', '+00:00'))


def calendar(sessions=None):
    if sessions is None:
        sessions = (Session('s1', '2026-01-05', dt('2026-01-05T00:00Z'), dt('2026-01-05T02:00Z')),)
    return SessionCalendar('fixture-calendar', 'r1', 'UTC', 'b'*64,
        dt('2026-01-01T00:00Z'), dt('2026-02-01T00:00Z'), sessions)


class TimeRules(unittest.TestCase):
    def test_offsets_select_both_folds_exactly(self):
        zone = load_zone(tzif('America/New_York'), 'America/New_York')
        first = parse_timestamp('2026-11-01T01:30:00.123456-04:00', zone)
        second = parse_timestamp('2026-11-01T01:30:00.123456-05:00', zone)
        self.assertEqual((second-first).total_seconds(), 3600)
        self.assertEqual(first.microsecond, 123456)
        self.assertEqual(first.tzinfo, timezone.utc)

    def test_nonexistent_naive_wrong_offset_and_precision_are_rejected(self):
        zone = load_zone(tzif('America/New_York'), 'America/New_York')
        for value in ('2026-03-08T02:30:00-05:00', '2026-11-01T01:30:00',
                      '2026-07-01T12:00:00-05:00', '2026-01-05T00:00:00.1234567-05:00',
                      '2026-01-05T00:00:60-05:00', '2026-01-05T00:00:00-05:99'):
            with self.subTest(value=value), self.assertRaises(ContractError):
                parse_timestamp(value, zone)

    def test_calendar_wire_and_holiday_early_close(self):
        sessions = (Session('fri', '2026-01-02', dt('2026-01-02T00:00Z'), dt('2026-01-02T01:00Z')),
                    Session('mon', '2026-01-05', dt('2026-01-05T00:00Z'), dt('2026-01-05T02:00Z')))
        value = calendar(sessions)
        self.assertEqual(SessionCalendar.from_json(value.to_json()), value)
        slots = expected_intervals(value, sessions[0].opened_at, sessions[-1].closed_at, 3600)
        self.assertEqual(len(slots), 3)  # No manufactured weekend bars; early Friday close.

    def test_overlap_reversed_and_out_of_coverage_sessions_rejected(self):
        session = calendar().sessions[0]
        for sessions in ((session, session), (Session('bad', '2025-12-31',
                 dt('2025-12-31T23:00Z'), dt('2026-01-01T01:00Z')),)):
            with self.assertRaises(ContractError):
                calendar(sessions)

    def test_partial_window_and_excessive_expansion_rejected(self):
        value = calendar()
        for start, end, interval in ((dt('2026-01-05T00:30Z'), dt('2026-01-05T02:00Z'), 3600),
                                     (dt('2026-01-05T00:00Z'), dt('2026-01-05T02:00Z'), 1),
                                     (dt('2025-12-31T00:00Z'), dt('2026-01-05T02:00Z'), 3600)):
            with self.assertRaises(ContractError):
                expected_intervals(value, start, end, interval)

    def test_bad_tzif_rejected(self):
        with self.assertRaises(ContractError):
            load_zone(b'not a zone', 'UTC')
