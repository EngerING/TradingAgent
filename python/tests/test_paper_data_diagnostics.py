import unittest
import copy,json,io,tempfile,os
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
from trading_agent.paper_lab import Authorization,stamp
from trading_agent.paper_data_diagnostics import account_value,currency_cash,session_status,quote_observation,exposure_check
from trading_agent.paper_execution_wire import execution_wire
from test_paper_lab import grant,IDENTITY,NOW

def row(tag,value,currency='EUR',source='SUMMARY'):return account_value(source,tag,value,currency)
def book(at=NOW):return {'bid':('1.10',stamp(at)),'ask':('1.1002',stamp(at))}

class AccountCashDiagnosticsTests(unittest.TestCase):
    def test_prefixed_explicit_zero_is_confirmed_not_missing(self):
        result=currency_cash([row('$LEDGER-CashBalance','0')],{'SUMMARY'})
        self.assertEqual('CONFIRMED_ZERO',result['state']);self.assertEqual('0',result['value'])
        self.assertEqual('$LEDGER-CashBalance',result['evidence'][0]['raw_tag'])
    def test_missing_eur_is_unknown_even_with_zero_positions_and_usd_cash(self):
        result=currency_cash([row('CashBalance','1000000','USD')],{'SUMMARY'})
        self.assertEqual('UNKNOWN',result['state']);self.assertIsNone(result['value'])
    def test_nonzero_positive_and_negative_cash_are_existing_exposure(self):
        for value in ('100','-100'):
            self.assertEqual('EXISTING_EXPOSURE',currency_cash([row('CashBalance',value)],{'SUMMARY'})['state'])
    def test_base_alias_resolves_from_account_level_values_not_ledger_currency(self):
        rows=[row('NetLiquidation','100','USD'),row('TotalCashValue','100','USD'),row('$LEDGER-CashBalance','0','BASE')]
        self.assertIsNone(currency_cash(rows,{'SUMMARY'})['value'])
        self.assertEqual('CONFIRMED_ZERO',currency_cash(rows,{'SUMMARY'},currency='USD')['state'])
        self.assertIsNone(currency_cash([row('Currency','USD','USD')],{'SUMMARY'})['base_currency'])
    def test_conflicting_sources_and_not_ready_do_not_admit_cash(self):
        rows=[row('CashBalance','0'),row('CashBalance','1',source='UPDATES')]
        self.assertEqual('CONFLICTING_CURRENCY_CASH',currency_cash(rows,{'SUMMARY','UPDATES'})['reason'])
        self.assertEqual('ACCOUNT_NOT_READY',currency_cash([row('CashBalance','0'),row('AccountReady','false','')],{'SUMMARY'})['reason'])
    def test_incomplete_source_and_settled_cash_are_not_confirmed_eur_balance(self):
        self.assertEqual('UNKNOWN',currency_cash([row('CashBalance','0')],set())['state'])
        self.assertEqual('UNKNOWN',currency_cash([row('SettledCash','0')],{'SUMMARY'})['state'])
    def test_identity_and_segment_fields_never_enter_cash_observations(self):
        for tag in ('AccountCode','$LEDGER-AccountOrGroup','CashBalance-S','TotalCashValue-C'):
            self.assertIsNone(account_value('SUMMARY',tag,IDENTITY,'EUR'))
        with self.assertRaises(ValueError):row('CashBalance','NaN')
    def test_other_currency_exposure_and_missing_ready_are_explicit(self):
        rows=[row('NetLiquidation','100','USD'),row('CashBalance','0'),row('CashBalance','20','GBP')]
        result=currency_cash(rows,{'SUMMARY'})
        self.assertIsNone(result['account_ready']);self.assertEqual('GBP',result['other_currency_exposure'][0]['currency'])
    def test_completed_download_without_currency_has_explicit_absence_not_zero(self):
        result=currency_cash([row('CashBalance','1000000','USD')],{'SUMMARY','UPDATES'},expected_sources={'SUMMARY','UPDATES'})
        self.assertEqual('COMPLETE',result['query_status']);self.assertEqual('EUR_ROW_ABSENT',result['row_status'])
        self.assertEqual('UNKNOWN',result['state']);self.assertIsNone(result['value'])
    def test_one_complete_source_with_zero_does_not_hide_incomplete_other_source(self):
        result=currency_cash([row('CashBalance','0')],{'SUMMARY'},expected_sources={'SUMMARY','UPDATES'})
        self.assertEqual('INCOMPLETE',result['query_status']);self.assertEqual('QUERY_INCOMPLETE',result['row_status'])
        self.assertEqual(['UPDATES'],result['missing_sources']);self.assertIsNone(result['value'])
    def test_currency_row_without_total_cash_is_present_but_balance_unknown(self):
        result=currency_cash([row('Currency','EUR')],{'SUMMARY'})
        self.assertEqual('ROW_PRESENT',result['row_status']);self.assertEqual('CURRENCY_BALANCE_NOT_REPORTED',result['reason'])
        self.assertEqual('UNKNOWN',result['state'])
    def test_download_end_with_api_error_is_not_successful_cash_certification(self):
        result=currency_cash([row('CashBalance','0')],{'SUMMARY'},errors=['SUMMARY_ERROR_321'])
        self.assertEqual('ERROR',result['query_status']);self.assertIsNone(result['value'])
    def test_explicit_zero_remains_zero_with_all_expected_sources_complete(self):
        result=currency_cash([row('CashBalance','0')],{'SUMMARY','UPDATES'},expected_sources={'SUMMARY','UPDATES'})
        self.assertEqual('CONFIRMED_ZERO',result['state']);self.assertEqual('ROW_PRESENT',result['row_status'])

class MarketDiagnosticsTests(unittest.TestCase):
    def test_official_finite_session_open_closed_unknown_and_end_boundary(self):
        hours='20261004:1715-20261005:1700;20261006:CLOSED'
        for at,expected in [('2026-10-04T21:14:59Z','CLOSED'),('2026-10-04T21:15:00Z','OPEN'),('2026-10-05T21:00:00Z','CLOSED'),('2026-10-06T18:00:00Z','CLOSED'),('2026-10-10T21:15:00Z','UNKNOWN')]:
            self.assertEqual(expected,session_status(hours,'US/Eastern',datetime.fromisoformat(at.replace('Z','+00:00'))))
    def test_dst_and_malformed_schedule_fail_closed(self):
        winter=datetime(2026,12,2,22,15,tzinfo=timezone.utc)
        self.assertEqual('OPEN',session_status('20261202:1715-20261203:1700','America/New_York',winter))
        for hours in ('bad','20261101:0130-20261101:0230'):
            self.assertEqual('UNKNOWN',session_status(hours,'America/New_York',winter))
    def test_realtime_current_and_open_only_is_usable(self):
        self.assertTrue(quote_observation(1,book(),'OPEN',[],NOW,tick_count=2)['available_for_execution'])
    def test_frozen_delayed_and_delayed_frozen_remain_non_executable(self):
        for kind in (2,3,4):
            q=quote_observation(kind,book(),'OPEN',[],NOW,tick_count=2)
            self.assertFalse(q['available_for_execution']);self.assertIn(q['type'],q['reasons'])
    def test_closed_market_and_stale_prices_are_distinct(self):
        self.assertIn('MARKET_CLOSED',quote_observation(1,book(),'CLOSED',[],NOW)['reasons'])
        self.assertIn('STALE_TICKS',quote_observation(1,book(NOW-timedelta(seconds=6)),'OPEN',[],NOW)['reasons'])
    def test_subscription_error_no_ticks_and_adapter_error_are_distinct(self):
        self.assertIn('SUBSCRIPTION_MISSING',quote_observation(0,{},'OPEN',[354],NOW)['reasons'])
        self.assertIn('NO_TICKS',quote_observation(1,{},'OPEN',[],NOW)['reasons'])
        self.assertIn('NO_BID_ASK_TICKS',quote_observation(1,{},'OPEN',[],NOW,tick_count=4)['reasons'])
        self.assertIn('ADAPTER_ERROR',quote_observation(1,{},'OPEN',[321],NOW)['reasons'])
    def test_crossed_and_future_prices_are_rejected(self):
        crossed=book();crossed['bid']=('2',stamp(NOW))
        self.assertIn('INVALID_OR_CROSSED_QUOTE',quote_observation(1,crossed,'OPEN',[],NOW)['reasons'])
        self.assertIn('STALE_TICKS',quote_observation(1,book(NOW+timedelta(seconds=1)),'OPEN',[],NOW)['reasons'])
    def test_unclassified_or_partial_subscription_error_blocks_even_with_prices(self):
        for code in (9999,10090):
            result=quote_observation(1,book(),'OPEN',[code],NOW,tick_count=2)
            self.assertFalse(result['available_for_execution']);self.assertIn('BROKER_DATA_ERROR',result['reasons'])

class AdapterDiagnosticsTests(unittest.TestCase):
    def wire(self):
        a=grant();auth=Authorization(lambda:a,lambda *args:True,lambda:NOW)
        w=execution_wire(auth,lambda **kw:None,read_only=True);w.expected=IDENTITY;w.verified=True
        return w
    def test_readonly_mode_blocks_all_order_methods_even_with_an_approved_payload(self):
        w=self.wire()
        for method,args in ((w.client.placeOrder,(1,None,None)),(w.client.placeOrderProtoBuf,(None,)),(w.client.cancelOrder,(1,None)),(w.client.cancelOrderProtoBuf,(None,))):
            with self.assertRaisesRegex(PermissionError,'READ_ONLY_DIAGNOSTIC_NO_ORDERS'):method(*args)
    def test_summary_updates_and_multi_confirm_same_explicit_zero(self):
        w=self.wire();w.active_summary=6001;w.active_updates=True;w.active_multi=6002
        w.accountSummary(6001,IDENTITY,'$LEDGER-CashBalance','0','EUR');w.accountSummaryEnd(6001)
        w.updateAccountValue('CashBalance','0','EUR',IDENTITY);w.accountDownloadEnd(IDENTITY)
        w.accountUpdateMulti(6002,IDENTITY,'','$LEDGER-TotalCashBalance','0','EUR');w.accountUpdateMultiEnd(6002)
        self.assertEqual('CONFIRMED_ZERO',currency_cash(w.account_rows,w.account_completed)['state'])
        self.assertNotIn(IDENTITY,str(w.account_rows))
    def test_wrong_account_aggregate_and_model_are_rejected(self):
        for account in ('All','DUR99995678'):
            w=self.wire();w.active_summary=6001;w.accountSummary(6001,account,'CashBalance','0','EUR')
            self.assertFalse(w.verified);self.assertEqual([],w.account_rows)
        w=self.wire();w.active_multi=6002;w.accountUpdateMulti(6002,IDENTITY,'foreign-model','CashBalance','0','EUR')
        self.assertIn('UNEXPECTED_ACCOUNT_MODEL',w.account_errors)
    def test_late_account_callbacks_do_not_confirm_a_new_generation(self):
        w=self.wire();w.active_multi=6003;w.accountUpdateMulti(6002,IDENTITY,'','CashBalance','0','EUR');w.accountUpdateMultiEnd(6002)
        w.updateAccountValue('CashBalance','0','EUR',IDENTITY)
        self.assertEqual([],w.account_rows);self.assertFalse(w.multi_done.is_set())
    def test_duplicate_data_type_preserves_prices_and_initial_type_can_follow_ticks(self):
        w=self.wire();w.active_quote=6001
        w.tickPrice(6001,1,1.1,None);w.tickPrice(6001,2,1.1002,None)
        w.marketDataType(6001,1);w.marketDataType(6001,1)
        self.assertEqual(2,len(w.quote_data));w.marketDataType(6001,2);self.assertEqual({},w.quote_data)
    def test_sentinel_removes_a_previous_price_and_delayed_ticks_keep_their_family(self):
        w=self.wire();w.active_quote=6001;w.marketDataType(6001,1)
        w.tickPrice(6001,1,1.1,None);w.tickPrice(6001,1,-1,None);self.assertNotIn('bid',w.quote_data)
        w.marketDataType(6001,3);w.tickPrice(6001,1,1.1,None);self.assertNotIn('bid',w.quote_data)
        w.tickPrice(6001,66,1.1,None);self.assertEqual('DELAYED',w.quote_family['bid'])
    def test_request_error_is_classified_without_becoming_an_order_rejection(self):
        w=self.wire();w.active_quote=6001;w.error(6001,0,354,'private '+IDENTITY)
        self.assertEqual([354],w.request_errors[6001]);self.assertEqual([],w.drain());self.assertNotIn(IDENTITY,str(w.api_events))
    def test_observe_current_quote_from_official_callbacks_without_network(self):
        w=self.wire();w.trading_session={'hours':'20261004:0000-20261005:0000','timezone':'UTC','received_at':stamp(NOW)}
        def received(req,*args):
            w.tickPrice(req,1,1.1,None);w.tickPrice(req,2,1.1002,None);w.marketDataType(req,1)
        with patch.object(w.client,'isConnected',return_value=True),patch.object(w.client,'reqMarketDataType'),patch.object(w.client,'reqMktData',side_effect=received),patch.object(w.client,'cancelMktData'),patch('trading_agent.paper_execution_wire.utc',return_value=NOW),patch('trading_agent.paper_execution_wire.stamp',return_value=stamp(NOW)):
            self.assertTrue(w.observe_quote(timeout=.01)['available_for_execution'])
        self.assertIsNone(w.active_quote)
    def test_subscription_cancellation_is_not_an_order_rejection(self):
        w=self.wire();w.error(-1,0,2100,'unsubscribed '+IDENTITY)
        self.assertEqual([],w.drain());self.assertEqual(2100,w.api_events[0]['code'])
    def test_strict_snapshot_still_blocks_unknown_cash(self):
        w=self.wire()
        def missing():w.eur_cash=None;w.base_currency='USD';w.initial_margin=None;return {'state':'UNKNOWN','other_currency_exposure':[]}
        with patch.object(w.client,'isConnected',return_value=True),patch.object(w.client,'reqAllOpenOrders',side_effect=w.openOrderEnd),patch.object(w.client,'reqPositions',side_effect=w.positionEnd),patch.object(w.client,'cancelPositions'),patch.object(w.client,'reqExecutions',side_effect=lambda req,f:w.execDetailsEnd(req)),patch.object(w.client,'reqCompletedOrders',side_effect=lambda api:w.completedOrdersEnd()),patch.object(w,'account_snapshot',side_effect=missing):
            with self.assertRaisesRegex(PermissionError,'EUR_CASH_RECONCILIATION_UNAVAILABLE'):w.snapshot()
            self.assertIsNone(w.snapshot(diagnostic=True)['eur_cash'])
    def test_portfolio_callback_requires_active_exact_account_and_ignores_late_data(self):
        w=self.wire();contract=w.contract()
        w.updatePortfolio(contract,100,1,100,1,0,0,IDENTITY);self.assertEqual([],w.portfolio_rows)
        w.active_updates=True;w.updatePortfolio(contract,100,1,100,1,0,0,IDENTITY)
        self.assertEqual('100',w.portfolio_rows[0]['quantity']);self.assertNotIn(IDENTITY,str(w.portfolio_rows))
        w.updatePortfolio(contract,0,1,0,1,0,0,'DUR99995678');self.assertFalse(w.verified)
    def test_account_specific_positions_complete_and_cancel_without_network(self):
        w=self.wire()
        def receive(req,account,model):
            self.assertEqual(IDENTITY,account);self.assertEqual('',model)
            w.positionMulti(req,account,model,w.contract(),100,1.1);w.positionMultiEnd(req)
        with patch.object(w.client,'isConnected',return_value=True),patch.object(w.client,'reqPositionsMulti',side_effect=receive),patch.object(w.client,'cancelPositionsMulti') as cancel:
            result=w.additional_exposure()
        self.assertEqual('COMPLETE',result['status']);self.assertEqual('100',result['positions'][0]['quantity'])
        cancel.assert_called_once();self.assertIsNone(w.active_positions_multi);self.assertNotIn(IDENTITY,str(result))
    def test_positions_timeout_and_late_end_never_confirm_empty_exposure(self):
        w=self.wire()
        with patch.object(w.client,'isConnected',return_value=True),patch.object(w.client,'reqPositionsMulti'),patch.object(w.client,'cancelPositionsMulti'),patch.object(w,'wait',side_effect=TimeoutError):
            result=w.additional_exposure()
        self.assertEqual('INCOMPLETE',result['status']);w.positionMultiEnd(w.request_id)
        self.assertFalse(w.positions_multi_done.is_set())
    def test_positions_multi_foreign_account_or_model_fail_closed(self):
        for account,model in (('DUR99995678',''),(IDENTITY,'foreign-model')):
            w=self.wire();w.active_positions_multi=6001;w.positionMulti(6001,account,model,w.contract(),0,1)
            self.assertFalse(w.verified);self.assertEqual([],w.multi_positions)
            self.assertEqual(['POSITION_SCOPE_MISMATCH'],w.exposure_errors)

class JointExposureTests(unittest.TestCase):
    def snapshot(self,rows=None):
        rows=[row('NetLiquidation','100','USD'),row('CashBalance','0')] if rows is None else rows
        return {'cash_reconciliation':currency_cash(rows,{'SUMMARY'}),'positions':[],'portfolio':[],'foreign_positions':[],'orders':[]}
    def additional(self):return {'status':'COMPLETE','positions':[],'errors':[]}
    def test_empty_positions_and_orders_do_not_certify_absent_eur(self):
        result=exposure_check(self.snapshot([row('CashBalance','1000000','USD')]),self.additional(),{})
        self.assertEqual('BLOCKED',result['status']);self.assertIsNone(result['eur_balance'])
        self.assertFalse(result['automatic_cash_certification']);self.assertEqual('EUR_ROW_ABSENT',result['cash_row_status'])
    def test_explicit_zero_requires_all_exposure_sources_and_journal_clear(self):
        self.assertEqual('FLAT_CONFIRMED',exposure_check(self.snapshot(),self.additional(),{})['status'])
        additional=self.additional();additional['status']='INCOMPLETE'
        self.assertIn('EXPOSURE_QUERY_INCOMPLETE',exposure_check(self.snapshot(),additional,{})['reasons'])
        self.assertIn('JOURNAL_RECONCILIATION_REQUIRED',exposure_check(self.snapshot(),self.additional(),{'intent':{}})['reasons'])
    def test_real_cash_zero_with_virtual_forex_or_open_orders_still_blocks(self):
        for source in ('positions','portfolio'):
            snapshot=self.snapshot();snapshot[source]=[{'quantity':'100','security_type':'CASH'}]
            self.assertIn('POSITION_EXPOSURE_PRESENT',exposure_check(snapshot,self.additional(),{})['reasons'])
        additional=self.additional();additional['positions']=[{'quantity':'-100'}]
        self.assertIn('POSITION_EXPOSURE_PRESENT',exposure_check(self.snapshot(),additional,{})['reasons'])
        snapshot=self.snapshot();snapshot['orders']=[{'order_id':42}]
        self.assertIn('OPEN_ORDERS_PRESENT',exposure_check(snapshot,self.additional(),{})['reasons'])

class InspectionSafetyTests(unittest.TestCase):
    def test_fresh_inspection_binding_cannot_be_used_for_execution(self):
        from trading_agent.paper_lab_diagnostics import InspectionAuthorization
        now=datetime.now(timezone.utc);a=grant();candidate={'account':IDENTITY,'port':7497,'observed_at':stamp(now)}
        from trading_agent.ibkr_session import SessionConfiguration
        auth=InspectionAuthorization.__new__(InspectionAuthorization);auth.root=Path('.');auth.process={'pid':2,'started':'2'};auth.configuration=SessionConfiguration()
        def loader(path):return copy.deepcopy(candidate if path.name=='ibkr-paper-candidate.dpapi' else a)
        with patch('trading_agent.paper_lab_diagnostics.unseal',side_effect=loader),patch('trading_agent.paper_lab.same_process',return_value=True),patch.dict(os.environ,{'LIVE_TRADING':'false'}):
            self.assertTrue(auth.read(management=True)['inspection_only'])
            with self.assertRaisesRegex(PermissionError,'INSPECTION_ONLY_NO_EXECUTION'):auth.read()
            candidate['account']='DUR99995678'
            with self.assertRaisesRegex(PermissionError,'FRESH_EXACT_IDENTITY_REQUIRED'):auth.read(management=True)
    def test_stale_inspection_and_private_exception_text_are_blocked(self):
        from trading_agent.paper_lab_diagnostics import InspectionAuthorization,safe_reason
        now=datetime.now(timezone.utc);a=grant();candidate={'account':IDENTITY,'port':7497,'observed_at':stamp(now-timedelta(minutes=3))}
        from trading_agent.ibkr_session import SessionConfiguration
        auth=InspectionAuthorization.__new__(InspectionAuthorization);auth.root=Path('.');auth.process={'pid':2,'started':'2'};auth.configuration=SessionConfiguration()
        with patch('trading_agent.paper_lab_diagnostics.unseal',side_effect=lambda p:copy.deepcopy(candidate if p.name=='ibkr-paper-candidate.dpapi' else a)):
            with self.assertRaisesRegex(PermissionError,'FRESH_EXACT_IDENTITY_REQUIRED'):auth.read(management=True)
        self.assertEqual('ValueError',safe_reason(ValueError(IDENTITY)))
    def test_diagnosis_never_renews_grant_or_clears_emergency_even_when_flat(self):
        from trading_agent.paper_lab_diagnostics import inspect
        a=grant();a['expires_at']=stamp(NOW+timedelta(minutes=30))
        state={'emergency':True,'sessions':{},'orders':{},'strategy_capital':{'initial':100,'loss_allowance':20,'equity':'100','consumed_loss':'0'}}
        commits=[]
        journal=SimpleNamespace(load=lambda scope:{'revision':7,'state':copy.deepcopy(state)},commit=lambda scope,rev,current,event:commits.append((rev,current,event)))
        wire=SimpleNamespace(connect=lambda record:[IDENTITY],client=SimpleNamespace(serverVersion=lambda:226),
            snapshot=lambda **kw:{'cash_reconciliation':{'state':'CONFIRMED_ZERO','base_currency':'USD','value':'0','query_status':'COMPLETE','row_status':'ROW_PRESENT'},'orders':[],'foreign_positions':[],'positions':[]},
            additional_exposure=lambda:{'status':'COMPLETE','positions':[],'errors':[]},
            contract_details=lambda:{'contract_id':12087792},trading_session={'hours':'synthetic','timezone':'UTC'},
            observe_quote=lambda:{'type':'LIVE','reasons':[],'available_for_execution':True},api_events=[],read_diagnostics=lambda:{'request_trace':[],'api_events':[]},disconnect=lambda:None)
        wire.connected=True;wire.session=SimpleNamespace(binding=SimpleNamespace(masked_account='***5678'))
        base=Path(__file__).resolve().parents[2]/'artifacts';base.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as directory:
            root=Path(directory);(root/'.local').mkdir();grant_path=root/'.local/paper-lab-authorization.dpapi';grant_path.write_bytes(b'protected fixture');stop=root/'.local/paper-lab.emergency';stop.write_bytes(b'latched fixture')
            auth=SimpleNamespace(read=lambda **kw:copy.deepcopy(a))
            with patch('trading_agent.paper_lab_diagnostics.InspectionAuthorization',return_value=auth),patch('trading_agent.paper_lab_diagnostics.DotnetJournal',return_value=journal),patch('trading_agent.paper_lab_diagnostics.execution_wire',return_value=wire) as factory,patch('trading_agent.ibkr_session.session_guard',return_value=wire.session),redirect_stdout(io.StringIO()):inspect(root)
            self.assertTrue(factory.call_args.kwargs['read_only']);self.assertEqual(b'protected fixture',grant_path.read_bytes());self.assertEqual(b'latched fixture',stop.read_bytes())
            self.assertEqual(state,commits[0][1]);report=json.loads((root/'artifacts/paper-lab/data-diagnostics.json').read_text())
            self.assertFalse(report['execution_enabled']);self.assertEqual(0,report['orders_sent']);self.assertEqual('FLAT_CONFIRMED',report['reconciliation'])
