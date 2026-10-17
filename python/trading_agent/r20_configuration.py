"""Isolated configuration workflow; no execution, market readers or cohort creation."""
from dataclasses import asdict, fields, replace
from datetime import datetime, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import sys

from .r20_profiles import EconomicProfile, canonical, decimal_text, digest, economic_day, encoded, strict_json, utc
from .r20_economics import DailyState, identity
from .r20_persistence import TestStore, sql_text
from .r20_sizing import CostModel, Limits, Stress, size

FIELDS=('risk_per_trade_pct','capital_allocation_pct','max_leverage','daily_loss_limit_pct','max_open_positions')

def daily_payload(d):
    return dict(asdict(d),used_loss=d.used_loss,open_risk=d.open_risk,pending_risk=d.pending_risk,remaining=d.remaining)


def typed(cls,obj):
    if set(obj)!={f.name for f in fields(cls)}: raise ValueError('POLICY_FIELDS_INVALID')
    integers={'position_ceiling','max_grid_points'}; strings={'name','evidence'}
    return cls(**{k:v if k in integers|strings else decimal_text(v) for k,v in obj.items()})


class ConfigurationService:
    def __init__(self,store,context,clock=lambda:datetime.now(timezone.utc)):
        if context.get('classification')!='SYNTHETIC_TEST_ONLY':raise ValueError('ISOLATED_CONTEXT_REQUIRED')
        identity(context['scope'])
        self.store,self.context,self.clock=store,context,clock

    def install(self):
        self.store.execute(Path(__file__).with_name('r20_configuration_schema.sql').read_text(encoding='utf-8'))

    def history(self):
        text=self.store.execute(f"SELECT payload FROM r20_v2_config.events WHERE scope={sql_text(self.context['scope'])} ORDER BY revision;")
        rows=[strict_json(line) for line in text.splitlines()];prev=''
        for i,row in enumerate(rows):
            material={k:v for k,v in row.items() if k!='hash'}
            if row['revision']!=i+1 or row['previous']!=prev or digest(material)!=row['hash']:
                raise ValueError('CONFIG_CHAIN_INTEGRITY')
            prev=row['hash']
        return rows

    def profile(self,values,version,at):
        if not isinstance(values,dict) or set(values)!=set(FIELDS) or any(values[k] in ('',None) for k in FIELDS):
            raise ValueError('FIELDS_REQUIRED')
        if not isinstance(values['max_open_positions'],str) or not values['max_open_positions'].isascii() or not values['max_open_positions'].isdigit():
            raise ValueError('POSITIVE_INTEGER_REQUIRED')
        h=self.store.load(self.context['scope'])
        if h is None:raise ValueError('ACCOUNTING_CONTEXT_MISSING')
        base=h.snapshot.profile
        c=typed(CostModel,self.context['costs']) if self.context.get('costs') else None
        l=typed(Limits,self.context['limits']) if self.context.get('limits') else None
        return EconomicProfile(max(version,h.snapshot.daily.profile_version+1),base.scope_id,base.capital_base_usd,base.equity_cap_usd,
            *(decimal_text(values[k]) for k in FIELDS[:4]),int(values[FIELDS[4]]),
            at,economic_day(at)[2],at,c.policy_hash if c else digest({'cost':'UNKNOWN'}),
            l.policy_hash if l else digest({'limits':'UNKNOWN'}))

    def daily(self,profile,at):
        accounting=self.store._rows(self.context['scope'])
        h=accounting[-1][1] if accounting else None
        if h is None:raise ValueError('ACCOUNTING_CONTEXT_MISSING')
        d=h.snapshot.daily
        if d.day_id!=economic_day(at)[0]:raise ValueError('DAY_BOUNDARY_UNVERIFIED')
        if not d.inventory_verified:raise ValueError('INVENTORY_RECONCILIATION_REQUIRED')
        # Preview never changes the accounting ledger or the profile on existing positions.
        p=profile
        d=d.observe(p,at,d.current_equity,d.open_terms,d.pending_terms)
        activated=[x for x in self.history() if x['lifecycle']=='ACTIVATED_FOR_SHADOW' and x['day']==d.day_id]
        cap=min([d.budget]+[decimal_text(x['dailyBudget']) for x in activated])
        crossed=False
        for _,head in accounting:
            past=head.snapshot.daily
            if past.day_id!=d.day_id:continue
            applicable=[decimal_text(x['dailyBudget']) for x in activated if utc(datetime.fromisoformat(x['at']))<=past.at]
            crossed=crossed or past.loss_blocked or past.used_loss>=min([past.budget]+applicable)
        return replace(d,budget=cap,loss_blocked=d.loss_blocked or crossed or d.used_loss>=cap),p,h

    def preview(self,values):
        at=utc(self.clock());blockers=[];assessment=None;profile=None;daily=None
        try:
            rows=self.history()
            version=max([x['revision'] for x in rows]+[0])+1
            saved=next((x for x in reversed(rows) if x['profile'] and x['values']==values),None)
            p=EconomicProfile.from_json(encoded(saved['profile'])) if saved else self.profile(values,version,at)
            if not p.valid_at(at):raise ValueError('PROFILE_EXPIRED')
            profile=strict_json(p.to_json())
            daily,p,h=self.daily(p,at)
            blockers.extend(self.context.get('cost_unknowns',[]))
            if not self.context.get('costs'):blockers.append('COST_POLICY_UNKNOWN')
            if not self.context.get('limits'):blockers.append('MARGIN_POLICY_UNKNOWN')
            if daily.loss_blocked:blockers.append('DAILY_LOSS_BLOCKED')
            blockers.extend(daily.operational_blocks)
            if not blockers:
                c=self.context
                args={k:decimal_text(c[k]) for k in ('price','stop_distance','free_margin','existing_exposure',
                     'committed_margin','liquidity_quantity','pending_costs')}
                assessment=asdict(size(profile=p,at=at,side=c['side'],economic_equity=daily.current_equity,
                    open_positions=len(daily.open_terms),pending_positions=len(daily.pending_terms),daily=daily,
                    costs=typed(CostModel,c['costs']),limits=typed(Limits,c['limits']),
                    stresses=tuple(typed(Stress,s) for s in c['stresses']),**args))
        except (ValueError,KeyError,TypeError) as exc:
            reason=str(exc) if isinstance(exc,ValueError) else 'CONTEXT_INCOMPLETE'
            blockers.append(reason)
        return canonical(dict(profile=profile,assessment=assessment,blockers=sorted(set(blockers)),
            daily=daily_payload(daily) if daily else None,classification=self.context['classification'],
            executionEnabled=False,cohortStarted=False,costProvenance=self.cost_provenance()))

    def cost_provenance(self):
        return dict(spread='OBSERVED_HISTORICAL_P50_0.2_PIP_NOT_A_DEFAULT',
            tariff='PUBLISHED_IBKR_TIER_I_MIN_2_USD_PER_ORDER_NOT_CONFIRMED',
            commissions='SYNTHETIC_ESTIMATE' if self.context.get('costs') else 'UNKNOWN',
            slippage='UNKNOWN' if 'SLIPPAGE_UNKNOWN' in self.context.get('cost_unknowns',[]) else 'SYNTHETIC_ASSUMPTION',
            financing='UNKNOWN' if 'FINANCING_UNKNOWN' in self.context.get('cost_unknowns',[]) else 'SYNTHETIC_ASSUMPTION',
            evidence=self.context['evidence'],brokerConfirmed=False)

    def view(self):
        at=utc(self.clock());rows=self.history();last=rows[-1] if rows else None
        active=next((x for x in reversed(rows) if x['lifecycle']=='ACTIVATED_FOR_SHADOW'),None)
        valid=active and EconomicProfile.from_json(encoded(active['profile'])).valid_at(at)
        lifecycle=last['lifecycle'] if last else None
        status='EXPIRED' if active and not valid else lifecycle or 'BLOCKED'
        h=self.store.load(self.context['scope']);d=h.snapshot.daily if h else None
        blockers=list(self.context.get('cost_unknowns',[]))
        if not valid:blockers.append('NO_APPROVED_CURRENT_PROFILE')
        if d:
            if d.loss_blocked:blockers.append('DAILY_LOSS_BLOCKED')
            blockers.extend(d.operational_blocks)
            if d.day_id!=economic_day(at)[0]:blockers.append('DAY_BOUNDARY_UNVERIFIED')
        else:blockers.append('ACCOUNTING_CONTEXT_MISSING')
        if valid:
            p=EconomicProfile.from_json(encoded(active['profile']))
            try:d,_,_=self.daily(p,at)
            except ValueError as exc:blockers.append(str(exc))
            if d and d.loss_blocked:blockers.append('DAILY_LOSS_BLOCKED')
            if active['contextHash']!=digest(self.context):blockers.append('CONTEXT_CHANGED_REVALIDATE')
        if valid and blockers:status='BLOCKED'
        if valid and not blockers:status='ACTIVATED_FOR_SHADOW'
        return canonical(dict(revision=last['revision'] if last else 0,lifecycle=lifecycle,status=status,
            day=economic_day(at)[0],timezone='America/Santo_Domingo',at=at,
            currentProfile=active['profile'] if valid else None,latest=last,history=rows,
            daily=daily_payload(d) if d else None,blockers=sorted(set(blockers)),
            accountingRevision=h.revision if h else None,accountingHash=h.hash if h else None,
            classification='SYNTHETIC_TEST_ONLY',costProvenance=self.cost_provenance(),
            executionEnabled=False,cohortStarted=False,ordersSupported=False))

    def command(self,action,body,actor):
        if action not in ('draft','validate','activate'):raise ValueError('ACTION_INVALID')
        identity(actor)
        expected={'revision','requestId','values'} if action=='draft' else {'revision','requestId'}
        if not isinstance(body,dict) or set(body)!=expected:raise ValueError('COMMAND_FIELDS')
        identity(body['requestId'])
        if type(body['revision']) is not int or body['revision']<0:raise ValueError('REVISION_REQUIRED')
        reqhash=digest(dict(action=action,body=body,actor=actor));rows=self.history()
        for row in rows:
            if row['requestId']==body['requestId']:
                if row['requestHash']!=reqhash:raise ValueError('IDEMPOTENCY_CONFLICT')
                return row
        last=rows[-1] if rows else None;revision=last['revision'] if last else 0
        if revision!=body['revision']:raise ValueError('CAS_CONFLICT')
        at=utc(self.clock());h=self.store.load(self.context['scope'])
        if h is None:raise ValueError('ACCOUNTING_CONTEXT_MISSING')
        profile=None;budget=None
        if action=='draft':
            values=body['values']
            if not isinstance(values,dict) or not set(values)<=set(FIELDS) or any(not isinstance(v,str) or len(v)>96 for v in values.values()):
                raise ValueError('DRAFT_FIELDS')
            lifecycle='DRAFT'
        else:
            if last is None or last['lifecycle']!=('DRAFT' if action=='validate' else 'VALIDATED'):
                raise ValueError('STATE_TRANSITION')
            values=last['values']
            if action=='validate':
                p=self.profile(values,revision+1,at);profile=strict_json(p.to_json());lifecycle='VALIDATED'
            else:
                p=EconomicProfile.from_json(encoded(last['profile']))
                if not p.valid_at(at):raise ValueError('PROFILE_EXPIRED')
                if last['contextHash']!=digest(self.context):raise ValueError('CONTEXT_CHANGED_REVALIDATE')
                preview=self.preview(values)
                if preview['blockers']:raise ValueError('CONFIGURATION_BLOCKED')
                d,_,_=self.daily(p,at);budget=str(d.budget)
                profile=last['profile'];lifecycle='ACTIVATED_FOR_SHADOW'
        row=canonical(dict(revision=revision+1,previous=last['hash'] if last else '',requestId=body['requestId'],
            requestHash=reqhash,actor=actor,at=at,day=economic_day(at)[0],lifecycle=lifecycle,values=values,
            profile=profile,dailyBudget=budget,contextHash=digest(self.context),accountingHash=h.hash))
        row['hash']=digest(row)
        self.store.execute('SELECT r20_v2_config.append_event('+','.join((sql_text(self.context['scope']),
            str(revision),sql_text(row['previous']),sql_text(body['requestId']),sql_text(reqhash),
            sql_text(h.hash),sql_text(encoded(row))))+');')
        # Read persisted receipt; SQL handles the concurrent identical request case.
        return next(x for x in self.history() if x['requestId']==body['requestId'])


def main():
    request=strict_json(sys.stdin.read(65537))
    if not isinstance(request,dict) or set(request)!={'action','body','actor'}:raise ValueError('REQUEST_FIELDS')
    from .r20_admission import RoleStore
    store=RoleStore(os.environ['R20_V2_TEST_DATABASE'],os.environ['R20_V2_TEST_SYSTEM_ID'],os.environ['R20_V2_DB_ROLE'])
    context=strict_json(Path(os.environ['R20_V2_CONTEXT']).read_text(encoding='utf-8'))
    service=ConfigurationService(store,context)
    if request['action'].startswith('preparation-'):
        from .r20_preparation import PreparationService
        preparation=PreparationService(store,context)
        action=request['action'].removeprefix('preparation-')
        if action=='view':
            if request['body']!={}:raise ValueError('READ_ONLY')
            result=preparation.view()
        elif action=='preview':
            if not isinstance(request['body'],dict) or set(request['body']) not in ({'values'},{'values','purpose'}):raise ValueError('PREVIEW_FIELDS')
            result=preparation.preview(request['body']['values'],request['body'].get('purpose','NORMAL'))
        else:result=preparation.command(action,request['body'],request['actor'])
    elif request['action']=='monitor':
        if request['body']!={}:raise ValueError('MONITOR_READ_ONLY')
        from .r20_monitor import monitor
        result=monitor(store,context,authentic_evidence=os.environ.get('R20_AUTHENTIC_READ_EVIDENCE'))
    elif request['action']=='view':result=service.view()
    elif request['action']=='preview':
        if not isinstance(request['body'],dict) or set(request['body'])!={'values'}:raise ValueError('PREVIEW_FIELDS')
        result=service.preview(request['body']['values'])
    else:result=service.command(request['action'],request['body'],request['actor'])
    print(encoded(dict(result=result)))

if __name__=='__main__':
    try:main()
    except (ValueError,KeyError,TypeError) as exc:
        code=str(exc) if isinstance(exc,ValueError) else 'INVALID_REQUEST'
        print(encoded(dict(error=code)));sys.exit(2)
    except Exception:
        print(encoded(dict(error='CONFIGURATION_STORAGE_UNAVAILABLE')));sys.exit(3)
