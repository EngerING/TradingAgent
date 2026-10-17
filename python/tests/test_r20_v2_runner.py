"""Isolated runner control; no operational cohorts or broker orders."""
import unittest
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from trading_agent.r20_runner import RunnerControl, ReplayRunner, source_manifest

ROOT=Path(__file__).resolve().parents[2]

class RunnerTests(unittest.TestCase):
    def setUp(self):
        from test_r20_v2_shadow import ShadowTests
        self.fixture=ShadowTests();self.fixture.setUp()
        self.f=self.fixture
        RunnerControl.install(self.f.store)
        self.control=RunnerControl(self.f.store,self.f.scope)
        self.manifest=source_manifest(ROOT)
        self.control.preregister(self.manifest)
        self.runner=ReplayRunner(self.f.cycle,self.control,ROOT)

    def test_registration_immutable_and_changed_source_rejected(self):
        self.control.preregister(self.manifest)
        with self.assertRaises(Exception):self.control.preregister(dict(self.manifest,engineHash='0'*64))
        self.assertEqual(self.manifest,self.control.state()['manifest'])

    def test_stop_persistent_preserves_inventory_then_valid_target(self):
        self.f.opened()
        before=self.f.cycle.view()
        self.control.stop('operator-test')
        recovered=RunnerControl(self.f.store,self.f.scope)
        self.assertTrue(recovered.state()['stopRequested'])
        self.assertEqual('STOPPING_MANAGING_SHADOW',self.runner.status()['status'])
        self.runner.step(self.f.quote(connected=False),'offline')
        self.assertEqual(before['positions'],self.f.cycle.inventory())
        with self.assertRaises(Exception):self.f.cycle.reserve(self.f.signal('new'),'forbidden')
        q=self.f.quote('1.04',self.f.quote().at+timedelta(seconds=1));self.f.cycle.clock=lambda:q.at
        self.runner.step(q,'target')
        self.assertEqual('STOPPED',self.runner.status()['status'])
        self.assertEqual('TAKE_PROFIT',self.f.cycle.view()['trades'][0]['reason'])
        self.assertEqual(1,len(self.f.cycle.view()['trades']))

    def test_stop_rejects_already_reserved_open_and_releases_budget(self):
        self.f.permit();self.f.cycle.reserve(self.f.signal(),'reserved')
        self.control.stop('operator-test')
        with self.assertRaises(Exception):self.f.cycle.open('reserved',self.f.quote(),'forbidden')
        self.runner.step(self.f.quote(),'release')
        self.assertEqual((),self.f.store.load(self.f.scope).snapshot.daily.pending_terms)
        self.assertEqual('STOPPED',self.runner.status()['status'])

    def test_roles_cannot_register_or_clear_stop(self):
        from trading_agent.r20_admission import RoleStore
        self.control.stop('operator-test')
        for role in ('reader','profile-admin','paper'):
            c=RunnerControl(RoleStore(self.f.store.database,self.f.store.system_id,role),self.f.scope)
            with self.assertRaises(Exception):c.stop('forged')
            with self.assertRaises(Exception):c.preregister(self.manifest)
        with self.assertRaises(Exception):self.f.store.execute('DELETE FROM r20_v2_runner.controls;')

    def test_restart_recovers_identical_state_and_idempotent_observation(self):
        self.f.opened();q=self.f.quote('1.01')
        row=self.runner.step(q,'mark')
        r=ReplayRunner(self.f.cycle,RunnerControl(self.f.store,self.f.scope),ROOT)
        self.assertEqual(row,r.step(q,'mark'))
        self.assertEqual(1,len(r.status()['positions']))

    def test_stop_lost_response_is_idempotent_and_no_later_reservations(self):
        self.f.permit()
        self.control.stop('operator-test')
        first=self.control.state()
        self.control.stop('operator-test')
        self.assertEqual(first,self.control.state())
        from concurrent.futures import ThreadPoolExecutor
        def reserve(i):
            try:self.f.cycle.reserve(self.f.signal('after-'+str(i)),'after-'+str(i));return True
            except Exception as exc:self.assertIn('SHADOW_STOP_REQUESTED',str(exc));return False
        with ThreadPoolExecutor(max_workers=2) as pool:self.assertEqual([False,False],list(pool.map(reserve,[1,2])))
        self.assertEqual([],self.f.cycle.admission.receipts())

    def test_unexpected_process_exit_releases_singleton_and_preserves_stop(self):
        import subprocess,sys
        from uuid import uuid4
        self.control.stop('operator-test')
        path=ROOT/'artifacts/aggressive-growth-r20-20261010/r20-v2-readiness-20261013'/('crash-'+uuid4().hex+'.lock')
        code="from pathlib import Path; from trading_agent.aggressive_growth_runner import run_lock; import sys,os;\nwith run_lock(Path(sys.argv[1])): os._exit(23)"
        self.assertEqual(23,subprocess.run([sys.executable,'-c',code,str(path)],capture_output=True).returncode)
        from trading_agent.aggressive_growth_runner import run_lock
        with run_lock(path):self.assertTrue(RunnerControl(self.f.store,self.f.scope).state()['stopRequested'])

    def test_monitor_reads_exact_accounting_without_mutation(self):
        from trading_agent.r20_monitor import monitor
        from trading_agent.r20_admission import RoleStore
        self.f.opened();before=self.f.store.load(self.f.scope)
        view=monitor(RoleStore(self.f.store.database,self.f.store.system_id,'reader'),self.f.ctx)
        self.assertEqual(str(before.snapshot.daily.current_equity),view['equity'])
        self.assertEqual(before,self.f.store.load(self.f.scope))
        self.assertEqual(1,len(view['positions']))

    def test_monitor_uses_one_consistent_lifecycle_accounting_cut(self):
        from unittest.mock import patch
        from trading_agent.r20_monitor import monitor
        self.f.opened();state=self.f.cycle._state()
        with patch('trading_agent.r20_shadow.ShadowCycle._state',side_effect=[state,ValueError('SECOND_INCONSISTENT_READ')]):
            self.assertEqual(state[1].hash,monitor(self.f.store,self.f.ctx)['accountingHash'])

    def test_stop_pending_reservation_cross_day_preserves_management(self):
        self.f.permit();self.f.cycle.reserve(self.f.signal(),'midnight-reservation')
        self.control.stop('operator-test')
        tomorrow=self.f.quote().at+timedelta(days=1)
        self.f.cycle.clock=lambda:tomorrow
        self.runner.step(self.f.quote(at=tomorrow),'midnight-stop')
        self.assertEqual('STOPPED',self.runner.status()['status'])
        self.assertEqual((),self.f.store.load(self.f.scope).snapshot.daily.pending_terms)

    def test_singleton_other_process_denied_and_released_after_exit(self):
        import subprocess,sys
        from trading_agent.aggressive_growth_runner import run_lock
        with TemporaryDirectory(dir=ROOT/'artifacts/aggressive-growth-r20-20261010/r20-v2-readiness-20261013') as folder:
            path=Path(folder)/'singleton.lock'
            cmd=[sys.executable,'-c',"from pathlib import Path; from trading_agent.aggressive_growth_runner import run_lock; import sys;\nwith run_lock(Path(sys.argv[1])): print('acquired')",str(path)]
            with run_lock(path):
                p=subprocess.run(cmd,capture_output=True,text=True)
                self.assertNotEqual(0,p.returncode)
                self.assertIn('R20_OBSERVER_ALREADY_RUNNING',p.stderr)
            self.assertEqual(0,subprocess.run(cmd,capture_output=True).returncode)
