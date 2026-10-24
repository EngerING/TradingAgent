"""Ephemeral 30-minute M03-A.3 leases from revocable encrypted owner consent."""
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import secrets

from trading_agent.core_v3.contracts import require, canonical_bytes, content_hash, utc
from trading_agent.core_v3.market_observation.authorization import (
    Approval, Grant, Scope, accounts_digest,
)
from trading_agent.core_v3.market_observation.contracts import CapturePolicy, SessionKind
from .authorization import DataApproval, DataPermit, RW_HOST_SCOPE
from .contracts import CollectorConfig
from .host_identity import validate_profile


def issue_data_lease(profile, *, now=None, revocation_check=None):
    """No socket, credentials, TWS login or order API. Caller owns explicit host consent."""
    profile = validate_profile(profile)
    require(profile['enabled'], 'M033_PROFILE_REVOKED')
    if now is None:
        now = datetime.now(timezone.utc)
    now = utc(now)
    kind = SessionKind(profile['kind'])
    name = 'm03a3-' + kind.value.lower() + '-read-v1'
    policy = CapturePolicy(name, max_events=512, max_duration_seconds=120,
                           max_requests=16, max_reconnects=0)
    config = CollectorConfig(name, policy, enabled=True, max_segments=8,
                             max_run_seconds=900, retry_seconds=4, max_failures=2)
    key = secrets.token_bytes(32)
    unique = secrets.token_hex(12)
    expires = now + timedelta(minutes=30)
    attestation = content_hash({
        'source': 'M03A3_LOCAL_OWNER_ATTESTATION_NOT_BROKER_PROOF',
        'consent_at': profile['consent_at'],
        'environment': kind.value,
        'endpoint': ('127.0.0.1', profile['port'], profile['client_id']),
        'account_hmac': accounts_digest(profile['account'], key),
        'scope': RW_HOST_SCOPE,
        'tws_read_only_disabled_declared': True,
    })
    grant = Grant('m03a3-' + unique, Scope.CAPTURE, '127.0.0.1',
                  profile['port'], profile['client_id'], 'm03a3-' + unique,
                  kind, content_hash(policy.to_dict()),
                  accounts_digest(profile['account'], key), attestation, now, expires,
                  tws_read_only_confirmed=False, market_permission_confirmed=True)
    permit = DataPermit(content_hash(grant.to_dict()), content_hash(config.to_dict()),
                        now, expires, scope=RW_HOST_SCOPE)
    sign = lambda record: hmac.new(key, canonical_bytes(record.to_dict()), hashlib.sha256).hexdigest()
    approval = DataApproval(Approval(grant, sign(grant), key, enabled=True),
                            permit, sign(permit), key,
                            host_revocation_check=revocation_check)
    approval.verify(config, now)
    return config, approval
