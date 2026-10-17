"""TEST-only atomic budget reservations. No runner, cohorts, fills or broker I/O."""
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from .r20_configuration import ConfigurationService, typed
from .r20_economics import Cost, PendingRisk, equity, identity, exact
from .r20_persistence import TestStore, Snapshot, chain_hash, sql_text
from .r20_profiles import EconomicProfile, decimal_text, digest, encoded, strict_json, utc
from .r20_sizing import AllocationRequest, CostModel, Limits, Stress, size

ROLES={'reader':'r20_lab_reader','profile-admin':'r20_lab_profiles',
       'shadow':'r20_lab_shadow','paper':'r20_lab_paper_disabled'}


class RoleStore(TestStore):
    """Role chosen by trusted host; never from an HTTP body. TEST cluster only."""
    def __init__(self,database,system_id,role):
        super().__init__(database,system_id)
        if role not in ROLES:raise ValueError('ROLE_NOT_ALLOWED')
        self.role=role

    def execute(self,sql):
        return super().execute('SET ROLE '+ROLES[self.role]+';'+sql)


@dataclass(frozen=True)
class SignalProposal:
    signal_id:str
    side:str
    price:Decimal
    stop_distance:Decimal
    signal_at:datetime
    quote_at:datetime
    source:str
    engine_hash:str
    evidence_hash:str

    def validate(self,at):
        identity(self.signal_id);at=utc(at)
        if self.side not in ('LONG','SHORT'):raise ValueError('SIDE_REQUIRED')
        if self.source!='SYNTHETIC_TEST_ONLY':raise ValueError('ISOLATED_SIGNAL_REQUIRED')
        from .r20_profiles import number
        import re
        number(self.price,positive=True);number(self.stop_distance,positive=True)
        if not all(isinstance(v,str) and re.fullmatch('[a-f0-9]{64}',v) for v in (self.engine_hash,self.evidence_hash)):
            raise ValueError('SOURCE_HASH_REQUIRED')
        if not 0<=(at-utc(self.quote_at)).total_seconds()<=30:raise ValueError('QUOTE_STALE_OR_FUTURE')
        if not 0<=(at-utc(self.signal_at)).total_seconds()<=180:raise ValueError('SIGNAL_STALE_OR_FUTURE')

    @classmethod
    def from_engine(cls,signal,*,signal_id,price,quote_at,engine_hash,evidence_hash,source):
        """Pure boundary adapter for existing signal(); side=null yields NO_SIGNAL.

        Provenance verification belongs to a future trusted reader, not this parser.
        The lab coordinator accepts only explicitly synthetic test material.
        """
        if signal.get('strategy')!='AGGRESSIVE_TREND_BREAKOUT_V1':raise ValueError('STRATEGY_MISMATCH')
        if signal.get('side') is None:return None
        return cls(signal_id,signal['side'],price,decimal_text(signal['stop_distance']),
                   datetime.fromisoformat(signal['at']),quote_at,source,engine_hash,evidence_hash)


class AdmissionCoordinator:
    def __init__(self,store,context,clock=lambda:datetime.now(timezone.utc)):
        self.configuration=ConfigurationService(store,context,clock)
        self.store,self.context,self.clock=store,context,clock

    @staticmethod
    def install(store):
        if isinstance(store,RoleStore):raise ValueError('OWNER_SETUP_ONLY')
        store.execute(Path(__file__).with_name('r20_admission_schema.sql').read_text(encoding='utf-8'))

    def receipts(self):
        value=self.store.execute(f'SELECT payload FROM r20_v2_admission.receipts WHERE scope={sql_text(self.context["scope"])} ORDER BY accounting_revision;')
        rows=[strict_json(line) for line in value.splitlines()]
        for row in rows:
            if row['hash']!=digest({k:v for k,v in row.items() if k!='hash'}):raise ValueError('RECEIPT_INTEGRITY')
        return rows

    @exact
    def reserve(self,signal,request_id,*,expected_head=None,before_commit=None,after_commit=None):
        if not isinstance(signal,SignalProposal):raise ValueError('TYPED_SIGNAL_REQUIRED')
        identity(request_id)
        reqhash=digest(dict(signal=asdict(signal),requestId=request_id,scope=self.context['scope']))
        receipts=self.receipts()
        for row in receipts:
            if row['requestId']==request_id:
                if row['requestHash']!=reqhash:raise ValueError('IDEMPOTENCY_CONFLICT')
                return row
        if any(row['signal']['signal_id']==signal.signal_id for row in receipts):raise ValueError('SIGNAL_ALREADY_RESERVED')
        at=utc(self.clock());signal.validate(at)
        rows=self.configuration.history()
        active=next((r for r in reversed(rows) if r['lifecycle']=='ACTIVATED_FOR_SHADOW'),None)
        if active is None:raise ValueError('PROFILE_REQUIRED')
        if active['contextHash']!=digest(self.context):raise ValueError('CONTEXT_CHANGED_REVALIDATE')
        if self.context.get('cost_unknowns'):raise ValueError('COST_POLICY_UNKNOWN')
        profile=EconomicProfile.from_json(encoded(active['profile']))
        if not profile.valid_at(at):raise ValueError('PROFILE_EXPIRED')
        from .r20_shadow_plan import resolve_plan
        plan=resolve_plan(self.store,self.context,profile,at)
        daily,profile,head=self.configuration.daily(profile,at)
        if expected_head is not None and expected_head!=head:raise ValueError('CAS_CONFLICT')
        expected_head=head
        pending_ids={p.position_id for p in daily.pending_terms}
        receipts=[r for r in receipts if r['signal']['signal_id'] in pending_ids]
        if {r['signal']['signal_id'] for r in receipts}!=pending_ids:raise ValueError('PENDING_INVENTORY_RECONCILIATION_REQUIRED')
        if len(daily.open_terms)+len(daily.pending_terms)>=profile.max_open_positions:raise ValueError('ENTRY_DENIED:POSITION_LIMIT')
        # The accounting prototype stores PnL/risk, not quantity/protection/margin
        # of filled positions. Never treat missing exposure as a zero position.
        positions=[]
        if daily.open_terms:
            # No client supplies exposure. Recover full immutable positions from
            # the lifecycle ledger and require valuation at the candidate price.
            if self.store.execute("SELECT to_regclass('r20_v2_shadow.events') IS NOT NULL;")!='t':
                raise ValueError('OPEN_INVENTORY_CONTEXT_REQUIRED')
            from .r20_shadow import ShadowCycle
            try:positions=ShadowCycle(self.store,self.context,self.clock).inventory()
            except ValueError as exc:raise ValueError('OPEN_INVENTORY_CONTEXT_REQUIRED') from exc
            if {p['position_id'] for p in positions}!={p.position_id for p in daily.open_terms}:
                raise ValueError('OPEN_INVENTORY_CONTEXT_REQUIRED')
            for p in positions:
                expected=(1 if p['side']=='LONG' else -1)*decimal_text(p['quantity'])*(signal.price-decimal_text(p['entry_price']))
                if dict(head.snapshot.open_gross)[p['position_id']]!=expected:raise ValueError('OPEN_INVENTORY_REVALUATION_REQUIRED')
        # Costs from old reservations are already included in economic equity.
        # PendingRisk below carries only incremental stress loss, never those costs again.
        committed=sum((decimal_text(r['assessment']['initial_margin']) for r in receipts),Decimal(0))
        pending_quantity=sum((decimal_text(r['assessment']['quantity']) for r in receipts),Decimal(0))
        pending_exposure=pending_quantity*signal.price
        c=self.context
        args={k:decimal_text(c[k]) for k in ('free_margin','existing_exposure','committed_margin','liquidity_quantity')}
        args['existing_exposure']+=pending_exposure
        args['committed_margin']+=committed
        args['existing_exposure']+=sum((decimal_text(p['quantity'])*signal.price for p in positions),Decimal(0))
        args['committed_margin']+=sum((decimal_text(p['quantity'])*signal.price*decimal_text(p['initial_margin_fraction']) for p in positions),Decimal(0))
        args['free_margin']=max(Decimal(0),min(args['free_margin']-committed,daily.current_equity-args['committed_margin']))
        scenarios=[]
        base_scenarios=[typed(Stress,source) for source in c['stresses']]
        direction=1 if signal.side=='LONG' else -1
        if base_scenarios and not any(-direction*s.price_move==signal.stop_distance for s in base_scenarios):
            # ATR supplies the exact stop scenario; preserve every approved gap
            # scenario, and use their conservative cost/margin buffers. No new
            # arbitrary shock or reduced assumption is introduced.
            base_scenarios.append(replace(base_scenarios[0],name='candidate_stop',price_move=-direction*signal.stop_distance,
                existing_loss=max(s.existing_loss for s in base_scenarios),
                existing_exposure_change=max(s.existing_exposure_change for s in base_scenarios),
                existing_maintenance=max(s.existing_maintenance for s in base_scenarios),
                maintenance_fraction=max(s.maintenance_fraction for s in base_scenarios),
                equity_buffer=max(s.equity_buffer for s in base_scenarios),margin_buffer=max(s.margin_buffer for s in base_scenarios),
                extra_fixed_cost=max(s.extra_fixed_cost for s in base_scenarios),extra_unit_cost=max(s.extra_unit_cost for s in base_scenarios),
                evidence='DERIVED_STOP_FROM_APPROVED_LAB_SCENARIOS:'+digest(c['stresses'])))
        for stress in base_scenarios:
            loss=sum((max(Decimal(0),(-1 if r['signal']['side']=='LONG' else 1)*
                      decimal_text(r['assessment']['quantity'])*stress.price_move) for r in receipts),Decimal(0))
            loss+=sum((max(Decimal(0),(-1 if p['side']=='LONG' else 1)*decimal_text(p['quantity'])*stress.price_move) for p in positions),Decimal(0))
            open_quantity=sum((decimal_text(p['quantity']) for p in positions),Decimal(0))
            scenarios.append(replace(stress,existing_loss=stress.existing_loss+loss,
                existing_exposure_change=stress.existing_exposure_change+(pending_quantity+open_quantity)*stress.price_move,
                existing_maintenance=stress.existing_maintenance+pending_quantity*(signal.price+stress.price_move)*stress.maintenance_fraction+
                sum((decimal_text(p['quantity'])*(signal.price+stress.price_move)*max(stress.maintenance_fraction,decimal_text(p['maintenance_fraction'])) for p in positions),Decimal(0))))
        assessment=size(profile=profile,at=at,side=signal.side,price=signal.price,stop_distance=signal.stop_distance,
            economic_equity=daily.current_equity,pending_costs=Decimal(0),daily=daily,
            open_positions=len(daily.open_terms),pending_positions=len(daily.pending_terms),
            costs=typed(CostModel,c['costs']),limits=typed(Limits,c['limits']),
            stresses=tuple(scenarios),purpose=plan['purpose'] if plan else 'NORMAL',
            allocation_request=AllocationRequest(decimal_text(plan['allocation_usd']),decimal_text(plan['requested_allocation_leverage'])) if plan else None,**args)
        if not assessment.admitted:raise ValueError('ENTRY_DENIED:'+','.join(assessment.reasons))
        reserve_cost=assessment.estimated_costs
        worst=max(r.candidate_loss for r in assessment.stress)
        cost=Cost('reservation-'+request_id,reserve_cost,'RESERVED','ESTIMATED','SYNTHETIC_ADMISSION:'+signal.evidence_hash)
        costs=head.snapshot.costs+(cost,)
        value=equity(profile.capital_base_usd,head.snapshot.realized_gross,tuple(v for _,v in head.snapshot.open_gross),costs).economic
        daily=daily.observe(profile,at,value,daily.open_terms,daily.pending_terms+(PendingRisk(signal.signal_id,worst-reserve_cost),))
        saved=Snapshot(profile,daily,head.snapshot.realized_gross,head.snapshot.open_gross,costs,'SYNTHETIC_RESERVATION_ONLY')
        revision=head.revision+1
        body=saved.to_json()
        receipt=dict(scope=self.context['scope'],requestId=request_id,requestHash=reqhash,signal=asdict(signal),at=at,
            configRevision=rows[-1]['revision'],configHash=rows[-1]['hash'],activeProfileHash=profile.configuration_hash,
            accountingRevision=revision,accountingHash=chain_hash(head.hash,revision,request_id,body),
            assessment=asdict(assessment),classification='SYNTHETIC_RESERVATION_ONLY',ordersSupported=False,cohortStarted=False)
        if plan:receipt['executionPlan']=plan
        receipt['hash']=digest(receipt)
        if before_commit:before_commit()
        self.store.execute('SELECT r20_v2_admission.reserve('+','.join((sql_text(self.context['scope']),
            sql_text(request_id),sql_text(reqhash),str(head.revision),sql_text(head.hash),
            str(rows[-1]['revision']),sql_text(rows[-1]['hash']),sql_text(profile.to_json()),
            sql_text(body),sql_text(encoded(receipt))))+');')
        if after_commit:after_commit()
        return next(r for r in self.receipts() if r['requestId']==request_id)
