"""Versioned cost evidence proposal. Estimates never imply broker confirmation."""
from dataclasses import dataclass,asdict
from decimal import Decimal
from .r20_profiles import decimal_text,digest,encoded,strict_json,number


@dataclass(frozen=True)
class CostEvidence:
    component:str
    status:str
    assumption:str|None
    unit:str
    evidence:str
    limitations:tuple[str,...]

    def __post_init__(self):
        if self.component not in ('commission','spread','slippage','financing'):raise ValueError('COST_COMPONENT')
        if self.status not in ('PUBLISHED_ESTIMATE','OBSERVED_WITH_ASSUMPTION','UNBOUNDED_ASSUMPTION','UNKNOWN','EVIDENCE_BOUND'):
            raise ValueError('COST_STATUS')
        if self.assumption is not None:number(decimal_text(self.assumption))
        if not self.evidence or not isinstance(self.limitations,tuple) or not self.limitations:raise ValueError('EVIDENCE_AND_LIMITATIONS_REQUIRED')
        if self.status!='UNKNOWN' and self.assumption is None:raise ValueError('ESTIMATE_REQUIRED')


@dataclass(frozen=True)
class CostPolicy:
    policy_id:str
    version:int
    instrument:str
    pricing_basis:str
    commission_aggregation:str
    commission_rate:str
    minimum_per_order:str
    components:tuple[CostEvidence,...]
    classification:str

    def __post_init__(self):
        if type(self.version) is not int or self.version<1 or self.instrument!='EUR/USD':raise ValueError('POLICY_IDENTITY')
        if self.classification!='PROPOSED_NOT_ACTIVATED' or self.pricing_basis!='MIDPOINT':raise ValueError('PROPOSAL_REQUIRED')
        if self.commission_aggregation!='FULL_NOTIONAL_PER_CHARGEABLE_EVENT':raise ValueError('COMMISSION_BASIS_REQUIRED')
        number(decimal_text(self.commission_rate),positive=True);number(decimal_text(self.minimum_per_order),positive=True)
        if not isinstance(self.components,tuple) or any(not isinstance(x,CostEvidence) for x in self.components):raise ValueError('IMMUTABLE_COMPONENTS_REQUIRED')
        if {x.component for x in self.components}!={'commission','spread','slippage','financing'} or len(self.components)!=4:
            raise ValueError('COMPONENTS_REQUIRED')

    @property
    def policy_hash(self):return digest(asdict(self))

    @property
    def normal_entry_blockers(self):
        return ('COST_POLICY_NOT_APPROVED',)+tuple(x.component.upper()+'_COST_UNBOUNDED' for x in self.components if x.status in ('UNKNOWN','UNBOUNDED_ASSUMPTION'))

    def commission_estimate(self,quantity,entry_price,exit_price,*,entry_orders,exit_orders):
        for value in (quantity,entry_price,exit_price):number(value,positive=True)
        if any(type(n) is not int or n<1 for n in (entry_orders,exit_orders)):raise ValueError('ORDER_COUNT_REQUIRED')
        from .r20_economics import exact
        @exact
        def calculate():
            rate=decimal_text(self.commission_rate);minimum=decimal_text(self.minimum_per_order)
            # With no per-event allocation, reserve the full-notional estimate
            # for every chargeable event (including replacement/overnight).
            return (entry_orders*max(minimum,quantity*entry_price*rate),
                    exit_orders*max(minimum,quantity*exit_price*rate))
        return calculate()

    def to_json(self):return encoded(dict(asdict(self),policy_hash=self.policy_hash,normal_entry_blockers=self.normal_entry_blockers))

    @classmethod
    def from_json(cls,text):
        row=strict_json(text)
        if set(row)!={'policy_id','version','instrument','pricing_basis','commission_aggregation','commission_rate','minimum_per_order','components','classification','policy_hash','normal_entry_blockers'}:
            raise ValueError('POLICY_FIELDS')
        expected=row.pop('policy_hash');blocks=row.pop('normal_entry_blockers')
        row['components']=tuple(CostEvidence(**dict(x,limitations=tuple(x['limitations']))) for x in row['components'])
        p=cls(**row)
        if p.policy_hash!=expected or list(p.normal_entry_blockers)!=blocks:raise ValueError('POLICY_HASH_MISMATCH')
        return p
