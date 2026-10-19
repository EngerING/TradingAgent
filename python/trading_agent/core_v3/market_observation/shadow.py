"""Quote hypotheses only: no fills, economics, backtester bridge or authority."""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from ..contracts import require, identifier, decimal_text, content_hash, utc
from ..historical_ingestion.contracts import Record
from ..economic_contracts import _hash
from .authorization import Approval, Scope
from .contracts import Origin, DataType
from .journal import Journal
from .validation import micros


@dataclass(frozen=True, slots=True)
class ShadowSpec(Record):
    SCHEMA = 'trading.core_v3.observation.shadow_spec'
    strategy_id: str
    version: int
    operator: str
    threshold: Decimal
    direction: str
    allow_unknown_source_time: bool = False
    max_source_age_ms: int = 2000
    subsequent_max_seconds: int = 60
    max_signals: int = 64
    max_subsequent: int = 64

    def __post_init__(self):
        self.check_types()
        identifier(self.strategy_id)
        decimal_text(self.threshold)
        require(1 <= self.version <= 1000000 and self.operator in ('BID_GT','ASK_LT')
                and self.threshold > 0 and self.direction in ('LONG','SHORT'), 'OBS_SHADOW_SPEC')
        require(1 <= self.max_source_age_ms <= 60000 and 1 <= self.subsequent_max_seconds <= 300
                and 1 <= self.max_signals <= 64 and 0 <= self.max_subsequent <= 64, 'OBS_SHADOW_BUDGET')


@dataclass(frozen=True, slots=True)
class ShadowSignal(Record):
    SCHEMA = 'trading.core_v3.observation.shadow_signal'
    strategy_id: str
    strategy_version: int
    strategy_sha256: str
    generated_at: datetime
    causal_sequence: int
    prefix_sha256: str
    available_sequences: tuple[int, ...]
    hypothetical_direction: str
    uncertainty: tuple[str, ...]
    origin: Origin

    def __post_init__(self):
        self.check_types()
        identifier(self.strategy_id)
        _hash(self.strategy_sha256)
        _hash(self.prefix_sha256)
        object.__setattr__(self, 'generated_at', utc(self.generated_at))
        require(self.strategy_version >= 1 and self.causal_sequence >= 1
                and self.hypothetical_direction in ('LONG','SHORT','NO_TRADE')
                and len(self.available_sequences) <= 2 and all(1 <= seq <= self.causal_sequence for seq in self.available_sequences)
                and len(self.uncertainty) <= 16, 'OBS_SHADOW_SIGNAL')


@dataclass(frozen=True, slots=True)
class SubsequentCondition(Record):
    SCHEMA = 'trading.core_v3.observation.subsequent_condition'
    signal_sequence: int
    observed_sequence: int
    observed_at: datetime
    bid: Decimal
    ask: Decimal
    prefix_sha256: str
    source_age_us: int | None

    def __post_init__(self):
        self.check_types()
        require(self.observed_sequence > self.signal_sequence, 'OBS_SUBSEQUENT_CAUSALITY')
        _hash(self.prefix_sha256)
        decimal_text(self.bid)
        decimal_text(self.ask)
        require(0 < self.bid <= self.ask and (self.source_age_us is None or self.source_age_us >= 0), 'OBS_SUBSEQUENT_QUOTE')
        object.__setattr__(self, 'observed_at', utc(self.observed_at))


@dataclass(frozen=True, slots=True)
class ShadowResult(Record):
    SCHEMA = 'trading.core_v3.observation.shadow_result'
    metadata_sha256: str
    strategy_sha256: str
    cutoff: datetime
    available_prefix_sequence: int
    available_prefix_sha256: str
    signals: tuple[ShadowSignal, ...]
    subsequent: tuple[SubsequentCondition, ...]
    incomplete: bool
    action: str = 'NO_TRADE'
    execution_authorized: bool = False
    statistically_validated: bool = False
    economically_approved: bool = False

    def __post_init__(self):
        self.check_types()
        require(self.action == 'NO_TRADE' and not self.execution_authorized and not self.statistically_validated
                and not self.economically_approved and len(self.signals) <= 64 and len(self.subsequent) <= 64, 'OBS_SHADOW_AUTHORITY')


def observe(journal, spec, *, cutoff, approval=None, now=None):
    require(type(journal) is Journal and type(spec) is ShadowSpec, 'OBS_SHADOW_SOURCE')
    cutoff = utc(cutoff)
    spec_hash = content_hash(spec.to_dict())
    if journal.origin is Origin.SOCKET:
        require(type(approval) is Approval and now is not None, 'OBS_REAL_SHADOW_DISABLED')
        approval.verify(Scope.SHADOW, journal.policy, journal.session_id, journal.session_kind, now)
        require(approval.grant.shadow_spec_sha256 == spec_hash and approval.grant.journal_metadata_sha256 == journal.metadata,
                'OBS_SHADOW_APPROVAL_BINDING')
    rows = journal.history()
    signals, subsequent = [], []
    prefix, digest, incomplete, generated_at = 0, journal.metadata, False, None
    for row in rows:
        value, raw = row.value, row.value.event
        # Never skip a future prefix row to consume later entries with an earlier wall time.
        if raw.received_at > cutoff or value.as_of > cutoff:
            break
        if len(signals) >= spec.max_signals:
            incomplete = True
            break
        prefix, digest = row.sequence, row.sha256
        generated_at = max(raw.received_at, value.as_of, generated_at or raw.received_at)
        quote = value.quote
        uncertainty = list(value.reasons)
        direction = 'NO_TRADE'
        available = ()
        eligible = value.accepted and quote is not None
        if quote:
            source_age = None if quote.bid_source_at is None or quote.ask_source_at is None else max(
                micros(generated_at-t) for t in (quote.bid_source_at,quote.ask_source_at))
            if max(micros(generated_at-t) for t in (quote.bid_received_at,quote.ask_received_at)) > journal.policy.side_max_age_ms*1000:
                uncertainty.append('RECEIPT_TOO_OLD_AT_GENERATION')
                eligible = False
            # Raw per-connection sequences are mapped to durable global journal indices.
            indices = tuple(r.sequence for r in rows[:row.sequence] if r.value.event.connection_id == raw.connection_id
                            and r.value.event.sequence in (quote.bid_sequence, quote.ask_sequence))
            available = indices
            if quote.data_type is not DataType.LIVE:
                uncertainty.append('FEED_NOT_LIVE')
                eligible = False
            if source_age is None:
                uncertainty.append('SOURCE_AGE_UNKNOWN')
                eligible = eligible and spec.allow_unknown_source_time
            elif source_age > spec.max_source_age_ms*1000:
                uncertainty.append('SOURCE_TOO_OLD')
                eligible = False
            if eligible:
                for signal in signals:
                    delta = generated_at-signal.generated_at
                    if (signal.hypothetical_direction != 'NO_TRADE' and row.sequence > signal.causal_sequence
                            and 0 < delta.total_seconds() <= spec.subsequent_max_seconds):
                        if len(subsequent) >= spec.max_subsequent:
                            incomplete = True
                            break
                        subsequent.append(SubsequentCondition(signal.causal_sequence, row.sequence, generated_at,
                                          quote.bid, quote.ask, row.sha256, source_age))
                matches = quote.bid > spec.threshold if spec.operator == 'BID_GT' else quote.ask < spec.threshold
                if matches:
                    direction = spec.direction
        elif not uncertainty:
            uncertainty.append('NO_COMPLETE_QUOTE')
        signals.append(ShadowSignal(spec.strategy_id, spec.version, spec_hash, generated_at, row.sequence,
                       row.sha256, available, direction, tuple(dict.fromkeys(uncertainty)), raw.origin))
    # Detect changed/deleted prefix; appends preserving it may coexist.
    after = journal.history()
    require(len(after) >= len(rows) and all(a.sha256 == b.sha256 for a,b in zip(rows, after)), 'OBS_SHADOW_SOURCE_CHANGED')
    result = ShadowResult(journal.metadata, spec_hash, cutoff, prefix, digest, tuple(signals), tuple(subsequent), incomplete)
    result.to_json()
    return result
