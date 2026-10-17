"""MOCK isolated read-model fixtures, never production quotes or execution evidence."""
import copy
from contextlib import closing
from datetime import datetime,timezone,timedelta
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from trading_agent.dashboard_projection import project,portfolio,numeric,safe_text,encoded,trade_view
import hashlib

class DashboardProjectionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir='artifacts/frontend-preparation');self.root=Path(self.temp.name)
        self.study='eurusd-shadow-'+'b'*32;self.at='2026-10-07T12:00:00+00:00'
        self.state=dict(protocol=dict(configuration=dict(profiles={p:dict(risk_fraction=r,trade_risk_cap_usd=c,daily_loss_budget_usd=c) for p,r,c in [('EURUSD_R1','.01','1'),('EURUSD_R5','.05','5'),('EURUSD_R10','.10','10')]}),costs=dict(openingCommission='2',closingCommission='2'),folds=[]),portfolio_metrics={},portfolio_heads={},status='PREPARED_NOT_RUNNING')
        for p in self.state['protocol']['configuration']['profiles']:
            self.state['portfolio_metrics'][p]=dict(equity_realized='100',net_pnl='0',gross_pnl='0',consumed_loss='0',completed_trades=0,wins=0,equity_curve=[])
        self.envelope=dict(head=dict(study_id=self.study,state=self.state,classification='SIMULATED_SHADOW',broker_orders=0,live_enabled=False,at=self.at),revision=1)
        self.now=datetime.fromisoformat(self.at)
    def tearDown(self):self.temp.cleanup()
    def snapshot(self):return project(self.root,self.envelope,self.now)
    def observation(self,age=0,kind='LIVE'):
        self.envelope['observation']=dict(details=dict(quote=dict(bid='1.12',ask='1.1201',at=(self.now-timedelta(seconds=age)).isoformat(),type=kind,market_status='OPEN'),features={}))
    def local(self,state):
        folder=self.root/'artifacts/research/eurusd-shadow'/self.study;folder.mkdir(parents=True,exist_ok=True)
        db=sqlite3.connect(folder/'EURUSD_R1.sqlite3');db.execute('CREATE TABLE events(revision,payload,previous,hash)')
        payload=dict(state=state);h=hashlib.sha256(encoded([1,payload,''])).hexdigest()
        db.execute('INSERT INTO events VALUES(?,?,?,?)',(1,encoded(payload).decode(),'',h));db.commit();db.close();self.state['portfolio_heads']['EURUSD_R1']=h
    def test_prepared_real_shape_does_not_imply_active(self):
        s=self.snapshot();self.assertEqual([e['status'] for e in s['experiments']],['PAUSED']*3)
    def test_initial_allocation_is_not_broker_balance(self):
        self.assertEqual([e['metrics']['equity'] for e in self.snapshot()['experiments']],[100]*3)
    def test_risk_each_portfolio(self):self.assertEqual([e['risk']['nextBudget'] for e in self.snapshot()['experiments']],[1,5,10])
    def test_missing_market_is_not_zero_quote(self):
        q=self.snapshot()['market'];self.assertIsNone(q['bid']);self.assertEqual(q['quality'],'MISSING')
    def test_current_live_quote(self):self.observation(4);self.assertEqual(self.snapshot()['market']['quality'],'LIVE')
    def test_stale_is_not_live(self):self.observation(31);self.assertEqual(self.snapshot()['market']['quality'],'STALE')
    def test_future_quote_is_rejected(self):self.observation(-10);self.assertEqual(self.snapshot()['market']['quality'],'STALE')
    def test_delayed_is_preserved(self):self.observation(1,'DELAYED');self.assertEqual(self.snapshot()['market']['quality'],'DELAYED')
    def test_metrics_without_trades_not_invented(self):
        m=self.snapshot()['experiments'][0]['metrics'];self.assertIsNone(m['winRate']);self.assertIsNone(m['profitFactor']);self.assertIsNone(m['riskOfRuin'])
    def test_daily_stop_missing_is_unknown(self):
        self.assertIsNone(self.snapshot()['experiments'][0]['stoppedForDay'])
    def test_daily_stop_uses_santo_domingo_not_utc_date(self):
        self.now=datetime.fromisoformat('2026-10-08T02:00:00+00:00')
        self.state['portfolio_metrics']['EURUSD_R1']['daily_stops']={'2026-10-07':'NET_BREAK_EVEN'}
        p=self.snapshot()['experiments'][0];self.assertTrue(p['stoppedForDay']);self.assertEqual('NET_BREAK_EVEN',p['dailyStopReason'])
    def test_daily_stop_display_resets_without_deleting_history(self):
        self.now=datetime.fromisoformat('2026-10-08T12:00:00+00:00');self.state['portfolio_metrics']['EURUSD_R1']['daily_stops']={'2026-10-07':'DAILY_FIRST_LOSS_STOP'}
        self.assertFalse(self.snapshot()['experiments'][0]['stoppedForDay']);self.assertIn('2026-10-07',self.state['portfolio_metrics']['EURUSD_R1']['daily_stops'])
    def test_unknown_sources_do_not_create_files(self):self.snapshot();self.assertEqual(list(self.root.iterdir()),[])
    def test_readonly_hash_validation(self):
        self.local(dict(trades=[],position=None));self.assertEqual(portfolio(self.root,self.study,'EURUSD_R1',self.state['portfolio_heads']['EURUSD_R1'])['trades'],[])
    def test_mirror_mismatch_blocks_projection(self):
        self.local(dict(trades=[],position=None));self.state['portfolio_heads']['EURUSD_R1']='f'*64
        with self.assertRaisesRegex(ValueError,'MISMATCH'):self.snapshot()
    def test_journal_tamper_is_not_served(self):
        self.local(dict(trades=[],position=None));path=self.root/'artifacts/research/eurusd-shadow'/self.study/'EURUSD_R1.sqlite3'
        with closing(sqlite3.connect(path)) as db:db.execute("UPDATE events SET hash='fake'");db.commit()
        with self.assertRaisesRegex(ValueError,'INTEGRITY'):self.snapshot()
    def test_wrong_scope_rejected(self):
        self.envelope['head']['broker_orders']=1
        with self.assertRaisesRegex(ValueError,'SCOPE'):self.snapshot()
    def test_traversal_study_rejected(self):
        self.envelope['head']['study_id']='../../.local'
        with self.assertRaisesRegex(ValueError,'SCOPE'):self.snapshot()
    def test_secrets_redacted(self):self.assertEqual(safe_text('sk-test123 DU123456'), '[REDACTED] [REDACTED]')
    def test_nan_and_bool_are_not_numeric(self):
        self.assertIsNone(numeric('NaN'));self.assertIsNone(numeric(True))
    def test_quote_curve_order_and_deduplication(self):
        q=dict(at=self.at,bid='1',ask='1.2');self.envelope['quotes']=[q,q,dict(at='2026-10-07T11:59:00+00:00',bid='1',ask='1.1')]
        self.assertEqual(len(self.snapshot()['market']['series']),2);self.assertEqual(self.snapshot()['market']['series'][-1]['value'],1.1)
    def test_calibration_seven_empty_buckets(self):
        c=self.snapshot()['calibration'];self.assertEqual(len(c['buckets']),7);self.assertTrue(all(b['average_probability'] is None for b in c['buckets']))
    def test_risk_tracks_equity_down_never_up_above_cap(self):
        self.state['portfolio_metrics']['EURUSD_R1']['equity_realized']='90';self.assertEqual(self.snapshot()['experiments'][0]['risk']['nextBudget'],.9)
    def test_missing_study_no_fake_allocation(self):
        self.envelope['head']=None;s=self.snapshot();self.assertIsNone(s['experiments'][0]['metrics']);self.assertIsNone(s['studyId'])

if __name__=='__main__':unittest.main()
