"""Closed, immutable V3.1 metadata contracts. No I/O or execution authority."""
from dataclasses import dataclass, fields
from datetime import datetime, timezone
from decimal import Decimal, localcontext
from enum import Enum
import hashlib
import json
import math
import re


MAX_JSON_BYTES = 131072
DECIMAL_PATTERN = r'-?(?:0|[1-9][0-9]{0,17})(?:\.[0-9]{1,12})?'
ID_PATTERN = r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}'
UNIT_PATTERN = r'[A-Z][A-Z0-9_]{0,15}'


class ContractError(ValueError):
    """Fixed local error code; never includes caller content."""


def require(condition, code):
    if not condition:
        raise ContractError(code)


def identifier(value):
    require(type(value) is str and re.fullmatch(ID_PATTERN, value) is not None, 'IDENTIFIER_INVALID')
    return value


def currency(value):
    require(type(value) is str and re.fullmatch(r'[A-Z]{3}', value) is not None, 'CURRENCY_INVALID')
    return value


def unit(value):
    require(type(value) is str and re.fullmatch(UNIT_PATTERN, value) is not None, 'UNIT_INVALID')
    return value


def shape(value, names):
    require(type(value) is dict and set(value) == set(names), 'FIELDS_INVALID')


def decimal_text(value):
    require(type(value) is Decimal and value.is_finite(), 'DECIMAL_REQUIRED')
    sign, digits, exponent = value.as_tuple()
    require(len(digits) <= 1000, 'DECIMAL_LIMIT')
    if value.is_zero():
        return '0'
    digits = list(digits)
    while digits[-1] == 0:
        digits.pop()
        exponent += 1
    require(len(digits) <= 28 and len(digits) + exponent <= 18 and exponent >= -12, 'DECIMAL_LIMIT')
    # Tuple reconstruction avoids context-dependent rounding by Decimal.normalize().
    return format(Decimal((sign, tuple(digits), exponent)), 'f')


def parse_decimal(value):
    require(type(value) is str and re.fullmatch(DECIMAL_PATTERN, value) is not None, 'DECIMAL_TEXT_REQUIRED')
    result = Decimal(value)
    decimal_text(result)
    return result


def utc(value):
    require(type(value) is datetime and value.tzinfo is not None and value.utcoffset() is not None,
            'AWARE_TIMESTAMP_REQUIRED')
    try:
        return value.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        raise ContractError('TIMESTAMP_INVALID') from None


def instant(value):
    require(type(value) is str and re.fullmatch(
        r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?(?:Z|[+-][0-9]{2}:[0-9]{2})',
        value) is not None, 'TIMESTAMP_INVALID')
    try:
        return utc(datetime.fromisoformat(value.replace('Z', '+00:00')))
    except (ValueError, OverflowError):
        raise ContractError('TIMESTAMP_INVALID') from None


def _json_tree(value, depth=0):
    require(depth <= 32, 'JSON_DEPTH_LIMIT')
    if type(value) is dict:
        require(len(value) <= 4096, 'JSON_COLLECTION_LIMIT')
        for key, item in value.items():
            require(type(key) is str, 'JSON_KEY_INVALID')
            _json_tree(key, depth + 1)
            _json_tree(item, depth + 1)
    elif type(value) is list:
        require(len(value) <= 4096, 'JSON_COLLECTION_LIMIT')
        for item in value:
            _json_tree(item, depth + 1)
    elif type(value) is str:
        require(not any(0xD800 <= ord(c) <= 0xDFFF for c in value), 'JSON_UNICODE_INVALID')
    elif type(value) is float:
        require(math.isfinite(value), 'JSON_NONFINITE')
    else:
        require(value is None or type(value) in (bool, int), 'JSON_TYPE_INVALID')


def strict_json(raw):
    require(type(raw) in (str, bytes), 'JSON_TEXT_REQUIRED')
    try:
        encoded = raw.encode('utf-8') if type(raw) is str else raw
        require(len(encoded) <= MAX_JSON_BYTES, 'JSON_SIZE_LIMIT')

        def pairs(items):
            result = {}
            for key, value in items:
                require(key not in result, 'JSON_DUPLICATE_KEY')
                result[key] = value
            return result

        def nonfinite(_):
            raise ContractError('JSON_NONFINITE')

        value = json.loads(encoded.decode('utf-8'), object_pairs_hook=pairs, parse_constant=nonfinite)
        require(type(value) is dict, 'JSON_OBJECT_REQUIRED')
        _json_tree(value)
        return value
    except ContractError:
        raise
    except (ValueError, UnicodeError, TypeError, RecursionError):
        raise ContractError('JSON_INVALID') from None


def _wire(value, depth=0):
    require(depth <= 32, 'JSON_DEPTH_LIMIT')
    if isinstance(value, Value):
        return _wire(value.to_dict(), depth + 1)
    if isinstance(value, Enum):
        return value.value
    if type(value) is Decimal:
        return decimal_text(value)
    if type(value) is datetime:
        return utc(value).isoformat(timespec='microseconds').replace('+00:00', 'Z')
    if type(value) in (tuple, list):
        return [_wire(item, depth + 1) for item in value]
    if type(value) is dict:
        require(all(type(k) is str for k in value), 'JSON_KEY_INVALID')
        return {k: _wire(v, depth + 1) for k, v in value.items()}
    require(value is None or type(value) in (str, bool, int), 'CANONICAL_TYPE_INVALID')
    return value


def canonical_bytes(value):
    value = _wire(value)
    _json_tree(value)
    encoded = json.dumps(value, sort_keys=True, separators=(',', ':'),
                         ensure_ascii=True, allow_nan=False).encode('utf-8')
    require(len(encoded) <= MAX_JSON_BYTES, 'JSON_SIZE_LIMIT')
    return encoded


def content_hash(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def enum_value(kind, value):
    require(type(value) is str and value in {v.value for v in kind}, 'ENUM_INVALID')
    return kind(value)


class Environment(str, Enum):
    RESEARCH = 'RESEARCH'
    SIMULATION = 'SIMULATION'
    PAPER = 'PAPER'
    LIVE = 'LIVE'


class AssetClass(str, Enum):
    FOREX = 'FOREX'
    EQUITY = 'EQUITY'


class SourceKind(str, Enum):
    SYNTHETIC = 'SYNTHETIC'
    CALLER_UNVERIFIED = 'CALLER_UNVERIFIED'
    AUTHENTIC_CAPTURE = 'AUTHENTIC_CAPTURE'
    HISTORICAL_VERIFIED = 'HISTORICAL_VERIFIED'
    DERIVED = 'DERIVED'


class Value:
    __slots__ = ()

    def to_dict(self):
        return {f.name: _wire(getattr(self, f.name)) for f in fields(self)}

    def to_json(self):
        return canonical_bytes(self).decode('utf-8')

    @classmethod
    def from_json(cls, raw):
        return cls.from_dict(strict_json(raw))


class Versioned(Value):
    __slots__ = ()

    def to_dict(self):
        return dict(schema=self.SCHEMA, schema_version=1, **super().to_dict())

    @classmethod
    def payload(cls, data):
        shape(data, {f.name for f in fields(cls)} | {'schema', 'schema_version'})
        require(data['schema'] == cls.SCHEMA and type(data['schema_version']) is int
                and data['schema_version'] == 1, 'SCHEMA_INCOMPATIBLE')
        return {f.name: data[f.name] for f in fields(cls)}


@dataclass(frozen=True, slots=True)
class Money(Value):
    amount: Decimal
    currency: str

    def __post_init__(self):
        decimal_text(self.amount)
        currency(self.currency)

    @classmethod
    def from_dict(cls, data):
        shape(data, ('amount', 'currency'))
        return cls(parse_decimal(data['amount']), data['currency'])

    def add(self, other):
        require(type(other) is Money, 'MONEY_REQUIRED')
        require(self.currency == other.currency, 'CURRENCY_MISMATCH')
        with localcontext() as arithmetic:
            arithmetic.prec = 60
            return Money(self.amount + other.amount, self.currency)


@dataclass(frozen=True, slots=True)
class Quantity(Value):
    amount: Decimal
    unit: str

    def __post_init__(self):
        decimal_text(self.amount)
        require(self.amount > 0, 'POSITIVE_QUANTITY_REQUIRED')
        unit(self.unit)

    @classmethod
    def from_dict(cls, data):
        shape(data, ('amount', 'unit'))
        return cls(parse_decimal(data['amount']), data['unit'])


@dataclass(frozen=True, slots=True)
class Price(Value):
    amount: Decimal
    currency: str
    per_unit: str

    def __post_init__(self):
        decimal_text(self.amount)
        require(self.amount > 0, 'POSITIVE_PRICE_REQUIRED')
        currency(self.currency)
        unit(self.per_unit)

    @classmethod
    def from_dict(cls, data):
        shape(data, ('amount', 'currency', 'per_unit'))
        return cls(parse_decimal(data['amount']), data['currency'], data['per_unit'])


@dataclass(frozen=True, slots=True)
class EvidenceRef(Value):
    evidence_id: str
    source_kind: SourceKind
    environment: Environment
    content_sha256: str | None
    observed_at: datetime | None
    valid_until: datetime | None

    def __post_init__(self):
        identifier(self.evidence_id)
        require(type(self.source_kind) is SourceKind and type(self.environment) is Environment, 'ENUM_REQUIRED')
        require(self.content_sha256 is None or (type(self.content_sha256) is str
                and re.fullmatch(r'[a-f0-9]{64}', self.content_sha256) is not None), 'HASH_INVALID')
        require((self.observed_at is None) == (self.valid_until is None), 'EVIDENCE_TIME_PAIR_REQUIRED')
        if self.observed_at is not None:
            object.__setattr__(self, 'observed_at', utc(self.observed_at))
            object.__setattr__(self, 'valid_until', utc(self.valid_until))
            require(self.observed_at < self.valid_until, 'EVIDENCE_TIME_INVALID')

    def require_current(self, now):
        """Checks time only; does not authenticate a source or grant permission."""
        now = utc(now)
        require(self.observed_at is not None, 'EVIDENCE_TIME_UNKNOWN')
        require(self.observed_at <= now < self.valid_until, 'EVIDENCE_NOT_CURRENT')

    @classmethod
    def from_dict(cls, data):
        shape(data, (f.name for f in fields(cls)))
        return cls(data['evidence_id'], enum_value(SourceKind, data['source_kind']),
                   enum_value(Environment, data['environment']), data['content_sha256'],
                   None if data['observed_at'] is None else instant(data['observed_at']),
                   None if data['valid_until'] is None else instant(data['valid_until']))


@dataclass(frozen=True, slots=True)
class Instrument(Versioned):
    SCHEMA = 'trading.core_v3.instrument'

    instrument_id: str
    specification_version: int
    asset_class: AssetClass
    symbol: str
    base_currency: str | None
    quote_currency: str
    quantity_unit: str
    multiplier: Decimal
    tick: Price
    minimum_quantity: Quantity
    quantity_step: Quantity
    calendar_id: str

    def __post_init__(self):
        identifier(self.instrument_id)
        identifier(self.calendar_id)
        require(type(self.specification_version) is int and 1 <= self.specification_version <= 2147483647,
                'SPECIFICATION_VERSION_INVALID')
        require(type(self.asset_class) is AssetClass, 'ASSET_CLASS_REQUIRED')
        require(type(self.symbol) is str and re.fullmatch(r'[A-Z0-9][A-Z0-9./_-]{0,31}', self.symbol)
                is not None, 'SYMBOL_INVALID')
        currency(self.quote_currency)
        unit(self.quantity_unit)
        if self.asset_class is AssetClass.FOREX:
            currency(self.base_currency)
            require(self.base_currency != self.quote_currency, 'CURRENCY_PAIR_INVALID')
        else:
            require(self.base_currency is None, 'EQUITY_BASE_CURRENCY_NOT_APPLICABLE')
        decimal_text(self.multiplier)
        require(self.multiplier > 0, 'POSITIVE_MULTIPLIER_REQUIRED')
        require(type(self.tick) is Price and type(self.minimum_quantity) is Quantity
                and type(self.quantity_step) is Quantity, 'INSTRUMENT_TERMS_REQUIRED')
        require(self.minimum_quantity.unit == self.quantity_step.unit == self.quantity_unit
                and self.tick.per_unit == self.quantity_unit, 'UNIT_MISMATCH')
        require(self.tick.currency == self.quote_currency, 'CURRENCY_MISMATCH')

    def check_terms(self, quantity, price):
        """Unit/grid compatibility only. Never an economic or execution approval."""
        require(type(quantity) is Quantity and type(price) is Price, 'TYPED_TERMS_REQUIRED')
        require(quantity.unit == price.per_unit == self.quantity_unit, 'UNIT_MISMATCH')
        require(price.currency == self.quote_currency, 'CURRENCY_MISMATCH')
        with localcontext() as arithmetic:
            arithmetic.prec = 60
            require(quantity.amount >= self.minimum_quantity.amount and
                    (quantity.amount - self.minimum_quantity.amount) % self.quantity_step.amount == 0,
                    'QUANTITY_GRID_MISMATCH')
            require(price.amount % self.tick.amount == 0, 'PRICE_TICK_MISMATCH')

    @classmethod
    def from_dict(cls, data):
        values = cls.payload(data)
        values['asset_class'] = enum_value(AssetClass, values['asset_class'])
        values['multiplier'] = parse_decimal(values['multiplier'])
        values['tick'] = Price.from_dict(values['tick'])
        values['minimum_quantity'] = Quantity.from_dict(values['minimum_quantity'])
        values['quantity_step'] = Quantity.from_dict(values['quantity_step'])
        return cls(**values)
