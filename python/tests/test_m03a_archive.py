"""Durability, bounded rotation and causal M03-B views using synthetic byte streams."""
import base64
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from trading_agent.core_v3.contracts import ContractError
from trading_agent.core_v3.market_observation.contracts import Origin, SessionKind, Kind
from trading_agent.core_v3.market_observation.journal import Journal
from trading_agent.market_data.archive import Archive
from test_m03a_contracts import AT
from test_m03a_reader import config, permission, packets
from trading_agent.market_data.reader import TranscriptReader


class ArchiveTests(unittest.TestCase):
    def capture(self, archive):
        reader = TranscriptReader(packets(), archive.config, permission(archive.config), now=lambda:AT)
        iterator = reader.events()
        try:
            for event in iterator:
                archive.append(event, as_of=AT)
                if event.kind is Kind.ASK: break
        finally: iterator.close()

    def archive(self, directory, cfg=None, **kw):
        return Archive(Path(directory), cfg or config(enabled=True), 'session-1', Origin.FIXTURE,
                       SessionKind.PAPER, **kw)

    def test_commit_before_view_and_stale_quote(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.archive(directory, create=True) as archive:
                self.capture(archive)
                view = archive.observe(AT)
                self.assertEqual('FRESH', view.freshness)
                self.assertIsNotNone(view.quote)
                self.assertEqual('NO_TRADE', view.decision)
                self.assertEqual(view, type(view).from_json(view.to_json()))
                self.assertIsNone(archive.observe(AT+timedelta(seconds=3)).quote)
                self.assertEqual('UNAVAILABLE', archive.observe(AT-timedelta(seconds=1)).freshness)

    def test_restart_gap_chain_and_no_cross_epoch_quote(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.archive(directory, create=True) as archive:
                self.capture(archive)
                before = archive.checkpoint()
            with self.archive(directory, checkpoint=before) as archive:
                self.assertEqual('UNAVAILABLE', archive.observe(AT).freshness)
                archive.rotate(AT)
                self.assertTrue(any(r.value.event.diagnostic == 'COLLECTOR_RESTART_GAP' for r in archive.history()))
                self.assertIsNone(archive.observe(AT).quote)
                self.assertEqual(2, len(archive.segments))

    def test_failed_commit_closes_without_uncommitted_quote(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.archive(directory, create=True) as archive:
                with patch.object(Journal, '_before_commit', side_effect=OSError('fixture')):
                    with self.assertRaises(OSError): self.capture(archive)
                self.assertIsNone(archive.observe(AT).quote)

    def test_origin_environment_and_unknown_files_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.archive(directory, create=True): pass
            with self.assertRaises(ContractError):
                Archive(Path(directory), config(enabled=True),'session-1',Origin.SOCKET,SessionKind.PAPER)
            (Path(directory)/'unowned.txt').write_text('fixture')
            with self.assertRaises(ContractError): self.archive(directory)

    def test_segment_budget_and_exclusive_writer(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.archive(directory, config(enabled=True,max_segments=1), create=True) as archive:
                with self.assertRaises(ContractError): self.archive(directory, archive.config)
                archive.rotate(AT)
                with self.assertRaises(ContractError): archive.rotate(AT)

    def test_duplicate_conflict_and_checkpoint_reject_rollback(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.archive(directory, create=True) as archive:
                r = TranscriptReader(packets(),archive.config,permission(archive.config),now=lambda:AT)
                iterator = r.events()
                event = next(iterator)
                row = archive.append(event, as_of=AT)
                self.assertEqual(row, archive.append(event, as_of=AT))
                with self.assertRaises(ContractError): archive.append(replace(event,diagnostic='CONFLICT'),as_of=AT)
                iterator.close()
                checkpoint = archive.checkpoint()
            wrong = replace(checkpoint, sha256='0'*64)
            with self.assertRaises(ContractError): self.archive(directory, checkpoint=wrong)


if __name__ == '__main__': unittest.main()
