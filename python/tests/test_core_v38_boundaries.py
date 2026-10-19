"""Synthetic calendar/month and hostile inputs; never real Dukascopy schema evidence."""
import ast
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from trading_agent.core_v3.contracts import ContractError, canonical_bytes, content_hash
from trading_agent.core_v3.historical_ingestion.contracts import DatasetSpec, ReviewReceipt, Session, SessionCalendar
from trading_agent.core_v3.historical_ingestion.ingestion import ingest_canonical
from trading_agent.core_v3.historical_ingestion.files import archive_local
from trading_agent.core_v3.historical_ingestion.records import HistoricalBar, HistoricalQuote
from test_core_v38_contracts import spec, instant
from test_core_v38_time import tzif
from test_core_v38_ingestion import HEADER, ROWS, EVIDENCE, bundle, ingest
from test_core_v38_adversarial import QHEADER, QROWS


class Boundaries(unittest.TestCase):
    def test_one_month_h1_synthetic_calendar_without_weekend_fill(self):
        begin = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 2, 1, tzinfo=timezone.utc)
        sessions, rows = [], []
        day = begin
        while day < end:
            if day.weekday() < 5:  # Fabricated fixture calendar, NOT a Dukascopy session specification.
                sessions.append(Session('s'+day.strftime('%Y%m%d'), day.date().isoformat(), day, day+timedelta(days=1)))
                for hour in range(24):
                    opened = day+timedelta(hours=hour)
                    closed = opened+timedelta(hours=1)
                    text = lambda value: value.isoformat(timespec='seconds').replace('+00:00', 'Z')
                    rows.append(f'b{len(rows)},EURUSD,{text(opened)},{text(closed)},{text(closed)},1.1,1.1002,1.0999,1.1001,\n')
            day += timedelta(days=1)
        raw = (HEADER+''.join(rows)).encode()
        zone = tzif()
        evidence_hash = hashlib.sha256(EVIDENCE).hexdigest()
        cal = SessionCalendar('synthetic-month', 'r1', 'UTC', evidence_hash, begin, end, tuple(sessions))
        value = spec(window_start=begin, window_end=end, exported_at=end,
            observed_at=end+timedelta(hours=1), raw_sha256=hashlib.sha256(raw).hexdigest(),
            calendar_sha256=content_hash(cal), tzif_sha256=hashlib.sha256(zone).hexdigest(), evidence_sha256=evidence_hash)
        receipt = ReviewReceipt(value.provider_id, value.export_id, content_hash(value), evidence_hash,
            'fixture-reviewer', 'synthetic-month-evidence', end+timedelta(hours=1))
        result = ingest_canonical(raw, value, cal, zone, EVIDENCE, (receipt,), cutoff=end+timedelta(hours=2))
        self.assertEqual(result.manifest.status, 'READY_FOR_INSPECTION')
        self.assertEqual(len(result.records), 552)
        self.assertEqual(result.report.expected_intervals, 552)
        self.assertEqual(result.report.gap_count, 0)
        self.assertEqual(result.manifest.source_kind, 'SYNTHETIC_TEST_FIXTURE')

    def test_malformed_csv_utf8_and_empty_files_are_quarantined(self):
        for raw in (b'', b'\xff', (HEADER+'"unterminated\n').encode(),
                    (HEADER+'\n'+ROWS).encode(), b'\xef\xbb\xbf'+(HEADER+ROWS).encode()):
            with self.subTest(raw=raw):
                result = ingest(raw)
                self.assertEqual(result.manifest.status, 'QUARANTINED')
                self.assertEqual(result.records, ())

    def test_row_and_byte_budgets_fail_closed(self):
        first = QROWS.splitlines()[0]
        rows = '\n'.join(first.replace('q1,', f'q{i},').replace(',1,1.1000', f',{i},1.1000')
                         for i in range(4097))+'\n'
        raw = (QHEADER+rows).encode()
        result = ingest(raw, kind='QUOTE', representation='BID_ASK', interval_seconds=0, quote_max_gap_seconds=7200)
        self.assertEqual(result.manifest.status, 'QUARANTINED')
        self.assertFalse(result.report.scan_complete)
        self.assertIn('H38_ROW_LIMIT', [i.code for i in result.report.issues])
        with self.assertRaises(ContractError):
            ingest(b'x'*(1048576+1))

    def test_combined_errors_stay_bounded_and_archivable(self):
        raw = (HEADER+(ROWS.splitlines()[0]+'\n')*50+'bad,row\n'*128).encode()
        parts = list(bundle(raw))
        parts[4] = b''
        parts[1] = replace(parts[1], raw_sha256='0'*64, calendar_sha256='0'*64,
                           tzif_sha256='0'*64, evidence_sha256='0'*64)
        parts[-1] = ()
        result = ingest_canonical(*parts, cutoff=instant(3))
        self.assertEqual(result.manifest.status, 'QUARANTINED')
        self.assertLessEqual(len(result.report.issues), 256)
        self.assertIn('H38_ISSUE_LIMIT', [i.code for i in result.report.issues])
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name, data in dict(zip(('raw.csv', 'descriptor.json', 'calendar.json', 'timezone.tzif', 'evidence.bin'),
                 (raw, canonical_bytes(parts[1]), canonical_bytes(parts[2]), parts[3], b''))).items():
                (root/name).write_bytes(data)
            target = archive_local(root/'archive', root, cutoff=instant(3))
            self.assertEqual((target/'raw.csv').read_bytes(), raw)
            self.assertEqual((target/'normalized.jsonl').read_bytes(), b'')

    def test_timezone_conversion_underflow_is_quarantined(self):
        start = datetime(1, 1, 1, tzinfo=timezone.utc)
        end = start+timedelta(hours=1)
        parts = list(bundle())
        parts[3] = tzif('America/New_York')
        parts[2] = SessionCalendar('fixture-ancient', 'r1', 'America/New_York', parts[1].evidence_sha256,
            start, end, (Session('s', '0001-01-01', start, end),))
        parts[1] = replace(parts[1], timezone_name='America/New_York', window_start=start, window_end=end,
            calendar_sha256=content_hash(parts[2]), tzif_sha256=hashlib.sha256(parts[3]).hexdigest())
        result = ingest_canonical(*parts, cutoff=instant(5))
        self.assertIn('H38_TIMESTAMP_RANGE', [i.code for i in result.report.issues])
        self.assertEqual(result.records, ())

    def test_late_publication_cannot_be_reordered_into_a_causal_stream(self):
        raw = (HEADER+ROWS.replace('01:00:00Z,1.1000', '03:00:00Z,1.1000')).encode()
        result = ingest(raw)
        self.assertIn('H38_AVAILABILITY_ORDER', [i.code for i in result.report.issues])
        self.assertEqual(result.records, ())

    def test_package_imports_have_no_engine_broker_model_or_dynamic_execution(self):
        folder = Path(__file__).parents[1]/'trading_agent/core_v3/historical_ingestion'
        forbidden = ('socket', 'subprocess', 'requests', 'http', 'broker', 'tws', 'event_backtest',
                     'statistical_validation', 'strategy_catalog', 'research_runner', 'kronos', 'providers')
        for path in folder.glob('*.py'):
            tree = ast.parse(path.read_text(encoding='utf-8'))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or '']
                else:
                    names = []
                self.assertFalse(any(word in name for name in names for word in forbidden), (path, names))
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    self.assertNotIn(node.func.id, ('eval', 'exec', '__import__'))

    def test_local_types_cannot_implicitly_become_backtester_input(self):
        from trading_agent.core_v3.event_backtest.contracts import SyntheticBar, SyntheticDataset
        from trading_agent.core_v3.event_backtest.reader import load
        result = ingest()
        self.assertNotIsInstance(result, SyntheticDataset)
        self.assertNotIsInstance(result.records[0], SyntheticBar)
        with self.assertRaises(ContractError):
            load(None, None, None, result, None)

    def test_failed_publish_leaves_no_readable_archive_or_modified_input(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            raw, value, cal, zone, evidence, reviews = bundle()
            for name, data in {'raw.csv': raw, 'descriptor.json': canonical_bytes(value),
                'calendar.json': canonical_bytes(cal), 'timezone.tzif': zone, 'evidence.bin': evidence}.items():
                (root/name).write_bytes(data)
            with patch.object(Path, 'rename', side_effect=OSError('controlled failure')):
                with self.assertRaises(OSError):
                    archive_local(root/'archive', root, reviews=reviews, cutoff=instant(5))
            self.assertEqual(list((root/'archive').iterdir()), [])
            self.assertEqual((root/'raw.csv').read_bytes(), raw)
