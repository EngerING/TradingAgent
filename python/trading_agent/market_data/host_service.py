"""M03-A.3 operator CLI and revocable background DATA_ONLY collector, not a trader."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket
import sys
import threading
import time
import uuid

from trading_agent.core_v3.contracts import require, ContractError
from trading_agent.core_v3.market_observation.contracts import Origin, SessionKind
from .archive import Archive
from .host_approval import issue_data_lease
from .host_identity import HostVault, fingerprint, KINDS, default_path
from .reader import MarketReader
from .supervisor import Supervisor

STOP = threading.Event()
MAX_ARCHIVES_PER_PROFILE = 10000


def _read_masked_account(prompt, *, get_key=None, emit=None, interactive=None):
    """Read account identifier from a Windows console; echo only '*' and never the value."""
    require(sys.platform == 'win32', 'M033_WINDOWS_REQUIRED')
    # No stdin redirection or invisible getpass fallback. A real console is required.
    if interactive is None:
        interactive = sys.stdin.isatty() and sys.stdout.isatty()
    require(interactive is True, 'M033_INTERACTIVE_CONSOLE_REQUIRED')
    import msvcrt
    take_key = get_key or msvcrt.getwch

    def default_emit(value):
        sys.stdout.write(value)
        sys.stdout.flush()

    write = emit or default_emit
    chars = []
    write(prompt)
    while True:
        key = take_key()
        if key in ('\r', '\n'):
            write('\n')
            require(6 <= len(chars) <= 80, 'M033_ACCOUNT_INPUT_LENGTH')
            return ''.join(chars).upper()
        if key in ('\b', '\x7f'):
            if chars:
                chars.pop()
                write('\b \b')
            continue
        if key in ('\x00', '\xe0'):
            take_key()  # Discard the scan code for arrows/function keys.
            continue
        if key in ('\x03', '\x04', '\x1a', '\x1b'):
            write('\n')
            raise ContractError('M033_ACCOUNT_INPUT_CANCELLED')
        if type(key) is not str or len(key) != 1 or not key.isascii() or not key.isalnum():
            write('\n')
            raise ContractError('M033_ACCOUNT_INPUT_INVALID')
        if len(chars) >= 80:
            write('\n')
            raise ContractError('M033_ACCOUNT_INPUT_TOO_LONG')
        chars.append(key)
        write('*')


def output(status, **values):
    print(json.dumps({'status':status, 'mode':'IBKR_DATA_ONLY' if status in ('CAPTURE_RUNNING','CAPTURE_STOPPED') else 'OFFLINE',
                      'decision':'NO_TRADE','executionAuthorized':False, **values}, sort_keys=True), flush=True)


def _listener_reachable(profile):
    # Only the exact explicitly enrolled loopback endpoint. This is not identity proof.
    try:
        with socket.create_connection((profile['host'], profile['port']), timeout=1):
            return True
    except OSError:
        return False


def _interruptible_reader(host_stop):
    """Forward the process shutdown signal into the active 120-second socket reader."""
    def create(config, approval, **kwargs):
        supervisor_stop = kwargs.pop('stop')
        return MarketReader(config, approval, **kwargs,
                            stop=lambda:host_stop.is_set() or supervisor_stop())
    return create


def _profile_loop(vault, kind, archive_root, stop, result):
    count = 0
    try:
        base = archive_root / kind.lower()
        base.mkdir(parents=True, exist_ok=True)
        require(base.is_dir() and not base.is_symlink(), 'M033_ARCHIVE_ROOT')
        while not stop.is_set():
            profiles = vault.load()
            profile = profiles.get(kind)
            if profile is None or not profile['enabled']:
                result[kind] = 'CONSENT_REVOKED_OR_ABSENT'
                break
            digest = fingerprint(profile)
            # Cache DPAPI decryption for at most one second, even during busy ticks.
            state = {'until':0.0, 'ok':False}
            def still_authorized():
                now_mono = time.monotonic()
                if now_mono >= state['until']:
                    state['ok'] = vault.is_current(kind, digest)
                    state['until'] = now_mono + 1
                return state['ok'] and not stop.is_set()
            cfg, approval = issue_data_lease(profile,
                revocation_check=still_authorized)
            if not _listener_reachable(profile):
                result[kind] = 'WAITING_FOR_TWS'
                stop.wait(15)
                continue
            require(sum(1 for item in base.iterdir() if item.is_dir()) <
                    MAX_ARCHIVES_PER_PROFILE, 'M033_ARCHIVE_RETENTION_REQUIRED')
            directory = base / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
                                + '-' + uuid.uuid4().hex[:10])
            directory.mkdir(mode=0o700)
            try:
                with Archive(directory,cfg,approval.capture.grant.session_id,
                             Origin.SOCKET,SessionKind(kind),create=True) as archive:
                    supervisor = Supervisor(archive, approval,
                                            reader_factory=_interruptible_reader(stop),
                                            wait=stop.wait)
                    health = supervisor.run()
            except (OSError,ContractError):
                result[kind] = 'LOCAL_STORAGE_OR_PERMISSION_FAILURE'
                break
            count += 1
            result[kind] = health.code
            # Refuse to continue after account/profile mismatch or uncertain safety.
            if health.code in ('IDENTITY_OR_PERMISSION_REJECTED','PROFILE_REJECTED',
                               'SESSION_OR_FEED_INVALID','CONFIGURATION_OR_PERMISSION_REJECTED',
                               'STORAGE_FAILURE'):
                break
            # A new 30-minute signed permit will be issued before the next cycle.
            # Each 15-minute bounded capture has a fresh journal epoch and declares gaps.
            stop.wait(2 if health.code in ('RUN_DEADLINE','CAPTURE_BOUNDARY','SEGMENT_BUDGET')
                      else 15)
    except (OSError,ContractError):
        result[kind] = 'HOST_REJECTED'
    finally:
        output('CAPTURE_STOPPED', environment=kind, runs=count,
               reason=result.get(kind,'STOPPED'))


def main(argv=None):
    p = argparse.ArgumentParser(description='M03-A.3 encrypted host identity, DATA_ONLY')
    sub = p.add_subparsers(dest='command', required=True)
    enroll = sub.add_parser('enroll')
    enroll.add_argument('--kind', choices=KINDS, required=True)
    enroll.add_argument('--port', type=int, required=True)
    enroll.add_argument('--client-id', type=int, required=True)
    enroll.add_argument('--confirm-market-data', action='store_true')
    enroll.add_argument('--confirm-session', action='store_true')
    enroll.add_argument('--confirm-read-only-disabled', action='store_true')
    enroll.add_argument('--replace', action='store_true')
    status = sub.add_parser('status')
    revoke = sub.add_parser('revoke')
    revoke.add_argument('--kind', choices=KINDS, required=True)
    watch = sub.add_parser('watch')
    watch.add_argument('--kind', choices=('BOTH',)+KINDS, required=True)
    watch.add_argument('--approved-data-only', action='store_true')
    args = p.parse_args(argv)
    if args.command == 'watch' and not args.approved_data_only:
        output('DISABLED');return 0
    try:
        require(sys.platform == 'win32', 'M033_WINDOWS_REQUIRED')
        vault = HostVault()
        if args.command == 'status':
            profiles = vault.load()
            output('HOST_PROFILE_STATUS', profiles=[
                {'environment':kind,'registered':True,'enabled':profile['enabled'],
                 'port':profile['port']} for kind,profile in sorted(profiles.items())])
            return 0
        if args.command == 'enroll':
            require(args.confirm_market_data and args.confirm_session and
                    args.confirm_read_only_disabled, 'M033_OPERATOR_CONFIRMATIONS')
            account = _read_masked_account('Identificador IBKR ' + args.kind +
                                           ' (* por caracter, Enter para confirmar): ')
            vault.enroll(args.kind,account,port=args.port,
                         client_id=args.client_id,confirm=True,replace=args.replace)
            output('HOST_DATA_IDENTITY_SAVED', environment=args.kind,
                   account_suffix=account[-4:], encrypted=True,
                   socketConnected=False)
            return 0
        if args.command == 'revoke':
            vault.revoke(args.kind)
            output('HOST_DATA_CONSENT_REVOKED', environment=args.kind)
            return 0
        profiles = vault.load()
        kinds = KINDS if args.kind == 'BOTH' else (args.kind,)
        require(all(kind in profiles and profiles[kind]['enabled'] for kind in kinds),
                'M033_CONSENT_REQUIRED')
        archive_root = default_path().parent / 'captures'
        archive_root.mkdir(parents=True, exist_ok=True)
        require(archive_root.is_dir() and not archive_root.is_symlink(),
                'M033_ARCHIVE_ROOT')
        STOP.clear()
        result = {}
        output('CAPTURE_RUNNING', environments=list(kinds))
        workers = [threading.Thread(target=_profile_loop,
                   args=(vault,kind,archive_root,STOP,result),daemon=True) for kind in kinds]
        for worker in workers: worker.start()
        try:
            while any(worker.is_alive() for worker in workers):
                time.sleep(.5)
        except KeyboardInterrupt:
            STOP.set()
        finally:
            STOP.set()
            for worker in workers: worker.join(timeout=10)
        return 0
    except (ContractError,OSError,ValueError,EOFError):
        output('HOST_DATA_ONLY_REJECTED')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
