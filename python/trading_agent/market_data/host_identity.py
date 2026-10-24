"""M03-A.3 Windows-user protected DATA_ONLY identities; never stores IBKR login credentials."""
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sys

from trading_agent.core_v3.contracts import require, ContractError

KINDS = ('PAPER', 'LIVE')
SCHEMA = 'trading.m03a3.local_host_identities'
VERSION = 1
MAX_VAULT_BYTES = 16384


class _Blob(ctypes.Structure):
    _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_ubyte))]


def _dpapi(payload, *, decrypt=False):
    """CryptProtectData/UnprotectData with current Windows user scope (not machine scope)."""
    require(sys.platform == 'win32' and isinstance(payload, bytes) and payload,
            'M033_WINDOWS_DPAPI_REQUIRED')
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    func = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    func.argtypes = [ctypes.POINTER(_Blob), ctypes.c_void_p, ctypes.c_void_p,
                     ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_Blob)]
    func.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    raw = (ctypes.c_ubyte * len(payload)).from_buffer_copy(payload)
    source = _Blob(len(payload), ctypes.cast(raw, ctypes.POINTER(ctypes.c_ubyte)))
    target = _Blob()
    # No CRYPTPROTECT_LOCAL_MACHINE. No password/TOTP ever collected here.
    if not func(ctypes.byref(source), None, None, None, None, 0, ctypes.byref(target)):
        raise ContractError('M033_DPAPI_FAILED')
    try:
        return ctypes.string_at(target.pbData, target.cbData)
    finally:
        kernel.LocalFree(ctypes.cast(target.pbData, ctypes.c_void_p))


def default_path():
    require(sys.platform == 'win32' and bool(os.environ.get('LOCALAPPDATA')),
            'M033_WINDOWS_HOST_REQUIRED')
    return Path(os.environ['LOCALAPPDATA']) / 'TradingAgent' / 'market-data-host' / 'identities.dpapi'


def validate_profile(profile):
    require(type(profile) is dict and set(profile) == {
        'kind', 'account', 'host', 'port', 'client_id',
        'market_data_confirmed', 'read_only_disabled_confirmed', 'enabled', 'consent_at'
    }, 'M033_PROFILE_FIELDS')
    kind, account = profile['kind'], profile['account']
    require(kind in KINDS and type(account) is str and
            re.fullmatch(r'[A-Z0-9]{6,80}', account) is not None,
            'M033_ACCOUNT_FORMAT')
    require((kind != 'PAPER' or account.startswith('DU') and account.endswith('3784')) and
            (kind != 'LIVE' or not account.startswith('DU')),
            'M033_ENVIRONMENT_ACCOUNT')
    require(profile['host'] == '127.0.0.1' and
            type(profile['port']) is int and 1024 <= profile['port'] <= 65535 and
            type(profile['client_id']) is int and 1 <= profile['client_id'] < 2**31,
            'M033_ENDPOINT')
    require(profile['market_data_confirmed'] is True and
            profile['read_only_disabled_confirmed'] is True and
            type(profile['enabled']) is bool and
            type(profile['consent_at']) is str and len(profile['consent_at']) <= 40,
            'M033_DATA_ONLY_CONSENT')
    try:
        stamp = datetime.fromisoformat(profile['consent_at'])
    except ValueError:
        require(False, 'M033_CONSENT_TIME')
    require(stamp.tzinfo is not None, 'M033_CONSENT_TIME')
    return profile


def fingerprint(profile):
    return hashlib.sha256(json.dumps(validate_profile(profile), sort_keys=True,
                                     separators=(',', ':')).encode('utf-8')).hexdigest()


class HostVault:
    """Atomic encrypted-at-rest local file. Authorship is the current Windows login."""
    def __init__(self, path=None, *, protect=None, unprotect=None):
        self.path = Path(path) if path is not None else default_path()
        require(self.path.is_absolute(), 'M033_VAULT_PATH')
        self.protect = protect or (lambda payload: _dpapi(payload))
        self.unprotect = unprotect or (lambda payload: _dpapi(payload, decrypt=True))

    def load(self):
        if not self.path.exists():
            return {}
        require(self.path.is_file() and not self.path.is_symlink() and
                self.path.stat().st_nlink == 1 and
                0 < self.path.stat().st_size <= MAX_VAULT_BYTES,
                'M033_VAULT_FILE')
        encrypted = self.path.read_bytes()
        try:
            document = json.loads(self.unprotect(encrypted).decode('utf-8'))
        except (ValueError, UnicodeError, TypeError):
            raise ContractError('M033_VAULT_DECRYPT_OR_SCHEMA') from None
        require(type(document) is dict and set(document) == {'schema', 'version', 'profiles'} and
                document['schema'] == SCHEMA and document['version'] == VERSION and
                type(document['profiles']) is dict and
                set(document['profiles']).issubset(KINDS), 'M033_VAULT_SCHEMA')
        profiles = document['profiles']
        for kind, value in profiles.items():
            require(validate_profile(value)['kind'] == kind, 'M033_VAULT_KIND')
        require(not (len(profiles) == 2 and
            (profiles['PAPER']['port'] == profiles['LIVE']['port'] or
             profiles['PAPER']['client_id'] == profiles['LIVE']['client_id'])),
            'M033_AMBIGUOUS_ENDPOINTS')
        return profiles

    def save(self, profiles):
        require(type(profiles) is dict and set(profiles).issubset(KINDS),
                'M033_VAULT_SCHEMA')
        for kind, profile in profiles.items():
            require(validate_profile(profile)['kind'] == kind, 'M033_VAULT_KIND')
        require(not (len(profiles) == 2 and
            (profiles['PAPER']['port'] == profiles['LIVE']['port'] or
             profiles['PAPER']['client_id'] == profiles['LIVE']['client_id'])),
            'M033_AMBIGUOUS_ENDPOINTS')
        document = {'schema': SCHEMA, 'version': VERSION, 'profiles': profiles}
        payload = json.dumps(document, sort_keys=True, separators=(',', ':')).encode('utf-8')
        encrypted = self.protect(payload)
        require(type(encrypted) is bytes and 0 < len(encrypted) <= MAX_VAULT_BYTES,
                'M033_VAULT_CIPHERTEXT')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        require(not self.path.parent.is_symlink() and
                (not self.path.exists() or
                 self.path.is_file() and not self.path.is_symlink() and
                 self.path.stat().st_nlink == 1),
                'M033_VAULT_PATH')
        temp = self.path.with_name(self.path.name + '.' + secrets.token_hex(8) + '.tmp')
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(encrypted)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, self.path)
        finally:
            if temp.exists():
                temp.unlink()

    def enroll(self, kind, account, *, port, client_id, confirm, replace=False):
        require(kind in KINDS and confirm is True, 'M033_EXPLICIT_DATA_CONSENT')
        profiles = self.load()
        require(kind not in profiles or replace is True, 'M033_ALREADY_ENROLLED')
        profile = validate_profile({
            'kind': kind, 'account': account, 'host': '127.0.0.1', 'port': port,
            'client_id': client_id, 'market_data_confirmed': True,
            'read_only_disabled_confirmed': True, 'enabled': True,
            'consent_at': datetime.now(timezone.utc).isoformat()
        })
        profiles[kind] = profile
        self.save(profiles)

    def revoke(self, kind):
        profiles = self.load()
        require(kind in profiles, 'M033_UNKNOWN_PROFILE')
        profiles[kind] = dict(profiles[kind], enabled=False)
        self.save(profiles)

    def is_current(self, kind, digest):
        profiles = self.load()
        return kind in profiles and profiles[kind]['enabled'] and fingerprint(profiles[kind]) == digest
