"""Immutable R20 V2 configuration contracts. No activation, storage or execution."""
from dataclasses import asdict, dataclass, fields
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import re
from zoneinfo import ZoneInfo

ZONE = 'America/Santo_Domingo'


def number(value, *, minimum=Decimal(0), positive=False):
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError('FINITE_DECIMAL_REQUIRED')
    if value < minimum or (positive and value == minimum):
        raise ValueError('NUMBER_OUT_OF_RANGE')
    # Bound precision/scale so canonicalization and arithmetic cannot exhaust resources.
    if len(value.as_tuple().digits) > 96 or abs(value.as_tuple().exponent) > 96:
        raise ValueError('DECIMAL_PRECISION_LIMIT')
    return value


def utc(value):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('AWARE_TIMESTAMP_REQUIRED')
    return value.astimezone(timezone.utc)


def economic_day(at):
    date = utc(at).astimezone(ZoneInfo(ZONE)).date()
    start = datetime.combine(date, time(), ZoneInfo(ZONE))
    end = datetime.combine(date+timedelta(days=1), time(), ZoneInfo(ZONE))
    return date.isoformat(), utc(start), utc(end)


def canonical(value):
    if isinstance(value, Decimal):
        if not value.is_finite(): raise ValueError('FINITE_DECIMAL_REQUIRED')
        text = format(value, 'f')
        return (text.rstrip('0').rstrip('.') if '.' in text else text) if value else '0'
    if isinstance(value, datetime): return utc(value).isoformat(timespec='microseconds').replace('+00:00','Z')
    if isinstance(value, dict): return {k:canonical(v) for k,v in value.items()}
    if isinstance(value, (list, tuple)): return [canonical(v) for v in value]
    return value


def encoded(value):
    return json.dumps(canonical(value), sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value): return hashlib.sha256(encoded(value).encode('utf-8')).hexdigest()


def strict_json(text):
    def pairs(items):
        obj={}
        for key,value in items:
            if key in obj: raise ValueError('DUPLICATE_JSON_KEY')
            obj[key]=value
        return obj
    if not isinstance(text,str) or len(text)>1_000_000: raise ValueError('JSON_SIZE_LIMIT')
    return json.loads(text,object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('NONFINITE_JSON')))


def decimal_text(value):
    if not isinstance(value,str) or not re.fullmatch(r'-?\d{1,96}(?:\.\d{1,96})?', value):
        raise ValueError('DECIMAL_STRING_REQUIRED')
    result=Decimal(value)
    if len(result.as_tuple().digits)>96: raise ValueError('DECIMAL_PRECISION_LIMIT')
    return result


@dataclass(frozen=True)
class EconomicProfile:
    configuration_version: int
    scope_id: str
    capital_base_usd: Decimal
    equity_cap_usd: Decimal | None
    risk_per_trade_pct: Decimal
    capital_allocation_pct: Decimal
    max_leverage: Decimal
    daily_loss_limit_pct: Decimal
    max_open_positions: int
    effective_from: datetime
    effective_until: datetime
    created_at: datetime
    cost_policy_hash: str
    operational_policy_hash: str
    economic_timezone: str = ZONE

    def __post_init__(self):
        for name in ('configuration_version','max_open_positions'):
            value=getattr(self,name)
            if type(value) is not int or not 0<value<=1_000_000: raise ValueError('POSITIVE_INTEGER_REQUIRED')
        if not isinstance(self.scope_id,str) or not re.fullmatch(r'r20-v2-[a-zA-Z0-9_-]{1,80}',self.scope_id):
            raise ValueError('V2_SCOPE_REQUIRED')
        number(self.capital_base_usd,positive=True)
        if self.equity_cap_usd is not None: number(self.equity_cap_usd,positive=True)
        for name in ('risk_per_trade_pct','capital_allocation_pct','daily_loss_limit_pct'):
            if number(getattr(self,name),positive=True)>100: raise ValueError('PERCENT_OUT_OF_RANGE')
        number(self.max_leverage,minimum=Decimal(1))
        for name in ('cost_policy_hash','operational_policy_hash'):
            if not isinstance(getattr(self,name),str) or not re.fullmatch('[a-f0-9]{64}',getattr(self,name)):
                raise ValueError('POLICY_HASH_REQUIRED')
        if self.economic_timezone!=ZONE: raise ValueError('ECONOMIC_TIMEZONE_REQUIRED')
        for name in ('effective_from','effective_until','created_at'):
            object.__setattr__(self,name,utc(getattr(self,name)))
        if not self.created_at<=self.effective_from<self.effective_until<=economic_day(self.effective_from)[2]:
            raise ValueError('PROFILE_INTERVAL_INVALID')

    @property
    def configuration_hash(self): return digest(asdict(self))

    def valid_at(self, at): return self.effective_from<=utc(at)<self.effective_until

    def to_json(self):
        return encoded(dict(asdict(self),configuration_hash=self.configuration_hash))

    @classmethod
    def from_json(cls,text):
        obj=strict_json(text)
        names={f.name for f in fields(cls)}
        if not isinstance(obj,dict) or set(obj)!=names|{'configuration_hash'}: raise ValueError('PROFILE_FIELDS_INVALID')
        expected=obj.pop('configuration_hash')
        for name in ('capital_base_usd','equity_cap_usd','risk_per_trade_pct','capital_allocation_pct','max_leverage','daily_loss_limit_pct'):
            if name=='equity_cap_usd' and obj[name] is None: continue
            obj[name]=decimal_text(obj[name])
        for name in ('effective_from','effective_until','created_at'):
            if not isinstance(obj[name],str): raise ValueError('TIMESTAMP_STRING_REQUIRED')
            obj[name]=datetime.fromisoformat(obj[name])
        result=cls(**obj)
        if result.configuration_hash!=expected: raise ValueError('PROFILE_HASH_MISMATCH')
        return result
