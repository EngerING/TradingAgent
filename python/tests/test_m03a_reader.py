"""Connection doubles always identify their events as synthetic fixtures."""
from dataclasses import replace
from datetime import timedelta
import hashlib
import hmac
import unittest
from unittest.mock import patch

from trading_agent.core_v3.contracts import ContractError, canonical_bytes, content_hash
from trading_agent.core_v3.market_observation.contracts import Origin, Kind, SessionKind
from trading_agent.market_data.authorization import DataPermit, DataApproval
from trading_agent.market_data.contracts import CollectorConfig
from trading_agent.market_data.reader import MarketReader, TranscriptReader
from test_m03a_contracts import AT
from test_core_v39_validation import policy
from test_core_v39_protocol import approval, KEY, frame
from test_core_v39_collection import details
from test_m03a_wire import batch


def config(**changes):
    return CollectorConfig('m03a-fixture', policy(max_reconnects=0, max_duration_seconds=120), **changes)


def permission(cfg=None, kind=SessionKind.PAPER, **changes):
    cfg = cfg or config(enabled=True)
    cap = approval(enabled=True, session_kind=kind, policy_sha256=content_hash(cfg.capture.to_dict()),
                   issued_at=AT-timedelta(seconds=1), expires_at=AT+timedelta(minutes=2), **changes)
    permit = DataPermit(content_hash(cap.grant.to_dict()), content_hash(cfg.to_dict()),
                        AT-timedelta(seconds=1), AT+timedelta(minutes=2))
    signature = hmac.new(KEY, canonical_bytes(permit.to_dict()), hashlib.sha256).hexdigest()
    return DataApproval(cap, permit, signature, KEY)


def packets(accounts='DU123', hours='20261023:0000-20261024:0000', feed=1):
    f = details()[:-1].decode().split('\0')
    f[27], f[28] = 'UTC', hours
    return (frame(15,1,accounts)[4:], ('\0'.join(f)+'\0').encode(), frame(52,1,100)[4:],
            frame(58,1,101,feed)[4:], frame(1,6,101,66 if feed==3 else 1,'1.1000',0,0)[4:],
            frame(1,6,101,67 if feed==3 else 2,'1.1002',0,0)[4:])


class ReaderTests(unittest.TestCase):
    def reader(self, payloads=None, cfg=None, auth=None):
        cfg = cfg or config(enabled=True)
        return TranscriptReader(payloads or packets(), cfg, auth or permission(cfg), now=lambda:AT)

    def test_paper_and_live_read_only_with_full_identity(self):
        for kind in SessionKind:
            r = self.reader(auth=permission(kind=kind))
            events = tuple(r.events())
            self.assertTrue(any(e.kind is Kind.ASK for e in events))
            self.assertTrue(all(e.origin is Origin.FIXTURE and e.session_kind is kind for e in events))
            self.assertNotIn('DU123', repr(events))
            self.assertTrue(r.closed)
            self.assertTrue(set(r.sent_opcodes) <= {71,17,49,9,59,1,2,20,25})

    def test_unknown_account_and_changed_session_block(self):
        for payloads in (packets(accounts='U999'), packets()+(frame(15,1,'U999')[4:],)):
            events = tuple(self.reader(payloads).events())
            self.assertTrue(any(e.kind is Kind.GAP for e in events))
            self.assertNotIn('U999', repr(events))
        r = self.reader(packets(accounts='U999'))
        tuple(r.events())
        self.assertNotIn(1, r.sent_opcodes)

    def test_offline_invalid_signature_readonly_unknown_and_binding_fail_before_socket(self):
        cfg = config()
        permits = [permission(cfg), permission(tws_read_only_confirmed=False), permission()]
        permits[-1].signature = '0'*64
        with patch('socket.socket', side_effect=AssertionError('no socket')):
            for permit in permits:
                with self.assertRaises(ContractError): tuple(MarketReader(cfg, permit, now=lambda:AT).events())

    def test_closed_market_does_not_request_quotes_or_history(self):
        r = self.reader(packets(hours='20261023:CLOSED'))
        events = tuple(r.events())
        self.assertTrue(any(e.diagnostic == 'MARKET_CLOSED' for e in events))
        self.assertNotIn(1, r.sent_opcodes)
        self.assertNotIn(20, r.sent_opcodes)

    def test_grant_expiry_revocation_and_config_tampering(self):
        p = permission()
        p.verify(config(enabled=True), AT)
        for cfg, at in ((config(enabled=True), AT+timedelta(minutes=3)), (config(), AT)):
            with self.assertRaises(ContractError): p.verify(cfg, at)
        p.capture.revoke()
        with self.assertRaises(ContractError): p.verify(config(enabled=True), AT)

    def test_live_delayed_frozen_confirmed_without_relabel(self):
        for feed in (1,2,3,4):
            values = tuple(self.reader(packets(feed=feed)).events())
            event = next(e for e in values if e.kind is Kind.DATA_TYPE)
            self.assertEqual({1:'LIVE',2:'FROZEN',3:'DELAYED',4:'DELAYED_FROZEN'}[feed], event.data_type.value)

    def test_consumer_close_cancels_own_subscription(self):
        r = self.reader()
        iterator = r.events()
        for event in iterator:
            if event.kind is Kind.BID: break
        iterator.close()
        self.assertTrue(r.closed)
        self.assertEqual(2, r.sent_opcodes[-1])

    def test_three_native_timeframes_are_paced_and_matched(self):
        cfg = config(enabled=True)
        clock = [AT]
        r = TranscriptReader(packets()+(batch(),batch(60),batch(240)),cfg,permission(cfg),
            now=lambda:clock[0],mono=lambda:int((clock[0]-AT).total_seconds()*10**9))
        receive = r.fixture.recv
        def paced(n):
            for req, offset in ((202,20),(203,40)):
                if r.fixture.data[4:].startswith(('17\0'+str(req)+'\0').encode()) and clock[0] < AT+timedelta(seconds=offset):
                    clock[0] = AT+timedelta(seconds=offset)
                    import socket
                    raise socket.timeout()
            return receive(n)
        r.fixture.recv = paced
        events = tuple(r.events())
        requests = [e for e in events if e.diagnostic == 'HISTORY_REQUEST_PLANNED']
        self.assertEqual([201,202,203],[e.wire_request_id for e in requests])
        self.assertEqual([0,20,40],[int((e.received_at-AT).total_seconds()) for e in requests])
        self.assertEqual([201,202,203],[e.wire_request_id for e in events if e.diagnostic == 'HISTORY_BATCH'])

    def test_expiry_inside_blocking_receive_rejects_and_closes(self):
        cfg = config(enabled=True)
        clock = [AT]
        r = TranscriptReader(packets(),cfg,permission(cfg),now=lambda:clock[0])
        receive = r.fixture.recv
        def late(n):
            data = receive(n)
            if not r.fixture.data: clock[0] = AT+timedelta(minutes=3)
            return data
        r.fixture.recv = late
        events = tuple(r.events())
        self.assertFalse(any(e.kind is Kind.ASK for e in events))
        self.assertTrue(any(e.kind is Kind.GAP and e.raw_frame_sha256 for e in events))
        self.assertTrue(r.closed)

    def test_unverified_server_and_disconnected_endpoint(self):
        r = self.reader()
        r.fixture.data = bytearray(frame(180,'fixture'))
        events = tuple(r.events())
        self.assertEqual('PROFILE_REJECTED',r.reason)
        self.assertEqual((),r.sent_opcodes)
        r = self.reader()
        with patch.object(r,'_open',side_effect=OSError('fixture')):
            events = tuple(r.events())
        self.assertEqual('DISCONNECTED',r.reason)
        self.assertTrue(r.closed)


if __name__ == '__main__': unittest.main()
