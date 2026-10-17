from datetime import datetime, timezone
from pathlib import Path
import unittest

from trading_agent.aggressive_growth import configuration, initial_state
from trading_agent.aggressive_growth_projection import project

ROOT = Path(__file__).resolve().parents[2]
AT = '2026-10-09T17:00:00+00:00'


class ProjectionTests(unittest.TestCase):
    def payload(self):
        return dict(experiment='aggressive-r20-'+'a'*32,scope='AGGRESSIVE_GROWTH_R20',
                    classification='SHADOW_SIMULATED',broker_orders=0,live_enabled=False,
                    state=initial_state(configuration(ROOT),'a'*64,AT))

    def test_empty_ledger_is_not_a_profitable_strategy(self):
        view=project(self.payload(),datetime.fromisoformat(AT))
        self.assertEqual('100',view['equity'])
        self.assertEqual(0,view['shadowTrades'])
        self.assertEqual(0,view['paperTrades'])
        self.assertIsNone(view['winRate'])
        self.assertIsNone(view['expectancy'])
        self.assertIsNone(view['anticipatedTotalLoss'])
        self.assertFalse(view['eligibility']['statisticallyValidated'])
        self.assertEqual('IBKR_PAPER',view['paper']['classification'])

    def test_shadow_cannot_become_paper_or_live_in_projection(self):
        for key,value in [('classification','IBKR_PAPER'),('broker_orders',1),('live_enabled',True)]:
            p=self.payload();p[key]=value
            with self.assertRaises(ValueError):project(p,datetime.fromisoformat(AT))

    def test_stale_heartbeat_is_not_running_evidence(self):
        p=self.payload();p['state']['status']='SHADOW_RUNNING'
        v=project(p,datetime(2026,10,9,18,tzinfo=timezone.utc))
        self.assertEqual('STALE',v['evidenceQuality'])
        self.assertEqual('SHADOW_HEARTBEAT_STALE',v['status'])

    def test_kronos_future_or_old_forecast_does_not_claim_support(self):
        for at in ('2026-10-08T09:00:39+00:00','2026-10-09T18:00:00+00:00'):
            p=self.payload();p['state']['latest_kronos']=dict(status='OBSERVER_ONLY',created_at=at,projected_direction='LONG',agreement='AGREE',calibrated_probability=.9)
            v=project(p,datetime.fromisoformat(AT))
            self.assertIsNone(v['kronos']['agreement'])
            self.assertIsNone(v['kronos']['calibratedProbability'])

    def test_closed_results_and_baseline_are_independent(self):
        p=self.payload();r=p['state']['portfolios']['R20'];b=p['state']['portfolios']['BASELINE_1X']
        r.update(equity='93',cash_equity='93',realized_gross='1',realized_net='-7',fees='4',consumed_loss='7')
        r['trades']=[dict(id='one',side='LONG',quantity='800',entry='1.1',notional='880',at=AT,closed_at=AT,gross_pnl='1',net_pnl='-7',timeframe=60,classification='SHADOW_SIMULATED',assessment={})]
        v=project(p,datetime.fromisoformat(AT))
        self.assertEqual('93',v['equity']);self.assertEqual('100',v['baseline']['equity'])
        self.assertEqual('0',v['winRate']);self.assertEqual('-7',v['expectancy'])
        self.assertEqual('SHADOW_SIMULATED',v['trades'][0]['classification'])
        self.assertEqual(0,v['baseline']['closedTrades'])

    def test_missing_cost_is_unknown_not_zero(self):
        p=self.payload();p['state']['portfolios']['R20']['financing_cost']=None
        self.assertIsNone(project(p,datetime.fromisoformat(AT))['financing'])

    def test_positive_kronos_agreement_requires_frozen_comparable_evidence(self):
        p=self.payload();state=p['state'];state['opportunities']=1
        state['signals']=[dict(id='signal',at='2026-10-09T16:59:00Z',observed_at=AT,timeframe=60,side='LONG',
                              decisions={'R20':dict(admitted=False,reason='POSITION_OCCUPIED')},
                              kronos=dict(prediction_id='frozen',status='OBSERVER_ONLY',fresh=True,timeframe=60,temporal_compatible=True,
                                          created_at='2026-10-09T16:01:00Z',candle_timestamp='2026-10-09T16:00:00Z',
                                          prediction_end='2026-10-09T18:00:00Z',direction='LONG'))]
        state['latest_kronos']=dict(prediction_id='later',direction='SHORT')
        k=project(p,datetime.fromisoformat(AT))['kronos']
        self.assertEqual('frozen',k['predictionId']);self.assertEqual('AGREE',k['agreement'])
        state['signals'][0]['kronos']['timeframe']=240
        self.assertIsNone(project(p,datetime.fromisoformat(AT))['kronos']['agreement'])

    def test_expired_candle_cannot_stay_usable_until_long_horizon_end(self):
        p=self.payload();p['state']['latest_kronos']=dict(status='OBSERVER_ONLY',fresh=True,as_of=AT,
            created_at='2026-10-09T16:01:00Z',candle_timestamp='2026-10-09T16:00:00Z',prediction_end='2026-10-10T18:00:00Z')
        self.assertEqual('KRONOS_UNAVAILABLE',project(p,datetime(2026,10,9,19,tzinfo=timezone.utc))['kronos']['status'])

    def test_nested_paper_authority_is_rejected(self):
        p=self.payload();p['state']['paper']['authorization_granted']=True
        with self.assertRaises(ValueError):project(p,datetime.fromisoformat(AT))

    def test_dashboard_routes_r20_independently_without_old_shadow_head(self):
        from trading_agent.dashboard_projection import project as dashboard
        result=dashboard(ROOT,dict(aggressiveGrowth=self.payload()),datetime.fromisoformat(AT))
        self.assertEqual('100',result['aggressiveGrowth']['equity'])
        self.assertEqual(dashboard(ROOT,{},datetime.fromisoformat(AT))['experiments'],result['experiments'])


if __name__=='__main__':unittest.main()
