"""Commit before publication; transcript and authentic paths cannot swap provenance."""
from datetime import timedelta
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from trading_agent.core_v3.contracts import ContractError
from trading_agent.core_v3.market_observation.collector import FixtureAdapter, collect
from trading_agent.core_v3.market_observation.ibkr_adapter import IBKRReader, TranscriptAdapter
from trading_agent.core_v3.market_observation.journal import Journal
from trading_agent.core_v3.market_observation.contracts import Origin, SessionKind, Kind
from test_core_v39_validation import policy, prices, AT
from test_core_v39_protocol import approval, frame


def details():
    values = [10,8,100,'EUR','CASH','','0','','IDEALPRO','USD','EUR.USD',
        'IDEALPRO','EUR.USD',12087792,'0.00005',1,'','', 'IDEALPRO',1,0,'Euro','',
        '','','','','UTC','','','',0,0,0,'','','','','']
    return frame(*values)[4:]


def transcript():
    return (frame(15,1,'DU123')[4:], details(), frame(52,1,100)[4:],
            frame(58,1,101,1)[4:], frame(1,6,101,1,'1.1000',0,0)[4:],
            frame(1,6,101,2,'1.1002',0,0)[4:])


class CollectionTests(unittest.TestCase):
    def test_simulated_capture_commits_then_closes_without_network(self):
        with tempfile.TemporaryDirectory() as directory:
            with Journal(Path(directory)/'fixture.sqlite', policy(), 'session-1', Origin.FIXTURE, SessionKind.PAPER) as journal:
                adapter = FixtureAdapter(prices())
                receipt = collect(adapter, journal, now=lambda: AT+timedelta(seconds=1))
                self.assertTrue(adapter.closed)
                self.assertEqual(5, receipt.committed)
                self.assertEqual(5, receipt.checkpoint.sequence)
                self.assertEqual('NO_TRADE', receipt.action)

    def test_failed_commit_closes_and_exposes_no_uncommitted_record(self):
        with tempfile.TemporaryDirectory() as directory:
            with Journal(Path(directory)/'fixture.sqlite', policy(), 'session-1', Origin.FIXTURE, SessionKind.PAPER) as journal:
                adapter = FixtureAdapter(prices())
                with patch.object(Journal, '_before_commit', side_effect=ConnectionError('fixture')):
                    with self.assertRaises(ConnectionError):
                        collect(adapter, journal, now=lambda: AT)
                self.assertTrue(adapter.closed)
                self.assertEqual((), journal.history())

    def test_real_reader_default_off_before_socket_creation(self):
        with patch('trading_agent.core_v3.market_observation.ibkr_adapter.socket.socket', side_effect=AssertionError('must not create socket')):
            with self.assertRaises(ContractError):
                list(IBKRReader(policy(), approval(), now=lambda: AT).events())

    def test_transcript_is_fixture_and_preserves_market_frames_only(self):
        adapter = TranscriptAdapter(transcript(), policy(), 'session-1', SessionKind.PAPER, now=lambda: AT)
        events = tuple(adapter.events())
        self.assertTrue(all(raw.origin is Origin.FIXTURE for raw in events))
        account = next(raw for raw in events if raw.redacted)
        self.assertEqual('', account.raw_frame_b64)
        self.assertEqual(64, len(account.raw_frame_sha256))
        self.assertNotIn('DU123', repr(events))
        self.assertEqual('1.1002', next(raw for raw in events if raw.kind is Kind.ASK).price_text)

    def test_duplicate_contract_or_missing_end_cannot_subscribe(self):
        for payloads in ((details(), details()), (details(),)):
            adapter = TranscriptAdapter(payloads, policy(), 'session-1', SessionKind.PAPER, now=lambda: AT)
            events = tuple(adapter.events())
            self.assertTrue(any(raw.kind is Kind.GAP for raw in events))
            self.assertFalse(any(raw.kind in (Kind.BID,Kind.ASK) for raw in events))

    def test_health_gap_stops_quotes_and_requires_fresh_connection(self):
        payloads = transcript()+(frame(4,2,-1,1100,'not logged')[4:], frame(1,6,101,1,'1.2',0,0)[4:])
        adapter = TranscriptAdapter(payloads, policy(), 'session-1', SessionKind.PAPER, now=lambda: AT)
        events = tuple(adapter.events())
        self.assertTrue(any(raw.kind is Kind.GAP for raw in events))
        self.assertFalse(any(raw.price_text == '1.2' for raw in events))
