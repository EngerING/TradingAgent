"""Offline adversarial tests for locally provisioned M03-A.2 Paper permits."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from trading_agent.core_v3.contracts import ContractError
from trading_agent.core_v3.market_observation.authorization import Approval, Grant, Scope
from trading_agent.core_v3.market_observation.contracts import SessionKind
from trading_agent.market_data.backfill.__main__ import Signatures
from trading_agent.market_data.backfill.contracts import (
    BackfillSpec, HistoricalApproval, HistoricalPermit,
)
from trading_agent.market_data.backfill.host_provisioner import (
    FILE_NAMES, build_bundle, write_new_bundle,
)


NOW = datetime(2026, 10, 24, 0, 0, tzinfo=timezone.utc)
START = datetime(2026, 10, 18, 0, 0, tzinfo=timezone.utc)
END = datetime(2026, 10, 23, 21, 0, tzinfo=timezone.utc)
ACCOUNT = 'DU00003784'  # Synthetic, never a real account.
KEY = b'k' * 32


def bundle(**changes):
    args = dict(
        account=ACCOUNT, start=START, end=END, now=NOW,
        paper_confirmed=True, market_data_confirmed=True,
        read_only_disabled_confirmed=True, key=KEY,
    )
    args.update(changes)
    return build_bundle(**args)


def approve(files):
    spec = BackfillSpec.from_json(files['spec.json'])
    grant = Grant.from_json(files['capture-grant.json'])
    permit = HistoricalPermit.from_json(files['historical-permit.json'])
    signatures = Signatures.from_json(files['signatures.json'])
    auth = HistoricalApproval(
        Approval(grant, signatures.capture_signature,
                 files['verification.key'], enabled=spec.enabled),
        permit, signatures.historical_signature,
        files['verification.key'],
    )
    return spec, grant, auth


class HostHistoryProvisionerTests(unittest.TestCase):
    def test_valid_paper_bundle_has_independent_signatures_and_restricted_scope(self):
        files = bundle()
        self.assertEqual(set(FILE_NAMES), set(files))
        spec, grant, auth = approve(files)
        self.assertIs(grant.session_kind, SessionKind.PAPER)
        self.assertFalse(grant.tws_read_only_confirmed)
        self.assertEqual((grant.host, grant.port, grant.client_id),
                         ('127.0.0.1', 7497, 19032))
        self.assertEqual((15, 60, 240), spec.timeframes)
        self.assertEqual(END, spec.end)
        auth.verify(spec, NOW)
        auth.capture.check_accounts(ACCOUNT)
        with self.assertRaises(ContractError):
            auth.capture.verify(
                Scope.CAPTURE, spec.collector.capture,
                grant.session_id, SessionKind.PAPER, NOW,
            )

    def test_no_secret_or_full_account_serialized(self):
        files = bundle()
        for name, raw in files.items():
            self.assertLessEqual(len(raw), 128 if name == 'verification.key' else 4096)
            self.assertNotIn(ACCOUNT.encode('ascii'), raw)
            if name != 'verification.key':
                self.assertNotIn(KEY, raw)
        self.assertEqual(KEY, files['verification.key'])

    def test_all_three_local_operator_confirmations_are_mandatory(self):
        for flag in ('paper_confirmed', 'market_data_confirmed',
                     'read_only_disabled_confirmed'):
            with self.subTest(flag=flag), self.assertRaises(ContractError):
                bundle(**{flag: False})
        with self.assertRaises(ContractError):
            bundle(paper_confirmed='true')

    def test_wrong_or_live_like_account_fails_closed(self):
        for account in ('U12343784', 'DU00009999', 'DU-any-3784', '', 'DU1234'):
            with self.subTest(account=account), self.assertRaises(ContractError):
                bundle(account=account)

    def test_future_invalid_or_out_of_scope_range_is_rejected(self):
        for start, end in (
            (START, NOW + timedelta(minutes=15)),
            (NOW - timedelta(minutes=30), NOW),
            (START - timedelta(days=2), END),
            (START.replace(hour=1), END),
        ):
            with self.subTest(start=start, end=end), self.assertRaises(ContractError):
                bundle(start=start, end=end)

    def test_expiration_and_signature_tampering_are_denied(self):
        files = bundle()
        spec, grant, auth = approve(files)
        auth.verify(spec, NOW + timedelta(minutes=29))
        with self.assertRaises(ContractError):
            auth.verify(spec, NOW + timedelta(minutes=30))
        altered = dict(files)
        sigs = Signatures.from_json(files['signatures.json'])
        poisoned = ('1' if sigs.historical_signature[0] == '0' else '0')
        altered['signatures.json'] = Signatures(
            sigs.capture_signature,
            poisoned + sigs.historical_signature[1:],
        ).to_json().encode('utf-8')
        _, _, changed = approve(altered)
        with self.assertRaises(ContractError):
            changed.verify(spec, NOW)

    def test_writes_only_to_new_empty_directory_with_no_socket(self):
        files = bundle()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'secured'
            root.mkdir()
            with patch('socket.socket', side_effect=AssertionError('NO_SOCKET')):
                write_new_bundle(root, files)
            self.assertEqual(set(FILE_NAMES), {p.name for p in root.iterdir()})
            self.assertEqual(KEY, (root / 'verification.key').read_bytes())
            with self.assertRaises(ContractError):
                write_new_bundle(root, files)

    def test_account_mismatch_revocation_and_live_relabel_fail(self):
        files = bundle()
        spec, grant, auth = approve(files)
        with self.assertRaises(ContractError):
            auth.capture.check_accounts('DU99993784')
        auth.capture.revoke()
        with self.assertRaises(ContractError):
            auth.verify(spec, NOW)
        self.assertIs(grant.session_kind, SessionKind.PAPER)


if __name__ == '__main__':
    unittest.main()
