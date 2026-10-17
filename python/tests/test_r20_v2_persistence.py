"""Synthetic accounting ledgers only, isolated PostgreSQL; never trading cohorts."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal as D
import os
import json
from pathlib import Path
import subprocess
import sys
import unittest
from uuid import uuid4

from test_r20_v2_profiles import AT, profile
from trading_agent.r20_economics import Cost, DailyState, OpenRisk, PendingRisk, equity
from trading_agent.r20_persistence import Snapshot, TestStore, sql_text


def snapshot(p=None, *, costs=(), opened=(), realized=D('0'), previous=None, at=AT,
             open_terms=(), pending_terms=()):
    p=p or profile(scope_id='r20-v2-test-ledger-unit')
    value=equity(p.capital_base_usd,realized,tuple(v for _,v in opened),costs).economic
    day=previous or DailyState.begin(p,D('100'),at,boundary_verified=True)
    day=day.observe(p,at,value,open_terms,pending_terms)
    return Snapshot(p,day,realized,opened,costs,'SYNTHETIC_ACCOUNTING_ONLY')


class SnapshotTests(unittest.TestCase):
    def test_roundtrip_exact_and_equity_consistency(self):
        s=snapshot(costs=(Cost('fee',D('2'),'RESERVED','ESTIMATED','test'),))
        self.assertEqual(s,Snapshot.from_json(s.to_json()))
        with self.assertRaisesRegex(ValueError,'EQUITY_MISMATCH'):
            replace(s,daily=replace(s.daily,current_equity=D('100')))

    def test_duplicate_pnl_or_cost_ids_rejected(self):
        with self.assertRaises(ValueError): snapshot(opened=(('p1',D('1')),('p1',D('1'))))
        c=Cost('fee',D('2'),'RESERVED','ESTIMATED','test')
        with self.assertRaises(ValueError): snapshot(costs=(c,c))

    def test_target_guard_before_connection(self):
        for database in ('postgres','r20_v2_test_x',"bad'; DROP DATABASE postgres;"):
            with self.assertRaisesRegex(ValueError,'ISOLATED_TEST_TARGET'):
                TestStore(database,'7692346685552779632')
        with self.assertRaises(ValueError): TestStore('r20_v2_test_'+'a'*32,'7692664583620497868')


class PersistenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Deliberately fail, never silently skip the integration contract.
        cls.store=TestStore(os.environ['R20_V2_TEST_DATABASE'],os.environ['R20_V2_TEST_SYSTEM_ID'])
        cls.store.install()
        cls.evidence=[]

    @classmethod
    def tearDownClass(cls):
        destination=os.environ.get('R20_V2_PERSISTENCE_EVIDENCE')
        if destination:
            Path(destination).write_text(json.dumps(dict(database=cls.store.database,port=55432,
                system_id=cls.store.system_id,synthetic_accounting_only=True,cohorts_created=0,
                records=cls.evidence),indent=2),encoding='utf-8')

    def setUp(self):
        self.p=profile(scope_id='r20-v2-test-ledger-'+uuid4().hex)
        self.s=snapshot(self.p)

    def tearDown(self):
        record=dict(test=self.id(),scope=self.p.scope_id)
        try:
            h=self.store.load(self.p.scope_id)
            record.update(revision=h.revision if h else 0,hash=h.hash if h else None,integrity=True)
        except ValueError as exc:
            record.update(integrity=False,reason=str(exc),intentional_corruption='hash_corruption' in self.id())
        self.evidence.append(record)

    def append(self,s=None,key='first',rev=0,previous=''):
        return self.store.append(s or self.s,key,rev,previous)

    def test_restart_preserves_profile_equity_reserves_and_block(self):
        c=Cost('fee',D('2'),'RESERVED','ESTIMATED','test')
        s=snapshot(self.p,costs=(c,),opened=(('p1',D('-25')),),
                   open_terms=(OpenRisk('p1',D('-27'),D('-30')),))
        s=replace(s,daily=replace(s.daily,operational_blocks=('EMERGENCY_STOP',)))
        receipt=self.append(s)
        reload=TestStore(self.store.database,self.store.system_id).load(self.p.scope_id)
        self.assertEqual(s,reload.snapshot); self.assertEqual(receipt.hash,reload.hash)
        self.assertTrue(reload.snapshot.daily.loss_blocked)
        self.assertEqual(D('30'),reload.snapshot.daily.used_loss+reload.snapshot.daily.open_risk)

    def test_idempotent_lost_response_retry_does_not_append(self):
        self.append()  # Simulate caller losing this successful return value.
        retry=self.append()
        self.assertEqual(1,retry.revision)
        self.assertEqual(1,self.store.load(self.p.scope_id).revision)
        with self.assertRaisesRegex(ValueError,'IDEMPOTENCY_CONFLICT'):
            self.append(replace(self.s,evidence='different'))
        h=self.store.load(self.p.scope_id)
        self.append(key='second',rev=h.revision,previous=h.hash)
        self.assertEqual(1,self.append().revision)
        self.assertEqual(2,self.store.load(self.p.scope_id).revision)

    def test_recovery_from_fresh_os_process(self):
        h=self.append()
        code=('import os; from trading_agent.r20_persistence import TestStore; '
              's=TestStore(os.environ["R20_V2_TEST_DATABASE"],os.environ["R20_V2_TEST_SYSTEM_ID"]); '
              f'print(s.load("{self.p.scope_id}").hash)')
        result=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,check=True,timeout=30)
        self.assertEqual(h.hash,result.stdout.strip())

    def test_two_writers_same_head_exactly_one_wins(self):
        h=self.append()
        def commit(key):
            try: return self.append(key=key,rev=h.revision,previous=h.hash).revision
            except (ValueError,RuntimeError): return 'CONFLICT'
        with ThreadPoolExecutor(2) as pool: values=list(pool.map(commit,('a','b')))
        self.assertEqual(1,values.count(2)); self.assertEqual(1,values.count('CONFLICT'))
        self.assertEqual(2,self.store.load(self.p.scope_id).revision)

    def test_same_request_concurrent_only_one_event(self):
        with ThreadPoolExecutor(2) as pool: values=list(pool.map(lambda _:self.append(),range(2)))
        self.assertEqual(values[0],values[1]); self.assertEqual(1,values[0].revision)

    def test_profile_version_immutable_and_intraday_latch(self):
        loss=snapshot(self.p,realized=D('-21'))
        h=self.append(loss)
        changed=replace(self.p,configuration_version=2,daily_loss_limit_pct=D('50'))
        after=snapshot(changed,realized=D('10'),previous=loss.daily,at=AT+timedelta(seconds=1))
        h=self.append(after,'profile-2',h.revision,h.hash)
        self.assertTrue(h.snapshot.daily.loss_blocked); self.assertEqual(D('20'),h.snapshot.daily.budget)
        forged=replace(after,daily=replace(after.daily,loss_blocked=False))
        with self.assertRaisesRegex(ValueError,'DAILY_TRANSITION'):
            self.append(forged,'unlock',h.revision,h.hash)
        changed_again=replace(changed,max_leverage=D('6'))
        with self.assertRaises(ValueError):
            self.append(snapshot(changed_again),'reuse',h.revision,h.hash)

    def test_new_day_preserves_operational_blocks_and_reservations(self):
        s=replace(self.s,daily=replace(self.s.daily,operational_blocks=('EMERGENCY_STOP','UNCERTAIN_ORDER'),
                                      pending_terms=(PendingRisk('pending',D('5')),)))
        h=self.append(s)
        at=AT.replace(day=13,hour=4)
        p=replace(self.p,configuration_version=2,effective_from=at,effective_until=at+timedelta(days=1),created_at=at)
        day=s.daily.next_day(p,D('100'),at,boundary_verified=True)
        new=Snapshot(p,day,D('0'),(),(),s.evidence)
        h=self.append(new,'next-day',h.revision,h.hash)
        self.assertFalse(h.snapshot.daily.can_enter(D('1')))
        with self.assertRaisesRegex(ValueError,'OPERATIONAL_BLOCK_REMOVED'):
            self.append(replace(new,daily=replace(day,operational_blocks=())),'clear',h.revision,h.hash)

    def test_fee_reserve_accrual_settlement_no_double_deduction(self):
        h=None
        for i,(status,provenance) in enumerate((('RESERVED','ESTIMATED'),('ACCRUED','BROKER_CONFIRMED'),('SETTLED','BROKER_CONFIRMED'))):
            c=Cost('same-charge',D('2'),status,provenance,'SYNTHETIC_BROKER_REPORT')
            s=snapshot(self.p,costs=(c,),previous=h.snapshot.daily if h else None,at=AT+timedelta(seconds=i))
            h=self.append(s,'fee-'+str(i),h.revision if h else 0,h.hash if h else '')
            self.assertEqual(D('98'),h.snapshot.daily.current_equity)
        with self.assertRaisesRegex(ValueError,'COST_HISTORY'):
            self.append(snapshot(self.p,previous=h.snapshot.daily,at=AT+timedelta(seconds=4)),
                        'erase-fee',h.revision,h.hash)

    def test_atomic_rollback_and_append_only(self):
        h=self.append()
        for statement in ('DELETE FROM r20_v2_test.events','UPDATE r20_v2_test.events SET previous_hash=\'bad\'',
                          'TRUNCATE r20_v2_test.events','DELETE FROM r20_v2_test.profiles'):
            with self.assertRaises(RuntimeError): self.store.execute(statement)
        self.assertEqual(h,self.store.load(self.p.scope_id))
        with self.assertRaises(RuntimeError):
            self.store.execute('BEGIN; INSERT INTO r20_v2_test.profiles VALUES (\'bad\',1,\'bad\',\'{}\'); SELECT 1/0; COMMIT;')
        self.assertEqual('0',self.store.execute("SELECT count(*) FROM r20_v2_test.profiles WHERE scope_id='bad'"))

    def test_reject_rewind_and_wrong_previous_without_side_effect(self):
        h=self.append()
        with self.assertRaisesRegex(ValueError,'CAS_CONFLICT'):
            self.append(key='wrong',rev=1,previous='0'*64)
        later=snapshot(self.p,previous=self.s.daily,at=AT+timedelta(seconds=1))
        h=self.append(later,'later',h.revision,h.hash)
        s=self.s
        with self.assertRaises(ValueError): self.append(s,'rewind',h.revision,h.hash)
        self.assertEqual(h,self.store.load(self.p.scope_id))

    def test_database_rejects_direct_latch_reset_and_equity_tampering(self):
        loss=snapshot(self.p,realized=D('-21'))
        h=self.append(loss)
        recovered=snapshot(self.p,previous=loss.daily,realized=D('0'),at=AT+timedelta(seconds=1))
        self.assertTrue(recovered.daily.loss_blocked)
        forged=replace(recovered,daily=replace(recovered.daily,loss_blocked=False))
        def raw(body,key):
            return self.store.execute('SELECT r20_v2_test.append_state('+','.join((
                sql_text(self.p.scope_id),sql_text(key),'1',sql_text(h.hash),'1',
                sql_text(self.p.configuration_hash),sql_text(self.p.to_json()),sql_text(body)))+');')
        with self.assertRaises(RuntimeError): raw(forged.to_json(),'unlock-direct')
        with self.assertRaises(RuntimeError):
            raw(recovered.to_json().replace('"realized_gross":"0"','"realized_gross":"99"'),'fake-equity')
        self.assertEqual(h,self.store.load(self.p.scope_id))

    def test_simultaneous_positions_pending_and_profile_change(self):
        costs=(Cost('entry1',D('2'),'SETTLED','MODELED','test'),
               Cost('exit1',D('2'),'RESERVED','ESTIMATED','test'),
               Cost('exit2',D('2'),'RESERVED','ESTIMATED','test'))
        s=snapshot(self.p,costs=costs,opened=(('p1',D('-3')),('p2',D('1'))),
                   open_terms=(OpenRisk('p1',D('-5'),D('-8')),OpenRisk('p2',D('-1'),D('-5'))),
                   pending_terms=(PendingRisk('candidate',D('4')),))
        h=self.append(s)
        d=self.store.load(self.p.scope_id).snapshot.daily
        self.assertEqual(D('92'),d.current_equity)
        self.assertEqual(D('19'),d.used_loss+d.open_risk+d.pending_risk)
        self.assertTrue(d.can_enter(D('1'))); self.assertFalse(d.can_enter(D('1.01')))
        p=replace(self.p,configuration_version=2,daily_loss_limit_pct=D('50'))
        new=snapshot(p,costs=costs,opened=s.open_gross,previous=d,at=AT+timedelta(seconds=1),
                     open_terms=d.open_terms,pending_terms=d.pending_terms)
        h=self.append(new,'profile',h.revision,h.hash)
        self.assertEqual(D('1'),h.snapshot.daily.remaining)

    def test_hash_corruption_detected_even_if_admin_bypasses_trigger(self):
        h=self.append()
        # Destructive fault injection ONLY in this disposable test ledger/database.
        self.store.execute("BEGIN; SET LOCAL session_replication_role=replica; "
            f"UPDATE r20_v2_test.events SET event_hash=repeat('0',64) WHERE scope_id='{self.p.scope_id}'; COMMIT;")
        with self.assertRaisesRegex(ValueError,'CHAIN_INTEGRITY'):
            self.store.load(self.p.scope_id)


if __name__=='__main__': unittest.main()
