"""Real temporary SQLite; no historical database is used."""
from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from pathlib import Path
import sqlite3
import tempfile
import unittest

from test_core_v3_research_contracts import AT, budget, request
from trading_agent.core_v3.contracts import ContractError
from trading_agent.core_v3.research_contracts import DesignRequest, ResearchState
from trading_agent.core_v3.research_designer import SimulatedDesigner
from trading_agent.core_v3.research_journal import ResearchJournal


class ResearchJournalTests(unittest.TestCase):
    def test_atomic_reservation_and_known_response_settlement_survive_restart(self):
        req = request()
        with tempfile.TemporaryDirectory() as root:
            with ResearchJournal(root, budget(requests=1)) as journal:
                result, created = journal.receive(req, now=AT)
                self.assertTrue(created)
                self.assertEqual(ResearchState.RECEIVED, result.state)
                result = journal.admit(req.request_id, now=AT)
                self.assertEqual(ResearchState.BUDGET_RESERVED, result.state)
                self.assertEqual(1, journal.budget_status().reserved_requests)
                self.assertEqual(200, journal.budget_status().reserved_tokens)
                journal.start(req.request_id, now=AT)
                raw = SimulatedDesigner().propose(DesignRequest(req, result.preflight))
                journal.record_reply(req.request_id, raw, now=AT)
                self.assertEqual(1, journal.budget_status().consumed_requests)
                self.assertEqual(0, journal.budget_status().reserved_tokens)
                journal.begin_postflight(req.request_id, req.inputs, now=AT)
                final = journal.finish(req.request_id, now=AT)
                self.assertEqual(ResearchState.CANDIDATE_RECORDED, final.state)
                path = journal.path
            with ResearchJournal(root, budget(requests=1)) as journal:
                cached, created = journal.receive(req, now=AT)
                self.assertFalse(created)
                self.assertEqual(final, cached)
                self.assertEqual(0, journal.budget_status().remaining_requests)
                self.assertEqual(path, journal.path)

    def test_conflicting_ids_and_budget_configuration_are_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            with ResearchJournal(root, budget()) as journal:
                req = request()
                journal.receive(req, now=AT)
                for changed in (replace(req, idempotency_key='new-key'),
                                replace(req, request_id='new-request')):
                    with self.assertRaisesRegex(ContractError, 'IDEMPOTENCY_CONFLICT'):
                        journal.receive(changed, now=AT)
            with self.assertRaises(ContractError):
                ResearchJournal(root, budget(requests=3))

    def test_recovery_keeps_uncertain_reservation_and_does_not_retry(self):
        with tempfile.TemporaryDirectory() as root:
            with ResearchJournal(root, budget(requests=1)) as journal:
                req = request()
                journal.receive(req, now=AT)
                journal.admit(req.request_id, now=AT)
                journal.start(req.request_id, now=AT)
            with ResearchJournal(root, budget(requests=1)) as journal:
                result = journal.recover(req.request_id, now=AT)
                self.assertEqual(ResearchState.INTERRUPTED, result.state)
                self.assertEqual(1, result.charge.reserved_requests)
                self.assertEqual(0, journal.budget_status().remaining_requests)
                self.assertEqual(result, journal.receive(req, now=AT)[0])

    def test_events_are_append_only_and_tail_deletion_is_detected(self):
        with tempfile.TemporaryDirectory() as root:
            with ResearchJournal(root, budget()) as journal:
                journal.receive(request(), now=AT)
                with self.assertRaises(sqlite3.IntegrityError):
                    journal.db.execute('DELETE FROM events WHERE sequence=2')
                journal.db.execute('DROP TRIGGER immutable_events_delete')
                journal.db.execute('DELETE FROM events WHERE sequence=2')
                journal.db.execute("CREATE TRIGGER immutable_events_delete BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT,'IMMUTABLE'); END")
                with self.assertRaisesRegex(ContractError, 'JOURNAL_INTEGRITY'):
                    journal.history()

    def test_path_is_fixed_and_private_or_redirected_roots_are_rejected(self):
        with self.assertRaises(ContractError):
            ResearchJournal(Path.cwd() / '.local', budget())
        with tempfile.TemporaryDirectory() as root:
            with ResearchJournal(root, budget()) as journal:
                self.assertEqual(Path(root).resolve() / 'artifacts/research/core-v3-3/journal.sqlite3', journal.path)

    def test_concurrent_requests_have_one_reservation_and_duplicate_has_one_owner(self):
        for same_id in (False, True):
            with self.subTest(same_id=same_id), tempfile.TemporaryDirectory() as root:
                with ResearchJournal(root, budget(requests=1)):
                    pass
                ready = Barrier(2)
                def worker(index):
                    with ResearchJournal(root, budget(requests=1)) as journal:
                        ready.wait(timeout=5)
                        req = request(name='same' if same_id else 'request-' + str(index))
                        result, owned = journal.receive(req, now=AT)
                        return owned, journal.admit(req.request_id, now=AT).state if owned else result.state
                with ThreadPoolExecutor(max_workers=2) as pool:
                    results = list(pool.map(worker, range(2)))
                if same_id:
                    self.assertEqual(1, sum(owned for owned, state in results))
                else:
                    self.assertEqual(1, sum(state is ResearchState.BUDGET_RESERVED for owned, state in results))
                with ResearchJournal(root, budget(requests=1)) as journal:
                    self.assertEqual(1, journal.budget_status().reserved_requests)

    def test_preinvoke_expiry_and_known_unused_recovery_release_only_unused_budget(self):
        for expired in (False, True):
            with tempfile.TemporaryDirectory() as root:
                with ResearchJournal(root, budget(requests=1)) as journal:
                    req = request()
                    journal.receive(req, now=AT)
                    journal.admit(req.request_id, now=AT)
                    result = (journal.start(req.request_id, now=AT + timedelta(seconds=31)) if expired
                              else journal.recover(req.request_id, now=AT))
                    self.assertEqual(0, result.charge.reserved_requests)
                    self.assertEqual(1, journal.budget_status().remaining_requests)

    def test_sqlite_failure_rolls_back_reservation_and_head_together(self):
        with tempfile.TemporaryDirectory() as root:
            with ResearchJournal(root, budget()) as journal:
                req = request()
                journal.receive(req, now=AT)
                journal.db.execute("CREATE TRIGGER fail_reservation BEFORE INSERT ON events WHEN NEW.state='BUDGET_RESERVED' BEGIN SELECT RAISE(ABORT,'INJECTED_FAILURE'); END")
                with self.assertRaisesRegex(ContractError, 'RESEARCH_PERSISTENCE_FAILED'):
                    journal.admit(req.request_id, now=AT)
                self.assertEqual(ResearchState.RECEIVED, journal.read(req.request_id).state)
                self.assertEqual(0, journal.budget_status().reserved_requests)
                journal.db.execute('DROP TRIGGER fail_reservation')
                self.assertEqual(ResearchState.BUDGET_RESERVED, journal.admit(req.request_id, now=AT).state)

    def test_payload_alteration_and_illegal_rehashed_transition_are_detected(self):
        for semantic in (False, True):
            with self.subTest(semantic=semantic), tempfile.TemporaryDirectory() as root:
                with ResearchJournal(root, budget()) as journal:
                    journal.receive(request(), now=AT)
                    row = journal.history()[-1]
                    journal.db.execute('DROP TRIGGER immutable_events_update')
                    if semantic:
                        changed = 'CANDIDATE_RECORDED'
                        digest = journal._event_hash(row['sequence'], row['request_id'], changed, row['at'],
                                                     row['payload'], row['previous_sha256'])
                        journal.db.execute('UPDATE events SET state=?,event_sha256=? WHERE sequence=2', (changed, digest))
                        journal.db.execute('UPDATE head SET event_sha256=?', (digest,))
                    else:
                        journal.db.execute("UPDATE events SET payload='{}' WHERE sequence=2")
                    journal.db.execute("CREATE TRIGGER immutable_events_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT,'IMMUTABLE'); END")
                    with self.assertRaisesRegex(ContractError, 'JOURNAL_INTEGRITY'):
                        journal.history()

    def test_busy_database_fails_with_bounded_locking_and_preserves_the_ledger(self):
        with tempfile.TemporaryDirectory() as root, ResearchJournal(root, budget()) as journal:
            journal.db.execute('BEGIN IMMEDIATE')
            try:
                with self.assertRaisesRegex(ContractError, 'RESEARCH_PERSISTENCE_FAILED'):
                    ResearchJournal(root, budget())
            finally:
                journal.db.execute('ROLLBACK')
            self.assertEqual(1, len(journal.history()))
            self.assertEqual(0, journal.budget_status().reserved_requests)
