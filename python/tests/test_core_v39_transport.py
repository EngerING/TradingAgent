"""Socket lifecycle exercised with byte doubles only; no socket is constructed."""
from datetime import timedelta
import struct
import unittest
from unittest.mock import patch

from trading_agent.core_v3.contracts import content_hash
from trading_agent.core_v3.market_observation.ibkr_adapter import IBKRReader
from trading_agent.core_v3.market_observation.contracts import Kind
from test_core_v39_validation import AT, policy
from test_core_v39_protocol import approval, frame
from test_core_v39_collection import transcript


class ByteSocket:
    def __init__(self, payloads, *, complete=None):
        self.buffer=bytearray(frame(157,'fixture-server-time')+b''.join(struct.pack('!I',len(p))+p for p in payloads))
        self.sent=[]
        self.closed=False
        self.complete=complete

    def settimeout(self,value):
        assert value==2

    def connect(self,endpoint):
        assert endpoint==('127.0.0.1',4002)

    def sendall(self,data):
        self.sent.append(data)

    def recv(self,n):
        # Fragment even the length prefix; no undocumented full-frame assumption.
        n=min(n,3)
        value=bytes(self.buffer[:n]); del self.buffer[:n]
        if not self.buffer and self.complete:
            self.complete()
        return value

    def close(self):
        self.closed=True


class TransportTests(unittest.TestCase):
    def reader(self, rules, now=lambda:AT):
        permit=approval(enabled=True,policy_sha256=content_hash(rules.to_dict()))
        return IBKRReader(rules,permit,now=now)

    def test_fragmentation_preflight_and_safe_subscription_cleanup(self):
        sock=ByteSocket(transcript())
        with patch('trading_agent.core_v3.market_observation.ibkr_adapter.socket.socket',return_value=sock):
            events=tuple(self.reader(policy(max_reconnects=0)).events())
        self.assertTrue(any(e.kind is Kind.ASK for e in events))
        self.assertTrue(sock.closed)
        opcodes=[int(data[4:].split(b'\0',1)[0]) for data in sock.sent[1:]]
        self.assertEqual([71,17,49,9,59,1,2],opcodes)
        self.assertEqual(Kind.DISCONNECTED,events[-1].kind)

    def test_expiry_after_blocking_receive_keeps_late_frame_rejected(self):
        clock=[AT]
        sock=ByteSocket(transcript(),complete=lambda:clock.__setitem__(0,AT+timedelta(minutes=3)))
        with patch('trading_agent.core_v3.market_observation.ibkr_adapter.socket.socket',return_value=sock):
            events=tuple(self.reader(policy(max_reconnects=0),lambda:clock[0]).events())
        self.assertFalse(any(e.kind is Kind.ASK for e in events))
        late=next(e for e in events if e.diagnostic=='FRAME_AFTER_PERMISSION_OR_DEADLINE')
        self.assertGreater(late.raw_frame_size,0)
        self.assertIsNotNone(late.raw_frame_sha256)
        self.assertTrue(late.redacted)
        self.assertTrue(sock.closed)

    def test_consumer_interruption_cancels_only_market_subscription(self):
        sock=ByteSocket(transcript())
        reader=self.reader(policy(max_reconnects=0))
        with patch('trading_agent.core_v3.market_observation.ibkr_adapter.socket.socket',return_value=sock):
            iterator=reader.events()
            for event in iterator:
                if event.kind is Kind.BID:
                    break
            iterator.close()
        self.assertTrue(sock.closed)
        self.assertEqual(b'2',sock.sent[-1][4:].split(b'\0',1)[0])

    def test_reconnect_has_new_identity_and_repeats_full_preflight(self):
        first,second=ByteSocket(transcript()),ByteSocket(transcript())
        with patch('trading_agent.core_v3.market_observation.ibkr_adapter.socket.socket',side_effect=[first,second]):
            events=tuple(self.reader(policy(max_reconnects=1)).events())
        connections=[e for e in events if e.kind is Kind.CONNECTED]
        self.assertEqual(2,len(connections))
        self.assertNotEqual(connections[0].connection_id,connections[1].connection_id)
        self.assertTrue(all(e.sequence==1 for e in connections))
        self.assertTrue(first.closed and second.closed)

    def test_unverified_server_version_never_sends_market_request(self):
        sock=ByteSocket(())
        sock.buffer=bytearray(frame(180,'fixture-time'))
        from trading_agent.core_v3.contracts import ContractError
        with patch('trading_agent.core_v3.market_observation.ibkr_adapter.socket.socket',return_value=sock):
            with self.assertRaises(ContractError): tuple(self.reader(policy(max_reconnects=0)).events())
        self.assertEqual(1,len(sock.sent))
        self.assertTrue(sock.closed)
