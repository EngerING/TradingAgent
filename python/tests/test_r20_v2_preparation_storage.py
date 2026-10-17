import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from uuid import uuid4
from test_r20_v2_profiles import AT, profile
from test_r20_v2_persistence import snapshot
from test_r20_v2_configuration import context
from test_r20_v2_preparation import VALUES
from trading_agent.r20_configuration import ConfigurationService
from trading_agent.r20_preparation import PreparationService
from trading_agent.r20_persistence import TestStore
from trading_agent.r20_admission import RoleStore, AdmissionCoordinator

class PreparationStorageTests(unittest.TestCase):
    def setUp(self):
        self.db=os.environ['R20_V2_TEST_DATABASE'];self.system=os.environ['R20_V2_TEST_SYSTEM_ID']
        self.store=TestStore(self.db,self.system);self.store.install()
        self.scope='r20-v2-test-ledger-prep-'+uuid4().hex;self.p=profile(scope_id=self.scope)
        self.store.append(snapshot(self.p),'seed',0,'');self.c=context(self.scope)
        ConfigurationService(self.store,self.c).install()
        AdmissionCoordinator.install(self.store)
        PreparationService(self.store,self.c).install()
        self.s=PreparationService(RoleStore(self.db,self.system,'profile-admin'),self.c,lambda:AT)

    def save(self,values=VALUES,key=None,revision=0):
        return self.s.command('save',dict(values=values,requestId=key or uuid4().hex,revision=revision),'admin')

    def test_save_validate_restart_never_activates_or_changes_accounting(self):
        before=self.store.load(self.scope);first=self.save()
        self.assertEqual('GUARDADO',first['lifecycle'])
        self.s.command('validate',dict(revision=1,requestId='validate'),'admin')
        restarted=PreparationService(self.s.store,self.c,lambda:AT)
        self.assertEqual(self.s.view(),restarted.view())
        self.assertEqual('VALIDO',restarted.view()['status']);self.assertIsNone(restarted.view()['activeProfile'])
        self.assertFalse(restarted.view()['executionEnabled'])
        self.assertEqual(before,self.store.load(self.scope))
        self.assertEqual([],ConfigurationService(self.store,self.c).history())

    def test_unknowns_are_null_and_missing_limits_cannot_save(self):
        self.save()
        p=self.s.preview(VALUES)
        self.assertIsNone(p['assessment']);self.assertIsNone(p['confirmed_margin_usd'])
        self.assertIn('AGGREGATE_LEVERAGE_CAP_UNKNOWN',p['unknowns'])
        with self.assertRaises(ValueError):self.save(dict(VALUES,risk_per_trade_pct=''),revision=1)
        self.assertEqual(1,len(self.s.history()))

    def test_permissions_and_operational_actions_denied(self):
        for role in ('reader','shadow','paper'):
            s=PreparationService(RoleStore(self.db,self.system,role),self.c,lambda:AT)
            self.assertIsNone(s.view()['activeProfile'])
            with self.assertRaises(RuntimeError):s.command('save',dict(values=VALUES,revision=0,requestId=role),'admin')
        for action in ('activate','start','stop','switch'):
            with self.assertRaisesRegex(ValueError,'OPERATIONAL_CONTROL_DISABLED'):self.s.command(action,{},'admin')

    def test_idempotency_concurrency_immutable_and_paper_is_only_intent(self):
        first=self.save(dict(VALUES,environment='IBKR_PAPER'),key='once')
        self.assertEqual(first,self.save(dict(VALUES,environment='IBKR_PAPER'),key='once'))
        with self.assertRaisesRegex(ValueError,'IDEMPOTENCY'):self.save(key='once')
        def attempt(k):
            try:return self.save(key=k,revision=1)['revision']
            except (ValueError,RuntimeError) as exc:self.assertIn('CAS',str(exc));return None
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(attempt,['a','b']))
        self.assertEqual([2],[r for r in results if r is not None])
        with self.assertRaises(RuntimeError):self.store.execute('DELETE FROM r20_v2_config.preparations;')
        self.assertIsNone(self.s.view()['controls']['effectiveEnvironment'])

    def test_expiry_and_capital_change_do_not_reset_state(self):
        self.save();self.s.clock=lambda:AT.replace(day=13,hour=4)
        self.assertEqual('EXPIRED',self.s.view()['status'])
        with self.assertRaisesRegex(ValueError,'PROFILE_EXPIRED'):self.s.command('validate',dict(revision=1,requestId='late'),'admin')
        self.c['aggregate_leverage_cap']='5';self.s.clock=lambda:AT
        p=self.s.preview(dict(VALUES,logical_capital_usd='200'))
        self.assertIn('LOGICAL_CAPITAL_CONTEXT_MISMATCH',p['unknowns'])
        self.assertEqual('100',str(self.store.load(self.scope).snapshot.profile.capital_base_usd))

    def test_direct_sql_rejects_null_environment(self):
        from trading_agent.r20_profiles import digest, encoded
        from trading_agent.r20_persistence import sql_text
        row=self.save()
        row.update(revision=2,previous=row['hash'],requestId='null-environment',requestHash='a'*64)
        row['profile']['values']['environment']=None
        row['profile']['configuration_hash']=digest({k:v for k,v in row['profile'].items() if k!='configuration_hash'})
        row['hash']=digest({k:v for k,v in row.items() if k!='hash'})
        statement='SELECT r20_v2_config.append_preparation('+','.join((sql_text(self.scope),'1',sql_text(row['previous']),sql_text(row['requestId']),sql_text(row['requestHash']),sql_text(encoded(row))))+');'
        with self.assertRaisesRegex(RuntimeError,'PREPARATION_FIELDS'):self.s.store.execute(statement)
        self.assertEqual(1,len(self.s.history()))

    def test_preview_account_leverage_uses_eligible_equity_cap(self):
        from decimal import Decimal as D
        scope='r20-v2-test-ledger-prep-cap-'+uuid4().hex
        p=profile(scope_id=scope,equity_cap_usd=D('50'))
        self.store.append(snapshot(p),'seed-cap',0,'')
        c=context(scope);c.update(aggregate_leverage_cap='5',existing_exposure='100')
        service=PreparationService(self.s.store,c,lambda:AT)
        self.assertEqual('2',service.preview(VALUES)['account_leverage'])

if __name__=='__main__':unittest.main()
