from datetime import datetime,timezone
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from trading_agent.equity_data_integrity import (event,unique_events,issuer_date,spy_events,
    historical_prices,scan,dividend_entitlements,verified_archive,integrity_report)
from test_equity_strategy_research import bars


class EquityDataIntegrityTests(unittest.TestCase):
    def dividend(self,symbol='F',ex='2024-02-15',pay='2024-03-01',amount='.18'):
        return event(symbol,ex,pay,amount,'https://issuer.example/dividends','a'*64)

    def trade(self,start='2024-02-14T14:30:00Z',end='2024-02-15T14:30:00Z',symbol='F'):
        return dict(symbol=symbol,entryAt=start,exitAt=end,quantity=2,side='LONG')

    def test_events_require_positive_amount_dates_universe_and_provenance(self):
        for symbol,ex,pay,amount in [('X','2024-02-15','2024-03-01','.1'),('F','2026-04-03','2026-04-04','.1'),
            ('F','2024-02-15','2024-02-14','.1'),('F','2024-02-15','2024-03-01','NaN'),('F','2024-02-15','2024-03-01','0')]:
            with self.assertRaises(ValueError):self.dividend(symbol,ex,pay,amount)
        with self.assertRaises(ValueError):event('F','2024-02-15','2024-03-01','.1','unknown','a'*64)

    def test_duplicate_event_is_idempotent_and_conflict_is_not_averaged(self):
        e=self.dividend();self.assertEqual(1,len(unique_events([e,e])))
        other={**e,'amount_usd':'.20'}
        with self.assertRaisesRegex(ValueError,'CONFLICTING'):unique_events([e,other])

    def test_entitlement_requires_ownership_before_ex_open(self):
        e=self.dividend();r=dividend_entitlements([self.trade()],[e],'UNADJUSTED',as_of='2024-02-20')
        self.assertEqual('0.36',r[0]['gross_receivable_usd']);self.assertFalse(r[0]['payable_date_passed'])
        self.assertEqual([],dividend_entitlements([self.trade(start='2024-02-15T14:30:00Z',end='2024-02-16T14:30:00Z')],[e],'UNADJUSTED'))
        self.assertEqual([],dividend_entitlements([self.trade(end='2024-02-14T21:00:00Z')],[e],'UNADJUSTED'))

    def test_payable_is_not_net_or_settled_cash_and_original_trade_is_unchanged(self):
        t=self.trade();before=copy.deepcopy(t)
        r=dividend_entitlements([t],[self.dividend()],'UNADJUSTED',as_of='2024-03-01')[0]
        self.assertTrue(r['payable_date_passed']);self.assertIsNone(r['net_receivable_usd'])
        self.assertEqual('UNKNOWN',r['withholding_status']);self.assertEqual(0,r['available_cash_credit'])
        self.assertFalse(r['strategy_pnl_updated']);self.assertEqual(before,t)

    def test_adjusted_unknown_price_or_duplicate_position_cannot_double_count(self):
        for basis in ('ADJUSTED_LAST','UNKNOWN','TOTAL_RETURN'):
            with self.assertRaises(ValueError):dividend_entitlements([self.trade()],[self.dividend()],basis)
        with self.assertRaisesRegex(ValueError,'DUPLICATE_DIVIDEND'):
            dividend_entitlements([self.trade(),self.trade()],[self.dividend()],'UNADJUSTED')

    def test_short_and_split_crossing_inventory_requires_separate_accounting(self):
        t=self.trade();t['side']='SHORT'
        with self.assertRaises(ValueError):dividend_entitlements([t],[self.dividend()],'UNADJUSTED')
        t=self.trade('2024-10-10T13:30:00Z','2024-12-12T21:00:00Z','SCHX')
        with self.assertRaisesRegex(ValueError,'SPLIT_INVENTORY'):dividend_entitlements([t],[],'SPLIT_RESTORED')

    def test_split_restores_only_ohlc_before_event_and_preserves_raw_volume(self):
        r=bars(2);r[0].update(opened_at='2024-10-10T13:30:00Z',closed_at='2024-10-10T14:30:00Z')
        r[1].update(opened_at='2024-10-11T13:30:00Z',closed_at='2024-10-11T14:30:00Z')
        before=copy.deepcopy(r);out=historical_prices('SCHX',r)
        self.assertEqual(before,r);self.assertEqual(30,out[0]['open']);self.assertEqual(10,out[1]['open'])
        self.assertEqual(r[0]['volume'],out[0]['volume']);self.assertEqual(r,historical_prices('F',r))

    def test_known_split_is_not_a_tradable_minus_66_percent_gap(self):
        r=bars(2);r[0].update(opened_at='2024-10-10T13:30:00Z',closed_at='2024-10-10T14:30:00Z',close=30,open=30,high=31,low=29)
        r[1].update(opened_at='2024-10-11T13:30:00Z',closed_at='2024-10-11T14:30:00Z')
        f=scan('SCHX',r,[])['flags'][0]
        self.assertEqual('KNOWN_SPLIT_3_TO_1',f['category']);self.assertAlmostEqual(0,f['economic_gap'])

    def test_2022_split_date_cannot_be_shifted_to_explain_february_jump(self):
        r=bars(2)
        r[0].update(opened_at='2022-02-10T14:30:00Z',closed_at='2022-02-10T15:30:00Z')
        r[1].update(opened_at='2022-02-11T14:30:00Z',closed_at='2022-02-11T15:30:00Z',open=5,high=6,low=4,close=5)
        self.assertEqual('DISCONTINUITY_REQUIRES_REVIEW',scan('SCHX',r,[])['flags'][0]['category'])
        r[0].update(opened_at='2022-03-10T14:30:00Z',closed_at='2022-03-10T15:30:00Z')
        r[1].update(opened_at='2022-03-11T14:30:00Z',closed_at='2022-03-11T15:30:00Z',open=10,high=11,low=9,close=10)
        f=scan('SCHX',r,[])['flags'][0]
        self.assertIn('20220311',f['category']);self.assertIsNone(f['economic_gap']);self.assertFalse(f['removed'])

    def test_original_split_2022_also_requires_inventory_accounting(self):
        t=self.trade('2022-03-10T14:30:00Z','2022-03-11T15:30:00Z','SCHX')
        with self.assertRaisesRegex(ValueError,'SPLIT_INVENTORY'):
            dividend_entitlements([t],[],'SPLIT_RESTORED')

    def test_real_gap_is_flagged_and_preserved_even_on_dividend_day(self):
        r=bars(2);r[0].update(opened_at='2024-02-14T14:30:00Z',closed_at='2024-02-14T15:30:00Z')
        r[1].update(opened_at='2024-02-15T14:30:00Z',closed_at='2024-02-15T15:30:00Z',open=7,high=8,low=6,close=7)
        before=copy.deepcopy(r);q=scan('F',r,[self.dividend()]);f=q['flags'][0]
        self.assertTrue(f['dividend_on_date']);self.assertFalse(f['removed']);self.assertEqual(before,r)

    def test_bad_ohlc_and_zero_volume_not_silently_interpolated(self):
        r=bars(1);r[0]['high']=1;r[0]['volume']=0;q=scan('F',r,[])
        self.assertEqual(1,q['invalid_bars']);self.assertEqual(1,q['zero_volume_bars'])
        with self.assertRaises(ValueError):scan('F',[r[0],r[0]],[])

    def test_archive_corruption_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'raw.json';p.write_text('{}');p.with_suffix('.sha256').write_text(hashlib.sha256(p.read_bytes()).hexdigest())
            self.assertEqual({},verified_archive(p));p.write_text('{"changed":true}')
            with self.assertRaises(ValueError):verified_archive(p)

    def test_date_serial_is_explicit_and_invalid_date_is_rejected(self):
        self.assertEqual('2024-02-15',str(issuer_date('02/15/2024')))
        self.assertEqual('2024-02-15',str(issuer_date('45337')))
        with self.assertRaises(ValueError):issuer_date('15')

    def test_actual_issuer_workbook_filters_exact_symbol_and_quarantines_recent_tail(self):
        p=Path('artifacts/research/equity-operational/sources/spy-distributions.xlsx')
        if not p.exists():self.fail('Authentic frozen issuer workbook fixture required')
        rows=spy_events(p,'https://www.ssga.com/official.xlsx')
        self.assertEqual(21,len(rows));self.assertTrue(all(x['symbol']=='SPY' and x['ex_date']<'2026-04-03' for x in rows))

    def test_final_strategy_never_evaluated_by_integrity_review(self):
        # Use small authentic-schema fixture; report only inspects prices and existing empty selection results.
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);old=root/'artifacts/research/equity-evidence';new=root/'artifacts/research/equity-operational'
            old.mkdir(parents=True);(new/'sources').mkdir(parents=True)
            r=bars(1);r[0].update(opened_at='2025-01-02T14:30:00Z',closed_at='2025-01-02T15:30:00Z')
            data={'symbols':{s:dict(bars={'60':r,'1440':r}) for s in ('SCHX','SPY','F')}}
            adjusted={'symbols':{s:dict(bars=r) for s in ('SCHX','SPY','F')}}
            for name,value in [('readonly',data),('adjusted-quality',adjusted)]:
                p=old/(name+'.json');p.write_text(json.dumps(value));p.with_suffix('.sha256').write_text(hashlib.sha256(p.read_bytes()).hexdigest())
            (old/'report.json').write_text('{"rows":[]}');(new/'sources/receipts.json').write_text('[]')
            with patch('trading_agent.equity_strategy_research.simulate',side_effect=AssertionError('FINAL_OPENED')):
                q=integrity_report(root)
            self.assertTrue(q['final_holdout_sealed']);self.assertEqual(0,q['strategies_recomputed'])
            self.assertEqual(6,q['reviewed_bar_count'])
