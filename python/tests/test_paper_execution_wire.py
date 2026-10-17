from datetime import datetime,timezone,timedelta
from types import SimpleNamespace
from unittest.mock import patch
import unittest
from trading_agent.paper_lab import Authorization,stamp
from trading_agent.paper_execution_wire import execution_wire
from test_paper_lab import grant,IDENTITY,INTENT,NOW

class ExecutionWireTests(unittest.TestCase):
    def setUp(self):
        self.a=grant();self.auth=Authorization(lambda:self.a,lambda *args:True,lambda:NOW)
        self.gates=[];self.w=execution_wire(self.auth,lambda management=False:self.gates.append(management),
            intent_guard=lambda o,role,order_id,quantity=None:None) # Explicit synthetic grant; no network.
        self.w.expected=IDENTITY;self.w.verified=True;self.w.next_order_id=10
        self.calls=[]
        self.patches=[patch.object(self.w.client,'isConnected',return_value=True),patch.object(self.w.client,'serverVersion',return_value=226),
                      patch.object(self.w.client,'useProtoBuf',return_value=True),patch.object(self.w.client,'sendMsg',side_effect=lambda *a:self.calls.append(a)),
                      patch.object(self.w.client,'sendMsgProtoBuf',side_effect=lambda *a:self.calls.append(a))]
        for p in self.patches:p.start()
        self.o={'intent':INTENT,'quantity':'100','order_ids':[10,11,12],'entry':'1.1001','stop':'1.099','target':'1.1016','fills':{},'statuses':{},
                'quote':{'type':'LIVE','bid':'1.1000','ask':'1.1001','at':stamp()}}
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
    def test_official_sdk_serializes_three_scoped_bracket_legs_without_network(self):
        self.w.bracket(self.o,self.a)
        self.assertEqual(3,len(self.calls));self.assertEqual([False,False,False],self.gates)
        self.assertEqual({},self.w.approved)
        parent,_=self.w.make_order(self.o,0,self.a);tp,_=self.w.make_order(self.o,1,self.a);stop,_=self.w.make_order(self.o,2,self.a)
        self.assertEqual((False,False,True),(parent.transmit,tp.transmit,stop.transmit));self.assertEqual(2,stop.ocaType);self.assertEqual(INTENT,stop.ocaGroup)
    def test_unregistered_live_raw_proto_and_global_cancel_blocked(self):
        r,_=self.w.make_order(self.o,0,self.a)
        with self.assertRaises(PermissionError):self.w.client.placeOrder(10,self.w.contract(),r)
        with self.assertRaises(PermissionError):self.w.client.placeOrderProtoBuf(None)
        with self.assertRaises(PermissionError):self.w.client.cancelOrderProtoBuf(None)
        with self.assertRaises(PermissionError):self.w.client.reqGlobalCancel()
        self.a['live_enabled']=True
        with self.assertRaises(PermissionError):self.w.bracket(self.o,self.a)
        self.assertEqual([],self.calls)
    def test_only_parent_cancel_and_existing_oca_take_profit_modification(self):
        self.w.cancel_parent(self.o);self.assertEqual(1,len(self.calls))
        from ibapi.order_cancel import OrderCancel
        with self.assertRaises(PermissionError):self.w.client.cancelOrder(12,OrderCancel())
        q={'type':'LIVE','bid':'1.1000','ask':'1.1001','at':stamp()}
        self.o['fills']={'in':{'order_id':10,'client_id':82,'contract_id':12087792,'side':'BUY','quantity':'100'}}
        self.o['statuses']={'10':'Filled'}
        self.w.close_owned(self.o,100,q,self.a);self.assertEqual(2,len(self.calls))
        with self.assertRaises(PermissionError):self.w.close_owned(self.o,0,q,self.a)
    def test_modern_and_legacy_fee_callbacks_and_sanitized_readonly_error(self):
        self.w.commissionAndFeesReport(SimpleNamespace(execId='x',commissionAndFees=2,currency='USD'))
        self.w.commissionReport(SimpleNamespace(execId='y',commission=2,currency='USD'))
        self.w.error(10,0,321,'API read-only; private account must not be stored')
        events=self.w.drain();self.assertEqual(['commission','commission','readonly','reject'],[e['kind'] for e in events])
        self.assertNotIn('private',str(events))
    def test_execution_requires_exact_account_and_records_received_broker_time(self):
        e=SimpleNamespace(acctNumber=IDENTITY,execId='x',orderId=10,permId=20,clientId=82,side='BOT',shares=100,price=1.1,time='20261004 19:00:00 UTC')
        self.w.execDetails(6001,self.w.contract(),e);event=self.w.drain()[0]
        self.assertEqual('BUY',event['side']);self.assertEqual(e.time,event['broker_time_raw']);self.assertNotIn(IDENTITY,str(event))
        e.acctNumber='DU99995678';self.w.execDetails(6001,self.w.contract(),e);self.assertFalse(self.w.verified)
    def test_quote_rejects_stale_frozen_and_crossed_prices(self):
        for q in ({'type':'FROZEN','bid':1,'ask':1.1,'at':stamp()},
                  {'type':'LIVE','bid':2,'ask':1,'at':stamp()},
                  {'type':'LIVE','bid':1,'ask':1.1,'at':stamp(datetime.now(timezone.utc)-timedelta(seconds=6))}):
            with self.assertRaises(PermissionError):self.w.validate_quote(q)
    def test_late_request_callbacks_do_not_complete_or_contaminate_current_request(self):
        self.w.active_quote=7000;self.w.marketDataType(6004,1);self.w.tickPrice(6004,1,1.1,None)
        self.assertEqual(0,self.w.data_type);self.assertEqual({},self.w.quote_data)
        self.w.active_summary=7001;self.w.accountSummary(6002,IDENTITY,'CashBalance','999','EUR');self.w.accountSummaryEnd(6002)
        self.assertFalse(hasattr(self.w,'eur_cash'));self.assertFalse(self.w.summary_done.is_set())
        self.w.active_execution=7002;self.w.execDetailsEnd(6001);self.assertFalse(self.w.exec_done.is_set())
        self.assertNotEqual(self.w.request(),self.w.request())
    def test_missing_protobuf_fee_is_unknown_but_explicit_zero_is_received_data(self):
        from ibapi.protobuf.CommissionAndFeesReport_pb2 import CommissionAndFeesReport
        from ibapi.decoder import Decoder
        decoder=Decoder(self.w,226)
        missing=CommissionAndFeesReport(execId='x',currency='USD')
        decoder.processCommissionAndFeesReportMsgProtoBuf(missing.SerializeToString())
        self.assertEqual(['commission_unavailable'],[e['kind'] for e in self.w.drain()])
        zero=CommissionAndFeesReport(execId='x',currency='USD',commissionAndFees=0)
        decoder.processCommissionAndFeesReportMsgProtoBuf(zero.SerializeToString())
        event=self.w.drain()[0];self.assertEqual('commission',event['kind']);self.assertEqual('0.0',event['amount'])

    def test_native_history_is_read_only_closed_causal_and_ignores_late_callbacks(self):
        now=datetime.now(timezone.utc);opened=int((now-timedelta(minutes=30)).timestamp())
        def request(req,contract,end,duration,size,source,rth,format_date,keep,options):
            self.assertEqual(('30 D','15 mins','MIDPOINT',0,2,False),(duration,size,source,rth,format_date,keep))
            self.w.historicalData(req,SimpleNamespace(date=str(opened),open=1.1,high=1.2,low=1,close=1.15))
            self.w.historicalData(req,SimpleNamespace(date=str(int(now.timestamp())),open=1.1,high=1.2,low=1,close=1.15))
            self.w.historicalDataEnd(req,'','')
        with patch.object(self.w.client,'reqHistoricalData',side_effect=request),patch.object(self.w.client,'cancelHistoricalData') as cancel:
            rows=self.w.history(15)
        self.assertEqual(1,len(rows));self.assertEqual(15,rows[0]['minutes']);cancel.assert_called_once()
        self.assertIsNone(self.w.active_history);self.assertEqual([],self.calls)
        self.w.historicalDataEnd(999,'','');self.assertEqual(1,len(rows))
    def test_history_failure_cannot_fabricate_empty_or_ready_series(self):
        def request(req,*args):
            self.w.historicalData(req,SimpleNamespace(date='invalid',open=1.1,high=1.2,low=1,close=1.15))
            self.w.historicalDataEnd(req,'','')
        with patch.object(self.w.client,'reqHistoricalData',side_effect=request),patch.object(self.w.client,'cancelHistoricalData'):
            with self.assertRaisesRegex(PermissionError,'HISTORY_REQUEST_FAILED'):self.w.history(15)
        self.assertEqual([],self.calls);self.assertIsNone(self.w.active_history)
