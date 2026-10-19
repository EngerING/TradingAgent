"""Transactions, conflicts, replay and bounded own storage."""
from dataclasses import replace
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from trading_agent.core_v3.contracts import ContractError
from trading_agent.core_v3.market_observation.contracts import Origin, SessionKind, Kind
from trading_agent.core_v3.market_observation.journal import Journal
from test_core_v39_validation import prices, event, policy, AT


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)/'market.sqlite'
        self.rules = policy()
        self.j = Journal(self.path, self.rules, 'session-1', Origin.FIXTURE, SessionKind.PAPER)

    def tearDown(self):
        self.j.close()
        self.tmp.cleanup()

    def put(self, raw):
        return self.j.append(raw, as_of=raw.received_at)

    def test_roundtrip_reopen_and_exact_duplicate(self):
        for raw in prices():
            self.put(raw)
        checkpoint = self.j.checkpoint()
        expected = self.j.export()
        self.assertEqual(self.put(prices()[-1]), self.j.history()[-1])
        self.j.close()
        self.j = Journal(self.path, self.rules, 'session-1', Origin.FIXTURE, SessionKind.PAPER, checkpoint=checkpoint)
        self.assertEqual(expected, self.j.export())
        self.assertEqual(5, len(self.j.history()))

    def test_invalid_original_is_preserved_and_sequence_gap_visible(self):
        for raw in prices()[:-1]:
            self.put(raw)
        bad = event(7, Kind.ASK, price_text='NaN', tick_type=2)
        row = self.put(bad)
        self.assertFalse(row.value.accepted)
        self.assertEqual('NaN', row.value.event.price_text)
        self.assertIn('RECEIVE_SEQUENCE_GAP', row.value.reasons)

    def test_conflict_and_cross_environment_fail(self):
        self.put(prices()[0])
        for raw in (replace(prices()[0], diagnostic='CHANGED'),
                    replace(prices()[1], session_kind=SessionKind.LIVE),
                    replace(prices()[1], origin=Origin.SOCKET)):
            with self.assertRaises(ContractError):
                self.put(raw)
        self.assertEqual(1, len(self.j.history()))

    def test_failure_before_commit_rolls_back_and_retry_is_single(self):
        with patch.object(Journal, '_before_commit', side_effect=ConnectionError('fixture')):
            with self.assertRaises(ConnectionError):
                self.put(prices()[0])
        self.assertEqual((), self.j.history())
        self.put(prices()[0])
        self.assertEqual(1, len(self.j.history()))

    def test_events_are_immutable_and_real_corruption_detected(self):
        self.put(prices()[0])
        with closing(sqlite3.connect(self.path, isolation_level=None)) as db:
            with self.assertRaises(sqlite3.DatabaseError):
                db.execute('DELETE FROM events')
            db.execute('UPDATE head SET digest=?', ('0'*64,))
        with self.assertRaises(ContractError):
            self.j.history()

    def test_external_checkpoint_detects_valid_prefix_rollback(self):
        self.put(prices()[0])
        old = self.path.read_bytes()
        self.put(prices()[1])
        checkpoint = self.j.checkpoint()
        self.j.close()
        self.path.write_bytes(old)
        with self.assertRaises(ContractError):
            Journal(self.path, self.rules, 'session-1', Origin.FIXTURE, SessionKind.PAPER, checkpoint=checkpoint)

    def test_event_and_disk_budgets_and_unsafe_sidecar(self):
        self.j.close()
        other = Path(self.tmp.name)/'bounded.sqlite'
        bounded = Journal(other, policy(max_events=1, max_disk_bytes=262144), 'session-1', Origin.FIXTURE, SessionKind.PAPER)
        try:
            bounded.append(prices()[0], as_of=AT)
            with self.assertRaises(ContractError):
                bounded.append(prices()[1], as_of=AT)
            self.assertLessEqual(other.stat().st_size, 262144)
        finally:
            bounded.close()
        sidecar = Path(str(self.path)+'-wal')
        sidecar.write_bytes(b'unsafe')
        with self.assertRaises(ContractError):
            Journal(self.path, self.rules, 'session-1', Origin.FIXTURE, SessionKind.PAPER)
