import copy
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from trading_agent.kronos.config import load
from trading_agent.kronos.contracts import classify,raw_frequencies,digest
from trading_agent.kronos.features import validate_input
from trading_agent.kronos.calibration import metrics,KronosCalibrationEngine,bucket
from trading_agent.kronos.predictor import KronosPredictionService
from trading_agent.kronos.evaluation import economic_profiles,required_gate,paired_benchmark
from trading_agent.kronos.adapter import choose_device
from trading_agent.kronos.projection import project
from trading_agent.kronos.persistence import source_request,profile_state_from_source

ROOT=Path(__file__).resolve().parents[2]
AT=datetime(2026,10,7,18,tzinfo=timezone.utc)
SIGNAL=dict(signal_id='original',strategy_id='frozen',direction='LONG',entry=1.12,stop_loss=1.11,take_profit=1.14,geometry_bucket='original')

def request(c):
    return dict(symbol='EUR/USD',timeframe='1H',as_of=AT.isoformat(),bars=[dict(opened_at=(AT-timedelta(hours=c['lookback']-i)).isoformat(),open=1.12,high=1.13,low=1.11,close=1.12) for i in range(c['lookback'])],
        source=dict(quality='AUTHENTIC',sha256='a'*64),signal=copy.deepcopy(SIGNAL),partition='FORWARD',regime='SIDEWAYS')

class FakeAdapter:
    telemetry={'device':'cpu','inference_seconds':.001};degraded=False
    def __init__(self,c):self.c=c;self.calls=0
    def samples(self,r):
        self.calls+=1
        return [[dict(open=1.12,high=1.15 if i%2 else 1.13,low=1.115,close=1.125) for _ in range(self.c['pred_len'])] for i in range(self.c['sample_count'])]

class InputTests(unittest.TestCase):
    def setUp(self):self.c=load(ROOT);self.r=request(self.c)
    def test_without_volume_is_explicit(self):self.assertEqual('WITHOUT_VOLUME',validate_input(self.r,self.c)['volume_mode'])
    def test_verified_volume(self):
        for b in self.r['bars']:b.update(volume=2,amount=2.24,volume_evidence='VERIFIED')
        self.assertEqual('WITH_VOLUME',validate_input(self.r,self.c)['volume_mode'])
    def test_synthetic_volume_rejected(self):
        self.r['bars'][0]['volume']=1
        with self.assertRaisesRegex(ValueError,'SYNTHETIC'):validate_input(self.r,self.c)
    def test_duplicate(self):
        self.r['bars'][1]['opened_at']=self.r['bars'][0]['opened_at']
        with self.assertRaisesRegex(ValueError,'DUPLICATE'):validate_input(self.r,self.c)
    def test_reversed(self):
        self.r['bars'].reverse()
        with self.assertRaises(ValueError):validate_input(self.r,self.c)
    def test_future_candle(self):
        self.r['bars'][-1]['opened_at']=AT.isoformat()
        with self.assertRaisesRegex(ValueError,'FUTURE'):validate_input(self.r,self.c)
    def test_missing_gap(self):
        self.r['bars'][0]['opened_at']=(AT-timedelta(hours=self.c['lookback']+4)).isoformat()
        with self.assertRaisesRegex(ValueError,'MISSING'):validate_input(self.r,self.c)
    def test_partial_bar_rejected(self):
        self.r['bars'][0]['opened_at']=(AT-timedelta(hours=self.c['lookback'],minutes=15)).isoformat()
        with self.assertRaisesRegex(ValueError,'ALIGNMENT'):validate_input(self.r,self.c)
    def test_corrupt_ohlc(self):
        self.r['bars'][0]['high']=1
        with self.assertRaisesRegex(ValueError,'CORRUPT'):validate_input(self.r,self.c)
    def test_nan(self):
        self.r['bars'][0]['close']=float('nan')
        with self.assertRaises(ValueError):validate_input(self.r,self.c)
    def test_stale(self):
        self.r['as_of']=(AT+timedelta(hours=4)).isoformat()
        with self.assertRaisesRegex(ValueError,'STALE'):validate_input(self.r,self.c)
    def test_incomplete_missing_field(self):
        del self.r['bars'][0]['close']
        with self.assertRaises(KeyError):validate_input(self.r,self.c)
    def test_timeframes_never_mixed(self):
        self.r['timeframe']='15m'
        with self.assertRaisesRegex(ValueError,'SCOPE'):validate_input(self.r,self.c)
    def test_provenance(self):
        self.r['source']['quality']='SYNTHETIC'
        with self.assertRaisesRegex(ValueError,'AUTHENTIC'):validate_input(self.r,self.c)
    def test_bounded_missing_is_reported_never_filled(self):
        for b in self.r['bars'][:32]:b['opened_at']=(datetime.fromisoformat(b['opened_at'])-timedelta(hours=1)).isoformat()
        self.assertEqual(1,validate_input(self.r,self.c)['missing_candles'])
    def test_exact_lookback(self):
        self.r['bars'].pop()
        with self.assertRaisesRegex(ValueError,'LOOKBACK'):validate_input(self.r,self.c)

class TrajectoryTests(unittest.TestCase):
    def test_tp(self):self.assertEqual('TP_FIRST',classify([dict(open=1.12,high=1.15,low=1.115,close=1.13)],SIGNAL))
    def test_sl(self):self.assertEqual('SL_FIRST',classify([dict(open=1.12,high=1.13,low=1.10,close=1.12)],SIGNAL))
    def test_both_stop_first(self):self.assertEqual('SL_FIRST',classify([dict(open=1.12,high=1.15,low=1.10,close=1.12)],SIGNAL))
    def test_adverse_gap(self):self.assertEqual('SL_FIRST',classify([dict(open=1.10,high=1.15,low=1.09,close=1.12)],SIGNAL))
    def test_neither(self):self.assertEqual('NEITHER',classify([dict(open=1.12,high=1.13,low=1.115,close=1.12)],SIGNAL))
    def test_invalid(self):self.assertEqual('INVALID',classify([dict(open=1.12,high=1.10,low=1.09,close=1.12)],SIGNAL))
    def test_short(self):
        s=dict(SIGNAL,direction='SHORT',stop_loss=1.14,take_profit=1.11)
        self.assertEqual('TP_FIRST',classify([dict(open=1.12,high=1.13,low=1.10,close=1.12)],s))
    def test_frequencies_not_renormalized(self):
        paths=[[dict(open=1.12,high=1.15,low=1.115,close=1.13)],[],[dict(open=1.12,high=1.13,low=1.115,close=1.12)]]
        f=raw_frequencies(paths,SIGNAL);self.assertEqual(1/3,f['raw_tp_frequency']);self.assertEqual(1/3,f['invalid_frequency'])

class CalibrationTests(unittest.TestCase):
    def setUp(self):self.c=load(ROOT)
    def prediction(self):return dict(symbol='EUR/USD',timeframe='1H',model_version='a',tokenizer_version='b',config_hash='c',regime='S',strategy_id='frozen',geometry_bucket='g',prediction_start=AT.isoformat(),raw_tp_frequency=.7,invalid_frequency=0)
    def rows(self):
        p=self.prediction();out=[]
        for i in range(120):
            end=AT-timedelta(hours=12*(120-i));out.append(dict(p,partition='CALIBRATION',prediction_start=(end-timedelta(hours=12)).isoformat(),prediction_end=end.isoformat(),observed_at=end.isoformat(),actual='TP_FIRST' if i%10<7 else 'SL_FIRST'))
        return out
    def test_insufficient(self):self.assertIsNone(KronosCalibrationEngine(self.c).probability(self.prediction(),[])['calibrated_probability'])
    def test_calibrated_uses_observed_not_invented(self):
        r=KronosCalibrationEngine(self.c).probability(self.prediction(),self.rows());self.assertEqual('CALIBRATED',r['state']);self.assertAlmostEqual(.7,r['calibrated_probability']);self.assertLess(r['lower95'],.7)
    def test_future_outcomes_embargoed(self):
        rows=self.rows()
        for r in rows:r['observed_at']=(AT+timedelta(days=1)).isoformat()
        self.assertEqual(0,KronosCalibrationEngine(self.c).probability(self.prediction(),rows)['sample_size'])
    def test_validation_not_training(self):
        rows=self.rows()
        for r in rows:r['partition']='VALIDATION'
        self.assertIsNone(KronosCalibrationEngine(self.c).probability(self.prediction(),rows)['calibrated_probability'])
    def test_no_timeframe_pooling(self):
        rows=self.rows()
        for r in rows:r['timeframe']='4H'
        self.assertEqual(0,KronosCalibrationEngine(self.c).probability(self.prediction(),rows)['sample_size'])
    def test_neither_counts_as_non_tp(self):
        stats=metrics([dict(raw_tp_frequency=.8,actual='TP_FIRST'),dict(raw_tp_frequency=.8,actual='NEITHER')]);self.assertEqual(.5,stats['observed_tp_rate']);self.assertEqual(.5,stats['tp_first_accuracy'])
    def test_brier(self):self.assertAlmostEqual(.04,metrics([dict(raw_tp_frequency=.8,actual='TP_FIRST')])['brier_score'])
    def test_bucket_boundary(self):self.assertEqual('70-75%',bucket(.70));self.assertEqual('80%+',bucket(.99))
    def test_degraded_invalid_paths(self):
        p=self.prediction();p['invalid_frequency']=.1
        self.assertEqual('CALIBRATION_DEGRADED',KronosCalibrationEngine(self.c).probability(p,self.rows())['state'])
    def test_invalid_historical_trajectories_cannot_train_calibration(self):
        rows=self.rows()
        for r in rows:r['invalid_frequency']=.1
        self.assertEqual(0,KronosCalibrationEngine(self.c).probability(self.prediction(),rows)['comparable_samples'])

class PredictorTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'artifacts');self.c=load(ROOT);self.a=FakeAdapter(self.c);self.s=KronosPredictionService(self.tmp.name,self.c,self.a,clock=lambda:AT)
    def tearDown(self):self.s.close();self.tmp.cleanup()
    def test_one_inference_for_three_profiles(self):
        r=request(self.c);a=self.s.submit(r);b=self.s.submit(copy.deepcopy(r));self.assertIs(a,b);p=a.result();self.assertEqual(1,self.a.calls);self.assertEqual(set(['R1','R5','R10']),set(p['consensus']['economic_profiles']))
    def test_different_signal_same_forecast_cache(self):
        r=request(self.c);a=self.s.predict(r);r['signal']['signal_id']='second';b=self.s.predict(r);self.assertEqual(1,self.a.calls);self.assertNotEqual(a['prediction_id'],b['prediction_id'])
    def test_input_mutation_invalidates_cache(self):
        r=request(self.c);self.s.predict(r);r['bars'][0]['close']=1.121;self.s.predict(r);self.assertEqual(2,self.a.calls)
    def test_artifact_hash(self):
        p=self.s.predict(request(self.c));import hashlib
        self.assertEqual(p['samples_sha256'],hashlib.sha256((Path(self.tmp.name)/p['samples_artifact']).read_bytes()).hexdigest())
    def test_model_failure_isolated(self):
        self.a.samples=Mock(side_effect=RuntimeError('MODEL_UNAVAILABLE'))
        with self.assertRaises(RuntimeError):self.s.predict(request(self.c))
        self.assertEqual('KRONOS_ERROR',self.s.state)
    def test_conflict_visible(self):
        r=request(self.c);r['signal'].update(direction='SHORT',stop_loss=1.14,take_profit=1.11)
        self.assertIn('TECHNICAL_KRONOS_DIRECTION_CONFLICT',self.s.predict(r)['consensus']['disagreements'])
    def test_no_subjective_probability(self):self.assertIsNone(self.s.predict(request(self.c))['calibrated_probability'])
    def test_future_request_rejected(self):
        r=request(self.c);r['as_of']=(AT+timedelta(minutes=1)).isoformat()
        with self.assertRaisesRegex(ValueError,'FUTURE'):self.s.predict(r)
    def test_cpu_fallback_selection(self):
        t=Mock();t.cuda.is_available.return_value=False
        self.assertEqual('cpu',choose_device(t,self.c)['device'])
    def test_low_vram_cpu(self):
        t=Mock();t.cuda.is_available.return_value=True;t.cuda.mem_get_info.return_value=(100,1000)
        self.assertEqual('cpu',choose_device(t,self.c)['device'])

class SafetyTests(unittest.TestCase):
    def test_oom_one_cpu_fallback(self):
        from trading_agent.kronos.adapter import LocalKronosAdapter
        class OOM(RuntimeError):pass
        t=Mock();t.cuda.OutOfMemoryError=OOM;a=LocalKronosAdapter(ROOT,load(ROOT));a.predictor=Mock()
        operation=Mock(side_effect=[OOM(),['cpu_result']]);self.assertEqual(['cpu_result'],a.with_oom_fallback(t,operation))
        self.assertEqual('cpu',a.telemetry['device']);self.assertTrue(a.degraded);self.assertEqual(2,operation.call_count)
    def test_cpu_failure_propagates_no_retry_loop(self):
        from trading_agent.kronos.adapter import LocalKronosAdapter
        class OOM(RuntimeError):pass
        t=Mock();t.cuda.OutOfMemoryError=OOM;a=LocalKronosAdapter(ROOT,load(ROOT));a.predictor=Mock();operation=Mock(side_effect=OOM())
        with self.assertRaises(OOM):a.with_oom_fallback(t,operation)
        self.assertEqual(2,operation.call_count)
    def test_required_unavailable_no_trade(self):self.assertEqual('NO_TRADE',required_gate(None,AT.isoformat(),3900,True)['decision'])
    def test_optional_unavailable_degraded(self):self.assertEqual('DEGRADED_MODE',required_gate(None,AT.isoformat(),3900,False)['reason'])
    def test_stale_rejected(self):self.assertEqual('NO_TRADE',required_gate(dict(candle_timestamp=(AT-timedelta(days=1)).isoformat()),AT.isoformat(),3900,True)['decision'])
    def test_r1_cannot_pay_commissions(self):self.assertEqual('COMMISSION_EXCEEDS_RISK_BUDGET',economic_profiles(SIGNAL,dict(calibrated_probability=.9,lower95=.85),load(ROOT))['R1']['reason'])
    def test_high_accuracy_negative_ev_rejected(self):
        s=dict(SIGNAL,take_profit=1.121)
        self.assertEqual('NO_TRADE',economic_profiles(s,dict(calibrated_probability=.99,lower95=.9),load(ROOT))['R10']['decision'])
    def test_configuration_live_rejected(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'artifacts') as d:
            p=Path(d)/'c.json';c=load(ROOT);c['live_enabled']=True;p.write_text(json.dumps(c))
            with self.assertRaises(ValueError):load(ROOT,p)
    def test_no_execution_imports(self):
        for p in (ROOT/'python/trading_agent/kronos').glob('*.py'):
            s=p.read_text(encoding='utf-8');self.assertNotIn('from ibapi',s);self.assertNotIn('import ibapi',s);self.assertNotIn('placeOrder(',s)
    def test_empty_dashboard_is_honest(self):self.assertEqual('KRONOS_UNAVAILABLE',project([])['status']);self.assertIsNone(project([])['calibration']['brier_score'])
    def test_empty_benchmark_no_profit(self):self.assertIsNone(paired_benchmark([],load(ROOT))['profiles']['R10']['delta_expectancy'])
    def test_source_path_traversal_rejected(self):
        e=dict(classification='SIMULATED_SHADOW',broker_orders=0,live_enabled=False,at=AT.isoformat(),details=dict(history_source=dict(path='../outside.json',sha256='a'*64)))
        src=dict(payload=e,revision=1,previous='',hash=digest([1,e,'']))
        with self.assertRaisesRegex(ValueError,'ARTIFACT_SCOPE'):source_request(ROOT,src,load(ROOT))

class BenchmarkPolicyTests(unittest.TestCase):
    def setUp(self):self.c=load(ROOT)
    def row(self,at,loss=True):
        signal=dict(signal_id=at,strategy_id='frozen',direction='LONG',entry=1.,stop_loss=.95,take_profit=1.2)
        bar=dict(opened_at=at,open=1.,high=1.05 if loss else 1.25,low=.94 if loss else .99,close=1.)
        return dict(partition='VALIDATION',prediction_start=at,prediction_end=(datetime.fromisoformat(at)+timedelta(hours=1)).isoformat(),
            signal=signal,future_bars=[bar],calibration=dict(calibrated_probability=.95,lower95=.9),consensus=dict(disagreements=[]))
    def test_first_loss_blocks_same_day(self):
        rows=[self.row('2026-10-05T13:00:00+00:00'),self.row('2026-10-05T15:00:00+00:00',False)]
        b=paired_benchmark(rows,self.c)['profiles']['R10']['BASELINE_ACTUAL'];self.assertEqual(1,b['trades']);self.assertEqual(1,b['rejected']['FIRST_LOSS_STOPS_DAY'])
    def test_next_day_allows_first_signal(self):
        rows=[self.row('2026-10-05T13:00:00+00:00'),self.row('2026-10-06T13:00:00+00:00',False)]
        self.assertEqual(2,paired_benchmark(rows,self.c)['profiles']['R10']['BASELINE_ACTUAL']['trades'])
    def test_positive_net_continues(self):
        rows=[self.row('2026-10-05T13:00:00+00:00',False),self.row('2026-10-05T15:00:00+00:00',False)]
        self.assertEqual(2,paired_benchmark(rows,self.c)['profiles']['R10']['BASELINE_ACTUAL']['trades'])
    def test_timezone_not_utc_midnight(self):
        rows=[self.row('2026-10-05T23:00:00+00:00'),self.row('2026-10-06T02:00:00+00:00',False)]
        self.assertEqual(1,paired_benchmark(rows,self.c)['profiles']['R10']['BASELINE_ACTUAL']['trades'])
    def test_calibration_not_oos(self):
        r=self.row('2026-10-05T13:00:00+00:00',False);r['partition']='CALIBRATION'
        self.assertEqual(0,paired_benchmark([r],self.c)['profiles']['R10']['BASELINE_ACTUAL']['trades'])
    def test_pending_is_not_win(self):
        r=self.row('2026-10-05T13:00:00+00:00',False);r['future_bars'][0].update(high=1.1,low=.99);r['signal']['hold_until']='2026-10-10T13:00:00+00:00'
        b=paired_benchmark([r],self.c)['profiles']['R10']['BASELINE_ACTUAL'];self.assertEqual(0,b['trades']);self.assertEqual(1,len(b['pending_positions']));self.assertIsNone(b['net_win_rate'])
    def test_pending_remains_blocked_across_later_windows(self):
        r=self.row('2026-10-05T13:00:00+00:00',False);r['future_bars'][0].update(high=1.1,low=.99);r['signal']['hold_until']='2026-10-10T13:00:00+00:00'
        b=paired_benchmark([r,self.row('2026-10-06T13:00:00+00:00',False)],self.c)['profiles']['R10']['BASELINE_ACTUAL']
        self.assertEqual(0,b['trades']);self.assertEqual(1,b['rejected']['POSITION_PENDING'])

class ProfileStateTests(unittest.TestCase):
    def setUp(self):
        self.c=load(ROOT);self.cal=dict(calibrated_probability=.9,lower95=.85)
        self.state={k:dict(equity=100.,consumed_loss=0.,reserved_usd=0.,pending=False,stopped_day=False,quality='VERIFIED_SHADOW_JOURNAL') for k in ('R1','R5','R10')}
    def evaluate(self):return economic_profiles(SIGNAL,self.cal,self.c,profile_state=self.state)
    def test_current_equity_reduces_risk_without_changing_fraction(self):
        self.state['R10']['equity']=80.
        self.assertEqual(8.,self.evaluate()['R10']['risk_budget']);self.assertEqual(5.,self.evaluate()['R5']['risk_budget'])
    def test_gains_do_not_raise_initial_absolute_cap(self):
        self.state['R10']['equity']=150.
        self.assertEqual(10.,self.evaluate()['R10']['risk_budget'])
    def test_consumed_losses_never_restored_by_gains(self):
        self.state['R10'].update(equity=150.,consumed_loss=18.)
        self.assertEqual(2.,self.evaluate()['R10']['risk_budget'])
    def test_loss_budget_exhaustion_blocks(self):
        self.state['R10']['consumed_loss']=20.
        self.assertEqual('CUMULATIVE_LOSS_LIMIT',self.evaluate()['R10']['reason'])
    def test_reservations_reduce_available_capital(self):
        baseline=self.evaluate()['R10']['quantity'];self.state['R10']['reserved_usd']=50.
        p=self.evaluate()['R10'];self.assertLess(p['quantity'],baseline);self.assertLessEqual(p['quantity']*SIGNAL['entry']+p['costs']+50.,100.)
    def test_pending_trade_blocks_until_reconciled(self):
        self.state['R10']['pending']=True
        self.assertEqual('RESULT_RECONCILIATION_PENDING',self.evaluate()['R10']['reason']);self.assertEqual(0.,self.evaluate()['R10']['quantity'])
    def test_first_loss_or_break_even_day_stops(self):
        self.state['R10']['stopped_day']=True
        self.assertEqual('FIRST_LOSS_STOPS_DAY',self.evaluate()['R10']['reason'])
    def test_missing_profile_is_unknown_not_capital100(self):
        del self.state['R10'];p=self.evaluate()['R10']
        self.assertEqual('PROFILE_STATE_UNKNOWN',p['reason']);self.assertIsNone(p['equity']);self.assertEqual(0.,p['quantity'])
    def test_source_uses_virtual_journal_and_local_day(self):
        event=dict(at='2026-10-06T02:00:00+00:00',state=dict(portfolio_metrics={'EURUSD_R10':dict(equity_realized='83',consumed_loss='17',pending_position=None,daily_stops={'2026-10-05':'NET_LOSS'})}))
        state=profile_state_from_source(event);self.assertEqual(83.,state['R10']['equity']);self.assertTrue(state['R10']['stopped_day']);self.assertEqual('UNKNOWN',state['R1']['quality'])
    def test_changed_equity_reuses_common_forecast_but_new_assessment(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'artifacts') as d:
            a=FakeAdapter(self.c);s=KronosPredictionService(d,self.c,a,clock=lambda:AT)
            try:
                r=request(self.c);r['profile_state']=copy.deepcopy(self.state);first=s.predict(r)
                r['profile_state']['R10']['equity']=80.;second=s.predict(r)
                self.assertEqual(1,a.calls);self.assertEqual(first['cache_key'],second['cache_key']);self.assertNotEqual(first['prediction_id'],second['prediction_id']);self.assertEqual(8.,second['consensus']['economic_profiles']['R10']['risk_budget'])
            finally:s.close()
    def test_restart_reuses_verified_artifact_without_model_call(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'artifacts') as d:
            a=FakeAdapter(self.c);s=KronosPredictionService(d,self.c,a,clock=lambda:AT)
            try:p=s.predict(request(self.c))
            finally:s.close()
            b=FakeAdapter(self.c);b.samples=Mock(side_effect=AssertionError('UNNECESSARY_INFERENCE'));s=KronosPredictionService(d,self.c,b,clock=lambda:AT)
            try:s.restore_forecast(p);s.predict(request(self.c));b.samples.assert_not_called()
            finally:s.close()
    def test_corrupt_persistent_samples_rejected(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'artifacts') as d:
            s=KronosPredictionService(d,self.c,FakeAdapter(self.c),clock=lambda:AT)
            try:
                p=s.predict(request(self.c));(Path(d)/p['samples_artifact']).write_bytes(b'corrupt')
                with self.assertRaisesRegex(ValueError,'HASH_INVALID'):s.restore_forecast(p)
            finally:s.close()

if __name__=='__main__':unittest.main()
