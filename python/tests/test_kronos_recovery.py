"""Recovery tests use fixtures only; no broker, model download or paid API."""
import copy
from contextlib import nullcontext, redirect_stdout
from datetime import timedelta
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from test_kronos import ROOT, AT, SIGNAL, FakeAdapter, request
from trading_agent.kronos.config import load, config_hash
from trading_agent.kronos.contracts import classify, digest, raw_frequencies
from trading_agent.kronos.features import validate_input
from trading_agent.kronos.predictor import KronosPredictionService
from trading_agent.kronos.projection import project
from trading_agent.kronos.worker import finalize_predictions, run


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.c=load(ROOT)
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'artifacts')
        self.adapter=FakeAdapter(self.c)
        self.service=KronosPredictionService(self.temp.name,self.c,self.adapter,clock=lambda:AT)
        self.p=self.service.predict(request(self.c))
    def tearDown(self):
        self.service.close();self.temp.cleanup()
    def future(self):
        return [dict(opened_at=(AT+timedelta(hours=i)).isoformat(),open=1.12,high=1.15,low=1.115,close=1.13) for i in range(self.c['pred_len'])]
    def context(self):
        r=request(self.c);r['as_of']=(AT+timedelta(hours=12)).isoformat();r['bars']=self.future()
        return r
    def evaluate(self,r=None,bars=None):
        journal=Mock();summary=finalize_predictions(journal,[dict(kind='PREDICTION',payload=self.p)],r or self.context(),bars)
        return journal,summary
    def test_failed_inference_retries_identical_window(self):
        self.service.pending.clear();self.service.cache.clear()
        self.adapter.samples=Mock(side_effect=[RuntimeError('TRANSIENT_MODEL_ERROR'),FakeAdapter(self.c).samples(request(self.c))])
        with self.assertRaises(RuntimeError):self.service.submit(request(self.c)).result()
        p=self.service.submit(request(self.c)).result()
        self.assertEqual('KRONOS_READY',p['status']);self.assertEqual(2,self.adapter.samples.call_count)
    def test_barrier_hit_does_not_hide_invalid_later_step(self):
        path=self.future();path[-1]['high']=1.
        self.assertEqual('INVALID',classify(path,SIGNAL))
        f=raw_frequencies([self.future(),path],SIGNAL)
        self.assertEqual(.5,f['raw_tp_frequency']);self.assertEqual(.5,f['invalid_frequency'])
    def test_valid_outcome_is_persisted_with_source(self):
        j,s=self.evaluate();out=j.append.call_args.args[1]
        self.assertEqual(1,s['newly_observed']);self.assertEqual('TP_FIRST',out['actual'])
        self.assertEqual(self.context()['source'],out['market_source']);self.assertGreater(out['mae'],0)
    def test_no_signal_still_evaluates_price_not_barriers(self):
        self.p['signal']=None;self.p['raw_tp_frequency']=None
        j,_=self.evaluate();out=j.append.call_args.args[1]
        self.assertIsNone(out['actual']);self.assertIsNone(out['brier_component']);self.assertIsNotNone(out['mae'])
    def test_immature_forecast_is_not_scored(self):
        r=self.context();r['as_of']=AT.isoformat()
        j,s=self.evaluate(r);j.append.assert_not_called();self.assertEqual(0,s['newly_observed'])
    def test_missing_observation_stays_pending_then_recovers(self):
        r=self.context();r['bars'].pop()
        j,s=self.evaluate(r);j.append.assert_not_called();self.assertEqual('MISSING_OUTCOME_CANDLES',s['pending'][0]['reason'])
        j,s=self.evaluate();self.assertEqual(1,s['newly_observed']);self.assertEqual(self.context()['as_of'],j.append.call_args.args[1]['observed_at'])
    def test_full_archive_evaluates_forecast_outside_model_context(self):
        r=self.context();r['bars']=[]
        j,s=self.evaluate(r,self.future());self.assertEqual(1,s['newly_observed']);self.assertEqual([],r['bars'])
    def test_duplicates_block_scoring(self):
        bars=self.future();bars.append(copy.deepcopy(bars[-1]))
        j,s=self.evaluate(bars=bars);j.append.assert_not_called();self.assertEqual('DUPLICATE_OUTCOME_CANDLES',s['pending'][0]['reason'])
    def test_corrupt_observation_does_not_produce_mae(self):
        bars=self.future();bars[-1]['high']=1.
        j,s=self.evaluate(bars=bars);j.append.assert_not_called();self.assertEqual('CORRUPT_OUTCOME_OHLC',s['pending'][0]['reason'])
    def test_timezone_offsets_match_same_utc_instant(self):
        bars=self.future()
        for b in bars:b['opened_at']=b['opened_at'].replace('+00:00','Z')
        _,s=self.evaluate(bars=bars);self.assertEqual(1,s['newly_observed'])
    def test_other_symbol_cannot_score_eurusd_forecast(self):
        r=self.context();r['symbol']='F';j,_=self.evaluate(r);j.append.assert_not_called()
    def test_restart_does_not_duplicate_outcome(self):
        j,s=self.evaluate();out=j.append.call_args.args[1]
        events=[dict(kind='PREDICTION',payload=self.p),dict(kind='OUTCOME',payload=out)]
        j.reset_mock();s=finalize_predictions(j,events,self.context());j.append.assert_not_called();self.assertEqual(0,s['newly_observed'])
    def test_duplicate_prediction_events_emit_single_outcome(self):
        e=dict(kind='PREDICTION',payload=self.p);j=Mock()
        s=finalize_predictions(j,[e,e],self.context());self.assertEqual(1,s['newly_observed']);self.assertEqual(1,j.append.call_count)
    def events(self,state='KRONOS_READY'):
        return [dict(kind='PREDICTION',payload=self.p),dict(kind='STATUS',payload=dict(at=AT.isoformat(),status=state))]
    def test_raw_only_is_separate_from_healthy_inference(self):
        self.p['signal']=None;self.p['calibration_state']='RAW_ONLY'
        v=project(self.events(),AT)
        self.assertEqual('HEALTHY',v['operationalHealth']);self.assertEqual('RAW_ONLY',v['calibrationState'])
        self.assertEqual('NO_ELIGIBLE_TECHNICAL_SIGNAL',v['diagnostics']['calibration_reason'])
    def test_invalid_paths_remain_degraded_and_explained(self):
        self.p['invalid_frequency']=.25
        v=project(self.events('KRONOS_DEGRADED'),AT)
        self.assertEqual('DEGRADED',v['operationalHealth']);self.assertEqual(8,v['diagnostics']['invalid_paths'])
        self.assertEqual('INVALID_MODEL_OHLC_TRAJECTORIES',v['reason'])
    def test_stale_heartbeat_is_unavailable_even_with_prediction(self):
        v=project(self.events(),AT+timedelta(minutes=3))
        self.assertEqual('UNAVAILABLE',v['operationalHealth']);self.assertIn('OBSERVER_HEARTBEAT_MISSING_OR_STALE',v['diagnostics']['reasons'])
    def test_status_selected_by_timestamp_not_input_order(self):
        events=self.events();events.append(dict(kind='STATUS',payload=dict(at=(AT-timedelta(minutes=1)).isoformat(),status='KRONOS_UNAVAILABLE')))
        self.assertEqual('KRONOS_READY',project(events,AT)['status'])
    def test_small_descriptive_sample_is_not_published_as_calibration(self):
        events=self.events();events.append(dict(kind='OUTCOME',payload=dict(prediction_id=self.p['prediction_id'],actual='TP_FIRST',mae=.01,directional_correct=True)))
        v=project(events,AT)
        self.assertEqual(1,v['diagnostics']['observed_barrier_samples']);self.assertIsNone(v['calibration']['brier_score'])
        self.assertEqual(.25,v['calibration']['descriptive_metrics']['brier_score']);self.assertIsNone(v['byRegime'][0]['brier_score'])
    def test_scores_use_gated_calibration_pool_not_recent_aggregate(self):
        self.p['calibration_state']='CALIBRATED';self.p['calibration'].update(comparable_samples=120,sample_size=40,metrics=dict(brier_score=.04,log_loss=.1,calibration_error=.02))
        v=project(self.events(),AT);self.assertEqual(.04,v['calibration']['brier_score'])
        self.assertIsNone(project(self.events(),AT+timedelta(hours=2))['calibration']['brier_score'])
    def test_restart_retains_cpu_fallback_degradation(self):
        self.p['diagnostics']['provider_degraded']=True
        self.service.restore_forecast(self.p)
        self.assertEqual('KRONOS_DEGRADED',self.service.predict(request(self.c))['status'])
    def test_postgres_outage_does_not_terminate_observer(self):
        root=Path(self.temp.name);(root/'.local/kronos').mkdir(parents=True)
        stop=root/'.local/kronos/observer.stop';j=Mock()
        def read(study):
            if j.read.call_count==1:raise RuntimeError('KRONOS_POSTGRES_UNAVAILABLE')
            stop.write_text('TEST_STOP');return dict(events=[dict(kind='PREDICTION',payload=self.p)],source={})
        j.read.side_effect=read
        def append(kind,payload,*args):
            if j.read.call_count==1:raise RuntimeError('KRONOS_POSTGRES_UNAVAILABLE')
        j.append.side_effect=append
        c=dict(self.c,poll_seconds=1)
        # Same config hash is required for a persistent cache hit.
        meta=validate_input(request(c),c);self.p['cache_key']=digest(['EUR/USD','1H',meta['candle_timestamp'],c['model_version'],c['tokenizer_version'],config_hash(c),meta['input_hash']])
        out=io.StringIO()
        with patch('trading_agent.kronos.worker.load',return_value=c),patch('trading_agent.kronos.worker.PostgreSQLJournal',return_value=j),patch('trading_agent.kronos.worker.KronosPredictionService',return_value=Mock()),patch('trading_agent.kronos.worker.instance_lock',return_value=nullcontext()),patch('trading_agent.kronos.worker.source_request',return_value=(request(c),self.future())),patch('trading_agent.kronos.worker.utcnow',return_value=AT),patch('trading_agent.kronos.worker.time.sleep'),redirect_stdout(out):
            run(root)
        self.assertEqual(2,j.read.call_count);self.assertIn('UNAVAILABLE_NOT_PERSISTED',out.getvalue());self.assertIn('"cached": true',out.getvalue())
    def test_invalid_input_prevents_evaluation_and_inference(self):
        r=request(self.c);r['bars'][0]['high']=1.
        j=Mock();j.read.return_value=dict(events=[],source={});service=Mock()
        root=Path(self.temp.name)
        with patch('trading_agent.kronos.worker.load',return_value=self.c),patch('trading_agent.kronos.worker.PostgreSQLJournal',return_value=j),patch('trading_agent.kronos.worker.KronosPredictionService',return_value=service),patch('trading_agent.kronos.worker.instance_lock',return_value=nullcontext()),patch('trading_agent.kronos.worker.source_request',return_value=(r,[])),patch('trading_agent.kronos.worker.utcnow',return_value=AT),patch('trading_agent.kronos.worker.finalize_predictions') as finalize,redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(ValueError,'CORRUPT_OHLC'):run(root,once=True)
        finalize.assert_not_called();service.submit.assert_not_called()

if __name__=='__main__':unittest.main()
