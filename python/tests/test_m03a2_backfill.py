"""M03-A.2 fixtures only. No TWS, credentials or financial operation."""
import base64
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from trading_agent.core_v3.contracts import ContractError, canonical_bytes, content_hash
from trading_agent.core_v3.market_observation.contracts import Origin, SessionKind, CapturePolicy, Kind
from trading_agent.market_data.contracts import CollectorConfig
from trading_agent.market_data.backfill.contracts import BackfillSpec, HistoricalPermit, HistoricalApproval
from trading_agent.market_data.backfill.wire import plan, request, cancel, history_fields
from trading_agent.market_data.backfill.store import HistoricalStore, HistoricalConsumer
from trading_agent.market_data.backfill.reader import HistoricalReader, FixtureHistoricalReader, collect
from test_core_v39_protocol import approval, KEY, frame
from test_m03a_reader import packets

START=datetime(2026,10,19,tzinfo=timezone.utc)
END=START+timedelta(days=7)


class Clock:
    def __init__(self): self.at=END; self.ns=0
    def now(self): return self.at
    def mono(self): return self.ns
    def wait(self, seconds): self.at+=timedelta(seconds=seconds); self.ns+=int(seconds*10**9); return False


def spec(**kw):
    cfg=CollectorConfig('historical-fixture',CapturePolicy('history-fixture',max_duration_seconds=300),enabled=True)
    return BackfillSpec(cfg,START,END,enabled=True,**kw)


def permit(s, clock, **kw):
    cap=approval(enabled=True,policy_sha256=content_hash(s.collector.capture.to_dict()),
        issued_at=clock.now()-timedelta(seconds=1),expires_at=clock.now()+timedelta(minutes=30),**kw)
    p=HistoricalPermit(content_hash(cap.grant.to_dict()),content_hash(s.to_dict()),cap.grant.issued_at,cap.grant.expires_at)
    return HistoricalApproval(cap,p,hmac.new(KEY,canonical_bytes(p.to_dict()),hashlib.sha256).hexdigest(),KEY)


def calendar(open_now=False, unknown=False):
    if unknown: return '20261026:CLOSED'
    days=[]
    for i in range(8):
        d=START+timedelta(days=i)
        hours=(d.strftime('%Y%m%d')+':0000-'+(d+timedelta(days=1)).strftime('%Y%m%d')+':0000'
               if i<5 or (i==7 and open_now) else d.strftime('%Y%m%d')+':CLOSED')
        days.append(hours)
    return ';'.join(days)


def response(window, *, missing=False, conflict=False, duplicate=False, future=False, reverse=False):
    times=[]; at=window.start
    while at<window.end:
        if at.weekday()<5: times.append(at)
        at+=timedelta(minutes=window.minutes)
    if missing and times: times.pop(len(times)//2)
    if future: times=[window.end]
    if duplicate and times: times.insert(1,times[0])
    if reverse: times.reverse()
    values=[]
    for i,t in enumerate(times):
        values += [str(int(t.timestamp())),'1.1','1.2','1.0','1.16' if conflict and i==1 else '1.15','-1','-1',-1]
    return frame(17,window.request_id,'start','end',len(times),*values)[4:]


def stream(s, *, open_now=False, unknown=False, mutate=None):
    preflight=packets(hours=calendar(open_now,unknown))[:3]
    return preflight+tuple(response(w,**(mutate(w) if mutate else {})) for w in plan(s))


def run(directory, s=None, *, clock=None, payloads=None, **reader_kw):
    s=s or replace(spec(),end=START+timedelta(days=1),timeframes=(15,));clock=clock or Clock()
    with HistoricalStore(Path(directory),s,'session-1',Origin.FIXTURE,SessionKind.PAPER,create=not (Path(directory)/'identity.json').exists()) as store:
        r=FixtureHistoricalReader(payloads or stream(s),s,permit(s,clock),store,
            now=clock.now,mono=clock.mono,wait=clock.wait,**reader_kw)
        result=collect(r,store)
        return result,r,clock


class BackfillTests(unittest.TestCase):
    def test_contracts_closed_disabled_and_observation_unchanged(self):
        s=spec(); self.assertEqual(s,BackfillSpec.from_json(s.to_json()))
        self.assertFalse(replace(s,enabled=False).enabled)
        with self.assertRaises(ContractError): BackfillSpec.from_json(s.to_json()[:-1]+',"extra":1}')
        for change in ({'timeframes':(5,)},{'timeframes':(15,15)},{'max_bytes':999999999},{'end':END+timedelta(days=1)}):
            with self.assertRaises(ContractError): replace(s,**change)

    def test_week_plan_is_ten_bounded_requests(self):
        windows=plan(spec());self.assertEqual(10,len(windows))
        self.assertEqual([7,2,1],[sum(w.minutes==m for w in windows) for m in (15,60,240)])
        self.assertEqual(10,len({w.request_id for w in windows}))

    def test_wire_literal_midpoint_only(self):
        w=plan(spec())[0];f=request(w,12087792)[4:].decode().split('\0')
        self.assertEqual('20',f[0]);self.assertEqual('1 D',f[17]);self.assertEqual('MIDPOINT',f[19])
        self.assertEqual(frame(25,1,w.request_id),cancel(w.request_id))
        for bad in (True,3,'placeOrder',None):
            with self.assertRaises(ContractError): cancel(bad)

    def test_request_limit_rejects_unfinishable_spec(self):
        s=spec();s=replace(s,collector=replace(s.collector,capture=replace(s.collector.capture,max_requests=13)))
        with self.assertRaises(ContractError): plan(s)

    def test_frame_bounds(self):
        for p in (b'17\0',b'x'*16385,frame(17,3000,'a','b',129)[4:]):
            with self.assertRaises(ContractError): history_fields(p)

    def test_week_closed_complete_paged_and_no_quote_request(self):
        with tempfile.TemporaryDirectory() as d:
            result,r,clock=run(d,spec())
            self.assertEqual('HISTORICAL_COMPLETE',result.status)
            self.assertEqual('MARKET_CLOSED',result.market_state)
            self.assertEqual([480,120,30],[sum(p.count for p in result.pages if p.minutes==m) for m in (15,60,240)])
            self.assertGreater(len(result.pages),3)
            self.assertTrue(set(r.sent_opcodes)<={71,17,49,9,20,25})
            self.assertGreaterEqual(clock.ns,180*10**9)
            self.assertTrue(r.closed)
            self.assertFalse(result.execution_authorized)
            self.assertEqual('UNKNOWN',result.feed_type)

    def test_week_open_is_history_only(self):
        with tempfile.TemporaryDirectory() as d:
            result,r,_=run(d,spec(),payloads=stream(spec(),open_now=True))
            self.assertEqual('MARKET_OPEN',result.market_state)
            self.assertEqual('HISTORICAL_COMPLETE',result.status)
            self.assertNotIn(1,r.sent_opcodes);self.assertNotIn(59,r.sent_opcodes)

    def test_missing_bar_partial(self):
        with tempfile.TemporaryDirectory() as d:
            result,_,_=run(d,payloads=stream(spec(),mutate=lambda w:{'missing':w.request_id==3000}))
            self.assertEqual('HISTORICAL_PARTIAL',result.status)
            self.assertIn('HISTORY_GAP',result.quality)

    def test_unknown_calendar_never_complete(self):
        with tempfile.TemporaryDirectory() as d:
            result,_,_=run(d,payloads=stream(spec(),unknown=True))
            self.assertEqual('HISTORICAL_PARTIAL',result.status)
            self.assertIn('CALENDAR_UNKNOWN',result.quality)

    def test_exact_duplicate_is_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            result,_,_=run(d,payloads=stream(spec(),mutate=lambda w:{'duplicate':w.request_id==3000}))
            self.assertEqual(96,sum(p.count for p in result.pages if p.minutes==15))
            self.assertIn('HISTORY_DUPLICATE',result.quality)

    def test_conflicting_duplicate_excluded(self):
        with tempfile.TemporaryDirectory() as d:
            result,_,_=run(d,payloads=stream(spec(),mutate=lambda w:{'duplicate':w.request_id==3000,'conflict':w.request_id==3000}))
            self.assertEqual('HISTORICAL_REJECTED',result.status)
            self.assertIn('HISTORY_CONFLICT',result.quality)

    def test_out_of_order_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            result,_,_=run(d,payloads=stream(spec(),mutate=lambda w:{'reverse':w.request_id==3000}))
            self.assertEqual('HISTORICAL_REJECTED',result.status)

    def test_future_bar_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            result,_,_=run(d,payloads=stream(spec(),mutate=lambda w:{'future':w.request_id==3000}))
            self.assertEqual('HISTORICAL_REJECTED',result.status)

    def test_consumer_pages_and_explicit_insufficient(self):
        with tempfile.TemporaryDirectory() as d:
            s=replace(spec(),end=START+timedelta(days=2),timeframes=(15,))
            result,_,clock=run(d,s);c=HistoricalConsumer(Path(d),s,'session-1',Origin.FIXTURE,SessionKind.PAPER)
            first=c.read(15,START,s.end,as_of=clock.now(),minimum_bars=193)
            self.assertEqual(64,len(first.bars));self.assertFalse(first.sufficient)
            all_bars=list(first.bars);cursor=first.next_cursor
            while cursor:
                page=c.read(15,START,s.end,as_of=clock.now(),cursor=cursor,minimum_bars=193)
                all_bars.extend(page.bars);cursor=page.next_cursor
            self.assertEqual(192,len(all_bars));self.assertTrue(all(b.origin is Origin.FIXTURE for b in all_bars))
            self.assertEqual(192,len({b.bar.opened_at for b in all_bars}))

    def test_consumer_cutoff_blocks_late_received_friday(self):
        with tempfile.TemporaryDirectory() as d:
            s=replace(spec(),end=START+timedelta(days=1),timeframes=(15,))
            run(d,s);c=HistoricalConsumer(Path(d),s,'session-1',Origin.FIXTURE,SessionKind.PAPER)
            with self.assertRaises(ContractError): c.read(15,START,s.end,as_of=END-timedelta(seconds=1))

    def test_paper_live_and_spec_binding(self):
        s=replace(spec(),end=START+timedelta(days=1),timeframes=(15,))
        with tempfile.TemporaryDirectory() as d:
            run(d,s)
            with self.assertRaises(ContractError): HistoricalConsumer(Path(d),s,'session-1',Origin.FIXTURE,SessionKind.LIVE).read(15,START,s.end,as_of=END+timedelta(hours=1))
        with tempfile.TemporaryDirectory() as d, HistoricalStore(Path(d),s,'session-1',Origin.FIXTURE,SessionKind.LIVE,create=True) as store:
            c=Clock();r=FixtureHistoricalReader(stream(s),s,permit(s,c,session_kind=SessionKind.LIVE),store,
                now=c.now,mono=c.mono,wait=c.wait)
            result=collect(r,store)
            self.assertIs(result.environment,SessionKind.LIVE)
            self.assertIs(result.origin,Origin.FIXTURE)

    def test_permission_denial_before_socket(self):
        with tempfile.TemporaryDirectory() as d, HistoricalStore(Path(d),spec(),'session-1',Origin.FIXTURE,SessionKind.PAPER,create=True) as store:
            clock=Clock();auth=permit(spec(),clock);auth.signature='0'*64
            with patch('socket.socket',side_effect=AssertionError('NO_NETWORK')):
                r=HistoricalReader(spec(),auth,store,now=clock.now,mono=clock.mono)
                with self.assertRaises(ContractError): collect(r,store)

    def test_single_writer_exclusion(self):
        with tempfile.TemporaryDirectory() as d, HistoricalStore(Path(d),spec(),'session-1',Origin.FIXTURE,SessionKind.PAPER,create=True):
            with self.assertRaises(ContractError): HistoricalStore(Path(d),spec(),'session-1',Origin.FIXTURE,SessionKind.PAPER)

    def test_restart_skips_completed_windows(self):
        with tempfile.TemporaryDirectory() as d:
            result,_,clock=run(d);clock.wait(600)
            again,r,_=run(d,clock=clock,payloads=packets(hours=calendar())[:3])
            self.assertEqual('HISTORICAL_COMPLETE',again.status)
            self.assertNotIn(20,r.sent_opcodes)

    def test_publication_failure_releases_writer(self):
        with tempfile.TemporaryDirectory() as d:
            s=spec();clock=Clock();store=HistoricalStore(Path(d),s,'session-1',Origin.FIXTURE,SessionKind.PAPER,create=True)
            r=FixtureHistoricalReader(stream(s),s,permit(s,clock),store,now=clock.now,mono=clock.mono,wait=clock.wait)
            with patch.object(store,'publish',side_effect=OSError('fixture')):
                with self.assertRaises(OSError): collect(r,store)
            self.assertTrue(r.closed);self.assertIsNone(store.archive._lock)
            with HistoricalStore(Path(d),s,'session-1',Origin.FIXTURE,SessionKind.PAPER): pass


if __name__=='__main__': unittest.main()
