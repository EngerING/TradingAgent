from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from trading_agent.eurusd_shadow_research import (configuration, regime, feature_engine, historical_labels, Calibrator,
    economic_gate, calibration_metrics, Study, contextual, process, PROFILES, SCOPE)
from trading_agent.eurusd_paper_research import encoded, sha, load_profile, Simulator

ROOT=Path(__file__).resolve().parents[2]
AT='2026-10-06T14:00:00+00:00'


def probability(p=.9,low=.85,status='CALIBRATED_RESEARCH_ESTIMATE'):
    return dict(probability=p,lower_95=low,status=status)


def size(**updates):
    return dict(admitted=True,net_target='2',risk='1',**updates)


class ProbabilityEconomicTests(unittest.TestCase):
    def test_high_probability_never_overrides_negative_ev(self):
        s=dict(admitted=True,net_target='.01',risk='1')
        self.assertEqual('NET_EV_NOT_POSITIVE',economic_gate(s,probability(.99,.9),{'recommendation':'TRADE'})['reason'])

    def test_ev_counts_net_target_and_total_loss_including_fees(self):
        r=economic_gate(size(),probability(.75,.7),{'recommendation':'TRADE'})
        self.assertEqual(Decimal('1.25'),Decimal(r['expected_value']));self.assertEqual(Decimal('1.1'),Decimal(r['conservative_ev']))

    def test_uncertainty_can_veto_positive_point_estimate(self):
        r=economic_gate(size(),probability(.9,.1),{'recommendation':'TRADE'})
        self.assertGreater(Decimal(r['expected_value']),0);self.assertEqual('NO_TRADE',r['decision'])

    def test_subjective_model_confidence_is_not_an_input(self):
        r=economic_gate(size(),probability(status='INSUFFICIENT_EVIDENCE'),{'recommendation':'TRADE','confidence':1})
        self.assertEqual('INSUFFICIENT_EVIDENCE',r['reason'])

    def test_model_can_only_veto(self):
        for advice in ('NO_TRADE','INSUFFICIENT_EVIDENCE'):
            with self.subTest(advice=advice): self.assertEqual('NO_TRADE',economic_gate(size(),probability(),{'recommendation':advice})['decision'])

    def test_sizing_rejection_precedes_model_advice(self):
        self.assertEqual('COMMISSION_EXCEEDS_RISK_BUDGET',economic_gate(dict(admitted=False,reason='COMMISSION_EXCEEDS_RISK_BUDGET'),probability(),{'recommendation':'TRADE'})['reason'])

    def test_all_three_portfolios_have_isolated_usd100(self):
        c=configuration(ROOT);self.assertEqual(PROFILES,tuple(c['profiles']))
        self.assertEqual('100',c['initial_capital_per_portfolio']);self.assertFalse(c['broker_orders_enabled'])

    def test_regime_uses_existing_computed_indicators(self):
        for trend,want in [('UPTREND','UPTREND'),('DOWNTREND','DOWNTREND'),('SIDEWAYS','RANGE')]:
            self.assertEqual(want,regime(dict(status='READY',trend=trend,volatility='NORMAL')))
        self.assertEqual('HIGH_VOLATILITY',regime(dict(status='READY',trend='UPTREND',volatility='HIGH')))
        self.assertEqual('ANOMALOUS_OR_INSUFFICIENT_DATA',regime(dict(status='READY'),True))

    def test_calibration_excludes_unresolved_and_future_results(self):
        rows=[dict(strategy='trend',side='BUY',regime='RANGE',signal_at='2026-10-01T14:00:00+00:00',resolved_at=AT,outcome='TP'),
              dict(strategy='trend',side='BUY',regime='RANGE',signal_at='2026-10-01T14:00:00+00:00',resolved_at=None,outcome='CENSORED')]
        c=Calibrator(rows,configuration(ROOT)['probability'],[])
        r=c.estimate(dict(strategy='trend',side='BUY',regime='RANGE'),AT)
        self.assertEqual(0,r['sample_size']);self.assertIsNone(r['probability'])

    def test_calibration_compares_same_side_regime_strategy_only(self):
        rows=[dict(strategy='trend',side='BUY',regime='RANGE',signal_at='2026-10-01T14:00:00+00:00',resolved_at='2026-10-02T14:00:00+00:00',outcome='TP')]
        c=Calibrator(rows,configuration(ROOT)['probability'],[])
        self.assertEqual(0,c.estimate(dict(strategy='trend',side='SELL',regime='RANGE'),AT)['sample_size'])
        self.assertEqual(1,c.estimate(dict(strategy='trend',side='BUY',regime='RANGE'),AT)['sample_size'])

    def test_competing_exit_never_disappears_from_denominator(self):
        rows=[dict(strategy='trend',side='BUY',regime='RANGE',signal_at='2026-10-01T14:00:00+00:00',resolved_at='2026-10-02T14:00:00+00:00',outcome=o) for o in ('TP','COMPETING_EXIT')]
        r=Calibrator(rows,configuration(ROOT)['probability'],[]).estimate(dict(strategy='trend',side='BUY',regime='RANGE'),AT)
        self.assertEqual(.5,r['probability']);self.assertEqual('INSUFFICIENT_EVIDENCE',r['status'])

    def test_bucket_boundaries_and_brier_are_calculated(self):
        r=calibration_metrics([dict(probability=.8,outcome='TP'),dict(probability=.6,outcome='SL')])
        self.assertAlmostEqual(.2,r['brier_score']);self.assertEqual(1,r['buckets'][-1]['samples'])
        self.assertEqual(1,r['buckets'][2]['samples'])

    def test_empty_calibration_is_unknown(self):
        r=calibration_metrics([]);self.assertIsNone(r['brier_score']);self.assertEqual('INSUFFICIENT_EVIDENCE',r['status'])

    def test_censored_price_paths_are_not_win_rate_samples(self):
        r=calibration_metrics([dict(probability=.9,outcome='COMPETING_EXIT')])
        self.assertEqual(0,r['sample_size']);self.assertEqual(1,r['censored'])

    def test_features_do_not_read_future_bars(self):
        point=dict(closed_at=AT,status='READY',trend='UPTREND',volatility='NORMAL')
        a=dict(normalized={'15':[dict(opened_at='2026-10-06T14:00:00+00:00',high='999',low='998',close='999')]},indicator_points={'15':[point]},quality={})
        q=dict(type='LIVE',market_status='OPEN',available_for_execution=True,at=AT,bid='1.1',ask='1.1001')
        r=feature_engine(a,q,AT);self.assertIsNone(r['support']);self.assertIsNone(r['resistance']);self.assertIsNone(r['liquidity'])


class FakeMirror:
    def __init__(self): self.rows=[]
    def __call__(self,root,study,events):
        for e in events:
            if e['revision']<=len(self.rows):
                if self.rows[e['revision']-1]['hash']!=e['hash']: raise ValueError('CONFLICT')
            else: self.rows.append(e)
        return dict(revision=len(self.rows),hash=self.rows[-1]['hash'] if self.rows else '',payload=self.rows[-1]['payload'] if self.rows else None)


class ShadowPersistenceAndContextTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.mirror=FakeMirror();self.id='eurusd-shadow-'+'a'*32
        self.s=Study(self.tmp.name,self.id,self.mirror)
        c=configuration(ROOT)
        self.s.state=dict(protocol=dict(configuration=c),openai=dict(calls=0,reserved_usd='0',observed_cost_upper_estimate='0',input_tokens=0,output_tokens=0,circuit_open=False))
        self.s.append('PREREGISTERED',{})

    def tearDown(self): self.s.db.close();self.tmp.cleanup()

    def test_restart_preserves_local_and_postgres_head(self):
        self.s.state['loss']='1';self.s.append('LOSS',{});head=self.s.head;self.s.db.close()
        self.s=Study(self.tmp.name,self.id,self.mirror);self.assertEqual(head,self.s.head);self.assertEqual('1',self.s.state['loss'])

    def test_deleted_local_state_cannot_erase_remote_losses(self):
        other=Path(self.tmp.name)/'empty'
        with self.assertRaisesRegex(ValueError,'LOCAL_SHADOW_JOURNAL_MISSING'):
            Study(other,self.id,self.mirror)

    def test_append_resumes_outbox_without_duplicate_remote_event(self):
        n=len(self.mirror.rows);self.s.sync();self.assertEqual(n,len(self.mirror.rows))

    def test_pg_unavailable_blocks_new_evaluation(self):
        self.s.mirror=Mock(side_effect=ValueError('PG_UNAVAILABLE'))
        with self.assertRaisesRegex(ValueError,'PG_UNAVAILABLE'): self.s.sync()

    def test_default_budget_makes_zero_provider_calls(self):
        provider=Mock();r=contextual(self.s,dict(id='signal',probability=probability()),provider=provider)
        provider.assert_not_called();self.assertEqual('INSUFFICIENT_EVIDENCE',r['recommendation'])

    def enable(self,budget='.5'):
        a=self.s.state['protocol']['configuration']['openai'];a['enabled']=True;a['max_cost_usd']=budget

    def test_call_reservation_is_durable_before_provider(self):
        self.enable()
        def provider(body,timeout):
            self.assertEqual('OPENAI_COST_RESERVED',json.loads(self.mirror.rows[-1]['payload'])['event'])
            self.assertNotIn('confidence',body['text']['format']['schema']['properties'])
            return dict(usage=dict(input_tokens=100,output_tokens=10),proposal_text=json.dumps(dict(recommendation='NO_TRADE',reasons=['costs'],limitations=['macro unknown'])),error=None)
        result=contextual(self.s,dict(id='signal',probability=probability()),provider=provider)
        self.assertEqual('NO_TRADE',result['recommendation']);self.assertEqual(100,self.s.state['openai']['input_tokens'])

    def test_auth_or_billing_error_opens_circuit_without_retry(self):
        self.enable();provider=Mock(return_value=dict(error='OPENAI_HTTP_429',usage=None))
        for _ in range(2): contextual(self.s,dict(id='signal',probability=probability()),provider=provider)
        self.assertEqual(1,provider.call_count);self.assertTrue(self.s.state['openai']['circuit_open'])

    def test_subjective_confidence_field_is_rejected(self):
        self.enable();provider=Mock(return_value=dict(error=None,usage=dict(input_tokens=100,output_tokens=10),proposal_text=json.dumps(dict(recommendation='TRADE',reasons=[],limitations=[],confidence=.99))))
        self.assertEqual('INSUFFICIENT_EVIDENCE',contextual(self.s,dict(id='signal',probability=probability()),provider=provider)['recommendation'])
        self.assertTrue(self.s.state['openai']['circuit_open'])

    def test_insufficient_historical_evidence_does_not_spend_tokens(self):
        self.enable();provider=Mock();contextual(self.s,dict(id='signal',probability=probability(status='INSUFFICIENT_EVIDENCE')),provider=provider);provider.assert_not_called()

    def test_budget_reservation_prevents_excess_call(self):
        self.enable('.0001');provider=Mock();contextual(self.s,dict(id='signal',probability=probability()),provider=provider);provider.assert_not_called()

    def test_journal_update_and_delete_are_blocked(self):
        for sql in ('DELETE FROM events','UPDATE events SET previous="x"'):
            with self.subTest(sql=sql),self.assertRaises(Exception): self.s.db.execute(sql)

    def test_uncertain_request_cannot_be_repeated_after_restart(self):
        self.enable();provider=Mock(side_effect=TimeoutError())
        contextual(self.s,dict(id='signal',probability=probability()),provider=provider)
        self.s.db.close();self.s=Study(self.tmp.name,self.id,self.mirror)
        contextual(self.s,dict(id='signal',probability=probability()),provider=provider)
        self.assertEqual(1,provider.call_count);self.assertEqual('signal',self.s.state['openai']['pending_opportunity'])


class CommonOpportunityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();root=Path(self.tmp.name)
        (root/'config').mkdir()
        (root/'config/eurusd-paper-research-100.json').write_bytes((ROOT/'config/eurusd-paper-research-100.json').read_bytes())
        self.mirror=FakeMirror();self.s=Study(root,'eurusd-shadow-'+'b'*32,self.mirror)
        c=configuration(ROOT);costs=dict(openingCommission='2',closingCommission='2',spread='.0001',slippage='.0002',adverseGap='.0001',minimumQuantity='.01',quantityStep='.01')
        strategy=dict(strategy_version='fixture_not_real',version=1)
        self.s.state=dict(protocol=dict(configuration=c,costs=costs,strategy=strategy),seen=[],portfolio_heads={},portfolio_metrics={},
            last_observation=None,status='PREPARED',research_handoff=None,calibration_records=[],forward_labels=[],settled_opportunity_ids=[],
            openai=dict(calls=0,reserved_usd='0',observed_cost_upper_estimate='0',input_tokens=0,output_tokens=0,circuit_open=False))
        for name,limits in c['profiles'].items():
            p=load_profile(ROOT);p.update(profile=name,risk_fraction=limits['risk_fraction'],maximum_trade_risk_usd=limits['trade_risk_cap_usd'],daily_loss_budget_usd=limits['daily_loss_budget_usd'])
            sim=Simulator(self.s.folder/(name+'.sqlite3'),p,costs,strategy,positive_expectancy_evidence=True)
            self.s.state['portfolio_heads'][name]=sim.head;self.s.state['portfolio_metrics'][name]=sim.metrics();sim.db.close()
        self.s.append('PREREGISTERED',{})
        signal=dict(strategy_id='trend',side='BUY',signal_at=AT,entry_at=None,entry_midpoint=None,stop_distance='.005',take_profit_distance='.025',reasons=['NO_NEXT_CLOSED_BAR'],context={})
        self.o=dict(at=AT,source='SYNTHETIC_TEST_ONLY',broker_orders=0,quote=dict(type='LIVE',market_status='OPEN',available_for_execution=True,at=AT,bid='1.1',ask='1.1001'),
            analysis=dict(normalized={'15':[]},indicator_points={'15':[dict(closed_at=AT,status='READY',trend='UPTREND',volatility='NORMAL')]},quality={},candidates=[signal],exit_signals=[]))
        self.cal=Mock(labels=[]);self.cal.estimate.return_value=probability()

    def tearDown(self): self.s.db.close();self.tmp.cleanup()

    def test_profiles_share_signal_prices_stop_target_and_regime(self):
        result=process(self.s,self.o,self.cal)
        rows=list(result['decisions'].values())
        for key in ('opportunity_id','signal_timestamp','reference_midpoint','stop_distance','target_distance','regime'):
            self.assertEqual(1,len({r[key] for r in rows}))
        self.assertEqual('COMMISSION_EXCEEDS_RISK_BUDGET',rows[0]['reason'])
        self.assertEqual('TARGET_DOES_NOT_COVER_COSTS',rows[1]['reason']);self.assertEqual('TARGET_DOES_NOT_COVER_COSTS',rows[2]['reason'])

    def test_three_rejections_do_not_make_three_trades(self):
        result=process(self.s,self.o,self.cal)
        self.assertEqual(0,sum(m['completed_trades'] for m in result['metrics'].values()));self.assertEqual(0,result['broker_orders'])
        for m in result['metrics'].values(): self.assertEqual('100',m['equity_realized'])

    def test_only_shadow_r5_r10_can_open_when_all_gates_pass(self):
        self.s.state['protocol']['configuration']['openai'].update(enabled=True,max_cost_usd='.5')
        self.o['analysis']['candidates'][0]['take_profit_distance']='.2'
        provider=Mock(return_value=dict(error=None,usage=dict(input_tokens=100,output_tokens=10),proposal_text=json.dumps(dict(recommendation='TRADE',reasons=['fixture'],limitations=['not real']))))
        result=process(self.s,self.o,self.cal,provider)
        self.assertEqual('NO_TRADE',result['decisions']['EURUSD_R1']['decision'])
        for name in ('EURUSD_R5','EURUSD_R10'):
            self.assertEqual('TRADE',result['decisions'][name]['decision'])
            self.assertIsNotNone(result['metrics'][name]['pending_position']);self.assertEqual('SIMULATED',result['metrics'][name]['fill_classification'])
        self.assertEqual(1,provider.call_count);self.assertEqual(0,result['broker_orders'])

    def test_repeated_quote_does_not_repeat_an_opportunity(self):
        process(self.s,self.o,self.cal);result=process(self.s,self.o,self.cal)
        self.assertTrue(all(r['reason']=='OPPORTUNITY_ALREADY_EVALUATED' for r in result['decisions'].values()))

    def test_counterfactual_outcome_is_not_a_completed_portfolio_trade(self):
        process(self.s,self.o,self.cal)
        self.o['at']='2026-10-06T14:15:00+00:00';self.o['quote']['at']=self.o['at']
        self.o['analysis']['normalized']['15']=[dict(opened_at=AT,minutes=15,open='1.1',high='1.13',low='1.099',close='1.12')]
        result=process(self.s,self.o,self.cal)
        self.assertEqual(1,len(self.s.state['forward_labels']));self.assertEqual('TP',self.s.state['forward_labels'][0]['outcome'])
        self.assertEqual(0,sum(m['completed_trades'] for m in result['metrics'].values()))
        self.assertEqual(1,len(self.s.state['calibration_records']))

    def test_counterfactual_and_two_portfolios_produce_only_one_probability_label(self):
        self.s.state['protocol']['configuration']['openai'].update(enabled=True,max_cost_usd='.5')
        self.o['analysis']['candidates'][0]['take_profit_distance']='.2'
        provider=Mock(return_value=dict(error=None,usage=dict(input_tokens=100,output_tokens=10),proposal_text=json.dumps(dict(recommendation='TRADE',reasons=[],limitations=[]))))
        process(self.s,self.o,self.cal,provider)
        self.o['at']='2026-10-06T14:15:00+00:00';self.o['quote']['at']=self.o['at']
        self.o['analysis']['normalized']['15']=[dict(opened_at=AT,minutes=15,open='1.1',high='1.31',low='1.099',close='1.3')]
        result=process(self.s,self.o,self.cal,provider)
        self.assertEqual(2,sum(m['completed_trades'] for m in result['metrics'].values()))
        self.assertEqual(1,len(self.s.state['forward_labels']));self.assertEqual(1,len(self.s.state['calibration_records']))


if __name__=='__main__': unittest.main()
