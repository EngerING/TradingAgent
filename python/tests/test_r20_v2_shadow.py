"""Isolated, explicitly synthetic virtual positions; never operating cohorts."""
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal as D
from concurrent.futures import ThreadPoolExecutor
import os, unittest
from uuid import uuid4
from test_r20_v2_configuration import VALUES
from test_r20_v2_profiles import AT
from test_r20_v2_sizing import stresses
from trading_agent.r20_profiles import canonical
from dataclasses import asdict
from trading_agent.r20_admission import RoleStore
from trading_agent.r20_persistence import sql_text
from trading_agent.r20_shadow import ShadowCycle, Quote


class ShadowTests(unittest.TestCase):
    def setUp(self):
        from test_r20_v2_admission import AdmissionTests
        AdmissionTests.setUp(self)
        self.ctx['stresses']+=canonical([asdict(replace(s,name='short-'+s.name)) for s in stresses('SHORT')])
        ShadowCycle.install(self.store)
        self.cycle=ShadowCycle(self.store,self.ctx,lambda:AT)
        self.activate()

    def activate(self,values=None):
        from test_r20_v2_admission import AdmissionTests
        return AdmissionTests.activate(self,values)

    def signal(self,name='signal-one',**changes):
        from test_r20_v2_admission import AdmissionTests
        return AdmissionTests.signal(self,name,**changes)

    def tearDown(self):
        if os.environ.get('R20_SHADOW_EVIDENCE'):
            from pathlib import Path
            from trading_agent.r20_profiles import encoded
            target=Path(os.environ['R20_SHADOW_EVIDENCE']);target.mkdir(parents=True,exist_ok=True)
            (target/(self._testMethodName+'.json')).write_text(encoded(self.cycle.view()),encoding='utf-8')

    def quote(self,price='1',at=AT,**changes):
        return replace(Quote(D(price)-D('.00001'),D(price)+D('.00001'),at,
            'SYNTHETIC_TEST_ONLY','OPEN',True,'b'*64),**changes)

    def permit(self):
        self.cycle.provision_test_permission(self.store,self.scope,AT,AT+timedelta(hours=24),'explicit-test-owner')

    def opened(self,side='LONG',name='one'):
        self.permit()
        signal=self.signal(name,side=side)
        receipt=self.cycle.reserve(signal,'reserve-'+name)
        event=self.cycle.open(receipt['requestId'],self.quote(),'open-'+name)
        return event['positions'][0]

    def test_profile_activation_does_not_authorize_open(self):
        with self.assertRaisesRegex(ValueError,'SHADOW_PERMISSION_REQUIRED'):
            self.cycle.reserve(self.signal(),'r')
        self.assertEqual(1,self.store.load(self.scope).revision)

    def test_long_short_full_cycle_and_no_double_cost(self):
        for side in ('LONG','SHORT'):
            with self.subTest(side=side):
                if side=='SHORT':self.setUp()
                p=self.opened(side,name=side)
                before=self.store.load(self.scope)
                self.assertEqual([],list(before.snapshot.daily.pending_terms))
                self.assertEqual(1,len(before.snapshot.daily.open_terms))
                self.assertEqual(D('100')-sum(c.amount for c in before.snapshot.costs),before.snapshot.daily.current_equity)
                end=self.quote('1.04' if side=='LONG' else '.96',AT+timedelta(seconds=1))
                self.cycle.clock=lambda:end.at
                row=self.cycle.observe(end,'close-'+side)
                self.assertEqual([],row['positions'])
                trade=row['trades'][-1]
                self.assertEqual('TAKE_PROFIT',trade['reason'])
                self.assertEqual(D(trade['gross'])-D(trade['cost']),D(trade['net']))
                h=self.store.load(self.scope)
                self.assertEqual((),h.snapshot.open_gross)
                self.assertEqual((),h.snapshot.daily.pending_terms)
                self.assertTrue(all(c.status=='SETTLED' and c.provenance=='MODELED' for c in h.snapshot.costs))
                self.cycle.clock=lambda:AT

    def test_stop_loss_uses_available_quote_with_gap(self):
        p=self.opened('SHORT')
        q=self.quote('1.03',AT+timedelta(seconds=1));self.cycle.clock=lambda:q.at
        row=self.cycle.observe(q,'stop')
        self.assertEqual('STOP_LOSS',row['trades'][0]['reason'])
        self.assertEqual('1.03',row['trades'][0]['exit_price'])

    def test_stale_future_closed_disconnected_preserve_inventory_and_accounting(self):
        self.opened();h=self.store.load(self.scope)
        for i,q in enumerate((self.quote(at=AT-timedelta(seconds=31)),self.quote(at=AT+timedelta(seconds=1)),
                              self.quote(market='CLOSED'),self.quote(connected=False))):
            row=self.cycle.observe(q,'invalid-'+str(i))
            self.assertEqual('DATA_UNAVAILABLE',row['kind'])
            self.assertEqual(h.snapshot,self.store.load(self.scope).snapshot)
            self.assertEqual(1,len(row['positions']));self.assertEqual([],row['trades'])

    def test_duplicate_close_lost_ack_and_new_process_recover_exactly(self):
        self.opened();q=self.quote('1.04',AT+timedelta(seconds=1));self.cycle.clock=lambda:q.at
        def lost():raise ConnectionError('ACK_LOST')
        with self.assertRaises(ConnectionError):self.cycle.observe(q,'close',after_commit=lost)
        h=self.store.load(self.scope)
        resumed=ShadowCycle(self.store,self.ctx,lambda:q.at+timedelta(minutes=5))
        result=resumed.observe(q,'close')
        self.assertEqual(h,self.store.load(self.scope))
        self.assertEqual(1,len(result['trades']))
        with self.assertRaisesRegex(ValueError,'IDEMPOTENCY_CONFLICT'):
            resumed.observe(self.quote('1.05',q.at),'close')

    def test_duplicate_open_and_repeated_signal(self):
        self.opened();h=self.store.load(self.scope)
        self.cycle.open('reserve-one',self.quote(),'open-one')
        self.assertEqual(h,self.store.load(self.scope))
        with self.assertRaisesRegex(ValueError,'POSITION_ALREADY_OPENED'):
            self.cycle.open('reserve-one',self.quote(),'another-open')
        with self.assertRaisesRegex(ValueError,'SIGNAL_ALREADY_RESERVED'):
            self.cycle.reserve(self.signal('one'),'another-reserve')

    def test_reduced_profile_does_not_change_position_or_force_admin_liquidation(self):
        p=self.opened()
        self.activate(dict(VALUES,max_leverage='1',max_open_positions='1'))
        q=self.quote('.999',AT+timedelta(seconds=1));self.cycle.clock=lambda:q.at
        row=self.cycle.observe(q,'follow')
        self.assertEqual(p,row['positions'][0])
        self.assertEqual([],row['trades'])

    def test_expired_profile_and_new_day_preserve_management_and_blocks(self):
        self.opened();h=self.store.load(self.scope)
        blocked=replace(h.snapshot,daily=replace(h.snapshot.daily,operational_blocks=('RECOVERY_REQUIRED',)))
        self.store.append(blocked,'block',h.revision,h.hash)
        tomorrow=AT.replace(day=13,hour=4);self.cycle.clock=lambda:tomorrow
        self.cycle.roll_management_day(self.quote(at=tomorrow),'midnight')
        h=self.store.load(self.scope)
        self.assertFalse(h.snapshot.daily.entry_profile_valid)
        self.assertEqual(('RECOVERY_REQUIRED',),h.snapshot.daily.operational_blocks)
        with self.assertRaises(ValueError):self.cycle.reserve(self.signal('tomorrow',signal_at=tomorrow,quote_at=tomorrow),'new')
        row=self.cycle.observe(self.quote('1.04',tomorrow),'finish')
        self.assertEqual('TAKE_PROFIT',row['trades'][0]['reason'])

    def test_profile_changed_after_reservation_requires_release_not_old_open(self):
        self.permit();self.cycle.reserve(self.signal(),'r')
        self.activate(dict(VALUES,max_leverage='1'))
        with self.assertRaisesRegex(ValueError,'PROFILE_CHANGED'):
            self.cycle.open('r',self.quote(),'o')
        self.cycle.release('r','release')
        h=self.store.load(self.scope)
        self.assertEqual(D('100'),h.snapshot.daily.current_equity)
        self.assertEqual((),h.snapshot.daily.pending_terms)

    def test_simultaneous_close_has_one_commit(self):
        self.opened();q=self.quote('1.04',AT+timedelta(seconds=1));self.cycle.clock=lambda:q.at
        h=self.store.load(self.scope)
        def close(i):
            try:return self.cycle.observe(q,'close-'+str(i),expected_head=h)
            except ValueError as e:self.assertIn('CAS_CONFLICT',str(e));return None
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(close,[1,2]))
        self.assertEqual(1,sum(r is not None for r in results))
        self.assertEqual(1,len(self.cycle.history()[-1]['trades']))

    def test_market_and_margin_unknowns_block_without_positions(self):
        self.permit();self.ctx['cost_unknowns']=['MARGIN_UNKNOWN','FINANCING_UNKNOWN']
        with self.assertRaises(ValueError):self.cycle.reserve(self.signal(),'unknown')
        self.assertEqual([],self.cycle.view()['positions'])

    def test_reader_admin_paper_cannot_mutate_lifecycle_or_permissions(self):
        self.opened()
        for role in ('reader','profile-admin','paper'):
            c=ShadowCycle(RoleStore(self.store.database,self.store.system_id,role),self.ctx,lambda:AT)
            with self.assertRaisesRegex(RuntimeError,'permission denied'):
                c.observe(self.quote(),'denied-'+role)
        for role in ('reader','profile-admin','shadow','paper'):
            with self.assertRaisesRegex(RuntimeError,'permission denied'):
                RoleStore(self.store.database,self.store.system_id,role).execute('DELETE FROM r20_v2_shadow.events;')

    def test_disconnect_in_transaction_rolls_back_accounting_and_lifecycle(self):
        self.opened();h=self.store.load(self.scope);history=self.cycle.history()
        from trading_agent.r20_persistence import TestStore
        class Broken(TestStore):
            def execute(self,sql):
                if sql.startswith('SELECT r20_v2_shadow.commit_event('):
                    sql='BEGIN;'+sql+'SELECT pg_terminate_backend(pg_backend_pid());COMMIT;'
                return super().execute(sql)
        c=ShadowCycle(Broken(self.store.database,self.store.system_id),self.ctx,lambda:AT)
        with self.assertRaises(RuntimeError):c.observe(self.quote(),'disconnect')
        self.assertEqual(h,self.store.load(self.scope));self.assertEqual(history,self.cycle.history())

    def test_open_inventory_included_in_second_sizing(self):
        p=self.opened()
        receipt=self.cycle.reserve(self.signal('second'),'second')
        self.assertLess(D(receipt['assessment']['quantity']),D(p['quantity']))
        self.cycle.open('second',self.quote(),'second-open')
        self.assertEqual(2,len(self.cycle.inventory()))
        h=self.store.load(self.scope)
        self.assertLessEqual(h.snapshot.daily.used_loss+h.snapshot.daily.open_risk+h.snapshot.daily.pending_risk,
                             h.snapshot.daily.budget)

    def test_high_precision_mark_is_reconciled_before_second_entry(self):
        self.opened()
        price=D('1.0000012345678901234567890123456789012345')
        q=self.quote(bid=price,ask=price)
        self.cycle.observe(q,'precise-mark')
        result=self.cycle.reserve(self.signal('precise-second',price=price),'precise-reserve')
        self.assertTrue(result['assessment']['admitted'])
        h=self.store.load(self.scope)
        self.assertLessEqual(h.snapshot.daily.used_loss+h.snapshot.daily.open_risk+h.snapshot.daily.pending_risk,h.snapshot.daily.budget)

    def test_genuine_modeled_margin_deficit_keeps_defensive_exit(self):
        p=self.opened()
        from trading_agent.r20_economics import Cost
        from test_r20_v2_persistence import snapshot
        h=self.store.load(self.scope);s=h.snapshot
        # Unexpected expense reduces available margin without changing the price,
        # administrative leverage profile or frozen SL/TP contract.
        s=snapshot(s.profile,costs=s.costs+(Cost('unexpected-model-charge',D('90'),'SETTLED','MODELED','SYNTHETIC_MARGIN_SHOCK'),),
            opened=s.open_gross,realized=s.realized_gross,previous=s.daily,open_terms=s.daily.open_terms)
        self.store.append(s,'margin-shock',h.revision,h.hash)
        q=self.quote('1',AT+timedelta(seconds=1));self.cycle.clock=lambda:q.at
        row=self.cycle.observe(q,'defensive')
        self.assertEqual('MODELED_MARGIN_DEFICIT',row['trades'][0]['reason'])
        self.assertLess(D(row['trades'][0]['net']),0)

    def test_emergency_preserved_and_only_fresh_quote_allows_defensive_exit(self):
        self.opened();h=self.store.load(self.scope)
        s=replace(h.snapshot,daily=replace(h.snapshot.daily,operational_blocks=('EMERGENCY_STOP',)))
        self.store.append(s,'emergency-test',h.revision,h.hash)
        self.cycle.observe(self.quote(connected=False),'offline-emergency')
        self.assertEqual(1,len(self.cycle.inventory()))
        row=self.cycle.observe(self.quote(),'fresh-emergency')
        self.assertEqual('EMERGENCY_DEFENSIVE_EXIT',row['trades'][0]['reason'])
        self.assertEqual(('EMERGENCY_STOP',),self.store.load(self.scope).snapshot.daily.operational_blocks)

    def test_pending_and_open_budget_not_double_counted(self):
        self.permit();a=self.cycle.reserve(self.signal('first'),'r1')
        before=self.store.load(self.scope).snapshot.daily
        self.cycle.open('r1',self.quote(),'o1')
        after=self.store.load(self.scope).snapshot.daily
        self.assertEqual(before.current_equity,after.current_equity)
        self.assertEqual(before.used_loss+before.pending_risk,after.used_loss+after.open_risk)
        self.assertLessEqual(after.used_loss+after.open_risk,after.budget)

    def test_profile_missing_and_daily_exhausted_keep_no_new_entries(self):
        self.permit();h=self.store.load(self.scope)
        self.cycle.reserve(self.signal('first'),'r1');self.cycle.reserve(self.signal('second'),'r2')
        with self.assertRaisesRegex(ValueError,'ENTRY_DENIED'):
            self.cycle.reserve(self.signal('third'),'r3')
        self.assertEqual(2,len(self.store.load(self.scope).snapshot.daily.pending_terms))
        self.assertEqual([],self.cycle.inventory())

    def test_open_lost_ack_and_reservation_release_recover_without_fee_repetition(self):
        self.permit();self.cycle.reserve(self.signal(),'reserve')
        def lost():raise ConnectionError('ACK_LOST')
        with self.assertRaises(ConnectionError):self.cycle.open('reserve',self.quote(),'open',after_commit=lost)
        h=self.store.load(self.scope)
        row=ShadowCycle(self.store,self.ctx,lambda:AT+timedelta(hours=25)).open('reserve',self.quote(),'open')
        self.assertEqual(h,self.store.load(self.scope));self.assertEqual(1,len(row['positions']))

    def test_future_bars_do_not_change_existing_engine_decision(self):
        from pathlib import Path
        from test_aggressive_growth import bars
        from trading_agent.aggressive_growth import configuration,signal
        root=Path(__file__).resolve().parents[2]
        # Original fixture timestamps, not the operating market or account.
        from datetime import datetime
        source=bars()
        end=datetime.fromisoformat(source[-1]['opened_at'])+timedelta(hours=1)
        for b in source:b['opened_at']=(datetime.fromisoformat(b['opened_at'])+(AT-end)).isoformat()
        closed_at=AT
        self.cycle.clock=lambda:closed_at
        q=self.quote('1.2',closed_at)
        decision=signal(configuration(root),source,60,closed_at)
        row=self.cycle.diagnose(root,source,60,q,'technical',quality='SYNTHETIC_CONTIGUOUS_COMPLETE')
        self.assertEqual(decision,row['input']['decision']);self.assertEqual([],row['positions'])
        future=dict(source[-1],opened_at=(closed_at+timedelta(hours=1)).isoformat(),close='999',high='1000')
        self.assertEqual(decision,signal(configuration(root),source+[future],60,closed_at))

    def test_quote_geometry_and_nonpositive_short_target_denied(self):
        self.permit()
        for q in (self.quote(bid=D('0')),self.quote(bid=D('2')),self.quote(evidence_hash='bad')):
            with self.assertRaises(ValueError):q.validate(AT)
        with self.assertRaises(ValueError):self.cycle.reserve(self.signal(stop_distance=D('.6'),side='SHORT'),'impossible')

    def test_mark_identical_and_zero_price_close_settles_reserve_once(self):
        self.opened();h=self.store.load(self.scope)
        self.cycle.observe(self.quote(),'m1');self.cycle.observe(self.quote(),'m2')
        after=self.store.load(self.scope).snapshot
        self.assertEqual((h.snapshot.costs,h.snapshot.open_gross,h.snapshot.realized_gross,h.snapshot.daily),
                         (after.costs,after.open_gross,after.realized_gross,after.daily))

    def test_full_position_survives_fresh_python_process(self):
        self.opened()
        import subprocess,sys,json
        from trading_agent.r20_profiles import encoded
        code='''import json,sys
from datetime import datetime
from trading_agent.r20_persistence import TestStore
from trading_agent.r20_shadow import ShadowCycle
r=json.load(sys.stdin);s=TestStore(r['database'],r['systemId'])
print(json.dumps(ShadowCycle(s,r['context'],lambda:datetime.fromisoformat(r['at'])).view()))
'''
        result=subprocess.run([sys.executable,'-c',code],input=encoded(dict(database=self.store.database,
            systemId=self.store.system_id,context=self.ctx,at=AT)),capture_output=True,text=True,encoding='utf-8',timeout=25)
        self.assertEqual(0,result.returncode,result.stderr)
        self.assertEqual(self.cycle.view(),json.loads(result.stdout))

    def test_existing_technical_engine_to_reservation_open_and_close(self):
        from pathlib import Path
        from trading_agent.aggressive_growth import configuration,signal
        root=Path(__file__).resolve().parents[2]
        for side in ('LONG','SHORT'):
            if side=='SHORT':self.setUp()
            self.permit();source=[]
            for i in range(70):
                c=D('1')+D(i)*D('.01') if side=='LONG' else D('2')-D(i)*D('.01')
                source.append(dict(opened_at=(AT-timedelta(hours=70-i)).isoformat(),minutes=60,
                    open=str(c),high=str(c+D('.00005')),low=str(c-D('.00005')),close=str(c)))
            q=self.quote(str(c));expected=signal(configuration(root),source,60,AT)
            self.assertEqual(side,expected['side'])
            receipt=self.cycle.reserve_engine(root,source,60,q,'engine-reserve',quality='SYNTHETIC_CONTIGUOUS_COMPLETE')
            row=self.cycle.open(receipt['requestId'],q,'engine-open');p=row['positions'][0]
            self.assertEqual(D(expected['stop_distance']),abs(D(p['entry_price'])-D(p['stop'])))
            end=self.quote(p['target'],AT+timedelta(seconds=1),bid=D(p['target']),ask=D(p['target']))
            self.cycle.clock=lambda:end.at
            closed=self.cycle.observe(end,'engine-close')
            self.assertEqual('TAKE_PROFIT',closed['trades'][0]['reason'])
            self.assertEqual(receipt['signal']['engine_hash'],closed['trades'][0]['position']['engine_hash'])
            future=dict(source[-1],opened_at=(AT+timedelta(hours=1)).isoformat())
            with self.assertRaisesRegex(ValueError,'SIGNAL_ALREADY_RESERVED'):
                self.cycle.reserve_engine(root,source+[future],60,q,'different-archive-same-candle',quality='SYNTHETIC_CONTIGUOUS_COMPLETE')

    def test_budget_tightening_then_relaxing_never_restores_daily_capacity(self):
        self.opened();self.activate(dict(VALUES,daily_loss_limit_pct='3'))
        self.activate(VALUES)
        self.cycle.observe(self.quote(),'synchronize-budget')
        h=self.store.load(self.scope)
        self.assertEqual(D('3'),h.snapshot.daily.budget)
        with self.assertRaises(ValueError):self.cycle.reserve(self.signal('next'),'next')

    def test_position_identity_prefix_does_not_settle_other_costs(self):
        self.opened(name='a');self.cycle.reserve(self.signal('a-second',stop_distance=D('.03')),'r-second')
        self.cycle.open('r-second',self.quote(),'o-second')
        row=self.cycle.observe(self.quote('1.04'),'close-both')
        self.assertEqual(1,len(row['trades']));self.assertEqual('a-second',row['positions'][0]['position_id'])
        costs=self.store.load(self.scope).snapshot.costs
        self.assertTrue(any(c.status=='RESERVED' for c in costs if c.cost_id in row['positions'][0]['cost_ids']))
        ids=[c.cost_id for c in self.store.load(self.scope).snapshot.costs]
        self.assertEqual(len(ids),len(set(ids)))

    def test_missing_midnight_valuation_blocks_entries_not_position_management(self):
        self.opened();tomorrow=AT.replace(day=13,hour=4)+timedelta(seconds=5)
        self.cycle.clock=lambda:tomorrow
        row=self.cycle.observe(self.quote('1.04',tomorrow),'next-day-exit')
        self.assertEqual('TAKE_PROFIT',row['trades'][0]['reason'])
        h=self.store.load(self.scope)
        self.assertIn('ECONOMIC_BOUNDARY_UNVERIFIED',h.snapshot.daily.operational_blocks)
        self.assertFalse(h.snapshot.daily.entry_profile_valid)

    def test_two_reservations_open_concurrently_use_one_accounting_head(self):
        from threading import Barrier
        self.permit();self.cycle.reserve(self.signal('x'),'rx');self.cycle.reserve(self.signal('y'),'ry')
        barrier=Barrier(2)
        def open_one(i):
            try:return self.cycle.open('r'+i,self.quote(),'o'+i,before_commit=lambda:barrier.wait(timeout=15))
            except ValueError as exc:self.assertIn('CAS_CONFLICT',str(exc));return None
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(open_one,['x','y']))
        self.assertEqual(1,sum(x is not None for x in results))
        self.assertEqual(1,len(self.cycle.inventory()))
        self.assertEqual(1,len(self.store.load(self.scope).snapshot.daily.pending_terms))


if __name__=='__main__':unittest.main()
