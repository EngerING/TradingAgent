"""Closed v1 contracts, separate from Observation and synthetic research engines."""
from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
import hmac

from trading_agent.core_v3.contracts import require, utc, content_hash, canonical_bytes
from trading_agent.core_v3.economic_contracts import _hash
from trading_agent.core_v3.historical_ingestion.contracts import Record
from trading_agent.core_v3.market_observation.contracts import Origin, SessionKind, ContractIdentity
from trading_agent.core_v3.market_observation.authorization import Approval, Scope
from ..contracts import CollectorConfig, Bar, codes

STATES = ('HISTORICAL_BACKFILL','HISTORICAL_COMPLETE','HISTORICAL_PARTIAL',
          'HISTORICAL_UNAVAILABLE','HISTORICAL_REJECTED')


@dataclass(frozen=True, slots=True)
class BackfillSpec(Record):
    SCHEMA = 'trading.m03a2.backfill_spec'
    collector: CollectorConfig
    start: datetime
    end: datetime
    timeframes: tuple[int, ...] = (15,60,240)
    enabled: bool = False
    max_attempts: int = 3
    max_bytes: int = 16777216

    def __post_init__(self):
        self.check_types()
        for n in ('start','end'): object.__setattr__(self,n,utc(getattr(self,n)))
        require(timedelta(days=1) <= self.end-self.start <= timedelta(days=7) and
                (self.start.hour,self.start.minute,self.start.second,self.start.microsecond)==(0,0,0,0) and
                self.end.minute%15==0 and self.end.second==0 and self.end.microsecond==0,
                'M032_DAY_RANGE')
        require(self.timeframes and tuple(sorted(set(self.timeframes)))==self.timeframes and
                all(m in (15,60,240) for m in self.timeframes),'M032_TIMEFRAMES')
        days=(self.end.date()-self.start.date()).days
        if self.end.time() != datetime.min.time(): days+=1
        requests=sum((days+{15:1,60:4,240:7}[m]-1)//{15:1,60:4,240:7}[m] for m in self.timeframes)
        require(self.collector.capture.max_duration_seconds>=20*(requests-1)+10,'M032_PACING_DURATION')
        require(1 <= self.max_attempts <= 3 and 1048576 <= self.max_bytes <= 16777216 and
                self.collector.capture.max_events >= 128,'M032_BUDGET')


@dataclass(frozen=True, slots=True)
class Window(Record):
    SCHEMA = 'trading.m03a2.request_window'
    request_id: int
    minutes: int
    start: datetime
    end: datetime

    def __post_init__(self):
        self.check_types()
        for n in ('start','end'): object.__setattr__(self,n,utc(getattr(self,n)))
        require(3000 <= self.request_id < 3032 and self.minutes in (15,60,240),'M032_REQUEST')
        require((self.start.hour,self.start.minute,self.start.second,self.start.microsecond)==(0,0,0,0) and
                self.end.minute%15==0 and self.end.second==0 and self.end.microsecond==0 and
                timedelta(minutes=15) <= self.end-self.start <=
                timedelta(days={15:1,60:4,240:7}[self.minutes]), 'M032_STEP_SIZE')


@dataclass(frozen=True, slots=True)
class HistoricalPermit(Record):
    SCHEMA = 'trading.m03a2.external_history_permit'
    capture_grant_sha256: str
    spec_sha256: str
    issued_at: datetime
    expires_at: datetime
    scope: str = 'EURUSD_MIDPOINT_HISTORICAL_BACKFILL_ONLY'

    def __post_init__(self):
        self.check_types()
        _hash(self.capture_grant_sha256); _hash(self.spec_sha256)
        for n in ('issued_at','expires_at'): object.__setattr__(self,n,utc(getattr(self,n)))
        require(0 < (self.expires_at-self.issued_at).total_seconds() <= 3600 and
                self.scope=='EURUSD_MIDPOINT_HISTORICAL_BACKFILL_ONLY','M032_PERMIT')


class HistoricalApproval:
    def __init__(self, capture, permit, signature, verification_key, *, host_revocation_check=None):
        require(type(capture) is Approval and type(permit) is HistoricalPermit and
                type(verification_key) is bytes and len(verification_key)>=32,'M032_APPROVAL')
        require(host_revocation_check is None or callable(host_revocation_check),
                'M034_REVOCATION_CALLBACK')
        _hash(signature)
        self.capture,self.permit,self.signature,self._key=capture,permit,signature,verification_key
        self._host_revocation_check=host_revocation_check

    def verify(self, spec, now):
        require(type(spec) is BackfillSpec,'M032_SPEC')
        if self._host_revocation_check is not None:
            require(self._host_revocation_check() is True,'M034_HISTORY_REVOKED')
        g,p=self.capture.grant,self.permit
        now=utc(now)
        # Core V3.9 Approval.verify stays unchanged: other consumers still require
        # broker-wide Read-Only API. Only the separately signed HistoricalPermit
        # may authorize an order-capable TWS for historical DATA_ONLY on Paper.
        if g.tws_read_only_confirmed:
            self.capture.verify(Scope.CAPTURE,spec.collector.capture,g.session_id,g.session_kind,now)
        else:
            require(g.session_kind is SessionKind.PAPER,'M032_PAPER_RW_NOT_AUTHORIZED')
            # Exact capture-grant signature, revocation, scope, policy and expiry
            # checks duplicated here solely for the Paper/history exception.
            # The ordinary Core/M03-A verification path is never relaxed.
            cap=self.capture
            expected=hmac.new(cap._key,canonical_bytes(g.to_dict()),hashlib.sha256).hexdigest()
            require(cap.enabled and not cap._revoked and
                    hmac.compare_digest(expected,cap.signature),'M032_PAPER_CAPTURE_DISABLED')
            require(g.scope is Scope.CAPTURE and
                    g.policy_sha256==content_hash(spec.collector.capture.to_dict()) and
                    g.issued_at<=now<g.expires_at and g.market_permission_confirmed,
                    'M032_PAPER_CAPTURE_UNVERIFIED')
        signature=hmac.new(self._key,canonical_bytes(p.to_dict()),hashlib.sha256).hexdigest()
        require(spec.enabled and spec.collector.enabled and hmac.compare_digest(signature,self.signature) and
                p.spec_sha256==content_hash(spec.to_dict()) and
                p.capture_grant_sha256==content_hash(g.to_dict()) and
                g.issued_at<=p.issued_at<=now<p.expires_at<=g.expires_at,'M032_PERMISSION')


@dataclass(frozen=True, slots=True)
class HistoricalBar(Record):
    SCHEMA = 'trading.m03a2.historical_bar'
    bar: Bar
    contract: ContractIdentity
    origin: Origin
    environment: SessionKind
    received_at: datetime
    request: Window
    connection_id: str
    commit_sha256: str

    def __post_init__(self):
        self.check_types(); _hash(self.commit_sha256)
        object.__setattr__(self,'received_at',utc(self.received_at))
        require(self.request.start<=self.bar.opened_at<self.request.end and
                self.bar.minutes==self.request.minutes and self.bar.available_at>=self.received_at and
                self.bar.effective_close<=min(self.request.end,self.received_at),'M032_CAUSAL_BAR')
        require(0<len(self.connection_id)<=80,'M032_CONNECTION')


@dataclass(frozen=True, slots=True)
class Page(Record):
    SCHEMA = 'trading.m03a2.history_page'
    identity_sha256: str
    minutes: int
    bars: tuple[HistoricalBar, ...]

    def __post_init__(self):
        self.check_types(); _hash(self.identity_sha256)
        require(self.minutes in (15,60,240) and 0<len(self.bars)<=64 and
                all(b.bar.minutes==self.minutes and b.bar.complete for b in self.bars) and
                all(a.bar.opened_at<b.bar.opened_at for a,b in zip(self.bars,self.bars[1:])), 'M032_PAGE')


@dataclass(frozen=True, slots=True)
class PageRef(Record):
    SCHEMA = 'trading.m03a2.page_ref'
    sha256: str
    minutes: int
    count: int

    def __post_init__(self):
        self.check_types(); _hash(self.sha256)
        require(self.minutes in (15,60,240) and 1<=self.count<=64,'M032_PAGE_REF')


@dataclass(frozen=True, slots=True)
class Dataset(Record):
    SCHEMA = 'trading.m03a2.historical_dataset'
    identity_sha256: str
    spec: BackfillSpec
    origin: Origin
    environment: SessionKind
    available_at: datetime
    status: str
    market_state: str
    quality: tuple[str, ...]
    pages: tuple[PageRef, ...]
    journal_head: str
    committed_events: int
    instrument: str = 'EUR/USD'
    source: str = 'IBKR_TWS_MIDPOINT'
    feed_type: str = 'UNKNOWN'
    decision: str = 'NO_TRADE'
    execution_authorized: bool = False
    indicators_evaluated: bool = False

    def __post_init__(self):
        self.check_types(); _hash(self.identity_sha256); _hash(self.journal_head); codes(self.quality)
        object.__setattr__(self,'available_at',utc(self.available_at))
        require(self.status in STATES and self.market_state in ('MARKET_OPEN','MARKET_CLOSED','MARKET_UNKNOWN') and
                len(self.pages)<=24 and 0<=self.committed_events<=8192,'M032_DATASET')
        require((self.instrument,self.source,self.feed_type,self.decision)==
                ('EUR/USD','IBKR_TWS_MIDPOINT','UNKNOWN','NO_TRADE') and
                not self.execution_authorized and not self.indicators_evaluated,'M032_NO_TRADE')
        require(sum(p.count for p in self.pages)<=2048,'M032_ROW_BUDGET')


@dataclass(frozen=True, slots=True)
class PageCursor(Record):
    SCHEMA = 'trading.m03a2.page_cursor'
    dataset_sha256: str
    query_sha256: str
    index: int

    def __post_init__(self):
        self.check_types(); _hash(self.dataset_sha256); _hash(self.query_sha256)
        require(0<=self.index<=24,'M032_CURSOR')
