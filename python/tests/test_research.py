from copy import deepcopy
from dataclasses import replace
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import unittest
from trading_agent.market import Candle,rsi,atr
from trading_agent.research_calendar import ForexCalendar,normalize,aggregate_15m
from trading_agent.research_indicators import settings,calculate
from trading_agent.research_analysis import analyze

ROOT=Path(__file__).resolve().parents[2]
BASE=datetime(2026,9,28,tzinfo=timezone.utc)


def calendar_config():return json.loads((ROOT/'config/forex-sessions.json').read_text())
def rows(n=80,minutes=15):
    return [{'opened_at':(BASE+timedelta(minutes=i*minutes)).isoformat(),'minutes':minutes,
             'open':1.1,'high':1.101,'low':1.099,'close':1.1,'volume':None,'spread':None} for i in range(n)]
def payload():
    return {'instrument':'EUR/USD','source':'IBKR_TWS','what_to_show':'MIDPOINT','as_of':(BASE+timedelta(days=5)).isoformat(),
            'calendar':calendar_config(),'originals':{str(m):rows(80 if m==15 else 5,m) for m in (15,60,240)}}


class CalendarTests(unittest.TestCase):
    def test_dst_changes_utc_session_open_and_weekend_is_closed(self):
        config=calendar_config();config.update(coverage_start='2026-03-01',coverage_end='2026-03-15')
        cal=ForexCalendar(config)
        self.assertEqual(cal.sessions[0][0].hour,22)
        self.assertEqual(next(a for a,b in cal.sessions if a.date().isoformat()=='2026-03-08').hour,21)
        self.assertIsNone(cal.session(datetime(2026,3,7,12,tzinfo=timezone.utc)))
    def test_explicit_holiday_override_is_not_inferred_from_currency_settlement(self):
        config=calendar_config();config['overrides']={'2026-09-28':None}
        self.assertIsNone(ForexCalendar(config).session(datetime(2026,9,28,22,tzinfo=timezone.utc)))
    def test_original_session_boundary_bars_preserved_and_excluded(self):
        samples=rows(1,240);samples[0]['opened_at']='2026-09-28T20:00:00+00:00';original=deepcopy(samples)
        normalized,q=normalize(samples,240,BASE+timedelta(days=2),ForexCalendar(calendar_config()))
        self.assertEqual(samples,original);self.assertEqual(normalized,[])
        self.assertEqual(q['excluded'],{'SESSION_BOUNDARY_SHORT_BAR':1})
        self.assertEqual(q['bars'][0]['effective_closed_at'],'2026-09-28T21:00:00+00:00')
    def test_duplicates_timezone_and_bad_prices_fail_closed(self):
        for sample in ([rows()[0],rows()[0]],[{**rows()[0],'opened_at':'2026-09-28T00:00:00'}],
                       [{**rows()[0],'close':float('nan')}],[{**rows()[0],'minutes':60}]):
            with self.assertRaises(ValueError):normalize(sample,15,BASE+timedelta(days=1),ForexCalendar(calendar_config()))
    def test_missing_bar_detected_without_fill_and_aggregation_requires_all_constituents(self):
        raw=rows(8);del raw[1]
        bars,q=normalize(raw,15,BASE+timedelta(days=1),ForexCalendar(calendar_config()))
        self.assertEqual(len(bars),7);self.assertEqual(q['missing_expected_openings'],[(BASE+timedelta(minutes=15)).isoformat()])
        derived=aggregate_15m(bars,60,ForexCalendar(calendar_config()))
        self.assertEqual(len(derived),1);self.assertEqual(derived[0].opened_at,BASE+timedelta(hours=1))
    def test_future_unclosed_bar_never_enters_normalized_series(self):
        bars,q=normalize(rows(3),15,BASE+timedelta(minutes=30),ForexCalendar(calendar_config()))
        self.assertEqual(len(bars),2);self.assertEqual(q['excluded']['NOT_CLOSED_AT_CUTOFF'],1)


class ReferenceIndicatorTests(unittest.TestCase):
    def test_wilder_rsi_mixed_reference(self):
        out=rsi([10,11,12,11,13,12],3)
        self.assertAlmostEqual(out[3],200/3);self.assertAlmostEqual(out[4],250/3);self.assertAlmostEqual(out[5],2000/33)
    def test_atr_reference_and_macd_alignment(self):
        bars=[Candle(BASE+timedelta(minutes=15*i),15,*values) for i,values in enumerate(((10,12,9,11),(11,13,10,12),(12,14,11,13),(13,16,12,15)))]
        self.assertEqual(atr(bars,3)[:3],[None,None,3]);self.assertAlmostEqual(atr(bars,3)[3],10/3)
        samples=[Candle(BASE+timedelta(minutes=15*i),15,x,x+.1,x-.1,x) for i,x in enumerate((1,2,3,4,5))]
        p=calculate(samples,settings({'ema_fast':2,'ema_slow':3,'macd_fast':2,'macd_slow':3,'macd_signal':2,'rsi':2,'atr':2,'volatility':2}))
        self.assertIsNone(p[2]['macd_signal']);self.assertAlmostEqual(p[3]['macd'],.5)
        self.assertAlmostEqual(p[3]['macd_signal'],.5);self.assertAlmostEqual(p[4]['ema_slow_slope'],1)
    def test_configurable_periods_and_warmup(self):
        bars=[Candle(BASE+timedelta(minutes=15*i),15,10,11,9,10) for i in range(10)]
        config=settings({'ema_fast':2,'ema_slow':3,'macd_fast':2,'macd_slow':3,'macd_signal':2,'rsi':2,'atr':2,'volatility':2})
        points=calculate(bars,config)
        self.assertEqual(points[2]['status'],'INSUFFICIENT_DATA');self.assertEqual(points[3]['status'],'READY')
        self.assertEqual(points[-1]['rsi'],50);self.assertEqual(points[-1]['log_return_std'],0)
        with self.assertRaises(ValueError):settings({'ema_fast':0})
    def test_prefix_indicators_do_not_change_with_future_prices(self):
        bars=[Candle(BASE+timedelta(minutes=15*i),15,10,11,9,10) for i in range(80)]
        self.assertEqual(calculate(bars[:60],settings()),calculate(bars,settings())[:60])
    def test_classifier_covers_both_trends_and_high_low_volatility(self):
        config=settings({'ema_fast':2,'ema_slow':3,'macd_fast':2,'macd_slow':3,'macd_signal':2,'rsi':2,'atr':2,'volatility':2})
        for prices,width,trend,volatility in (
            ([1+i*.01 for i in range(10)],.001,'UPTREND','HIGH'),
            ([1-i*.01 for i in range(10)],.001,'DOWNTREND','HIGH'),
            ([1]*10,.0001,'SIDEWAYS','LOW'),([1]*10,.01,'SIDEWAYS','HIGH')):
            bars=[Candle(BASE+timedelta(minutes=15*i),15,p,p+width,p-width,p) for i,p in enumerate(prices)]
            result=calculate(bars,config)[-1]
            self.assertEqual(result['trend'],trend);self.assertEqual(result['volatility'],volatility)


class ResearchContractTests(unittest.TestCase):
    def test_multitemporal_insufficient_data_and_unknown_costs_are_explicit(self):
        result=analyze(payload())
        self.assertEqual(result['latest']['240']['status'],'INSUFFICIENT_DATA')
        self.assertEqual(result['latest']['15']['status'],'READY');self.assertIsNone(result['net_profit'])
        self.assertEqual(result['evaluation_status'],'INCOMPLETE');self.assertFalse(result['orders_supported'])
        self.assertEqual(result['usable_counts']['15']['ema_slow'],31)
    def test_future_rows_cannot_change_cutoff_features_or_signals(self):
        a=payload();a['as_of']=(BASE+timedelta(hours=15)).isoformat();b=deepcopy(a)
        b['originals']['15'].append({**rows()[0],'opened_at':(BASE+timedelta(days=4)).isoformat(),'open':100,'high':101,'low':99,'close':100})
        x,y=analyze(a),analyze(b)
        self.assertEqual(x['indicator_points'],y['indicator_points']);self.assertEqual(x['candidates'],y['candidates'])
        self.assertEqual(x['latest'],y['latest'])
    def test_missing_expected_bar_resets_warmup(self):
        a=payload();del a['originals']['15'][50]
        result=analyze(a);self.assertEqual(result['latest']['15']['status'],'INSUFFICIENT_DATA')
    def test_multitemporal_contract_never_selects_a_future_close(self):
        data=payload()
        for i,bar in enumerate(data['originals']['15']):
            close=1.1+i*.0001;bar.update(open=close,close=close,high=close+.0001,low=close-.002)
        result=analyze(data);self.assertGreater(len(result['candidates']),0)
        for candidate in result['candidates']:
            for frame in candidate['context'].values():
                if frame['indicators']:
                    self.assertLessEqual(frame['indicators']['closed_at'],candidate['signal_at'])


if __name__=='__main__':unittest.main()
