"""M03-A.4 offline only: no sockets, no broker secrets, no financial execution."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Event
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from trading_agent.core_v3.contracts import ContractError
from trading_agent.market_data.host_identity import fingerprint
from trading_agent.market_data.host_history import (
    offhours_window, paper_history_approval, run_offhours_history,
)
from trading_agent.market_data.host_service import _health_snapshot, _monitor_supervisor
from trading_agent.market_data.supervisor import Health


AT = datetime(2026, 10, 24, 9, 21, tzinfo=timezone.utc)
ACCOUNT = 'DU12343784'  # synthetic, not an IBKR account


def paper():
    return {'kind':'PAPER','account':ACCOUNT,'host':'127.0.0.1','port':7497,
            'client_id':19033,'market_data_confirmed':True,
            'read_only_disabled_confirmed':True,'enabled':True,
            'consent_at':AT.isoformat()}


class Vault:
    def __init__(self, profile):
        self.profile = profile
        self.enabled = True

    def is_current(self, kind, digest):
        return self.enabled and kind == 'PAPER' and digest == fingerprint(self.profile)


class HistoryTests(unittest.TestCase):
    def test_explicit_bounded_week_and_causal_utc_quarter(self):
        start, end = offhours_window(AT)
        self.assertEqual(datetime(2026,10,18,tzinfo=timezone.utc),start)
        self.assertEqual(datetime(2026,10,24,9,15,tzinfo=timezone.utc),end)
        self.assertLess(end,AT)
        self.assertLess(end-start,timedelta(days=7))

    def test_real_m03a2_signed_permit_without_stored_signing_key(self):
        spec,approval=paper_history_approval(paper(),now=AT,revocation_check=lambda:True)
        approval.verify(spec,AT)
        self.assertFalse(approval.capture.grant.tws_read_only_confirmed)
        self.assertEqual('PAPER',approval.capture.grant.session_kind.value)
        self.assertEqual(19032,approval.capture.grant.client_id)
        self.assertEqual(7497,approval.capture.grant.port)
        self.assertFalse(hasattr(approval,'placeOrder'))

    def test_revoke_active_historical_approval(self):
        enabled = {'value':True}
        spec,approval=paper_history_approval(paper(),now=AT,
                            revocation_check=lambda:enabled['value'])
        approval.verify(spec,AT)
        enabled['value']=False
        with self.assertRaisesRegex(ContractError,'M034_HISTORY_REVOKED'):
            approval.verify(spec,AT)

    def test_live_and_invalid_paper_profile_rejected_before_socket(self):
        for value in (dict(paper(),kind='LIVE',account='U1234567'),
                      dict(paper(),port=7496),dict(paper(),enabled=False)):
            with self.subTest(profile=value), patch('socket.socket',side_effect=AssertionError('NO_NETWORK')):
                with self.assertRaises(ContractError):
                    paper_history_approval(value,now=AT,revocation_check=lambda:True)

    def test_missing_broker_calendar_and_cancellation_fail_closed(self):
        stop=Event()
        with patch('socket.socket',side_effect=AssertionError('NO_NETWORK')):
            with self.assertRaises(ContractError):
                run_offhours_history(paper(),Vault(paper()),stop,now=AT,
                                     market_closed_confirmed=False)
            stop.set()
            with self.assertRaises(ContractError):
                run_offhours_history(paper(),Vault(paper()),stop,now=AT,
                                     market_closed_confirmed=True)

    def test_invalid_vault_revision_fails_before_directory_creation(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault=Vault(paper());vault.enabled=False
            location=Path(tmp)/'history'
            with self.assertRaises(ContractError):
                run_offhours_history(paper(),vault,Event(),now=AT,root=location,
                                     market_closed_confirmed=True)
            self.assertFalse(location.exists())

    def test_one_attempt_per_day_even_after_partial_and_restart(self):
        class Store:
            def __enter__(self): return self
            def __exit__(self,*exc): pass
        with tempfile.TemporaryDirectory() as tmp:
            vault=Vault(paper())
            root=Path(tmp)/'history'
            response=SimpleNamespace(status='HISTORICAL_PARTIAL',
                       pages=(SimpleNamespace(count=23),),
                       market_state='MARKET_CLOSED',quality=('CALENDAR_UNKNOWN',))
            with patch('trading_agent.market_data.host_history.HistoricalStore',return_value=Store()), \
                 patch('trading_agent.market_data.host_history.HistoricalReader',return_value=object()), \
                 patch('trading_agent.market_data.host_history.collect',return_value=response), \
                 patch('socket.socket',side_effect=AssertionError('NO_NETWORK')):
                first=run_offhours_history(paper(),vault,Event(),now=AT,
                        root=root,market_closed_confirmed=True)
                again=run_offhours_history(paper(),vault,Event(),now=AT,
                        root=root,market_closed_confirmed=True)
            self.assertEqual('HISTORICAL_PARTIAL',first['code'])
            self.assertEqual(23,first['bars'])
            self.assertEqual('HISTORICAL_ALREADY_ATTEMPTED_TODAY',again['code'])
            self.assertEqual(['20261024'],[p.name for p in root.iterdir()])

    def test_historical_stop_callback_is_callable_and_tracks_cancellation(self):
        class Store:
            def __enter__(self): return self
            def __exit__(self, *exc): pass

        class Reader:
            def __init__(self, spec, approval, storage, *, stop, wait):
                self.stop, self.wait = stop, wait

        cancellation = Event()
        def exercise_reader(reader, storage):
            # Reproduce HistoricalReader.events(): it invokes self.stop().
            self.assertFalse(reader.stop())
            self.assertFalse(reader.wait(0))
            cancellation.set()
            self.assertTrue(reader.stop())
            return SimpleNamespace(status='HISTORICAL_PARTIAL', pages=(),
                                   market_state='MARKET_CLOSED', quality=())

        with tempfile.TemporaryDirectory() as tmp, \
             patch('trading_agent.market_data.host_history.HistoricalStore', return_value=Store()), \
             patch('trading_agent.market_data.host_history.HistoricalReader', Reader), \
             patch('trading_agent.market_data.host_history.collect', side_effect=exercise_reader), \
             patch('socket.socket', side_effect=AssertionError('NO_NETWORK')):
            result = run_offhours_history(paper(), Vault(paper()), cancellation, now=AT,
                root=Path(tmp)/'history', market_closed_confirmed=True)
        self.assertEqual('HISTORICAL_PARTIAL', result['code'])

    def test_health_status_redacts_identity_and_price(self):
        health=SimpleNamespace(code='MARKET_CLOSED',committed=23,segments=3)
        observed=SimpleNamespace(quote=None,quality=('QUOTE_UNAVAILABLE',),as_of=AT)
        snapshot=_health_snapshot(health,observed,'PAPER')
        self.assertEqual(23,snapshot['committedEvents'])
        self.assertFalse(snapshot['quoteAvailable'])
        self.assertNotIn(ACCOUNT,str(snapshot))
        self.assertNotIn('bid',str(snapshot).lower())

    def test_monitor_only_recognizes_broker_closed_health(self):
        health=SimpleNamespace(code='MARKET_CLOSED',committed=23,segments=3)
        supervisor=SimpleNamespace(health=health,latest=None)
        done,closed=Event(),Event()
        with patch('trading_agent.market_data.host_service.output') as out:
            with patch.object(done,'wait',side_effect=lambda n: True):
                _monitor_supervisor(supervisor,'PAPER',done,closed)
        self.assertTrue(closed.is_set())
        self.assertEqual('CAPTURE_HEALTH',out.call_args.args[0])

    def test_sequential_watch_history_releases_archive_before_backfill(self):
        from trading_agent.market_data.host_service import _profile_loop
        stop=Event();active={'writer':False,'history':0}
        class Archive:
            def __init__(self,*args,**kwargs): pass
            def __enter__(self):
                active['writer']=True
                return self
            def __exit__(self,*args): active['writer']=False
        class Supervisor:
            def __init__(self,*args,**kwargs):
                self.health=Health('MARKET_CLOSED',23,3)
                self.latest=None
            def run(self):
                Event().wait(.05) # allow the observation-only status thread to report closed
                return Health('RUN_DEADLINE',23,3)
        def fake_history(*args,**kwargs):
            self.assertFalse(active['writer'],'BACKFILL_DURING_ACTIVE_WRITER')
            self.assertTrue(kwargs['market_closed_confirmed'])
            active['history']+=1
            stop.set()
            return {'code':'HISTORICAL_PARTIAL','bars':0}
        with tempfile.TemporaryDirectory() as tmp:
            grants=SimpleNamespace(capture=SimpleNamespace(grant=SimpleNamespace(session_id='test')))
            with patch('trading_agent.market_data.host_service.issue_data_lease',return_value=(object(),grants)), \
                 patch('trading_agent.market_data.host_service._listener_reachable',return_value=True), \
                 patch('trading_agent.market_data.host_service.Archive',Archive), \
                 patch('trading_agent.market_data.host_service.Supervisor',Supervisor), \
                 patch('trading_agent.market_data.host_service.run_offhours_history',side_effect=fake_history), \
                 patch('trading_agent.market_data.host_service.output'):
                _profile_loop(SimpleNamespace(load=lambda:{'PAPER':paper()}),
                              'PAPER',Path(tmp),stop,{})
        self.assertEqual(1,active['history'])
        self.assertFalse(active['writer'])

    def test_fatal_capture_never_promotes_history(self):
        from trading_agent.market_data.host_service import _profile_loop
        stop=Event()
        class Archive:
            def __init__(self,*args,**kwargs): pass
            def __enter__(self): return self
            def __exit__(self,*args): pass
        class Supervisor:
            def __init__(self,*args,**kwargs):
                self.health=Health('NOT_STARTED',0,0)
                self.latest=None
            def run(self): return Health('IDENTITY_OR_PERMISSION_REJECTED',1,1)
        with tempfile.TemporaryDirectory() as tmp:
            grants=SimpleNamespace(capture=SimpleNamespace(grant=SimpleNamespace(session_id='test')))
            with patch('trading_agent.market_data.host_service.issue_data_lease',return_value=(object(),grants)), \
                 patch('trading_agent.market_data.host_service._listener_reachable',return_value=True), \
                 patch('trading_agent.market_data.host_service.Archive',Archive), \
                 patch('trading_agent.market_data.host_service.Supervisor',Supervisor), \
                 patch('trading_agent.market_data.host_service.run_offhours_history') as history, \
                 patch('trading_agent.market_data.host_service.output'):
                _profile_loop(SimpleNamespace(load=lambda:{'PAPER':paper()}),
                              'PAPER',Path(tmp),stop,{})
                history.assert_not_called()


if __name__=='__main__': unittest.main()
