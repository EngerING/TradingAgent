"""Opaque Dukascopy CSV custody. Actual columns await a real sample and export documentation."""
from dataclasses import dataclass
from datetime import datetime, date
import re

from ..contracts import canonical_bytes, identifier, require, utc
from .contracts import Record
from .files import ARCHIVE_LIMIT, _verify_bytes, read_local, store_bundle
from .ingestion import sha256


@dataclass(frozen=True, slots=True)
class DukascopySettings(Record):
    SCHEMA = 'trading.core_v3.historical.dukascopy.declared_export'
    instrument: str
    timeframe: str
    timezone_name: str
    side: str
    month: str
    exported_at: datetime
    observed_at: datetime
    data_origin: str
    configuration_reference: str
    provider: str = 'DUKASCOPY_BANK_SA'
    file_format: str = 'CSV'

    def __post_init__(self):
        self.check_types()
        require(self.provider == 'DUKASCOPY_BANK_SA' and self.instrument == 'EURUSD'
                and self.timeframe == 'H1' and self.timezone_name == 'UTC'
                and self.side in ('BID', 'ASK') and self.file_format == 'CSV', 'H38_DUKASCOPY_SCOPE')
        require(self.data_origin in ('PROVIDER_EXPORT', 'SYNTHETIC_TEST_FIXTURE'), 'H38_ORIGIN')
        require(re.fullmatch(r'[0-9]{4}-[0-9]{2}', self.month) is not None, 'H38_EXPORT_MONTH')
        try:
            start = date.fromisoformat(self.month+'-01')
            require(start < date.max, 'H38_EXPORT_MONTH')
        except ValueError:
            require(False, 'H38_EXPORT_MONTH')
        identifier(self.configuration_reference)
        for name in ('exported_at', 'observed_at'):
            object.__setattr__(self, name, utc(getattr(self, name)))
        require(start <= self.exported_at.date() and self.exported_at <= self.observed_at, 'H38_EXPORT_TIME')


def _custody_files(raw, settings, evidence, cutoff):
    require(type(settings) is DukascopySettings, 'H38_DUKASCOPY_SETTINGS')
    cutoff = utc(cutoff)
    require(settings.observed_at <= cutoff, 'H38_OBSERVED_AFTER_CUTOFF')
    manifest = {'schema': 'trading.core_v3.historical.dukascopy.custody', 'schema_version': 1,
        'status': 'QUARANTINED', 'reason': 'DUKASCOPY_FORMAT_UNVERIFIED',
        'provider': settings.provider, 'data_origin': settings.data_origin,
        'source_kind': 'REAL_HISTORICAL_UNVERIFIED' if settings.data_origin == 'PROVIDER_EXPORT'
                       else 'SYNTHETIC_TEST_FIXTURE',
        'settings_sha256': sha256(canonical_bytes(settings)), 'raw_sha256': sha256(raw),
        'raw_bytes': len(raw), 'evidence_sha256': sha256(evidence), 'cutoff': cutoff,
        'authenticity': 'NOT_VERIFIED', 'availability': 'UNKNOWN_NO_RETROACTIVE_ASSUMPTION',
        'scope': 'OFFLINE_HISTORICAL_INGESTION_ONLY', 'trading_decision': 'NO_TRADE',
        'backtest_eligible': False, 'execution_authority': False, 'paper_execution_eligible': False,
        'live_enabled': False, 'statistically_validated': False, 'normalized_rows': 0}
    return {'raw.csv': raw, 'settings.json': canonical_bytes(settings), 'evidence.bin': evidence,
            'manifest.json': canonical_bytes(manifest), 'normalized.jsonl': b''}


def stage_export(input_root, csv_name, output_root, settings, *, cutoff, evidence_name=None):
    """Keep original bytes and declared settings; do not guess, map or approve columns."""
    require(type(csv_name) is str and csv_name.lower().endswith('.csv'), 'H38_CSV_EXTENSION')
    require(type(settings) is DukascopySettings, 'H38_DUKASCOPY_SETTINGS')
    require(settings.observed_at <= utc(cutoff), 'H38_OBSERVED_AFTER_CUTOFF')
    raw = read_local(input_root, csv_name, max_bytes=ARCHIVE_LIMIT)
    evidence = b'' if evidence_name is None else read_local(input_root, evidence_name)
    return store_bundle(output_root, _custody_files(raw, settings, evidence, cutoff))


def verify_export(target, *, cutoff):
    """Recompute opaque custody bytes. This never validates columns or provider authenticity."""
    settings = DukascopySettings.from_json(read_local(target, 'settings.json'))
    raw = read_local(target, 'raw.csv', max_bytes=ARCHIVE_LIMIT)
    evidence = read_local(target, 'evidence.bin')
    _verify_bytes(target, _custody_files(raw, settings, evidence, cutoff))
    return settings
