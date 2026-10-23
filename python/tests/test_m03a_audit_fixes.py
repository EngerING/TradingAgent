"""Independent-audit regressions; every market frame is SYNTHETIC_TEST_FIXTURE."""
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from trading_agent.core_v3.contracts import ContractError
from trading_agent.core_v3.market_observation.contracts import Origin, SessionKind
from trading_agent.market_data.archive import Archive
from trading_agent.market_data.consumer import Consumer
from trading_agent.market_data.reader import TranscriptReader
from trading_agent.market_data.supervisor import Supervisor
from test_m03a_contracts import AT
from test_m03a_reader import config, packets, permission
from test_m03a_wire import batch


class AuditFixTests(unittest.TestCase):
    def archive(self, directory, cfg, *, create=False):
        return Archive(Path(directory),cfg,'session-1',Origin.FIXTURE,SessionKind.PAPER,create=create)

    def rejected_history(self, diagnostic, rejection):
        cfg = config(enabled=True)
        source = TranscriptReader(packets()+(batch(),),cfg,permission(cfg),now=lambda:AT,mono=lambda:0)
        events = tuple(source.events())
        changed = False
        with tempfile.TemporaryDirectory() as directory, self.archive(directory,cfg,create=True) as writer:
            rejected = None
            accepted_batch = None
            for event in events:
                if event.diagnostic == diagnostic:
                    changed = True
                if changed:
                    # Keep the offset on later events: the target alone is rejected,
                    # while the next event can have a valid sequence and clock delta.
                    if rejection == 'RECEIVE_SEQUENCE_GAP':
                        event = replace(event,sequence=event.sequence+1)
                    else:
                        event = replace(event,monotonic_ns=event.monotonic_ns+10**9)
                row = writer.append(event,as_of=AT)
                if event.diagnostic == diagnostic:
                    rejected = row
                if event.diagnostic == 'HISTORY_BATCH':
                    accepted_batch = row
                    break
            self.assertIsNotNone(rejected)
            self.assertFalse(rejected.value.accepted)
            self.assertIn(rejection,rejected.value.reasons)
            durable = writer.history()
            self.assertIn(rejected,durable)
            if diagnostic == 'HISTORY_REQUEST_PLANNED':
                # A batch cannot borrow authority from a rejected request plan even
                # when its own generic Core validation subsequently succeeds.
                self.assertTrue(accepted_batch.value.accepted)
            reader = Consumer(writer.root,cfg,'session-1',Origin.FIXTURE,SessionKind.PAPER)
            observed = reader.poll(AT,15)
            self.assertEqual('OK',observed.code)
            for view in (writer.observe(AT,15),observed.observation):
                self.assertEqual((),view.bars)
                self.assertEqual('UNAVAILABLE',view.freshness)
                self.assertIn(rejection,view.quality)
                self.assertIn('BARS_UNAVAILABLE',view.quality)
                self.assertEqual('SYNTHETIC_TEST_FIXTURE',view.origin.value)
                self.assertEqual('NO_TRADE',view.decision)
                self.assertFalse(view.execution_authorized)
        self.assertTrue(source.closed)

    def test_rejected_request_sequence_cannot_authorize_accepted_batch(self):
        self.rejected_history('HISTORY_REQUEST_PLANNED','RECEIVE_SEQUENCE_GAP')

    def test_rejected_request_clock_cannot_authorize_accepted_batch(self):
        self.rejected_history('HISTORY_REQUEST_PLANNED','RECEIPT_CLOCK_DISCONTINUITY')

    def test_rejected_batch_sequence_never_publishes_new_bars(self):
        self.rejected_history('HISTORY_BATCH','RECEIVE_SEQUENCE_GAP')

    def test_rejected_batch_clock_never_publishes_new_bars(self):
        self.rejected_history('HISTORY_BATCH','RECEIPT_CLOCK_DISCONTINUITY')

    def rotation_failure(self, failure, *, after_quote=False, unexpected=False):
        cfg = config(enabled=True,max_segments=3,max_failures=1)
        readers = []
        with tempfile.TemporaryDirectory() as directory:
            writer = self.archive(directory,cfg,create=True)
            def factory(*args, **kwargs):
                source = TranscriptReader(packets(),*args,**kwargs)
                readers.append(source)
                return source
            supervisor = Supervisor(writer,permission(cfg),reader_factory=factory,
                now=lambda:AT,mono=lambda:0,wait=lambda seconds:False)
            publish = writer._publisher.publish
            fired = []
            published_quote = []
            target = 2 if after_quote else 1
            def broken_publish(at):
                if len(writer.segments) == target and not fired:
                    fired.append(True)
                    raise failure
                result = publish(at)
                if writer.observe(at).quote is not None:
                    published_quote.append(True)
                return result
            try:
                with patch.object(writer._publisher,'publish',side_effect=broken_publish):
                    if unexpected:
                        with self.assertRaises(type(failure)):
                            supervisor.run()
                        health = supervisor.health
                    else:
                        health = supervisor.run()
                self.assertEqual([True],fired)
                if after_quote:
                    self.assertTrue(published_quote)
                self.assertEqual('STORAGE_FAILURE',health.code)
                self.assertTrue(readers and all(source.closed for source in readers))
                self.assertTrue(supervisor.latest is None or supervisor.latest.quote is None)
                self.assertIsNone(writer.current)
                self.assertIsNone(writer._lock)
                # This must succeed before any caller/context-manager closes writer.
                with self.archive(directory,cfg) as replacement:
                    permission(cfg).verify(cfg,AT)
                    self.assertIsNotNone(replacement._lock)
                    self.assertIsNone(replacement.observe(AT).quote)
            finally:
                writer.close()

    def test_initial_rotation_publication_oserror_releases_writer(self):
        self.rotation_failure(OSError('synthetic publication failure'))

    def test_initial_rotation_publication_contracterror_is_storage_failure(self):
        self.rotation_failure(ContractError('M03_PUBLICATION_CHANGED'))

    def test_later_rotation_publication_failure_clears_quote_and_releases_writer(self):
        self.rotation_failure(OSError('synthetic publication failure'),after_quote=True)

    def test_unexpected_rotation_publication_failure_propagates_after_cleanup(self):
        self.rotation_failure(RuntimeError('synthetic unexpected publication failure'),unexpected=True)

    def test_shutdown_publication_failure_overrides_early_stopped_result(self):
        cfg = config(enabled=True,max_segments=3,max_failures=1)
        readers = []
        with tempfile.TemporaryDirectory() as directory:
            writer = self.archive(directory,cfg,create=True)
            def factory(*args, **kwargs):
                source = TranscriptReader(packets(hours='20261023:CLOSED'),*args,**kwargs)
                readers.append(source)
                return source
            supervisor = Supervisor(writer,permission(cfg),reader_factory=factory,
                now=lambda:AT,mono=lambda:0,wait=lambda seconds:True)
            invalidate = writer.invalidate
            failures = []
            def broken_invalidate(at):
                failures.append(True)
                with patch.object(writer._publisher,'publish',side_effect=OSError('synthetic shutdown publication failure')):
                    return invalidate(at)
            try:
                with patch.object(writer,'invalidate',side_effect=broken_invalidate):
                    health = supervisor.run()
                self.assertEqual([True],failures)
                self.assertEqual('STORAGE_FAILURE',health.code)
                self.assertEqual(health,supervisor.health)
                self.assertTrue(readers and all(source.closed for source in readers))
                self.assertTrue(supervisor.latest is None or supervisor.latest.quote is None)
                self.assertIsNone(writer.current)
                self.assertIsNone(writer._lock)
                with self.archive(directory,cfg) as replacement:
                    permission(cfg).verify(cfg,AT)
                    self.assertIsNone(replacement.observe(AT).quote)
            finally:
                writer.close()


if __name__ == '__main__': unittest.main()
