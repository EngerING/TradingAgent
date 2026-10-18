"""Read-only imports of caller-supplied JSON; never reads a journal or refreshes data.

Source hashes identify content, not authenticity. These records intentionally do
not implement StrategyVersion or the future V3 economic gate.
"""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
import hashlib

from .contracts import (
    AssetClass, ContractError, Environment, EvidenceRef, Instrument, Money, Price,
    Quantity, SourceKind, Value, canonical_bytes, instant, parse_decimal, require,
    shape, strict_json, utc,
)
from ..ai_strategy_researcher.strategy_bundle_v2 import validate_bundle
from ..forex_research.economics import CONTEXT_FIELDS, COST_FIELDS, PLAN_FIELDS, assess


def _text(raw):
    require(type(raw) in (str, bytes), 'LEGACY_JSON_REQUIRED')
    try:
        value = raw.decode('utf-8') if type(raw) is bytes else raw
        require(len(value.encode('utf-8')) <= 32768, 'LEGACY_SIZE_LIMIT')
        return value
    except UnicodeError:
        raise ContractError('LEGACY_ENCODING_INVALID') from None


def _raw_hash(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _source_value(raw):
    # Historical loaders accept UTF-8 BOM. Strip it only for parsing, not hashing/storage.
    return strict_json(_text(raw).removeprefix('\ufeff'))


def _forex_instrument(instrument):
    require(type(instrument) is Instrument, 'INSTRUMENT_REQUIRED')
    require(instrument.asset_class is AssetClass.FOREX and instrument.symbol == 'EUR/USD'
            and instrument.base_currency == 'EUR' and instrument.quote_currency == 'USD'
            and instrument.quantity_unit == 'EUR' and instrument.multiplier == Decimal('1'),
            'LEGACY_INSTRUMENT_MISMATCH')


def _no_authority(value):
    for name in ('execution_authority', 'paper_execution_eligible', 'live_enabled'):
        require(value.get(name) is False, 'LEGACY_AUTHORITY_FORBIDDEN')
    require(value.get('trading_decision') == 'NO_TRADE', 'LEGACY_AUTHORITY_FORBIDDEN')


def _bundle(raw):
    value = _source_value(raw)
    _no_authority(value)
    require(value.get('backtested') is False and value.get('rules_compiled') is False,
            'LEGACY_VALIDATION_FLAGS_INVALID')
    try:
        validate_bundle(value)
    except (ValueError, TypeError, KeyError, OverflowError):
        raise ContractError('LEGACY_BUNDLE_INVALID') from None
    return value


def _authority_fields():
    return dict(environment='RESEARCH', scope='HISTORICAL_RESEARCH_ONLY',
                economically_approved=False, execution_authority=False,
                paper_execution_eligible=False, live_enabled=False, trading_decision='NO_TRADE')


def _verify_wire(data, result):
    shape(data, result.to_dict())
    require(type(data['schema_version']) is int and data['schema_version'] == 1
            and data['schema'] == result.SCHEMA, 'SCHEMA_INCOMPATIBLE')
    # JSON byte comparison also rejects 0/False or 1/True substitutions.
    require(canonical_bytes(data) == canonical_bytes(result), 'IMPORTED_FIELDS_MISMATCH')
    return result


@dataclass(frozen=True, slots=True)
class ImportedStrategy(Value):
    SCHEMA = 'trading.core_v3.imported_strategy'

    instrument: Instrument
    original_json: str

    def __post_init__(self):
        _forex_instrument(self.instrument)
        require(type(self.original_json) is str, 'LEGACY_JSON_REQUIRED')
        _bundle(self.original_json)

    def original_value(self):
        """Returns a detached inspection copy, not mutable contract state."""
        return _source_value(self.original_json)

    @property
    def direction(self):
        return self.original_value()['candidate']['direction']

    @property
    def timeframe_minutes(self):
        return {'15M': 15, '1H': 60, '4H': 240}[self.original_value()['candidate']['timeframe']]

    @property
    def provenance(self):
        raw_hash = _raw_hash(self.original_json)
        return EvidenceRef('legacy-' + raw_hash[:24], SourceKind.CALLER_UNVERIFIED,
                           Environment.RESEARCH, raw_hash, None, None)

    def to_dict(self):
        value = self.original_value()
        candidate = value['candidate']
        return dict(schema=self.SCHEMA, schema_version=1, instrument=self.instrument.to_dict(),
                    original_schema=value['schema'], original_json=self.original_json,
                    original_sha256=_raw_hash(self.original_json),
                    original_hashes={name: value[name] for name in
                                     ('candidate_sha256', 'rules_sha256', 'bundle_sha256')},
                    strategy_id=candidate['strategy_id'], strategy_version=candidate['version'],
                    direction=self.direction, timeframe_minutes=self.timeframe_minutes,
                    risk_profile=candidate['risk_profile'],
                    research_capital=Money(Decimal(candidate['research_capital_usd']), 'USD').to_dict(),
                    provenance=self.provenance.to_dict(), statistically_validated=None,
                    backtested=False, **_authority_fields())

    @classmethod
    def from_dict(cls, data):
        require(type(data) is dict and 'instrument' in data and 'original_json' in data, 'FIELDS_INVALID')
        result = cls(Instrument.from_dict(data['instrument']), data['original_json'])
        return _verify_wire(data, result)


def _assessment(original_json, context_json, plan_json, assessed_at, instrument):
    value = _source_value(original_json)
    context, plan = _source_value(context_json), _source_value(plan_json)
    _no_authority(value)
    require(value.get('schema') == 'FOREX_ECONOMIC_ASSESSMENT_V1', 'LEGACY_SCHEMA_INCOMPATIBLE')
    require(type(value.get('admitted')) is bool and value.get('statistically_validated') is False
            and value.get('broker_executability_verified') is False, 'LEGACY_VALIDATION_FLAGS_INVALID')
    shape(context, CONTEXT_FIELDS)
    shape(plan, PLAN_FIELDS)
    shape(context['costs'], COST_FIELDS)
    require(context['schema'] == 'FOREX_ECONOMIC_CONTEXT_V1' and plan['schema'] == 'FOREX_ECONOMIC_PLAN_V1',
            'LEGACY_SCHEMA_INCOMPATIBLE')
    require(context['source'] in ('SYNTHETIC_TEST_ONLY', 'CALLER_SUPPLIED_UNVERIFIED'),
            'LEGACY_SOURCE_UNSUPPORTED')
    expected = assess(context, plan, now=assessed_at)
    # Validate against the original pure implementation at the original cutoff.
    # This is consistency checking, not a new gate or a current economic approval.
    require(value == expected, 'LEGACY_ASSESSMENT_MISMATCH')
    require(instrument.minimum_quantity.amount == parse_decimal(context['minimum_quantity_eur'])
            and instrument.quantity_step.amount == parse_decimal(context['quantity_step_eur']),
            'LEGACY_INSTRUMENT_MISMATCH')
    quantity = Quantity(parse_decimal(plan['quantity_eur']), 'EUR')
    for name in ('entry_mid_usd_per_eur', 'stop_mid_usd_per_eur', 'target_mid_usd_per_eur'):
        instrument.check_terms(quantity, Price(parse_decimal(plan[name]), 'USD', 'EUR'))
    return value, context


@dataclass(frozen=True, slots=True)
class ImportedEconomicAssessment(Value):
    SCHEMA = 'trading.core_v3.imported_economic_assessment'

    instrument: Instrument
    original_json: str
    context_json: str
    plan_json: str
    assessed_at: datetime

    def __post_init__(self):
        _forex_instrument(self.instrument)
        require(all(type(text) is str for text in (self.original_json, self.context_json, self.plan_json)),
                'LEGACY_JSON_REQUIRED')
        object.__setattr__(self, 'assessed_at', utc(self.assessed_at))
        _assessment(self.original_json, self.context_json, self.plan_json, self.assessed_at, self.instrument)
        # Even a rejected historical assessment needs usable source-time metadata to import.
        self.provenance

    def original_value(self):
        return _source_value(self.original_json)

    @property
    def source_admitted(self):
        return self.original_value()['admitted']

    @property
    def provenance(self):
        context = _source_value(self.context_json)
        kind = SourceKind.SYNTHETIC if context['source'] == 'SYNTHETIC_TEST_ONLY' else SourceKind.CALLER_UNVERIFIED
        return EvidenceRef(context['evidence_id'], kind, Environment.RESEARCH, _raw_hash(self.context_json),
                           instant(context['observed_at']), instant(context['valid_until']))

    def to_dict(self):
        value = self.original_value()
        return dict(schema=self.SCHEMA, schema_version=1, instrument=self.instrument.to_dict(),
                    original_schema=value['schema'], original_json=self.original_json,
                    context_json=self.context_json, plan_json=self.plan_json,
                    assessed_at=utc(self.assessed_at).isoformat(timespec='microseconds').replace('+00:00', 'Z'),
                    original_sha256=_raw_hash(self.original_json),
                    context_sha256=_raw_hash(self.context_json), plan_sha256=_raw_hash(self.plan_json),
                    original_hashes=dict(input_sha256=value['input_sha256']),
                    provenance=self.provenance.to_dict(), source_admitted=self.source_admitted,
                    source_scope=value['scope'], statistically_validated=value['statistically_validated'],
                    broker_executability_verified=value['broker_executability_verified'], **_authority_fields())

    @classmethod
    def from_dict(cls, data):
        require(type(data) is dict and {'instrument', 'original_json', 'context_json', 'plan_json', 'assessed_at'} <= set(data),
                'FIELDS_INVALID')
        result = cls(Instrument.from_dict(data['instrument']), data['original_json'], data['context_json'],
                     data['plan_json'], instant(data['assessed_at']))
        return _verify_wire(data, result)


def import_forex_bundle(raw, *, instrument=None):
    return ImportedStrategy(instrument, _text(raw))


def import_forex_assessment(raw, *, context_json=None, plan_json=None, assessed_at=None, instrument=None):
    return ImportedEconomicAssessment(instrument, _text(raw), _text(context_json), _text(plan_json), assessed_at)
