"""Bounded, off-hours Paper historical collection using the encrypted host identity.

The module never sends orders and never persists a signing key. The caller must
first observe MARKET_CLOSED from a broker-validated calendar, not infer a clock.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import threading
import time

from trading_agent.core_v3.contracts import require, ContractError, utc
from trading_agent.core_v3.historical_ingestion.files import safe_path
from trading_agent.core_v3.market_observation.authorization import Approval, Grant
from trading_agent.core_v3.market_observation.contracts import Origin, SessionKind

from .backfill.__main__ import Signatures
from .backfill.contracts import BackfillSpec, HistoricalPermit, HistoricalApproval
from .backfill.host_provisioner import build_bundle
from .backfill.reader import HistoricalReader, collect
from .backfill.store import HistoricalStore
from .host_identity import validate_profile, fingerprint, default_path


def offhours_window(now):
    """One bounded week ending at a completed UTC quarter hour (no future bars)."""
    now = utc(now)
    end = now.replace(minute=(now.minute // 15) * 15, second=0, microsecond=0)
    start = (end - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)
    require(timedelta(days=1) <= end - start <= timedelta(days=7), 'M034_HISTORY_WINDOW')
    return start, end


def paper_history_approval(profile, *, now, revocation_check):
    """Construct an M03-A.2 signed permit entirely in memory from the DPAPI profile."""
    profile = validate_profile(profile)
    require(profile['kind'] == 'PAPER' and profile['enabled'] and
            profile['host'] == '127.0.0.1' and profile['port'] == 7497 and
            profile['market_data_confirmed'] and profile['read_only_disabled_confirmed'] and
            callable(revocation_check), 'M034_PAPER_PROFILE_REQUIRED')
    start, end = offhours_window(now)
    bundle = build_bundle(account=profile['account'], start=start, end=end, now=utc(now),
                          paper_confirmed=True, market_data_confirmed=True,
                          read_only_disabled_confirmed=True)
    spec = BackfillSpec.from_json(bundle['spec.json'])
    grant = Grant.from_json(bundle['capture-grant.json'])
    permit = HistoricalPermit.from_json(bundle['historical-permit.json'])
    signatures = Signatures.from_json(bundle['signatures.json'])
    key = bundle['verification.key']
    capture = Approval(grant, signatures.capture_signature, key, enabled=True)
    approval = HistoricalApproval(capture, permit, signatures.historical_signature, key,
                                  host_revocation_check=revocation_check)
    approval.verify(spec, utc(now))
    return spec, approval


def run_offhours_history(profile, vault, stop, *, now=None, root=None,
                         market_closed_confirmed=False):
    """At most one Paper history attempt per UTC day; only after broker closed evidence.

    A durable daily directory prevents repeated historic queries after a crash or
    restart. Partial datasets remain labelled PARTIAL/UNAVAILABLE for inspection.
    """
    require(market_closed_confirmed is True and isinstance(stop, threading.Event),
            'M034_BROKER_CALENDAR_REQUIRED')
    require(not stop.is_set(), 'M034_STOPPED')
    if now is None:
        now = datetime.now(timezone.utc)
    now = utc(now)
    digest = fingerprint(profile)
    require(vault.is_current('PAPER', digest), 'M034_REVOKED_PROFILE')
    history_root = Path(root) if root is not None else default_path().parent / 'historical' / 'paper'
    require(history_root.is_absolute(), 'M034_HISTORY_ROOT')
    history_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    require(not history_root.is_symlink(), 'M034_HISTORY_SYMLINK')
    safe_path(history_root)
    # Exactly one attempt per UTC day; never retry a failed or uncertain request
    # within the same day without operator review of the immutable evidence.
    destination = history_root / now.strftime('%Y%m%d')
    if destination.exists():
        require(destination.is_dir() and not destination.is_symlink(), 'M034_DAILY_MARKER')
        return {'code':'HISTORICAL_ALREADY_ATTEMPTED_TODAY', 'bars':0}
    # A bounded one-second cache prevents repeated expensive DPAPI operations,
    # while ensuring a revoked vault stops an active historical receive promptly.
    lease = {'until':0.0, 'valid':False}
    def still_authorized():
        if stop.is_set(): return False
        current = time.monotonic()
        if current >= lease['until']:
            lease['valid'] = vault.is_current('PAPER', digest)
            lease['until'] = current + 1
        return lease['valid']
    spec, approval = paper_history_approval(profile, now=now,
                                              revocation_check=still_authorized)
    require(not stop.is_set(), 'M034_STOPPED')
    destination.mkdir(mode=0o700)  # exclusive daily marker; concurrent attempts fail closed
    with HistoricalStore(destination, spec, approval.capture.grant.session_id,
                         Origin.SOCKET, SessionKind.PAPER, create=True) as storage:
        reader = HistoricalReader(spec, approval, storage, stop=stop.is_set, wait=stop.wait)
        result = collect(reader, storage)
    return {'code':result.status, 'bars':sum(page.count for page in result.pages),
            'market':result.market_state, 'quality':list(result.quality)}
