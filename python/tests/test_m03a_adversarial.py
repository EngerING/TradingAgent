"""Boundary and resource regressions. Fixtures have no broker or financial authority."""
import ast
import base64
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from trading_agent.core_v3.contracts import ContractError
from trading_agent.core_v3.market_observation.contracts import Kind, Origin, SessionKind
from trading_agent.market_data.archive import Archive
from trading_agent.market_data.reader import TranscriptReader
from trading_agent.market_data.calendar import TradingCalendar
from trading_agent.market_data.wire import historical, history_request, cancel_history
from test_m03a_contracts import AT
from test_m03a_reader import config, permission, packets
from test_m03a_wire import batch
from test_core_v39_protocol import frame


class AdversarialTests(unittest.TestCase):
    def reader(self, data, **kw):
        cfg = config(enabled=True)
        return TranscriptReader(data,cfg,permission(cfg),now=lambda:AT,**kw)

    def test_invalid_quote_sides_never_appear_in_consumer(self):
        cases = (packets()[:4], packets()[:4]+(frame(1,6,101,1,'-1',0,0)[4:],),
                 packets()[:5]+(frame(1,6,101,2,'1.0',0,0)[4:],))
        for data in cases:
            with tempfile.TemporaryDirectory() as directory:
                cfg = config(enabled=True)
                with Archive(Path(directory),cfg,'session-1',Origin.FIXTURE,SessionKind.PAPER,create=True) as archive:
                    reader = self.reader(data)
                    for raw in reader.events():
                        archive.append(raw,as_of=AT)
                        if raw.kind is Kind.ASK: self.assertIsNone(archive.observe(AT).quote)
                    self.assertIsNone(archive.observe(AT).quote)

    def test_all_nonread_wire_commands_and_financial_imports_absent(self):
        from trading_agent.core_v3.market_observation.ibkr_protocol import encode, Command
        for opcode in range(300):
            if opcode not in {c.value for c in Command}:
                with self.assertRaises(ContractError): encode(opcode)
        root = Path(__file__).resolve().parents[1]/'trading_agent/market_data'
        for file in root.glob('*.py'):
            tree = ast.parse(file.read_text())
            for node in ast.walk(tree):
                if isinstance(node,ast.ImportFrom) and node.module and node.module.startswith('trading_agent.'):
                    self.assertTrue(node.module.startswith('trading_agent.core_v3.'))
                if isinstance(node,ast.Attribute):
                    self.assertNotIn(node.attr,('placeOrder','cancelOrder','reqGlobalCancel','reqPositions','exec','eval'))

    def test_malformed_history_and_calendar_keep_rejected_frame(self):
        malformed = frame(17,201,'start','end',999)[4:]
        data = packets()+(malformed,)
        events = tuple(self.reader(data).events())
        rejected = next(e for e in events if e.kind is Kind.GAP and e.raw_frame_size)
        self.assertEqual(malformed,base64.b64decode(rejected.raw_frame_b64))
        events = tuple(self.reader(packets(hours='20261023:INVALID')).events())
        self.assertFalse(any(e.kind in (Kind.BID,Kind.ASK) for e in events))
        self.assertTrue(any(e.kind is Kind.GAP and e.raw_frame_size for e in events))

    def test_account_error_is_redacted_even_on_rejection(self):
        events = tuple(self.reader(packets()+(frame(15,1,'U999')[4:],)).events())
        self.assertNotIn('U999',repr(events))
        self.assertTrue(any(e.redacted for e in events))

    def test_oversize_frame_stops_before_body_and_closes(self):
        r = self.reader(packets())
        r.fixture.data = bytearray(struct.pack('!I',20000)+b'never read this body')
        values = tuple(r.events())
        self.assertTrue(r.closed)
        self.assertEqual((),r.sent_opcodes)
        self.assertFalse(any(v.kind is Kind.BID for v in values))

    def test_missing_segment_cannot_be_recreated_silently(self):
        with tempfile.TemporaryDirectory() as directory:
            cfg = config(enabled=True)
            with Archive(Path(directory),cfg,'session-1',Origin.FIXTURE,SessionKind.PAPER,create=True) as archive:
                archive.rotate(AT)
                missing = Path(directory)/archive.segments[0]
                archive.current.close()
                archive.current = None
                missing.unlink()
                with self.assertRaises(ContractError): archive.history()
                self.assertFalse(missing.exists())

    def test_source_range_and_session_boundary(self):
        cal = TradingCalendar('UTC','20261023:0000-20261023:1110',AT)
        bars,_ = historical(batch(),15,AT,cal)
        self.assertFalse(bars[0].complete)
        self.assertIn('BAR_SESSION_BOUNDARY',bars[0].quality)
        with self.assertRaises(ContractError): historical(batch(),15,AT,cal,request_end=AT-timedelta(days=2))

    def test_disk_and_memory_limits_reject_without_unbounded_growth(self):
        cfg = config(enabled=True,max_total_bytes=1048576)
        with tempfile.TemporaryDirectory() as directory:
            with Archive(Path(directory),cfg,'session-1',Origin.FIXTURE,SessionKind.PAPER,create=True) as archive:
                archive.rotate(AT)
                with (Path(directory)/'writer.lock').open('ab') as stream: stream.write(b'x'*1048576)
                with self.assertRaises(ContractError): archive._storage()
        with self.assertRaises(ContractError): self.reader(packets()*100)

    def test_pacing_budget_survives_restart(self):
        cfg = config(enabled=True)
        with tempfile.TemporaryDirectory() as directory:
            with Archive(Path(directory),cfg,'session-1',Origin.FIXTURE,SessionKind.PAPER,create=True) as archive:
                for raw in self.reader(packets()).events(): archive.append(raw,as_of=AT)
                self.assertEqual(AT+timedelta(seconds=600),archive.history_not_before())
            with Archive(Path(directory),cfg,'session-1',Origin.FIXTURE,SessionKind.PAPER) as archive:
                r = self.reader(packets(),history_not_before=archive.history_not_before())
                tuple(r.events())
                self.assertNotIn(20,r.sent_opcodes)


if __name__ == '__main__': unittest.main()
