"""Real temporary SQLite, never the operational journals."""
import sqlite3
import tempfile
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import unittest

from trading_agent.forex_research.journal import Journal


class JournalTests(unittest.TestCase):
    def test_restart_preserves_terminal_rejection_and_idempotency(self):
        with tempfile.TemporaryDirectory() as root:
            with Journal(root) as journal:
                self.assertIsNone(journal.reserve('request-1', {'fixture': 'one'}))
                saved = journal.finish('request-1', {'fixture': 'one'},
                                       reason='PREFLIGHT_BLOCKED')
            with Journal(root) as journal:
                self.assertEqual(saved, journal.reserve('request-1', {'fixture': 'one'}))
                self.assertEqual(2, len(journal.history()))
                self.assertIsNone(saved['candidate'])
                with self.assertRaisesRegex(ValueError, 'IDEMPOTENCY_CONFLICT'):
                    journal.reserve('request-1', {'fixture': 'two'})

    def test_uncertain_interruption_never_retries_a_reserved_request(self):
        with tempfile.TemporaryDirectory() as root:
            with Journal(root) as journal:
                journal.reserve('request-1', {})
            with Journal(root) as journal:
                with self.assertRaisesRegex(ValueError, 'REQUEST_PENDING_REVIEW'):
                    journal.reserve('request-1', {})

    def test_concurrent_reservations_have_one_winner(self):
        with tempfile.TemporaryDirectory() as root:
            with Journal(root):
                pass
            barrier = Barrier(2)

            def reserve():
                with Journal(root) as journal:
                    barrier.wait(timeout=5)
                    try:
                        journal.reserve('same-request', {})
                        return 'reserved'
                    except ValueError as exc:
                        return str(exc)

            with ThreadPoolExecutor(max_workers=2) as workers:
                results = list(workers.map(lambda _: reserve(), range(2)))
            self.assertCountEqual(['reserved', 'REQUEST_PENDING_REVIEW'], results)

    def test_events_are_immutable_and_hash_tampering_is_detected(self):
        with tempfile.TemporaryDirectory() as root:
            with Journal(root) as journal:
                journal.reserve('one', {})
                with self.assertRaises(sqlite3.IntegrityError):
                    journal.db.execute('DELETE FROM events')
                with self.assertRaises(sqlite3.IntegrityError):
                    journal.db.execute("UPDATE events SET phase='changed'")
                journal.db.execute('DROP TRIGGER immutable_events_update')
                journal.db.execute("UPDATE events SET event_sha256='corrupted'")
                with self.assertRaisesRegex(ValueError, 'JOURNAL_INTEGRITY'):
                    journal.history()

    def test_direct_candidate_registration_cannot_bypass_economics(self):
        with tempfile.TemporaryDirectory() as root:
            with Journal(root) as journal:
                journal.reserve('one', {})
                with self.assertRaises(ValueError):
                    journal.finish('one', {}, bundle={})
                self.assertEqual(1, len(journal.history()))

    def test_request_id_cannot_be_a_path(self):
        with tempfile.TemporaryDirectory() as root:
            with Journal(root) as journal:
                with self.assertRaises(ValueError):
                    journal.reserve('../../.local', {})
                self.assertEqual([], journal.history())


if __name__ == '__main__':
    unittest.main()
