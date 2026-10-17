"""Pure R20 V2 accounting and daily limits. No I/O or order authority."""
from dataclasses import asdict, dataclass, fields, replace
from datetime import datetime
from decimal import Decimal, localcontext
from functools import wraps
import re

from .r20_profiles import decimal_text, digest, economic_day, encoded, number, strict_json, utc

ZERO = Decimal(0)


def exact(fn):
    @wraps(fn)
    def call(*args, **kwargs):
        with localcontext() as ctx:
            ctx.prec=96
            return fn(*args, **kwargs)
    return call


def signed(value):
    if not isinstance(value,Decimal) or not value.is_finite(): raise ValueError('FINITE_DECIMAL_REQUIRED')
    if len(value.as_tuple().digits)>96 or abs(value.as_tuple().exponent)>96:
        raise ValueError('DECIMAL_PRECISION_LIMIT')
    return value


def identity(value):
    if not isinstance(value,str) or not re.fullmatch('[a-zA-Z0-9_-]{1,100}',value):
        raise ValueError('IDENTITY_REQUIRED')


def unique(values):
    if len(set(values))!=len(values): raise ValueError('DUPLICATE_IDENTITY')


@dataclass(frozen=True)
class Cost:
    cost_id: str
    amount: Decimal
    status: str
    provenance: str
    evidence: str

    def __post_init__(self):
        identity(self.cost_id); number(self.amount)
        if self.status not in ('SETTLED','ACCRUED','RESERVED'): raise ValueError('COST_STATUS_REQUIRED')
        if self.provenance not in ('ESTIMATED','MODELED','BROKER_CONFIRMED'): raise ValueError('COST_PROVENANCE_REQUIRED')
        if self.provenance=='ESTIMATED' and self.status!='RESERVED': raise ValueError('ESTIMATE_NOT_SETTLED')
        if not isinstance(self.evidence,str) or not self.evidence.strip(): raise ValueError('COST_EVIDENCE_REQUIRED')


@dataclass(frozen=True)
class Equity:
    cash: Decimal
    open_pnl: Decimal
    accrued: Decimal
    reserved: Decimal
    economic: Decimal

    @exact
    def eligible(self, *, pending=ZERO, cap=None):
        number(pending)
        if cap is not None: number(cap,positive=True)
        available=max(ZERO,self.economic-pending)
        return available if cap is None else min(available,cap)


@exact
def equity(initial, realized_gross, open_gross, costs):
    number(initial,positive=True); signed(realized_gross)
    unique([c.cost_id for c in costs])
    pnl=sum((signed(p) for p in open_gross),ZERO)
    totals={s:sum((c.amount for c in costs if c.status==s),ZERO) for s in ('SETTLED','ACCRUED','RESERVED')}
    cash=initial+realized_gross-totals['SETTLED']
    return Equity(cash,pnl,totals['ACCRUED'],totals['RESERVED'],
                  cash+pnl-totals['ACCRUED']-totals['RESERVED'])


@dataclass(frozen=True)
class OpenRisk:
    position_id: str
    current_net: Decimal
    stressed_net: Decimal

    def __post_init__(self):
        identity(self.position_id); signed(self.current_net); signed(self.stressed_net)

    @property
    @exact
    def additional(self): return max(ZERO,self.current_net-self.stressed_net)


@dataclass(frozen=True)
class PendingRisk:
    position_id: str
    total_loss: Decimal

    def __post_init__(self): identity(self.position_id); number(self.total_loss)


@dataclass(frozen=True)
class DailyState:
    scope_id: str
    day_id: str
    at: datetime
    reference: Decimal
    eligible_base: Decimal
    budget: Decimal
    current_equity: Decimal
    profile_version: int
    profile_hash: str
    loss_blocked: bool
    operational_blocks: tuple[str, ...]
    open_terms: tuple[OpenRisk, ...]
    pending_terms: tuple[PendingRisk, ...]
    inventory_verified: bool
    entry_profile_valid: bool = True

    def __post_init__(self):
        identity(self.scope_id); object.__setattr__(self,'at',utc(self.at))
        if self.day_id!=economic_day(self.at)[0]: raise ValueError('DAY_MISMATCH')
        signed(self.reference); signed(self.current_equity)
        number(self.eligible_base); number(self.budget)
        if self.budget>self.eligible_base or self.eligible_base>max(ZERO,self.reference): raise ValueError('DAILY_BUDGET_INVALID')
        if type(self.profile_version) is not int or self.profile_version<1: raise ValueError('PROFILE_VERSION_INVALID')
        if not isinstance(self.profile_hash,str) or not re.fullmatch('[a-f0-9]{64}',self.profile_hash): raise ValueError('PROFILE_HASH_REQUIRED')
        if any(type(x) is not bool for x in (self.loss_blocked,self.inventory_verified,self.entry_profile_valid)):
            raise ValueError('BOOLEAN_REQUIRED')
        for name in ('operational_blocks','open_terms','pending_terms'):
            if not isinstance(getattr(self,name),tuple): raise ValueError('IMMUTABLE_TUPLE_REQUIRED')
        for block in self.operational_blocks: identity(block)
        unique(self.operational_blocks)
        if any(not isinstance(p,OpenRisk) for p in self.open_terms) or any(not isinstance(p,PendingRisk) for p in self.pending_terms):
            raise ValueError('RISK_TERM_REQUIRED')
        unique([p.position_id for p in self.open_terms+self.pending_terms])
        if self.used_loss>=self.budget and not self.loss_blocked: raise ValueError('LOSS_LATCH_REQUIRED')

    @classmethod
    @exact
    def begin(cls,profile,reference,at,*,boundary_verified,operational_blocks=()):
        if boundary_verified is not True or not profile.valid_at(at): raise ValueError('DAY_BOUNDARY_UNVERIFIED')
        signed(reference)
        base=max(ZERO,reference)
        if profile.equity_cap_usd is not None: base=min(base,profile.equity_cap_usd)
        return cls(profile.scope_id,economic_day(at)[0],at,reference,base,
                   base*profile.daily_loss_limit_pct/100,reference,
                   profile.configuration_version,profile.configuration_hash,base==0,
                   operational_blocks,(),(),False)

    @property
    @exact
    def used_loss(self): return max(ZERO,self.reference-self.current_equity)

    @property
    @exact
    def open_risk(self): return sum((p.additional for p in self.open_terms),ZERO)

    @property
    @exact
    def pending_risk(self): return sum((p.total_loss for p in self.pending_terms),ZERO)

    @property
    @exact
    def remaining(self): return max(ZERO,self.budget-self.used_loss-self.open_risk-self.pending_risk)

    @exact
    def can_enter(self,candidate_loss):
        number(candidate_loss)
        return (self.inventory_verified and self.entry_profile_valid and not self.loss_blocked
                and not self.operational_blocks
                and self.used_loss+self.open_risk+self.pending_risk+candidate_loss<=self.budget)

    @exact
    def observe(self,profile,at,current_equity,open_terms,pending_terms):
        at=utc(at); signed(current_equity)
        if at<self.at or economic_day(at)[0]!=self.day_id: raise ValueError('DAILY_CLOCK_INVALID')
        if profile.scope_id!=self.scope_id: raise ValueError('PROFILE_NOT_APPLICABLE')
        if not profile.valid_at(at) and profile.configuration_hash!=self.profile_hash:
            raise ValueError('PROFILE_NOT_APPLICABLE')
        if profile.configuration_version<self.profile_version: raise ValueError('PROFILE_VERSION_REGRESSION')
        if profile.configuration_version==self.profile_version and profile.configuration_hash!=self.profile_hash:
            raise ValueError('PROFILE_VERSION_REUSED')
        budget=min(self.budget,self.eligible_base*profile.daily_loss_limit_pct/100)
        return replace(self,at=at,current_equity=current_equity,budget=budget,
                       profile_version=profile.configuration_version,profile_hash=profile.configuration_hash,
                       loss_blocked=self.loss_blocked or max(ZERO,self.reference-current_equity)>=budget,
                       open_terms=open_terms,pending_terms=pending_terms,inventory_verified=True,
                       entry_profile_valid=profile.valid_at(at))

    def next_day(self,profile,reference,at,*,boundary_verified):
        if profile.scope_id!=self.scope_id or economic_day(at)[0]<=self.day_id or utc(at)<=self.at:
            raise ValueError('NEXT_DAY_INVALID')
        if profile.configuration_version<=self.profile_version: raise ValueError('PROFILE_VERSION_REGRESSION')
        # New inventory must be revalued before admission; old global blocks carry over.
        new=self.begin(profile,reference,at,boundary_verified=boundary_verified,
                       operational_blocks=self.operational_blocks)
        return replace(new,open_terms=self.open_terms,pending_terms=self.pending_terms)

    @exact
    def management_day(self,profile,reference,at,*,boundary_verified):
        """Expired profile is retained for management, never activated for entry.

        A verified boundary resets ONLY the economic-day loss reference. The last
        daily percentage bounds management reporting until a new explicit profile;
        operational blocks and inventory survive. Admission remains disabled.
        """
        at=utc(at);signed(reference)
        if (type(boundary_verified) is not bool or profile.configuration_hash!=self.profile_hash
            or profile.valid_at(at) or economic_day(at)[0]<=self.day_id or at<=self.at):
            raise ValueError('MANAGEMENT_BOUNDARY_INVALID')
        if not boundary_verified:
            blocks=tuple(dict.fromkeys(self.operational_blocks+('ECONOMIC_BOUNDARY_UNVERIFIED',)))
            return replace(self,day_id=economic_day(at)[0],at=at,inventory_verified=False,
                           entry_profile_valid=False,operational_blocks=blocks)
        base=max(ZERO,reference)
        if profile.equity_cap_usd is not None:base=min(base,profile.equity_cap_usd)
        return replace(self,day_id=economic_day(at)[0],at=at,reference=reference,
            eligible_base=base,budget=base*profile.daily_loss_limit_pct/100,
            current_equity=reference,loss_blocked=base==0,inventory_verified=False,
            entry_profile_valid=False)

    def to_json(self):
        obj=asdict(self)
        return encoded(dict(obj,state_hash=digest(obj)))

    @classmethod
    def from_json(cls,text):
        obj=strict_json(text)
        if not isinstance(obj,dict) or set(obj)!={f.name for f in fields(cls)}|{'state_hash'}: raise ValueError('DAILY_FIELDS_INVALID')
        expected=obj.pop('state_hash')
        if digest(obj)!=expected: raise ValueError('DAILY_HASH_MISMATCH')
        for name,keys in [('open_terms',{'position_id','current_net','stressed_net'}),
                          ('pending_terms',{'position_id','total_loss'})]:
            if not isinstance(obj[name],list) or any(not isinstance(x,dict) or set(x)!=keys for x in obj[name]):
                raise ValueError('RISK_TERM_FIELDS_INVALID')
        if not isinstance(obj['operational_blocks'],list): raise ValueError('BLOCKS_LIST_REQUIRED')
        for name in ('reference','eligible_base','budget','current_equity'): obj[name]=decimal_text(obj[name])
        obj['at']=datetime.fromisoformat(obj['at'])
        obj['operational_blocks']=tuple(obj['operational_blocks'])
        obj['open_terms']=tuple(OpenRisk(x['position_id'],decimal_text(x['current_net']),decimal_text(x['stressed_net'])) for x in obj['open_terms'])
        obj['pending_terms']=tuple(PendingRisk(x['position_id'],decimal_text(x['total_loss'])) for x in obj['pending_terms'])
        return cls(**obj)
