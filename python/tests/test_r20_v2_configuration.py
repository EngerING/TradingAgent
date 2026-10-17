"""Configuration workflow only. Synthetic context; no runner or broker imports."""
from dataclasses import asdict,replace
from datetime import timedelta
from decimal import Decimal as D
import os
import unittest
from uuid import uuid4
from test_r20_v2_profiles import AT, profile
from test_r20_v2_persistence import snapshot
from test_r20_v2_sizing import costs,limits,stresses
from trading_agent.r20_configuration import ConfigurationService
from trading_agent.r20_persistence import TestStore
from trading_agent.r20_profiles import canonical

VALUES=dict(risk_per_trade_pct='20',capital_allocation_pct='50',max_leverage='5',daily_loss_limit_pct='20',max_open_positions='3')

def context(scope):
    return canonical(dict(scope=scope,classification='SYNTHETIC_TEST_ONLY',costs=asdict(costs()),
       limits=asdict(limits()),stresses=[asdict(s) for s in stresses()],side='LONG',price=D('1'),stop_distance=D('.02'),
       free_margin=D('100'),existing_exposure=D('0'),committed_margin=D('0'),liquidity_quantity=D('10000'),
       pending_costs=D('0'),cost_unknowns=[],evidence='ISOLATED_CONFIGURATION_TEST'))


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.store=TestStore(os.environ['R20_V2_TEST_DATABASE'],os.environ['R20_V2_TEST_SYSTEM_ID'])
        self.store.install()
        self.scope='r20-v2-test-ledger-config-'+uuid4().hex
        self.p=profile(scope_id=self.scope)
        self.store.append(snapshot(self.p),'seed',0,'')
        self.c=context(self.scope)
        self.s=ConfigurationService(self.store,self.c,lambda:AT)
        self.s.install()

    def command(self,action,revision=0,values=None,key=None):
        body=dict(revision=revision,requestId=key or uuid4().hex)
        if values is not None:body['values']=values
        return self.s.command(action,body,'test-admin')

    def test_draft_validation_preview_activation_is_config_only(self):
        self.assertEqual('BLOCKED',self.s.view()['status'])
        self.command('draft',values=VALUES)
        self.assertEqual('DRAFT',self.s.view()['lifecycle'])
        self.command('validate',1)
        self.assertEqual('VALIDATED',self.s.view()['lifecycle'])
        preview=self.s.preview(VALUES)
        self.assertTrue(preview['assessment']['admitted'])
        self.assertEqual(self.s.history()[-1]['profile']['configuration_hash'],preview['assessment']['profile_hash'])
        self.command('activate',2)
        v=self.s.view();self.assertEqual('ACTIVATED_FOR_SHADOW',v['status'])
        self.assertFalse(v['executionEnabled']);self.assertFalse(v['cohortStarted'])
        self.assertEqual(1,self.store.load(self.scope).revision)

    def test_missing_and_invalid_fields_never_validate(self):
        for key in VALUES:
            values=dict(VALUES);values.pop(key)
            self.assertIn('FIELDS_REQUIRED',self.s.preview(values)['blockers'])
        for key,value in [('max_leverage','0'),('risk_per_trade_pct','101'),('max_open_positions','1.5'),('capital_allocation_pct','NaN')]:
            self.assertTrue(self.s.preview(dict(VALUES,**{key:value}))['blockers'])
        self.command('draft',values={})
        with self.assertRaises(ValueError):self.command('validate',1)

    def test_unknown_costs_null_preview_and_activation_denied(self):
        self.s.context['cost_unknowns']=['SLIPPAGE_UNKNOWN','FINANCING_UNKNOWN']
        self.command('draft',values=VALUES);self.command('validate',1)
        self.assertIsNone(self.s.preview(VALUES)['assessment'])
        with self.assertRaisesRegex(ValueError,'CONFIGURATION_BLOCKED'):self.command('activate',2)

    def test_cas_idempotency_immutable_actor_and_hash(self):
        first=self.command('draft',values=VALUES,key='same')
        self.assertEqual(first,self.command('draft',values=VALUES,key='same'))
        with self.assertRaisesRegex(ValueError,'IDEMPOTENCY'):self.command('draft',values={},key='same')
        with self.assertRaisesRegex(ValueError,'CAS'):self.command('draft',values={})
        rows=self.s.history();self.assertEqual('test-admin',rows[0]['actor']);self.assertEqual(64,len(rows[0]['hash']))
        with self.assertRaises(RuntimeError):self.store.execute('DELETE FROM r20_v2_config.events;')

    def test_expiry_does_not_activate_previous_profile(self):
        self.command('draft',values=VALUES);self.command('validate',1);self.command('activate',2)
        self.s.clock=lambda:AT.replace(day=13,hour=4)
        v=self.s.view();self.assertEqual('EXPIRED',v['status']);self.assertIsNone(v['currentProfile'])

    def test_changes_preserve_open_inventory_and_daily_latch(self):
        from trading_agent.r20_economics import OpenRisk
        head=self.store.load(self.scope)
        loss=snapshot(self.p,opened=(('position',D('-25')),),open_terms=(OpenRisk('position',D('-25'),D('-30')),))
        self.store.append(loss,'loss',head.revision,head.hash)
        self.command('draft',values=dict(VALUES,daily_loss_limit_pct='100'));self.command('validate',1)
        with self.assertRaises(ValueError):self.command('activate',2)
        self.assertEqual(loss,self.store.load(self.scope).snapshot)
        self.assertTrue(self.s.view()['daily']['loss_blocked'])

    def test_new_draft_does_not_replace_active_profile(self):
        self.command('draft',values=VALUES);self.command('validate',1);self.command('activate',2)
        old=self.s.view()['currentProfile']
        self.command('draft',3,dict(VALUES,max_leverage='3'))
        self.assertEqual(old,self.s.view()['currentProfile'])

    def test_changed_context_requires_revalidation(self):
        self.command('draft',values=VALUES);self.command('validate',1)
        self.s.context['price']='1.01'
        with self.assertRaisesRegex(ValueError,'CONTEXT_CHANGED'):self.command('activate',2)

    def test_concurrent_writers_have_one_winner(self):
        from concurrent.futures import ThreadPoolExecutor
        def attempt(key):
            try:return self.command('draft',values=VALUES,key=key)['revision']
            except (ValueError,RuntimeError) as exc:
                self.assertIn('CAS_CONFLICT',str(exc));return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(attempt,['a','b']))
        self.assertEqual([1], [x for x in results if x is not None])
        self.assertEqual(1,len(self.s.history()))

    def test_restart_retains_configuration_and_accounting(self):
        self.command('draft',values=VALUES);self.command('validate',1);self.command('activate',2)
        restarted=ConfigurationService(self.store,self.c,lambda:AT)
        self.assertEqual(self.s.view(),restarted.view())

    def test_activated_lower_limit_remembers_crossing_after_equity_recovers(self):
        from trading_agent.r20_economics import OpenRisk
        self.command('draft',values=dict(VALUES,daily_loss_limit_pct='5'))
        self.command('validate',1);self.command('activate',2)
        h=self.store.load(self.scope)
        loss=snapshot(self.p,at=AT+timedelta(seconds=1),previous=h.snapshot.daily,
            opened=(('position',D('-6')),),open_terms=(OpenRisk('position',D('-6'),D('-8')),))
        h=self.store.append(loss,'crossed',h.revision,h.hash)
        recovered=snapshot(self.p,at=AT+timedelta(seconds=2),previous=h.snapshot.daily,
            opened=(('position',D('0')),),open_terms=(OpenRisk('position',D('0'),D('-2')),))
        self.store.append(recovered,'recovered',h.revision,h.hash)
        self.assertFalse(recovered.daily.loss_blocked)  # Original accounting ceiling is still 20.
        self.s.clock=lambda:AT+timedelta(seconds=3)
        self.assertTrue(self.s.view()['daily']['loss_blocked'])
        restarted=ConfigurationService(self.store,self.c,self.s.clock)
        self.assertEqual('BLOCKED',restarted.view()['status'])
        self.command('draft',3,dict(VALUES,daily_loss_limit_pct='100'));self.command('validate',4)
        with self.assertRaisesRegex(ValueError,'CONFIGURATION_BLOCKED'):self.command('activate',5)

if __name__=='__main__':unittest.main()
