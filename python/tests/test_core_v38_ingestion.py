from dataclasses import replace
import hashlib
import unittest

from trading_agent.core_v3.contracts import content_hash
from trading_agent.core_v3.historical_ingestion.contracts import ReviewReceipt
from trading_agent.core_v3.historical_ingestion.ingestion import ingest_canonical
from test_core_v38_contracts import spec, instant
from test_core_v38_time import calendar, tzif


HEADER = 'record_id,symbol,opened_at,closed_at,available_at,open,high,low,close,volume\n'
ROWS = ('b1,EURUSD,2026-01-05T00:00:00Z,2026-01-05T01:00:00Z,2026-01-05T01:00:00Z,1.1000,1.1002,1.0999,1.1001,\n'
        'b2,EURUSD,2026-01-05T01:00:00Z,2026-01-05T02:00:00Z,2026-01-05T02:00:00Z,1.1001,1.1003,1.1000,1.1002,10\n')
EVIDENCE = b'SYNTHETIC fixture evidence; no real provider origin is attested.'


def bundle(raw=None, **changes):
    raw = (HEADER+ROWS).encode() if raw is None else raw
    cal, zone = calendar(), tzif()
    value = spec(raw_sha256=hashlib.sha256(raw).hexdigest(),
        calendar_sha256=content_hash(cal), tzif_sha256=hashlib.sha256(zone).hexdigest(),
        evidence_sha256=hashlib.sha256(EVIDENCE).hexdigest(), **changes)
    review = ReviewReceipt(value.provider_id, value.export_id, content_hash(value), value.evidence_sha256,
                           'fixture-reviewer', 'fixture-external-ref', instant(4))
    return raw, value, cal, zone, EVIDENCE, (review,)


def ingest(raw=None, **changes):
    return ingest_canonical(*bundle(raw, **changes), cutoff=instant(5))


class Ingestion(unittest.TestCase):
    def test_canonical_fixture_preserves_exact_values_and_missing_volume(self):
        result = ingest()
        self.assertEqual(result.manifest.status, 'READY_FOR_INSPECTION')
        self.assertEqual(result.manifest.source_kind, 'SYNTHETIC_TEST_FIXTURE')
        self.assertEqual(result.manifest.authenticity, 'NOT_CRYPTOGRAPHICALLY_VERIFIED')
        self.assertIsNone(result.records[0].volume)
        self.assertEqual(str(result.records[1].volume), '10')
        self.assertEqual(result.manifest.input_rows, 2)
        self.assertEqual(ingest(), result)
        self.assertFalse(result.manifest.backtest_eligible)

    def test_hash_does_not_authenticate_without_host_review(self):
        parts = bundle()
        result = ingest_canonical(*parts[:-1], (), cutoff=instant(5))
        self.assertEqual(result.manifest.status, 'QUARANTINED')
        self.assertEqual(result.records, ())
        self.assertIn('H38_REVIEW_REQUIRED', [i.code for i in result.report.issues])

    def test_real_provider_format_cannot_be_approved_by_generic_receipt(self):
        result = ingest(provider_id='DUKASCOPY_BANK_SA', data_origin='PROVIDER_EXPORT', representation='BID')
        self.assertEqual(result.manifest.status, 'QUARANTINED')
        self.assertIn('H38_PROVIDER_FORMAT_UNVERIFIED', [i.code for i in result.report.issues])
        self.assertEqual(result.manifest.source_kind, 'REAL_HISTORICAL_UNVERIFIED')

    def test_invalid_ohlc_gap_duplicate_or_future_quarantines_entire_batch(self):
        for raw in ((HEADER+ROWS.splitlines()[0]+'\n').encode(),
                    (HEADER+ROWS+ROWS.splitlines()[0]+'\n').encode(),
                    (HEADER+ROWS.replace('1.1002,1.0999', '1.0000,1.0999')).encode(),
                    (HEADER+ROWS.replace('2026-01-05T02:00:00Z,1.1001',
                                         '2026-01-05T04:00:00Z,1.1001')).encode()):
            with self.subTest(raw=raw):
                result = ingest(raw)
                self.assertEqual(result.manifest.status, 'QUARANTINED')
                self.assertEqual(result.records, ())
                self.assertTrue(result.report.issues)
