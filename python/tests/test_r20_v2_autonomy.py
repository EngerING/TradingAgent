"""Synthetic integration only: explicit illustrative limits, no operative profile."""
from datetime import timedelta
from decimal import Decimal as D
from pathlib import Path
from uuid import uuid4
import unittest
from test_r20_v2_profiles import AT
import test_r20_v2_shadow as shadow_tests
from test_r20_v2_preparation import VALUES
from trading_agent.r20_configuration import ConfigurationService
from trading_agent.r20_preparation import PreparationService
from trading_agent.r20_shadow import ShadowCycle
from trading_agent.r20_shadow_plan import bind_preparation
from trading_agent.r20_runner import RunnerControl,ReplayRunner,source_manifest
from trading_agent.r20_profiles import digest,encoded
from trading_agent.r20_admission import RoleStore


class AutonomyTests(unittest.TestCase):
    quote=shadow_tests.ShadowTests.quote
    signal=shadow_tests.ShadowTests.signal
    activate=shadow_tests.ShadowTests.activate

    def setUp(self):
        shadow_tests.ShadowTests.setUp(self)
        self.ctx.update(aggregate_leverage_cap='5',liquidity_quantity='10')
        prep=PreparationService(self.store,self.ctx,lambda:AT);prep.install()
        # Values below are fixture limits, deliberately not the missing user choices.
        values=dict(VALUES,risk_per_trade_pct='20',daily_loss_limit_pct='20',max_open_positions='2')
        prep.command('save',dict(revision=0,requestId='save',values=values,purpose='TECHNICAL_VALIDATION'),'test-profile-admin')
        row=prep.command('validate',dict(revision=1,requestId='validate'),'test-profile-admin')
        self.ctx=bind_preparation(self.store,self.ctx,row['profile']['configuration_hash'],AT)
        self.config=ConfigurationService(self.store,self.ctx,lambda:AT)
        self.activate(dict(risk_per_trade_pct='20',capital_allocation_pct='100',max_leverage='5',daily_loss_limit_pct='20',max_open_positions='2'))
        self.cycle=ShadowCycle(self.store,self.ctx,lambda:AT)
        self.root=Path(__file__).resolve().parents[2]
        RunnerControl.install(self.store)
        self.control=RunnerControl(self.store,self.scope);self.control.preregister(source_manifest(self.root))

    def permit(self):
        self.cycle.provision_test_permission(self.store,self.scope,AT,AT+timedelta(hours=1),'explicit-test-owner',context=self.ctx)

    def runner(self):return ReplayRunner(self.cycle,self.control,self.root)

    def test_technical_full_cycle_and_sql_accept_bound_negative_target(self):
        self.permit()
        receipt=self.cycle.reserve(self.signal(),'r')
        self.assertLess(D(receipt['assessment']['net_target']),0)
        row=self.cycle.open('r',self.quote(),'open')
        self.assertFalse(row['positions'][0]['economically_viable'])
        self.assertEqual('TECHNICAL_VALIDATION',row['positions'][0]['purpose'])
        self.assertLessEqual(D(row['positions'][0]['sizing']['exposure']),400)
        q=self.quote('1.04',AT+timedelta(seconds=1));self.cycle.clock=lambda:q.at
        closed=self.cycle.observe(q,'close')
        self.assertEqual('TAKE_PROFIT',closed['trades'][0]['reason'])
        self.assertLess(D(closed['trades'][0]['net']),0)
        self.assertEqual(D('98.4'),self.store.load(self.scope).snapshot.daily.current_equity)

    def test_legacy_permission_cannot_authorize_technical_plan(self):
        self.cycle.provision_test_permission(self.store,self.scope,AT,AT+timedelta(hours=1),'legacy-owner')
        with self.assertRaisesRegex(ValueError,'BOUND_SHADOW_PERMISSION'):self.cycle.reserve(self.signal(),'r')

    def test_profile_admin_and_paper_cannot_issue_permission_or_reserve(self):
        for role in ('reader','profile-admin','paper','shadow'):
            store=RoleStore(self.store.database,self.store.system_id,role)
            with self.assertRaisesRegex(ValueError,'OWNER_SETUP_ONLY'):
                self.cycle.provision_test_permission(store,self.scope,AT,AT+timedelta(hours=1),'role',context=self.ctx)

    def test_changed_preparation_cannot_open_reserved_position(self):
        self.permit();self.cycle.reserve(self.signal(),'r')
        prep=PreparationService(self.store,self.ctx,lambda:AT)
        values=dict(VALUES,risk_per_trade_pct='20',daily_loss_limit_pct='20',max_open_positions='2')
        prep.command('save',dict(revision=2,requestId='changed',values=values),'profile-admin')
        with self.assertRaisesRegex(ValueError,'VALIDATED_PREPARATION'):self.cycle.open('r',self.quote(),'open')
        self.assertEqual([],self.cycle.inventory())

    def test_stop_preserves_open_inventory_until_valid_exit(self):
        self.permit();self.cycle.reserve(self.signal(),'r');self.cycle.open('r',self.quote(),'open')
        self.control.stop('test-operator')
        self.runner().step(self.quote(connected=False),'disconnected')
        self.assertEqual(1,len(self.cycle.inventory()))
        self.runner().step(self.quote('1.04'),'exit')
        self.assertEqual('STOPPED',self.runner().status()['status'])
        self.assertEqual(1,len(self.cycle.view()['trades']))

    def test_unknown_costs_remain_blocked_in_technical_mode(self):
        self.permit();self.ctx['cost_unknowns']=['SLIPPAGE_UNKNOWN']
        with self.assertRaises(ValueError):self.cycle.reserve(self.signal(),'r')

    def test_sql_rejects_forged_plan_even_with_valid_technical_receipt(self):
        from trading_agent.r20_persistence import sql_text
        self.permit();receipt=self.cycle.reserve(self.signal(),'r')
        profile=self.store.load(self.scope).snapshot.profile
        for changes in (dict(purpose='NORMAL'),dict(allocation_usd='9999'),dict(contextHash='0'*64),dict(preparationHash='1'*64)):
            forged=dict(receipt,executionPlan=dict(receipt['executionPlan'],**changes))
            with self.assertRaisesRegex(RuntimeError,'BOUND_SHADOW_PLAN_REQUIRED'):
                self.store.execute('SELECT r20_v2_admission.check_plan('+','.join((sql_text(self.scope),sql_text(encoded(forged))+'::jsonb',sql_text(profile.to_json())+'::jsonb',sql_text(AT.isoformat())+'::timestamptz'))+');')

    def test_preparation_change_racing_reserve_is_rejected_by_sql(self):
        self.permit();prep=PreparationService(self.store,self.ctx,lambda:AT)
        def change():
            v=dict(VALUES,risk_per_trade_pct='20',daily_loss_limit_pct='20',max_open_positions='2')
            prep.command('save',dict(revision=2,requestId='race',values=v),'profile-admin')
        with self.assertRaisesRegex(RuntimeError,'BOUND_SHADOW_PLAN_REQUIRED'):
            self.cycle.reserve(self.signal(),'r',before_commit=change)
        self.assertEqual((),self.store.load(self.scope).snapshot.daily.pending_terms)

    def test_recovery_releases_pending_without_manufacturing_entry(self):
        self.permit();self.cycle.reserve(self.signal(),'r')
        self.runner().step(self.quote(connected=False),'offline')
        self.assertEqual(1,len(self.store.load(self.scope).snapshot.daily.pending_terms))
        self.runner().step(self.quote(),'recover')
        self.assertEqual((),self.store.load(self.scope).snapshot.daily.pending_terms)
        self.assertEqual(D(100),self.store.load(self.scope).snapshot.daily.current_equity)
        self.assertEqual([],self.cycle.inventory())
        self.assertEqual([],self.cycle.view()['trades'])

    def test_runner_technical_signal_open_close_duplicate_and_projection(self):
        from trading_agent.r20_monitor import monitor
        self.permit()
        source=[]
        for i in range(70):
            c=D(2)-D(i)*D('.01')
            source.append(dict(opened_at=(AT-timedelta(hours=70-i)).isoformat(),minutes=60,
                open=str(c),high=str(c+D('.00005')),low=str(c-D('.00005')),close=str(c)))
        q=self.quote(str(c));runner=self.runner()
        opened=runner.step(q,'technical-entry',source,60)
        self.assertEqual('OPEN',opened['kind'],opened.get('reason'))
        p=opened['positions'][0]
        runner.step(q,'duplicate-signal',source,60)
        self.assertTrue(any('SIGNAL_ALREADY_RESERVED' in (r['reason'] or '') for r in self.cycle.history()))
        end=self.quote(p['target'],AT+timedelta(seconds=1),bid=D(p['target']),ask=D(p['target']))
        self.cycle.clock=lambda:end.at
        runner.step(end,'technical-close')
        recovered=ShadowCycle(self.store,self.ctx,lambda:end.at)
        view=monitor(self.store,self.ctx)
        self.assertEqual(recovered.view()['equity'],view['equity'])
        self.assertEqual(1,len(view['trades']))
        self.assertLess(D(view['trades'][0]['net']),0)
        self.assertEqual(1,sum(r['kind']=='OPEN' for r in recovered.history()))
        import os
        if os.environ.get('R20_AUTONOMY_EVIDENCE'):
            target=Path(os.environ['R20_AUTONOMY_EVIDENCE']);target.mkdir(parents=True,exist_ok=True)
            (target/'cycle.json').write_text(encoded(dict(context=self.ctx,opening=opened,monitor=view,history=recovered.history())),encoding='utf-8')

    def test_read_only_observer_never_calls_cycle_and_does_not_relabel(self):
        from trading_agent.r20_runner import ReadOnlyObserver
        class Source:
            def __init__(self):self.calls=0
            def poll(self):
                self.calls+=1
                if self.calls==1:raise ConnectionError('test-disconnect')
                return {'source':'IBKR_PAPER'},{'entryEligible':False,'source_timestamp':None}
        source=Source();reader=ReadOnlyObserver(self.root,source=source)
        self.assertEqual('DATA_UNAVAILABLE',reader.poll()['status'])
        self.assertEqual('IBKR_PAPER',reader.poll()['source']['source'])
        self.assertEqual(1,self.store.load(self.scope).revision)
