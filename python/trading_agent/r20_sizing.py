"""Bounded, pure R20 V2 sizing. Admissibility is NOT an execution permission."""
from dataclasses import asdict, dataclass, field, fields
from decimal import Decimal, ROUND_FLOOR

from .r20_profiles import EconomicProfile, digest, number, utc
from .r20_economics import ZERO, DailyState, exact, identity, signed, unique


def evidence(value):
    if not isinstance(value,str) or not value.strip() or len(value)>2000:
        raise ValueError('POLICY_EVIDENCE_REQUIRED')


def positive_int(value, maximum=1_000_000):
    if type(value) is not int or not 0<value<=maximum: raise ValueError('POSITIVE_INTEGER_REQUIRED')


@dataclass(frozen=True)
class AllocationRequest:
    """Fixed capital target, independent of the profile's aggregate leverage cap."""
    allocation_usd: Decimal
    requested_allocation_leverage: Decimal

    def __post_init__(self):
        number(self.allocation_usd,positive=True)
        number(self.requested_allocation_leverage,minimum=Decimal(1))


@dataclass(frozen=True)
class CostModel:
    open_min: Decimal
    close_min: Decimal
    open_per_unit: Decimal
    close_per_unit: Decimal
    entry_spread: Decimal
    exit_spread: Decimal
    entry_slippage: Decimal
    exit_slippage: Decimal
    financing_fixed: Decimal
    financing_per_unit: Decimal
    evidence: str

    def __post_init__(self):
        evidence(self.evidence)
        for f in fields(self):
            if f.name!='evidence': number(getattr(self,f.name))

    @property
    def policy_hash(self): return digest(asdict(self))

    @exact
    def breakdown(self,q):
        number(q,positive=True)
        return dict(open_fee=max(self.open_min,q*self.open_per_unit),
                    close_fee=max(self.close_min,q*self.close_per_unit),
                    spread=q*(self.entry_spread+self.exit_spread)/2,
                    slippage=q*(self.entry_slippage+self.exit_slippage),
                    financing=self.financing_fixed+q*self.financing_per_unit)

    @exact
    def total(self,q): return sum(self.breakdown(q).values(),ZERO)


@dataclass(frozen=True)
class Limits:
    min_quantity: Decimal
    quantity_step: Decimal
    initial_margin_fraction: Decimal
    initial_margin_buffer: Decimal
    h_min: Decimal
    hard_exposure_limit: Decimal
    risk_pct_ceiling: Decimal
    leverage_ceiling: Decimal
    position_ceiling: int
    max_grid_points: int
    evidence: str

    def __post_init__(self):
        evidence(self.evidence)
        for name in ('min_quantity','quantity_step','initial_margin_fraction','h_min',
                     'hard_exposure_limit','risk_pct_ceiling','leverage_ceiling'):
            number(getattr(self,name),positive=True)
        number(self.initial_margin_buffer)
        if self.h_min>=1 or self.risk_pct_ceiling>100 or self.leverage_ceiling<1:
            raise ValueError('LIMITS_OUT_OF_RANGE')
        positive_int(self.position_ceiling); positive_int(self.max_grid_points)

    @property
    def policy_hash(self): return digest(asdict(self))


@dataclass(frozen=True)
class Stress:
    name: str
    price_move: Decimal
    existing_loss: Decimal
    existing_exposure_change: Decimal
    existing_maintenance: Decimal
    maintenance_fraction: Decimal
    equity_buffer: Decimal
    margin_buffer: Decimal
    extra_fixed_cost: Decimal
    extra_unit_cost: Decimal
    evidence: str

    def __post_init__(self):
        identity(self.name); evidence(self.evidence)
        signed(self.price_move); signed(self.existing_exposure_change)
        for name in ('existing_loss','existing_maintenance','maintenance_fraction',
                     'equity_buffer','margin_buffer','extra_fixed_cost','extra_unit_cost'):
            number(getattr(self,name),positive=name=='maintenance_fraction')


@dataclass(frozen=True)
class StressResult:
    name: str
    equity: Decimal
    exposure: Decimal
    maintenance: Decimal
    required_headroom: Decimal
    candidate_loss: Decimal


@dataclass(frozen=True)
class Assessment:
    admitted: bool
    reasons: tuple[str,...]
    profile_hash: str | None
    input_hash: str
    quantity: Decimal = ZERO
    price_risk: Decimal = ZERO
    price_risk_budget: Decimal = ZERO
    allocation: Decimal = ZERO
    exposure: Decimal = ZERO
    initial_margin: Decimal = ZERO
    estimated_costs: Decimal = ZERO
    net_target: Decimal = ZERO
    net_stop: Decimal = ZERO
    effective_risk_pct: Decimal = ZERO
    leverage_after_costs: Decimal = ZERO
    headroom: Decimal = ZERO
    required_headroom: Decimal = ZERO
    stress: tuple[StressResult,...] = ()
    cost_status: str = field(default='ESTIMATED',init=False)
    paper_execution_eligible: bool = field(default=False,init=False)
    statistically_validated: bool = field(default=False,init=False)


@exact
def size(*,profile,at,side,price,stop_distance,economic_equity,pending_costs,
         existing_exposure,committed_margin,free_margin,liquidity_quantity,
         open_positions,pending_positions,daily,costs,limits,stresses,allocation_request=None,purpose='NORMAL'):
    """All inputs describe one reconciled snapshot; no market data is fetched here.

    The caller must verify quote/position provenance and policy calibration before
    any future integration. This function never authorizes or manages an order.
    """
    if purpose not in ('NORMAL','TECHNICAL_VALIDATION'):raise ValueError('PURPOSE_REQUIRED')
    at=utc(at)
    if profile is None: return Assessment(False,('PROFILE_REQUIRED',),None,'')
    if not isinstance(profile,EconomicProfile) or not isinstance(daily,DailyState):
        raise ValueError('TYPED_CONTRACT_REQUIRED')
    if not isinstance(costs,CostModel) or not isinstance(limits,Limits): raise ValueError('TYPED_POLICY_REQUIRED')
    if allocation_request is not None and not isinstance(allocation_request,AllocationRequest):
        raise ValueError('TYPED_ALLOCATION_REQUIRED')
    if not isinstance(stresses,tuple) or any(not isinstance(s,Stress) for s in stresses):
        raise ValueError('IMMUTABLE_STRESS_REQUIRED')
    if len(stresses)>128: raise ValueError('STRESS_COUNT_LIMIT')
    unique([s.name for s in stresses])
    for value in (price,stop_distance): number(value,positive=True)
    signed(economic_equity)
    for value in (pending_costs,existing_exposure,committed_margin,free_margin,liquidity_quantity): number(value)
    for value in (open_positions,pending_positions):
        if type(value) is not int or not 0<=value<=1_000_000: raise ValueError('POSITION_COUNT_INVALID')
    if side not in ('LONG','SHORT'): raise ValueError('SIDE_REQUIRED')
    sign=Decimal(1 if side=='LONG' else -1)
    material=dict(profile=profile.configuration_hash,at=at,side=side,price=price,
                  stop_distance=stop_distance,economic_equity=economic_equity,pending_costs=pending_costs,
                  existing_exposure=existing_exposure,committed_margin=committed_margin,free_margin=free_margin,
                  liquidity_quantity=liquidity_quantity,open_positions=open_positions,pending_positions=pending_positions,
                  daily=asdict(daily),costs=asdict(costs),limits=asdict(limits),stresses=[asdict(s) for s in stresses])
    if allocation_request is not None: material['allocation_request']=asdict(allocation_request)
    if purpose!='NORMAL':material['purpose']=purpose
    input_hash=digest(material)
    def reject(*reasons): return Assessment(False,tuple(reasons),profile.configuration_hash,input_hash)
    if not profile.valid_at(at): return reject('PROFILE_EXPIRED')
    if costs.policy_hash!=profile.cost_policy_hash or limits.policy_hash!=profile.operational_policy_hash:
        return reject('POLICY_MISMATCH')
    if (profile.risk_per_trade_pct>limits.risk_pct_ceiling or profile.max_leverage>limits.leverage_ceiling
            or profile.max_open_positions>limits.position_ceiling): return reject('OPERATIONAL_CEILING')
    if open_positions+pending_positions>=profile.max_open_positions: return reject('POSITION_LIMIT')
    if (daily.at!=at or daily.current_equity!=economic_equity or daily.profile_hash!=profile.configuration_hash
            or daily.scope_id!=profile.scope_id): return reject('DAILY_SNAPSHOT_MISMATCH')
    if len(daily.open_terms)!=open_positions or len(daily.pending_terms)!=pending_positions:
        return reject('INVENTORY_SNAPSHOT_MISMATCH')
    if pending_costs>daily.pending_risk: return reject('PENDING_RESERVE_MISMATCH')
    if not daily.can_enter(ZERO): return reject('DAILY_OR_OPERATIONAL_BLOCK')
    if min(price-sign*stop_distance,price+sign*2*stop_distance)<=0: return reject('INVALID_PROTECTION_PRICE')
    if (not any(-sign*s.price_move==stop_distance for s in stresses)
            or not any(-sign*s.price_move>stop_distance for s in stresses)):
        return reject('STRESS_COVERAGE_REQUIRED')
    if any(price+s.price_move<=0 or existing_exposure+s.existing_exposure_change<0 for s in stresses):
        return reject('STRESS_PRICE_OR_EXPOSURE_INVALID')
    available=economic_equity-pending_costs
    eligible=max(ZERO,available)
    if profile.equity_cap_usd is not None: eligible=min(eligible,profile.equity_cap_usd)
    if eligible<=0: return reject('EQUITY_UNAVAILABLE')
    budget=eligible*profile.risk_per_trade_pct/100
    allocation=eligible*profile.capital_allocation_pct/100
    multiplier=profile.max_leverage
    if allocation_request is not None:
        allocation=min(eligible,allocation_request.allocation_usd)
        multiplier=allocation_request.requested_allocation_leverage
    ceiling=min(budget/stop_distance,allocation*multiplier/price,liquidity_quantity)
    if ceiling<limits.min_quantity: return reject('MINIMUM_QUANTITY_UNAFFORDABLE')
    points=int(((ceiling-limits.min_quantity)/limits.quantity_step).to_integral_value(rounding=ROUND_FLOOR))+1
    if points>limits.max_grid_points: return reject('SIZING_UNRESOLVED')
    all_reasons=set()
    for index in range(points-1,-1,-1):
        q=limits.min_quantity+index*limits.quantity_step
        cost=costs.total(q); notional=q*price; risk=q*stop_distance
        net_target=2*risk-cost
        post=available-cost; exposure=existing_exposure+notional
        margin=notional*limits.initial_margin_fraction
        reasons=[]
        if net_target<=0 and purpose=='NORMAL': reasons.append('NONPOSITIVE_NET_TARGET')
        if post<=0: reasons.append('EQUITY_AFTER_COSTS')
        if margin+cost>min(available-committed_margin-limits.initial_margin_buffer,free_margin): reasons.append('INITIAL_MARGIN')
        if allocation_request is not None and margin+cost>allocation: reasons.append('ALLOCATION_CAPITAL')
        if exposure>limits.hard_exposure_limit: reasons.append('HARD_EXPOSURE')
        headroom=profile.max_leverage*post-exposure
        required=profile.max_leverage*post*limits.h_min
        worst=ZERO; net_stop=risk+cost; rows=[]
        for scenario in stresses:
            loss=max(ZERO,-sign*q*scenario.price_move)
            extra=scenario.extra_fixed_cost+q*scenario.extra_unit_cost
            eq=post-scenario.existing_loss-loss-extra
            exp=existing_exposure+scenario.existing_exposure_change+q*(price+scenario.price_move)
            maintenance=scenario.existing_maintenance+q*(price+scenario.price_move)*scenario.maintenance_fraction
            required_j=(exp-exposure)+profile.max_leverage*(post-eq+scenario.equity_buffer)
            required=max(required,required_j)
            worst=max(worst,loss+cost+extra)
            if -sign*scenario.price_move==stop_distance: net_stop=max(net_stop,risk+cost+extra)
            if eq<=scenario.equity_buffer: reasons.append('STRESS_EQUITY')
            if maintenance+scenario.margin_buffer>eq: reasons.append('MAINTENANCE_MARGIN')
            if exp>limits.hard_exposure_limit: reasons.append('HARD_EXPOSURE')
            rows.append(StressResult(scenario.name,eq,exp,maintenance,required_j,loss+cost+extra))
        if headroom<required: reasons.append('ADMIN_LEVERAGE_HEADROOM')
        if not daily.can_enter(worst): reasons.append('DAILY_CAPACITY')
        if not reasons:
            return Assessment(True,(),profile.configuration_hash,input_hash,q,risk,budget,allocation,
                              notional,margin,cost,net_target,net_stop,100*risk/eligible,
                              exposure/post,headroom,required,tuple(rows))
        all_reasons.update(reasons)
    return reject(*sorted(all_reasons))
