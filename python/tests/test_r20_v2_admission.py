"""Synthetic reservation ledgers only. No cohorts, fills or broker connections."""
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal as D
from concurrent.futures import ThreadPoolExecutor
import os, unittest
from uuid import uuid4
from test_r20_v2_configuration import context, VALUES
from test_r20_v2_profiles import AT, profile
from test_r20_v2_persistence import snapshot
from trading_agent.r20_configuration import ConfigurationService
from trading_agent.r20_persistence import TestStore
from trading_agent.r20_admission import AdmissionCoordinator, SignalProposal, RoleStore
from trading_agent.r20_economics import OpenRisk


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.store=TestStore(os.environ['R20_V2_TEST_DATABASE'],os.environ['R20_V2_TEST_SYSTEM_ID'])
        self.store.install()
        self.scope='r20-v2-test-ledger-admission-'+uuid4().hex
        self.p=profile(scope_id=self.scope)
        self.store.append(snapshot(self.p),'seed',0,'')
        self.ctx=context(self.scope)
        self.config=ConfigurationService(self.store,self.ctx,lambda:AT);self.config.install()
        AdmissionCoordinator.install(self.store)
        self.coordinator=AdmissionCoordinator(self.store,self.ctx,lambda:AT)

    def activate(self,values=None):
        revision=self.config.view()['revision']
        self.config.command('draft',dict(revision=revision,requestId=uuid4().hex,values=values or VALUES),'profile-admin')
        self.config.command('validate',dict(revision=revision+1,requestId=uuid4().hex),'profile-admin')
        return self.config.command('activate',dict(revision=revision+2,requestId=uuid4().hex),'profile-admin')

    def signal(self,name='signal-one',**changes):
        return replace(SignalProposal(name,'LONG',D('1'),D('.02'),AT,AT,'SYNTHETIC_TEST_ONLY','a'*64,'b'*64),**changes)

    def test_no_profile_unknown_expired_stale_or_wrong_source_means_no_reservation(self):
        with self.assertRaisesRegex(ValueError,'PROFILE_REQUIRED'):self.coordinator.reserve(self.signal(),'no-profile')
        self.activate()
        for proposal in (self.signal(quote_at=AT-timedelta(seconds=31)),self.signal(source='UNKNOWN'),self.signal(signal_at=AT-timedelta(seconds=181))):
            with self.assertRaises(ValueError):self.coordinator.reserve(proposal,uuid4().hex)
        self.ctx['cost_unknowns']=['FINANCING_UNKNOWN']
        with self.assertRaises(ValueError):self.coordinator.reserve(self.signal(),'unknown')
        self.ctx['cost_unknowns']=[];tomorrow=AT.replace(day=13,hour=4);self.coordinator.clock=lambda:tomorrow
        with self.assertRaisesRegex(ValueError,'PROFILE_EXPIRED'):
            self.coordinator.reserve(self.signal(signal_at=tomorrow,quote_at=tomorrow),'expired')
        self.assertEqual(1,self.store.load(self.scope).revision)

    def test_two_simultaneous_signals_cannot_reuse_one_head_or_budget(self):
        self.activate();head=self.store.load(self.scope)
        def reserve(i):
            try:return self.coordinator.reserve(self.signal('signal-'+str(i)),str(i),expected_head=head)
            except ValueError as exc:self.assertIn('CAS_CONFLICT',str(exc));return None
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(reserve,[1,2]))
        self.assertEqual(1,sum(x is not None for x in results))
        saved=self.store.load(self.scope).snapshot
        self.assertEqual(1,len(saved.daily.pending_terms))
        self.assertLessEqual(saved.daily.used_loss+saved.daily.pending_risk,saved.daily.budget)

    def test_sequential_signals_share_remaining_capacity_without_double_costs(self):
        self.activate()
        first=self.coordinator.reserve(self.signal('one'),'one')
        second=self.coordinator.reserve(self.signal('two'),'two')
        saved=self.store.load(self.scope).snapshot
        self.assertLess(D(second['assessment']['quantity']),D(first['assessment']['quantity']))
        self.assertEqual(D('4'),saved.daily.used_loss)
        self.assertEqual(D('16'),saved.daily.pending_risk)
        self.assertEqual(D('0'),saved.daily.remaining)
        with self.assertRaisesRegex(ValueError,'DAILY_CAPACITY'):self.coordinator.reserve(self.signal('three'),'three')
        self.assertEqual(3,self.store.load(self.scope).revision)

    def test_short_reservation_uses_increased_nominal_in_stress(self):
        from test_r20_v2_sizing import stresses
        from dataclasses import asdict
        from trading_agent.r20_profiles import canonical
        self.ctx['side']='SHORT';self.ctx['stresses']=canonical([asdict(s) for s in stresses('SHORT')])
        self.activate()
        receipt=self.coordinator.reserve(self.signal(side='SHORT'),'short')
        row=receipt['assessment']['stress'][1]
        self.assertEqual(D('260'),D(row['exposure']))
        self.assertEqual(D('88'),D(row['equity']))
        self.assertEqual('SHORT',receipt['signal']['side'])

    def test_pure_signal_contract_keeps_strategy_and_rejects_no_signal(self):
        common=dict(signal_id='boundary',price=D('1'),quote_at=AT,engine_hash='a'*64,evidence_hash='b'*64,source='SYNTHETIC_TEST_ONLY')
        signal=dict(strategy='AGGRESSIVE_TREND_BREAKOUT_V1',side='SHORT',stop_distance='0.02',at=AT.isoformat())
        p=SignalProposal.from_engine(signal,**common);self.assertEqual('SHORT',p.side);self.assertEqual(D('.02'),p.stop_distance)
        self.assertIsNone(SignalProposal.from_engine(dict(signal,side=None),**common))
        with self.assertRaisesRegex(ValueError,'STRATEGY_MISMATCH'):SignalProposal.from_engine(dict(signal,strategy='R10'),**common)

    def test_actual_existing_signal_engine_adapts_both_sides_without_changing_decisions(self):
        from test_aggressive_growth import bars,AT as engine_at,ROOT
        from trading_agent import aggressive_growth as engine
        configuration=engine.configuration(ROOT)
        for side in ('LONG','SHORT'):
            raw=engine.signal(configuration,bars(side),60,engine_at)
            proposal=SignalProposal.from_engine(raw,signal_id='engine-'+side,price=D(raw['close']),
                quote_at=engine_at,engine_hash='a'*64,evidence_hash='b'*64,source='SYNTHETIC_TEST_ONLY')
            self.assertEqual(side,proposal.side)
            self.assertEqual(D(raw['stop_distance']),proposal.stop_distance)
            self.assertEqual(raw,engine.signal(configuration,bars(side),60,engine_at))

    def test_db_rejects_forged_budget_reservation_even_from_shadow_role(self):
        self.activate()
        class ForgedStore(TestStore):
            def execute(self,sql):
                if sql.startswith('SELECT r20_v2_admission.reserve('):
                    import re,base64,json
                    matches=list(re.finditer("decode\\('([^']+)','base64'\\)",sql))
                    last=matches[-1]
                    row=json.loads(base64.b64decode(last.group(1)))
                    row['assessment']['estimated_costs']='0'
                    payload=base64.b64encode(json.dumps(row).encode()).decode()
                    sql=sql[:last.start(1)]+payload+sql[last.end(1):]
                return super().execute('SET ROLE r20_lab_shadow;'+sql)
        with self.assertRaisesRegex(RuntimeError,'RESERVATION_CERTIFICATE'):
            AdmissionCoordinator(ForgedStore(self.store.database,self.store.system_id),self.ctx,lambda:AT).reserve(self.signal(),'forged')
        self.assertEqual(1,self.store.load(self.scope).revision)

    def test_cost_is_reserved_once_and_pending_risk_excludes_that_cost(self):
        self.activate();receipt=self.coordinator.reserve(self.signal(),'reserve')
        h=self.store.load(self.scope)
        self.assertEqual(D('98'),h.snapshot.daily.current_equity)
        self.assertEqual(D('2'),h.snapshot.daily.used_loss)
        self.assertEqual(D('10'),h.snapshot.daily.pending_risk)
        self.assertEqual(D('12'),D(receipt['assessment']['stress'][1]['candidate_loss']))
        self.assertEqual(receipt,self.coordinator.reserve(self.signal(),'reserve'))
        self.assertEqual(2,self.store.load(self.scope).revision)
        with self.assertRaisesRegex(ValueError,'SIGNAL_ALREADY_RESERVED'):
            self.coordinator.reserve(self.signal(),'another-request')

    def test_profile_change_between_assessment_and_commit_is_rejected(self):
        self.activate();before=self.store.load(self.scope)
        def intervene():self.activate(dict(VALUES,max_leverage='3'))
        with self.assertRaisesRegex(ValueError,'CONFIG_CAS_CONFLICT'):
            self.coordinator.reserve(self.signal(),'race',before_commit=intervene)
        self.assertEqual(before,self.store.load(self.scope))

    def test_lost_ack_and_restart_return_original_receipt(self):
        self.activate()
        def lost():raise ConnectionError('simulated response lost after actual commit')
        with self.assertRaises(ConnectionError):self.coordinator.reserve(self.signal(),'lost',after_commit=lost)
        restarted=AdmissionCoordinator(self.store,self.ctx,lambda:AT+timedelta(seconds=3))
        receipt=restarted.reserve(self.signal(),'lost')
        self.assertEqual(2,receipt['accountingRevision']);self.assertEqual(2,self.store.load(self.scope).revision)

    def test_failure_before_commit_has_no_reservation(self):
        self.activate()
        def disconnected():raise ConnectionError('before commit')
        with self.assertRaises(ConnectionError):self.coordinator.reserve(self.signal(),'disconnected',before_commit=disconnected)
        self.assertEqual(1,self.store.load(self.scope).revision)

    def test_open_inventory_survives_profile_change_and_day_expiry(self):
        h=self.store.load(self.scope)
        opened=snapshot(self.p,opened=(('old-position',D('-1')),),open_terms=(OpenRisk('old-position',D('-1'),D('-2')),))
        self.store.append(opened,'open-inventory-fixture',h.revision,h.hash)
        self.activate(dict(VALUES,max_open_positions='1'))
        with self.assertRaisesRegex(ValueError,'POSITION_LIMIT'):self.coordinator.reserve(self.signal(),'full')
        self.activate(VALUES)
        with self.assertRaisesRegex(ValueError,'OPEN_INVENTORY_CONTEXT_REQUIRED'):self.coordinator.reserve(self.signal(),'missing-position-context')
        tomorrow=AT.replace(day=13,hour=4);self.coordinator.clock=lambda:tomorrow
        with self.assertRaisesRegex(ValueError,'PROFILE_EXPIRED'):
            self.coordinator.reserve(self.signal(signal_at=tomorrow,quote_at=tomorrow),'new-day')
        self.assertEqual(opened,self.store.load(self.scope).snapshot)

    def test_db_roles_separate_reader_profile_admin_shadow_and_paper(self):
        self.activate()
        for role in ('reader','profile-admin','paper'):
            guarded=AdmissionCoordinator(RoleStore(self.store.database,self.store.system_id,role),self.ctx,lambda:AT)
            with self.assertRaisesRegex(RuntimeError,'permission denied'):guarded.reserve(self.signal(),role)
        shadow=AdmissionCoordinator(RoleStore(self.store.database,self.store.system_id,'shadow'),self.ctx,lambda:AT)
        self.assertEqual(2,shadow.reserve(self.signal(),'shadow')['accountingRevision'])
        for role in ('reader','profile-admin','shadow','paper'):
            with self.assertRaisesRegex(RuntimeError,'permission denied'):
                RoleStore(self.store.database,self.store.system_id,role).execute('DELETE FROM r20_v2_test.events;')

    def test_shadow_and_paper_cannot_activate_profile(self):
        for role in ('reader','shadow','paper'):
            s=ConfigurationService(RoleStore(self.store.database,self.store.system_id,role),self.ctx,lambda:AT)
            with self.assertRaisesRegex(RuntimeError,'permission denied'):
                s.command('draft',dict(revision=0,requestId=role,values=VALUES),role)
        s=ConfigurationService(RoleStore(self.store.database,self.store.system_id,'profile-admin'),self.ctx,lambda:AT)
        self.assertEqual('DRAFT',s.command('draft',dict(revision=0,requestId='admin',values=VALUES),'admin')['lifecycle'])

    def test_database_connection_lost_before_commit_rolls_back_both_records(self):
        self.activate()
        class DroppedConnection(TestStore):
            def execute(self,sql):
                if sql.startswith('SELECT r20_v2_admission.reserve('):
                    sql='BEGIN;'+sql+'SELECT pg_terminate_backend(pg_backend_pid());COMMIT;'
                return super().execute(sql)
        dropped=DroppedConnection(self.store.database,self.store.system_id)
        with self.assertRaises(RuntimeError):
            AdmissionCoordinator(dropped,self.ctx,lambda:AT).reserve(self.signal(),'disconnect-in-transaction')
        self.assertEqual(1,self.store.load(self.scope).revision)
        self.assertEqual([],self.coordinator.receipts())

    def test_two_python_processes_use_one_snapshot_with_one_winner(self):
        import subprocess,sys,json
        from trading_agent.r20_profiles import encoded
        code='''import sys,json
from datetime import datetime
from decimal import Decimal
from trading_agent.r20_persistence import TestStore
from trading_agent.r20_admission import AdmissionCoordinator,SignalProposal
r=json.loads(sys.stdin.readline());s=TestStore(r['database'],r['systemId']);h=s.load(r['context']['scope'])
print('READY',flush=True);sys.stdin.readline()
a=datetime.fromisoformat(r['at']);p=SignalProposal(r['signal'],'LONG',Decimal('1'),Decimal('.02'),a,a,'SYNTHETIC_TEST_ONLY','a'*64,'b'*64)
try:
 out=AdmissionCoordinator(s,r['context'],lambda:a).reserve(p,r['signal'],expected_head=h)
 print(json.dumps({'committed':True,'revision':out['accountingRevision']}),flush=True)
except ValueError as e:print(json.dumps({'committed':False,'reason':str(e)}),flush=True)
'''
        self.activate()
        env={k:v for k,v in os.environ.items() if k.upper() in ('PATH','SYSTEMROOT','TEMP','TMP','PYTHONPATH')}
        workers=[]
        try:
            for i in range(2):
                proc=subprocess.Popen([sys.executable,'-c',code],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',env=env)
                workers.append(proc)
                proc.stdin.write(encoded(dict(database=self.store.database,systemId=self.store.system_id,context=self.ctx,at=AT,signal='process-'+str(i)))+'\n');proc.stdin.flush()
            for proc in workers:self.assertEqual('READY',proc.stdout.readline().strip())
            for proc in workers:proc.stdin.write('GO\n');proc.stdin.flush()
            results=[]
            for proc in workers:
                out,err=proc.communicate(timeout=25);self.assertEqual(0,proc.returncode,err);results.append(json.loads(out))
            self.assertEqual(1,sum(r['committed'] for r in results))
            self.assertIn('CAS_CONFLICT',next(r['reason'] for r in results if not r['committed']))
            self.assertEqual(2,self.store.load(self.scope).revision)
            if os.environ.get('R20_ADMISSION_EVIDENCE'):
                from pathlib import Path
                Path(os.environ['R20_ADMISSION_EVIDENCE']).write_text(json.dumps(dict(scope=self.scope,
                    processIds=[p.pid for p in workers],results=results,accountingRevision=2,synthetic=True)),encoding='utf-8')
        finally:
            for proc in workers:
                if proc.poll() is None:proc.kill();proc.wait()

    def test_new_day_needs_inventory_reconciliation_and_keeps_recovery_block(self):
        self.activate();self.coordinator.reserve(self.signal(),'overnight')
        h=self.store.load(self.scope)
        blocked=replace(h.snapshot,daily=replace(h.snapshot.daily,operational_blocks=('RECOVERY_REQUIRED',)))
        h=self.store.append(blocked,'block',h.revision,h.hash)
        at=AT.replace(day=13,hour=4)
        p=replace(h.snapshot.profile,configuration_version=10,created_at=at,effective_from=at,effective_until=at.replace(day=14))
        newday=h.snapshot.daily.next_day(p,h.snapshot.daily.current_equity,at,boundary_verified=True)
        saved=replace(h.snapshot,profile=p,daily=newday)
        self.store.append(saved,'boundary',h.revision,h.hash)
        self.config.clock=lambda:at
        self.config.command('draft',dict(revision=3,requestId='day-draft',values=VALUES),'admin')
        self.config.command('validate',dict(revision=4,requestId='day-validate'),'admin')
        with self.assertRaisesRegex(ValueError,'CONFIGURATION_BLOCKED'):
            self.config.command('activate',dict(revision=5,requestId='day-activate'),'admin')
        self.assertEqual(('RECOVERY_REQUIRED',),self.store.load(self.scope).snapshot.daily.operational_blocks)
        self.assertEqual(1,len(self.store.load(self.scope).snapshot.daily.pending_terms))

if __name__=='__main__':unittest.main()
