"""Paper-only exploratory cohort. No strategy promotion and no model authority.

PostgreSQL is authoritative; SEND_PENDING precedes the first SDK mutation.
A crash never repeats it. Account-wide OS mutex is held by the runner.
"""
import copy
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_FLOOR
import json
import os
from pathlib import Path
import re
import subprocess
from uuid import uuid4
from .eurusd_paper_research import number as N, instant, encoded, sha, ZONE

MODE='EURUSD_PAPER_EXPLORATORY'
CLASS='EXPLORATORY_NOT_VALIDATED'
PROFILES=('EURUSD_R1','EURUSD_R5','EURUSD_R10')
RATES=('0.01','0.05','0.10')
TERMINAL={'Filled','Cancelled','ApiCancelled','Rejected','Inactive'}
BASELINE_VERSION='9860cd16f4f43d38ca7c29f161aea82e17dea100da48bb78259457cc31133211'

def now(): return datetime.now(timezone.utc)
def day(at): return instant(at).astimezone(ZONE).date().isoformat()

class Journal:
    def __init__(self,root,cohort):
        self.root=Path(root)
        if not re.fullmatch(r'eurusd-explore-[a-f0-9]{32}',cohort):raise ValueError('COHORT_SCOPE_REQUIRED')
        self.cohort=cohort
    def call(self,data):
        r=subprocess.run(['dotnet',str(self.root/'src/TradingAgent.Api/bin/Debug/net9.0/TradingAgent.Api.dll'),'--eurusd-exploratory-journal'],
            input=encoded(dict(cohort=self.cohort,**data)).decode(),text=True,capture_output=True,cwd=self.root,timeout=15)
        try: result=json.loads(r.stdout)
        except ValueError: raise RuntimeError('EXPLORATORY_POSTGRES_UNAVAILABLE') from None
        if r.returncode or result.get('error'):raise RuntimeError('EXPLORATORY_POSTGRES_UNAVAILABLE_OR_CONFLICT')
        return result
    def load(self): return self.call({})
    def commit(self,revision,previous,data):
        material=encoded([revision,data,previous]).decode()
        return self.call(dict(event=dict(revision=revision,payload=encoded(data).decode(),previous=previous,hash=sha([revision,data,previous]),material=material)))

class Rotator:
    def __init__(self,journal,clock=now):
        self.journal,self.clock=journal,clock;self.reload()
    def reload(self):
        h=self.journal.load();self.revision,self.head=h['revision'],h['hash']
        self.conflicting_cohorts=h.get('conflicting_cohorts',[])
        self.state=json.loads(h['payload'])['state'] if h.get('payload') else None
        if h.get('payload'):
            p=json.loads(h['payload'])
            if sha([self.revision,p,p['previous']])!=self.head or p['cohort_id']!=self.journal.cohort or p['scope']!=MODE or p['live_enabled'] is not False:
                raise PermissionError('EXPLORATORY_JOURNAL_INTEGRITY_FAILED')
        return self.state
    def append(self,event,details=None):
        names={'SEND_PENDING':'PAPER_INTENT_PERSISTED','BRACKET_TRANSPORT_ATTEMPTED':'PAPER_ORDER_SUBMITTED','PROFILE_SKIPPED':'PROFILE_SKIPPED','PROTECTION_ACKNOWLEDGED':'PROTECTION_CONFIRMED',
            'COMMISSION_PENDING':'COMMISSION_RECORDED','STRICT_ACCOUNT_RECONCILED':'TRADE_RECONCILED','INCIDENT_GLOBAL_STOP':'RECOVERY_REQUIRED',
            'CLOSED_COMMISSION_RECONCILED_RESERVE_RELEASED_ROTATED':'TRADE_RECONCILED','OPPORTUNITY_REVIEWED':'PAPER_BLOCKED',
            'OWNED_RULE_EXIT_PENDING':'PAPER_EXIT','OWNED_RECOVERY_SEND_PENDING':'RECOVERY_REQUIRED'}
        rows=[]
        if event=='BROKER_CALLBACKS':
            names_by_kind={'fill':'PAPER_FILL','commission':'COMMISSION_RECORDED','open_order':'PAPER_ORDER_ACK','status':'PAPER_POSITION_UPDATED','completed_order':'PAPER_EXIT'}
            rows=[dict(kind=names_by_kind[e['kind']],detail=e.get('exec_id',str(e.get('order_id','')))) for e in (details or {}).get('events',[]) if e['kind'] in names_by_kind]
        elif event in names:rows=[dict(kind=names[event],detail=(details or {}).get('reason',event))]
        for index,row in enumerate(rows):
            row.update(id=f'{self.journal.cohort}:{self.revision+1}:{index}',at=self.clock().isoformat(),profile=(self.state.get('active') or {}).get('profile'),origin='POSTGRESQL_PAPER_JOURNAL')
            self.state.setdefault('paper_feed',[]).append(row)
        self.state['paper_feed']=self.state.get('paper_feed',[])[-200:]
        data=dict(cohort_id=self.journal.cohort,scope=MODE,classification=CLASS,live_enabled=False,
                  at=self.clock().isoformat(),event=event,previous=self.head,state=self.state,details=details or {})
        h=self.journal.commit(self.revision+1,self.head,data)
        self.revision,self.head=h['revision'],h['hash']
    def prepare(self,strategy,costs,provenance,binding_id,engine_hashes,reference_signal=None,purpose='PAPER_EXPLORATORY_RESEARCH'):
        if self.state is not None:raise ValueError('COHORT_ALREADY_EXISTS')
        if strategy['strategy_version']!=BASELINE_VERSION or strategy['version']!=1:raise PermissionError('BASELINE_EXACT_VERSION_REQUIRED')
        if purpose not in ('PAPER_EXPLORATORY_RESEARCH','PAPER_EXECUTION_DIAGNOSTIC'):raise ValueError('EXPERIMENT_PURPOSE_REQUIRED')
        protocol=dict(strategy=strategy,costs=costs,provenance=provenance,binding_id=binding_id,engine_hashes=engine_hashes,reference_signal=reference_signal,
            policy='WIN_TO_CONTINUE / FIRST_LOSS_STOPS_DAY',capital_per_profile='100',exposure_cap='100',
            daily_broker_close_limit=3,rotation=list(PROFILES),rates=list(RATES),baseline_reason='EXISTING_TREND_V1_EXIT_PARITY_TECHNICAL_BASELINE_NOT_ECONOMIC_WINNER',
            strategy_validation_gate='NO_VIABLE_STRATEGY_FOUND',protection_failure_is_not_bounded_loss=True,
            protocol_version=2,purpose=purpose,max_openings=1,max_authorization_minutes=30,
            rotation_policy='SKIP_WITH_REASON',selection_bias='Sequential allocation; unequal times and sample sizes; not a randomized comparison',
            diagnostic_close_seconds=60,protection_ack_seconds=10)
        self.state=dict(protocol=protocol,rotation=0,active=None,trials=[],seen=[],closed_days={},global_stop=None,
            status='PREPARED_NOT_AUTHORIZED',emergency_review=None,profiles={p:dict(equity='100',consumed_loss='0',reserved='0',
                stopped_days={},broker_trades=[],shadow_trades=[],blockers=['NOT_AUTHORIZED']) for p in PROFILES})
        self.append('COHORT_PREREGISTERED',dict(protocol_hash=sha(protocol)))
        return self.status()
    def select_profile(self,signal,quote):
        """Skip deterministic sizing/daily stops only; never skip authorization or UNKNOWN gates."""
        decisions={p:self.size(p,signal,quote) for p in PROFILES}
        self.state['last_opportunity']=dict(at=self.clock().isoformat(),signal=copy.deepcopy(signal),decisions=decisions,
            shadow_mode='SHADOW_SIZING_ONLY_NOT_A_FILL',selection_bias=self.state['protocol'].get('selection_bias'))
        for p,d in decisions.items():
            self.state['profiles'][p]['eligibility']='NUMERIC_ONLY_EXECUTION_UNVERIFIED' if d['admitted'] else 'BROKER_INELIGIBLE' if d['reason'] in ('COMMISSION_EXCEEDS_RISK_BUDGET','BROKER_SIZE_CONSTRAINT','CUMULATIVE_LOSS_LIMIT') else 'NO_TRADE'
        if self.state['protocol'].get('rotation_policy')!='SKIP_WITH_REASON':return
        if self.state['active']:return
        for _ in PROFILES:
            p=PROFILES[self.state['rotation']];d=decisions[p]
            if d['admitted']:break
            self.state.setdefault('skips',[]).append(dict(profile=p,signal_id=signal['opportunity_id'],at=self.clock().isoformat(),reason=d['reason']))
            self.state['rotation']=(self.state['rotation']+1)%len(PROFILES)
            self.append('PROFILE_SKIPPED',dict(profile=p,reason=d['reason'],signal_id=signal['opportunity_id'],next_profile=PROFILES[self.state['rotation']]))
        self.append('COMMON_OPPORTUNITY_ASSESSED',self.state['last_opportunity'])
    def status(self):
        return dict(cohort=self.journal.cohort,revision=self.revision,next_profile=PROFILES[self.state['rotation']],
            state=self.state,live_enabled=False,orders_sent=None if self.state.get('opening_attempts',0) else 0)
    def fail(self,reason):
        self.state['global_stop']=reason;self.state['status']='SUSPENDED';self.append('INCIDENT_GLOBAL_STOP',dict(reason=reason))
    def size(self,profile,signal,quote):
        i=PROFILES.index(profile);p=self.state['profiles'][profile];c=self.state['protocol']['costs']
        equity=N(p['equity']);budget=min(equity*N(RATES[i]),N(20)-N(p['consumed_loss']))
        result=dict(profile=profile,quantity='0',budget=str(max(Decimal(0),budget)),risk='0',notional='0',costs=None,
            reason=None,admitted=False,execution_mode='BROKER_PAPER_EXECUTION',strategy_validation_gate='NO_VIABLE_STRATEGY_FOUND')
        fixed=N(c['openingCommission'])+N(c['closingCommission'])
        result['commissions']=str(fixed)
        if day(self.clock().isoformat()) in p['stopped_days']:result['reason']='STOPPED_FOR_DAY';return result
        if budget<=0:result['reason']='CUMULATIVE_LOSS_LIMIT';return result
        if fixed>=budget:result['reason']='COMMISSION_EXCEEDS_RISK_BUDGET';return result
        entry=N(quote['ask']);stop=N(signal['stop_distance']);target=N(signal['take_profit_distance'])
        spread=max(N(quote['ask'])-N(quote['bid']),N(c['spread']));slip=2*N(c['slippage']);gap=N(c['adverseGap'])
        if min(entry,stop,target)<=0 or stop>=entry:raise ValueError('INVALID_SIGNAL_GEOMETRY')
        midpoint=N(signal.get('entry_midpoint',entry));original_stop=midpoint-stop;original_target=midpoint+target;tick=N('0.00005')
        # Record execution quantization without changing the original parameters.
        stop_level=(original_stop/tick).to_integral_value(rounding=ROUND_FLOOR)*tick
        target_level=(original_target/tick).to_integral_value(rounding=ROUND_FLOOR)*tick
        entry=(entry/tick).to_integral_value(rounding='ROUND_CEILING')*tick
        if not 0<stop_level<entry<target_level:result['reason']='BROKER_PRICE_GEOMETRY_CONSTRAINT';return result
        stop=entry-stop_level;target=target_level-entry
        unit=stop+spread+slip+gap;variable=spread+slip+gap;step=N(c['quantityStep'])
        quantity=(min(N(100),(budget-fixed)/unit,(min(equity,N(100))-N(p['reserved'])-fixed)/(entry+variable))/step).to_integral_value(rounding=ROUND_FLOOR)*step
        if quantity<N(c['minimumQuantity']):result['reason']='BROKER_SIZE_CONSTRAINT';return result
        costs=fixed+quantity*variable;risk=fixed+quantity*unit;notional=quantity*entry
        result.update(quantity=str(quantity),risk=str(risk),notional=str(notional),costs=str(costs),
            stop=str(stop_level),target=str(target_level),original_stop=str(original_stop),original_target=str(original_target),entry=str(entry),spread=str(spread),slippage=str(slip),gap=str(gap),
            gross_target=str(quantity*target),net_target=str(quantity*target-costs),reservation=str(notional+costs),
            reward_risk=str((quantity*target-costs)/risk),prior_ev=None,admitted=risk<=budget and notional+costs<=min(equity,N(100)))
        result['reason']=None if result['admitted'] else 'EXPERIMENTAL_RISK_OR_CAPITAL_EXCEEDED'
        return result
    def gates(self,signal,quote,evidence,authorized,emergency):
        profile=PROFILES[self.state['rotation']];p=self.state['profiles'][profile];at=self.clock().isoformat();reasons=[]
        if self.state['active']:reasons.append('ACCOUNT_NETTING_ACTIVE_TRIAL')
        if self.state['global_stop']:reasons.append(self.state['global_stop'])
        if emergency:reasons.append('EMERGENCY_STOP_ACTIVE')
        if not authorized:reasons.append('PAPER_EXPLORATORY_AUTHORIZATION_REQUIRED')
        if self.state['protocol'].get('protocol_version')==2 and self.state.get('opening_attempts',0)>=self.state['protocol']['max_openings']:reasons.append('SUPERVISED_TRIAL_CONSUMED_NEW_APPROVAL_REQUIRED')
        if getattr(self,'conflicting_cohorts',[]):reasons.append('OTHER_COHORT_PENDING_INTENT_OR_RESERVATION')
        if day(at) in p['stopped_days']:reasons.append('STOPPED_FOR_DAY')
        if N(p['consumed_loss'])>=20:reasons.append('CUMULATIVE_LOSS_LIMIT')
        if self.state['closed_days'].get(day(at),0)>=3:reasons.append('DAILY_GLOBAL_THREE_CLOSE_LIMIT')
        if signal.get('opportunity_id') in self.state['seen']:reasons.append('DUPLICATE_SIGNAL')
        if signal.get('strategy_version')!=self.state['protocol']['strategy']['strategy_version']:reasons.append('COHORT_STRATEGY_MISMATCH')
        diagnostic=self.state['protocol'].get('purpose')=='PAPER_EXECUTION_DIAGNOSTIC'
        if diagnostic:
            if signal.get('execution_purpose')!='PAPER_EXECUTION_DIAGNOSTIC' or signal.get('predictive_validation') is not False:reasons.append('DIAGNOSTIC_NOT_A_STRATEGY_SIGNAL')
        elif signal.get('execution_purpose')=='PAPER_EXECUTION_DIAGNOSTIC':reasons.append('DIAGNOSTIC_NOT_A_STRATEGY_SIGNAL')
        if signal.get('strategy_id') not in ('trend',self.state['protocol']['strategy'].get('strategy_id')):reasons.append('COHORT_STRATEGY_MISMATCH')
        if signal.get('side')!='BUY':reasons.append('EXPLORATORY_LONG_ONLY_NO_SHORT')
        if signal.get('reasons') or not signal.get('entry_at') or not signal.get('opportunity_id'):reasons.append('NO_VALID_ORIGINAL_SIGNAL')
        elif not 0<=(self.clock()-instant(signal['entry_at'])).total_seconds()<=5 or instant(signal['signal_at'])>instant(signal['entry_at']):reasons.append('LATE_OR_FUTURE_SIGNAL')
        for frame in signal.get('context',{}).values():
            for timestamp in (frame.get('as_of'),frame.get('indicators',{}).get('closed_at')):
                if timestamp and instant(timestamp)>instant(signal['signal_at']):reasons.append('FUTURE_CONTEXT')
        if quote.get('type')!='LIVE' or quote.get('market_status')!='OPEN' or quote.get('available_for_execution') is not True or not quote.get('bid') or not quote.get('ask') or not 0<N(quote['bid'])<=N(quote['ask']) or not quote.get('at') or not 0<=(self.clock()-instant(quote['at'])).total_seconds()<=5:
            reasons.append('LIVE_OPEN_FRESH_QUOTE_REQUIRED')
        required=('identity','account_reconciled','positions_flat','orders_clear','journal_reconciled','permissions','margin',
                  'settled_funds','minimum_size','fees_bounded','protection','calendar','old_incident_resolved')
        for k in required:
            trial_protection=(k=='protection' and diagnostic and self.state['protocol'].get('protocol_version')==2 and
                evidence.get(k)=='SUPERVISED_FIRST_TRIAL' and evidence.get('recovery')=='VERIFIED' and evidence.get('supervised_protection_consent') is True)
            if evidence.get(k)!='VERIFIED' and not trial_protection:reasons.append(k.upper()+'_UNVERIFIED')
        size=self.size(profile,signal,quote) if quote.get('ask') and signal.get('stop_distance') else dict(reason='SIZE_UNAVAILABLE',admitted=False,quantity='0')
        if not size['admitted']:reasons.append(size['reason'])
        if size['admitted']:
            minimum=N(evidence.get('minimum_quantity','20000'));step=N(evidence.get('quantity_increment','1'));q=N(size['quantity'])
            if q<minimum or q%step!=0:reasons.append('BROKER_SIZE_CONSTRAINT')
            if self.state['protocol'].get('protocol_version')==2 and q>N(evidence.get('verified_quantity','0')):reasons.append('QUANTITY_EXCEEDS_VERIFIED_SCOPE')
            if N(evidence.get('margin_required_usd','101'))>min(N(p['equity']),N(100)) or N(evidence.get('settled_usd','0'))<N(size['reservation']):reasons.append('EXPERIMENTAL_FUNDS_OR_MARGIN_INSUFFICIENT')
            if self.state['protocol'].get('protocol_version')==2 and N(size['net_target'])<=0 and evidence.get('bounded_unfavorable_experiment_consent') is not True:reasons.append('NET_TARGET_NEGATIVE_EXPERIMENT_CONSENT_REQUIRED')
        return dict(profile=profile,reasons=list(dict.fromkeys(reasons)),size=size,admitted=not reasons,
            paper_exploration_gate='PASS' if not reasons else 'BLOCKED',strategy_validation_gate='NO_VIABLE_STRATEGY_FOUND')
    def begin(self,signal,quote,evidence,grant,emergency,order_id,send):
        self.reload();self.select_profile(signal,quote);decision=self.gates(signal,quote,evidence,bool(grant),emergency)
        if self.state['protocol'].get('protocol_version')==2 and grant:
            if grant.get('profile')!=decision['profile'] or grant.get('single_use') is not True or grant.get('max_openings')!=1 or grant.get('purpose')!=self.state['protocol']['purpose']:
                decision['reasons'].append('PROFILE_SCOPED_SINGLE_USE_AUTHORIZATION_REQUIRED');decision['admitted']=False
        self.state['profiles'][decision['profile']]['blockers']=decision['reasons']
        self.append('OPPORTUNITY_REVIEWED',dict(signal=signal,quote=quote,decision=decision))
        if not decision['admitted']:return decision
        trial_id=sha([self.journal.cohort,signal['opportunity_id']]);d=decision['size'];p=decision['profile']
        # Plain signal repeat rejection persists before any SDK call, including an ambiguous send.
        self.state['seen'].append(signal['opportunity_id'])
        self.state['opening_attempts']=self.state.get('opening_attempts',0)+1
        trial=dict(intent=trial_id,trial_id=trial_id,profile=p,classification=CLASS,execution_mode='BROKER_PAPER_EXECUTION',
            strategy=self.state['protocol']['strategy'],signal=copy.deepcopy(signal),quote=copy.deepcopy(quote),quantity=d['quantity'],
            purpose=self.state['protocol'].get('purpose','PAPER_EXPLORATORY_RESEARCH'),predictive_validation=False,kronos=copy.deepcopy(signal.get('kronos')),
            entry=d['entry'],stop=d['stop'],target=d['target'],decision=d,order_ids=list(range(order_id,order_id+3)),
            client_id=82,contract_id=12087792,fills={},commissions={},statuses={},acks={},completed={},twins={},
            state='SEND_PENDING',reserved=d['reservation'],authorization_id=grant['session_id'],entry_at=None,exit_at=None,
            recovery_orders={},cancellations=[],close_attempted=False,protection_confirmed=False)
        self.state['active']=trial;self.state['profiles'][p]['reserved']=trial['reserved'];self.state['status']='RUNNING'
        self.state.setdefault('quote_history',[]).append(copy.deepcopy(quote))
        self.append('SEND_PENDING',trial)
        try:
            send(trial,grant);self.append('BRACKET_TRANSPORT_ATTEMPTED',dict(ack_verified=False))
        except Exception:
            self.fail('SEND_UNCERTAIN_RECONCILE_REQUIRED');raise
        return decision
    @staticmethod
    def inventory(t):
        return sum((N(e['quantity'])*(1 if e['side']=='BUY' else -1) for e in t['fills'].values()),Decimal(0))
    def ingest(self,events,quote=None):
        historical={e['exec_id']:(e,trial['commissions'].get(e['exec_id'])) for trial in self.state['trials'] for e in trial['fills'].values()}
        filtered=[]
        for e in events:
            prior=historical.get(e.get('exec_id'))
            if prior and e['kind']=='fill':
                if any(prior[0].get(k)!=e.get(k) for k in ('order_id','perm_id','client_id','contract_id','side','quantity','price')):
                    self.fail('HISTORICAL_EXECUTION_CORRECTION');raise PermissionError('HISTORICAL_EXECUTION_CORRECTION')
                continue
            if prior and e['kind']=='commission':
                if not prior[1] or (prior[1]['amount'],prior[1]['currency'])!=(e['amount'],e['currency']):
                    self.fail('HISTORICAL_COMMISSION_CORRECTION');raise PermissionError('HISTORICAL_COMMISSION_CORRECTION')
                continue
            filtered.append(e)
        events=filtered
        t=self.state['active']
        if not t:
            if any(e['kind']=='fill' for e in events):self.fail('UNKNOWN_EXECUTION');raise PermissionError('UNKNOWN_EXECUTION')
            return
        failure=None
        for e in events:
            kind=e['kind'];ids=t['order_ids']+list(map(int,t['recovery_orders']))
            if kind in ('disconnect','readonly'):failure='BROKER_UNCERTAIN'
            elif kind in ('open_order','status','completed_order'):
                if e['order_id'] not in ids:
                    if kind=='open_order' and e['status'] not in TERMINAL:failure='UNKNOWN_ORDER'
                    continue
                if kind!='status':
                    if e.get('client_id')!=82 or e.get('contract_id')!=12087792 or e.get('reference') not in (t['intent'],*(r['reference'] for r in t['recovery_orders'].values())):failure='ORDER_IDENTITY_MISMATCH';continue
                t['statuses'][str(e['order_id'])]=e['status']
                if kind=='open_order':t['acks'][str(e['order_id'])]=copy.deepcopy(e)
                if kind=='completed_order':t['completed'][str(e['order_id'])]=copy.deepcopy(e)
            elif kind=='fill':
                if e['exec_id'] in t['fills']:
                    prior=t['fills'][e['exec_id']]
                    if any(prior.get(k)!=e.get(k) for k in ('order_id','perm_id','client_id','contract_id','side','quantity','price')):failure='EXECUTION_CORRECTION_REQUIRES_REVIEW'
                    continue
                if e['order_id'] not in ids or e['client_id']!=82 or e['contract_id']!=12087792 or e.get('perm_id',0)<=0 or e['side']!=('BUY' if e['order_id']==t['order_ids'][0] else 'SELL') or N(e['quantity'])<=0 or N(e['price'])<=0:
                    failure='UNKNOWN_EXECUTION';continue
                t['fills'][e['exec_id']]=copy.deepcopy(e)
                if e['side']=='BUY' and t['entry_at'] is None:
                    t['entry_at']=e.get('broker_at') or e['at'];t['first_fill_received_at']=e['at']
                    # No EUR-row-absence exception is reusable in this cohort.
                    comparable=[q for q in [*self.state.get('quote_history',[]),t['quote'],quote or {}] if q.get('type')=='LIVE' and q.get('at') and 0<=(instant(t['entry_at'])-instant(q['at'])).total_seconds()<=5]
                    fill_quote=max(comparable,key=lambda q:q['at']) if comparable else None
                    if fill_quote:
                        for p in PROFILES:
                            if p==t['profile']:continue
                            sized=self.size(p,t['signal'],fill_quote)
                            t['twins'][p]=dict(profile=p,execution_mode='SIMULATED_SHADOW',state='OPEN' if sized['admitted'] else 'NO_TRADE',
                                reason=sized['reason'],decision=sized,entry_at=t['entry_at'],observed_at=e['at'],quote=copy.deepcopy(fill_quote),
                                entry=str(N(fill_quote['ask'])+N(self.state['protocol']['costs']['slippage'])),stop=t['stop'],target=t['target'],
                                quantity=sized['quantity'],fills_simulated=True)
                    else:
                        t['twins']={p:dict(profile=p,execution_mode='SIMULATED_SHADOW',state='NO_TRADE',reason='CONTEMPORANEOUS_FILL_QUOTE_MISSING') for p in PROFILES if p!=t['profile']}
                if e['side']=='SELL':t['exit_at']=e.get('broker_at') or e['at']
            elif kind=='commission':
                if N(e['amount'])<0 or e['currency']!='USD':failure='COMMISSION_CURRENCY_OR_AMOUNT_UNCERTAIN';continue
                prior=t['commissions'].get(e['exec_id'])
                if prior and (prior['amount'],prior['currency'])!=(e['amount'],e['currency']):failure='COMMISSION_CORRECTION_REQUIRES_REVIEW'
                t['commissions'][e['exec_id']]=copy.deepcopy(e)
            elif kind=='reject' and e.get('order_id') in ids:failure='BROKER_REJECTION'
        inventory=self.inventory(t)
        if inventory<0 or sum((N(e['quantity']) for e in t['fills'].values() if e['side']=='BUY'),Decimal(0))>N(t['quantity']):failure='OWNED_INVENTORY_MISMATCH'
        t['state']='OPEN_PROTECTION_PENDING' if inventory>0 else 'FLAT_RECONCILIATION_PENDING' if t['fills'] else 'ACK_PENDING_FILL'
        self.append('BROKER_CALLBACKS',dict(events=events))
        if failure:self.fail(failure);raise PermissionError(failure)
    def mark_twins(self,analysis,at):
        from .eurusd_paper_research import exit_decision
        t=self.state['active']
        if not t:return
        costs=self.state['protocol']['costs']
        for twin in t['twins'].values():
            if twin['state']!='OPEN':continue
            for b in analysis['normalized']['15']:
                opened=instant(b['opened_at'])
                if opened<instant(twin['entry_at']) or opened+timedelta(minutes=15)>instant(at) or twin.get('last_bar') and opened<=instant(twin['last_bar']):continue
                position=dict(strategy='trend',side='BUY',entry_at=twin['entry_at'],stop=twin['stop'],target=twin['target'])
                previous=twin.get('last_bar',twin['entry_at'])
                result=exit_decision(position,b,previous,analysis['exit_signals'],True) if opened>instant(twin['entry_at']) else None
                result=result or exit_decision(position,b,previous,analysis['exit_signals'],False)
                twin['last_bar']=b['opened_at']
                if result:
                    price=N(result[0])-N(costs['slippage'])-(N(twin['quote']['ask'])-N(twin['quote']['bid']))/2
                    gross=N(twin['quantity'])*(price-N(twin['entry']));fees=N(costs['openingCommission'])+N(costs['closingCommission'])
                    twin.update(state='CLOSED',exit=str(price),exit_at=result[2],gross_pnl=str(gross),net_pnl=str(gross-fees),fees=str(fees),close_reason=result[1],valuation='ORIGINAL_EXIT_BAR_SIMULATED_NOT_BROKER_FILL')
                    break
        self.append('SHADOW_TWINS_MARKED_NO_FUTURE_DATA')
    def protection(self,orders):
        t=self.state['active'];q=self.inventory(t)
        t['protection_confirmed']=False
        if q<=0:return False
        found=[]
        for index in (1,2):
            r=next((r for r in orders if r['order_id']==t['order_ids'][index]),None)
            expected='LMT' if index==1 else 'STP';price='limit_price' if index==1 else 'stop_price'
            if not r or r.get('status') not in ('Submitted','PreSubmitted') or r.get('side')!='SELL' or r.get('reference')!=t['intent'] or r.get('parent_id')!=t['order_ids'][0] or r.get('oca_group')!=t['intent'] or r.get('oca_type')!=2 or r.get('order_type')!=expected or r.get('client_id')!=82 or r.get('perm_id',0)<=0 or N(r.get(price,0))!=N(t['target'] if index==1 else t['stop']):return False
            # Total includes already executed shares; parent partials cannot leave oversized sells working.
            executed=sum((N(e['quantity']) for e in t['fills'].values() if e['order_id']==r['order_id']),Decimal(0))
            if N(r['quantity'])-executed!=q:return False
            found.append(r)
        t['protection_confirmed']=True;t['state']='OPEN_PROTECTED';self.append('PROTECTION_ACKNOWLEDGED',dict(orders=found));return True
    def reconcile(self,snapshot,additional):
        self.state.pop('last_reconciliation',None)
        t=self.state['active'];self.ingest(snapshot.get('events',[]))
        cash=snapshot.get('cash_reconciliation',{})
        if (snapshot.get('exposure_reads_complete') is not True or additional.get('status')!='COMPLETE' or additional.get('errors') or
            cash.get('query_status')!='COMPLETE' or cash.get('account_ready') is not True or cash.get('errors') or cash.get('value') is None or snapshot.get('eur_cash') is None or
            cash.get('base_currency')!='USD' or set(cash.get('completed_sources',[]))!=set(cash.get('expected_sources',[])) or
            len([s for s in cash.get('completed_sources',[]) if s.startswith('SUMMARY_')])!=2 or
            not {'ACCOUNT_UPDATES','ACCOUNT_UPDATES_MULTI'}<=set(cash.get('completed_sources',[])) or snapshot.get('foreign_positions') or snapshot.get('foreign_currency_balances')):
            self.fail('STRICT_ACCOUNT_RECONCILIATION_REQUIRED');return False
        for value in (snapshot,additional):
            if not value.get('received_at') or not 0<=(self.clock()-instant(value['received_at'])).total_seconds()<=30:
                self.fail('RECONCILIATION_STALE');return False
        def pos(rows):
            if rows is None:raise PermissionError('POSITION_QUERY_INCOMPLETE')
            relevant=[]
            for r in rows:
                if N(r['quantity'])!=0 and (r.get('contract_id')!=12087792 or r.get('security_type')!='CASH' or r.get('currency')!='USD'):raise PermissionError('FOREIGN_POSITION')
                if r.get('contract_id')==12087792:relevant.append(N(r['quantity']))
            if len(relevant)>1:raise PermissionError('AMBIGUOUS_POSITION')
            return relevant[0] if relevant else Decimal(0)
        try:
            inventory=self.inventory(t) if t else Decimal(0)
            if pos(snapshot.get('positions'))!=inventory or pos(additional.get('positions'))!=inventory:raise PermissionError('NETTING_NOT_ATTRIBUTABLE')
            if N(snapshot['eur_cash'])!=inventory or N(cash['value'])!=inventory:raise PermissionError('EUR_CASH_INVENTORY_NOT_ATTRIBUTABLE')
            if snapshot.get('portfolio') and pos(snapshot['portfolio'])!=inventory:raise PermissionError('PORTFOLIO_MISMATCH')
            ids=t['order_ids']+list(map(int,t['recovery_orders'])) if t else []
            if any(r['order_id'] not in ids for r in snapshot['orders']):raise PermissionError('UNKNOWN_ORDER')
        except PermissionError as error:self.fail(str(error));return False
        self.state['last_reconciliation']=dict(at=self.clock().isoformat(),inventory=str(inventory),orders=copy.deepcopy(snapshot['orders']))
        self.append('STRICT_ACCOUNT_RECONCILED')
        if not t:return not snapshot['orders']
        if inventory>0:
            if not t.get('entry_at'):self.fail('OPEN_POSITION_WITHOUT_OPENING_FILL');return False
            return self.protection(snapshot['orders'])
        if not t['fills']:
            # ACK without fill retains the reservation; no rotation and no exception consumption.
            if not snapshot['orders'] and all(t['statuses'].get(str(i)) in TERMINAL and t['completed'].get(str(i),{}).get('perm_id',0)>0 and t['completed'].get(str(i),{}).get('status') in TERMINAL for i in ids):
                self.state['profiles'][t['profile']]['reserved']='0';t['state']='CANCELLED_NO_FILL';t['reserved']='0'
                self.state['trials'].append(copy.deepcopy(t));self.state['active']=None;self.append('NO_FILL_RECONCILED_NO_ROTATION')
            return False
        if snapshot['orders'] or any(t['statuses'].get(str(i)) not in TERMINAL or t['completed'].get(str(i),{}).get('perm_id',0)<=0 for i in ids):return False
        if any(e not in t['commissions'] for e in t['fills']):t['state']='COMMISSION_PENDING';self.append('COMMISSION_PENDING');return False
        gross=sum((N(e['quantity'])*N(e['price'])*(1 if e['side']=='SELL' else -1) for e in t['fills'].values()),Decimal(0))
        fees=sum((N(t['commissions'][e]['amount']) for e in t['fills']),Decimal(0));net=gross-fees
        t.update(state='CLOSED_RECONCILED',gross_pnl=str(gross),net_pnl=str(net),fees=str(fees),reserved='0',closed_at=self.clock().isoformat(),
            duration_seconds=(instant(t['exit_at'])-instant(t['entry_at'])).total_seconds(),continuation='CONTINUE' if net>0 else 'STOPPED_FOR_DAY',sol_ready=True)
        self.settle_profile(t['profile'],net,t['closed_at'],t,False)
        for p,twin in t['twins'].items():
            if twin['state']=='CLOSED':
                self.settle_profile(p,N(twin['net_pnl']),twin['exit_at'],twin,True);continue
            if twin['state']!='OPEN':continue
            # This is a paired-time liquidation comparison, not an independent TP-before-SL backtest.
            q=N(twin['quantity']);quote=self.state.get('last_quote');c=self.state['protocol']['costs']
            if not quote or abs((instant(quote['at'])-instant(t['exit_at'])).total_seconds())>5:
                twin.update(state='MISSING_EXIT_QUOTE',net_pnl=None);continue
            exit_price=N(quote['bid'])-N(c['slippage']);tg=q*(exit_price-N(twin['entry']));tf=N(c['openingCommission'])+N(c['closingCommission']);tn=tg-tf
            twin.update(state='CLOSED',exit=str(exit_price),exit_at=t['exit_at'],net_pnl=str(tn),gross_pnl=str(tg),fees=str(tf),
                close_reason='PAIRED_BROKER_EXIT_TIME',strategy_outcome_validated=False)
            self.settle_profile(p,tn,t['closed_at'],twin,True)
        self.state['closed_days'][day(t['closed_at'])]=self.state['closed_days'].get(day(t['closed_at']),0)+1
        if -net>N(t['decision']['budget']):
            self.state['global_stop']='REALIZED_LOSS_EXCEEDS_PLANNED_RISK';t['risk_budget_exceeded']=True
        self.state['trials'].append(copy.deepcopy(t));self.state['active']=None;self.state['rotation']=(self.state['rotation']+1)%3
        self.append('CLOSED_COMMISSION_RECONCILED_RESERVE_RELEASED_ROTATED');return True
    def settle_profile(self,profile,net,at,trade,shadow):
        p=self.state['profiles'][profile];p['equity']=str(N(p['equity'])+net);p['consumed_loss']=str(N(p['consumed_loss'])+max(Decimal(0),-net));p['reserved']='0'
        if net<=0:p['stopped_days'][day(at)]='DAILY_FIRST_LOSS_STOP' if net<0 else 'DAILY_BREAK_EVEN_STOP'
        p['shadow_trades' if shadow else 'broker_trades'].append(copy.deepcopy(trade))
    def authorize_transport(self,t,role,order_id,quantity=None):
        # SDK callback validates the authoritative, immutable intent immediately before serialization.
        h=self.journal.load()
        if h['revision']!=self.revision or h['hash']!=self.head:raise PermissionError('JOURNAL_CHANGED_RECONCILE_REQUIRED')
        active=self.state['active']
        saved=json.loads(h['payload'])['state']['active'] if h.get('payload') else None
        if saved!=active:raise PermissionError('DURABLE_INTENT_STATE_CHANGED')
        if not active or active['intent']!=t['intent']:raise PermissionError('UNOWNED_MUTATION')
        if role in ('BRACKET_ENTRY','BRACKET_PROTECTION'):
            if active['state']!='SEND_PENDING' or active['fills'] or order_id not in active['order_ids'] or N(quantity)!=N(active['quantity']):raise PermissionError('ENTRY_ALREADY_ATTEMPTED_OR_CHANGED')
            if any(active.get(k)!=t.get(k) for k in ('quantity','entry','stop','target','order_ids','quote','strategy')):raise PermissionError('TRANSPORT_PAYLOAD_CHANGED')
        elif role=='OWNED_CLOSE':
            if not active['close_attempted'] or order_id!=active['order_ids'][1] or N(quantity)!=self.inventory(active) or self.inventory(active)<=0:raise PermissionError('REDUCE_ONLY_CLOSE_REQUIRED')
        elif role=='RECOVERY_CLOSE':
            r=active['recovery_orders'].get(str(order_id))
            if r!=t or N(quantity)!=self.inventory(active) or N(quantity)<=0:raise PermissionError('OWNED_REDUCE_ONLY_RECOVERY_REQUIRED')
        else:raise PermissionError('UNSCOPED_MUTATION_DISABLED')
