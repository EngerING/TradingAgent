"""Real Python -> isolated R20 CLI -> test PostgreSQL, with no market reader.

Requires TRADING_TEST_DB and TRADING_LAB_DB equal to TEST_DB and a built R20 API.
Observations are synthetic fixtures, never operational or forward evidence.
"""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import timedelta
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from test_aggressive_growth import ROOT, AT, observation
from trading_agent.aggressive_growth import configuration
from trading_agent.aggressive_growth_runner import Experiment, Journal, engine_hashes, run_lock, verify_protocol

TEST_DB = 'Host=127.0.0.1;Port=55432;Username=trading_test;Database=postgres'


@unittest.skipUnless(os.environ.get('TRADING_TEST_DB'), 'Explicit test database required')
class RealJournalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if any(os.environ.get(k) != TEST_DB for k in ('TRADING_TEST_DB', 'TRADING_LAB_DB')):
            raise RuntimeError('ISOLATED_TEST_DATABASE_55432_REQUIRED')
        cls.evidence = []

    @classmethod
    def tearDownClass(cls):
        destination = os.environ.get('R20_TEST_EVIDENCE')
        if destination:
            Path(destination).write_text(json.dumps(dict(database_port=55432, configuration='R20',
                fixture_evidence_only=True, experiments=cls.evidence), indent=2), encoding='utf-8')

    def setUp(self):
        self.identifier = 'aggressive-r20-' + uuid4().hex
        self.journal = Journal(ROOT, self.identifier, configuration='R20')
        self.at = AT + timedelta(seconds=1)
        self.reader_guard = patch('trading_agent.aggressive_growth_runner.Reader', side_effect=AssertionError('NO_BROKER_READER_IN_TESTS'))
        self.reader_guard.start(); self.addCleanup(self.reader_guard.stop)
        self.e = Experiment(self.journal, lambda: self.at)
        self.e.prepare(configuration(ROOT), engine_hashes(ROOT))

    def tearDown(self):
        head = self.journal.load()
        self.evidence.append(dict(test=self.id(), experiment=self.identifier, revision=head['revision'], hash=head['hash']))

    def reload(self):
        return Experiment(Journal(ROOT, self.identifier, configuration='R20'), lambda: self.at)

    def test_round_trip_inventory_stop_stale_quote_restart_and_terminal_idempotence(self):
        self.e.observe(observation()); opened = deepcopy(self.e.state)
        e = self.reload(); self.assertEqual(opened, e.state)
        e.stop(); stopping = deepcopy(e.state)
        self.assertTrue(stopping['stop_requested'])
        self.assertEqual(opened['portfolios'], stopping['portfolios'])
        e = self.reload(); self.at += timedelta(minutes=1)
        obs = observation(at=self.at); obs['quote']['at'] = AT.isoformat(); e.observe(obs)
        self.assertEqual('STOPPING_MANAGING_SHADOW', e.state['status'])
        self.assertEqual(opened['portfolios'], e.state['portfolios'])
        e = self.reload(); e.observe(observation(at=self.at))
        self.assertEqual('STOPPED', e.state['status'])
        for p in e.state['portfolios'].values():
            self.assertIsNone(p['active']); self.assertEqual(1, len(p['trades']))
            self.assertEqual('OPERATOR_STOP', p['trades'][0]['exit_reason'])
        head = self.journal.load(); e = self.reload(); e.stop(); e.observe(observation(at=self.at))
        self.assertEqual(head, self.journal.load())
        self.assertEqual(opened['signals'], e.state['signals'])

    def test_concurrent_consumers_commit_one_signal_set_and_reload_loser(self):
        first, second = self.reload(), self.reload()
        def consume(e):
            try: e.observe(observation()); return True
            except RuntimeError: return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(consume, (first, second)))
        self.assertEqual([False, True], sorted(outcomes))
        loser = first if not outcomes[0] else second
        self.assertIsNone(loser.state)
        with self.assertRaisesRegex(ValueError, 'R20_STATE_RELOAD_REQUIRED'): loser.observe(observation())
        winner = self.reload(); self.assertEqual(2, winner.revision)
        signals = deepcopy(winner.state['signals']); inventory = deepcopy(winner.state['portfolios'])
        winner.observe(observation())
        self.assertEqual(signals, winner.state['signals'])
        self.assertEqual(inventory, winner.state['portfolios'])

    def test_lost_ack_after_real_commit_requires_reload_without_duplicate(self):
        commit = self.journal.commit
        def lose_ack(*args):
            commit(*args)
            raise RuntimeError('ACK_LOST_AFTER_REAL_INSERT')
        with patch.object(self.journal, 'commit', side_effect=lose_ack):
            with self.assertRaisesRegex(RuntimeError, 'ACK_LOST'): self.e.observe(observation())
        self.assertIsNone(self.e.state)
        e = self.reload(); self.assertEqual(2, e.revision)
        before = deepcopy(e.state); e.observe(observation())
        self.assertEqual(before['signals'], e.state['signals'])
        self.assertEqual(before['portfolios'], e.state['portfolios'])

    def test_inventory_signals_stop_and_closed_trades_cannot_be_removed(self):
        self.e.observe(observation()); self.e.stop()
        def reject(mutate):
            e = self.reload(); candidate = deepcopy(e.state); mutate(candidate); head = self.journal.load()
            with self.assertRaises(RuntimeError): e.commit(candidate, 'INVALID_TEST_CANDIDATE')
            self.assertEqual(head, self.journal.load())
        reject(lambda s: s['portfolios']['R20'].update(active=None, equity=s['portfolios']['R20']['cash_equity']))
        reject(lambda s: s.update(signals=[]))
        reject(lambda s: s.update(stop_requested=False))
        reject(lambda s: s.update(run_kind='HISTORICAL'))
        reject(lambda s: s['portfolios']['R20']['active'].update(run_kind='HISTORICAL'))
        self.e = self.reload(); self.e.observe(observation())
        reject(lambda s: s['portfolios']['R20'].update(trades=[]))

    def test_historical_journal_cannot_be_reclassified_as_forward(self):
        identifier = 'aggressive-r20-' + uuid4().hex
        journal = Journal(ROOT, identifier, configuration='R20'); e = Experiment(journal, lambda: self.at)
        e.prepare(configuration(ROOT), engine_hashes(ROOT), 'HISTORICAL')
        obs = observation(); obs['quote']['type'] = 'HISTORICAL_MODELED'; e.observe(obs)
        restored = Experiment(journal, lambda: self.at)
        self.assertEqual('HISTORICAL', restored.state['portfolios']['R20']['active']['run_kind'])
        with self.assertRaisesRegex(ValueError, 'HISTORICAL_CANNOT_RUN_FORWARD'): verify_protocol(restored, ROOT)
        head = journal.load(); candidate = deepcopy(restored.state); candidate['run_kind'] = 'FORWARD'
        with self.assertRaises(RuntimeError): restored.commit(candidate, 'FORBIDDEN_RECLASSIFICATION')
        self.assertEqual(head, journal.load())
        self.evidence.append(dict(test=self.id(), experiment=identifier, revision=head['revision'], hash=head['hash'], run_kind='HISTORICAL'))


class ProcessLockTests(unittest.TestCase):
    def child(self, path):
        script = """import sys
from pathlib import Path
from trading_agent.aggressive_growth_runner import run_lock
try:
    with run_lock(Path(sys.argv[1])): print('ACQUIRED')
except RuntimeError as e:
    print(str(e))
"""
        return subprocess.run([sys.executable, '-c', script, str(path)], capture_output=True, text=True, timeout=10)

    def test_second_process_blocked_and_release_allows_restart_without_growing_lock(self):
        with tempfile.TemporaryDirectory(prefix='r20-lock-') as folder:
            path = Path(folder) / 'singleton.lock'
            with run_lock(path):
                result = self.child(path)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual('R20_OBSERVER_ALREADY_RUNNING', result.stdout.strip())
            result = self.child(path)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual('ACQUIRED', result.stdout.strip())
            self.assertEqual(0, path.stat().st_size)

    def test_unknown_build_configuration_rejected(self):
        with self.assertRaisesRegex(ValueError, 'R20_BUILD_CONFIGURATION_REQUIRED'):
            Journal(ROOT, 'aggressive-r20-' + 'a'*32, configuration='../../Release')


if __name__ == '__main__': unittest.main()
