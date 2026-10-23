"""Read-only publication regressions; every market byte is a synthetic fixture."""
from datetime import timedelta
from dataclasses import replace
import ast
import time
from unittest.mock import patch
from pathlib import Path
import tempfile
import unittest

from trading_agent.core_v3.market_observation.contracts import Origin, SessionKind
from trading_agent.market_data.archive import Archive
from trading_agent.market_data.consumer import Consumer, Cursor
from trading_agent.core_v3.contracts import ContractError
from trading_agent.core_v3.market_observation.contracts import Kind, DataType
from trading_agent.core_v3.market_observation.journal import Journal
from trading_agent.market_data.reader import TranscriptReader
from test_m03a_reader import packets, permission
from test_m03a_wire import batch
import test_m03a_archive as archive_fixtures
from test_m03a_contracts import AT
from test_m03a_reader import config

PERFORMANCE = {}


class ConsumerTests(unittest.TestCase):
    def writer(self, directory, **changes):
        cfg = config(enabled=True,**changes)
        return Archive(Path(directory),cfg,'session-1',Origin.FIXTURE,SessionKind.PAPER,create=True)

    def reader(self, writer, **changes):
        return Consumer(writer.root,writer.config,'session-1',Origin.FIXTURE,SessionKind.PAPER,**changes)

    def test_independent_reader_while_writer_is_open(self):
        cfg = config(enabled=True)
        with tempfile.TemporaryDirectory() as directory:
            with Archive(Path(directory),cfg,'session-1',Origin.FIXTURE,SessionKind.PAPER,create=True) as writer:
                archive_fixtures.ArchiveTests().capture(writer)
                reader = Consumer(Path(directory),cfg,'session-1',Origin.FIXTURE,SessionKind.PAPER)
                result = reader.poll(AT)
                self.assertEqual('OK',result.code)
                self.assertEqual('FRESH',result.observation.freshness)
                self.assertEqual('UNCHANGED',reader.poll(AT).code)
                self.assertIsNone(reader.poll(AT+timedelta(seconds=3)).observation.quote)
                cursor = Cursor.from_json(result.cursor.to_json())
                restarted = Consumer(Path(directory),cfg,'session-1',Origin.FIXTURE,SessionKind.PAPER,cursor=cursor)
                self.assertEqual('UNCHANGED',restarted.poll(AT).code)
            self.assertIsNone(reader.poll(AT).observation.quote)

    def test_commit_failure_and_publication_failure_never_expose_new_row(self):
        with tempfile.TemporaryDirectory() as directory, self.writer(directory) as writer:
            archive_fixtures.ArchiveTests().capture(writer)
            reader = self.reader(writer)
            before = reader.poll(AT)
            last = writer.history()[-1].value.event
            next_event = replace(last,sequence=last.sequence+1)
            with patch.object(Journal,'_before_commit',side_effect=OSError('fixture')):
                with self.assertRaises(OSError): writer.append(next_event,as_of=AT)
            self.assertEqual(before.cursor,reader.poll(AT).cursor)
            with patch.object(writer._publisher,'_write',side_effect=OSError('fixture')):
                with self.assertRaises(OSError): writer.append(next_event,as_of=AT)
            self.assertEqual('UNAVAILABLE',reader.poll(AT).code)

    def test_rotation_restart_disconnect_and_checkpoint_are_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.writer(directory) as writer:
                archive_fixtures.ArchiveTests().capture(writer)
                reader = self.reader(writer)
                anchor = reader.poll(AT).cursor
                writer.rotate(AT)
                self.assertIsNone(reader.poll(AT).observation.quote)
                archive_fixtures.ArchiveTests().capture(writer)
                self.assertIsNotNone(reader.poll(AT).observation.quote)
                raw = writer.history()[-1].value.event
                writer.append(replace(raw,kind=Kind.DISCONNECTED,sequence=raw.sequence+1,price_text=None),as_of=AT)
                self.assertIsNone(reader.poll(AT).observation.quote)
                bad = replace(anchor,sha256='0'*64)
                self.assertEqual('UNAVAILABLE',self.reader(writer,cursor=bad).poll(AT).code)
                cfg = writer.config
            with Archive(Path(directory),cfg,'session-1',Origin.FIXTURE,SessionKind.PAPER) as restarted:
                self.assertIsNone(self.reader(restarted,cursor=anchor).poll(AT).observation.quote)

    def test_tampered_missing_and_incomplete_files_do_not_return_cached_quote(self):
        for name in ('segment','consumer.json','view-0.json','owner.json','prefix-0001.json','view-0.tmp'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory, self.writer(directory) as writer:
                archive_fixtures.ArchiveTests().capture(writer)
                reader = self.reader(writer)
                self.assertIsNotNone(reader.poll(AT).observation.quote)
                path = writer.root/(writer.segments[0] if name == 'segment' else name)
                if name == 'segment':
                    # A byte change with unchanged length must invalidate even a warmed cache.
                    with path.open('r+b') as stream:
                        stream.seek(120)
                        stream.write(b'BAD')
                else: path.write_bytes(b'{')
                self.assertEqual('UNAVAILABLE',reader.poll(AT).code)
        with tempfile.TemporaryDirectory() as directory, self.writer(directory) as writer:
            archive_fixtures.ArchiveTests().capture(writer)
            reader = self.reader(writer)
            reader.poll(AT)
            writer.current.close()
            writer.current = None
            (writer.root/writer.segments[0]).unlink()
            self.assertEqual('UNAVAILABLE',reader.poll(AT).code)

    def test_paper_live_origin_and_session_binding(self):
        with tempfile.TemporaryDirectory() as directory, self.writer(directory) as writer:
            archive_fixtures.ArchiveTests().capture(writer)
            for session,origin,environment in (('session-2',Origin.FIXTURE,SessionKind.PAPER),
                    ('session-1',Origin.FIXTURE,SessionKind.LIVE),('session-1',Origin.SOCKET,SessionKind.PAPER)):
                reader = Consumer(writer.root,writer.config,session,origin,environment)
                self.assertEqual('UNAVAILABLE',reader.poll(AT).code)

    def test_nonlive_and_calendar_expiry_never_become_current(self):
        for feed in (1,2,3,4):
            with tempfile.TemporaryDirectory() as directory, self.writer(directory) as writer:
                source = TranscriptReader(packets(feed=feed),writer.config,permission(writer.config),now=lambda:AT,mono=lambda:0)
                iterator = source.events()
                for raw in iterator:
                    writer.append(raw,as_of=AT)
                    if raw.kind is Kind.ASK: break
                iterator.close()
                result = self.reader(writer).poll(AT)
                self.assertEqual({1:DataType.LIVE,2:DataType.FROZEN,3:DataType.DELAYED,4:DataType.DELAYED_FROZEN}[feed],result.observation.feed_type)
                if feed != 1: self.assertIsNone(result.observation.quote)
                self.assertIsNone(self.reader(writer).poll(AT+timedelta(days=1)).observation.quote)

    def test_all_timeframes_survive_without_replaying_on_poll_or_new_quote(self):
        with tempfile.TemporaryDirectory() as directory, self.writer(directory) as writer:
            # Literal synthetic history is persisted, using explicitly planned native requests.
            source = TranscriptReader(packets()+(batch(),),writer.config,permission(writer.config),now=lambda:AT,mono=lambda:0)
            for raw in source.events(): writer.append(raw,as_of=AT)
            reader = self.reader(writer)
            view = reader.poll(AT,15).observation
            self.assertEqual(1,len(view.bars))
            self.assertEqual('STALE',view.freshness)
            self.assertIsNone(view.quote)
            for minutes in (60,240): self.assertEqual('UNAVAILABLE',reader.poll(AT,minutes).observation.freshness)
            folded = writer._projection.folded
            with patch.object(writer,'history',side_effect=AssertionError('must not replay')):
                writer.observe(AT)
                last = writer.current.history()[-1].value.event
                writer.append(replace(last,sequence=last.sequence+1),as_of=AT)
            self.assertEqual(folded+1,writer._projection.folded)
            reader.poll(AT)
            hashed = reader.hashed_bytes
            started = time.perf_counter()
            for _ in range(25): self.assertIsNotNone(reader.poll(AT,15).observation)
            elapsed = time.perf_counter()-started
            self.assertEqual(hashed,reader.hashed_bytes)
            self.assertLess(elapsed,10)
            PERFORMANCE.update(warm_polls=25,warm_poll_ms_mean=elapsed*1000/25,warm_rehashed_bytes=0)

    def test_budget_and_cursor_shape_reject_without_limit_increases(self):
        with self.assertRaises(ContractError): Cursor('0'*64,17,0,'0'*64)
        with tempfile.TemporaryDirectory() as directory, self.writer(directory,max_segments=1) as writer:
            archive_fixtures.ArchiveTests().capture(writer)
            with self.assertRaises(ContractError): writer.rotate(AT)
            with (writer.root/'view-0.tmp').open('wb') as stream: stream.write(b'x'*131073)
            self.assertEqual('UNAVAILABLE',self.reader(writer).poll(AT).code)

    def test_consumer_has_no_sqlite_write_capture_or_execution_surface(self):
        import trading_agent.market_data.consumer as module
        tree = ast.parse(Path(module.__file__).read_text())
        imported = [node.module or '' for node in ast.walk(tree) if isinstance(node,ast.ImportFrom)]
        self.assertFalse(any('journal' in n or 'reader' in n or 'publication' in n for n in imported))
        for node in ast.walk(tree):
            if isinstance(node,ast.Attribute):
                self.assertNotIn(node.attr,('connect','write','unlink','append','placeOrder','cancelOrder','execute','executescript'))

    def test_three_complete_native_bar_views_have_causal_availability(self):
        with tempfile.TemporaryDirectory() as directory, self.writer(directory) as writer:
            clock = [AT]
            older = str(int((AT-timedelta(hours=4)).timestamp()))
            source = TranscriptReader(packets()+(batch(),batch(60),batch(240,timestamp=older)),writer.config,
                permission(writer.config),now=lambda:clock[0],mono=lambda:int((clock[0]-AT).total_seconds()*10**9))
            receive = source.fixture.recv
            def paced(n):
                for req,offset in ((202,20),(203,40)):
                    if source.fixture.data[4:].startswith(('17\0'+str(req)+'\0').encode()) and clock[0] < AT+timedelta(seconds=offset):
                        clock[0] = AT+timedelta(seconds=offset)
                        import socket
                        raise socket.timeout()
                return receive(n)
            source.fixture.recv = paced
            for raw in source.events(): writer.append(raw,as_of=clock[0])
            reader = self.reader(writer)
            for minutes in (15,60,240):
                result = reader.poll(clock[0],minutes)
                self.assertEqual(1,len(result.observation.bars))
                self.assertEqual('STALE',result.observation.freshness)
                self.assertEqual(minutes,result.observation.bars[0].minutes)
                self.assertLessEqual(result.observation.bars[0].available_at,result.observation.as_of)
            self.assertEqual('UNAVAILABLE',reader.poll(AT).code)

    def test_clock_uncertainty_and_forged_lifetime_never_extend_live_quote(self):
        with tempfile.TemporaryDirectory() as directory, self.writer(directory) as writer:
            archive_fixtures.ArchiveTests().capture(writer)
            reader = self.reader(writer)
            result = reader.poll(AT)
            self.assertIsNotNone(result.observation.quote)
            with patch('trading_agent.market_data.consumer.time.monotonic_ns',return_value=0):
                self.assertIsNone(reader.poll(AT).observation.quote)
            with patch('trading_agent.market_data.consumer.time.monotonic_ns',return_value=time.monotonic_ns()+10**10):
                self.assertIsNone(reader.poll(AT).observation.quote)
            from trading_agent.market_data.consumer import Publication
            path = writer.root/'consumer.json'
            publication = Publication.from_json(path.read_bytes())
            path.write_text(replace(publication,valid_until=AT+timedelta(days=10)).to_json())
            self.assertEqual('UNAVAILABLE',reader.poll(AT).code)

    def test_external_cursor_detects_whole_prefix_rollback(self):
        with tempfile.TemporaryDirectory() as directory, self.writer(directory) as writer:
            archive_fixtures.ArchiveTests().capture(writer)
            reader = self.reader(writer)
            older = reader.poll(AT).cursor
            saved = {p.name:p.read_bytes() for p in writer.root.iterdir() if p.name != 'writer.lock'}
            raw = writer.history()[-1].value.event
            writer.append(replace(raw,sequence=raw.sequence+1),as_of=AT)
            newer = reader.poll(AT).cursor
            self.assertNotEqual(older,newer)
            writer.current.close()
            writer.current = None
            for name,data in saved.items(): (writer.root/name).write_bytes(data)
            self.assertEqual('UNAVAILABLE',self.reader(writer,cursor=newer).poll(AT).code)

    def test_unknown_feed_and_changed_sealed_segment_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory, self.writer(directory) as writer:
            archive_fixtures.ArchiveTests().capture(writer)
            raw = writer.history()[-1].value.event
            writer.append(replace(raw,sequence=raw.sequence+1,kind=Kind.DATA_TYPE,data_type=DataType.UNKNOWN,price_text=None),as_of=AT)
            result = self.reader(writer).poll(AT)
            self.assertIsNone(result.observation.quote)
            self.assertEqual(DataType.UNKNOWN,result.observation.feed_type)
            writer.rotate(AT)
            with (writer.root/writer.segments[0]).open('r+b') as stream:
                stream.seek(120)
                stream.write(b'BAD')
            with self.assertRaises(ContractError): writer.observe(AT)
            self.assertEqual('UNAVAILABLE',self.reader(writer).poll(AT).code)

    def test_new_quote_rehashes_only_active_segment_and_folds_one_row(self):
        with tempfile.TemporaryDirectory() as directory, self.writer(directory) as writer:
            for _ in range(3):
                if writer.segments: writer.rotate(AT)
                archive_fixtures.ArchiveTests().capture(writer)
            reader = self.reader(writer)
            reader.poll(AT)
            before,folded = reader.hashed_bytes,writer._projection.folded
            last = writer.current.history()[-1].value.event
            started = time.perf_counter()
            with patch.object(writer,'history',side_effect=AssertionError('no archive replay')):
                writer.append(replace(last,sequence=last.sequence+1),as_of=AT)
                writer.observe(AT)
            result = reader.poll(AT)
            elapsed = time.perf_counter()-started
            size = (writer.root/writer.segments[-1]).stat().st_size
            self.assertIsNotNone(result.observation.quote)
            self.assertEqual(folded+1,writer._projection.folded)
            self.assertEqual(size,reader.hashed_bytes-before)
            PERFORMANCE.update(segments=3,new_quote_folded_rows=1,new_quote_rehashed_bytes=size,
                               new_quote_append_and_poll_ms=elapsed*1000)

    def test_writer_restart_invalidates_epoch_before_long_journal_verification(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.writer(directory) as writer:
                archive_fixtures.ArchiveTests().capture(writer)
                reader = self.reader(writer)
                self.assertIsNotNone(reader.poll(AT).observation.quote)
                cfg = writer.config
            scan = Archive._scan
            def paused_scan(reopened):
                result = reader.poll(AT)
                self.assertTrue(result.observation is None or result.observation.quote is None)
                return scan(reopened)
            with patch.object(Archive,'_scan',paused_scan):
                with Archive(Path(directory),cfg,'session-1',Origin.FIXTURE,SessionKind.PAPER): pass




if __name__ == '__main__': unittest.main()
