"""M03-A.5: synthetic broker transcripts only, no real TWS or execution."""
from datetime import datetime, timezone
from pathlib import Path
from threading import Event
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from trading_agent.core_v3.market_observation.contracts import Origin, Kind
from trading_agent.market_data.host_calendar import CalendarProbe, probe_broker_calendar
from trading_agent.market_data.host_service import _profile_loop
from trading_agent.market_data.reader import TranscriptReader
from trading_agent.market_data.supervisor import Health
from trading_agent.market_data.research_seed import verified_shadow_research_seed
from trading_agent.core_v3.contracts import ContractError
from test_m03a_reader import packets, config, permission
from test_m03a_contracts import AT
from test_m03a4_offhours_health import paper, Vault
from test_m03a2_backfill import run, spec, stream, response
from trading_agent.market_data.backfill.wire import plan


class CalendarOnlyTests(unittest.TestCase):
    def _probe(self, hours):
        cfg = config(enabled=True)
        reader = TranscriptReader(packets(hours=hours), cfg, permission(cfg),
                                  calendar_only=True, now=lambda:AT, mono=lambda:0)
        events = tuple(reader.events())
        self.assertTrue(reader.closed)
        self.assertTrue(set(reader.sent_opcodes) <= {71,17,49,9})
        self.assertNotIn(20,reader.sent_opcodes)
        self.assertNotIn(1,reader.sent_opcodes)
        self.assertNotIn(59,reader.sent_opcodes)
        self.assertFalse(any(e.kind in (Kind.BID, Kind.ASK) for e in events))
        return reader

    def test_broker_closed_requires_full_preflight(self):
        reader=self._probe('20261023:CLOSED')
        self.assertEqual('MARKET_CLOSED',reader.reason)

    def test_broker_open_calendar_only_never_subscribes(self):
        reader=self._probe('20261023:0000-20261024:0000')
        self.assertEqual('MARKET_OPEN',reader.reason)

    def test_unknown_is_neither_open_nor_closed(self):
        reader=self._probe('20261024:CLOSED')
        self.assertEqual('MARKET_UNKNOWN',reader.reason)

    def test_fixture_can_never_certify_broker_closed(self):
        cfg=config(enabled=True)
        class ClosedTranscript(TranscriptReader):
            def __init__(self,cfg,permit,**kwargs):
                super().__init__(packets(hours='20261023:CLOSED'),cfg,permit,
                                 mono=lambda:0,**kwargs)
        # A fixture is useful for checking the wire restrictions; its origin is
        # never an acceptable authority for a real off-hours historical run.
        with patch('trading_agent.market_data.host_calendar.TranscriptReader',ClosedTranscript):
            result=probe_broker_calendar(cfg,permission(cfg),Event(),
                                        reader_factory=ClosedTranscript,now=lambda:AT)
        self.assertEqual('CLOSED',result.state)
        self.assertEqual(Origin.FIXTURE.value,result.origin)
        self.assertFalse(result.broker_closed)


class OffHoursRecheckTests(unittest.TestCase):
    def _run(self, probe, stop, **extra):
        grants=SimpleNamespace(capture=SimpleNamespace(grant=SimpleNamespace(session_id='test')))
        with tempfile.TemporaryDirectory() as tmp, \
             patch('trading_agent.market_data.host_service.issue_data_lease',
                   return_value=(object(),grants)), \
             patch('trading_agent.market_data.host_service._listener_reachable',return_value=True), \
             patch('trading_agent.market_data.host_service.probe_broker_calendar',
                   return_value=probe), \
             patch('trading_agent.market_data.host_service.output') as output, \
             patch('trading_agent.market_data.host_service.Archive') as archive, \
             patch('trading_agent.market_data.host_service.run_offhours_history',
                   side_effect=extra.get('history')) as history:
            _profile_loop(SimpleNamespace(load=lambda:{'PAPER':paper()}),
                          'PAPER',Path(tmp),stop,{})
            return output.call_args_list, archive.call_count, history.call_args_list

    def test_closed_at_start_runs_history_without_capture_or_quotes(self):
        stop=Event()
        def capture(*args,**kwargs):
            self.assertTrue(kwargs['market_closed_confirmed'])
            stop.set()
            return {'code':'HISTORICAL_PARTIAL','bars':0}
        output,archives,histories=self._run(CalendarProbe('CLOSED',Origin.SOCKET.value),
                                            stop,history=capture)
        self.assertEqual(0,archives)
        self.assertEqual(1,len(histories))
        self.assertTrue(any(x.args[0]=='CALENDAR_STATUS' for x in output))

    def test_unknown_does_not_consume_daily_history_or_open_archive(self):
        stop=Event()
        def cancel_wait(_): stop.set();return True
        with patch.object(stop,'wait',side_effect=cancel_wait):
            _,archives,histories=self._run(CalendarProbe('UNKNOWN',Origin.SOCKET.value),stop)
        self.assertEqual(0,archives)
        self.assertFalse(histories)

    def test_untrusted_closed_fixture_does_not_collect(self):
        stop=Event()
        def cancel_wait(_): stop.set();return True
        with patch.object(stop,'wait',side_effect=cancel_wait):
            _,archives,histories=self._run(CalendarProbe('CLOSED',Origin.FIXTURE.value),stop)
        self.assertEqual(0,archives)
        self.assertFalse(histories)

    def test_open_calendar_retains_continuous_live_capture_path(self):
        stop=Event()
        class Archive:
            def __init__(self,*a,**kw):pass
            def __enter__(self):return self
            def __exit__(self,*a):pass
        class Supervisor:
            def __init__(self,*a,**kw):
                self.health=Health('CAPTURING',1,1);self.latest=None
            def run(self):stop.set();return Health('STOPPED',1,1)
        with patch('trading_agent.market_data.host_service.Archive',Archive), \
             patch('trading_agent.market_data.host_service.Supervisor',Supervisor):
            _,_,histories=self._run(CalendarProbe('OPEN',Origin.SOCKET.value),stop)
        self.assertEqual([],histories)


class HistoricalSafetyTests(unittest.TestCase):
    def test_offhours_history_rechecks_calendar_before_first_query(self):
        with tempfile.TemporaryDirectory() as tmp:
            result,reader,_=run(tmp,spec(),payloads=stream(spec(),open_now=True),
                                require_market_closed=True)
        self.assertEqual('HISTORICAL_UNAVAILABLE',result.status)
        self.assertIn('BACKFILL_BROKER_CLOSED_REQUIRED',result.quality)
        self.assertNotIn(20,reader.sent_opcodes)
        self.assertNotIn(1,reader.sent_opcodes)

    def test_unknown_calendar_never_dispatches_historical_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            unknown=packets(hours='20261025:CLOSED')[:3]
            payloads=unknown+tuple(response(w) for w in plan(spec()))
            result,reader,_=run(tmp,spec(),payloads=payloads,
                                require_market_closed=True)
        self.assertNotIn(20,reader.sent_opcodes)
        self.assertNotEqual('HISTORICAL_COMPLETE',result.status)


class KronosReuseTests(unittest.TestCase):
    def test_read_only_source_contract_does_not_promote_into_live_feed(self):
        verified={'timeframe':'1H','as_of':'2026-10-20T12:00:00+00:00',
                  'bars':[{'opened_at':'2026-10-20T11:00:00+00:00',
                           'open':'1.1','high':'1.2','low':'1.0','close':'1.1'}],
                  'source':{'quality':'AUTHENTIC','provider':'IBKR_PAPER_MIDPOINT',
                            'sha256':'a'*64,'event_hash':'b'*64}}
        with patch('trading_agent.kronos.persistence.source_request',return_value=verified) as reader:
            seed=verified_shadow_research_seed('/unused',object(),{'timeframe':'1H'})
        reader.assert_called_once()
        self.assertFalse(seed.execution_authorized)
        self.assertEqual('RESEARCH_ONLY_NOT_MARKET_FEED',seed.destination)
        self.assertEqual(1,len(seed.bars))

    def test_shadow_source_cannot_be_relabelled_live_or_unverified(self):
        for source in ({'quality':'AUTHENTIC','provider':'SYNTHETIC',
                        'sha256':'a'*64,'event_hash':'b'*64},
                       {'quality':'UNVERIFIED','provider':'IBKR_PAPER_MIDPOINT',
                        'sha256':'a'*64,'event_hash':'b'*64},
                       {'quality':'AUTHENTIC','provider':'IBKR_PAPER_MIDPOINT',
                        'sha256':'X'*64,'event_hash':'b'*64}):
            raw={'timeframe':'1H','as_of':'2026-10-20T12:00:00+00:00',
                 'bars':[],'source':source}
            with self.subTest(source=source), \
                 patch('trading_agent.kronos.persistence.source_request',return_value=raw):
                with self.assertRaises(ContractError):
                    verified_shadow_research_seed('/unused',object(),{'timeframe':'1H'})


if __name__=='__main__': unittest.main()
