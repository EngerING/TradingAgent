"""Immutable normalized records and inspection results, with no synthetic-engine API."""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
import hashlib
import re

from ..contracts import canonical_bytes, decimal_text, identifier, require, utc
from ..economic_contracts import _hash
from .contracts import MAX_ROWS, PARSER_VERSION, Record


def amounts(*values):
    for value in values:
        if value is not None:
            decimal_text(value)
            require(value >= 0, 'H38_NEGATIVE_AMOUNT')


@dataclass(frozen=True, slots=True)
class HistoricalBar(Record):
    SCHEMA = 'trading.core_v3.historical.bar'
    row_number: int
    record_id: str
    opened_at: datetime
    closed_at: datetime
    available_at: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal | None

    def __post_init__(self):
        self.check_types()
        require(2 <= self.row_number <= MAX_ROWS+1, 'H38_ROW_NUMBER')
        identifier(self.record_id)
        for name in ('opened_at', 'closed_at', 'available_at'):
            object.__setattr__(self, name, utc(getattr(self, name)))
        require(self.opened_at < self.closed_at <= self.available_at, 'H38_BAR_TIME')
        amounts(self.open, self.high, self.low, self.close, self.volume)
        require(0 < self.low <= min(self.open, self.close) <= max(self.open, self.close) <= self.high, 'H38_OHLC')


@dataclass(frozen=True, slots=True)
class HistoricalQuote(Record):
    SCHEMA = 'trading.core_v3.historical.quote'
    row_number: int
    record_id: str
    event_at: datetime
    available_at: datetime
    sequence: int
    bid: Decimal
    ask: Decimal
    bid_size: Decimal | None
    ask_size: Decimal | None

    def __post_init__(self):
        self.check_types()
        require(2 <= self.row_number <= MAX_ROWS+1 and 0 <= self.sequence < 2**63, 'H38_QUOTE_SEQUENCE')
        identifier(self.record_id)
        for name in ('event_at', 'available_at'):
            object.__setattr__(self, name, utc(getattr(self, name)))
        require(self.event_at <= self.available_at, 'H38_QUOTE_TIME')
        amounts(self.bid, self.ask, self.bid_size, self.ask_size)
        require(0 < self.bid <= self.ask, 'H38_CROSSED_QUOTE')


def records_hash(records):
    digest = hashlib.sha256(b'CORE_V38_RECORD_STREAM_V1\0')
    for record in records:
        require(type(record) in (HistoricalBar, HistoricalQuote), 'H38_RECORD_TYPE')
        raw = canonical_bytes(record)
        digest.update(len(raw).to_bytes(8, 'big'))
        digest.update(raw)
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class Issue(Record):
    SCHEMA = 'trading.core_v3.historical.issue'
    row_number: int
    code: str

    def __post_init__(self):
        self.check_types()
        require(0 <= self.row_number <= MAX_ROWS+2, 'H38_ROW_NUMBER')
        require(re.fullmatch(r'[A-Z][A-Z0-9_]{0,79}', self.code) is not None, 'H38_ISSUE_CODE')


@dataclass(frozen=True, slots=True)
class QualityReport(Record):
    SCHEMA = 'trading.core_v3.historical.quality'
    input_rows: int
    candidate_rows: int
    scan_complete: bool
    expected_intervals: int | None
    gap_count: int
    issues: tuple[Issue, ...]

    def __post_init__(self):
        self.check_types()
        require(0 <= self.candidate_rows <= self.input_rows <= MAX_ROWS+1, 'H38_ROW_COUNT')
        require(self.expected_intervals is None or 0 <= self.expected_intervals <= MAX_ROWS, 'H38_ROW_COUNT')
        require(0 <= self.gap_count <= MAX_ROWS*2 and len(self.issues) <= 256, 'H38_REPORT_LIMIT')
        require(self.scan_complete or bool(self.issues), 'H38_INCOMPLETE_REPORT')


@dataclass(frozen=True, slots=True)
class IngestionManifest(Record):
    SCHEMA = 'trading.core_v3.historical.manifest'
    status: str
    data_origin: str
    raw_sha256: str
    descriptor_sha256: str
    calendar_sha256: str
    tzif_sha256: str
    evidence_sha256: str
    review_sha256: str | None
    candidate_records_sha256: str
    report_sha256: str
    input_rows: int
    cutoff: datetime
    source_kind: str
    assurance: str
    parser_version: str = PARSER_VERSION
    authenticity: str = 'NOT_CRYPTOGRAPHICALLY_VERIFIED'
    scope: str = 'OFFLINE_HISTORICAL_INGESTION_ONLY'
    trading_decision: str = 'NO_TRADE'
    backtest_eligible: bool = False
    execution_authority: bool = False
    paper_execution_eligible: bool = False
    live_enabled: bool = False
    statistically_validated: bool = False

    def __post_init__(self):
        self.check_types()
        for value in (self.raw_sha256, self.descriptor_sha256, self.calendar_sha256, self.tzif_sha256,
                      self.evidence_sha256, self.candidate_records_sha256, self.report_sha256):
            _hash(value)
        if self.review_sha256 is not None:
            _hash(self.review_sha256)
        require(self.status in ('READY_FOR_INSPECTION', 'QUARANTINED'), 'H38_STATUS')
        require((self.data_origin, self.source_kind) in (
            ('PROVIDER_EXPORT', 'REAL_HISTORICAL_UNVERIFIED'),
            ('SYNTHETIC_TEST_FIXTURE', 'SYNTHETIC_TEST_FIXTURE')), 'H38_ORIGIN')
        require(self.assurance == ('UNREVIEWED' if self.review_sha256 is None else 'LOCAL_REVIEW_ATTESTED'),
                'H38_ASSURANCE')
        require(self.status != 'READY_FOR_INSPECTION' or (
            self.data_origin == 'SYNTHETIC_TEST_FIXTURE' and self.review_sha256 is not None), 'H38_REAL_ADAPTER_PENDING')
        require(0 <= self.input_rows <= MAX_ROWS+1, 'H38_ROW_COUNT')
        object.__setattr__(self, 'cutoff', utc(self.cutoff))
        require(self.parser_version == PARSER_VERSION and self.authenticity == 'NOT_CRYPTOGRAPHICALLY_VERIFIED'
                and self.scope == 'OFFLINE_HISTORICAL_INGESTION_ONLY' and self.trading_decision == 'NO_TRADE'
                and all(v is False for v in (self.backtest_eligible, self.execution_authority,
                    self.paper_execution_eligible, self.live_enabled, self.statistically_validated)), 'H38_AUTHORITY')


@dataclass(frozen=True, slots=True)
class IngestionResult:
    manifest: IngestionManifest
    report: QualityReport
    records: tuple

    def __post_init__(self):
        from ..contracts import content_hash
        require(type(self.manifest) is IngestionManifest and type(self.report) is QualityReport
                and type(self.records) is tuple, 'H38_RESULT_TYPES')
        require(self.manifest.report_sha256 == content_hash(self.report)
                and self.manifest.input_rows == self.report.input_rows, 'H38_REPORT_BINDING')
        if self.manifest.status == 'READY_FOR_INSPECTION':
            require(not self.report.issues and self.report.scan_complete
                    and len(self.records) == self.report.candidate_rows > 0
                    and records_hash(self.records) == self.manifest.candidate_records_sha256, 'H38_RESULT_BINDING')
        else:
            require(bool(self.report.issues) and not self.records, 'H38_QUARANTINE_BINDING')
