"""Complete virtual lifecycle in a strictly isolated synthetic laboratory.

No runner, cohort creation, broker transport, HTTP execution or operational DB.
The existing technical signal function is consumed without modifying V1.
"""
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import re

from .r20_admission import AdmissionCoordinator, RoleStore, SignalProposal
from .r20_configuration import typed
from .r20_economics import Cost, OpenRisk, equity, exact, identity
from .r20_persistence import Snapshot, chain_hash, sql_text, transition
from .r20_profiles import EconomicProfile, decimal_text, digest, economic_day, encoded, number, strict_json, utc
from .r20_sizing import CostModel, Limits

D=Decimal


@dataclass(frozen=True)
class Quote:
    bid:Decimal
    ask:Decimal
    at:datetime
    source:str
    market:str
    connected:bool
    evidence_hash:str

    @property
    @exact
    def midpoint(self):return self.bid+(self.ask-self.bid)/2

    def validate(self,now):
        number(self.bid,positive=True);number(self.ask,positive=True)
        if self.ask<self.bid:raise ValueError('QUOTE_CROSSED')
        if self.source!='SYNTHETIC_TEST_ONLY':raise ValueError('ISOLATED_QUOTE_REQUIRED')
        if self.connected is not True or self.market!='OPEN':raise ValueError('QUOTE_UNAVAILABLE')
        if not isinstance(self.evidence_hash,str) or not re.fullmatch('[a-f0-9]{64}',self.evidence_hash):
            raise ValueError('QUOTE_EVIDENCE_REQUIRED')
        if not 0<=(utc(now)-utc(self.at)).total_seconds()<=30:raise ValueError('QUOTE_STALE_OR_FUTURE')


class ShadowCycle:
    def __init__(self,store,context,clock=lambda:datetime.now(timezone.utc)):
        self.store,self.context,self.clock=store,context,clock
        self.scope=context['scope']
        if context['classification']!='SYNTHETIC_TEST_ONLY':raise ValueError('ISOLATED_CYCLE_REQUIRED')
        self.admission=AdmissionCoordinator(store,context,clock)

    @staticmethod
    def install(store):
        if isinstance(store,RoleStore):raise ValueError('OWNER_SETUP_ONLY')
        store.execute(Path(__file__).with_name('r20_shadow_schema.sql').read_text(encoding='utf-8'))

    @staticmethod
    def provision_test_permission(owner,scope,start,end,actor,*,context=None):
        """Explicit TEST bootstrap capability; no profile/API can issue it."""
        if isinstance(owner,RoleStore):raise ValueError('OWNER_SETUP_ONLY')
        identity(scope);identity(actor)
        if utc(end)<=utc(start):raise ValueError('PERMISSION_WINDOW')
        payload=dict(scope=scope,start=utc(start),end=utc(end),actor=actor,
                     classification='SYNTHETIC_TEST_ONLY',brokerOrders=False)
        if context is not None:
            from .r20_shadow_plan import bind_preparation
            if context['scope']!=scope:raise ValueError('PERMISSION_SCOPE_MISMATCH')
            bound=bind_preparation(owner,context,context['shadow_plan']['preparationHash'],start)
            if bound!=context:raise ValueError('PLAN_BINDING_MISMATCH')
            payload.update(plan=context['shadow_plan'],contextHash=digest(context))
        body=encoded(payload)
        owner.execute('INSERT INTO r20_v2_shadow.permissions VALUES('+','.join((
            sql_text(scope),sql_text(digest(strict_json(body))),sql_text(body)))+') ON CONFLICT DO NOTHING;')

    def _permission(self,at):
        raw=self.store.execute(f'SELECT payload FROM r20_v2_shadow.permissions WHERE scope={sql_text(self.scope)};')
        if not any(datetime.fromisoformat(r['start'])<=at<datetime.fromisoformat(r['end'])
                   for r in (strict_json(line) for line in raw.splitlines())):
            raise ValueError('SHADOW_PERMISSION_REQUIRED')

    def _state(self):
        raw=self.store.execute(f"""BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
          SELECT json_build_object('lifecycle',COALESCE((SELECT json_agg(payload::json ORDER BY revision)
            FROM r20_v2_shadow.events WHERE scope={sql_text(self.scope)}),'[]'::json),
          'accounting',COALESCE((SELECT json_agg(json_build_object('revision',e.revision,'previous',e.previous_hash,
            'hash',e.event_hash,'request',e.request_id,'payload',e.payload,'profile',p.payload) ORDER BY e.revision)
            FROM r20_v2_test.events e LEFT JOIN r20_v2_test.profiles p ON p.scope_id=e.scope_id AND p.version=e.profile_version
            WHERE e.scope_id={sql_text(self.scope)}),'[]'::json))::text; COMMIT;""")
        data=strict_json(raw)
        rows=[];prev=''
        accounting={h.revision:h for _,h in self.store.decode_rows(self.scope,data['accounting'])}
        if not accounting:raise ValueError('ACCOUNTING_LEDGER_REQUIRED')
        for r in data['lifecycle']:
            body=encoded({k:v for k,v in r.items() if k!='hash'})
            if r['revision']!=len(rows)+1 or r['previousHash']!=prev or digest(strict_json(body))!=r['hash']:
                raise ValueError('SHADOW_CHAIN_INTEGRITY')
            head=accounting.get(r['accountingRevision'])
            if head is None or head.hash!=r['accountingHash']:raise ValueError('SHADOW_ACCOUNTING_INTEGRITY')
            prev=r['hash'];rows.append(r)
        head=accounting[max(accounting)]
        positions=rows[-1]['positions'] if rows else []
        if {p['position_id'] for p in positions}!={i for i,_ in head.snapshot.open_gross}:
            raise ValueError('SHADOW_INVENTORY_RECONCILIATION_REQUIRED')
        return rows,head

    def history(self):return self._state()[0]

    def inventory(self):
        rows,_=self._state()
        return rows[-1]['positions'] if rows else []

    def _replay(self,key,request):
        identity(key)
        for row in self.history():
            if row['requestId']==key:
                if row['requestHash']!=digest(request):raise ValueError('IDEMPOTENCY_CONFLICT')
                return row
        return None

    def _commit(self,key,request,kind,snapshot,positions,trades,quote=None,reason=None,
                expected_head=None,before_commit=None,after_commit=None):
        rows,head=self._state()
        if expected_head is not None and head!=expected_head:raise ValueError('CAS_CONFLICT')
        transition(head.snapshot,snapshot)
        at=utc(self.clock())
        if at<head.snapshot.daily.at:raise ValueError('OBSERVATION_CLOCK_REGRESSION')
        if rows and at<datetime.fromisoformat(rows[-1]['at']):raise ValueError('OBSERVATION_CLOCK_REGRESSION')
        rev=len(rows)+1;prev=rows[-1]['hash'] if rows else ''
        account_key='shadow-'+key;identity(account_key)
        body=snapshot.to_json()
        event=dict(scope=self.scope,revision=rev,previousHash=prev,requestId=key,requestHash=digest(request),
            kind=kind,at=at,positions=positions,trades=trades,quote=asdict(quote) if quote else None,reason=reason,
            input=request,
            accountingRevision=head.revision+1,accountingHash=chain_hash(head.hash,head.revision+1,account_key,body),
            classification='SYNTHETIC_VIRTUAL_LAB',cohortStarted=False,brokerOrders=0,liveEnabled=False)
        event['hash']=digest(event)
        if before_commit:before_commit()
        self.store.execute('SELECT r20_v2_shadow.commit_event('+','.join((sql_text(self.scope),sql_text(key),
            sql_text(digest(request)),str(head.revision),sql_text(head.hash),str(rev-1),sql_text(prev),
            sql_text(snapshot.profile.to_json()),sql_text(body),sql_text(encoded(event)),
            sql_text(encoded({k:v for k,v in event.items() if k!='hash'}))))+');')
        if after_commit:after_commit()
        return next(r for r in self.history() if r['requestId']==key)

    def reserve(self,signal,key,**hooks):
        self.admission.clock=self.clock
        # A stable reservation retry is recovered even after permission expiry.
        if not any(r['requestId']==key for r in self.admission.receipts()):self._permission(utc(self.clock()))
        return self.admission.reserve(signal,key,**hooks)

    def _management_daily(self,head,at,value,terms,pending):
        s=head.snapshot;profile=s.profile;daily=s.daily
        active=next((r for r in reversed(self.admission.configuration.history()) if r['lifecycle']=='ACTIVATED_FOR_SHADOW'),None)
        if active and active['contextHash']==digest(self.context) and daily.inventory_verified:
            candidate=EconomicProfile.from_json(encoded(active['profile']))
            if candidate.valid_at(at) and candidate.configuration_version>=profile.configuration_version:
                profile=candidate
                daily,profile,loaded=self.admission.configuration.daily(profile,at)
                if loaded!=head:raise ValueError('CAS_CONFLICT')
        return profile,daily.observe(profile,at,value,terms,pending)

    @exact
    def open(self,reservation,quote,key,**hooks):
        request=dict(action='open',reservation=reservation,quote=asdict(quote))
        replay=self._replay(key,request)
        if replay:return replay
        at=utc(self.clock());quote.validate(at);self._permission(at)
        rows,head=self._state();positions=rows[-1]['positions'] if rows else [];trades=rows[-1]['trades'] if rows else []
        receipt=next((r for r in self.admission.receipts() if r['requestId']==reservation),None)
        if receipt is None:raise ValueError('RESERVATION_REQUIRED')
        pid=receipt['signal']['signal_id']
        if not any(p.position_id==pid for p in head.snapshot.daily.pending_terms):
            raise ValueError('POSITION_ALREADY_OPENED_OR_RELEASED')
        signal=SignalProposal(**dict(receipt['signal'],price=decimal_text(receipt['signal']['price']),
            stop_distance=decimal_text(receipt['signal']['stop_distance']),
            signal_at=datetime.fromisoformat(receipt['signal']['signal_at']),quote_at=datetime.fromisoformat(receipt['signal']['quote_at'])))
        signal.validate(at)
        if quote.midpoint!=signal.price:raise ValueError('PRICE_CHANGED_REASSESS_REQUIRED')
        active=next((r for r in reversed(self.admission.configuration.history()) if r['lifecycle']=='ACTIVATED_FOR_SHADOW'),None)
        if active is None or active['profile']['configuration_hash']!=receipt['activeProfileHash']:raise ValueError('PROFILE_CHANGED_REASSESS_REQUIRED')
        profile=head.snapshot.profile
        if profile.configuration_hash!=receipt['activeProfileHash'] or not profile.valid_at(at):raise ValueError('PROFILE_EXPIRED')
        if head.snapshot.daily.loss_blocked or head.snapshot.daily.operational_blocks:raise ValueError('DAILY_OR_OPERATIONAL_BLOCK')
        if self.context.get('cost_unknowns') or active['contextHash']!=digest(self.context):raise ValueError('COST_OR_CONTEXT_UNKNOWN')
        from .r20_shadow_plan import resolve_plan
        plan=resolve_plan(self.store,self.context,profile,at)
        if plan!=receipt.get('executionPlan'):raise ValueError('PLAN_CHANGED_REASSESS_REQUIRED')
        q=decimal_text(receipt['assessment']['quantity']);distance=signal.stop_distance
        if signal.side=='SHORT' and signal.price-2*distance<=0:raise ValueError('TARGET_NONPOSITIVE')
        model=typed(CostModel,self.context['costs']);breakdown=model.breakdown(q)
        if model.policy_hash!=profile.cost_policy_hash:raise ValueError('COST_POLICY_CHANGED')
        costs=tuple(c for c in head.snapshot.costs if c.cost_id!='reservation-'+reservation)
        # Each component has one identity: entry settled, all remaining estimated.
        parts={'open_fee':breakdown['open_fee'],'entry_spread':q*model.entry_spread/2,
               'entry_slippage':q*model.entry_slippage,'close_fee':breakdown['close_fee'],
               'exit_spread':q*model.exit_spread/2,'exit_slippage':q*model.exit_slippage,'financing':breakdown['financing']}
        for part,amount in parts.items():
            settled=part in ('open_fee','entry_spread','entry_slippage')
            costs+=(Cost(pid+'-'+part,amount,'SETTLED' if settled else 'RESERVED',
                        'MODELED' if settled else 'ESTIMATED','SYNTHETIC_VIRTUAL_COST:'+signal.evidence_hash),)
        worst=max(decimal_text(r['candidate_loss']) for r in receipt['assessment']['stress'])
        limits=typed(Limits,self.context['limits']);sign=1 if signal.side=='LONG' else -1
        position=dict(position_id=pid,reservation=reservation,side=signal.side,quantity=q,entry_price=signal.price,
            stop=signal.price-sign*distance,target=signal.price+sign*2*distance,opened_at=at,quote=asdict(quote),
            engine_hash=signal.engine_hash,source_hash=signal.evidence_hash,entry_profile=active['profile'],
            cost_model=asdict(model),cost_total=model.total(q),cost_ids=[pid+'-'+part for part in parts],stressed_net=-worst,
            initial_margin_fraction=limits.initial_margin_fraction,
            maintenance_fraction=max(decimal_text(s['maintenance_fraction']) for s in self.context['stresses']),
            hard_exposure_limit=limits.hard_exposure_limit,
            margin_evidence=limits.evidence,operational_policy_hash=profile.operational_policy_hash)
        position.update(execution_plan=plan,purpose=plan['purpose'] if plan else 'NORMAL',
            economically_viable=decimal_text(receipt['assessment']['net_target'])>0,
            sizing=receipt['assessment'],intrabar_protection='UNVERIFIED_BETWEEN_QUOTES')
        positions=positions+[strict_json(encoded(position))]
        gross=head.snapshot.open_gross+((pid,D(0)),)
        value=equity(profile.capital_base_usd,head.snapshot.realized_gross,tuple(v for _,v in gross),costs).economic
        daily=head.snapshot.daily.observe(profile,at,value,
            head.snapshot.daily.open_terms+(OpenRisk(pid,-model.total(q),-worst),),
            tuple(p for p in head.snapshot.daily.pending_terms if p.position_id!=pid))
        snapshot=Snapshot(profile,daily,head.snapshot.realized_gross,gross,costs,'SYNTHETIC_VIRTUAL_OPEN')
        return self._commit(key,request,'OPEN',snapshot,positions,trades,quote,expected_head=head,**hooks)

    @exact
    def release(self,reservation,key,**hooks):
        request=dict(action='release',reservation=reservation)
        replay=self._replay(key,request)
        if replay:return replay
        rows,h=self._state();s=h.snapshot
        r=next((r for r in self.admission.receipts() if r['requestId']==reservation),None)
        if r is None:raise ValueError('RESERVATION_REQUIRED')
        pid=r['signal']['signal_id']
        if not any(p.position_id==pid for p in s.daily.pending_terms):raise ValueError('RESERVATION_NOT_PENDING')
        costs=tuple(c for c in s.costs if c.cost_id!='reservation-'+reservation)
        value=equity(s.profile.capital_base_usd,s.realized_gross,tuple(v for _,v in s.open_gross),costs).economic
        profile,daily=self._management_daily(h,utc(self.clock()),value,s.daily.open_terms,
                             tuple(p for p in s.daily.pending_terms if p.position_id!=pid))
        return self._commit(key,request,'RELEASE',replace(s,profile=profile,daily=daily,costs=costs),rows[-1]['positions'] if rows else [],
            rows[-1]['trades'] if rows else [],expected_head=h,**hooks)

    @exact
    def observe(self,quote,key,*,expected_head=None,before_commit=None,after_commit=None):
        request=dict(action='observe',quote=asdict(quote))
        replay=self._replay(key,request)
        if replay:return replay
        at=utc(self.clock());rows,h=self._state();s=h.snapshot
        if expected_head is not None and h!=expected_head:raise ValueError('CAS_CONFLICT')
        positions=rows[-1]['positions'] if rows else [];trades=list(rows[-1]['trades']) if rows else []
        try:
            quote.validate(at)
            last=next((r for r in reversed(rows) if r['quote'] and r['kind'] not in ('DATA_UNAVAILABLE','SIGNAL_DIAGNOSTIC')),None)
            if last and quote.at<datetime.fromisoformat(last['quote']['at']):raise ValueError('QUOTE_TIME_REGRESSION')
        except ValueError as exc:
            return self._commit(key,request,'DATA_UNAVAILABLE',s,positions,trades,quote,str(exc),h,before_commit,after_commit)
        if economic_day(at)[0]!=s.daily.day_id:
            self.roll_management_day(quote,'day-'+key)
            rows,h=self._state();s=h.snapshot
        gross=[];terms=[];remaining=[];costs=s.costs;realized=s.realized_gross
        all_gross={p['position_id']:(1 if p['side']=='LONG' else -1)*decimal_text(p['quantity'])*
                   (quote.midpoint-decimal_text(p['entry_price'])) for p in positions}
        mark_equity=equity(s.profile.capital_base_usd,realized,tuple(all_gross.values()),costs).economic
        maintenance=sum((decimal_text(p['quantity'])*quote.midpoint*decimal_text(p['maintenance_fraction']) for p in positions),D(0))
        margin_deficit=mark_equity<=maintenance
        exposure=sum((decimal_text(p['quantity'])*quote.midpoint for p in positions),D(0))
        exposure_breach=bool(positions) and exposure>min(decimal_text(p['hard_exposure_limit']) for p in positions)
        for p in positions:
            pid=p['position_id'];price=quote.midpoint;v=all_gross[pid];long=p['side']=='LONG'
            reason=('STOP_LOSS' if (price<=decimal_text(p['stop']) if long else price>=decimal_text(p['stop'])) else
                    'TAKE_PROFIT' if (price>=decimal_text(p['target']) if long else price<=decimal_text(p['target'])) else
                    'EMERGENCY_DEFENSIVE_EXIT' if 'EMERGENCY_STOP' in s.daily.operational_blocks else
                    'HARD_EXPOSURE_LIMIT' if exposure_breach else
                    'MODELED_MARGIN_DEFICIT' if margin_deficit else None)
            if reason:
                realized+=v
                costs=tuple(replace(c,status='SETTLED',provenance='MODELED') if c.cost_id in p['cost_ids'] and c.status=='RESERVED' else c for c in costs)
                trades.append(dict(position=p,position_id=pid,closed_at=at,exit_quote=asdict(quote),
                    exit_price=price,reason=reason,gross=v,cost=decimal_text(p['cost_total']),net=v-decimal_text(p['cost_total']),
                    classification='SYNTHETIC_VIRTUAL_LAB'))
            else:
                remaining.append(p);gross.append((pid,v))
                terms.append(OpenRisk(pid,v-decimal_text(p['cost_total']),decimal_text(p['stressed_net'])))
        value=equity(s.profile.capital_base_usd,realized,tuple(v for _,v in gross),costs).economic
        profile,daily=self._management_daily(h,at,value,tuple(terms),s.daily.pending_terms)
        snapshot=Snapshot(profile,daily,realized,tuple(gross),costs,'SYNTHETIC_VIRTUAL_OBSERVATION')
        return self._commit(key,request,'CLOSE' if len(trades)>(len(rows[-1]['trades']) if rows else 0) else 'MARK',
            snapshot,remaining,strict_json(encoded(trades)),quote,expected_head=h,before_commit=before_commit,after_commit=after_commit)

    def roll_management_day(self,quote,key):
        request=dict(action='management-day',quote=asdict(quote))
        replay=self._replay(key,request)
        if replay:return replay
        at=utc(self.clock());quote.validate(at);rows,h=self._state();s=h.snapshot
        # The boundary must use the last verified valuation: do not guess an
        # unobserved midnight price from a later quote. Only same-price boundary
        # evidence is accepted by this lab contract; otherwise block for review.
        positions=rows[-1]['positions'] if rows else []
        last=next((r for r in reversed(rows) if r['quote'] and r['kind'] not in ('DATA_UNAVAILABLE','SIGNAL_DIAGNOSTIC')),None)
        verified=(not positions or (quote.at==economic_day(at)[1] and last is not None and Quote(**dict(last['quote'],
            bid=decimal_text(last['quote']['bid']),ask=decimal_text(last['quote']['ask']),
            at=datetime.fromisoformat(last['quote']['at']))).midpoint==quote.midpoint))
        day=s.daily.management_day(s.profile,s.daily.current_equity,at,boundary_verified=verified)
        return self._commit(key,request,'MANAGEMENT_DAY',replace(s,daily=day),positions,rows[-1]['trades'] if rows else [],quote,expected_head=h)

    def diagnose(self,root,bars,minutes,quote,key,*,quality):
        """Existing EMA/breakout/ATR decision, persisted without opening authority.

        The lab requires explicit contiguous synthetic quality. Authentic reader
        evidence needs a separately reviewed ingestion boundary and is rejected
        here; callers cannot relabel it through the configuration HTTP service.
        """
        from .aggressive_growth import configuration,signal,closed_bars
        from .aggressive_growth_runner import engine_hashes
        at=utc(self.clock());technical=configuration(root)
        evidence=digest(bars)
        decision=signal(technical,bars,minutes,at)
        reason=decision['reason'] or 'CANDIDATE_ONLY'
        try:
            quote.validate(at)
            if quality!='SYNTHETIC_CONTIGUOUS_COMPLETE':raise ValueError('DATA_QUALITY_UNVERIFIED')
            closed=closed_bars(bars,minutes,at)
            if any((b['opened_at']-a['opened_at']).total_seconds()!=minutes*60 for a,b in zip(closed,closed[1:])):
                raise ValueError('BAR_GAP')
            proposal=SignalProposal.from_engine(decision,signal_id='signal-'+digest(dict(strategy=decision['strategy'],minutes=minutes,candle_at=decision['at']))[:32],
                price=quote.midpoint,quote_at=quote.at,engine_hash=engine_hashes(root),evidence_hash=evidence,source=quote.source)
            if proposal:proposal.validate(at)
            if self.context.get('cost_unknowns'):reason='COST_OR_MARGIN_UNKNOWN'
        except (ValueError,TypeError,KeyError) as exc:reason=str(exc)
        request=dict(action='diagnose',decision=decision,sourceHash=evidence,engineHash=engine_hashes(root),
                     quality=quality,quote=asdict(quote),minutes=minutes)
        replay=self._replay(key,request)
        if replay:return replay
        rows,h=self._state()
        return self._commit(key,request,'SIGNAL_DIAGNOSTIC',h.snapshot,rows[-1]['positions'] if rows else [],
                            rows[-1]['trades'] if rows else [],quote,reason,expected_head=h)

    def reserve_engine(self,root,bars,minutes,quote,key,*,quality):
        """Signal-to-budget boundary, deliberately not an automatic open loop."""
        diagnostic=self.diagnose(root,bars,minutes,quote,'diagnose-'+key,quality=quality)
        decision=diagnostic['input']['decision']
        if decision['side'] is None:return dict(status='NO_SIGNAL',diagnostic=diagnostic)
        if diagnostic['reason']!='CANDIDATE_ONLY':raise ValueError('ENTRY_DATA_OR_COST_BLOCKED:'+diagnostic['reason'])
        proposal=SignalProposal.from_engine(decision,
            signal_id='signal-'+digest(dict(strategy=decision['strategy'],minutes=minutes,candle_at=decision['at']))[:32],
            price=quote.midpoint,quote_at=quote.at,engine_hash=diagnostic['input']['engineHash'],
            evidence_hash=diagnostic['input']['sourceHash'],source=quote.source)
        return self.reserve(proposal,key)

    def view(self):
        rows,h=self._state()
        return dict(scope=self.scope,classification='SYNTHETIC_VIRTUAL_LAB',cohortStarted=False,
            lifecycleRevision=len(rows),accountingRevision=h.revision,accountingHash=h.hash,
            positions=rows[-1]['positions'] if rows else [],trades=rows[-1]['trades'] if rows else [],
            lastEvent=rows[-1] if rows else None,equity=str(h.snapshot.daily.current_equity),
            daily=strict_json(h.snapshot.daily.to_json()),brokerOrders=0,liveEnabled=False)
