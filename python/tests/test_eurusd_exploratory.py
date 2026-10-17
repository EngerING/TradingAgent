from copy import deepcopy
from datetime import datetime,timedelta,timezone
import json
import unittest
from unittest.mock import Mock,patch
from trading_agent.eurusd_exploratory import Rotator,BASELINE_VERSION,PROFILES,sha,encoded
from trading_agent.eurusd_exploratory_projection import overlay

AT=datetime(2026,10,7,15,tzinfo=timezone.utc)
class Memory:
    cohort='eurusd-explore-'+'a'*32
    def __init__(self):self.h=dict(revision=0,hash='',payload=None)
    def load(self):return deepcopy(self.h)
    def commit(self,revision,previous,data):
        if revision!=self.h['revision']+1 or previous!=self.h['hash']:raise RuntimeError('CAS_CONFLICT')
        self.h=dict(revision=revision,hash=sha([revision,data,previous]),payload=encoded(data).decode());return self.load()

class ExploratoryTests(unittest.TestCase):
    def setUp(self):
        self.at=AT;self.j=Memory();self.r=Rotator(self.j,lambda:self.at)
        self.r.prepare(dict(strategy_version=BASELINE_VERSION,version=1,strategy_id='trend'),
            dict(openingCommission='0.05',closingCommission='0.05',spread='0.0001',slippage='0.00005',adverseGap='0.0001',minimumQuantity='0.01',quantityStep='0.01'),{},'binding',{})
        # Existing historical cohort compatibility; new supervised v2 has separate tests.
        self.r.state['protocol']['protocol_version']=1;self.r.state['protocol']['rotation_policy']='CLOSED_ONLY'
        self.r.append('LEGACY_FIXTURE')
        self.signal=dict(strategy_version=BASELINE_VERSION,strategy_id='trend',side='BUY',reasons=[],opportunity_id='s1',
            signal_at=AT.isoformat(),entry_at=AT.isoformat(),entry_midpoint='1.1',stop_distance='0.01',take_profit_distance='0.02')
        self.quote=dict(bid='1.0999',ask='1.1',at=AT.isoformat(),type='LIVE',market_status='OPEN',available_for_execution=True)
        self.e={k:'VERIFIED' for k in ('identity','account_reconciled','positions_flat','orders_clear','journal_reconciled','permissions','margin','settled_funds','minimum_size','fees_bounded','protection','calendar','old_incident_resolved')}
        self.e.update(minimum_quantity='0.01',quantity_increment='0.01',margin_required_usd='0',settled_usd='100')
    def begin(self):
        send=Mock();d=self.r.begin(self.signal,self.quote,self.e,dict(session_id='newgrant'),False,1+3*len(self.r.state['trials']),send)
        self.assertTrue(d['admitted'],d);self.assertEqual(1,send.call_count);return self.r.state['active']
    def fill(self,t,side='BUY',q=None,price=None,exec_id='e1',oid=None):
        oid=oid or t['order_ids'][0 if side=='BUY' else 1]
        return dict(kind='fill',exec_id=exec_id,order_id=oid,perm_id=100+oid,client_id=82,contract_id=12087792,side=side,
            quantity=q or t['quantity'],price=price or ('1.1' if side=='BUY' else '1.12'),at=self.at.isoformat(),broker_at=self.at.isoformat())
    def fee(self,exec_id,amount='0.05'):return dict(kind='commission',exec_id=exec_id,amount=amount,currency='USD',at=self.at.isoformat())
    def snapshot(self,quantity='0',orders=None):
        cash=dict(query_status='COMPLETE',account_ready=True,errors=[],value=quantity,base_currency='USD',completed_sources=['ACCOUNT_UPDATES','ACCOUNT_UPDATES_MULTI','SUMMARY_1','SUMMARY_2'],expected_sources=['ACCOUNT_UPDATES','ACCOUNT_UPDATES_MULTI','SUMMARY_1','SUMMARY_2'])
        pos=[dict(contract_id=12087792,security_type='CASH',currency='USD',quantity=quantity)] if quantity!='0' else []
        return (dict(events=[],exposure_reads_complete=True,cash_reconciliation=cash,eur_cash=quantity,foreign_positions=[],foreign_currency_balances=[],positions=pos,portfolio=pos,orders=orders or [],received_at=self.at.isoformat()),
                dict(status='COMPLETE',errors=[],positions=pos,received_at=self.at.isoformat()))
    def terminal(self,t):
        es=[]
        for i in t['order_ids']:
            es.append(dict(kind='completed_order',order_id=i,perm_id=100+i,client_id=82,contract_id=12087792,reference=t['intent'],status='Filled' if i!=t['order_ids'][2] else 'Cancelled'))
        self.r.ingest(es)
    def close(self,t,price='1.12',fee=True):
        buy_id='e'+str(1+2*len(self.r.state['trials']));sell_id='e'+str(2+2*len(self.r.state['trials']))
        self.r.ingest([self.fill(t,exec_id=buy_id),self.fee(buy_id)],self.quote);self.at+=timedelta(seconds=2)
        self.r.ingest([self.fill(t,'SELL',price=price,exec_id=sell_id)]+([self.fee(sell_id)] if fee else []));self.terminal(t)
        return self.r.reconcile(*self.snapshot())
    def test_rotation_three_closed_reconciled(self):
        for i,p in enumerate(PROFILES):
            self.signal['opportunity_id']='s'+str(i);self.signal.update(entry_at=self.at.isoformat(),signal_at=self.at.isoformat());self.quote['at']=self.at.isoformat()
            self.assertEqual(p,PROFILES[self.r.state['rotation']]);self.assertTrue(self.close(self.begin()))
        self.assertEqual(0,self.r.state['rotation']);self.assertEqual(3,len(self.r.state['trials']))
    def test_cost_four_dollars_blocks_r1(self):
        self.r.state['protocol']['costs'].update(openingCommission='2',closingCommission='2')
        self.assertEqual('COMMISSION_EXCEEDS_RISK_BUDGET',self.r.size(PROFILES[0],self.signal,self.quote)['reason'])
    def test_four_dollar_r5_r10_no_leverage(self):
        self.r.state['protocol']['costs'].update(openingCommission='2',closingCommission='2')
        for p in PROFILES[1:]:
            d=self.r.size(p,self.signal,self.quote);self.assertLessEqual(float(d['risk']),float(d['budget']));self.assertLessEqual(float(d['reservation']),100)
    def test_economic_validation_rejection_does_not_replace_exploration_gate(self):
        d=self.r.gates(self.signal,self.quote,self.e,True,False);self.assertTrue(d['admitted']);self.assertEqual('NO_VIABLE_STRATEGY_FOUND',d['strategy_validation_gate'])
    def test_preflight_failure_zero_sends(self):
        self.e['margin']='UNKNOWN';send=Mock();d=self.r.begin(self.signal,self.quote,self.e,{},True,1,send);send.assert_not_called();self.assertIsNone(self.r.state['active']);self.assertIn('MARGIN_UNVERIFIED',d['reasons'])
    def test_no_signal_no_send(self):
        self.signal['reasons']=['NO_SIGNAL'];self.assertIn('NO_VALID_ORIGINAL_SIGNAL',self.r.gates(self.signal,self.quote,self.e,True,False)['reasons'])
    def test_future_signal_blocked(self):
        self.signal['signal_at']=(AT+timedelta(seconds=1)).isoformat();self.assertIn('LATE_OR_FUTURE_SIGNAL',self.r.gates(self.signal,self.quote,self.e,True,False)['reasons'])
    def test_future_context_blocked(self):
        self.signal['context']={'15':{'as_of':(AT+timedelta(seconds=1)).isoformat()}};self.assertIn('FUTURE_CONTEXT',self.r.gates(self.signal,self.quote,self.e,True,False)['reasons'])
    def test_late_signal_blocked(self):
        self.at+=timedelta(seconds=6);self.assertFalse(self.r.gates(self.signal,self.quote,self.e,True,False)['admitted'])
    def test_minimum_size_not_rounded_up(self):
        self.e['minimum_quantity']='20000';self.assertIn('BROKER_SIZE_CONSTRAINT',self.r.gates(self.signal,self.quote,self.e,True,False)['reasons'])
    def test_increment_constraint(self):
        self.e['quantity_increment']='100';self.assertIn('BROKER_SIZE_CONSTRAINT',self.r.gates(self.signal,self.quote,self.e,True,False)['reasons'])
    def test_account_netting_blocks_parallel(self):
        self.begin();self.assertIn('ACCOUNT_NETTING_ACTIVE_TRIAL',self.r.gates(self.signal,self.quote,self.e,True,False)['reasons'])
    def test_ack_no_fill_no_rotation_or_release(self):
        t=self.begin();self.r.ingest([dict(kind='status',order_id=1,status='Submitted')]);self.r.reconcile(*self.snapshot());self.assertEqual('ACK_PENDING_FILL',t['state']);self.assertEqual(0,self.r.state['rotation']);self.assertNotEqual('0',t['reserved'])
    def test_partial_fill_not_settled(self):
        t=self.begin();self.r.ingest([self.fill(t,q='1')],self.quote);self.assertEqual(1,self.r.inventory(t));self.assertEqual(0,self.r.state['rotation'])
    def test_full_fill_not_a_winner(self):
        t=self.begin();self.r.ingest([self.fill(t)],self.quote);self.assertEqual([],self.r.state['profiles'][PROFILES[0]]['broker_trades'])
    def test_late_commission_holds_reserve_and_rotation(self):
        t=self.begin();self.assertFalse(self.close(t,fee=False));self.assertEqual('COMMISSION_PENDING',t['state']);self.assertEqual(0,self.r.state['rotation']);self.assertNotEqual('0',self.r.state['profiles'][PROFILES[0]]['reserved'])
        self.r.ingest([self.fee('e2')]);self.assertTrue(self.r.reconcile(*self.snapshot()));self.assertEqual(1,self.r.state['rotation'])
    def test_unknown_commission_currency_global_stop(self):
        t=self.begin();self.r.ingest([self.fill(t)],self.quote);e=self.fee('e1');e['currency']='EUR'
        with self.assertRaises(PermissionError):self.r.ingest([e])
        self.assertEqual('COMMISSION_CURRENCY_OR_AMOUNT_UNCERTAIN',self.r.state['global_stop'])
    def test_duplicate_execution_not_double_counted(self):
        t=self.begin();e=self.fill(t);self.r.ingest([e,e],self.quote);self.assertEqual(1,len(t['fills']))
    def test_fill_identity_foreign(self):
        t=self.begin();e=self.fill(t);e['contract_id']=1
        with self.assertRaises(PermissionError):self.r.ingest([e])
    def test_oversell_global_stop(self):
        t=self.begin()
        with self.assertRaises(PermissionError):self.r.ingest([self.fill(t,'SELL')])
    def test_duplicate_signal_after_restart(self):
        t=self.begin();self.close(t);r=Rotator(self.j,lambda:self.at);self.assertIn('DUPLICATE_SIGNAL',r.gates(self.signal,self.quote,self.e,True,False)['reasons'])
    def test_crash_send_pending_never_resends(self):
        send=Mock(side_effect=TimeoutError())
        with self.assertRaises(TimeoutError):self.r.begin(self.signal,self.quote,self.e,dict(session_id='x'),False,1,send)
        r=Rotator(self.j,lambda:self.at);self.assertEqual('SEND_UNCERTAIN_RECONCILE_REQUIRED',r.state['global_stop']);self.assertIsNotNone(r.state['active'])
        again=Mock();r.begin(self.signal,self.quote,self.e,dict(session_id='x'),False,1,again);again.assert_not_called()
    def test_reconciliation_cash_absent_preserves_unknown(self):
        self.begin();s,a=self.snapshot();s['eur_cash']=None;s['cash_reconciliation']['value']=None
        self.assertFalse(self.r.reconcile(s,a));self.assertIsNone(s['eur_cash']);self.assertEqual('STRICT_ACCOUNT_RECONCILIATION_REQUIRED',self.r.state['global_stop'])
    def test_reconciliation_after_first_fill_strict(self):
        t=self.begin();self.r.ingest([self.fill(t)],self.quote);s,a=self.snapshot(t['quantity']);s['eur_cash']=None
        self.assertFalse(self.r.reconcile(s,a));self.assertNotEqual('0',t['reserved'])
    def test_position_mismatch_blocks(self):
        self.begin();self.assertFalse(self.r.reconcile(*self.snapshot('1')));self.assertEqual('NETTING_NOT_ATTRIBUTABLE',self.r.state['global_stop'])
    def test_unknown_order_blocks(self):
        self.begin();s,a=self.snapshot(orders=[dict(order_id=99)]);self.assertFalse(self.r.reconcile(s,a));self.assertEqual('UNKNOWN_ORDER',self.r.state['global_stop'])
    def test_stale_reconciliation_not_certified(self):
        s,a=self.snapshot();s['received_at']=(AT-timedelta(seconds=31)).isoformat();self.assertFalse(self.r.reconcile(s,a));self.assertNotIn('last_reconciliation',self.r.state)
    def test_open_child_prevents_settlement(self):
        t=self.begin();self.r.ingest([self.fill(t),self.fill(t,'SELL',exec_id='e2'),self.fee('e1'),self.fee('e2')],self.quote);self.terminal(t)
        self.assertFalse(self.r.reconcile(*self.snapshot(orders=[dict(order_id=3)])));self.assertEqual(0,self.r.state['rotation'])
    def test_terminal_without_completed_ack_does_not_rotate(self):
        t=self.begin();self.r.ingest([self.fill(t),self.fill(t,'SELL',exec_id='e2'),self.fee('e1'),self.fee('e2')],self.quote)
        t['statuses']={str(i):'Filled' for i in t['order_ids']};self.assertFalse(self.r.reconcile(*self.snapshot()))
    def test_loss_stops_profile_not_global(self):
        t=self.begin();self.assertTrue(self.close(t,price='1.09'));self.assertTrue(self.r.state['profiles'][PROFILES[0]]['stopped_days']);self.assertFalse(self.r.state['profiles'][PROFILES[1]]['stopped_days']);self.assertIsNone(self.r.state['global_stop'])
    def test_zero_stops_profile(self):
        self.r.settle_profile(PROFILES[0],0,AT.isoformat(),{},False);self.assertEqual('DAILY_BREAK_EVEN_STOP',next(iter(self.r.state['profiles'][PROFILES[0]]['stopped_days'].values())))
    def test_profit_never_restores_consumed_loss(self):
        self.r.settle_profile(PROFILES[0],-1,AT.isoformat(),{},False);self.r.settle_profile(PROFILES[0],2,AT.isoformat(),{},False);self.assertEqual('1',self.r.state['profiles'][PROFILES[0]]['consumed_loss'])
    def test_next_day_profile_loss_reset_only_daily(self):
        self.r.settle_profile(PROFILES[0],-1,AT.isoformat(),{},False);self.at+=timedelta(days=1);self.signal.update(entry_at=self.at.isoformat(),signal_at=self.at.isoformat());self.quote['at']=self.at.isoformat();self.assertNotIn('STOPPED_FOR_DAY',self.r.gates(self.signal,self.quote,self.e,True,False)['reasons'])
    def test_three_daily_global_closes(self):
        self.r.state['closed_days']['2026-10-07']=3;self.assertIn('DAILY_GLOBAL_THREE_CLOSE_LIMIT',self.r.gates(self.signal,self.quote,self.e,True,False)['reasons'])
    def test_technical_stop_global(self):
        self.r.fail('PROTECTION_FAILURE');self.r.state['rotation']=1;self.assertIn('PROTECTION_FAILURE',self.r.gates(self.signal,self.quote,self.e,True,False)['reasons'])
    def test_strategy_change_rejected(self):
        self.signal['strategy_version']='b'*64;self.assertIn('COHORT_STRATEGY_MISMATCH',self.r.gates(self.signal,self.quote,self.e,True,False)['reasons'])
    def test_short_entry_not_supported(self):
        self.signal['side']='SELL';self.assertIn('EXPLORATORY_LONG_ONLY_NO_SHORT',self.r.gates(self.signal,self.quote,self.e,True,False)['reasons'])
    def test_shadow_twins_at_actual_first_fill(self):
        t=self.begin();self.r.ingest([self.fill(t)],self.quote);self.assertEqual(set(PROFILES[1:]),set(t['twins']));self.assertTrue(all(x['execution_mode']=='SIMULATED_SHADOW' and x['entry_at']==t['entry_at'] and x['stop']==t['stop'] for x in t['twins'].values()))
    def test_missing_contemporaneous_quote_is_no_trade(self):
        t=self.begin();self.at+=timedelta(seconds=6);self.r.ingest([self.fill(t)]);self.assertTrue(all(x['state']=='NO_TRADE' for x in t['twins'].values()))
    def test_protection_ack_exact_inventory_and_links(self):
        t=self.begin();self.r.ingest([self.fill(t)],self.quote);orders=[]
        for i in (1,2):
            orders.append(dict(order_id=t['order_ids'][i],client_id=82,perm_id=100+i,status='Submitted',side='SELL',reference=t['intent'],parent_id=1,oca_group=t['intent'],oca_type=2,order_type='LMT' if i==1 else 'STP',quantity=t['quantity'],limit_price=t['target'],stop_price=t['stop']))
        self.assertTrue(self.r.protection(orders));orders[1]['quantity']='100000';self.assertFalse(self.r.protection(orders))
    def test_mutation_guard_independent_close(self):
        t=self.begin()
        with self.assertRaises(PermissionError):self.r.authorize_transport(t,'OWNED_CLOSE',2,t['quantity'])
    def test_live_ui_payload_rejected(self):
        with self.assertRaises(ValueError):overlay({},dict(scope='EURUSD_PAPER_EXPLORATORY',classification='EXPLORATORY_NOT_VALIDATED',live_enabled=True))
    def test_competing_writer_no_order(self):
        r2=Rotator(self.j,lambda:self.at);self.r.append('OTHER_WRITER');r2.state['global_stop']='x'
        with self.assertRaises(RuntimeError):r2.append('STALE')
    def test_journal_tamper_rejected(self):
        self.j.h['hash']='b'*64
        with self.assertRaises(PermissionError):Rotator(self.j,lambda:self.at)

    def test_other_cohort_pending_intent_blocks_even_broker_flat(self):
        self.r.conflicting_cohorts=['other'];self.assertIn('OTHER_COHORT_PENDING_INTENT_OR_RESERVATION',self.r.gates(self.signal,self.quote,self.e,True,False)['reasons'])
    def test_sdk_facet_captures_actual_stop_ack(self):
        from types import SimpleNamespace
        from trading_agent.eurusd_exploratory_wire import exploratory_wire
        w=exploratory_wire(Mock(),Mock(),Mock(),None);w.expected='DU0000';w.collect_open=True;w.open_orders=[]
        order=SimpleNamespace(account='DU0000',permId=1,clientId=82,action='SELL',totalQuantity=1,orderType='STP',parentId=1,ocaGroup='x',ocaType=2,orderRef='x',tif='GTC',lmtPrice=0,auxPrice=1.09)
        w.openOrder(3,SimpleNamespace(conId=12087792),order,SimpleNamespace(status='Submitted',initMarginChange='0'))
        self.assertEqual('1.09',w.drain()[0]['stop_price']);self.assertEqual('1.09',w.open_orders[0]['stop_price'])
    def test_authorization_rejects_live_before_process_checks(self):
        from trading_agent.eurusd_exploratory_runner import Authorization
        with patch('trading_agent.eurusd_exploratory_runner.AccountBinding.load_or_migrate',return_value=Mock()),patch('trading_agent.eurusd_exploratory_runner.SessionConfiguration.load',return_value=Mock()):
            a=Authorization('.',self.j.cohort,loader=lambda:dict(environment='LIVE_TRADING',live_enabled=True))
            with self.assertRaisesRegex(PermissionError,'LIVE_DISABLED'):a.read()
    def test_authorization_rejects_foreign_binding(self):
        from trading_agent.eurusd_exploratory_runner import Authorization
        with patch('trading_agent.eurusd_exploratory_runner.AccountBinding.load_or_migrate',return_value=Mock(binding_id='known',account='DU0000')),patch('trading_agent.eurusd_exploratory_runner.SessionConfiguration.load',return_value=Mock()):
            a=Authorization('.',self.j.cohort,loader=lambda:dict(mode='EURUSD_PAPER_EXPLORATORY',scope='EURUSD_PAPER_EXPLORATORY',cohort=self.j.cohort,environment='PAPER_TRADING',live_enabled=False,binding_id='wrong',account='DU0000'))
            with self.assertRaisesRegex(PermissionError,'EXPLORATORY_BINDING_REQUIRED'):a.read()
    def test_old_diagnostic_authorization_cannot_be_reused(self):
        from trading_agent.eurusd_exploratory_runner import Authorization
        with patch('trading_agent.eurusd_exploratory_runner.AccountBinding.load_or_migrate',return_value=Mock()),patch('trading_agent.eurusd_exploratory_runner.SessionConfiguration.load',return_value=Mock()):
            a=Authorization('.',self.j.cohort,loader=lambda:dict(mode='ExecutionDiagnostics',environment='PAPER_TRADING',live_enabled=False))
            with self.assertRaisesRegex(PermissionError,'EXPLORATORY_BINDING_REQUIRED'):a.read()

    def test_unsaved_intent_change_blocks_transport(self):
        t=self.begin();t['quantity']='100'
        with self.assertRaisesRegex(PermissionError,'DURABLE_INTENT_STATE_CHANGED'):self.r.authorize_transport(t,'BRACKET_ENTRY',1,'100')
    def test_registered_entry_transport_checks_exact_payload(self):
        t=self.begin();self.r.authorize_transport(t,'BRACKET_ENTRY',1,t['quantity'])
        with self.assertRaises(PermissionError):self.r.authorize_transport(t,'BRACKET_ENTRY',1,'1000000')
    def test_recovery_transport_cannot_oversell_owned(self):
        t=self.begin();self.r.ingest([self.fill(t)],self.quote)
        rec=dict(intent=t['intent'],quantity=t['quantity'],authorization_id='fresh',reference='RECOVERY-fresh',order_id=4)
        t['recovery_orders']['4']=rec;self.r.append('RECOVERY_PENDING')
        self.r.authorize_transport(rec,'RECOVERY_CLOSE',4,t['quantity'])
        with self.assertRaises(PermissionError):self.r.authorize_transport(rec,'RECOVERY_CLOSE',4,'1000000')
    def test_stop_r1_does_not_block_r5(self):
        self.r.settle_profile(PROFILES[0],-1,AT.isoformat(),{},False);self.r.state['rotation']=1
        self.assertNotIn('STOPPED_FOR_DAY',self.r.gates(self.signal,self.quote,self.e,True,False)['reasons'])
    def test_quote_stale_does_not_create_paper_mark(self):
        from trading_agent.eurusd_exploratory_projection import view_trial
        t=self.begin();self.r.ingest([self.fill(t)],self.quote);q=dict(self.quote,at='2000-01-01T00:00:00+00:00')
        v=view_trial(t,q);self.assertIsNone(v['currentPrice']);self.assertIsNone(v['netPnl'])
    def test_shadow_does_not_count_as_broker_fill(self):
        t=self.begin();self.r.ingest([self.fill(t)],self.quote)
        for p in PROFILES[1:]:self.assertEqual([],self.r.state['profiles'][p]['broker_trades'])

    def test_historical_fills_repeated_by_reconciliation_are_not_new_trades(self):
        t=self.begin();self.close(t);self.r.ingest(list(t['fills'].values())+list(t['commissions'].values()),self.quote)
        self.assertIsNone(self.r.state['global_stop']);self.assertEqual(1,self.r.state['rotation'])
    def test_historical_commission_correction_blocks_instead_of_erasing_loss(self):
        t=self.begin();self.close(t,price='1.09');before=self.r.state['profiles'][PROFILES[0]]['consumed_loss']
        with self.assertRaisesRegex(PermissionError,'HISTORICAL_COMMISSION_CORRECTION'):self.r.ingest([self.fee('e1','0')])
        self.assertEqual(before,self.r.state['profiles'][PROFILES[0]]['consumed_loss'])

    def test_shadow_quote_after_actual_broker_fill_is_never_used(self):
        t=self.begin();self.at+=timedelta(seconds=10);q=dict(self.quote,at=(self.at+timedelta(seconds=1)).isoformat());self.r.ingest([self.fill(t)],q)
        self.assertTrue(all(x['state']=='NO_TRADE' for x in t['twins'].values()))
    def test_history_quote_before_fill_can_create_twin(self):
        t=self.begin();self.at+=timedelta(seconds=8);q=dict(self.quote,at=(self.at-timedelta(seconds=1)).isoformat());self.r.state['quote_history']=[q];self.r.ingest([self.fill(t)])
        self.assertTrue(all(x['state']=='OPEN' for x in t['twins'].values()))
    def test_crossed_quote_gate_before_send_pending(self):
        self.quote['bid']='2';send=Mock();d=self.r.begin(self.signal,self.quote,self.e,dict(session_id='fresh'),False,1,send);send.assert_not_called();self.assertIn('LIVE_OPEN_FRESH_QUOTE_REQUIRED',d['reasons'])

    def test_eur_cash_conversion_cannot_be_mistaken_for_flat_speculative_account(self):
        s,a=self.snapshot();s['eur_cash']='100';s['cash_reconciliation']['value']='100';self.assertFalse(self.r.reconcile(s,a));self.assertEqual('EUR_CASH_INVENTORY_NOT_ATTRIBUTABLE',self.r.state['global_stop'])

    def auth_fixture(self,mutations=None):
        from trading_agent.eurusd_exploratory_runner import Authorization
        a=dict(environment='PAPER_TRADING',live_enabled=False,mode='EURUSD_PAPER_EXPLORATORY',scope='EURUSD_PAPER_EXPLORATORY',cohort=self.j.cohort,binding_id='binding',account='DU0000',authorized=True,revoked=False,paper_checked=True,identity_manual_match=True,read_only_disabled_checked=True,forex_permission_checked=True,owned_reduce_only_management=True,client_id=82,max_quantity='100',max_notional_usd='100',order_types=['LMT','STP'],tws_pid=1,tws_start_filetime='1',confirmed_at=AT.isoformat(),expires_at=(AT+timedelta(minutes=30)).isoformat(),protocol_version=2,single_use=True,max_openings=1,profile=PROFILES[0],purpose='PAPER_EXPLORATORY_RESEARCH')
        a.update(mutations or {})
        return Authorization('.',self.j.cohort,loader=lambda:deepcopy(a),clock=lambda:self.at)
    def auth_patches(self):
        from contextlib import ExitStack
        stack=ExitStack();stack.enter_context(patch('trading_agent.eurusd_exploratory_runner.AccountBinding.load_or_migrate',return_value=Mock(binding_id='binding',account='DU0000')));stack.enter_context(patch('trading_agent.eurusd_exploratory_runner.SessionConfiguration.load',return_value=Mock()));stack.enter_context(patch('trading_agent.eurusd_exploratory_runner.same_process',return_value=True));return stack
    def test_new_authorization_validates_complete_scope(self):
        with self.auth_patches():self.assertEqual('EURUSD_PAPER_EXPLORATORY',self.auth_fixture().read()['mode'])
    def test_revoked_authorization_only_preapproved_management(self):
        with self.auth_patches():
            a=self.auth_fixture(dict(revoked=True))
            with self.assertRaisesRegex(PermissionError,'REVOKED_OR_EXPIRED'):a.read()
            self.assertTrue(a.read(management=True)['owned_reduce_only_management'])
    def test_expired_authorization_cannot_open(self):
        self.at=AT+timedelta(minutes=31)
        with self.auth_patches():
            with self.assertRaisesRegex(PermissionError,'REVOKED_OR_EXPIRED'):self.auth_fixture().read()
    def test_management_delegation_has_a_deadline(self):
        self.at=AT+timedelta(days=2)
        with self.auth_patches():
            with self.assertRaisesRegex(PermissionError,'INDEPENDENT_RECOVERY'):self.auth_fixture().read(management=True)
    def test_api_read_only_flag_not_silently_ignored(self):
        with self.auth_patches():
            with self.assertRaisesRegex(PermissionError,'GRANT_INVALID'):self.auth_fixture(dict(read_only_disabled_checked=False)).read()
    def test_quantity_scope_cannot_be_increased_in_a_grant(self):
        with self.auth_patches():
            with self.assertRaisesRegex(PermissionError,'GRANT_INVALID'):self.auth_fixture(dict(max_quantity='1000')).read()

    def test_missing_sell_quote_does_not_report_zero_exit_slippage(self):
        from trading_agent.eurusd_exploratory_projection import view_trial
        t=self.begin();self.close(t);v=view_trial(t,self.quote);self.assertIsNone(v['slippage']);self.assertIsNone(v['closingSlippage']);self.assertIsNotNone(v['openingSlippage']);self.assertEqual('BROKER_TAKE_PROFIT',v['exitReason'])

    def test_prepared_cohort_does_not_downgrade_fresh_original_shadow_quotes(self):
        from trading_agent.eurusd_exploratory_projection import overlay
        at=datetime.now(timezone.utc).isoformat();self.r.state['last_quote']=dict(self.quote,at='2000-01-01T00:00:00+00:00')
        result=dict(market=dict(quality='LIVE',bid=1.12,ask=1.1201,at=at,marketStatus='OPEN'),trades=[],experiments=[],openPositions=[],notifications=[])
        p=dict(scope='EURUSD_PAPER_EXPLORATORY',classification='EXPLORATORY_NOT_VALIDATED',live_enabled=False,state=self.r.state,cohort_id=self.j.cohort)
        view=overlay(result,p);self.assertEqual('LIVE',view['market']['quality']);self.assertEqual(1.12,view['market']['bid'])

if __name__=='__main__':unittest.main()
