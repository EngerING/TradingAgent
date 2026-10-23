"""Causal snapshots, denied providers, durable retry and filesystem fault fixtures."""
import base64
from dataclasses import replace
from datetime import timedelta
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from trading_agent.core_v3.contracts import ContractError
from trading_agent.core_v3.market_observation.contracts import Origin, SessionKind, Kind
from trading_agent.market_data.backfill.contracts import BackfillSpec
from trading_agent.market_data.backfill.store import HistoricalStore, HistoricalConsumer
from trading_agent.market_data.backfill.reader import FixtureHistoricalReader, collect
from trading_agent.market_data.backfill.wire import plan
from test_m03a2_backfill import START, END, spec, Clock, permit, stream, response, run, calendar
from test_m03a_reader import packets
from test_core_v39_protocol import frame


def small(): return replace(spec(),end=START+timedelta(days=1),timeframes=(15,))


class RecoveryTests(unittest.TestCase):
    def test_short_default_deadline_cannot_claim_weekly_capacity(self):
        s=spec()
        with self.assertRaises(ContractError):
            replace(s,collector=replace(s.collector,capture=replace(s.collector.capture,max_duration_seconds=60)))

    def test_existing_data_permit_is_not_historical_authority(self):
        from test_m03a_reader import permission
        with tempfile.TemporaryDirectory() as d, HistoricalStore(Path(d),small(),'session-1',Origin.FIXTURE,SessionKind.PAPER,create=True) as store:
            with self.assertRaises(ContractError): FixtureHistoricalReader((),small(),permission(),store)

    def test_provider_permission_denial_is_redacted_and_unavailable(self):
        s=small()
        payloads=packets(hours=calendar())[:3]+(frame(4,2,3000,354,'sensitive provider error fixture')[4:],)
        with tempfile.TemporaryDirectory() as d:
            result,r,_=run(d,s,payloads=payloads)
            self.assertEqual('HISTORICAL_UNAVAILABLE',result.status)
            self.assertIn('PROVIDER_PERMISSION_DENIED',result.quality)
            self.assertNotIn('sensitive provider',result.to_json())

    def test_wrong_connected_account_is_not_accepted_as_environment(self):
        s=small()
        payloads=packets(accounts='OTHERFIXTURE',hours=calendar())[:3]
        with tempfile.TemporaryDirectory() as d:
            result,r,_=run(d,s,payloads=payloads)
            self.assertFalse(result.pages);self.assertNotIn(20,r.sent_opcodes)

    def test_expired_permission_stops_without_historical_send(self):
        with tempfile.TemporaryDirectory() as d, HistoricalStore(Path(d),small(),'session-1',Origin.FIXTURE,SessionKind.PAPER,create=True) as store:
            c=Clock();auth=permit(small(),c);c.wait(1801)
            r=FixtureHistoricalReader(stream(small()),small(),auth,store,now=c.now,mono=c.mono,wait=c.wait)
            with self.assertRaises(ContractError): collect(r,store)
            self.assertNotIn(20,r.sent_opcodes)

    def test_recovery_after_committed_batch_publication_failure(self):
        s=small();c=Clock()
        with tempfile.TemporaryDirectory() as d:
            store=HistoricalStore(Path(d),s,'session-1',Origin.FIXTURE,SessionKind.PAPER,create=True)
            r=FixtureHistoricalReader(stream(s),s,permit(s,c),store,now=c.now,mono=c.mono,wait=c.wait)
            with patch.object(store,'publish',side_effect=OSError('synthetic after commit')):
                with self.assertRaises(OSError): collect(r,store)
            with HistoricalStore(Path(d),s,'session-1',Origin.FIXTURE,SessionKind.PAPER) as recovered:
                self.assertFalse(recovered.pending())
                result=recovered.publish(c.now())
            self.assertEqual('HISTORICAL_COMPLETE',result.status)
            self.assertEqual(96,sum(p.count for p in result.pages))

    def test_recovery_before_append_does_not_invent_completed_interval(self):
        s=small();c=Clock()
        with tempfile.TemporaryDirectory() as d:
            store=HistoricalStore(Path(d),s,'session-1',Origin.FIXTURE,SessionKind.PAPER,create=True)
            r=FixtureHistoricalReader(stream(s),s,permit(s,c),store,now=c.now,mono=c.mono,wait=c.wait)
            append=store.archive.append
            def fail(event,**kwargs):
                if event.diagnostic=='BACKFILL_BATCH': raise OSError('synthetic before commit')
                return append(event,**kwargs)
            with patch.object(store.archive,'append',side_effect=fail):
                with self.assertRaises(OSError): collect(r,store)
            with HistoricalStore(Path(d),s,'session-1',Origin.FIXTURE,SessionKind.PAPER) as recovered:
                self.assertTrue(recovered.pending());self.assertFalse(recovered.samples)
                self.assertIsNotNone(recovered.last_planned)

    def test_restart_cooldown_conserves_ambiguous_planned_request(self):
        s=small();c=Clock()
        with tempfile.TemporaryDirectory() as d:
            run(d,s,clock=c)
            with HistoricalStore(Path(d),s,'session-1',Origin.FIXTURE,SessionKind.PAPER) as store:
                r=FixtureHistoricalReader(stream(s),s,permit(s,c),store,now=c.now,mono=c.mono,wait=c.wait)
                with self.assertRaises(ContractError): collect(r,store)
                self.assertFalse(r.sent_opcodes)

    def test_overlapping_interval_reuses_completed_day(self):
        first=small();c=Clock()
        with tempfile.TemporaryDirectory() as d:
            run(d,first,clock=c);c.wait(600)
            second=replace(first,end=START+timedelta(days=2))
            missing=replace(plan(second)[0],start=START+timedelta(days=1),end=START+timedelta(days=2))
            payloads=packets(hours=calendar())[:3]+(response(missing),)
            result,r,_=run(d,second,clock=c,payloads=payloads)
            self.assertEqual('HISTORICAL_COMPLETE',result.status)
            self.assertEqual(192,sum(p.count for p in result.pages))
            self.assertEqual(1,r.sent_opcodes.count(20))

    def test_snapshot_survives_later_publication_and_is_explicitly_causal(self):
        s=small();c=Clock()
        with tempfile.TemporaryDirectory() as d:
            run(d,s,clock=c)
            old=(Path(d)/'dataset.json').read_bytes();digest=hashlib.sha256(old).hexdigest();cutoff=c.now()
            c.wait(600);run(d,s,clock=c,payloads=packets(hours=calendar())[:3])
            consumer=HistoricalConsumer(Path(d),s,'session-1',Origin.FIXTURE,SessionKind.PAPER)
            with self.assertRaises(ContractError): consumer.read(15,START,s.end,as_of=cutoff)
            view=consumer.read(15,START,s.end,as_of=cutoff,snapshot=digest)
            self.assertEqual(64,len(view.bars))

    def test_cursor_cannot_change_query_or_cutoff(self):
        s=small()
        with tempfile.TemporaryDirectory() as d:
            _,_,c=run(d,s);consumer=HistoricalConsumer(Path(d),s,'session-1',Origin.FIXTURE,SessionKind.PAPER)
            page=consumer.read(15,START,s.end,as_of=c.now())
            with self.assertRaises(ContractError):
                consumer.read(15,START+timedelta(hours=1),s.end,as_of=c.now(),cursor=page.next_cursor)

    def test_corrupt_immutable_page_is_rejected(self):
        s=small()
        with tempfile.TemporaryDirectory() as d:
            result,_,c=run(d,s);page=Path(d)/'pages'/(result.pages[0].sha256+'.json')
            page.write_bytes(page.read_bytes().replace(b'1.15',b'1.16',1))
            with self.assertRaises(ContractError): HistoricalConsumer(Path(d),s,'session-1',Origin.FIXTURE,SessionKind.PAPER).read(15,START,s.end,as_of=c.now())

    def test_consumer_never_opens_sqlite_or_writes(self):
        import io
        s=small()
        with tempfile.TemporaryDirectory() as d:
            _,_,c=run(d,s)
            original=io.open;opened=[]
            def readonly(path,mode='r',*args,**kwargs):
                self.assertFalse(any(v in mode for v in 'wax+'))
                opened.append(mode);return original(path,mode,*args,**kwargs)
            with patch('sqlite3.connect',side_effect=AssertionError('NO_SQLITE')),patch('io.open',side_effect=readonly):
                view=HistoricalConsumer(Path(d),s,'session-1',Origin.FIXTURE,SessionKind.PAPER).read(15,START,s.end,as_of=c.now())
            self.assertEqual(64,len(view.bars))
            self.assertTrue(opened)


if __name__=='__main__': unittest.main()
