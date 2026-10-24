"""Local, foreground M03-A.2 Paper HISTORY_ONLY permit issuer.

This module has no socket, broker client, order opcode, or automatic renewal.
Operator declarations are NOT proof of the actual TWS session: the historical
reader must independently compare the managed accounts received from TWS.
"""
import argparse
from datetime import datetime, timedelta, timezone
import getpass
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import sys

from trading_agent.core_v3.contracts import (
    ContractError, canonical_bytes, content_hash, instant, require, utc,
)
from trading_agent.core_v3.market_observation.authorization import (
    Approval, Grant, Scope, accounts_digest,
)
from trading_agent.core_v3.market_observation.contracts import (
    CapturePolicy, SessionKind,
)
from trading_agent.market_data.contracts import CollectorConfig
from .contracts import BackfillSpec, HistoricalApproval, HistoricalPermit
from .__main__ import Signatures


FILE_NAMES = (
    'spec.json', 'capture-grant.json', 'historical-permit.json',
    'signatures.json', 'verification.key',
)
PAPER_ACCOUNT_SUFFIX = '3784'
PERMIT_MINUTES = 30


def build_bundle(*, account, start, end, now, paper_confirmed,
                 market_data_confirmed, read_only_disabled_confirmed, key=None):
    """Construct two bound signatures in memory. No network or file writes."""
    require(type(paper_confirmed) is bool and paper_confirmed and
            type(market_data_confirmed) is bool and market_data_confirmed and
            type(read_only_disabled_confirmed) is bool and read_only_disabled_confirmed,
            'M032_HOST_CONFIRMATION_REQUIRED')
    # The prefix/suffix are a local guard for the owner's known Paper account,
    # not broker-authenticated proof that an API socket belongs to Paper.
    require(type(account) is str and account.isascii() and account.isalnum() and
            account.startswith('DU') and account.endswith(PAPER_ACCOUNT_SUFFIX) and
            6 <= len(account) <= 80, 'M032_EXPECTED_PAPER_ACCOUNT')
    now = utc(now)
    start, end = utc(start), utc(end)
    require(end <= now, 'M032_FUTURE_CUTOFF')
    require(key is None or (type(key) is bytes and len(key) >= 32),
            'M032_KEY_LENGTH')
    key = secrets.token_bytes(32) if key is None else key

    policy = CapturePolicy('paper-history-host-v1', max_duration_seconds=300)
    collector = CollectorConfig('paper-history-host-v1', policy, enabled=True)
    spec = BackfillSpec(collector, start, end, enabled=True)
    identifier = secrets.token_hex(12)
    attestation = content_hash({
        'source': 'LOCAL_OPERATOR_DECLARATION_NOT_TWS_PROOF',
        'account_binding_hmac': accounts_digest(account, key),
        'paper_confirmed': True,
        'market_data_confirmed': True,
        'tws_read_only_confirmed': False,
    })
    issued = now
    expires = now + timedelta(minutes=PERMIT_MINUTES)
    grant = Grant(
        approval_id='history-' + identifier,
        scope=Scope.CAPTURE,
        host='127.0.0.1',
        port=7497,
        client_id=19032,
        session_id='history-' + identifier,
        session_kind=SessionKind.PAPER,
        policy_sha256=content_hash(policy.to_dict()),
        accounts_hmac=accounts_digest(account, key),
        attestation_sha256=attestation,
        issued_at=issued,
        expires_at=expires,
        tws_read_only_confirmed=False,
        market_permission_confirmed=True,
    )
    permit = HistoricalPermit(
        capture_grant_sha256=content_hash(grant.to_dict()),
        spec_sha256=content_hash(spec.to_dict()),
        issued_at=issued,
        expires_at=expires,
    )
    sign = lambda record: hmac.new(
        key, canonical_bytes(record.to_dict()), hashlib.sha256
    ).hexdigest()
    signatures = Signatures(sign(grant), sign(permit))
    approval = HistoricalApproval(
        Approval(grant, signatures.capture_signature, key, enabled=True),
        permit, signatures.historical_signature, key,
    )
    approval.verify(spec, now)
    files = {
        'spec.json': spec.to_json().encode('utf-8'),
        'capture-grant.json': grant.to_json().encode('utf-8'),
        'historical-permit.json': permit.to_json().encode('utf-8'),
        'signatures.json': signatures.to_json().encode('utf-8'),
        'verification.key': key,
    }
    require(set(files) == set(FILE_NAMES) and
            all(len(data) <= (128 if name == 'verification.key' else 4096)
                for name, data in files.items()), 'M032_LOCAL_FILE')
    return files


def write_new_bundle(directory, files):
    """Only writes to an already secured, empty directory outside this repo."""
    require(type(files) is dict and set(files) == set(FILE_NAMES) and
            all(type(data) is bytes for data in files.values()), 'M032_BUNDLE')
    root = Path(directory)
    require(root.is_dir() and not root.is_symlink(), 'M032_LOCAL_DIRECTORY')
    root = root.resolve(strict=True)
    repo = Path(__file__).resolve().parents[4]
    require(root != repo and repo not in root.parents and
            not tuple(root.iterdir()), 'M032_LOCAL_DIRECTORY')
    for name in FILE_NAMES:
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, 'O_BINARY', 0)
        fd = os.open(str(root / name), flags, 0o600)
        with os.fdopen(fd, 'wb') as out:
            out.write(files[name])
            out.flush()
            os.fsync(out.fileno())


def main(argv=None):
    parser = argparse.ArgumentParser(description='Local Paper historical DATA_ONLY issuer')
    parser.add_argument('--start-utc', required=True)
    parser.add_argument('--end-utc', required=True)
    parser.add_argument('--approval-directory', required=True)
    parser.add_argument('--confirm-paper', action='store_true')
    parser.add_argument('--confirm-market-data', action='store_true')
    parser.add_argument('--confirm-read-only-disabled', action='store_true')
    args = parser.parse_args(argv)
    try:
        require(sys.platform == 'win32', 'M032_WINDOWS_REQUIRED')
        require(args.confirm_paper and args.confirm_market_data and
                args.confirm_read_only_disabled, 'M032_HOST_CONFIRMATION_REQUIRED')
        account = getpass.getpass('Cuenta completa de TWS Paper (no se mostrara): ')
        bundle = build_bundle(
            account=account,
            start=instant(args.start_utc), end=instant(args.end_utc),
            now=datetime.now(timezone.utc),
            paper_confirmed=True, market_data_confirmed=True,
            read_only_disabled_confirmed=True,
        )
        write_new_bundle(args.approval_directory, bundle)
        print(json.dumps({
            'status': 'HISTORICAL_PAPER_PERMIT_PREPARED',
            'mode': 'DATA_ONLY',
            'expires_in_minutes': PERMIT_MINUTES,
            'executionAuthorized': False,
            'socketConnected': False,
            'decision': 'NO_TRADE',
        }))
        return 0
    except (ContractError, OSError, ValueError, EOFError):
        print(json.dumps({
            'status': 'HOST_PREPARATION_REJECTED',
            'decision': 'NO_TRADE',
            'executionAuthorized': False,
            'socketConnected': False,
        }))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
