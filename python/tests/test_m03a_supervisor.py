"""Supervisor runs real parser/journal with identified synthetic transport only."""
from datetime import timedelta
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from trading_agent.core_v3.market_observation.contracts import Origin, SessionKind, Kind
from trading_agent.core_v3.market_observation.journal import Journal
from trading_agent.market_data.archive import Archive
from trading_agent.market_data.reader import TranscriptReader
from trading_agent.market_data.supervisor import Supervisor
from test_m03a_contracts import AT
from test_m03a_reader import config, permission, packets
from test_m03a_wire import batch
from test_core_v39_protocol import frame


class SupervisorTests(unittest.TestCase):
    def run_fixture(self, directory, cfg=None, payloads=None, wait=None):
        cfg = cfg or config(enabled=True,max_segments=3,max_failures=1)
        archive = Archive(Path(directory),cfg,'session-1',Origin.FIXTURE,SessionKind.PAPER,create=True)
        readers = []
        def factory(*args, **kw):
            reader = TranscriptReader(payloads or packets(),*args,**kw)
            readers.append(reader)
            return reader
        supervisor = Supervisor(archive,permission(cfg),reader_factory=factory,now=lambda:AT,mono=lambda:0,
                                wait=wait or (lambda seconds:False))
        return archive,supervisor,readers

    def test_disconnect_bounded_progressive_retry_and_repreflight(self):
        waits = []
        with tempfile.TemporaryDirectory() as directory:
            archive,s,readers = self.run_fixture(directory,wait=lambda n:waits.append(n) or False)
            with archive:
                result = s.run()
                self.assertEqual('RETRY_BUDGET',result.code)
                self.assertEqual([2],waits)
                self.assertEqual(2,len(readers))
                epochs = [r.value.event.connection_id for r in archive.history() if r.value.event.kind is Kind.CONNECTED]
                self.assertEqual(2,len(set(epochs)))
                self.assertTrue(all(r.closed for r in readers))
                self.assertTrue(all(r.sent_opcodes[:4] == (71,17,49,9) for r in readers))
                self.assertIsNone(s.latest.quote)

    def test_closed_wait_is_cancellable_and_no_web_dependency(self):
        with tempfile.TemporaryDirectory() as directory:
            archive,s,readers = self.run_fixture(directory,payloads=packets(hours='20261023:CLOSED'),wait=lambda n:True)
            with archive:
                self.assertEqual('STOPPED',s.run().code)
                self.assertNotIn(1,readers[0].sent_opcodes)
                self.assertNotIn(20,readers[0].sent_opcodes)

    def test_storage_failure_closes_reader_and_does_not_publish(self):
        with tempfile.TemporaryDirectory() as directory:
            archive,s,readers = self.run_fixture(directory)
            with archive, patch.object(Journal,'_before_commit',side_effect=OSError('fixture')):
                self.assertEqual('STORAGE_FAILURE',s.run().code)
                self.assertIsNone(s.latest)
                self.assertTrue(readers[0].closed)
                self.assertEqual((),archive.history())

    def test_connectivity_callback_reconnects_even_when_tcp_did_not_close(self):
        with tempfile.TemporaryDirectory() as directory:
            archive,s,readers = self.run_fixture(directory,payloads=packets()+(frame(4,2,-1,1100,'fixture')[4:],))
            with archive:
                self.assertEqual('RETRY_BUDGET',s.run().code)
                self.assertEqual(2,len(readers))
                self.assertTrue(all(r.closed for r in readers))

    def test_offline_default_never_creates_transport(self):
        with tempfile.TemporaryDirectory() as directory:
            archive,s,readers = self.run_fixture(directory,config())
            with archive:
                self.assertEqual('DISABLED',s.run().code)
                self.assertEqual([],readers)

    def test_historical_batch_persisted_and_available_after_reopen(self):
        with tempfile.TemporaryDirectory() as directory:
            archive,s,readers = self.run_fixture(directory,config(enabled=True,max_failures=0),payloads=packets()+(batch(),))
            with archive:
                s.run()
                value = archive.observe(AT,15)
                self.assertEqual(1,len(value.bars))
                self.assertEqual('SYNTHETIC_TEST_FIXTURE',value.origin.value)
                self.assertIn('DISCONNECTED_OR_RESTARTED',value.quality)
                before = value.to_json()
            with Archive(Path(directory),archive.config,'session-1',Origin.FIXTURE,SessionKind.PAPER) as reopened:
                self.assertEqual(before,reopened.observe(AT,15).to_json())


if __name__ == '__main__': unittest.main()
