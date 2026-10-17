"""Protected identity selection and execution mode; never an order authorization.

AccountBinding deliberately outlives a session grant. Its expiry/revocation,
emergency, risk and reconciliation gates remain in Authorization/PaperLab.
"""
from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import os
from pathlib import Path
import re
import time
import threading

from .paper_lab import unseal, stamp


class ExecutionMode(str, Enum):
    Research = 'Research'
    PaperAuto = 'PaperAuto'
    LiveApproval = 'LiveApproval'


@dataclass(frozen=True)
class SessionConfiguration:
    host: str = '127.0.0.1'
    port: int = 7497

    def __post_init__(self):
        # Local TWS process attestation cannot certify a remote endpoint.
        if self.host not in ('127.0.0.1', '::1') or type(self.port) is not int or not 1 <= self.port <= 65535:
            raise PermissionError('IBKR_ENDPOINT_CONFIGURATION_INVALID')

    @classmethod
    def load(cls, root):
        path = Path(root)/'config/ibkr-session.json'
        if not path.exists():
            return cls()
        value = json.loads(path.read_text(encoding='utf-8-sig'))
        if set(value) != {'host', 'port'}:
            raise PermissionError('IBKR_ENDPOINT_CONFIGURATION_INVALID')
        return cls(**value)

    def matches(self, grant):
        if (grant.get('host', '127.0.0.1'), grant.get('port')) != (self.host, self.port):
            raise PermissionError('IBKR_AUTHORIZED_ENDPOINT_MISMATCH')


class AccountBinding:
    """No inference from an account name, suffix, prefix, endpoint or candidate."""
    def __init__(self, record):
        if (record.get('schema_version') != 1 or record.get('environment') != 'PAPER_TRADING'
                or record.get('live_enabled') is not False or record.get('paper_checked') is not True
                or record.get('identity_manual_match') is not True or record.get('revoked') is not False
                or not re.fullmatch(r'[A-Za-z0-9]{1,64}', record.get('account', ''))):
            raise PermissionError('ACCOUNT_BINDING_INVALID')
        expected = hashlib.sha256(record['account'].encode()).hexdigest()
        if record.get('binding_id') != expected:
            raise PermissionError('ACCOUNT_BINDING_INVALID')
        self._record = dict(record)

    @property
    def account(self): return self._record['account']
    @property
    def binding_id(self): return self._record['binding_id']
    @property
    def masked_account(self): return '***'+self.account[-4:]

    @classmethod
    def from_attestation(cls, grant):
        if (grant.get('schema_version') != 1 or grant.get('paper_checked') is not True
                or grant.get('identity_manual_match') is not True
                or grant.get('live_enabled', False) is not False
                or grant.get('environment', 'PAPER_TRADING') != 'PAPER_TRADING'):
            raise PermissionError('PROTECTED_PAPER_IDENTITY_REQUIRED')
        # The historical read-only grant has no environment/live fields. Its
        # manually matched Paper attestation is identity evidence only.
        account = grant.get('account', '')
        record = {'schema_version': 1, 'account': account,
            'binding_id': hashlib.sha256(account.encode()).hexdigest(),
            'environment': 'PAPER_TRADING', 'live_enabled': False,
            'paper_checked': True, 'identity_manual_match': True, 'revoked': False,
            'created_at': stamp(), 'scope': 'IDENTITY_ONLY_NOT_ORDER_AUTHORIZATION'}
        return cls(record)

    @classmethod
    def load_or_migrate(cls, root, *, loader=unseal, sealer=None):
        root = Path(root); path = root/'.local/ibkr-account-binding.dpapi'
        anchors = []
        for name in ('paper-lab-authorization.dpapi', 'ibkr-paper-authorized.dpapi'):
            anchor = root/'.local'/name
            if anchor.exists():
                value = loader(anchor)
                if value.get('paper_checked') is True and value.get('identity_manual_match') is True:
                    anchors.append(cls.from_attestation(value))
        identities = {a.account for a in anchors}
        if len(identities) > 1:
            raise PermissionError('ACCOUNT_BINDING_AMBIGUOUS_ATTESTATIONS')
        if path.exists():
            binding = cls(loader(path))
            if identities and identities != {binding.account}:
                raise PermissionError('ACCOUNT_BINDING_ATTESTATION_CHANGED')
            return binding
        if len(identities) != 1:
            raise PermissionError('ACCOUNT_BINDING_MISSING_PROTECTED_IDENTITY')
        binding = anchors[0]
        if sealer is None:
            from .paper_identity import protect
            sealer = protect
        # Serialize concurrent migrations, including across processes. An
        # interrupted migration leaves a fail-closed lock, never a new identity.
        path.parent.mkdir(parents=True, exist_ok=True)
        lock = path.with_suffix('.migration.lock')
        owned_lock = False
        try:
            with lock.open('xb'):
                owned_lock = True
                if path.exists():
                    existing = cls(loader(path))
                    if existing.account != binding.account:
                        raise PermissionError('ACCOUNT_BINDING_ATTESTATION_CHANGED')
                    return existing
                sealed = sealer(json.dumps(binding._record).encode())
                temporary = path.with_suffix('.tmp')
                temporary.write_bytes(sealed); temporary.replace(path)
        except FileExistsError:
            raise PermissionError('ACCOUNT_BINDING_MIGRATION_IN_PROGRESS') from None
        finally:
            # Do not remove another process's lock on acquisition failure.
            if owned_lock:
                lock.unlink(missing_ok=True)
        return binding

    def select(self, managed_accounts):
        # Keep the existing single-account TWS isolation requirement. An extra
        # account, including another Paper account, is ambiguous and hard-stops.
        accounts = list(managed_accounts)
        if not accounts:
            raise PermissionError('ACCOUNT_BINDING_NO_MANAGED_ACCOUNTS')
        if len(accounts) != 1:
            raise PermissionError('ACCOUNT_BINDING_AMBIGUOUS_MANAGED_ACCOUNTS')
        if accounts[0] != self.account:
            raise PermissionError('ACCOUNT_BINDING_EXPECTED_ACCOUNT_UNAVAILABLE')
        return self.account


class IbkrSessionGuard:
    def __init__(self, binding, configuration=SessionConfiguration(), mode=ExecutionMode.Research,
                 *, emit=None, binding_loader=None):
        self.binding, self.configuration, self.mode = binding, configuration, ExecutionMode(mode)
        self.emit = emit or (lambda event: None)
        self.binding_loader = binding_loader
        self.connected = False; self.verified = False; self.read_only = False

    def event(self, name, **data):
        self.emit({'event': name, 'at': stamp(), 'account': self.binding.masked_account,
                   'execution_mode': self.mode.value, **data})

    def validate_grant(self, grant):
        if os.environ.get('LIVE_TRADING', 'false').lower() != 'false':
            raise PermissionError('LIVE_DISABLED')
        current = self.binding_loader() if self.binding_loader else self.binding
        if current.binding_id != self.binding.binding_id:
            raise PermissionError('ACCOUNT_BINDING_CHANGED')
        if (grant.get('environment') != 'PAPER_TRADING' or grant.get('live_enabled') is not False
                or grant.get('account') != self.binding.account or grant.get('paper_checked') is not True
                or grant.get('identity_manual_match') is not True):
            raise PermissionError('ACCOUNT_BINDING_GRANT_MISMATCH')
        self.configuration.matches(grant)

    def verify_connected(self, grant, accounts):
        self.connected = self.verified = False
        try:
            self.validate_grant(grant); self.binding.select(accounts)
        except PermissionError:
            self.event('ACCOUNT_BINDING_FAILED'); raise
        self.connected = self.verified = True
        self.event('IBKR_CONNECTED', host=self.configuration.host, port=self.configuration.port)
        self.event('PAPER_ACCOUNT_VERIFIED')

    def disconnected(self):
        self.connected = self.verified = False
        self.event('IBKR_DISCONNECTED')

    def detected_read_only(self):
        self.read_only = True
        self.event('PAPER_AUTO_BLOCKED', reason='TWS API is read-only.')

    def authorize_mutation(self, grant, *, connected, management=False):
        self.validate_grant(grant)
        if self.mode != ExecutionMode.PaperAuto:
            raise PermissionError('RESEARCH_NO_ORDERS' if self.mode == ExecutionMode.Research
                                  else 'LIVE_APPROVAL_REQUIRES_INDEPENDENT_PER_ORDER_AUTHORIZATION')
        if self.read_only or grant.get('read_only_disabled_checked') is not True:
            raise PermissionError('PAPER_AUTO_BLOCKED: TWS API is read-only.')
        if not connected or not self.connected or not self.verified:
            raise ConnectionError('IBKR_SESSION_DISCONNECTED')
        if grant.get('inspection_only') or grant.get('review_only'):
            raise PermissionError('INSPECTION_ONLY_NO_EXECUTION')
        # Expiry/process validity and bounded close-only management are checked
        # by the protected Authorization on every SDK mutation, never here.


class SessionReconnect:
    """Only reconnection/reconciliation can retry. Never retries an order call."""
    def __init__(self, lab, *, attempts=3, sleep=time.sleep):
        self.lab, self.attempts, self.sleep = lab, min(max(attempts, 1), 3), sleep

    def reconcile(self):
        self.lab.reconciled = False
        for attempt in range(self.attempts):
            try:
                return self.lab.connect_and_reconcile()
            except PermissionError:
                # PermissionError subclasses OSError; a hard gate never retries.
                self.lab.reconciled = False
                self.lab.wire.disconnect()
                raise
            except (ConnectionError, TimeoutError, OSError):
                self.lab.reconciled = False
                self.lab.wire.disconnect()
                if attempt+1 == self.attempts:
                    self.lab.stop('IBKR_RECONNECT_EXHAUSTED'); raise
                self.sleep(.25 * 2**attempt)
        raise AssertionError('UNREACHABLE')


class StructuredSessionEvents:
    """Durable transport audit; never receives raw broker messages or identity."""
    def __init__(self,path):
        self.path=Path(path);self.lock=threading.Lock()

    def __call__(self,event):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.lock, self.path.open('a',encoding='utf-8') as stream:
            stream.write(json.dumps(event,allow_nan=False)+'\n');stream.flush();os.fsync(stream.fileno())


def session_guard(root, mode):
    root = Path(root)
    binding = AccountBinding.load_or_migrate(root)
    return IbkrSessionGuard(binding, SessionConfiguration.load(root), mode,
        emit=StructuredSessionEvents(root/'artifacts/paper-lab/session-events.jsonl'),
        binding_loader=lambda: AccountBinding.load_or_migrate(root))


if __name__ == '__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--root',required=True);args=p.parse_args()
    try:
        binding=AccountBinding.load_or_migrate(args.root)
        configuration=SessionConfiguration.load(args.root)
        print(json.dumps({'event':'ACCOUNT_BINDING_LOADED','account':binding.masked_account,
            'host':configuration.host,'port':configuration.port,'scope':'IDENTITY_ONLY',
            'order_authorization_renewed':False,'live_enabled':False}))
    except Exception:
        print(json.dumps({'event':'ACCOUNT_BINDING_FAILED','state':'HARD_STOP','live_enabled':False}))
        raise SystemExit(1)
