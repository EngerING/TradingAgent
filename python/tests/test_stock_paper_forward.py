import copy
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from trading_agent.stock_paper_forward import (CANDIDATE,VERSION,Journal,Ledger,estimate,configuration,
    readiness,h40_exit,h40_next_signal,PaperExecutionGuard,CAPABILITIES,inspect,number,core_risk)
from trading_agent.stock_paper_forward_wire import stock_forward_wire
from trading_agent.stock_paper_forward_runner import owned_snapshot,drain
from trading_agent.broker import PaperOptions
from trading_agent.ai_strategy_researcher.simulation import signals,exit_event
from test_paper_account_capabilities import CapClient

BASE=datetime(2027,1,4,14,30,tzinfo=timezone.utc)

def plan():
    return dict(at=BASE.isoformat(),intent='H40-a',signal_key='a',strategy_version=VERSION,
        side='BUY',quantity=2,entry='10',stop='9.9',target='10.1',fees='.1',risk='.4',
        con_id=100,order_ids=[10,11,12],entry_session=BASE.isoformat(),signal=dict(signal_at=(BASE-timedelta(days=3)).isoformat()),friction={})
def order(oid,status='Submitted'):
    return dict(order_id=oid,order_ref='H40-a',perm_id=oid+100,status=status,quantity='2',side='BUY' if oid==10 else 'SELL',
        con_id=100,symbol='F',security_type='STK',currency='USD',parent_id=0 if oid==10 else 10,oca_group='' if oid==10 else 'H40-a',oca_type=0 if oid==10 else 2)
def fill(oid,exec_id='b',q=2,price=10,stamp=BASE):
    return dict(order_id=oid,order_ref='H40-a',perm_id=oid+100,exec_id=exec_id,con_id=100,
        side='BUY' if oid==10 else 'SELL',quantity=str(q),price=str(price),at=stamp.isoformat())
def position(q):return dict(con_id=100,symbol='F',security_type='STK',currency='USD',quantity=str(q))
def snap(q=0,orders=None,execs=None,fees=None):
    return dict(identity_verified=True,complete=True,connected=True,at=BASE.isoformat(),
        positions=[position(q)] if q else [],open_orders=orders or [],completed_orders=[order(10,'Filled'),order(11,'Cancelled'),order(12,'Cancelled')],
        executions=execs or [],commissions=fees or [],next_session_start=(BASE+timedelta(days=1)).isoformat())
def fee(exec_id,amount='.05'):return dict(exec_id=exec_id,currency='USD',commission=amount)
def rows(n=42):
    return [dict(opened_at=(BASE+timedelta(days=i)).isoformat(),closed_at=(BASE+timedelta(days=i,hours=6)).isoformat(),
        open=10,high=10.5,low=9.5,close=10,volume=100) for i in range(n)]

class StockForwardLedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'journal.sqlite3';self.j=Journal(self.path,'binding');self.l=Ledger(self.j)
    def tearDown(self):self.j.close();self.tmp.cleanup()
    def reserved(self):self.l.reserve(plan())
    def test_capital_100_isolated(self):self.assertEqual(self.l.state['equity'],'100');self.assertEqual(self.l.state['reservation'],'0')
    def test_reserve_includes_both_fees(self):self.reserved();self.assertEqual(number(self.l.state['reservation']),number('20.1'))
    def test_limit_includes_fees(self):
        p=plan();p.update(quantity=10)
        with self.assertRaisesRegex(PermissionError,'ALLOCATION'):self.l.reserve(p)
    def test_short_not_allowed(self):
        p=plan();p['side']='SELL'
        with self.assertRaises(PermissionError):self.l.reserve(p)
    def test_productive_risk_not_relaxed(self):
        p=plan();p['risk']='2'
        with self.assertRaisesRegex(PermissionError,'PROTECTED_RISK'):self.l.reserve(p)
    def test_simultaneous_position_block(self):
        self.reserved()
        with self.assertRaisesRegex(PermissionError,'NOT_DEFINITIVE'):self.l.reserve(plan())
    def test_pre_send_once(self):
        self.reserved();self.l.pre_send(10)
        with self.assertRaisesRegex(PermissionError,'NO_BLIND'):self.l.pre_send(10)
    def test_restart_keeps_reserve_and_attempt(self):
        self.reserved();self.l.pre_send(10);self.j.close();self.j=Journal(self.path,'binding');self.l=Ledger(self.j)
        self.assertGreater(number(self.l.state['reservation']),0)
        with self.assertRaisesRegex(PermissionError,'NO_BLIND'):self.l.pre_send(10)
    def test_revision_cas(self):
        other=Ledger(self.j);self.reserved()
        with self.assertRaisesRegex(PermissionError,'JOURNAL_CHANGED'):other.write('OLD')
    def test_hash_tamper_detected(self):
        self.j.db.execute("UPDATE events SET kind='TAMPER' WHERE revision=1");self.j.db.commit()
        with self.assertRaisesRegex(PermissionError,'INTEGRITY'):self.j.load()
    def test_different_binding_denied(self):
        with self.assertRaisesRegex(PermissionError,'SCOPE'):Journal(self.path,'other')
    def test_bracket_zero_fills_keeps_reserve(self):
        self.reserved();s=snap(orders=[order(10),order(11),order(12)]);s['completed_orders']=[]
        self.l.reconcile(s);self.assertEqual(self.l.state['intent']['state'],'PENDING');self.assertGreater(number(self.l.state['reservation']),0)
    def test_cancelled_unfilled_releases_only_when_flat_no_orders(self):
        self.reserved();s=snap();s['completed_orders'][0]=order(10,'Cancelled');self.l.reconcile(s)
        self.assertIsNone(self.l.state['intent']);self.assertEqual(self.l.state['reservation'],'0')
    def test_partial_fill_needs_reconciliation(self):
        self.reserved();self.l.fill(fill(10,q=1));self.assertIsNone(self.l.state['intent']['last_reconciled_at'])
        s=snap(q=1,orders=[order(10),order(11),order(12)],execs=[fill(10,q=1)]);s['completed_orders']=[]
        self.l.reconcile(s);self.assertEqual(self.l.state['intent']['state'],'PARTIAL_PARENT_MANAGEMENT_REQUIRED')
    def test_full_fill_open_protected(self):
        self.reserved();self.l.reconcile(snap(q=2,execs=[fill(10)],orders=[order(11),order(12)]))
        self.assertEqual(self.l.state['intent']['state'],'OPEN_PROTECTED')
    def test_selling_exceeds_confirmed_buy_rejected(self):
        self.reserved();self.l.fill(fill(10,q=1))
        with self.assertRaisesRegex(PermissionError,'SHORT'):self.l.fill(fill(11,'s',q=2))
    def test_fill_deduplicated(self):
        self.reserved();f=fill(10);self.l.fill(f);r=self.l.revision;self.l.fill(f);self.assertEqual(self.l.revision,r)
    def test_changed_exec_rejected(self):
        self.reserved();self.l.fill(fill(10))
        with self.assertRaisesRegex(PermissionError,'EXEC_ID_CHANGED'):self.l.fill(fill(10,price=11))
    def test_unknown_execution_rejected(self):
        self.reserved();f=fill(10);f['order_ref']='other'
        with self.assertRaisesRegex(PermissionError,'UNRECOGNIZED'):self.l.fill(f)
    def test_changed_permid_rejected(self):
        self.reserved();self.l.order(order(10));o=order(10);o['perm_id']=999
        with self.assertRaisesRegex(PermissionError,'PERM_ID_CHANGED'):self.l.order(o)
    def test_changed_contract_ack_rejected(self):
        self.reserved();o=order(10);o['con_id']=999
        with self.assertRaisesRegex(PermissionError,'GEOMETRY_CHANGED'):self.l.order(o)
    def test_broker_bracket_link_required(self):
        self.reserved();o=order(12);o['oca_type']=1
        with self.assertRaisesRegex(PermissionError,'OCA_LINK_CHANGED'):self.l.order(o)
    def test_fill_permid_matches_ack(self):
        self.reserved();self.l.order(order(10));f=fill(10);f['perm_id']=999
        with self.assertRaisesRegex(PermissionError,'PERM_ID_MISMATCH'):self.l.fill(f)
    def test_inventory_mark_never_realized_win(self):
        self.reserved();s=snap(q=2,execs=[fill(10)],fees=[fee('b')],orders=[order(11),order(12)])
        s['quote']=dict(bid='11',market_data_type=1,received_at=BASE.isoformat());self.l.reconcile(s)
        self.assertEqual(self.l.state['realized_equity'],'100');self.assertEqual(number(self.l.state['equity']),number('101.95'))
        self.assertEqual(self.l.entry_block(BASE.isoformat()),'PREVIOUS_RESULT_NOT_DEFINITIVE')
        self.l.reconcile(snap(execs=[fill(10),fill(11,'s',price=11)],fees=[fee('b'),fee('s')]))
        self.assertEqual(number(self.l.state['equity']),number('101.90'))
    def test_uncertain_snapshot_keeps_reserve(self):
        self.reserved();s=snap();s['complete']=False
        with self.assertRaises(PermissionError):self.l.reconcile(s)
        self.assertGreater(number(self.l.state['reservation']),0)
    def test_unknown_position_rejected(self):
        s=snap(q=1)
        with self.assertRaisesRegex(PermissionError,'UNKNOWN_POSITION'):self.l.reconcile(s)
    def test_position_mismatch_rejected(self):
        self.reserved()
        with self.assertRaisesRegex(PermissionError,'MISMATCH'):self.l.reconcile(snap(q=1))
    def test_commission_pending_not_win(self):
        self.reserved();self.l.reconcile(snap(execs=[fill(10),fill(11,'s',price=11)]))
        self.assertEqual(self.l.state['intent']['state'],'FLAT_COMMISSION_PENDING');self.assertEqual(self.l.state['equity'],'100')
        self.assertGreater(number(self.l.state['reservation']),0)
    def test_fee_can_precede_execution(self):
        self.reserved();self.l.fee(fee('b'));self.l.reconcile(snap(execs=[fill(10),fill(11,'s',price=11)],fees=[fee('s')]))
        self.assertEqual(number(self.l.state['equity']),number('101.90'));self.assertEqual(number(self.l.state['cash']),100)
    def test_flat_pending_orders_no_release(self):
        self.reserved();self.l.reconcile(snap(orders=[order(12)],execs=[fill(10),fill(11,'s',price=11)],fees=[fee('b'),fee('s')]))
        self.assertEqual(self.l.state['intent']['state'],'FLAT_ORDERS_PENDING')
    def settled(self,price):
        self.reserved();self.l.reconcile(snap(execs=[fill(10),fill(11,'s',price=price)],fees=[fee('b'),fee('s')]))
    def test_loss_stops_day_and_survives_restart(self):
        self.settled('9.9');self.j.close();self.j=Journal(self.path,'binding');self.l=Ledger(self.j)
        self.assertEqual(self.l.entry_block(BASE.isoformat()),'DAILY_FIRST_LOSS_STOP');self.assertIsNone(self.l.entry_block((BASE+timedelta(days=1)).isoformat()))
        self.assertEqual(number(self.l.state['consumed_loss']),number('.30'))
    def test_break_even_stops_day(self):self.settled('10.05');self.assertEqual(self.l.entry_block(BASE.isoformat()),'DAILY_BREAK_EVEN_STOP')
    def test_net_win_can_continue(self):self.settled('10.1');self.assertIsNone(self.l.entry_block(BASE.isoformat()))
    def test_duplicate_closed_signal_rejected(self):
        self.settled('10.1')
        with self.assertRaisesRegex(PermissionError,'DUPLICATE_SIGNAL'):self.l.reserve(plan())
    def test_gains_do_not_restore_losses(self):
        self.l.state['consumed_loss']='5';self.settled('10.1');self.assertEqual(self.l.state['consumed_loss'],'5')
    def test_commission_currency_unknown_blocks(self):
        self.reserved();f=fee('b');f['currency']='EUR'
        with self.assertRaisesRegex(PermissionError,'NOT_DEFINITIVE'):self.l.fee(f)
    def test_cumulative_budget_halts_independent_of_day(self):
        self.l.state['consumed_loss']='20';self.assertEqual(self.l.entry_block((BASE+timedelta(days=30)).isoformat()),'CUMULATIVE_LOSS_STOP')

class StockForwardSemanticsTests(unittest.TestCase):
    def test_original_candidate_exact(self):self.assertEqual(CANDIDATE['risk_percent'],2);self.assertEqual(configuration(Path('.'))['strategy_version'],VERSION)
    def test_stop_first_same_bar(self):
        r=rows(2);r[0].update(low=8,high=12);s=dict(index=0,stop=9,target=11)
        self.assertEqual(h40_exit(r,s)[2],'STOP_FIRST_IF_AMBIGUOUS')
    def test_stop_gap_actual_open(self):
        r=rows(2);r[0].update(open=8,low=7,high=10,close=9)
        self.assertEqual(h40_exit(r,dict(index=0,stop=9,target=11))[1:3],(8.,'STOP_GAP'))
    def test_hold40_next_open_precedes_stop(self):
        r=rows();r[39].update(open=8,low=7,high=10,close=9)
        e=h40_exit(r,dict(index=0,stop=9,target=11));self.assertEqual((e[0],e[1],e[2]),(39,8.,'RULE_NEXT_OPEN'))
    def test_paper_and_simulation_equivalent_decisions(self):
        for stop,target in ((9,11),(9.8,11),(9,10.2)):
            r=rows();s=dict(index=0,stop=stop,target=target);_,f=signals(r,CANDIDATE)
            self.assertEqual(h40_exit(r,s),exit_event(r,f,s,CANDIDATE))
    def test_no_latest_bar_signal_without_real_next_open(self):
        r=rows();r[-2]['close']=5;r[-2]['low']=4;r[-1]['close']=6;r[-1]['low']=5
        e,_=signals(r,CANDIDATE);self.assertFalse(any(s['index']==len(r) for s in e))
    def test_profile_study_never_auth_or_leverage(self):
        for risk in (3,5,10,15):
            p=estimate(12,11,13,risk,spread='.01');self.assertFalse(p['execution_authorized']);self.assertLessEqual(number(p['reserved_cash']),100)
    def test_study_stop_costs_in_budget(self):
        for risk in (3,5,10,15):
            p=estimate(12,11,13,risk);self.assertLessEqual(number(p['estimated_loss']),number(p['risk_budget']))
    def test_unaffordable_no_leverage(self):self.assertEqual(estimate(101,99,103,15)['quantity'],0)

class StockForwardWireTests(unittest.TestCase):
    def setUp(self):
        from ibapi.order import Order
        self.w=stock_forward_wire(PaperOptions('DU123',paper_mode_attested=True,timeout=.02),
            (CapClient,object,SimpleNamespace,Order,SimpleNamespace,SimpleNamespace))
        self.w.connect()
    def tearDown(self):self.w.disconnect()
    def test_inspection_client_cannot_place_order(self):
        with self.assertRaises(PermissionError):self.w._client.placeOrder(10,SimpleNamespace(),SimpleNamespace())
    def test_inspection_client_cannot_cancel(self):
        with self.assertRaises(PermissionError):self.w._client.cancelOrder(10,SimpleNamespace())
    def test_raw_protobuf_blocked(self):
        with self.assertRaises(PermissionError):self.w._client.placeOrderProtoBuf(SimpleNamespace())
        with self.assertRaises(PermissionError):self.w._client.cancelOrderProtoBuf(SimpleNamespace())
    def test_bracket_links_protection_to_parent(self):
        p=plan();o0,_=self.w.build(p,0);o1,_=self.w.build(p,1);o2,_=self.w.build(p,2)
        self.assertFalse(o0.transmit);self.assertFalse(o1.transmit);self.assertTrue(o2.transmit)
        self.assertEqual((o1.parentId,o2.parentId),(10,10));self.assertEqual((o1.ocaGroup,o2.ocaGroup),('H40-a','H40-a'));self.assertEqual(o2.ocaType,2)
    def test_paper_identity_change_disconnects(self):self.w.managedAccounts('U123');self.assertFalse(self.w.connected)
    def test_guard_failure_zero_send_and_reserve(self):
        class Guard:
            def admission(self,*args):raise PermissionError('GATE_FAILED')
        self.w.guard=Guard();self.w.ledger=SimpleNamespace(reserve=lambda p:self.fail('reserve before gates'))
        with self.assertRaisesRegex(PermissionError,'GATE_FAILED'):self.w.bracket({},plan())
    def test_independent_sell_needs_zero_pending_orders(self):
        class L:
            state={'intent':{'position':'1','last_reconciled_at':BASE.isoformat(),'sell_attempted':False}}
            def reconcile(self,s):pass
        self.w.ledger=L()
        with self.assertRaisesRegex(PermissionError,'CANCELLED'):self.w.close_owned(dict(open_orders=[order(12)]),'10','EXIT')
    def test_zero_position_no_sell(self):
        class L:
            state={'intent':{'position':'0'}}
            def reconcile(self,s):pass
        self.w.ledger=L();self.assertIsNone(self.w.close_owned({},'10','EXIT'))
    def test_close_partial_no_blind_retry(self):
        class L:
            state={'intent':{'position':'1','last_reconciled_at':BASE.isoformat(),'sell_attempted':True}}
            def reconcile(self,s):pass
        self.w.ledger=L()
        with self.assertRaisesRegex(PermissionError,'CANCELLED'):self.w.close_owned(dict(open_orders=[]),'10','EXIT')
    def test_parent_expires_at_next_open_window(self):
        o,_=self.w.build(plan(),0);self.assertEqual(o.tif,'GTD');self.assertEqual(o.goodTillDate,'20270104-14:31:00')
    def writable(self,ledger):
        from ibapi.order import Order
        self.w.disconnect();self.w=stock_forward_wire(PaperOptions('DU123',paper_mode_attested=True,timeout=.02,read_only=False),
            (CapClient,object,SimpleNamespace,Order,SimpleNamespace,SimpleNamespace));self.w.connect()
        class Guard:
            def admission(self,*a):pass
            def grant(self,management=False):return {}
        self.w.bind_execution(Guard(),ledger)
    def test_guarded_bracket_sdk_serialization(self):
        with tempfile.TemporaryDirectory() as d:
            j=Journal(Path(d)/'j.db','binding');l=Ledger(j);self.writable(l);sent=[]
            try:
                with patch.object(CapClient,'placeOrder',lambda s,oid,c,o:sent.append((oid,c.secType,o.action,o.parentId,o.transmit)),create=True):
                    self.w.bracket({},plan())
                self.assertEqual(sent,[(10,'STK','BUY',0,False),(11,'STK','SELL',10,False),(12,'STK','SELL',10,True)])
                self.assertEqual(l.state['intent']['attempted'],[10,11,12])
            finally:j.close()
    def test_sdk_error_stops_remaining_legs_no_retry(self):
        with tempfile.TemporaryDirectory() as d:
            j=Journal(Path(d)/'j.db','binding');l=Ledger(j);self.writable(l);sent=[]
            def error(s,oid,c,o):sent.append(oid);self.w.error(oid,201,'REJECTED')
            try:
                with patch.object(CapClient,'placeOrder',error,create=True):
                    with self.assertRaises(ConnectionError):self.w.bracket({},plan())
                self.assertEqual(sent,[10]);self.assertTrue(l.state['intent']['uncertain']);self.assertGreater(number(l.state['reservation']),0)
            finally:j.close()
    def test_independent_close_exact_remaining_long(self):
        with tempfile.TemporaryDirectory() as d:
            j=Journal(Path(d)/'j.db','binding');l=Ledger(j);l.reserve(plan());s=snap(q=1,execs=[fill(10,q=1)]);s['completed_orders'][0]=order(10,'Cancelled')
            self.writable(l);sent=[]
            from trading_agent.stock_paper_forward_wire import datetime as original_datetime
            class Clock(original_datetime):
                @classmethod
                def now(cls,tz=None):return BASE
            s['quote']=dict(bid='10',ask='10.01',market_data_type=1,field_received_at=dict(bid=BASE.isoformat(),ask=BASE.isoformat()))
            s['active_session']=dict(start=BASE.isoformat(),end=(BASE+timedelta(hours=6)).isoformat())
            self.w.positions=lambda:[position(1)]
            self.w.all_orders=lambda:[]
            try:
                with patch('trading_agent.stock_paper_forward_wire.datetime',Clock),patch.object(CapClient,'placeOrder',lambda client,oid,c,o:sent.append((o.action,o.totalQuantity,o.parentId)),create=True):
                    self.w.close_owned(s,'10','RULE_NEXT_OPEN')
                self.assertEqual(sent,[('SELL',number(1),0)]);self.assertTrue(l.state['intent']['sell_attempted'])
                l.state['intent']['sell_attempted']=False
                self.w.positions=lambda:[];before=len(sent)
                with patch('trading_agent.stock_paper_forward_wire.datetime',Clock):
                    self.assertIsNone(self.w.close_owned(s,'10','RULE_NEXT_OPEN'))
                self.assertEqual(len(sent),before)
            finally:j.close()
    def test_close_cannot_use_missing_quote_or_closed_session(self):
        class L:
            state={'intent':{'position':'1','last_reconciled_at':BASE.isoformat(),'sell_attempted':False,'quantity':'2','con_id':100}}
            def reconcile(self,s):pass
        self.w.ledger=L()
        with self.assertRaisesRegex(PermissionError,'LIVE_QUOTE'):self.w.close_owned(dict(open_orders=[],positions=[position(1)]),'10','EXIT')

class StockForwardReadinessTests(unittest.TestCase):
    def test_unknown_capabilities_not_inferred_from_contract(self):
        s=snap();s['contract']=dict(con_id=100,order_types='LMT,STP')
        blocks=readiness(s,configuration(Path('.')),BASE)
        self.assertIn('STOCK_PERMISSION_UNKNOWN_OR_RESTRICTED',blocks);self.assertIn('PROTECTION_ACCEPTANCE_UNKNOWN_OR_RESTRICTED',blocks)
    def test_verified_contract_still_no_effective_permission(self):
        s=snap();s['capabilities']={'whole_share_minimum':dict(status='VERIFIED',compatible=True)}
        self.assertIn('STOCK_PERMISSION_UNKNOWN_OR_RESTRICTED',readiness(s,configuration(Path('.')),BASE))
    def test_delayed_quote_blocks(self):
        s=snap();s['quote']=dict(market_data_type=3,received_at=BASE.isoformat(),bid='12',ask='12.01',field_received_at=dict(bid=BASE.isoformat(),ask=BASE.isoformat()))
        self.assertIn('LIVE_BID_ASK_UNAVAILABLE_OR_STALE',readiness(s,configuration(Path('.')),BASE))
    def test_research_risk_always_blocked_in_productive_route(self):
        self.assertIn('H40_RISK_2_PERCENT_EXCEEDS_PRODUCTIVE_0_5_PERCENT',readiness(snap(),configuration(Path('.')),BASE))
    def test_unknown_historical_forex_not_adopted_as_h40(self):
        l=SimpleNamespace(state={'intent':None});s=snap(execs=[dict(order_ref='FX',exec_id='fx')]);s['commissions']=[fee('fx')]
        self.assertEqual(owned_snapshot(s,l)['executions'],[])

if __name__=='__main__':unittest.main()
