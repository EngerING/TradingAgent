"""Adversarial boundary tests. SDK is referenced only here as an offline wire oracle."""
import ast
from contextlib import closing
from dataclasses import FrozenInstanceError, replace
from datetime import timedelta
from pathlib import Path
import sqlite3
import struct
import tempfile
import unittest
from unittest.mock import patch

from trading_agent.core_v3.contracts import ContractError
from trading_agent.core_v3.market_observation.contracts import CapturePolicy, RawEvent, Kind, Origin, SessionKind
from trading_agent.core_v3.market_observation.validation import State, step
from trading_agent.core_v3.market_observation.journal import Journal
from trading_agent.core_v3.market_observation.ibkr_adapter import IBKRReader, TranscriptAdapter
from trading_agent.core_v3.market_observation.ibkr_protocol import Command, encode
from trading_agent.core_v3.market_observation.collector import FixtureAdapter, collect
from trading_agent.core_v3.market_observation.shadow import observe
from test_core_v39_validation import policy, prices, event, fold, AT
from test_core_v39_protocol import approval, frame
from test_core_v39_collection import transcript
from test_core_v39_shadow import spec


class SecurityTests(unittest.TestCase):
    def test_no_operational_import_or_order_reference_in_product(self):
        root = Path(__file__).resolve().parents[1]/'trading_agent/core_v3/market_observation'
        denied = {'ibapi','tws','broker','ibkr_session','paper_lab','paper_execution_wire','subprocess',
                  'event_backtest','statistical_validation','SyntheticDataset','placeOrder','cancelOrder',
                  'reqOpenOrders','reqAllOpenOrders','reqGlobalCancel','exerciseOptions'}
        for path in root.glob('*.py'):
            tree = ast.parse(path.read_text(encoding='utf-8'))
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import,ast.ImportFrom)):
                    names = ([node.module or ''] if isinstance(node,ast.ImportFrom) else [])+[n.name for n in node.names]
                    self.assertFalse(any(set(name.split('.')) & denied for name in names), (path,names))
                if isinstance(node,ast.Attribute):
                    self.assertNotIn(node.attr,denied)
                if isinstance(node,ast.Name):
                    self.assertNotIn(node.id,denied)
        for name in ('placeOrder','cancelOrder','reqGlobalCancel'):
            self.assertFalse(hasattr(IBKRReader,name))
        self.assertEqual({1,2,9,17,49,59,71},{v.value for v in Command})

    def test_closed_json_versions_duplicates_and_immutable_copies(self):
        raw = prices()[-1]
        self.assertEqual(raw,RawEvent.from_json(raw.to_json()))
        data = raw.to_dict()
        data['execution_authorized'] = True
        with self.assertRaises(ContractError): RawEvent.from_dict(data)
        data = raw.to_dict(); data['schema_version'] = 2
        with self.assertRaises(ContractError): RawEvent.from_dict(data)
        with self.assertRaises(ContractError): RawEvent.from_json('{"schema":1,"schema":2}')
        with self.assertRaises(FrozenInstanceError): raw.price_text = '3'
        for changes in ({'max_events':4097},{'max_disk_bytes':True},{'max_reconnects':3}):
            with self.assertRaises(ContractError): policy(**changes)

    def test_raw_frame_hash_size_redaction_and_encoding_cannot_diverge(self):
        raw=prices()[0]
        for changes in ({'raw_frame_b64':'eA=='}, {'raw_frame_size':1,'raw_frame_sha256':'0'*64},
                        {'raw_frame_b64':'***'}, {'raw_frame_b64':'eA==','redacted':True}):
            with self.assertRaises(ContractError): replace(raw,**changes)

    def test_monotonic_side_age_catches_accumulated_small_wall_drift(self):
        raws = list(prices()[:-1])
        base = raws[-1]
        for n in range(1,11):
            raw = replace(event(4+n,Kind.NOTICE), received_at=base.received_at+timedelta(milliseconds=n),
                          monotonic_ns=base.monotonic_ns+n*400000000)
            raws.append(raw)
        raws.append(replace(event(15,Kind.ASK,price_text='1.1002',tick_type=2),
            received_at=raws[-1].received_at+timedelta(milliseconds=1), monotonic_ns=raws[-1].monotonic_ns+400000000))
        _,values = fold(tuple(raws))
        self.assertIn('SIDE_RECEIPT_STALE',values[-1].reasons)
        self.assertIsNone(values[-1].quote)

    def test_rejected_wire_frame_retains_bytes_digest_and_size(self):
        blob = frame(58,1,101,99)[4:]
        raws = tuple(TranscriptAdapter(transcript()+(blob,),policy(),'session-1',SessionKind.PAPER,now=lambda:AT).events())
        gap = raws[-1]
        self.assertEqual(Kind.GAP,gap.kind)
        self.assertEqual(len(blob),gap.raw_frame_size)
        self.assertTrue(gap.raw_frame_b64)
        self.assertEqual(64,len(gap.raw_frame_sha256))

    def test_foreign_sqlite_is_rejected_without_mutating_bytes_or_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'foreign.sqlite'
            with closing(sqlite3.connect(path)) as db:
                db.execute('PRAGMA journal_mode=WAL')
                db.execute('CREATE TABLE unrelated(value)')
                db.commit()
            before = path.read_bytes()
            with self.assertRaises(ContractError): Journal(path,policy(),'session-1',Origin.FIXTURE,SessionKind.PAPER)
            self.assertEqual(before,path.read_bytes())

    def test_concurrent_handles_same_idempotency_key_commit_one_event(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'own.sqlite'
            with Journal(path,policy(),'session-1',Origin.FIXTURE,SessionKind.PAPER) as a:
                with Journal(path,policy(),'session-1',Origin.FIXTURE,SessionKind.PAPER) as b:
                    one = a.append(prices()[0],as_of=AT)
                    two = b.append(prices()[0],as_of=AT)
                    self.assertEqual(one,two)
                    self.assertEqual(1,len(a.history()))

    def test_reorder_is_recorded_as_rejection_not_sorted(self):
        with tempfile.TemporaryDirectory() as directory:
            with Journal(Path(directory)/'own.sqlite',policy(),'session-1',Origin.FIXTURE,SessionKind.PAPER) as j:
                j.append(prices()[0],as_of=AT)
                j.append(prices()[2],as_of=AT)
                value=j.append(prices()[1],as_of=AT)
                self.assertFalse(value.value.accepted)
                self.assertIn('RECEIVE_SEQUENCE_GAP',value.value.reasons)
                self.assertEqual((1,3,2),tuple(row.value.event.sequence for row in j.history()))

    def test_real_shadow_requires_distinct_signed_approval_and_no_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            with Journal(Path(directory)/'own.sqlite',policy(),'session-1',Origin.SOCKET,SessionKind.PAPER) as j:
                before=j.checkpoint()
                with self.assertRaises(ContractError): observe(j,spec(),cutoff=AT)
                with self.assertRaises(ContractError): observe(j,spec(),cutoff=AT,approval=approval(enabled=True),now=AT)
                self.assertEqual(before,j.checkpoint())

    def test_restart_appends_gap_and_clears_stale_quotes(self):
        with tempfile.TemporaryDirectory() as directory:
            with Journal(Path(directory)/'own.sqlite',policy(),'session-1',Origin.FIXTURE,SessionKind.PAPER) as j:
                collect(FixtureAdapter(prices()),j,now=lambda:AT+timedelta(seconds=1))
                second = tuple(replace(raw,connection_id='connection-2',received_at=raw.received_at+timedelta(seconds=1),
                                       monotonic_ns=raw.monotonic_ns+1000000000) for raw in prices()[:2])
                collect(FixtureAdapter(second),j,now=lambda:AT+timedelta(seconds=2))
                self.assertEqual('COLLECTOR_RESTART_GAP',j.history()[5].value.event.diagnostic)
                self.assertIsNone(j.history()[-1].value.quote)

    def test_restart_after_reorder_uses_unoccupied_receive_key(self):
        with tempfile.TemporaryDirectory() as directory:
            with Journal(Path(directory)/'own.sqlite',policy(),'session-1',Origin.FIXTURE,SessionKind.PAPER) as j:
                for raw in prices()+(event(7,Kind.NOTICE),event(6,Kind.NOTICE)):
                    j.append(raw,as_of=raw.received_at)
                second=replace(prices()[0],connection_id='connection-2',received_at=AT+timedelta(seconds=2),monotonic_ns=2000000000)
                collect(FixtureAdapter((second,)),j,now=lambda:AT+timedelta(seconds=2))
                self.assertEqual(8,j.history()[-2].value.event.sequence)
                self.assertEqual('connection-2',j.history()[-1].value.event.connection_id)

    def test_shadow_rechecks_quote_age_at_actual_generation_time(self):
        with tempfile.TemporaryDirectory() as directory:
            with Journal(Path(directory)/'own.sqlite',policy(),'session-1',Origin.FIXTURE,SessionKind.PAPER) as j:
                for index,raw in enumerate(prices()):
                    j.append(raw,as_of=AT+timedelta(seconds=60) if index==0 else raw.received_at)
                result=observe(j,spec(allow_unknown_source_time=True),cutoff=AT+timedelta(seconds=61))
                self.assertEqual('NO_TRADE',result.signals[-1].hypothetical_direction)
                self.assertIn('RECEIPT_TOO_OLD_AT_GENERATION',result.signals[-1].uncertainty)

    def test_outgoing_bytes_match_installed_official_sdk_without_connecting(self):
        # Oracle dependency is test-only and already installed; no client.run/connect.
        from ibapi.client import EClient
        from ibapi.wrapper import EWrapper
        from ibapi.contract import Contract
        client = EClient(EWrapper())
        client.isConnected = lambda: True
        client.serverVersion = lambda: 157
        client.useProtoBuf = lambda _: False
        client.clientId = 39
        captured=[]
        def capture(code,text):
            payload=(str(code)+'\0'+text).encode('ascii')
            captured.append(struct.pack('!I',len(payload))+payload)
        client.sendMsg=capture
        client.startApi(); self.assertEqual(encode(Command.START,client_id=39),captured[-1])
        client.reqManagedAccts(); self.assertEqual(encode(Command.ACCOUNTS),captured[-1])
        client.reqCurrentTime(); self.assertEqual(encode(Command.TIME),captured[-1])
        client.reqMarketDataType(1); self.assertEqual(encode(Command.DATA_TYPE),captured[-1])
        c=Contract(); c.symbol='EUR'; c.secType='CASH'; c.exchange='IDEALPRO'; c.currency='USD'
        c.strike=0.0  # Explicit fixed Forex request field; SDK defaults to UNSET_DOUBLE.
        client.reqContractDetails(100,c); self.assertEqual(encode(Command.CONTRACT,request_id=100),captured[-1])
        c.conId=12087792
        client.reqMktData(101,c,'',False,False,[])
        self.assertEqual(encode(Command.SUBSCRIBE,con_id=c.conId),captured[-1])
        client.cancelMktData(101); self.assertEqual(encode(Command.CANCEL),captured[-1])
