"""R20 requirements; synthetic fixtures are tests, never market evidence."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
from pathlib import Path
import unittest

from trading_agent import aggressive_growth as r20

ROOT = Path(__file__).resolve().parents[2]
AT = datetime(2026, 10, 9, 16, tzinfo=timezone.utc)


def bars(side='LONG', minutes=60, count=70):
    rows = []
    for i in range(count):
        close = Decimal('1.10') + Decimal(i) * Decimal('.0001')
        if side == 'SHORT':
            close = Decimal('2.30') - close
        rows.append(dict(opened_at=(AT-timedelta(minutes=minutes*(count-i))).isoformat(),
                         minutes=minutes, open=str(close), high=str(close+Decimal('.00005')),
                         low=str(close-Decimal('.00005')), close=str(close)))
    return rows


def quote(at=None, midpoint='1.107'):
    m = Decimal(midpoint)
    return dict(at=(at or AT+timedelta(seconds=1)).isoformat(), bid=str(m-Decimal('.00001')),
                ask=str(m+Decimal('.00001')), type='LIVE', market_status='OPEN', available_for_execution=True)


def observation(side='LONG', at=None):
    at = at or AT+timedelta(seconds=1)
    return dict(at=at.isoformat(), quote=quote(at), history_source={'sha256': 'test-only'},
                analysis={'normalized': {'60': bars(side), '240': bars(side, 240)},
                          'quality': {'60': {'missing_expected_openings': []}, '240': {'missing_expected_openings': []}}},
                capabilities={})


class StrategyTests(unittest.TestCase):
    def setUp(self): self.c = r20.configuration(ROOT)

    def test_symmetric_closed_breakout(self):
        for side in ('LONG', 'SHORT'):
            with self.subTest(side=side):
                s = r20.signal(self.c, bars(side), 60, AT)
                self.assertEqual(side, s['side'])
                self.assertEqual(Decimal(s['target_distance']), 2*Decimal(s['stop_distance']))
                self.assertEqual(AT.isoformat(), s['at'])

    def test_future_bar_cannot_change_signal(self):
        rows = bars()
        before = r20.signal(self.c, rows, 60, AT)
        future = dict(rows[-1], opened_at=AT.isoformat(), high='1000', close='999')
        self.assertEqual(before, r20.signal(self.c, rows+[future], 60, AT))

    def test_prior_twenty_excludes_signal_bar(self):
        rows = bars(); rows[-1]['high'] = '5'
        self.assertEqual('LONG', r20.signal(self.c, rows, 60, AT)['side'])

    def test_equal_prior_high_is_not_breakout(self):
        rows = bars(); rows[-1]['close'] = rows[-2]['high']; rows[-1]['open'] = rows[-1]['close']
        self.assertIsNone(r20.signal(self.c, rows, 60, AT)['side'])

    def test_insufficient_and_corrupt_input_block(self):
        self.assertEqual('INSUFFICIENT_CLOSED_BARS', r20.signal(self.c, bars()[:30], 60, AT)['reason'])
        rows = bars(); rows[-1]['low'] = '4'
        self.assertEqual('INVALID_MARKET_DATA', r20.signal(self.c, rows, 60, AT)['reason'])


class SizingTests(unittest.TestCase):
    def setUp(self):
        self.c = r20.configuration(ROOT)
        self.s = dict(side='LONG', stop_distance='.03', target_distance='.06')

    def test_updated_equity_price_risk_and_ten_times(self):
        for equity in ('100', '60', '130'):
            d = r20.assess(self.c, quote(), self.s, equity)
            self.assertTrue(d['admitted'])
            self.assertLessEqual(Decimal(d['price_risk']), Decimal(equity)*Decimal('.20'))
            self.assertLessEqual(Decimal(d['notional']), Decimal(equity)*10)
            self.assertLessEqual(Decimal(d['margin'])+Decimal(d['estimated_costs']), Decimal(equity))

    def test_costs_separate_from_risk_negative_economics_allowed(self):
        s = dict(self.s, stop_distance='.0002', target_distance='.0004')
        d = r20.assess(self.c, quote(), s, '100')
        self.assertTrue(d['admitted'])
        self.assertLess(Decimal(d['net_target']), 0)
        self.assertEqual(Decimal('4'), Decimal(d['fees']))
        self.assertEqual(Decimal(d['price_risk'])+Decimal(d['estimated_costs']), Decimal(d['anticipated_total_loss']))

    def test_baseline_and_decimal_increment(self):
        d = r20.assess(self.c, quote(), self.s, '100', leverage='1')
        self.assertLessEqual(Decimal(d['notional']), 100)
        self.assertEqual(Decimal(0), Decimal(d['quantity']) % Decimal('.01'))

    def test_equity_minimum_and_margin_rejections(self):
        self.assertEqual('EQUITY_EXHAUSTED', r20.assess(self.c, quote(), self.s, '0')['reason'])
        self.assertFalse(r20.assess(self.c, quote(), self.s, '1')['admitted'])
        self.assertFalse(r20.assess(self.c, quote(), self.s, '100', conditions={'minimum_quantity': '20000'})['admitted'])
        self.assertEqual('MARGIN_REJECTION', r20.assess(self.c, quote(), self.s, '100', conditions={'margin_allowed': False})['reason'])

    def test_short_geometry_and_nonfinite_rejection(self):
        d = r20.assess(self.c, quote(), dict(self.s, side='SHORT'), '100')
        self.assertGreater(Decimal(d['stop']), Decimal(d['entry']))
        self.assertLess(Decimal(d['target']), Decimal(d['entry']))
        self.assertFalse(r20.assess(self.c, dict(quote(), ask='NaN'), self.s, '100')['admitted'])


class SimulationTests(unittest.TestCase):
    def setUp(self):
        self.c = r20.configuration(ROOT)
        self.s = r20.initial_state(self.c, 'a'*64, AT.isoformat())

    def consume(self, o=None, **kw):
        o = o or observation()
        return r20.consume(self.s, o, datetime.fromisoformat(o['at']), **kw)

    def test_same_opportunities_baseline_one_position_dedupe(self):
        self.consume()
        a,b = self.s['portfolios'].values()
        self.assertEqual(a['active']['signal_id'], b['active']['signal_id'])
        self.assertEqual(60, a['active']['timeframe'])
        self.assertGreater(Decimal(a['active']['quantity']), Decimal(b['active']['quantity']))
        self.assertEqual(2, len(self.s['seen']))
        self.assertTrue(any(e['reason']=='POSITION_OCCUPIED' for e in self.s['signals'][-1]['decisions'].values()))
        self.consume()
        self.assertEqual(2, len(self.s['signals']))

    def test_stale_signal_quote_and_stop_no_fake_fill(self):
        self.consume(observation(at=AT+timedelta(minutes=5)))
        self.assertIsNone(self.s['portfolios']['R20']['active'])
        self.assertEqual('SIGNAL_STALE', self.s['last_no_trade']['reason'])
        fresh = r20.initial_state(self.c, 'a'*64, AT.isoformat()); self.s = fresh
        o=observation(); o['quote']['at']=(AT-timedelta(minutes=1)).isoformat()
        self.consume(o)
        self.assertIsNone(self.s['portfolios']['R20']['active'])
        self.assertEqual('QUOTE_STALE_MISSING_OR_CLOSED', self.s['last_no_trade']['reason'])

    def test_gap_loss_and_slippage_exceed_price_stop_without_capping(self):
        self.consume(); p=self.s['portfolios']['R20']; before=deepcopy(p['active'])
        o=observation(at=AT+timedelta(seconds=20)); o['quote']=quote(AT+timedelta(seconds=20),'1.05')
        self.consume(o)
        t=p['trades'][0]
        self.assertLess(Decimal(t['net_pnl']), -Decimal(before['price_risk']))
        self.assertEqual(Decimal('100')+Decimal(t['net_pnl']), Decimal(p['cash_equity']))
        self.assertEqual(Decimal(t['fees']), Decimal(p['fees']))

    def test_stop_is_terminal_and_closes_virtual_only(self):
        self.consume(); self.consume(observation(at=AT+timedelta(seconds=10)),stop=True)
        self.assertEqual('STOPPED', self.s['status'])
        self.assertIsNone(self.s['portfolios']['R20']['active'])
        self.consume()
        self.assertEqual('STOPPED', self.s['status'])
        self.assertEqual(1, len(self.s['portfolios']['R20']['trades']))

    def test_paper_plan_has_no_execution_or_calibrated_authority(self):
        self.consume(kronos={'status':'KRONOS_UNAVAILABLE'})
        self.assertFalse(self.s['paper']['execution_authorized'])
        self.assertTrue(self.s['paper']['single_use'])
        self.assertEqual('SHADOW_SIMULATED',self.s['portfolios']['R20']['active']['classification'])
        self.assertIsNone(self.s['latest_kronos']['calibrated_probability'])

    def test_position_retains_entry_equity_and_quote_evidence(self):
        self.consume()
        t=self.s['portfolios']['R20']['active']
        self.assertEqual('100',t['entry_equity'])
        self.assertEqual(observation()['quote'],self.s['signals'][0]['quote'])
        self.assertFalse(self.s['paper']['authorization_granted'])

    def test_kronos_future_or_expired_cannot_support_signal(self):
        for changes in ({'created_at':(AT+timedelta(seconds=10)).isoformat()}, {'prediction_end':(AT-timedelta(seconds=1)).isoformat()}):
            k=dict(status='KRONOS_READY',created_at=(AT-timedelta(seconds=10)).isoformat(),candle_timestamp=AT.isoformat(),prediction_end=(AT+timedelta(hours=12)).isoformat(),direction='LONG',**{})
            k.update(changes)
            self.assertFalse(r20.kronos_evidence(k,AT)['fresh'])

    def test_native_candle_seed_values_are_fixed(self):
        self.assertEqual(Decimal('2.5'),r20.ema([Decimal(i) for i in (1,2,3,4)],4))
        self.assertEqual(Decimal('3.5'),r20.ema([Decimal(i) for i in (1,2,3,4,5)],4))
        flat=bars()
        for row in flat:row.update(open='1.1',high='1.101',low='1.099',close='1.1')
        self.assertEqual(Decimal('.002'),Decimal(r20.signal(self.c,flat,60,AT)['atr14']))

    def test_prior_entry_bar_never_stops_new_position(self):
        self.consume(); p=self.s['portfolios']['R20'];o=observation(at=AT+timedelta(minutes=59))
        row=dict(opened_at=AT.isoformat(),open='1.107',high='1.2',low='.9',close='1.107')
        o['analysis']['normalized']['60'].append(row)
        self.consume(o)
        self.assertIsNotNone(p['active'])

    def test_both_barriers_stop_first_and_short_gap(self):
        for side in ('LONG','SHORT'):
            d=r20.assess(self.c,quote(),dict(side=side,stop_distance='.01',target_distance='.02'),'100')
            t=dict(d,timeframe=60,at=(AT-timedelta(hours=2)).isoformat(),side=side)
            b=dict(opened_at=(AT-timedelta(hours=1)).isoformat(),open='1.107',high='1.2',low='1.0',close='1.107')
            price,reason=r20.exit_check(t,[b],quote(),AT,self.c)
            self.assertEqual(Decimal(d['stop']),price)
            self.assertEqual('STOP_OR_GAP',reason)

    def test_missed_closed_candles_are_recorded_as_rejections(self):
        self.consume()
        later=observation(at=AT+timedelta(hours=3,seconds=1))
        series=later['analysis']['normalized']['60']
        for i in range(3):series.append(dict(series[-1],opened_at=(AT+timedelta(hours=i)).isoformat()))
        self.consume(later)
        self.assertEqual(5,len(self.s['seen']))


if __name__ == '__main__': unittest.main()
