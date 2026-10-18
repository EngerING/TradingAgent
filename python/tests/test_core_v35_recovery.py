"""Interrupted cross-file protocols, corruption and competing workers."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
import sqlite3
import tempfile
from threading import Barrier
import unittest
from unittest.mock import patch

from test_core_v35_contracts import AT, budget, command
from test_core_v35_catalog import complete
from trading_agent.core_v3.contracts import ContractError
from trading_agent.core_v3.research_journal import ResearchJournal
from trading_agent.core_v3.strategy_catalog.contracts import State
from trading_agent.core_v3.strategy_catalog.research_link import SourceChanged, SourceUnavailable
from trading_agent.core_v3.strategy_catalog.service import Catalog
from trading_agent.core_v3.strategy_catalog.store import _Store
from trading_agent.core_v3.strategy_catalog import service
from trading_agent.core_v3.strategy_v34.contracts import Indicator, Operand, Rule


class CatalogRecoveryTests(unittest.TestCase):
    def test_failure_before_request_commit_rolls_back_event_and_head(self):
        with tempfile.TemporaryDirectory() as root, ResearchJournal(root, budget()) as journal, Catalog(root) as catalog:
            req = complete(journal)
            cmd = command(req=req)
            before = journal.history()
            catalog._store.db.execute("CREATE TRIGGER fail_request BEFORE INSERT ON events WHEN NEW.state='REQUESTED' BEGIN SELECT RAISE(ABORT,'FAULT'); END")
            with self.assertRaisesRegex(ContractError, 'CATALOG_PERSISTENCE_FAILED'):
                catalog.register(cmd, journal, req.inputs, now=AT)
            self.assertEqual(1, len(catalog.history()))
            catalog._store.db.execute('DROP TRIGGER fail_request')
            self.assertEqual(State.VALIDATED, catalog.register(cmd, journal, req.inputs, now=AT).state)
            self.assertEqual(before, journal.history())

    def test_crash_after_request_or_prepare_requires_explicit_reconciliation(self):
        for phase in (State.REQUESTED, State.PREPARED):
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as root:
                with ResearchJournal(root, budget()) as journal:
                    req = complete(journal)
                    cmd = command(req=req)
                    source_before = journal.history()
                    with Catalog(root) as catalog:
                        target = patch.object(service, 'capture', side_effect=KeyboardInterrupt) if phase is State.REQUESTED else patch.object(_Store, 'record', side_effect=KeyboardInterrupt)
                        with target, self.assertRaises(KeyboardInterrupt):
                            catalog.register(cmd, journal, req.inputs, now=AT)
                        self.assertEqual(phase, catalog.outcome(cmd.operation_id).state)
                    with Catalog(root) as catalog:
                        self.assertEqual(phase, catalog.register(cmd, journal, req.inputs, now=AT).state)
                        self.assertEqual(State.VALIDATED, catalog.reconcile(cmd.operation_id, journal, req.inputs, now=AT).state)
                        self.assertEqual(1, len(catalog.versions()))
                    self.assertEqual(source_before, journal.history())

    def test_sqlite_failure_after_record_is_pending_and_never_duplicates_the_version(self):
        with tempfile.TemporaryDirectory() as root, ResearchJournal(root, budget()) as journal:
            req = complete(journal)
            cmd = command(req=req)
            with Catalog(root) as catalog:
                catalog._store.db.execute("CREATE TRIGGER fail_validation BEFORE INSERT ON events WHEN NEW.state='VALIDATED' BEGIN SELECT RAISE(ABORT,'FAULT'); END")
                with self.assertRaisesRegex(ContractError, 'CATALOG_PERSISTENCE_FAILED'):
                    catalog.register(cmd, journal, req.inputs, now=AT)
                self.assertEqual(State.RECORDED, catalog.outcome(cmd.operation_id).state)
                self.assertEqual(1, len(catalog.versions()))
                catalog._store.db.execute('DROP TRIGGER fail_validation')
            with Catalog(root) as catalog:
                self.assertEqual(State.VALIDATED, catalog.reconcile(cmd.operation_id, journal, req.inputs, now=AT).state)
                self.assertEqual(1, sum(row['state'] == 'RECORDED' for row in catalog.history()))

    def test_unknown_commit_acknowledgement_is_resolved_by_durable_idempotency(self):
        original = _Store.event
        with tempfile.TemporaryDirectory() as root, ResearchJournal(root, budget()) as journal, Catalog(root) as catalog:
            req = complete(journal)
            cmd = command(req=req)
            def ambiguous(store, view, state, payload, *, now):
                result = original(store, view, state, payload, now=now)
                if state is State.VALIDATED:
                    raise KeyboardInterrupt
                return result
            with patch.object(_Store, 'event', autospec=True, side_effect=ambiguous), self.assertRaises(KeyboardInterrupt):
                catalog.register(cmd, journal, req.inputs, now=AT)
            result = catalog.register(cmd, journal, req.inputs, now=AT)
            self.assertEqual(State.VALIDATED, result.state)
            self.assertEqual(1, len(catalog.versions()))
            self.assertEqual(1, journal.budget_status().consumed_requests)

    def test_source_unavailable_after_record_blocks_until_explicit_recovery(self):
        original = service.verify
        calls = [0]
        with tempfile.TemporaryDirectory() as root, ResearchJournal(root, budget()) as journal, Catalog(root) as catalog:
            req = complete(journal)
            cmd = command(req=req)
            def unavailable(source, proof):
                calls[0] += 1
                if calls[0] == 2:
                    raise SourceUnavailable('RESEARCH_SOURCE_UNAVAILABLE')
                return original(source, proof)
            with patch.object(service, 'verify', side_effect=unavailable):
                result = catalog.register(cmd, journal, req.inputs, now=AT)
            self.assertEqual(State.RECOVERY_REQUIRED, result.state)
            self.assertEqual(1, len(catalog.versions()))
            self.assertEqual(State.VALIDATED, catalog.reconcile(cmd.operation_id, journal, req.inputs, now=AT).state)

    def test_expiry_during_interruption_invalidates_but_preserves_recorded_history(self):
        with tempfile.TemporaryDirectory() as root, ResearchJournal(root, budget()) as journal, Catalog(root) as catalog:
            req = complete(journal)
            cmd = command(req=req)
            catalog._store.db.execute("CREATE TRIGGER fail_validation BEFORE INSERT ON events WHEN NEW.state='VALIDATED' BEGIN SELECT RAISE(ABORT,'FAULT'); END")
            with self.assertRaises(ContractError):
                catalog.register(cmd, journal, req.inputs, now=AT)
            catalog._store.db.execute('DROP TRIGGER fail_validation')
            original = catalog.version(cmd.catalog_id, 1)
            result = catalog.reconcile(cmd.operation_id, journal, req.inputs, now=AT + timedelta(seconds=31))
            self.assertEqual(State.INVALIDATED, result.state)
            self.assertEqual(original, catalog.version(cmd.catalog_id, 1))

    def test_cached_terminal_does_not_accept_another_valid_but_missing_source_prefix(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as other:
            with ResearchJournal(root, budget()) as journal, ResearchJournal(other, budget()) as replacement, Catalog(root) as catalog:
                req = complete(journal)
                cmd = command(req=req)
                catalog.register(cmd, journal, req.inputs, now=AT)
                with self.assertRaises(SourceChanged):
                    catalog.register(cmd, replacement, req.inputs, now=AT)

    def test_real_source_corruption_blocks_revalidation_and_cached_readthrough(self):
        from trading_agent.core_v3.strategy_catalog.contracts import Action
        with tempfile.TemporaryDirectory() as root, ResearchJournal(root, budget()) as journal, Catalog(root) as catalog:
            req = complete(journal)
            cmd = command(req=req)
            catalog.register(cmd, journal, req.inputs, now=AT)
            journal.db.execute('DROP TRIGGER immutable_events_update')
            journal.db.execute("UPDATE events SET payload='{}' WHERE sequence=(SELECT MAX(sequence) FROM events)")
            journal.db.execute("CREATE TRIGGER immutable_events_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT,'IMMUTABLE'); END")
            validation = replace(cmd, operation_id='source-check', idempotency_key='source-check-key', action=Action.REVALIDATE)
            self.assertEqual(State.RECOVERY_REQUIRED, catalog.register(validation, journal, req.inputs, now=AT).state)
            with self.assertRaises(SourceUnavailable):
                catalog.register(cmd, journal, req.inputs, now=AT)
            self.assertEqual(1, len(catalog.versions()))

    def test_tail_loss_and_rehashed_illegal_transitions_are_detected(self):
        for tail in (False, True):
            with self.subTest(tail=tail), tempfile.TemporaryDirectory() as root:
                with ResearchJournal(root, budget()) as journal, Catalog(root) as catalog:
                    req = complete(journal)
                    cmd = command(req=req)
                    catalog.register(cmd, journal, req.inputs, now=AT)
                    db = catalog._store.db
                    if tail:
                        db.execute('DROP TRIGGER immutable_events_delete')
                        db.execute('DELETE FROM events WHERE sequence=(SELECT MAX(sequence) FROM events)')
                        db.execute("CREATE TRIGGER immutable_events_delete BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT,'IMMUTABLE'); END")
                    else:
                        row = catalog.history()[1]
                        digest = _Store._hash(row['sequence'], row['operation_id'], 'VALIDATED', row['at'], row['payload'], row['previous_sha256'])
                        db.execute('DROP TRIGGER immutable_events_update')
                        db.execute('UPDATE events SET state=?,event_sha256=? WHERE sequence=2', ('VALIDATED', digest))
                        db.execute("CREATE TRIGGER immutable_events_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT,'IMMUTABLE'); END")
                    with self.assertRaisesRegex(ContractError, 'CATALOG_INTEGRITY'):
                        catalog.history()

    def test_competing_workers_claim_once_and_conflicting_revisions_have_one_winner(self):
        for revision in (False, True):
            with self.subTest(revision=revision), tempfile.TemporaryDirectory() as root:
                with ResearchJournal(root, budget()) as journal, Catalog(root) as catalog:
                    req = complete(journal)
                    initial = command(req=req)
                    if revision:
                        first = catalog.register(initial, journal, req.inputs, now=AT)
                        parent = first.target.record_sha256
                    else:
                        parent = None
                ready = Barrier(2)
                def worker(index):
                    with ResearchJournal(root, budget()) as source, Catalog(root) as catalog:
                        if revision:
                            rule = initial.strategy.entry_rules[0]
                            updated = replace(initial.strategy, entry_rules=(Rule(rule.left, rule.operator, Operand(Indicator.SMA, 4 + index, 0)),))
                            cmd = command(name='revision-' + str(index), req=req, strategy=updated, version=2, parent=parent)
                        else:
                            cmd = initial
                        ready.wait(timeout=10)
                        return catalog.register(cmd, source, req.inputs, now=AT)
                with ThreadPoolExecutor(max_workers=2) as pool:
                    results = list(pool.map(worker, range(2)))
                with Catalog(root) as catalog:
                    self.assertEqual(2 if revision else 1, len(catalog.versions()))
                    self.assertTrue(any(r.state is State.VALIDATED for r in results))
                    if revision:
                        self.assertEqual(1, sum(r.state is State.REJECTED for r in results))
