"""MOCK price paths/providers exclusively for deterministic research tests."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from decimal import Decimal
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from trading_agent.eurusd_cost_aware_search import (catalogue,signals,path_exit,labels_for,calibrated,
    economics,MemorySimulator,ResearchSimulator,movement_requirements,profile,FOLDER,validate_sol_advice)
from trading_agent.eurusd_cost_aware_forward import (read_source,archived_analysis,Campaign,process_event,identifier)
from trading_agent.eurusd_paper_research import sha,encoded
from trading_agent.eurusd_shadow_research import configuration

ROOT=Path(__file__).resolve().parents[2]
AT='2026-10-01T12:00:00+00:00'
MOCK_COSTS=dict(openingCommission='2',closingCommission='2',spread='.0014',slippage='.00045',adverseGap='.00005',minimumQuantity='.01',quantityStep='.01',holdingCostStatus='MOCK_BOUNDED_COSTS_FOR_TESTS_ONLY',source='MOCK_COSTS_NOT_IBKR_EVIDENCE')

def forecast(p=.9,low=.85,status='CALIBRATED_RESEARCH_ESTIMATE'):
    return dict(status=status,probability=p,lower_95=low,family_adjusted_interval=[low,.99])

def signal(at=AT,target='.20'):
    return dict(strategy_id=catalogue()[0]['id'],side='BUY',signal_at=at,entry_at=at,entry_midpoint='1.12',stop_distance='.001',take_profit_distance=target,reasons=[],regime='UPTREND',calibration=forecast(),opportunity_id=sha(at))

def analysis():
    begin=datetime(2026,9,29,12,tzinfo=timezone.utc);higher=[];points=[];base=[]
    for i in range(25):
        at=begin+timedelta(hours=i);close=1.10+i*.0001
        if i==24:close=1.12
        higher.append(dict(opened_at=at.isoformat(),minutes=60,open=close,high=close+.00005,low=close-.00005,close=close))
        points.append(dict(closed_at=(at+timedelta(hours=1)).isoformat(),status='READY',ema_fast=1.1,ema_slow=1.09,rsi=60,macd=.01,macd_signal=.009,macd_histogram=.001,atr=.001,trend='UPTREND',volatility='NORMAL'))
        for j in range(4):
            t=at+timedelta(minutes=j*15);base.append(dict(opened_at=t.isoformat(),minutes=15,open=close,high=close+.00005,low=close-.00005,close=close))
    base.append(dict(opened_at=(begin+timedelta(hours=25)).isoformat(),minutes=15,open=1.12,high=1.12,low=1.12,close=1.12))
    return dict(normalized={'60':higher,'15':base},indicator_points={'60':points},quality={'60':{'missing_expected_openings':[]}})


class CatalogueTests(unittest.TestCase):
    def test_bounded_frozen_catalogue(self):
        c=catalogue();self.assertEqual(16,len(c));self.assertEqual(16,len({x['strategy_version'] for x in c}))
        self.assertEqual({'trend','breakout','momentum','mean_reversion'},{x['family'] for x in c})
        self.assertEqual(c,catalogue())
    def test_parameters_not_fitted_to_outcomes(self):
        for c in catalogue():
            self.assertEqual(2,c['stop_atr']);self.assertEqual([20,50],[c['indicators']['ema_fast'],c['indicators']['ema_slow']])
            self.assertEqual('PROPOSED_OFFLINE_NOT_ACTIVE',c['stage'])
    def test_retains_nosignal_and_warmup_opportunities(self):
        rows=signals(analysis(),catalogue()[0]);self.assertEqual(25,len(rows))
        self.assertIn('INDICATOR_WARMUP',rows[0]['reasons']);self.assertTrue(rows[-1]['reasons'])
    def test_breakout_uses_prior_structure_and_atr(self):
        c=next(x for x in catalogue() if x['family']=='breakout' and x['minutes']==60 and x['horizon']=='position')
        s=signals(analysis(),c)[-1];self.assertEqual('BUY',s['side']);self.assertEqual('0.036',s['take_profit_distance'])
        self.assertLess(Decimal(s['structure']['prior_high']),Decimal(s['entry_midpoint']))
    def test_future_highs_do_not_change_signal_geometry(self):
        c=catalogue()[0];a=analysis();before=signals(a,c)[20];a['normalized']['60'][-1]['high']=999
        self.assertEqual(before,signals(a,c)[20])
    def test_missing_native_next_open_is_not_invented(self):
        a=analysis();a['normalized']['15'].pop()
        self.assertIn('NO_AUTHENTIC_NEXT_OPEN',signals(a,catalogue()[0])[-1]['reasons'])
    def test_unexplained_gap_blocks_candidate(self):
        a=analysis();a['quality']['60']['missing_expected_openings']=[a['normalized']['60'][22]['opened_at']]
        self.assertIn('UNEXPLAINED_DATA_GAP',signals(a,catalogue()[0])[-1]['reasons'])
    def test_mean_reversion_does_not_force_huge_target_to_pay_fees(self):
        c=next(x for x in catalogue() if x['family']=='mean_reversion' and x['minutes']==60)
        a=analysis();a['indicator_points']['60'][-2]['rsi']=29;a['indicator_points']['60'][-1].update(rsi=31,trend='SIDEWAYS',ema_fast=1.121)
        s=signals(a,c)[-1];self.assertAlmostEqual(.001,float(s['take_profit_distance']))


class EconomicTests(unittest.TestCase):
    def test_seventy_percent_wins_negative_ev_rejected(self):
        r=economics(dict(admitted=True,net_target='.1',risk='3'),forecast(.7,.65))
        self.assertLess(Decimal(r['expected_value']),0);self.assertEqual('NO_TRADE',r['decision'])
    def test_positive_point_ev_negative_interval_rejected(self):
        r=economics(dict(admitted=True,net_target='10',risk='5'),forecast(.9,.1))
        self.assertGreater(Decimal(r['expected_value']),0);self.assertEqual('NO_TRADE',r['decision'])
    def test_positive_ev_below_uncertainty_buffer_rejected(self):
        r=economics(dict(admitted=True,net_target='1',risk='1'),forecast(.6,.6))
        self.assertEqual('0.2',r['expected_value']);self.assertEqual('NO_TRADE',r['decision'])
    def test_cost_gate_cannot_be_overridden_by_probability(self):
        r=economics(dict(admitted=False,reason='TARGET_DOES_NOT_COVER_COSTS',net_target='-4',risk='5'),forecast(1,1))
        self.assertEqual('TARGET_DOES_NOT_COVER_COSTS',r['reason']);self.assertIsNone(r['break_even_win_rate'])
    def test_insufficient_sample_never_uses_subjective_confidence(self):
        r=economics(dict(admitted=True,net_target='20',risk='5'),{**forecast(status='INSUFFICIENT_EVIDENCE'),'confidence':1})
        self.assertEqual('NO_TRADE',r['decision'])
    def test_break_even_uses_net_win_and_cost_inclusive_loss(self):
        r=economics(dict(admitted=True,net_target='10',risk='5'),forecast())
        self.assertAlmostEqual(1/3,float(r['break_even_win_rate']));self.assertEqual('TRADE',r['decision'])
    def test_r1_fees_exceed_risk(self):
        sim=MemorySimulator(profile(ROOT,'EURUSD_R1'),MOCK_COSTS,catalogue()[0])
        self.assertEqual('COMMISSION_EXCEEDS_RISK_BUDGET',sim.enter(signal())['reason'])
    def test_unknown_holding_costs_cannot_admit_even_positive_calibrated_ev(self):
        costs={**MOCK_COSTS,'holdingCostStatus':'UNKNOWN'}
        sim=MemorySimulator(profile(ROOT,'EURUSD_R10'),costs,catalogue()[0])
        self.assertEqual('HOLDING_COST_EVIDENCE_UNKNOWN',sim.enter(signal())['reason'])
    def test_r5_r10_same_signal_different_sizing_only(self):
        s=signal();s['stop_distance']='.02';sizes=[]
        for name in ('EURUSD_R5','EURUSD_R10'):
            sim=MemorySimulator(profile(ROOT,name),MOCK_COSTS,catalogue()[0]);sizes.append(sim.size(s,AT))
        self.assertLess(Decimal(sizes[0]['quantity']),Decimal(sizes[1]['quantity']))
        self.assertEqual('1.12',s['entry_midpoint']);self.assertEqual('.02',s['stop_distance'])
    def test_exposure_plus_friction_reserved_within_usd100(self):
        sim=MemorySimulator(profile(ROOT,'EURUSD_R10'),MOCK_COSTS,catalogue()[0]);d=sim.size(signal(),AT)
        self.assertLessEqual(Decimal(d['notional'])+Decimal(d['costs']),100)
    def test_gains_do_not_change_risk_percentage(self):
        sim=MemorySimulator(profile(ROOT,'EURUSD_R5'),MOCK_COSTS,catalogue()[0]);sim.enter(signal());sim.close('1.32','2026-10-01T13:00:00+00:00','TAKE_PROFIT')
        self.assertGreater(Decimal(sim.state['equity']),100);self.assertEqual('0.05',sim.profile['risk_fraction']);self.assertLessEqual(Decimal(sim.size(signal('2026-10-01T14:00:00+00:00'), '2026-10-01T14:00:00+00:00')['risk']),5)
    def test_first_net_loss_stops_day_not_next_day(self):
        sim=MemorySimulator(profile(ROOT,'EURUSD_R10'),MOCK_COSTS,catalogue()[0]);sim.enter(signal());sim.close('1.119','2026-10-01T13:00:00+00:00','STOP')
        self.assertEqual('DAILY_FIRST_LOSS_STOP',sim.enter(signal('2026-10-01T14:00:00+00:00'))['reason'])
        self.assertTrue(sim.enter(signal('2026-10-02T12:00:00+00:00'))['admitted'])
    def test_pending_commission_is_not_a_win(self):
        sim=MemorySimulator(profile(ROOT,'EURUSD_R10'),MOCK_COSTS,catalogue()[0]);sim.enter(signal());sim.close('1.32','2026-10-01T13:00:00+00:00','TAKE_PROFIT',commission_pending=True)
        self.assertEqual('RESULT_RECONCILIATION_PENDING',sim.enter(signal('2026-10-01T14:00:00+00:00'))['reason']);self.assertEqual(0,sim.metrics()['completed_trades'])
    def test_movement_geometry_accounts_for_both_fees_friction_gap(self):
        rows=movement_requirements(ROOT,MOCK_COSTS,Decimal('1.12'),Decimal('.002'))
        self.assertEqual('0',rows[0]['quantity_eur']);self.assertIsNone(rows[0]['movements']['net_1_usd']['pips'])
        for row in rows[1:]:
            qty=Decimal(row['quantity_eur']);delta=Decimal(row['movements']['net_3_usd']['movement_usd_per_eur'])
            self.assertAlmostEqual(3,float(qty*delta-Decimal(row['costs_and_uncertainty_usd'])))


class PricePathCalibrationTests(unittest.TestCase):
    def position(self):return dict(strategy=catalogue()[0]['id'],side='BUY',entry_at=AT,stop='1.11',target='1.14')
    def bar(self,**changes):return dict(opened_at=AT,minutes=15,open='1.12',high='1.13',low='1.115',close='1.12',**changes)
    def test_ambiguous_bar_stop_first(self):
        b=self.bar();b.update(high='1.15',low='1.10')
        self.assertEqual('STOP_AMBIGUOUS',path_exit(self.position(),b,catalogue()[0])[1])
    def test_adverse_gap_not_capped_to_stop(self):
        b=self.bar();b.update(open='1.09',high='1.10',low='1.08',close='1.09')
        self.assertEqual('1.09',path_exit(self.position(),b,catalogue()[0])[0])
    def test_horizon_exit_at_next_observed_open(self):
        b=self.bar();b.update(opened_at='2026-10-07T12:00:00+00:00')
        self.assertEqual(('1.12','HORIZON_NEXT_OBSERVED_OPEN',b['opened_at']),path_exit(self.position(),b,catalogue()[0]))
    def test_horizon_open_does_not_credit_favorable_gap_beyond_target(self):
        b=self.bar();b.update(opened_at='2026-10-07T12:00:00+00:00',open='1.16',high='1.17',low='1.15',close='1.16')
        self.assertEqual('1.14',path_exit(self.position(),b,catalogue()[0])[0])
    def test_future_resolved_labels_cannot_calibrate_present(self):
        l=dict(strategy=catalogue()[0]['id'],side='BUY',regime='UPTREND',signal_at='2026-09-20T12:00:00+00:00',resolved_at='2026-10-02T12:00:00+00:00',outcome='TP')
        r=calibrated([l],configuration(ROOT)['probability'],[],signal(),AT)
        self.assertEqual(0,r['sample_size']);self.assertEqual('INSUFFICIENT_EVIDENCE',r['status']);self.assertEqual(1,r['censor_fraction'])
    def test_nonoverlapping_paths_not_three_portfolio_samples(self):
        a=analysis();s=signal(a['normalized']['15'][-3]['opened_at']);s.pop('calibration');s['take_profit_distance']='.2'
        t=deepcopy(s);t.update(entry_at=a['normalized']['15'][-2]['opened_at'],signal_at=a['normalized']['15'][-2]['opened_at'])
        rows=labels_for(a,catalogue()[0],[s,t]);self.assertEqual(2,len(rows));self.assertEqual([True,False],[r['calibration_eligible'] for r in rows])
    def test_zero_sample_calibration_error_unknown(self):
        r=calibrated([],configuration(ROOT)['probability'],[],signal(),AT)
        self.assertIsNone(r['calibration_error']);self.assertIsNone(r['probability']);self.assertFalse(r['model_generated_probability'])
    def test_other_regime_and_side_not_comparable(self):
        l=dict(strategy=catalogue()[0]['id'],side='SELL',regime='RANGE',signal_at='2026-09-20T12:00:00+00:00',resolved_at='2026-09-21T12:00:00+00:00',outcome='TP')
        self.assertEqual(0,calibrated([l],configuration(ROOT)['probability'],[],signal(),AT)['sample_size'])


class PersistenceTests(unittest.TestCase):
    def test_loss_survives_restarting_candidate_simulator(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'arm.sqlite3';p=profile(ROOT,'EURUSD_R10');candidate=catalogue()[0]
            sim=ResearchSimulator(path,p,MOCK_COSTS,candidate);sim.enter(signal());sim.close('1.119','2026-10-01T13:00:00+00:00','STOP');loss=sim.state['consumed_loss'];sim.db.close()
            restored=ResearchSimulator(path,p,MOCK_COSTS,candidate)
            try:
                self.assertEqual(loss,restored.state['consumed_loss']);self.assertEqual('DAILY_FIRST_LOSS_STOP',restored.enter(signal('2026-10-01T14:00:00+00:00'))['reason'])
            finally:restored.db.close()
    def test_candidate_journal_immutable(self):
        with tempfile.TemporaryDirectory() as temp:
            sim=ResearchSimulator(Path(temp)/'arm.sqlite3',profile(ROOT,'EURUSD_R10'),MOCK_COSTS,catalogue()[0])
            try:
                with self.assertRaises(sqlite3.IntegrityError):sim.db.execute('DELETE FROM events')
            finally:sim.db.close()
    def test_source_absent_is_not_created_or_treated_as_zero(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError,'UNAVAILABLE'):read_source(Path(temp),'eurusd-shadow-'+'a'*32,0,'',lambda *a:None)
            self.assertEqual([],list(Path(temp).iterdir()))
    def test_source_chain_and_postgres_head_must_match(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);study='eurusd-shadow-'+'a'*32;folder=root/'artifacts/research/eurusd-shadow'/study;folder.mkdir(parents=True)
            db=sqlite3.connect(folder/'journal.sqlite3');db.execute('CREATE TABLE events(revision INTEGER,payload TEXT,previous TEXT,hash TEXT)')
            body=dict(study_id=study);digest=sha([1,body,'']);db.execute('INSERT INTO events VALUES(1,?,?,?)',(encoded(body).decode(),'',digest));db.commit();db.close()
            self.assertEqual(1,len(read_source(root,study,0,'',lambda *a:dict(revision=1,hash=digest))))
            with self.assertRaisesRegex(ValueError,'NOT_RECONCILED'):read_source(root,study,0,'',lambda *a:dict(revision=1,hash='b'*64))
            self.assertEqual([],read_source(root,study,0,'',lambda *a:dict(revision=2,hash='b'*64)))
    def test_archive_path_traversal_rejected(self):
        with self.assertRaisesRegex(ValueError,'PATH_REQUIRED'):archived_analysis(ROOT,dict(history_source=dict(path='../../secrets.json')),AT)
    def test_identifier_traversal_rejected(self):
        for value in ('../shadow','forward-xxx','eurusd-shadow-'+'a'*33):
            with self.assertRaises(ValueError):identifier(value,'eurusd-shadow')
    def test_forward_preregistration_restores_and_prevents_edit(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)/FOLDER/('forward-'+'a'*32);folder.mkdir(parents=True)
            c=Campaign(temp,folder.name);c.state=dict(status='PREPARED_NOT_RUNNING');c.append('REGISTERED',dict(openai_calls=0));head=c.head;c.db.close()
            restored=Campaign(temp,folder.name)
            try:
                self.assertEqual(head,restored.head)
                with self.assertRaises(sqlite3.IntegrityError):restored.db.execute('UPDATE events SET hash=?',('b'*64,))
            finally:restored.db.close()


class ForwardIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);root=Path(self.temp.name)
        (root/'config').mkdir()
        for name in ('eurusd-shadow-research.json','eurusd-paper-research-100.json'):(root/'config'/name).write_bytes((ROOT/'config'/name).read_bytes())
        folder=root/FOLDER/('forward-'+'a'*32);folder.mkdir(parents=True)
        self.c=Campaign(root,folder.name);self.addCleanup(self.c.db.close)
        self.candidate=next(x for x in catalogue() if x['family']=='breakout' and x['minutes']==60 and x['horizon']=='position')
        self.a=analysis();self.at=self.a['indicator_points']['60'][-1]['closed_at']
        self.c.state=dict(started_at=(datetime.fromisoformat(self.at)-timedelta(minutes=1)).isoformat(),
            protocol=dict(candidates=[self.candidate],profiles=configuration(ROOT)['profiles'],costs=MOCK_COSTS,folds=[]),
            source_revision=0,source_hash='',portfolio_heads={},portfolio_metrics={},pending_paths={},forward_labels=[],seen=[],status='PREPARED')
        for name in configuration(ROOT)['profiles']:
            arm=self.candidate['id']+'-'+name;sim=ResearchSimulator(folder/(arm+'.sqlite3'),profile(root,name),MOCK_COSTS,self.candidate)
            self.c.state['portfolio_heads'][arm]=sim.head;sim.db.close()
        self.event=dict(event='COMMON_MARKET_OPPORTUNITY_EVALUATED',state=dict(last_observation=self.at),details=dict(
            quote=dict(at=self.at,bid='1.11999',ask='1.12001',type='LIVE',market_status='OPEN',available_for_execution=True),history_source={},features={'source':'MOCK'}))
    def step(self,revision=1,late=False):
        clock=lambda:datetime.fromisoformat(self.at)+timedelta(seconds=60 if late else 1)
        process_event(self.c,revision,'b'*64,self.event,{self.candidate['id']:[]},analysis_loader=lambda *a:self.a,clock=clock)
        return json.loads(self.c.db.execute('SELECT payload FROM events ORDER BY revision DESC LIMIT 1').fetchone()[0])['details']
    def test_same_opportunity_sent_to_all_three_profiles(self):
        d=self.step()['decisions'][0];self.assertEqual(set(configuration(ROOT)['profiles']),set(d['profiles']))
        self.assertEqual(1,len(self.c.state['seen']));self.assertIsNotNone(d['signal']['opportunity_id'])
    def test_rejected_signal_keeps_counterfactual_path_not_a_trade(self):
        d=self.step()['decisions'][0]
        self.assertTrue(all(not p['admitted'] for p in d['profiles'].values()))
        self.assertEqual(1,len(self.c.state['pending_paths']));self.assertTrue(all(m['completed_trades']==0 for m in self.c.state['portfolio_metrics'].values()))
    def test_repeated_observation_does_not_duplicate_entries_or_labels(self):
        self.step();d=self.step(2)['decisions'][0]
        self.assertTrue(all(p['reason']=='OPPORTUNITY_ALREADY_EVALUATED' for p in d['profiles'].values()))
        self.assertEqual(1,len(self.c.state['pending_paths']));self.assertEqual(1,len(self.c.state['seen']))
    def test_late_consumer_never_backfills_shadow_entry(self):
        d=self.step(late=True)['decisions'][0]
        self.assertTrue(all(p['reason']=='SIDECAR_LATE_NO_BACKFILLED_ENTRY' for p in d['profiles'].values()))
    def test_counterfactual_outcome_of_rejected_signal_is_persisted(self):
        self.step();at=datetime.fromisoformat(self.at)
        self.a['normalized']['15'][-1].update(low='1.0',high='1.12',close='1.0')
        self.event['state']['last_observation']=(at+timedelta(minutes=15)).isoformat()
        self.event['details']['quote']['at']=self.event['state']['last_observation'];self.step(2)
        self.assertEqual(1,len(self.c.state['forward_labels']));self.assertEqual('SL',self.c.state['forward_labels'][0]['outcome'])
        self.assertTrue(all(m['completed_trades']==0 for m in self.c.state['portfolio_metrics'].values()))
    def test_portfolio_head_conflict_suspends_before_blind_retry(self):
        self.c.state['portfolio_heads'][next(iter(self.c.state['portfolio_heads']))]='0'*64
        with self.assertRaisesRegex(ValueError,'RECONCILIATION_REQUIRED'):self.step()
    def test_pre_start_observations_do_not_open_historical_positions(self):
        self.c.state['started_at']=(datetime.fromisoformat(self.at)+timedelta(minutes=15)).isoformat()
        d=self.step();self.assertEqual(1,d['revision']);self.assertEqual([],self.c.state['seen'])


class SolContractTests(unittest.TestCase):
    def test_valid_advice_stays_separate_even_when_model_says_trade(self):
        result=validate_sol_advice(dict(recommendation='TRADE',reasons=['MOCK'],hypothesis='Investigate alternative horizon with new evidence'))
        self.assertFalse(result['automatic_adoption']);self.assertFalse(result['execution_authorized'])
    def test_model_generated_probability_rejected(self):
        with self.assertRaises(ValueError):validate_sol_advice(dict(recommendation='TRADE',reasons=[],hypothesis=None,probability=.99))
    def test_risk_override_rejected(self):
        with self.assertRaises(ValueError):validate_sol_advice(dict(recommendation='TRADE',reasons=[],hypothesis=None,risk=15))
    def test_malformed_response_rejected(self):
        for bad in (None,{},dict(recommendation='TRADE',reasons='reason',hypothesis=None)):
            with self.subTest(value=bad),self.assertRaises(ValueError):validate_sol_advice(bad)

if __name__=='__main__':unittest.main()
