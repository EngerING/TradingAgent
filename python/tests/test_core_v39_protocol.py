"""Independent wire vectors and external-host permission binding; no sockets."""
from datetime import timedelta
from dataclasses import replace
import hashlib
import hmac
import struct
import unittest

from trading_agent.core_v3.contracts import ContractError, canonical_bytes, content_hash
from trading_agent.core_v3.market_observation.authorization import Grant, Scope, Approval, accounts_digest
from trading_agent.core_v3.market_observation.ibkr_protocol import Command, encode, handshake, fields, decode
from trading_agent.core_v3.market_observation.contracts import DataType, Kind, SessionKind
from test_core_v39_validation import policy, AT

KEY = b'fixture-only-not-a-provisioned-authority-key'


def approval(scope=Scope.CAPTURE, *, enabled=False, **changes):
    grant = Grant('approval-1', scope, '127.0.0.1', 4002, 39, 'session-1', SessionKind.PAPER,
        content_hash(policy().to_dict()), accounts_digest('DU123', KEY), 'a'*64,
        AT-timedelta(seconds=1), AT+timedelta(minutes=2), True, True)
    grant = replace(grant, **changes)
    signature = hmac.new(KEY, canonical_bytes(grant.to_dict()), hashlib.sha256).hexdigest()
    return Approval(grant, signature, KEY, enabled=enabled)


def frame(*values):
    raw = ('\0'.join(str(v) for v in values)+'\0').encode('ascii')
    return struct.pack('!I', len(raw))+raw


class ProtocolTests(unittest.TestCase):
    def test_handshake_and_outgoing_vectors(self):
        self.assertEqual(b'API\0\0\0\0\x09v157..157', handshake())
        self.assertEqual(frame(71,2,39,''), encode(Command.START, client_id=39))
        self.assertEqual(frame(49,1), encode(Command.TIME))
        self.assertEqual(frame(17,1), encode(Command.ACCOUNTS))
        self.assertEqual(frame(59,1,1), encode(Command.DATA_TYPE))
        self.assertEqual(frame(2,2,101), encode(Command.CANCEL, request_id=101))
        self.assertEqual(frame(9,8,100,0,'EUR','CASH','', '0.0','','','IDEALPRO','','USD','','',0,'',''),
                         encode(Command.CONTRACT, request_id=100))
        self.assertEqual(frame(1,11,101,12087792,'EUR','CASH','','0.0','','','IDEALPRO','','USD','','',0,'',0,0,''),
                         encode(Command.SUBSCRIBE, request_id=101, con_id=12087792))

    def test_unknown_commands_and_malformed_frames_are_denied(self):
        for value in (3,4,'placeOrder','cancelOrder',True,None):
            with self.assertRaises(ContractError):
                encode(value)
        with self.assertRaises(ContractError):
            decode(b'1\0')
        for blob in (b'1\x00bad', b'\xff\0', b'1\0'*10000):
            with self.assertRaises(ContractError):
                fields(blob, 128)

    def test_decoder_preserves_decimal_text_and_confirmed_type(self):
        tick = decode(b'1\x006\x00101\x001\x001.10000\x000\x000\x00')
        self.assertEqual(('BID', '1.10000', 1), (tick.kind.value, tick.price_text, tick.tick_type))
        for code, expected in ((1,DataType.LIVE),(2,DataType.FROZEN),(3,DataType.DELAYED),(4,DataType.DELAYED_FROZEN)):
            decoded = decode(('58\0'+'1\0'+'101\0'+str(code)+'\0').encode())
            self.assertEqual(expected, decoded.data_type)

    def test_connection_health_errors_invalidate_and_sensitive_error_is_redacted(self):
        for code in (1100,1101,1102,1300,2103,2108,354,10167,10168,10186):
            raw = ('4\0'+'2\0'+'-1\0'+str(code)+'\0secret-account\0').encode()
            decoded = decode(raw)
            self.assertEqual(Kind.GAP, decoded.kind)
            self.assertTrue(decoded.redacted)
            self.assertNotIn('secret', repr(decoded))

    def test_authorization_default_disabled_expiry_revocation_and_separate_scope(self):
        for obj in (approval(), approval(enabled=True, session_kind=SessionKind.LIVE),
                    approval(enabled=True, policy_sha256='0'*64), approval(enabled=True, expires_at=AT)):
            with self.assertRaises(ContractError):
                obj.verify(Scope.CAPTURE, policy(), 'session-1', SessionKind.PAPER, AT)
        obj = approval(enabled=True)
        obj.verify(Scope.CAPTURE, policy(), 'session-1', SessionKind.PAPER, AT)
        with self.assertRaises(ContractError):
            obj.verify(Scope.SHADOW, policy(), 'session-1', SessionKind.PAPER, AT)
        obj.revoke()
        with self.assertRaises(ContractError):
            obj.verify(Scope.CAPTURE, policy(), 'session-1', SessionKind.PAPER, AT)

    def test_invalid_signature_and_identity_fail_without_raw_account_error(self):
        obj = approval(enabled=True)
        obj.signature = '0'*64
        with self.assertRaises(ContractError):
            obj.verify(Scope.CAPTURE, policy(), 'session-1', SessionKind.PAPER, AT)
        with self.assertRaises(ContractError) as error:
            approval(enabled=True).check_accounts('LIVE-PRIVATE')
        self.assertNotIn('PRIVATE', str(error.exception))
