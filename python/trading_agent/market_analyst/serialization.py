"""Closed, bounded V1 documents; parsing never authenticates a source."""
from dataclasses import fields
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import re
import types
from typing import get_args, get_origin, get_type_hints

MAX_JSON_BYTES = 131072


class AnalystError(ValueError):
    """Fixed codes only; no input contents in errors."""


def require(condition, code):
    if not condition:
        raise AnalystError(code)


def utc(value):
    require(type(value) is datetime and value.tzinfo is not None
            and value.utcoffset() == timedelta(0), 'MA_UTC_REQUIRED')
    return value.astimezone(timezone.utc)


def decimal_text(value):
    require(type(value) is Decimal and value.is_finite(), 'MA_DECIMAL_REQUIRED')
    require(len(value.as_tuple().digits) <= 64 and -40 <= value.as_tuple().exponent <= 12
            and value.copy_abs() <= Decimal('1e12'), 'MA_DECIMAL_RANGE')
    if not value:
        return '0'
    text = format(value, 'f')
    return text.rstrip('0').rstrip('.') if '.' in text else text


def identifier(value):
    require(type(value) is str and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:/-]{0,95}', value)
            is not None, 'MA_IDENTIFIER')


def hash_text(value):
    require(type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None,
            'MA_HASH')


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode('ascii')).hexdigest()


def _check(value, annotation):
    origin, args = get_origin(annotation), get_args(annotation)
    if origin is types.UnionType:
        for option in args:
            try:
                _check(value, option)
                return
            except AnalystError:
                continue
        raise AnalystError('MA_TYPE')
    if origin is tuple:
        require(type(value) is tuple and len(value) <= 4096, 'MA_COLLECTION')
        for item in value:
            _check(item, args[0])
        return
    require(type(value) is annotation, 'MA_TYPE')
    if annotation is Decimal:
        decimal_text(value)
    elif annotation is datetime:
        utc(value)
    elif annotation is str:
        require(len(value) <= 256, 'MA_TEXT_LIMIT')


def _encode(value):
    if isinstance(value, Record):
        return value.to_dict()
    if type(value) is tuple:
        return [_encode(v) for v in value]
    if type(value) is Decimal:
        return decimal_text(value)
    if type(value) is datetime:
        return utc(value).isoformat()
    return value


def _decode(value, annotation):
    origin, args = get_origin(annotation), get_args(annotation)
    if origin is types.UnionType:
        for option in args:
            try:
                return _decode(value, option)
            except AnalystError:
                continue
        raise AnalystError('MA_TYPE')
    if origin is tuple:
        require(type(value) is list and len(value) <= 4096, 'MA_COLLECTION')
        return tuple(_decode(v, args[0]) for v in value)
    if isinstance(annotation, type) and issubclass(annotation, Record):
        return annotation.from_dict(value)
    if annotation is Decimal:
        require(type(value) is str and len(value) <= 80
                and re.fullmatch(r'-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?', value), 'MA_DECIMAL_TEXT')
        value = Decimal(value)
    elif annotation is datetime:
        require(type(value) is str and len(value) <= 40
                and value.endswith(('+00:00', 'Z')),
                'MA_UTC_REQUIRED')
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            raise AnalystError('MA_UTC_REQUIRED') from None
    _check(value, annotation)
    return value


class Record:
    __slots__ = ()

    def __post_init__(self):
        hints = get_type_hints(type(self))
        for field in fields(self):
            _check(getattr(self, field.name), hints[field.name])

    def to_dict(self):
        return {'schema': 'trading.market_analyst.' + type(self).__name__, 'schema_version': 1,
                **{f.name: _encode(getattr(self, f.name)) for f in fields(self)}}

    def to_json(self):
        text = canonical(self.to_dict())
        require(len(text.encode('ascii')) <= MAX_JSON_BYTES, 'MA_DOCUMENT_LIMIT')
        return text

    def sha256(self):
        return hashlib.sha256(self.to_json().encode('ascii')).hexdigest()

    @classmethod
    def from_dict(cls, value):
        expected = {f.name for f in fields(cls)} | {'schema', 'schema_version'}
        require(type(value) is dict and set(value) == expected, 'MA_FIELDS')
        require(value['schema'] == 'trading.market_analyst.' + cls.__name__
                and type(value['schema_version']) is int and value['schema_version'] == 1,
                'MA_SCHEMA')
        hints = get_type_hints(cls)
        return cls(**{f.name: _decode(value[f.name], hints[f.name]) for f in fields(cls)})

    @classmethod
    def from_json(cls, raw):
        require(type(raw) is str and len(raw) <= MAX_JSON_BYTES, 'MA_DOCUMENT_LIMIT')
        try:
            require(len(raw.encode('utf-8')) <= MAX_JSON_BYTES, 'MA_DOCUMENT_LIMIT')
        except UnicodeEncodeError:
            raise AnalystError('MA_JSON_ENCODING') from None

        def pairs(items):
            result = {}
            for key, value in items:
                require(key not in result, 'MA_DUPLICATE_JSON_KEY')
                result[key] = value
            return result

        def constant(_):
            raise AnalystError('MA_JSON_NUMBER')

        try:
            value = json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
            return cls.from_dict(value)
        except (ValueError, TypeError, RecursionError) as exc:
            if isinstance(exc, AnalystError):
                raise
            raise AnalystError('MA_JSON') from None
