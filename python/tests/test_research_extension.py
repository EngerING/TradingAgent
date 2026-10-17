from copy import deepcopy
from datetime import datetime,timedelta,timezone
import unittest
from trading_agent.history_extension import digest
from trading_agent.research_extension import prepare,extended,regional_windows
from test_research import rows

ACCOUNT='PAPER-fixture'
START=datetime(2026,9,28,tzinfo=timezone.utc);END=START+timedelta(days=1)
def archive():
    receipts=[]
    def add(kind,values,minutes=15):
        receipts.append({'source':'IBKR_TWS','account_id':ACCOUNT,'request':{'kind':kind,'minutes':minutes,'start':START.isoformat(),'end':END.isoformat(),'days':1},
            'received_at':(END+timedelta(days=1)).isoformat(),'availability':'AVAILABLE','error':None,
            'rows':values,'content_hash':digest(values),'orders_supported':False,'live_enabled':False})
    add('SCHEDULE',[{'start':'20260927-17:15:00','end':'20260929-17:00:00','time_zone':'US/Eastern',
        'sessions':[{'start':'20260927-17:15:00','end':'20260928-17:00:00','reference_date':'20260928'},
                    {'start':'20260928-17:15:00','end':'20260929-17:00:00','reference_date':'20260929'}]}])
    for m in (15,60,240):add('MIDPOINT',rows(80 if m==15 else 5,m),m)
    add('BID_ASK',[{**rows(1)[0],'open':'1.1000','close':'1.1002'}])
    add('TICKS',[{'timestamp':START.isoformat(),'bid':'1.1','ask':'1.1002','spread':'.0002'}])
    return {'schema_version':1,'source':'IBKR_TWS','account_id':ACCOUNT,'instrument':'EUR/USD','receipts':receipts,
        'requested_start':START.isoformat(),'requested_end':END.isoformat(),'orders_supported':False,'live_enabled':False}
class ExtensionTests(unittest.TestCase):
    def test_observed_spreads_do_not_verify_execution_costs(self):
        originals,calendar,bars,ticks,costs,_=prepare(archive(),ACCOUNT)
        self.assertEqual(calendar['status'],'IBKR_HISTORICAL_SCHEDULE');self.assertEqual(bars[0]['spread'],'0.0002')
        self.assertEqual(bars[0]['status'],'OBSERVED_BAR_AVERAGE');self.assertEqual(costs['closing_commission']['status'],'UNKNOWN')
        self.assertFalse(costs['executable']);self.assertEqual(len(ticks),1)
        a=archive();p=a['receipts'][-2];p['rows'][0]['close']=p['rows'][0]['open'];p['content_hash']=digest(p['rows'])
        _,_,zero,_,evidence,_=prepare(a,ACCOUNT)
        self.assertIsNone(zero[0]['spread']);self.assertEqual(zero[0]['raw_average_difference'],'0.0000')
        self.assertEqual(evidence['unresolved_zero_average_spread_count'],1)
    def test_archive_identity_hash_and_schedule_coverage_fail_closed(self):
        for mutate in (lambda a:a.update(account_id='PAPER-other'),
                       lambda a:a['receipts'][1]['rows'][0].update(close=9),
                       lambda a:a['receipts'][0].update(availability='UNAVAILABLE')):
            a=archive();mutate(a)
            with self.assertRaises(ValueError):prepare(a,ACCOUNT)
    def test_native_and_derived_are_separate_and_split_is_frozen(self):
        a=archive();p={'archive':a,'expected_account':ACCOUNT,'validation_start':(START+timedelta(hours=12)).isoformat(),
            'as_of':(END+timedelta(days=1)).isoformat(),'instrument':'EUR/USD','source':'IBKR_TWS','what_to_show':'MIDPOINT'}
        r=extended(p);self.assertEqual(len(r['extension']['originals']['15']),80)
        self.assertTrue(r['extension']['split']['parameters_frozen']);self.assertFalse(r['extension']['split']['optimization_performed'])
        self.assertTrue(all(b['source'].startswith('DERIVED_') for b in r['extension']['derived_series']['60']))
        self.assertEqual(r['extension']['execution_comparison']['paper_execution_observations'],[])
    def test_regional_windows_follow_local_dst_and_may_overlap(self):
        self.assertIn('LONDON',regional_windows(datetime(2026,7,1,7,tzinfo=timezone.utc)))
        self.assertNotIn('LONDON',regional_windows(datetime(2026,1,1,7,tzinfo=timezone.utc)))
        self.assertEqual(set(regional_windows(datetime(2026,7,1,13,tzinfo=timezone.utc))),{'LONDON','NEW_YORK'})
    def test_future_prices_do_not_change_closed_features_or_signals(self):
        a=archive()
        page=a['receipts'][1]
        for i,r in enumerate(page['rows']):
            value=1.1+i*.0001;r.update(open=value,close=value,high=value+.00002,low=value-.0001)
        page['content_hash']=digest(page['rows']);b=deepcopy(a)
        future=b['receipts'][1];future['rows'][60].update(open=99,close=99,high=100,low=98);future['content_hash']=digest(future['rows'])
        p={'expected_account':ACCOUNT,'validation_start':(START+timedelta(hours=8)).isoformat(),
            'as_of':(START+timedelta(hours=12)).isoformat(),'instrument':'EUR/USD','source':'IBKR_TWS','what_to_show':'MIDPOINT',
            'indicators':{'ema_fast':2,'ema_slow':3,'macd_fast':2,'macd_slow':3,'macd_signal':2,'rsi':2,'atr':2,'volatility':2}}
        x,y=extended({**p,'archive':a}),extended({**p,'archive':b})
        self.assertGreater(len(x['candidates']),0);self.assertEqual(x['indicator_points'],y['indicator_points'])
        self.assertEqual(x['candidates'],y['candidates'])
        self.assertEqual(set(x['candidates'][0]),{'strategy_id','side','signal_at','entry_at','entry_midpoint','stop_distance','take_profit_distance','reasons','context'})
        self.assertTrue(x['extension']['signal_annotations'])
