"""Read-only request lifecycle regression. No IBKR socket or actual grants."""
import copy,io,tempfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch
import unittest
from ibapi.client import EClient
from ibapi.message import OUT
from trading_agent.paper_execution_wire import execution_wire
from trading_agent.paper_lab import stamp
import test_paper_lab as fixtures

class ReadRequestTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.PaperLabTests();self.f.setUp()
        self.w=execution_wire(self.f.auth,lambda **kw:None,read_only=True);self.w.expected=fixtures.IDENTITY;self.w.verified=True
        p=patch.object(self.w.client,'isConnected',return_value=True);p.start();self.addCleanup(p.stop)
    def test_api226_summary_cancel_uses_official_legacy_serialization(self):
        with patch.object(self.w.client,'serverVersion',return_value=226),patch.object(self.w.client,'sendMsg') as legacy,patch.object(self.w.client,'sendMsgProtoBuf') as proto:
            self.w.client.cancelAccountSummary(6002)
            self.assertEqual((OUT.CANCEL_ACCOUNT_SUMMARY,'1\x006002\x00'),legacy.call_args.args);proto.assert_not_called()
    def test_compatibility_does_not_change_order_or_other_negotiated_protocols(self):
        with patch.object(self.w.client,'serverVersion',return_value=226):
            for request in (OUT.REQ_ACCOUNT_SUMMARY,OUT.PLACE_ORDER,OUT.CANCEL_ORDER,OUT.REQ_POSITIONS):
                self.assertEqual(EClient.useProtoBuf(self.w.client,request),self.w.client.useProtoBuf(request))
        with patch.object(self.w.client,'serverVersion',return_value=227):
            self.assertEqual(EClient.useProtoBuf(self.w.client,OUT.CANCEL_ACCOUNT_SUMMARY),self.w.client.useProtoBuf(OUT.CANCEL_ACCOUNT_SUMMARY))
    def test_repeated_account_queries_release_both_summary_subscriptions(self):
        subscriptions=set();peak=[]
        def summary(req,group,tags):
            if len(subscriptions)>=2:self.w.error(req,0,322,'Maximum summaries');return
            subscriptions.add(req);peak.append(len(subscriptions));self.w.accountSummaryEnd(req)
        def legacy(msg,data):
            self.assertEqual(OUT.CANCEL_ACCOUNT_SUMMARY,msg);subscriptions.remove(int(data.split('\x00')[1]))
        def updates(subscribe,account):
            if subscribe:self.w.accountDownloadEnd(account)
        with patch.object(self.w.client,'serverVersion',return_value=226),patch.object(self.w.client,'sendMsg',side_effect=legacy),patch.object(self.w.client,'sendMsgProtoBuf'),patch.object(self.w.client,'reqAccountSummary',side_effect=summary),patch.object(self.w.client,'reqAccountUpdates',side_effect=updates),patch.object(self.w.client,'reqAccountUpdatesMulti',side_effect=lambda req,*args:self.w.accountUpdateMultiEnd(req)),patch.object(self.w.client,'cancelAccountUpdatesMulti'):
            for _ in range(4):
                result=self.w.account_snapshot();self.assertIsNone(result['value'])
        self.assertEqual(set(),subscriptions);self.assertLessEqual(max(peak),2);self.assertEqual([],self.w.api_events)
    def test_rejected_summary_fails_immediately_without_fabricating_end(self):
        self.w.active_summary=6007;self.w.error(6007,0,322,'private '+fixtures.IDENTITY)
        with self.assertRaisesRegex(PermissionError,'PAPER_ACCOUNT_SUMMARY_REQUEST_FAILED'):self.w.wait(self.w.summary_done)
        r=self.w.read_diagnostics();last=r['request_trace'][-1]
        self.assertEqual(('reqAccountSummary','accountSummaryEnd',6007,'BROKER_ERROR'),(last['request'],last['callback_expected'],last['request_id'],last['result']))
        self.assertEqual([322],last['error_codes']);self.assertNotIn('SUMMARY_6007',self.w.account_completed);self.assertNotIn(fixtures.IDENTITY,str(r))
    def test_stale_summary_error_cannot_complete_a_new_request(self):
        self.w.active_summary=6008;self.w.error(6007,0,322,'late')
        self.assertFalse(self.w.summary_done.is_set());self.w.accountSummaryEnd(6008);self.w.wait(self.w.summary_done)
        self.assertEqual('COMPLETE',self.w.request_trace[-1]['result'])
    def test_missing_end_records_exact_request_and_socket_before_cleanup(self):
        self.w.active_summary=6007
        with patch.object(self.w.summary_done,'wait',return_value=False) as waited,self.assertRaisesRegex(TimeoutError,'PAPER_API_TIMEOUT'):self.w.wait(self.w.summary_done)
        waited.assert_called_once_with(10);r=self.w.request_trace[-1]
        self.assertEqual(6007,r['request_id']);self.assertEqual('TIMEOUT',r['result']);self.assertTrue(r['socket_connected']);self.assertTrue(r['identity_verified'])
    def test_missing_position_end_is_distinguished_from_summary_timeout(self):
        with patch.object(self.w.positions_done,'wait',return_value=False),self.assertRaises(TimeoutError):self.w.wait(self.w.positions_done)
        self.assertEqual('reqPositions',self.w.request_trace[-1]['request']);self.assertEqual('positionEnd',self.w.request_trace[-1]['callback_expected'])

class WorkerFailureAuditTests(unittest.TestCase):
    def test_review_failure_persists_request_diagnostics_and_keeps_emergency(self):
        from trading_agent.paper_lab_runner import run
        f=fixtures.PaperLabTests();f.setUp();f.w.disconnect=lambda:None
        original=f.w.snapshot;calls=[];diagnostics={'request_trace':[{'request':'reqAccountSummary','request_id':6007,'callback_expected':'accountSummaryEnd','result':'TIMEOUT','socket_connected':True}],'api_events':[{'request_id':6007,'code':322}]}
        def snapshot():
            calls.append(1)
            if len(calls)==2:raise TimeoutError('PAPER_API_TIMEOUT')
            return original()
        f.w.snapshot=snapshot;f.w.read_diagnostics=lambda:copy.deepcopy(diagnostics)
        base=Path(__file__).resolve().parents[2]/'artifacts'
        with tempfile.TemporaryDirectory(dir=base) as directory:
            root=Path(directory);(root/'.local').mkdir();(root/'.local/paper-lab.emergency').write_bytes(b'latched')
            with patch('trading_agent.paper_lab_runner.Authorization',return_value=f.auth),patch('trading_agent.paper_lab_runner.unseal',return_value={}),patch('trading_agent.paper_lab_runner.DotnetJournal',return_value=f.j),patch('trading_agent.paper_lab_runner.execution_wire',return_value=f.w),patch('trading_agent.paper_lab_runner.session_guard',return_value=None),patch('trading_agent.paper_lab_runner.validate_review_permit',return_value='synthetic-permit'),redirect_stdout(io.StringIO()),self.assertRaises(TimeoutError):
                run(root,review=True)
            self.assertEqual(b'latched',(root/'.local/paper-lab.emergency').read_bytes())
        event=f.j.events[-1];self.assertEqual('WORKER_SUSPENDED',event['event']);self.assertEqual(diagnostics,event['data']['wire'])
        self.assertTrue(f.j.state['emergency']);self.assertEqual({},f.j.state['orders']);self.assertEqual({},f.j.state['sessions']);self.assertEqual([],f.w.calls)
