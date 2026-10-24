"""Offline adversarial M03-A.3 tests. No IBKR socket or financial execution."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from trading_agent.core_v3.contracts import ContractError
from trading_agent.core_v3.market_observation.contracts import SessionKind
from trading_agent.market_data.authorization import DataPermit, DataApproval, RW_HOST_SCOPE
from trading_agent.market_data.host_approval import issue_data_lease
from trading_agent.market_data.host_identity import HostVault, _dpapi, fingerprint

AT = datetime(2026,10,23,17,0,tzinfo=timezone.utc)
ACCOUNT_PAPER = 'DU12343784'
ACCOUNT_LIVE = 'U1234567'


def fake_vault(path):
    return HostVault(path,protect=lambda payload:b'cipher:'+payload[::-1],
                     unprotect=lambda ciphertext:ciphertext[len(b'cipher:'):][::-1])


def paper():
    return dict(kind='PAPER',account=ACCOUNT_PAPER,host='127.0.0.1',
                port=7497,client_id=19033,market_data_confirmed=True,
                read_only_disabled_confirmed=True,enabled=True,
                consent_at=AT.isoformat())


def live():
    return dict(paper(),kind='LIVE',account=ACCOUNT_LIVE,port=7496,client_id=19034)


class DurableIdentityTests(unittest.TestCase):
    def test_empty_vault_starts_with_no_authority(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault=fake_vault(Path(tmp)/'identities.dpapi')
            self.assertEqual({},vault.load())
            self.assertFalse(vault.path.exists())

    def test_enroll_two_exact_accounts_persist_encrypted(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault=fake_vault(Path(tmp)/'identities.dpapi')
            vault.save({'PAPER':paper(),'LIVE':live()})
            self.assertEqual(ACCOUNT_PAPER,vault.load()['PAPER']['account'])
            self.assertEqual(ACCOUNT_LIVE,vault.load()['LIVE']['account'])
            encrypted=vault.path.read_bytes()
            self.assertNotIn(ACCOUNT_PAPER.encode(),encrypted)
            self.assertNotIn(ACCOUNT_LIVE.encode(),encrypted)

    def test_revoke_persists_and_invalidates_current_lease(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault=fake_vault(Path(tmp)/'vault')
            vault.save({'PAPER':paper()})
            digest=fingerprint(vault.load()['PAPER'])
            config,approval=issue_data_lease(paper(),now=AT,
                     revocation_check=lambda:vault.is_current('PAPER',digest))
            approval.verify(config,AT)
            vault.revoke('PAPER')
            self.assertFalse(vault.is_current('PAPER',digest))
            with self.assertRaises(ContractError):approval.verify(config,AT)

    def test_profile_change_prevents_previous_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault=fake_vault(Path(tmp)/'vault')
            vault.save({'PAPER':paper()})
            digest=fingerprint(vault.load()['PAPER'])
            newer=dict(paper(),client_id=19044)
            vault.save({'PAPER':newer})
            self.assertFalse(vault.is_current('PAPER',digest))

    def test_reject_cross_environment_identity_and_collision(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault=fake_vault(Path(tmp)/'vault')
            with self.assertRaises(ContractError):vault.save({'LIVE':dict(live(),account=ACCOUNT_PAPER)})
            with self.assertRaises(ContractError):vault.save({'PAPER':dict(paper(),account=ACCOUNT_LIVE)})
            with self.assertRaises(ContractError):vault.save({'PAPER':paper(),'LIVE':dict(live(),port=7497)})

    def test_reject_invalid_files_and_undecipherable_vault(self):
        with tempfile.TemporaryDirectory() as tmp:
            file=Path(tmp)/'vault'
            vault=fake_vault(file)
            file.write_bytes(b'plaintext:DU12343784')
            with self.assertRaises(ContractError):vault.load()

    def test_unconfirmed_enrollment_and_duplicate_require_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault=fake_vault(Path(tmp)/'vault')
            with self.assertRaises(ContractError):
                vault.enroll('PAPER',ACCOUNT_PAPER,port=7497,client_id=19033,confirm=False)
            vault.enroll('PAPER',ACCOUNT_PAPER,port=7497,client_id=19033,confirm=True)
            with self.assertRaises(ContractError):
                vault.enroll('PAPER',ACCOUNT_PAPER,port=7497,client_id=19033,confirm=True)
            self.assertEqual(ACCOUNT_PAPER,vault.load()['PAPER']['account'])

    @unittest.skipUnless(sys.platform=='win32','Real DPAPI available on Windows CI')
    def test_windows_current_user_dpapi_round_trip(self):
        encrypted=_dpapi(b'confidential-data-not-a-broker-password')
        self.assertNotIn(b'confidential-data',encrypted)
        self.assertEqual(b'confidential-data-not-a-broker-password',
                         _dpapi(encrypted,decrypt=True))


class DataLeaseTests(unittest.TestCase):
    def test_paper_data_only_lease_without_orders(self):
        cfg,approval=issue_data_lease(paper(),now=AT)
        approval.verify(cfg,AT)
        self.assertFalse(approval.capture.grant.tws_read_only_confirmed)
        self.assertEqual(RW_HOST_SCOPE,approval.permit.scope)
        self.assertEqual(SessionKind.PAPER,approval.capture.grant.session_kind)
        self.assertLessEqual((approval.permit.expires_at-AT).total_seconds(),1800)
        self.assertEqual(900,cfg.max_run_seconds)
        self.assertEqual(16,cfg.capture.max_requests)

    def test_live_data_only_lease_with_exact_account_binding(self):
        cfg,approval=issue_data_lease(live(),now=AT)
        approval.verify(cfg,AT)
        self.assertEqual(SessionKind.LIVE,approval.capture.grant.session_kind)
        approval.capture.check_accounts(ACCOUNT_LIVE)
        with self.assertRaises(ContractError):
            approval.capture.check_accounts(ACCOUNT_PAPER)

    def test_expired_signed_lease_fails_closed(self):
        cfg,approval=issue_data_lease(paper(),now=AT)
        with self.assertRaises(ContractError):
            approval.verify(cfg,AT+timedelta(minutes=11))

    def test_original_scope_cannot_bypass_broker_read_only_guard(self):
        cfg,approval=issue_data_lease(paper(),now=AT)
        prior=DataPermit(approval.permit.capture_grant_sha256,
                         approval.permit.config_sha256,
                         AT,AT+timedelta(minutes=10))
        bogus=DataApproval(approval.capture,prior,approval.signature,approval._key)
        with self.assertRaises(ContractError):bogus.verify(cfg,AT)

    def test_tampered_capture_grant_rejected(self):
        cfg,approval=issue_data_lease(live(),now=AT)
        approval.capture.grant=replace(approval.capture.grant,port=7100)
        with self.assertRaises(ContractError):approval.verify(cfg,AT)

    def test_revocation_callback_stops_even_valid_signed_lease(self):
        cfg,approval=issue_data_lease(live(),now=AT,revocation_check=lambda:False)
        with self.assertRaises(ContractError):approval.verify(cfg,AT)

    def test_disabled_profile_cannot_issue_permit(self):
        with self.assertRaises(ContractError):
            issue_data_lease(dict(live(),enabled=False),now=AT)


if __name__=='__main__':unittest.main()
