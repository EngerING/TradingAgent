from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import unittest
from trading_agent.market import Candle, analyze, ema, rsi, atr, validate, analyze_timeframes
from trading_agent.backtest import Config, run, split_dataset, compare

BASE=datetime(2026,1,5,tzinfo=timezone.utc)
def bars(n=80, minutes=15, price=1.1):
    return [Candle(BASE+timedelta(minutes=i*minutes),minutes,price,price+.001,price-.001,price,None) for i in range(n)]


class Indicators(unittest.TestCase):
    def test_constant_series(self):
        xs=bars(); a=analyze(xs,xs[-1].closed_at)
        self.assertAlmostEqual(a['ema20'],1.1);self.assertAlmostEqual(a['ema50'],1.1)
        self.assertAlmostEqual(a['macd'],0);self.assertEqual(a['rsi'],50)
        self.assertAlmostEqual(a['atr'],.002);self.assertEqual(a['volatility_per_bar'],0)
        self.assertFalse(a['volume_available']);self.assertIsNone(a['mean_spread'])
    def test_known_ema(self):
        self.assertEqual(ema([1,2,3,4,5],3),[None,None,2,3,4])
    def test_rsi_rising_and_falling(self):
        self.assertEqual(rsi(list(range(1,30)))[-1],100)
        self.assertEqual(rsi(list(range(30,1,-1)))[-1],0)
    def test_no_warmup_invention(self):
        self.assertIsNone(rsi([1,2,3])[-1])
        with self.assertRaises(ValueError):analyze(bars(5),BASE+timedelta(days=1))
    def test_missing_data_rejected(self):
        xs=bars();del xs[20]
        with self.assertRaises(ValueError):validate(xs,xs[-1].closed_at)
    def test_duplicate_nan_invalid_ohlc(self):
        for sample in ([bars()[0],bars()[0]], [replace(bars()[0],close=float('nan'))], [replace(bars()[0],high=1.0)]):
            with self.assertRaises(ValueError):validate(sample,BASE+timedelta(days=1))
    def test_future_bar_rejected(self):
        with self.assertRaises(ValueError):validate(bars(1),BASE)
    def test_timeframes_use_only_closed(self):
        series={m:bars(80,m) for m in (15,60,240)}
        end=series[240][-1].closed_at
        for m in series:series[m].append(Candle(end,m,1,2,.5,1))
        result=analyze_timeframes(series,end)
        self.assertEqual(set(result),{'context','conditions','entries'})
    def test_spread_variation(self):
        xs=[replace(c,spread=.0001) for c in bars()];xs[-1]=replace(xs[-1],spread=.0003)
        self.assertAlmostEqual(analyze(xs,xs[-1].closed_at)['spread_change'],.0002)


class Backtesting(unittest.TestCase):
    def config(self,**kwargs):
        return replace(Config(),capital='100',stop='0.01',take_profit='0.02',spread='0',slippage='0',gap_reserve='0',
                       signal='always_long',**kwargs)
    def test_known_stop(self):
        xs=bars(2,price=1);xs[1]=replace(xs[1],low=.98,high=1)
        result=run(xs,self.config())
        self.assertEqual(result['trades'][0]['quantity'],'25')
        self.assertEqual(Decimal(result['net_profit']),Decimal('-.25'))
        self.assertEqual(Decimal(result['expectancy']),Decimal('-.25'))
        self.assertEqual(Decimal(result['profit_factor']),0)
        self.assertEqual(Decimal(result['max_drawdown']),Decimal('.0025'))
    def test_known_take_profit(self):
        xs=bars(2,price=1);xs[1]=replace(xs[1],high=1.03)
        r=run(xs,self.config());self.assertEqual(Decimal(r['net_profit']),Decimal('.50'));self.assertIsNone(r['profit_factor'])
    def test_both_stop_and_target_stop_first(self):
        xs=bars(2,price=1);xs[1]=replace(xs[1],high=1.03,low=.98)
        r=run(xs,self.config());self.assertTrue(r['trades'][0]['ambiguous']);self.assertEqual(r['trades'][0]['reason'],'STOP_AMBIGUOUS')
    def test_costs_charged_once(self):
        xs=bars(2,price=1);xs[1]=replace(xs[1],high=1.03)
        config=replace(self.config(),spread='.001',slippage='.001',commission_fixed='.01')
        r=run(xs,config);t=r['trades'][0]
        self.assertEqual(Decimal(t['quantity']),20);self.assertEqual(Decimal(t['cost']),Decimal('.05'));self.assertEqual(Decimal(t['net']),Decimal('.35'))
    def test_gap_stop_worse_than_trigger(self):
        xs=bars(3,price=1);xs[2]=replace(xs[2],open=.97,high=.975,low=.96,close=.965)
        r=run(xs,self.config());self.assertEqual(Decimal(r['trades'][0]['exit']),Decimal('.97'))
    def test_reproducible(self):
        self.assertEqual(run(bars(),Config()),run(bars(),Config()))
    def test_signal_not_filled_on_same_bar(self):
        r=run(bars(2,price=1),self.config());t=r['trades'][0]
        self.assertEqual(t['entry_at'],bars(2)[1].opened_at.isoformat())
    def test_future_changes_do_not_change_prior_trades(self):
        xs=bars(5,price=1);xs[1]=replace(xs[1],low=.98);a=run(xs,self.config())
        xs[-1]=replace(xs[-1],high=2);b=run(xs,self.config())
        self.assertEqual(a['trades'][0],b['trades'][0])
    def test_holdout_separate(self):
        xs=bars();dev,test=split_dataset(xs,xs[40].opened_at);self.assertEqual(len(dev),40);self.assertEqual(len(test),40)
        self.assertLessEqual(dev[-1].closed_at,test[0].opened_at)
    def test_comparison_same_assumptions(self):
        with self.assertRaises(ValueError):compare(bars(),[Config(),replace(Config(),spread='.1')])
    def test_minimum_and_limits(self):
        r=run(bars(),replace(Config(),signal='always_long',minimum_quantity='20000'))
        self.assertEqual(r['trades'],[]);self.assertTrue(all(not d['accepted'] for d in r['decisions']))
    def test_five_losses_reduction(self):
        xs=bars(6,price=1)
        for i in range(1,6):xs[i]=replace(xs[i],low=.98)
        r=run(xs,self.config(daily_limit='.5',weekly_limit='.5'))
        self.assertEqual(r['max_loss_streak'],5)
        self.assertLess(Decimal(r['trades'][3]['quantity']),Decimal(r['trades'][2]['quantity']))

if __name__=='__main__':unittest.main()
