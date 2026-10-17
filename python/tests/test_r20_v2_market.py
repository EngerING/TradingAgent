"""Recorded authentic evidence is historical, never an execution fixture."""
from copy import deepcopy
from datetime import datetime,timedelta
from pathlib import Path
import json,unittest
from trading_agent.r20_market import assess_market

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'artifacts/aggressive-growth-r20-20261010/r20-v2-shadow-cycle-20261013/authentic-market-source.json'

class MarketBoundaryTests(unittest.TestCase):
    def setUp(self):self.raw=json.loads(SOURCE.read_text());self.at=datetime.fromisoformat(self.raw['at'])
    def assess(self,raw=None,**kw):return assess_market(ROOT,raw or self.raw,kw.pop('now',self.at),identity_verified=kw.pop('identity_verified',True),**kw)
    def test_authentic_read_cannot_authorize_entry(self):
        view=self.assess()
        self.assertEqual('VERIFIED_AT_CUTOFF',view['status'])
        self.assertFalse(view['entryEligible']);self.assertEqual(0,view['brokerOrders'])
        self.assertEqual('CALLBACK_RECEIPT',view['timestampBasis'])
        self.assertIsNone(view['sourceTimestamp'])
        self.assertEqual('NO_BREAKOUT',view['signals']['60']['reason'])
    def test_mismatch_stale_future_delayed_or_incomplete_rejected(self):
        with self.assertRaisesRegex(ValueError,'EXACT_ACCOUNT'):self.assess(identity_verified=False)
        for mutate in (lambda r:r['quote'].update(source='IBKR_LIVE'),
                       lambda r:r['quote'].update(market_data_type=3),
                       lambda r:r['quote'].update(at=(self.at+timedelta(seconds=1)).isoformat()),
                       lambda r:r['bars']['60'].pop(100)):
            r=deepcopy(self.raw);mutate(r)
            with self.assertRaises(ValueError):self.assess(r)
        with self.assertRaisesRegex(ValueError,'STALE'):self.assess(now=self.at+timedelta(seconds=31))
    def test_future_bars_do_not_change_closed_signal(self):
        r=deepcopy(self.raw);row=dict(r['bars']['60'][-1]);row['opened_at']=(self.at+timedelta(hours=2)).isoformat()
        row.update(open='99',high='100',low='98',close='99');r['bars']['60'].append(row)
        self.assertEqual(self.assess()['signals'],self.assess(r)['signals'])

    def test_transport_disconnect_reconnect_revalidates_identity(self):
        from unittest.mock import patch,MagicMock
        from trading_agent.r20_market import PaperReadSource
        from datetime import timezone
        auth=MagicMock();auth.read.return_value={'account':'TEST_PAPER_EXACT'};auth.binding.masked_account='***TEST'
        first=MagicMock();first.connect.side_effect=ConnectionError('DISCONNECTED')
        second=MagicMock();second.connect.return_value=['WRONG_ACCOUNT']
        with patch('trading_agent.eurusd_exploratory_runner.ExploratoryReadIdentity',return_value=auth),\
             patch('trading_agent.ibkr_session.session_guard'),\
             patch('trading_agent.paper_execution_wire.execution_wire',side_effect=[first,second]) as transport:
            source=PaperReadSource(ROOT)
            with self.assertRaises(ConnectionError):source.poll()
            self.assertIsNone(source.wire);first.disconnect.assert_called_once()
            with self.assertRaisesRegex(ValueError,'EXACT_ACCOUNT'):source.poll()
            second.disconnect.assert_called_once();second.history.assert_not_called()
            self.assertTrue(all(call.kwargs['read_only'] is True for call in transport.call_args_list))
