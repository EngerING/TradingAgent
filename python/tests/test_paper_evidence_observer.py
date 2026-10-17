import copy
from datetime import datetime,timedelta,timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from trading_agent.paper_evidence_observer import (CONFIG,REQUIRED,Store,attach_evidence,classify,folder,
    load_spec,prepare,project,research_preflight,run,sessions_from,status,validate_config,validate_evidence)
from trading_agent.paper_evidence_wire import observer_wire
from trading_agent.broker import PaperOptions
from trading_agent.ai_strategy_researcher.contracts import encoded
from trading_agent.ai_strategy_researcher.runner import run as research_run
from ai_research_fixtures import fixture
from test_paper_account_capabilities import CapClient

CONFIGURATION=json.loads(Path(CONFIG).read_bytes())
BASE=datetime(2027,1,4,13,0,tzinfo=timezone.utc)


def sample(now,kind=1,bid='12',ask='12.01'):
    return dict(bid=bid,ask=ask,received_at=now.isoformat(),field_received_at=dict(bid=now.isoformat(),ask=now.isoformat()),
        market_data_type=kind,sizes={},source='IBKR_TWS_REQ_MKT_DATA',quote_source_timestamp=None)


def spec():
    return dict(config=copy.deepcopy(CONFIGURATION),registered_at=BASE.isoformat(),baseline_history_sha256='a'*64,
                baseline_deferred_ids=[],account_binding_sha256='b'*64)


def completed_rows(kind=1,missing=False,documented=False):
    # Synthetic authoritative receipt; production never constructs weekday templates.
    starts=[BASE+timedelta(days=i,hours=1) for i in range(28) if (BASE+timedelta(days=i)).weekday()<5][:20]
    sessions=[dict(day=a.strftime('%Y%m%d'),start=a.isoformat(),end=(a+timedelta(minutes=4)).isoformat()) for a in starts]
    coverage=dict(start=BASE.strftime('%Y%m%d-%H:%M:%S'),end=(starts[-1]+timedelta(days=1)).strftime('%Y%m%d-%H:%M:%S'),time_zone='UTC')
    rows=[dict(kind='STARTED',at=BASE.isoformat(),payload={},hash='x'),
          dict(kind='CALENDAR',payload=dict(sessions=sessions,coverage=coverage),hash='x')]
    for a in starts:
        for i in range(4):
            if missing and a==starts[0]:continue
            q=classify(sample(a+timedelta(minutes=i),kind),a+timedelta(minutes=i),CONFIGURATION)
            rows.append(dict(kind='QUOTE',payload=q,hash='x'))
    end=starts[-1]+timedelta(minutes=4)
    if documented:
        facts=[]
        for name in REQUIRED:
            value=True if name=='stock_etf_permissions' else 'TIERED' if name=='effective_fee_plan' else 100 if name=='SettledCash_USD' else 1 if name in ('effective_minimum_quantity','quantity_increment') else dict(reviewed_for_fully_funded_100_usd_long=True,compatible_with_study=True,conservative_roundtrip_cost_usd_at_minimum=.5)
            facts.append(dict(name=name,status='VERIFIED',value=value,observed_at=end.isoformat()))
        facts.append(dict(name='corporate_action_coverage',value='COMPLETE',coverage_start=BASE.isoformat(),coverage_end=end.isoformat()))
        rows.append(dict(kind='DOCUMENTED_EVIDENCE',payload=dict(facts=facts),hash='x'))
    return rows,end


class PaperEvidenceObserverTests(unittest.TestCase):
    def setup_study(self,d):
        fixture(d);p=Path(d,CONFIG);p.write_bytes(encoded(CONFIGURATION));return prepare(d,'study')

    def test_preregister_is_immutable_and_does_not_connect(self):
        with tempfile.TemporaryDirectory() as d:
            with patch('trading_agent.paper_evidence_observer.connect',side_effect=AssertionError('connection')):
                self.setup_study(d);self.assertEqual('PREREGISTERED_NOT_STARTED',status(d,'study')['study_status'])
            with self.assertRaises(FileExistsError):prepare(d,'study')
            self.assertFalse((folder(d,'study')/'journal.sqlite3').exists())

    def test_altered_spec_fails_hash_verification(self):
        with tempfile.TemporaryDirectory() as d:
            self.setup_study(d);(folder(d,'study')/'spec.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'TAMPERED'):load_spec(d,'study')

    def test_scope_and_bounds_cannot_relax_capital_live_or_session_count(self):
        for key,value in [('capital_usd',1000000),('environment','LIVE'),('symbol','SPY'),('sessions',19),('minimum_live_coverage',.1),('poll_seconds',1)]:
            c=copy.deepcopy(CONFIGURATION);c[key]=value
            with self.assertRaises(ValueError):validate_config(c)

    def test_real_calendar_ignores_closed_days_and_handles_early_close(self):
        c=dict(received_at=BASE.isoformat(),time_zone='America/New_York',liquid_hours='20270104:0930-20270104:1300;20270105:CLOSED')
        s=sessions_from(c,[],BASE);self.assertEqual(1,len(s));self.assertEqual('2027-01-04T18:00:00+00:00',s[0]['end'])

    def test_calendar_conflict_is_not_silently_merged(self):
        c=dict(received_at=BASE.isoformat(),time_zone='UTC',liquid_hours='20270104:1400-20270104:1800')
        schedule=[dict(day='20270104',start='20270104-14:00:00',end='20270104-19:00:00',time_zone='UTC')]
        with self.assertRaisesRegex(ValueError,'CONFLICT'):sessions_from(c,schedule,BASE)

    def test_stale_empty_calendar_and_ambiguous_dst_fail(self):
        c=dict(received_at=BASE.isoformat(),time_zone='America/New_York',liquid_hours='')
        with self.assertRaisesRegex(ValueError,'STALE'):sessions_from(c,[],BASE+timedelta(minutes=6))
        with self.assertRaisesRegex(ValueError,'MISSING'):sessions_from(c,[],BASE)
        c['liquid_hours']='20271107:0130-20271107:0300'
        with self.assertRaisesRegex(ValueError,'DST'):sessions_from(c,[],BASE)

    def test_market_types_are_distinct_and_frozen_is_stale(self):
        self.assertEqual(['LIVE','STALE','DELAYED','STALE','MISSING'],[classify(sample(BASE,k),BASE,CONFIGURATION)['status'] for k in (1,2,3,4,0)])

    def test_missing_price_not_zero_and_no_future_backfill(self):
        r=classify(sample(BASE,bid=None),BASE,CONFIGURATION);self.assertEqual('MISSING',r['status']);self.assertIsNone(r['bid']);self.assertIsNone(r['spread'])

    def test_crossed_nonfinite_and_future_timestamps_fail_quality(self):
        for q in (sample(BASE,bid='14'),sample(BASE,bid='NaN'),sample(BASE+timedelta(seconds=1))):
            r=classify(q,BASE,CONFIGURATION);self.assertTrue(r['flags']);self.assertEqual('MISSING',r['status'])

    def test_old_receipt_is_stale_and_exchange_time_remains_unknown(self):
        r=classify(sample(BASE),BASE+timedelta(seconds=31),CONFIGURATION);self.assertEqual('STALE',r['status']);self.assertIsNone(r['quote_source_timestamp']);self.assertFalse(r['executable'])

    def test_twenty_sessions_not_calendar_days_and_no_orders_or_billing(self):
        rows,end=completed_rows();r=project(spec(),rows,end);self.assertEqual(20,r['completed_sessions']);self.assertEqual('EXECUTION_CONSTRAINT_BLOCKED',r['decision'])
        self.assertGreater((end-BASE).days,20);self.assertEqual(0,r['openai_requests']);self.assertEqual(0,r['orders_sent'])

    def test_missing_day_counts_without_extending_study_until_good_days(self):
        rows,end=completed_rows(missing=True);r=project(spec(),rows,end);self.assertEqual(20,r['completed_sessions']);self.assertEqual(0,r['sessions'][0]['samples']);self.assertEqual('DATA_QUALITY_BLOCKED',r['decision'])

    def test_delayed_data_cannot_pass_live_coverage(self):
        rows,end=completed_rows(kind=3);self.assertEqual('DATA_QUALITY_BLOCKED',project(spec(),rows,end)['decision'])

    def test_duplicate_samples_cannot_inflate_coverage(self):
        rows,end=completed_rows();one=[r for r in rows if r['kind']=='QUOTE'][0]
        rows=[r for r in rows if r['kind']!='QUOTE']+[one]*1000
        r=project(spec(),rows,end);self.assertEqual(1,r['sessions'][0]['live_slots']);self.assertEqual('DATA_QUALITY_BLOCKED',r['decision'])

    def test_calendar_coverage_gap_prevents_claiming_consecutive_sessions(self):
        rows,end=completed_rows();rows[1]['payload'].pop('coverage');r=project(spec(),rows,end)
        self.assertFalse(r['consecutive_calendar_coverage_verified']);self.assertEqual('DATA_QUALITY_BLOCKED',r['decision'])

    def test_contract_day_covers_final_close_after_schedule_receipt_time(self):
        rows,end=completed_rows();last=rows[1]['payload']['sessions'][-1]
        rows[1]['payload']['coverage']['end']=(end-timedelta(minutes=1)).strftime('%Y%m%d-%H:%M:%S')
        day=last['day'];rows[1]['payload']['contract']=dict(time_zone='UTC',liquid_hours=day+':1400-'+day+':1404')
        r=project(spec(),rows,end);self.assertTrue(r['consecutive_calendar_coverage_verified'])
        self.assertEqual('EXECUTION_CONSTRAINT_BLOCKED',r['decision'])

    def test_research_summary_contains_observed_cost_inputs_without_measured_slippage(self):
        rows,end=completed_rows(documented=True);r=project(spec(),rows,end)
        self.assertAlmostEqual(.01,r['research_summary']['median_spread_usd']);self.assertEqual(.5,r['research_summary']['conservative_roundtrip_cost_usd_at_minimum'])
        self.assertEqual('UNKNOWN_NOT_MEASURED',r['research_summary']['slippage'])

    def test_only_fully_documented_good_study_prepares_budget_not_execution(self):
        rows,end=completed_rows(documented=True);r=project(spec(),rows,end)
        self.assertEqual('EVIDENCE_READY_FOR_RESEARCH',r['decision']);self.assertEqual('1.00',r['research_proposal']['max_cost_usd']);self.assertFalse(r['execution_authorized'])

    def test_missing_corporate_actions_blocks_ready(self):
        rows,end=completed_rows(documented=True);rows[-1]['payload']['facts'].pop()
        self.assertEqual('DATA_QUALITY_BLOCKED',project(spec(),rows,end)['decision'])

    def test_settled_cash_absence_insufficiency_and_expiry_are_not_available_funds(self):
        for value,age in ((0,0),(100,2)):
            rows,end=completed_rows(documented=True)
            f=next(f for f in rows[-1]['payload']['facts'] if f['name']=='SettledCash_USD');f.update(value=value,observed_at=(end-timedelta(days=age)).isoformat())
            self.assertIn('SettledCash_USD',project(spec(),rows,end)['required_unknown'])

    def test_affordable_minimum_cost_gate_uses_100_not_broker_million(self):
        rows,end=completed_rows(documented=True)
        next(f for f in rows[-1]['payload']['facts'] if f['name']=='effective_minimum_quantity')['value']=100
        self.assertEqual('EXECUTION_CONSTRAINT_BLOCKED',project(spec(),rows,end)['decision'])

    def test_journal_append_restart_status_readonly_and_tamper_detection(self):
        with tempfile.TemporaryDirectory() as d:
            self.setup_study(d);s=load_spec(d,'study');p=folder(d,'study')/'journal.sqlite3'
            store=Store(p,s);store.append('STARTED',{});store.close();before=p.read_bytes();status(d,'study');self.assertEqual(before,p.read_bytes())
            db=sqlite3.connect(p);db.execute("UPDATE events SET payload='{}' WHERE seq=1");db.commit();db.close()
            with self.assertRaisesRegex(ValueError,'TAMPERED'):status(d,'study')

    def test_unsafe_study_id_rejected(self):
        with self.assertRaisesRegex(ValueError,'SAFE_STUDY'):folder('.', '../escape')

    def test_transport_rejects_all_order_variants(self):
        w=observer_wire(PaperOptions('DU123',paper_mode_attested=True,timeout=.02),(CapClient,object,SimpleNamespace));w.connect()
        try:
            for name in ('placeOrder','placeOrderProtoBuf','cancelOrder','cancelOrderProtoBuf','reqGlobalCancel','exerciseOptions','reqAutoOpenOrders'):
                with self.assertRaises(PermissionError):getattr(w._client,name)(1)
        finally:w.disconnect()

    def test_sizes_and_last_timestamp_provenance_and_late_callbacks(self):
        w=observer_wire(PaperOptions('DU123',paper_mode_attested=True,timeout=.02),(CapClient,object,SimpleNamespace));w.connect();req=w._begin('quote')
        w.sizes={};w.size_times={};w.last_trade_at=None;w.marketDataType(req,1)
        w.tickSize(req,0,100);w.tickSize(req,8,12345);w.tickSize(req-1,3,99);w.tickString(req,45,1800000000)
        self.assertEqual('100',w.sizes['bid_size']);self.assertNotIn('ask_size',w.sizes);self.assertTrue(w.last_trade_at);w.marketDataType(req,3);self.assertEqual({},w.sizes);w.disconnect()

    def test_foreign_identity_disconnects_and_no_fallback_to_live(self):
        w=observer_wire(PaperOptions('DU123',paper_mode_attested=True,timeout=.02),(CapClient,object,SimpleNamespace));w.connect();w.managedAccounts('U123');self.assertFalse(w.connected);w.disconnect()

    def test_defer_real_openai_preflight_blocks_before_credentials_journal_or_provider(self):
        with tempfile.TemporaryDirectory() as d:
            fixture(d)
            with patch('trading_agent.ai_strategy_researcher.runner.worker_environment',side_effect=AssertionError('credentials')):
                with self.assertRaisesRegex(ValueError,'NEW_EVIDENCE'):research_run(d,'real',provider='openai')
            self.assertFalse((Path(d)/'artifacts/research/ai-strategy-research/journal.sqlite3').exists())

    def test_no_study_has_no_ready_evidence_or_billed_calls(self):
        with tempfile.TemporaryDirectory() as d:
            fixture(d);r=research_preflight(d);self.assertEqual('INSUFFICIENT_EVIDENCE',r['decision']);self.assertEqual([],r['ready_studies'])

    def test_document_attachment_requires_paper_bound_source_hash_and_recent_scope(self):
        with tempfile.TemporaryDirectory() as d:
            s=spec();p=Path(d,'artifacts/research/paper-evidence-observer/evidence/source.txt');p.parent.mkdir(parents=True);p.write_text('Operator verified Paper source')
            f=dict(name='effective_fee_plan',status='VERIFIED',value='TIERED',source='OPERATOR_VERIFIED_PAPER_DOCUMENT',source_path=str(p.relative_to(d)).replace('\\','/'),source_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),observed_at=BASE.isoformat())
            m=dict(environment='PAPER_TRADING',account_binding_sha256='b'*64,facts=[f]);validate_evidence(d,s,m,BASE)
            for key,value in [('environment','LIVE'),('account_binding_sha256','x')]:
                bad=copy.deepcopy(m);bad[key]=value
                with self.assertRaises(ValueError):validate_evidence(d,s,bad,BASE)
            p.write_text('changed')
            with self.assertRaisesRegex(ValueError,'TAMPERED'):validate_evidence(d,s,m,BASE)

    def test_identity_error_suspends_observer_and_resume_keeps_start_anchor(self):
        with tempfile.TemporaryDirectory() as d:
            self.setup_study(d)
            def deny(*a):raise PermissionError('PRIVATE_ACCOUNT_DETAIL_MUST_NOT_BE_LOGGED')
            r=run(d,'study',connector=deny,max_cycles=1);self.assertEqual('SUSPENDED',r['study_status'])
            p=folder(d,'study')/'journal.sqlite3';store=Store(p,load_spec(d,'study'),True)
            try:rows=store.rows();self.assertEqual(1,sum(r['kind']=='STARTED' for r in rows));self.assertNotIn('PRIVATE_ACCOUNT',str(rows))
            finally:store.close()

    def test_stop_signal_is_cooperative_and_own_study_only(self):
        with tempfile.TemporaryDirectory() as d:
            self.setup_study(d);dest=folder(d,'study');counter=[]
            def deny(*a):raise ConnectionError()
            def sleep(_):counter.append(1);(dest/'stop.request').write_text('STOP')
            r=run(d,'study',connector=deny,sleeper=sleep);self.assertEqual('STOPPED',r['study_status']);self.assertEqual(1,len(counter))

    def fake_reader(self,clock,fail_sample=False):
        class Reader:
            connected=True;events=[]
            def contract_details(self,symbol):
                return dict(con_id=42,symbol='F',currency='USD',security_type='STK',received_at=clock[0].isoformat(),time_zone='UTC',liquid_hours='20270104:1400-20270104:1800',minimum_size='0.0001',size_increment='0.0001')
            def recent_schedule(self):
                return dict(sessions=[dict(day='20270104',start='20270104-14:00:00',end='20270104-18:00:00',time_zone='UTC')],coverage=dict(start='20270101-00:00:00',end='20270105-00:00:00',time_zone='UTC'))
            def values(self,mode):return []
            def sample(self):
                if fail_sample:raise ConnectionError('not logged')
                return sample(clock[0])
            def disconnect(self):self.connected=False
        return Reader()

    def test_driver_records_quote_and_resumes_same_anchor_and_slots(self):
        with tempfile.TemporaryDirectory() as d:
            self.setup_study(d);clock=[BASE]
            def connector(*args):clock[0]=BASE+timedelta(hours=1);return self.fake_reader(clock)
            r=run(d,'study',connector=connector,clock=lambda:clock[0],max_cycles=1);self.assertEqual(1,r['observations'])
            r=run(d,'study',connector=connector,clock=lambda:clock[0],max_cycles=1);self.assertEqual(2,r['observations']);self.assertEqual(1,r['sessions'][0]['live_slots'])
            store=Store(folder(d,'study')/'journal.sqlite3',load_spec(d,'study'),True)
            try:self.assertEqual(1,sum(row['kind']=='STARTED' for row in store.rows()))
            finally:store.close()

    def test_driver_disconnection_records_missing_without_inventing_quote(self):
        with tempfile.TemporaryDirectory() as d:
            self.setup_study(d);clock=[BASE]
            def connector(*args):clock[0]=BASE+timedelta(hours=1);return self.fake_reader(clock,True)
            r=run(d,'study',connector=connector,clock=lambda:clock[0],max_cycles=1)
            self.assertEqual(0,r['observations']);self.assertEqual(1,r['interruptions'])

    def test_real_schedule_request_is_current_rth_and_requires_callback(self):
        w=observer_wire(PaperOptions('DU123',paper_mode_attested=True,timeout=.02),(CapClient,object,SimpleNamespace));w.connect();w.paced=lambda:None
        seen=[]
        def reply(req,contract,end,duration,size,what,use_rth,*args):
            seen.append((contract.symbol,end,duration,size,what,use_rth))
            w.historicalSchedule(req,'20270101-00:00:00','20270105-00:00:00','UTC',[SimpleNamespace(startDateTime='20270104-14:00:00',endDateTime='20270104-18:00:00',refDate='20270104')])
        w._client.reqHistoricalData=reply
        try:
            result=w.recent_schedule();self.assertEqual(('F','','30 D','1 day','SCHEDULE',1),seen[0]);self.assertEqual(1,len(result['sessions']))
            w._client.reqHistoricalData=lambda *a:None
            with self.assertRaises(TimeoutError):w.recent_schedule()
        finally:w.disconnect()

    def test_attach_documents_cannot_create_an_order_or_openai_request(self):
        with tempfile.TemporaryDirectory() as d:
            self.setup_study(d);s=load_spec(d,'study');dest=folder(d,'study')
            # ABSENT binding is deliberately not sufficient for operator evidence.
            with self.assertRaisesRegex(ValueError,'SCOPE'):validate_evidence(d,s,dict(environment='PAPER_TRADING',account_binding_sha256='ABSENT',facts=[]))
            self.assertFalse((dest/'journal.sqlite3').exists())


if __name__=='__main__':unittest.main()
