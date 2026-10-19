from dataclasses import replace
from decimal import Decimal, localcontext
import hashlib
import unittest

from trading_agent.core_v3.contracts import ContractError, content_hash
from trading_agent.core_v3.historical_ingestion.ingestion import ingest_canonical
from trading_agent.core_v3.historical_ingestion.records import IngestionManifest
from test_core_v38_contracts import instant
from test_core_v38_ingestion import HEADER, ROWS, EVIDENCE, bundle, ingest


QHEADER = 'record_id,symbol,event_at,available_at,sequence,bid,ask,bid_size,ask_size\n'
QROWS = ('q1,EURUSD,2026-01-05T00:00:00Z,2026-01-05T00:00:00Z,1,1.1000,1.1002,,1\n'
         'q2,EURUSD,2026-01-05T01:00:00Z,2026-01-05T01:00:00Z,2,1.1001,1.1003,2,\n')


def quotes(rows=QROWS, **changes):
    settings = dict(kind='QUOTE', representation='BID_ASK', interval_seconds=0, quote_max_gap_seconds=3600)
    return ingest((QHEADER+rows).encode(), **(settings | changes))


class Adversarial(unittest.TestCase):
    def assert_quarantine(self, result, code=None):
        self.assertEqual(result.manifest.status, 'QUARANTINED')
        self.assertEqual(result.records, ())
        if code:
            self.assertIn(code, [i.code for i in result.report.issues])

    def test_quotes_preserve_sides_and_unknown_sizes(self):
        value = quotes()
        self.assertEqual(value.manifest.status, 'READY_FOR_INSPECTION')
        self.assertEqual(value.records[0].ask-value.records[0].bid, Decimal('0.0002'))
        self.assertIsNone(value.records[0].bid_size)
        self.assertIsNone(value.records[1].ask_size)

    def test_crossed_quotes_negative_sizes_order_gaps_and_sequences(self):
        cases = ((QROWS.replace('1.1000,1.1002', '1.1003,1.1002'), 'H38_CROSSED_QUOTE'),
                 (QROWS.replace(',2,\n', ',-1,\n'), 'H38_NEGATIVE_AMOUNT'),
                 ('\n'.join(reversed(QROWS.splitlines()))+'\n', 'H38_EVENT_ORDER'),
                 (QROWS.splitlines()[0]+'\n', 'H38_GAP'),
                 (QROWS.replace(',2,1.1001', ',True,1.1001'), 'H38_QUOTE_SEQUENCE'),
                 (QROWS.replace('01:00:00Z', '02:00:00Z'), 'H38_OUTSIDE_SESSION'))
        for rows, code in cases:
            with self.subTest(code=code):
                self.assert_quarantine(quotes(rows), code)

    def test_equal_quote_instants_require_distinct_sequence_and_id(self):
        same = QROWS.replace('01:00:00Z', '00:00:00Z')
        # Increasing sequence at equal timestamps is valid; heartbeat covers remaining session.
        self.assertEqual(quotes(same, quote_max_gap_seconds=7200).manifest.status, 'READY_FOR_INSPECTION')
        self.assert_quarantine(quotes(same.replace(',2,1.1001', ',1,1.1001'),
                                      quote_max_gap_seconds=7200), 'H38_DUPLICATE_EVENT')

    def test_hash_tampering_and_review_rebinding(self):
        parts = list(bundle())
        parts[0] = parts[0].replace(b'1.1000', b'1.1001')
        self.assert_quarantine(ingest_canonical(*parts, cutoff=instant(5)), 'H38_RAW_HASH')
        parts = list(bundle())
        parts[1] = replace(parts[1], export_id='different-export')
        self.assert_quarantine(ingest_canonical(*parts, cutoff=instant(5)), 'H38_REVIEW_REQUIRED')
        parts = list(bundle())
        parts[-1] = (parts[-1][0], parts[-1][0])
        self.assert_quarantine(ingest_canonical(*parts, cutoff=instant(5)), 'H38_AMBIGUOUS_REVIEW')

    def test_export_observed_is_a_conservative_availability_bound(self):
        self.assert_quarantine(ingest(available_basis='EXPORT_OBSERVED'), 'H38_EXPORT_AVAILABILITY')
        raw = (HEADER+ROWS.replace('01:00:00Z,1.1000', '03:00:00Z,1.1000')
                           .replace('02:00:00Z,1.1001', '03:00:00Z,1.1001')).encode()
        result = ingest(raw, available_basis='EXPORT_OBSERVED')
        self.assertEqual(result.manifest.status, 'READY_FOR_INSPECTION')
        self.assertTrue(all(r.available_at == instant(3) for r in result.records))

    def test_missing_initial_bar_off_tick_bad_headers_and_nonfinite(self):
        samples = ((HEADER+ROWS.splitlines()[1]+'\n', 'H38_GAP'),
                   (HEADER+ROWS.replace('1.1002,', '1.10021,'), 'H38_OFF_TICK'),
                   (HEADER.replace('close,volume', 'volume,close')+ROWS, 'H38_CSV_HEADER'),
                   (HEADER+ROWS.replace('1.1000,', 'NaN,'), 'DECIMAL_TEXT_REQUIRED'),
                   (HEADER+ROWS.replace('b1,', '=formula,'), 'IDENTIFIER_INVALID'))
        for text, code in samples:
            with self.subTest(code=code):
                self.assert_quarantine(ingest(text.encode()), code)

    def test_global_decimal_context_cannot_change_digest(self):
        normal = ingest()
        with localcontext() as context:
            context.prec = 2
            self.assertEqual(ingest(), normal)

    def test_forged_permissions_or_origin_are_rejected_by_manifest(self):
        manifest = ingest().manifest
        self.assertEqual(IngestionManifest.from_json(manifest.to_json()), manifest)
        for change in ({'backtest_eligible': True}, {'live_enabled': True},
                       {'execution_authority': True}, {'trading_decision': 'TRADE'},
                       {'source_kind': 'SYNTHETIC'}, {'authenticity': 'AUTHENTIC'}):
            with self.subTest(change=change), self.assertRaises(ContractError):
                replace(manifest, **change)

    def test_calendar_evidence_must_be_bound_to_reviewed_local_evidence(self):
        parts = list(bundle())
        parts[2] = replace(parts[2], evidence_sha256='e'*64)
        parts[1] = replace(parts[1], calendar_sha256=content_hash(parts[2]))
        parts[-1] = (replace(parts[-1][0], descriptor_sha256=content_hash(parts[1])),)
        self.assert_quarantine(ingest_canonical(*parts, cutoff=instant(5)), 'H38_CALENDAR_EVIDENCE')

    def test_raw_data_cannot_serve_as_its_own_independent_evidence(self):
        parts = list(bundle())
        parts[4] = parts[0]
        parts[1] = replace(parts[1], evidence_sha256=hashlib.sha256(parts[0]).hexdigest())
        parts[-1] = (replace(parts[-1][0], descriptor_sha256=content_hash(parts[1]),
                             evidence_sha256=parts[1].evidence_sha256),)
        self.assert_quarantine(ingest_canonical(*parts, cutoff=instant(5)), 'H38_SELF_EVIDENCE')

    def test_known_provider_cannot_be_promoted_by_fixture_label(self):
        self.assert_quarantine(ingest(provider_id='DUKASCOPY_BANK_SA'), 'H38_PROVIDER_FORMAT_UNVERIFIED')
