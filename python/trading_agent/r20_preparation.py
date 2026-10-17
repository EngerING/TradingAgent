"""Versioned preparation only. No activation, runner or broker authority.

The existing economic solver is reused; old EconomicProfile payloads/hashes are
not reinterpreted. Storage is restricted by TestStore to the isolated cluster.
"""
from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from .r20_profiles import canonical, decimal_text, digest, economic_day, encoded, strict_json, utc, number
from .r20_economics import exact, identity
from .r20_configuration import ConfigurationService, typed
from .r20_profiles import EconomicProfile
from .r20_sizing import AllocationRequest, CostModel, Limits, Stress, size
from .r20_persistence import sql_text

FIELDS=('logical_capital_usd','allocation_usd','requested_allocation_leverage',
        'risk_per_trade_pct','daily_loss_limit_pct','max_open_positions','environment')


def validate_purpose(purpose,environment):
    if purpose not in ('NORMAL','TECHNICAL_VALIDATION'):raise ValueError('PURPOSE_REQUIRED')
    if purpose=='TECHNICAL_VALIDATION' and environment!='SHADOW':raise ValueError('TECHNICAL_SHADOW_ONLY')
    return purpose


def validate_values(values):
    if not isinstance(values,dict) or set(values)!=set(FIELDS): raise ValueError('PREPARATION_FIELDS_REQUIRED')
    if any(not isinstance(v,str) or not v or len(v)>96 for v in values.values()):
        raise ValueError('EXPLICIT_VALUES_REQUIRED')
    if values['environment'] not in ('SHADOW','IBKR_PAPER'): raise ValueError('ENVIRONMENT_INVALID')
    parsed={k:decimal_text(values[k]) for k in FIELDS[:5]}
    for v in parsed.values():number(v,positive=True)
    if parsed['requested_allocation_leverage']<1:raise ValueError('ALLOCATION_LEVERAGE_MINIMUM_ONE')
    if any(parsed[k]>100 for k in ('risk_per_trade_pct','daily_loss_limit_pct')):raise ValueError('PERCENT_OUT_OF_RANGE')
    count=values['max_open_positions']
    if not count.isascii() or not count.isdigit() or not 0<int(count)<=1_000_000:raise ValueError('POSITIVE_INTEGER_REQUIRED')
    return dict(parsed,max_open_positions=int(count),environment=values['environment'])


@exact
def theoretical(values):
    result=dict(exposure_target_usd=None,target_account_leverage=None)
    try:
        a=decimal_text(values['allocation_usd']);l=decimal_text(values['requested_allocation_leverage'])
        number(a,positive=True);number(l,minimum=Decimal(1));result['exposure_target_usd']=a*l
        e=decimal_text(values['logical_capital_usd']);number(e,positive=True)
        result['target_account_leverage']=a*l/e
    except (KeyError,TypeError,ValueError):pass
    return canonical(result)


class PreparationService(ConfigurationService):
    def install(self):
        self.store.execute(Path(__file__).with_name('r20_preparation_schema.sql').read_text(encoding='utf-8'))

    def history(self):
        text=self.store.execute('SELECT payload FROM r20_v2_config.preparations WHERE scope='+sql_text(self.context['scope'])+' ORDER BY revision;')
        rows=[strict_json(line) for line in text.splitlines()];prev=''
        for i,row in enumerate(rows):
            if row['revision']!=i+1 or row['previous']!=prev or digest({k:v for k,v in row.items() if k!='hash'})!=row['hash']:
                raise ValueError('PREPARATION_CHAIN_INTEGRITY')
            p=row['profile']
            if digest({k:v for k,v in p.items() if k!='configuration_hash'})!=p['configuration_hash']:
                raise ValueError('PREPARATION_PROFILE_INTEGRITY')
            prev=row['hash']
        return rows

    @exact
    def preview(self,values,purpose='NORMAL'):
        summary=theoretical(values);problems=[];assessment=None;profile=None;account_leverage=None
        try:
            parsed=validate_values(values)
            validate_purpose(purpose,parsed['environment'])
        except ValueError as exc:parsed=None;problems.append(str(exc))
        c=self.context
        unknowns=list(c.get('cost_unknowns',[]))
        if not c.get('costs'):unknowns.append('COST_POLICY_UNKNOWN')
        if not c.get('limits'):unknowns.append('MARGIN_POLICY_UNKNOWN')
        if c.get('aggregate_leverage_cap') is None:unknowns.append('AGGREGATE_LEVERAGE_CAP_UNKNOWN')
        if parsed and not unknowns:
            try:
                h=self.store.load(c['scope'])
                if h is None:raise ValueError('ACCOUNTING_CONTEXT_MISSING')
                if parsed['logical_capital_usd']!=h.snapshot.profile.capital_base_usd:
                    raise ValueError('LOGICAL_CAPITAL_CONTEXT_MISMATCH')
                at=utc(self.clock());costs=typed(CostModel,c['costs']);limits=typed(Limits,c['limits'])
                cap=decimal_text(c['aggregate_leverage_cap'])
                p=EconomicProfile(h.snapshot.daily.profile_version+1,c['scope'],parsed['logical_capital_usd'],
                    h.snapshot.profile.equity_cap_usd,parsed['risk_per_trade_pct'],Decimal(100),cap,
                    parsed['daily_loss_limit_pct'],parsed['max_open_positions'],at,economic_day(at)[2],at,
                    costs.policy_hash,limits.policy_hash)
                # Existing accounting and configuration latches are read, never replaced.
                daily,_,_=ConfigurationService(self.store,c,self.clock).daily(p,at)
                args={k:decimal_text(c[k]) for k in ('price','stop_distance','free_margin','existing_exposure',
                    'committed_margin','liquidity_quantity','pending_costs')}
                eligible=max(Decimal(0),daily.current_equity-args['pending_costs'])
                if p.equity_cap_usd is not None:eligible=min(eligible,p.equity_cap_usd)
                if eligible>0:account_leverage=args['existing_exposure']/eligible
                a=size(profile=p,at=at,side=c['side'],economic_equity=daily.current_equity,
                    daily=daily,open_positions=len(daily.open_terms),pending_positions=len(daily.pending_terms),
                    costs=costs,limits=limits,stresses=tuple(typed(Stress,s) for s in c['stresses']),
                    allocation_request=AllocationRequest(parsed['allocation_usd'],parsed['requested_allocation_leverage']),purpose=purpose,**args)
                assessment=asdict(a);profile=strict_json(p.to_json())
            except (ValueError,KeyError,TypeError) as exc:
                unknowns.append(str(exc) if isinstance(exc,ValueError) else 'CONTEXT_INCOMPLETE')
        return canonical(dict(contractVersion=2,classification='SYNTHETIC_TEST_ONLY',
            structurallyValid=parsed is not None,validationErrors=problems,unknowns=sorted(set(unknowns)),
            **summary,account_leverage=account_leverage,aggregate_leverage_cap=c.get('aggregate_leverage_cap'),
            assessment=assessment,solverProfile=profile,confirmed_margin_usd=None,
            executionEnabled=False,ordersSupported=False,cohortStarted=False))

    def view(self):
        rows=self.history();last=rows[-1] if rows else None;at=utc(self.clock())
        expired=bool(last and at>=datetime.fromisoformat(last['profile']['effective_until'].replace('Z','+00:00')))
        safety=self.context.get('safety',{})
        # Server-provided observation only; absence/age is not live confirmation.
        return canonical(dict(contractVersion=2,classification='SYNTHETIC_TEST_ONLY',revision=len(rows),
            latest=last,history=rows,status='EXPIRED' if expired else last['lifecycle'] if last else 'NO_ACTIVADO',
            activeProfile=None,executionEnabled=False,ordersSupported=False,cohortStarted=False,
            timezone='America/Santo_Domingo',at=at,day=economic_day(at)[0],
            controls=dict(start=False,stop=False,switchEnvironment=False,effectiveEnvironment=None,
                reason='OPERATIONAL_BACKEND_NOT_AUTHORIZED'),
            readiness=dict(shadow='BLOCKED',paper='BLOCKED',live='BLOCKED',
                reasons=['NO_OPERATIONAL_PROFILE','NO_SHADOW_PERMISSION','NO_PAPER_PERMISSION','COST_MARGIN_GATES_PENDING']),
            safety=dict(emergency=safety.get('emergency','UNKNOWN'),live=safety.get('live','BLOCKED_BY_DESIGN'),
                ibkr=safety.get('ibkr','UNKNOWN'),observedAt=safety.get('observedAt'),
                provenance='HISTORICAL_READ_ONLY_SNAPSHOT' if safety else 'UNAVAILABLE'),
            costProvenance=self.cost_provenance()))

    def command(self,action,body,actor):
        if action not in ('save','validate'):raise ValueError('OPERATIONAL_CONTROL_DISABLED')
        identity(actor)
        expected={'revision','requestId','values'} if action=='save' else {'revision','requestId'}
        if not isinstance(body,dict) or set(body) not in (expected,expected|{'purpose'} if action=='save' else expected):raise ValueError('COMMAND_FIELDS')
        identity(body['requestId'])
        if type(body['revision']) is not int or body['revision']<0:raise ValueError('REVISION_REQUIRED')
        reqhash=digest(dict(action=action,body=body,actor=actor));rows=self.history()
        for row in rows:
            if row['requestId']==body['requestId']:
                if row['requestHash']!=reqhash:raise ValueError('IDEMPOTENCY_CONFLICT')
                return row
        if len(rows)!=body['revision']:raise ValueError('CAS_CONFLICT')
        at=utc(self.clock());last=rows[-1] if rows else None
        if action=='save':
            validate_values(body['values'])
            purpose=validate_purpose(body.get('purpose','NORMAL'),body['values']['environment'])
            profile=canonical(dict(contract_version=2,configuration_version=len(rows)+1,
                profile_id=self.context['scope']+'-'+str(len(rows)+1),scope=self.context['scope'],values=body['values'],
                effective_from=at,effective_until=economic_day(at)[2],created_at=at,
                economic_timezone='America/Santo_Domingo',purpose=purpose,activation='NOT_ACTIVATED'))
            profile['configuration_hash']=digest(profile);lifecycle='GUARDADO'
        else:
            if not last or last['lifecycle']!='GUARDADO':raise ValueError('STATE_TRANSITION')
            profile=last['profile'];validate_values(profile['values'])
            if at>=datetime.fromisoformat(profile['effective_until'].replace('Z','+00:00')):raise ValueError('PROFILE_EXPIRED')
            lifecycle='VALIDO'
        row=canonical(dict(revision=len(rows)+1,previous=last['hash'] if last else '',requestId=body['requestId'],
            requestHash=reqhash,actor=actor,at=at,lifecycle=lifecycle,profile=profile,
            contextHash=digest(self.context),executionEnabled=False,activation='NOT_ACTIVATED'))
        row['hash']=digest(row)
        self.store.execute('SELECT r20_v2_config.append_preparation('+','.join((sql_text(self.context['scope']),
            str(len(rows)),sql_text(row['previous']),sql_text(body['requestId']),sql_text(reqhash),sql_text(encoded(row))))+');')
        return next(x for x in self.history() if x['requestId']==body['requestId'])
