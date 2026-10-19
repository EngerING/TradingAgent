from dataclasses import replace
from pathlib import Path
import hashlib
import os
import tempfile
import unittest

from trading_agent.core_v3.contracts import ContractError, canonical_bytes, content_hash
from trading_agent.core_v3.historical_ingestion.files import ingest_local, archive_local, read_local, verify_archive
from trading_agent.core_v3.historical_ingestion.dukascopy_intake import DukascopySettings, stage_export, verify_export
from test_core_v38_contracts import instant
from test_core_v38_ingestion import bundle


class Files(unittest.TestCase):
    def make_input(self, root):
        raw, spec, cal, zone, evidence, reviews = bundle()
        for name, data in {'raw.csv': raw, 'descriptor.json': canonical_bytes(spec),
                           'calendar.json': canonical_bytes(cal), 'timezone.tzif': zone,
                           'evidence.bin': evidence}.items():
            (root/name).write_bytes(data)
        return reviews

    def test_local_roundtrip_archive_and_idempotence(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            reviews = self.make_input(root)
            result = ingest_local(root, reviews=reviews, cutoff=instant(5))
            target = archive_local(root/'archive', root, reviews=reviews, cutoff=instant(5))
            self.assertEqual(target.name, hashlib.sha256((target/'file_index.json').read_bytes()).hexdigest())
            self.assertEqual((target/'raw.csv').read_bytes(), (root/'raw.csv').read_bytes())
            self.assertEqual(verify_archive(target, reviews=reviews, cutoff=instant(5)), result)
            self.assertEqual(archive_local(root/'archive', root, reviews=reviews, cutoff=instant(5)), target)
            self.assertEqual(len((target/'normalized.jsonl').read_bytes().splitlines()), 2)

    def test_archive_detects_corruption_and_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            reviews = self.make_input(root)
            target = archive_local(root/'archive', root, reviews=reviews, cutoff=instant(5))
            (target/'raw.csv').write_bytes(b'corrupt')
            with self.assertRaises(ContractError):
                verify_archive(target, reviews=reviews, cutoff=instant(5))
            with self.assertRaises(ContractError):
                archive_local(root/'archive', root, reviews=reviews, cutoff=instant(5))
            self.assertEqual((target/'raw.csv').read_bytes(), b'corrupt')

    def test_dangerous_paths_rejected_before_io(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in ('../secret', '.local/raw.csv', 'C:/secret', 'raw.csv:stream',
                         'https://provider/data', r'\\server\data', 'NUL', 'CON.csv', 'raw.csv.', 'a\\b'):
                with self.subTest(name=name), self.assertRaises(ContractError):
                    read_local(root, name)

    def test_quarantine_preserves_original_and_exposes_no_normalized_rows(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.make_input(root)
            target = archive_local(root/'archive', root, reviews=(), cutoff=instant(5))
            self.assertEqual((target/'normalized.jsonl').read_bytes(), b'')
            self.assertTrue((target/'raw.csv').read_bytes())
            value = verify_archive(target, reviews=(), cutoff=instant(5))
            self.assertEqual(value.manifest.status, 'QUARANTINED')

    def test_dukascopy_intake_is_schema_opaque_and_keeps_bid_ask_separate(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            original = b'SYNTHETIC fixture opaque header\nNever guess these columns\n'
            (root/'bid.csv').write_bytes(original)
            settings = DukascopySettings('EURUSD', 'H1', 'UTC', 'BID', '2024-01',
                instant(3), instant(4), 'SYNTHETIC_TEST_FIXTURE', 'declared-export-config-1')
            bid = stage_export(root, 'bid.csv', root/'archive', settings, cutoff=instant(5))
            ask = stage_export(root, 'bid.csv', root/'archive', replace(settings, side='ASK'), cutoff=instant(5))
            self.assertNotEqual(bid, ask)
            self.assertEqual((bid/'raw.csv').read_bytes(), original)
            text = (bid/'manifest.json').read_text()
            self.assertIn('FORMAT_UNVERIFIED', text)
            self.assertIn('NO_TRADE', text)
            self.assertEqual((bid/'normalized.jsonl').read_bytes(), b'')
            self.assertEqual(stage_export(root, 'bid.csv', root/'archive', settings, cutoff=instant(5)), bid)
            self.assertEqual(verify_export(bid, cutoff=instant(5)), settings)
            (bid/'normalized.jsonl').write_bytes(b'forged normalized data')
            with self.assertRaises(ContractError):
                verify_export(bid, cutoff=instant(5))

    def test_dukascopy_settings_reject_other_scope_and_untrusted_permissions(self):
        value = DukascopySettings('EURUSD', 'H1', 'UTC', 'BID', '2024-01',
            instant(3), instant(4), 'SYNTHETIC_TEST_FIXTURE', 'fixture-config')
        for changes in ({'side': 'MID'}, {'timezone_name': 'LOCAL'}, {'month': '2024-13'},
                        {'instrument': 'USDJPY'}, {'provider': 'OTHER'}, {'timeframe': 'M1'}):
            with self.subTest(changes=changes), self.assertRaises(ContractError):
                replace(value, **changes)
        with self.assertRaises(ContractError):
            DukascopySettings.from_dict(value.to_dict() | {'approved': True})
        with self.assertRaises(ContractError):
            DukascopySettings.from_dict(value.to_dict() | {'observed_at': '2026-01-05T04:00:00-00:00'})

    def test_hardlinked_inputs_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'original.csv').write_bytes(b'SYNTHETIC fixture')
            os.link(root/'original.csv', root/'linked.csv')
            with self.assertRaises(ContractError):
                read_local(root, 'linked.csv')
