"""One supervised F/H40 Paper trial; independent of PaperAuto and Forex grants.

Prepare/Inspect/Status/RecoveryInspect never bind a mutation-capable transport.
Consent is Windows DPAPI, tied to a preregistration, Paper binding, TWS process
and source hashes. Unknown permissions are never inferred from contract metadata.
"""
import argparse
import copy
from datetime import timedelta
from decimal import Decimal
import json
from pathlib import Path
import re
import subprocess
import time
import uuid
from . import stock_paper_forward as stock
from .stock_paper_forward_runner import run_lock, owned_snapshot, drain, manage
from .ibkr_session import AccountBinding, SessionConfiguration
from .paper_lab import unseal, same_process
from .paper_identity import protect
from .broker import PaperOptions

D=Decimal
ROOT_FOLDER='artifacts/paper-trials/h40'
SCOPE='H40_SUPERVISED_SINGLE_PAPER_TRIAL'
RECOVERY_SCOPE='H40_TRIAL_OWNED_RECOVERY_CLOSE_ONLY'
R2_PROFILE='PAPER_EXPERIMENTAL_H40_SUPERVISED_V1'
R3_PROFILE='H40_PAPER_EXPERIMENTAL_R3'
R3_SCOPE='H40_R3_SUPERVISED_SINGLE_PAPER_TRIAL'
TRIAL_PATTERN=r'h40-trial-[a-f0-9]{32}'
CAPS=tuple(k for k in stock.CAPABILITIES if k not in ('protection_acceptance','partial_fill_protection'))

def folder(root,trial):
    if not re.fullmatch(TRIAL_PATTERN,trial):raise PermissionError('INVALID_TRIAL_ID')
    return Path(root)/ROOT_FOLDER/trial

def config(root,profile=R2_PROFILE):
    stock.check_live();stock.configuration(root)
    if profile not in (R2_PROFILE,R3_PROFILE):raise PermissionError('UNKNOWN_H40_EXPERIMENT_PROFILE')
    file='config/h40-paper-r3.json' if profile==R3_PROFILE else 'config/h40-paper-trial.json'
    c=json.loads((Path(root)/file).read_text(encoding='utf-8'))
    expected=dict(schema_version=1,profile='PAPER_EXPERIMENTAL_H40_SUPERVISED_V1',environment='PAPER_TRADING',
        capital_usd=100,maximum_notional_usd=100,maximum_forecast_loss_usd=10,original_h40_risk_percent=2,
        maximum_quantity=1,maximum_opening_attempts=1,authorization_minutes=30,protection_ack_seconds=5,
        poll_seconds=1,cost_model='FIXED_FEE_STRESS',partial_and_late_cost_allowance_usd=1,
        exit_semantics='ORIGINAL_H40_STOP_TARGET_HOLD40_OR_EXPLICIT_OWNED_RECOVERY',
        daily_policy='WIN_TO_CONTINUE / FIRST_LOSS_STOPS_DAY',day_timezone='America/Santo_Domingo',supervised=True,live_enabled=False)
    if profile==R3_PROFILE:expected.update(profile=R3_PROFILE,experimental_risk_percent=3)
    if c!=expected:raise PermissionError('H40_TRIAL_PREREGISTERED_LIMITS_CHANGED')
    return c

def selected_risk(c):return D(c.get('experimental_risk_percent',c['original_h40_risk_percent']))
def entry_scope(c):return R3_SCOPE if c['profile']==R3_PROFILE else SCOPE
def recovery_scope(c):return 'H40_R3_TRIAL_OWNED_RECOVERY_CLOSE_ONLY' if c['profile']==R3_PROFILE else RECOVERY_SCOPE
def variant_version(c):
    return __import__('hashlib').sha256((stock.VERSION+'|'+R3_PROFILE+'|RISK_PERCENT=3').encode()).hexdigest() if c['profile']==R3_PROFILE else stock.VERSION
def budget(c,equity,losses):
    return min(D(3) if c['profile']==R3_PROFILE else D(10),stock.number(equity)*selected_risk(c)/100,D(10),D(20)-stock.number(losses))

def hashes(root,profile=R2_PROFILE):
    paths=stock.source_hashes(root)
    for p in ('config/h40-paper-trial.json','python/trading_agent/h40_paper_trial.py',
        'src/TradingAgent.Core/H40PaperTrialRisk.cs','scripts/h40-paper-trial.ps1'):
        paths[p]=stock.sha(Path(root)/p)
    if profile==R3_PROFILE:
        for p in ('config/h40-paper-r3.json','src/TradingAgent.Core/H40PaperR3Risk.cs'):
            paths[p]=stock.sha(Path(root)/p)
    return paths

def seal_new(path,value,sealer=protect):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    sealed=sealer(stock.encoded(value))
    with path.open('xb') as f:
        f.write(sealed);f.flush()
        __import__('os').fsync(f.fileno())

def prepare(root,profile=R2_PROFILE):
    c=config(root,profile);trial='h40-trial-'+uuid.uuid4().hex;p=folder(root,trial);p.mkdir(parents=True,exist_ok=False)
    value=dict(trial_id=trial,created_at=stock.now().isoformat(),strategy_version=stock.VERSION,
        original_candidate=stock.CANDIDATE,profile=c,scope=entry_scope(c),source_hashes=hashes(root,profile),
        protection='UNKNOWN_UNTIL_OWN_ORDER_ACK_AND_POSITION_RECONCILIATION',
        authorization_required=True,execution_authorized=False,live_enabled=False)
    if profile==R3_PROFILE:value.update(variant_version=variant_version(c),trade_classification='H40_SIGNAL_PAPER_EXPERIMENT',strategy_profitability_proven=False)
    with (p/'protocol.json').open('xb') as f:f.write(stock.encoded(value))
    (p/'protocol.sha256').write_text(stock.sha(p/'protocol.json'),encoding='ascii')
    return dict(trial_id=trial,protocol=str(p/'protocol.json'),sha256=stock.sha(p/'protocol.json'),orders_sent=0)

def protocol(root,trial):
    p=folder(root,trial);value=json.loads((p/'protocol.json').read_text(encoding='utf-8'))
    profile=value['profile']['profile'];c=config(root,profile)
    if (p/'protocol.sha256').read_text(encoding='ascii')!=stock.sha(p/'protocol.json') or value['trial_id']!=trial or value['profile']!=c or value['strategy_version']!=stock.VERSION or value['original_candidate']!=stock.CANDIDATE or value['source_hashes']!=hashes(root,profile) or value.get('scope')!=entry_scope(c):
        raise PermissionError('TRIAL_PROTOCOL_OR_DEPLOYMENT_CHANGED')
    if profile==R3_PROFILE and (value.get('variant_version')!=variant_version(c) or value.get('trade_classification')!='H40_SIGNAL_PAPER_EXPERIMENT'):raise PermissionError('R3_VARIANT_IDENTITY_REQUIRED')
    return value

def trial_config(root,trial):return protocol(root,trial)['profile']

def evidence(root,path,binding,clock=stock.now,*,expected_scope=SCOPE):
    """Explicit operator Paper receipts, frozen into the separate protected grant.

    They complement UNKNOWN callbacks; contradicting/restricted callbacks win.
    Quotes, positions, orders, schedule and binding can NEVER come from receipts.
    """
    path=Path(path);doc=json.loads(path.read_text(encoding='utf-8'))
    if doc.get('environment')!='PAPER_TRADING' or doc.get('binding_id')!=binding or doc.get('scope')!=expected_scope:
        raise PermissionError('PAPER_ONLY_EVIDENCE_REQUIRED')
    for k,row in doc.get('capabilities',{}).items():
        if k not in CAPS or row.get('status')!='VERIFIED' or row.get('compatible') is not True or row.get('source') not in ('OPERATOR_PAPER_TWS','OPERATOR_PAPER_CLIENT_PORTAL') or not row.get('reference') or not 0<=(clock()-stock.at(row['observed_at'])).total_seconds()<=86400:
            raise PermissionError('PAPER_CAPABILITY_RECEIPT_INVALID')
        v=row.get('value')
        if k in ('settled_cash','available_funds') and stock.number(v)<100 or k in ('whole_share_minimum','quantity_increment') and stock.number(v)!=1 or k=='contract_margin' and not 0<=stock.number(v)<=1:
            raise PermissionError('PAPER_CAPABILITY_RECEIPT_RESTRICTED')
        if k=='stock_permission' and v is not True or k=='account_restrictions' and v!='WHOLE_SHARE_CASH_LONG_ALLOWED' or k=='effective_fees' and v not in ('FIXED','TIERED') or k=='corporate_actions' and v!='CURRENT_SIGNAL_HISTORY_CHECKED':
            raise PermissionError('PAPER_CAPABILITY_RECEIPT_RESTRICTED')
    return doc

def cost_consent(doc):
    return doc.get('cost_scenario')==dict(status='ESTIMATED',model='FIXED_FEE_STRESS',
        effective_fees='UNKNOWN',contingency_usd=1,operator_accepts_uncertainty=True,
        source='https://www.interactivebrokers.com/en/pricing/commissions-stocks.php')

def merged(snapshot,receipts):
    s=copy.deepcopy(snapshot)
    for k,row in receipts.get('capabilities',{}).items():
        current=s['capabilities'].get(k,{})
        if current.get('status')=='UNKNOWN':s['capabilities'][k]=row
    return s

def blockers(snapshot,c,receipts=None,stamp=None,bootstrap=False):
    stamp=stamp or stock.now();s=merged(snapshot,receipts or {})
    blocks=stock.readiness(s,dict(maximum_quote_age_seconds=15),stamp)
    blocks=[b for b in blocks if b!='H40_RISK_2_PERCENT_EXCEEDS_PRODUCTIVE_0_5_PERCENT']
    if c['profile']==R2_PROFILE and cost_consent(receipts or {}) and s['capabilities'].get('effective_fees',{}).get('status')=='UNKNOWN':
        blocks=[b for b in blocks if b!='EFFECTIVE_FEES_UNKNOWN_OR_RESTRICTED']
    if bootstrap:
        blocks=[b for b in blocks if b not in ('PROTECTION_ACCEPTANCE_UNKNOWN_OR_RESTRICTED','PARTIAL_FILL_PROTECTION_UNKNOWN_OR_RESTRICTED')]
        declared=set(snapshot.get('declared_protection',{}).get('order_types','').split(','))
        if not {'LMT','STP'}.issubset(declared):blocks.append('DECLARED_BRACKET_TYPES_UNAVAILABLE')
        # A rejection/restriction is not UNKNOWN and cannot be bootstrapped.
        for k in ('protection_acceptance','partial_fill_protection'):
            r=s['capabilities'].get(k,{})
            if r.get('status')!='UNKNOWN' and (r.get('status')!='VERIFIED' or r.get('compatible') is not True):blocks.append('PROTECTION_PREVIOUSLY_REJECTED')
    else:blocks.append('SPECIFIC_SUPERVISED_PROTECTION_CONSENT_REQUIRED')
    for k in CAPS:
        r=s['capabilities'].get(k,{})
        try:
            if r.get('status')=='VERIFIED' and not 0<=(stamp-stock.at(r['observed_at'])).total_seconds()<=86400:blocks.append(k.upper()+'_EVIDENCE_EXPIRED')
        except (KeyError,ValueError):blocks.append(k.upper()+'_EVIDENCE_TIME_UNKNOWN')
    return list(dict.fromkeys(blocks))

def size(entry,stop,target,spread,c,cash=100,equity=100,losses=0):
    # Select only the preregistered profile. Neither costs nor a previous loss
    # can increase the selected percentage or the one-share quantity ceiling.
    rate=selected_risk(c)
    first=stock.estimate(entry,stop,target,rate,cash,equity,spread,c['cost_model'],losses)
    p=stock.number(first.get('entry',entry));q=min(first['quantity'],c['maximum_quantity'])
    for q in range(q,0,-1):
        opening=stock.commission(q,p,c['cost_model'],'BUY')+D(c['partial_and_late_cost_allowance_usd'])/2
        closing=stock.commission(q,max(p,stock.number(target)),c['cost_model'],'SELL')+D(c['partial_and_late_cost_allowance_usd'])/2
        sp=max(stock.number(spread),stock.number(entry)*D('.0005'));slip=stock.number(entry)*D('.0005');gap=stock.number(entry)*D('.005')
        padding=D(0)
        if c['profile']==R3_PROFILE:
            # Core assesses the BUY limit versus the real BID, not the raw ASK.
            # Reserve the larger loss so limit/tick padding cannot understate
            # the unchanged engine's stop-distance + spread calculation.
            bid=stock.number(entry)-stock.number(spread)
            engine_geometry=abs((p+bid)/2-stock.number(stop))+(p-bid)
            padding=max(D(0),engine_geometry-(p-stock.number(stop)+sp))
        risk=q*(p-stock.number(stop)+sp+2*slip+gap+D('.02')+padding)+opening+closing
        cash_reserved=q*p+opening+closing
        room=budget(c,equity,losses)
        if cash_reserved<=min(D(100),stock.number(cash),stock.number(equity)) and risk<=room:
            return dict(quantity=q,entry=str(p),opening_fee=str(opening),closing_fee=str(closing),fees=str(opening+closing),risk=str(risk),
                notional=str(q*p),reserved_cash=str(cash_reserved),budget=str(room),
                slippage_per_unit=str(2*slip+D('.02')),gap_per_unit=str(gap),
                friction=dict(spread=str(q*sp),slippage=str(q*2*slip),gap=str(q*gap),
                    target_net=str(q*(stock.number(target)-p-sp-2*slip-gap-D('.02')-padding)-opening-closing),
                    execution_price_padding=str(q*padding)),
                costs_status='ESTIMATED_NOT_GUARANTEED',tail_loss_not_bounded=True)
    return dict(quantity=0,reason='R3_BUDGET_INSUFFICIENT_INCLUDING_CONTINGENCY' if c['profile']==R3_PROFILE else 'ORIGINAL_H40_2_PERCENT_BUDGET_INSUFFICIENT_INCLUDING_CONTINGENCY',
        budget=str(budget(c,equity,losses)),tail_loss_not_bounded=True)

def risk(root,state,request,profile=R2_PROFILE):
    eq=stock.number(state['equity']);loss=stock.number(state['consumed_loss']);stamp=stock.now().isoformat()
    if state['intent'] or state['completed'] or loss or eq!=100:raise PermissionError('FIRST_TRIAL_REQUIRES_UNCONSUMED_ALLOCATION')
    account=dict(accountId='PAPER-H40-TRIAL',equity=str(eq),units=1,dayNav=100,weekNav=100,highNav=100,at=stamp,
        capital=dict(initialCapital=100,lossAllowance=20,environment='PAPER_TRADING'))
    raw=dict(account=account,request=request,strategy_version=stock.VERSION,cash=state['cash'],reservations=state['reservation'])
    flag='--h40-paper-trial-risk'
    if profile==R3_PROFILE:
        raw.update(experiment_profile=profile,variant_version=variant_version(config(root,profile)));flag='--h40-paper-r3-risk'
    elif profile!=R2_PROFILE:raise PermissionError('UNKNOWN_H40_EXPERIMENT_PROFILE')
    result=subprocess.run(['dotnet',str(Path(root)/'src/TradingAgent.Api/bin/Debug/net9.0/TradingAgent.Api.dll'),flag],
        input=stock.encoded(raw).decode(),capture_output=True,text=True,timeout=20,cwd=root)
    if result.returncode:raise PermissionError('H40_TRIAL_RISK_PROTOCOL_UNAVAILABLE')
    value=json.loads(result.stdout)
    if value.get('allowed') is True and stock.number(value['quantity'])!=stock.number(request['maximumQuantity']):raise PermissionError('RISK_ENGINE_QUANTITY_MISMATCH')
    return value

def trial_request(plan,snapshot,c):
    request=stock.risk_request(plan,snapshot);request['proposedRisk']=selected_risk(c)/100
    return request

class TrialLedger(stock.Ledger):
    def __init__(self,journal,trial,consumer=None,*,profile_config=None):
        super().__init__(journal);self.trial=trial;self.consumer=consumer
        self.c=profile_config or dict(profile=R2_PROFILE,original_h40_risk_percent=2)
        if self.state.get('experiment_profile') not in (None,self.c['profile']):raise PermissionError('TRIAL_PROFILE_JOURNAL_SCOPE_MISMATCH')
        if self.state.get('trial_id') not in (None,trial):raise PermissionError('TRIAL_JOURNAL_SCOPE_MISMATCH')
        if self.state.get('trial_id') is None:self.state['trial_id']=trial;self.write('TRIAL_BOUND')
        if self.c['profile']==R3_PROFILE and self.state.get('experiment_profile') is None:
            self.state.update(experiment_profile=R3_PROFILE,variant_version=variant_version(self.c),trade_classification='H40_SIGNAL_PAPER_EXPERIMENT')
            self.write('R3_VARIANT_BOUND',dict(original_h40_risk_percent=2,experimental_risk_percent=3))
    def write(self,kind,details=None):
        if getattr(self,'c',{}).get('profile')==R3_PROFILE:
            details={**(details or {}),'experiment_profile':R3_PROFILE,'variant_version':variant_version(self.c),
                'parent_strategy_version':stock.VERSION,'trade_classification':'H40_SIGNAL_PAPER_EXPERIMENT'}
            if kind=='TRADE_SETTLED':details.update(strategy_profitability_proven=False,
                original_h40_exit_observed=details.get('reason')!='EXPLICIT_SUPERVISED_RECOVERY_CLOSE_ONLY')
        super().write(kind,details)
    def reserve(self,plan):
        if self.state.get('opening_consumed') or self.state['completed']:raise PermissionError('ONE_TRIAL_OPENING_ONLY')
        block=self.entry_block(plan['at'])
        if block:raise PermissionError(block)
        q=stock.number(plan['quantity']);spent=q*stock.number(plan['entry'])+stock.number(plan['fees'])
        if q!=1 or plan['side']!='BUY' or plan['strategy_version']!=stock.VERSION or plan.get('trial_id')!=self.trial or spent>min(D(100),stock.number(self.state['cash']),stock.number(self.state['equity'])):
            raise PermissionError('TRIAL_LONG_CASH_SCOPE_REQUIRED')
        if self.c['profile']==R3_PROFILE and (plan.get('experiment_profile')!=R3_PROFILE or plan.get('variant_version')!=variant_version(self.c) or plan.get('trade_classification')!='H40_SIGNAL_PAPER_EXPERIMENT'):
            raise PermissionError('R3_STRATEGY_AND_DIAGNOSTIC_MUST_BE_SEPARATE')
        if not 0<stock.number(plan['risk'])<=budget(self.c,self.state['equity'],self.state['consumed_loss']):
            raise PermissionError('TRIAL_RISK_LIMIT')
        if len(plan['order_ids'])!=3 or len(set(plan['order_ids']))!=3 or min(plan['order_ids'])<self.state['next_order_id']:raise PermissionError('ORDER_ID_COLLISION')
        if self.consumer:self.consumer() # Global, durable single use before SEND_PENDING.
        self.state['opening_consumed']=True;self.state['next_order_id']=max(plan['order_ids'])+1;self.state['reservation']=str(spent)
        self.state['intent']={**copy.deepcopy(plan),'state':'PREPARED','orders':{},'executions':{},'fees_observed':{},'attempted':[],
            'sell_attempted':False,'first_fill_at':None,'uncertain':False,'last_reconciled_at':None,'position':'0'}
        self.write('EXPERIMENTAL_RESERVED',dict(trial_id=self.trial,original_risk_percent=2,selected_risk_percent=str(selected_risk(self.c)),outer_ceiling_usd=10))
    def pre_send(self,oid):
        super().pre_send(oid)
        i=self.state['intent'];i.setdefault('first_send_at',stock.now().isoformat());self.write('TRIAL_SEND_CLOCK')
    def reconcile(self,snapshot):
        i=self.state['intent']
        if i:
            parent=next((o for o in snapshot.get('completed_orders',[])+snapshot.get('open_orders',[]) if o['order_id']==i['order_ids'][0]),None)
            buys=[f for f in list(i['executions'].values())+snapshot.get('executions',[]) if f['side']=='BUY' and f['order_ref']==i['intent']]
            if parent and (parent['status']=='Filled' or stock.number(parent.get('filled',0))>0) and not buys:
                self.suspend('FILLED_ACK_WITHOUT_EXECUTION_EVIDENCE');raise PermissionError('FILLED_ACK_WITHOUT_EXECUTION_EVIDENCE')
        super().reconcile(snapshot)
        i=self.state['intent']
        if i and i['state']=='OPEN_PROTECTED':
            i['state']='OPEN_REQUIRES_PROTECTION_ACK_REVIEW';self.write('PROTECTION_ACCEPTANCE_NOT_YET_ASSERTED')

class TrialGuard:
    def __init__(self,root,trial,ledger,loader=None,clock=stock.now):
        self.root=Path(root);self.trial=trial;self.ledger=ledger;self.clock=clock
        self.c=trial_config(root,trial) if (folder(root,trial)/'protocol.json').exists() else config(root)
        self.loader=loader or (lambda:unseal(folder(root,trial)/'authorization.dpapi'))
    def grant(self,management=False):
        stock.check_live();protocol(self.root,self.trial);g=self.loader();binding=AccountBinding(unseal(self.root/'.local/ibkr-account-binding.dpapi'))
        if g.get('scope')!=entry_scope(self.c) or g.get('trial_id')!=self.trial or g.get('account')!=binding.account or g.get('binding_id')!=binding.binding_id or g.get('environment')!='PAPER_TRADING' or g.get('live_enabled') is not False or g.get('supervised_protection_bootstrap') is not True or g.get('protocol_sha256')!=stock.sha(folder(self.root,self.trial)/'protocol.json') or g.get('source_hashes')!=hashes(self.root,self.c['profile']):
            raise PermissionError('TRIAL_INDEPENDENT_AUTHORIZATION_REQUIRED')
        if self.c['profile']==R3_PROFILE and (g.get('variant_version')!=variant_version(self.c) or g.get('experiment_profile')!=R3_PROFILE):raise PermissionError('R3_VARIANT_AUTHORIZATION_REQUIRED')
        SessionConfiguration.load(self.root).matches(g)
        if g.get('read_only_disabled_checked') is not True or not same_process(g['tws_pid'],g['tws_start_filetime']):raise PermissionError('TWS_PROTECTED_SESSION_CHANGED')
        if not management:
            if g.get('revoked') is not False or not stock.at(g['issued_at'])<=self.clock()<stock.at(g['expires_at']) or not 0<(stock.at(g['expires_at'])-stock.at(g['issued_at'])).total_seconds()<=1800:raise PermissionError('TRIAL_AUTHORIZATION_EXPIRED_OR_REVOKED')
            for n in ('paper-lab.emergency','paper-auto.stop','stock-paper-forward.stop','h40-paper-trial.stop'):
                if (self.root/'.local'/n).exists():raise PermissionError('PROTECTED_EMERGENCY_OR_STOP_ACTIVE')
        return g
    def admission(self,snapshot,plan):
        g=self.grant();blocked=blockers(snapshot,self.c,g['paper_evidence'],self.clock(),bootstrap=True)
        if blocked:raise PermissionError(blocked[0])
        if snapshot.get('binding_id')!=g['binding_id']:raise PermissionError('EXACT_PAPER_IDENTITY_CHANGED')
        if not all(snapshot.get('account_queries',{}).get(m,{}).get('complete') is True for m in ('summary','ledger','updates','multi')):raise PermissionError('ACCOUNT_QUERIES_INCOMPLETE')
        stamp=self.clock();session=snapshot['active_session']
        if not stock.at(session['start'])<=stamp<stock.at(session['start'])+timedelta(seconds=60):raise PermissionError('H40_NEXT_OPEN_ENTRY_EXPIRED')
        plan_geometry(plan,snapshot,self.trial)
        expected=stock.h40_next_signal(plan['completed_bars'],plan['opening_bar'],session,stock.configuration(self.root))
        if expected is None or expected!=plan['signal']:raise PermissionError('H40_SIGNAL_NOT_REPRODUCIBLE')
        if stock.number(plan['stop'])!=stock.number(expected['stop']) or stock.number(plan['target'])!=stock.number(expected['target']):raise PermissionError('H40_ORIGINAL_EXIT_LEVELS_REQUIRED')
        computed=size(snapshot['quote']['ask'],expected['stop'],expected['target'],stock.number(snapshot['quote']['ask'])-stock.number(snapshot['quote']['bid']),self.c,self.ledger.state['cash'],self.ledger.state['equity'],self.ledger.state['consumed_loss'])
        for k in ('quantity','entry','fees','risk','opening_fee','closing_fee','slippage_per_unit','gap_per_unit'):
            if k not in computed or stock.number(plan[k])!=stock.number(computed[k]):raise PermissionError('TRIAL_SIZE_NOT_REPRODUCIBLE')
        block=self.ledger.entry_block(stamp.isoformat())
        if block:raise PermissionError(block)
        if self.c['profile']==R3_PROFILE and (plan.get('experiment_profile')!=R3_PROFILE or plan.get('variant_version')!=variant_version(self.c) or plan.get('trade_classification')!='H40_SIGNAL_PAPER_EXPERIMENT'):raise PermissionError('R3_STRATEGY_AND_DIAGNOSTIC_MUST_BE_SEPARATE')
        value=risk(self.root,self.ledger.state,trial_request(plan,snapshot,self.c),self.c['profile'])
        self.ledger.write('EXPERIMENTAL_RISK_AND_FEASIBILITY',value)
        if value.get('allowed') is not True:raise PermissionError(value.get('reason','RISK_ENGINE_DENIED'))
        if self.c['profile']==R3_PROFILE and stock.number(value['estimatedLoss'])>stock.number(plan['risk']):raise PermissionError('R3_RISK_RESERVATION_BELOW_ENGINE_ESTIMATE')

def plan_geometry(plan,snapshot,trial):
    contract=snapshot.get('contract',{});key=stock.digest([stock.VERSION,plan['signal']['signal_at'],trial])
    if (contract.get('symbol'),contract.get('security_type'),contract.get('currency'))!=('F','STK','USD') or plan.get('con_id')!=contract.get('con_id') or plan.get('entry_session')!=snapshot['active_session']['start'] or plan.get('trial_id')!=trial or plan.get('strategy_version')!=stock.VERSION or plan.get('side')!='BUY' or plan.get('signal_key')!=key or plan.get('intent')!='H40-'+key[:32]:
        raise PermissionError('TRIAL_CONTRACT_SIGNAL_OR_GTD_BINDING_CHANGED')

def inspect(root,trial):
    c=trial_config(root,trial);value=stock.inspect(root,stock.configuration(root))
    value['productive_route_blocked']=True;value['experimental_blockers']=blockers(value,c,bootstrap=True)
    value['protection_acceptance']='UNKNOWN_NO_ORDER_SENT';value['supervised_consent_present']=(folder(root,trial)/'authorization.dpapi').exists()
    value.update(experiment_profile=c['profile'],variant_version=variant_version(c),selected_risk_percent=str(selected_risk(c)),
        trade_classification='READ_ONLY_EXECUTION_READINESS_DIAGNOSTIC',strategy_success=False,orders_sent=0)
    ref=value.get('risk_input',{})
    if ref.get('status')=='ESTIMATED_REFERENCE_NOT_A_SIGNAL' and value.get('quote',{}).get('ask'):
        value['controlled_reference_size']=size(value['quote']['ask'],ref['stop'],ref['target'],stock.number(value['quote']['ask'])-stock.number(value['quote']['bid']),c)
    return value

def diagnose(root,trial):
    """Read-only readiness/economics diagnostic, NOT a filled execution cycle.

    This action cannot skip an H40 signal, transmit an order or contribute a
    winning trade to strategy statistics. A no-signal execution diagnostic
    would require another protocol and protected authorization, not Run.
    """
    value=inspect(root,trial);c=trial_config(root,trial);sized=value.get('controlled_reference_size',{})
    value['diagnostic_kind']='READ_ONLY_PRETRADE_DIAGNOSTIC'
    value['execution_diagnostic_performed']=False;value['strategy_signal_verified']=False
    value['no_signal_execution_protocol']='NOT_IMPLEMENTED_FOR_F_DO_NOT_REUSE_FOREX_EXECUTION_DIAGNOSTICS'
    value['reference_risk_fits_selected_budget']=sized.get('quantity')==1
    value['reference_target_net_positive']=sized.get('quantity',0)>0 and stock.number(sized['friction']['target_net'])>0
    value['strategy_entry_eligible']=False
    if c['profile']==R3_PROFILE:
        ref=value.get('risk_input',{});quote=value.get('quote',{})
        if ref.get('status')=='ESTIMATED_REFERENCE_NOT_A_SIGNAL' and quote.get('ask'):
            value['commission_cap_unverified_stress']=cap_unverified_stress(quote['ask'],ref['stop'],ref['target'],stock.number(quote['ask'])-stock.number(quote['bid']),c)
    if sized.get('quantity',0)>0 and not value['reference_target_net_positive']:
        value['economic_blocker']='ESTIMATED_TARGET_NET_NONPOSITIVE_RISK_ENGINE_ECONOMIC_FILTER_REMAINS'
    value['operational_blockers']=list(value['experimental_blockers'])
    if any((Path(root)/'.local'/p).exists() for p in ('paper-lab.emergency','paper-auto.stop','stock-paper-forward.stop','h40-paper-trial.stop')):value['operational_blockers'].append('PROTECTED_EMERGENCY_OR_STOP_ACTIVE')
    if not value['supervised_consent_present']:value['operational_blockers'].append('INDEPENDENT_SINGLE_USE_AUTHORIZATION_NOT_GRANTED')
    value['operational_blockers'].append('AUTHENTIC_NEXT_OPEN_H40_SIGNAL_NOT_VERIFIED_BY_REFERENCE_INSPECTION')
    if value.get('economic_blocker'):value['operational_blockers'].append(value['economic_blocker'])
    p=folder(root,trial)/'diagnostics';p.mkdir(exist_ok=True)
    dest=p/(stock.now().strftime('%Y%m%dT%H%M%S%f')+'-'+uuid.uuid4().hex[:8]+'.json')
    with dest.open('xb') as f:f.write(stock.encoded(value))
    dest.with_suffix('.sha256').write_text(stock.sha(dest),encoding='ascii')
    value['diagnostic_evidence_path']=str(dest);value['diagnostic_evidence_sha256']=stock.sha(dest)
    return value

def cap_unverified_stress(entry,stop,target,spread,c):
    """Conservative sensitivity, not a claim that IBKR omits its published cap.

    Keep both order minima until the account-specific cap application is known;
    retain regulatory/contingency components without inventing a new tariff.
    """
    from .ai_strategy_researcher.costs import commission_details
    from decimal import ROUND_CEILING
    model=size(entry,stop,target,spread,c)
    if not model.get('quantity'):return dict(status='ESTIMATED_SENSITIVITY_ONLY',quantity=0,reason=model['reason'])
    p=stock.number(model['entry']);fees=[]
    for side,price in (('BUY',p),('SELL',max(p,stock.number(target)))):
        d=commission_details(1,price,c['cost_model'],side)
        raw=sum(v for k,v in d['components'].items() if k!='rounding_reserve')
        raw+=max(D(1),d['base_rate'])-d['components']['base_commission']
        fees.append(raw.quantize(D('.01'),rounding=ROUND_CEILING)+D(c['partial_and_late_cost_allowance_usd'])/2)
    extra=sum(fees)-stock.number(model['fees']);risk_value=stock.number(model['risk'])+extra
    return dict(status='ESTIMATED_SENSITIVITY_ONLY_NOT_AN_IBKR_INVOICE',quantity=1,
        cap_application='UNKNOWN',opening_fee=str(fees[0]),closing_fee=str(fees[1]),fees=str(sum(fees)),
        estimated_loss=str(risk_value),selected_budget=model['budget'],fits_budget=risk_value<=stock.number(model['budget']),
        reserved_cash=str(p+sum(fees)),target_net=str(stock.number(model['friction']['target_net'])-extra))

def status(root,trial):
    c=trial_config(root,trial);p=folder(root,trial);result=dict(trial_id=trial,environment='PAPER_TRADING',live_enabled=False,
        authorized=(p/'authorization.dpapi').exists(),execution_ready=False,
        emergency=any((Path(root)/'.local'/n).exists() for n in ('paper-lab.emergency','paper-auto.stop')),
        global_opening_consumed=(Path(root)/'.local/h40-paper-trial-consumed.dpapi').exists())
    result.update(experiment_profile=c['profile'],variant_version=variant_version(c),selected_risk_percent=str(selected_risk(c)))
    if (p/'journal.sqlite3').exists():
        b=AccountBinding(unseal(Path(root)/'.local/ibkr-account-binding.dpapi'));j=stock.Journal(p/'journal.sqlite3',b.binding_id)
        try:result['revision'],result['ledger']=j.load()
        finally:j.close()
    return result

def wire_read(root,c,binding,read_only=True):
    from .stock_paper_forward_wire import stock_forward_wire
    e=SessionConfiguration.load(root)
    return stock_forward_wire(PaperOptions(binding.account,host=e.host,port=e.port,verified_tws_port=e.port,
        configured_endpoint=True,paper_mode_attested=True,read_only=read_only,client_id=93,timeout=20))

def snapshot_owned(wire,ledger,binding):
    binding.select(wire.accounts)
    value=owned_snapshot(wire.snapshot(),ledger);binding.select(wire.accounts);value['binding_id']=binding.binding_id
    return value

def protection_state(ledger,snapshot,c,stamp):
    i=ledger.state['intent']
    if not i:return 'FLAT'
    q=stock.number(i['position']);orders=snapshot['open_orders'];children=[o for o in orders if o['order_id'] in i['order_ids'][1:]]
    accepted=len(children)==2 and all(o['status'] in ('Submitted','PreSubmitted') and stock.number(o['quantity'])==q and o.get('perm_id',0)>0 for o in children)
    if q and accepted:return 'OWN_REMAINING_POSITION_PROTECTION_ACKNOWLEDGED'
    if q or (stamp-stock.at(i['first_send_at'])).total_seconds()>=c['protection_ack_seconds']:
        return 'SUPERVISED_PROTECTION_NOT_CONFIRMED_RECOVERY_REQUIRED'
    return 'AWAITING_ACK_NO_ACCEPTANCE_CLAIM'

def wait_bracket_ack(wire,ledger,c):
    # Do not spend the ACK deadline inside slow account/history queries. The
    # three independent ACKs are collected before a full position snapshot.
    deadline=time.monotonic()+c['protection_ack_seconds']
    while time.monotonic()<deadline:
        drain(wire,ledger);i=ledger.state['intent']
        if not wire.connected or i['uncertain'] or ledger.state['suspended']:break
        if all(str(oid) in i['orders'] and i['orders'][str(oid)].get('perm_id',0)>0 and i['orders'][str(oid)]['status'] in ('Submitted','PreSubmitted','Filled') for oid in i['order_ids']):
            ledger.write('BRACKET_ACK_RECEIVED_NOT_YET_POSITION_PROTECTION_VERIFIED');return True
        time.sleep(.05)
    ledger.suspend('BRACKET_ACK_DEADLINE_RECONCILE_RECOVERY_REQUIRED');return False

def run(root,trial):
    c=trial_config(root,trial);root=Path(root);p=folder(root,trial)
    binding=AccountBinding(unseal(root/'.local/ibkr-account-binding.dpapi'))
    # No allocation journal or connection until a genuine independent grant.
    temporary=TrialGuard(root,trial,None);temporary.grant(management=(p/'journal.sqlite3').exists())
    if (root/'.local/h40-paper-trial-consumed.dpapi').exists() and not (p/'journal.sqlite3').exists():raise PermissionError('ONE_GLOBAL_H40_TRIAL_ONLY')
    other=root/stock.FOLDER/'journal.sqlite3'
    if other.exists():
        j=stock.Journal(other,binding.binding_id)
        try:
            _,s=j.load()
            if s['intent'] or s['completed'] or stock.number(s['reservation']) or stock.number(s['consumed_loss']):raise PermissionError('EXPERIMENTAL_ALLOCATION_ALREADY_USED')
        finally:j.close()
    with run_lock(p/'runner.lock'):
        j=stock.Journal(p/'journal.sqlite3',binding.binding_id)
        def consume():seal_new(root/'.local/h40-paper-trial-consumed.dpapi',dict(trial_id=trial,binding_id=binding.binding_id,at=stock.now().isoformat()))
        ledger=TrialLedger(j,trial,consume,profile_config=c);guard=TrialGuard(root,trial,ledger);wire=None
        try:
            wire=wire_read(root,c,binding,False);binding.select(wire.connect());wire.bind_execution(guard,ledger)
            while True:
                guard.grant(management=ledger.state['intent'] is not None)
                snap=snapshot_owned(wire,ledger,binding);drain(wire,ledger);ledger.reconcile(snap)
                i=ledger.state['intent']
                if i:
                    state=protection_state(ledger,snap,c,stock.now());ledger.write('SUPERVISED_PROTECTION_STATUS',dict(status=state))
                    if state=='SUPERVISED_PROTECTION_NOT_CONFIRMED_RECOVERY_REQUIRED':
                        # With zero fills, stop the parent; keep children until
                        # cancellation/fills have been reconciled. A pending BUY
                        # must not survive a suspension as an unobserved entry.
                        if stock.number(i['position'])==0 and any(o['order_id']==i['order_ids'][0] and o['status']!='PendingCancel' for o in snap['open_orders']):
                            wire.cancel_owned(i['order_ids'][0])
                        ledger.suspend(state);return dict(state='SUSPENDED',reason=state,recovery_required=True,live_enabled=False)
                    manage(wire,ledger,snap)
                    if ledger.state['suspended']:return dict(state='SUSPENDED',reason=ledger.state['suspended'],recovery_required=True)
                else:
                    if ledger.state.get('opening_consumed'):return dict(state='COMPLETED_ONE_TRIAL',repeat=False,live_enabled=False)
                    guard.grant()
                    blocks=blockers(snap,c,guard.grant()['paper_evidence'],bootstrap=True)
                    if blocks:return dict(state='BLOCKED',blockers=blocks,orders_sent=0)
                    rows=wire.daily_context();snap=snapshot_owned(wire,ledger,binding);drain(wire,ledger);ledger.reconcile(snap)
                    session=snap['active_session'];stamp=stock.now()
                    if not session or not stock.at(session['start'])<=stamp<stock.at(session['start'])+timedelta(seconds=60):return dict(state='NO_TRADE',reason='AUTHENTIC_NEXT_OPEN_WINDOW_ABSENT',orders_sent=0)
                    completed=[r for r in rows if stock.at(r['closed_at'])<=stock.at(session['start'])]
                    opening=next((r for r in rows if stock.at(r['opened_at'])==stock.at(session['start'])),None)
                    signal=stock.h40_next_signal(completed,opening,session,stock.configuration(root)) if opening and len(completed)>=100 else None
                    if signal is None:return dict(state='NO_TRADE',reason='NO_AUTHENTIC_H40_SIGNAL',orders_sent=0)
                    sized=size(snap['quote']['ask'],signal['stop'],signal['target'],stock.number(snap['quote']['ask'])-stock.number(snap['quote']['bid']),c)
                    if not sized['quantity']:return dict(state='NO_TRADE',reason=sized['reason'],orders_sent=0)
                    first=max(wire.next_order_id,ledger.state['next_order_id']);key=stock.digest([stock.VERSION,signal['signal_at'],trial])
                    plan={**sized,'at':stamp.isoformat(),'intent':'H40-'+key[:32],'signal_key':key,'strategy_version':stock.VERSION,'trial_id':trial,
                        'side':'BUY','signal':signal,'stop':str(signal['stop']),'target':str(signal['target']),'cash':ledger.state['cash'],
                        'con_id':snap['contract']['con_id'],'order_ids':[first,first+1,first+2],'entry_session':session['start'],
                        'completed_bars':completed,'opening_bar':opening}
                    if c['profile']==R3_PROFILE:plan.update(experiment_profile=R3_PROFILE,variant_version=variant_version(c),trade_classification='H40_SIGNAL_PAPER_EXPERIMENT')
                    wire.bracket(snap,plan)
                    if not wait_bracket_ack(wire,ledger,c):return dict(state='SUSPENDED',reason=ledger.state['suspended'],recovery_required=True)
                time.sleep(c['poll_seconds'])
        except BaseException:
            if ledger.state['intent']:ledger.suspend('TRIAL_STOPPED_RECONCILIATION_REQUIRED')
            raise
        finally:
            if wire:wire.disconnect()
            j.close()

def recovery_read(root,trial,wire_factory=wire_read):
    c=trial_config(root,trial);p=folder(root,trial)
    if not (p/'journal.sqlite3').exists():raise PermissionError('NO_OWNED_TRIAL_INVENTORY')
    b=AccountBinding(unseal(Path(root)/'.local/ibkr-account-binding.dpapi'));j=stock.Journal(p/'journal.sqlite3',b.binding_id)
    wire=None
    try:
        l=TrialLedger(j,trial,profile_config=c);wire=wire_factory(root,c,b,True);b.select(wire.connect())
        s=snapshot_owned(wire,l,b);l.reconcile(s);i=l.state['intent']
        if not i:return dict(position='0',orders_sent=0,reservation=l.state['reservation'],recovery_needed=False)
        buys=[f for f in i['executions'].values() if f['side']=='BUY'];q=stock.number(i['position'])
        if not buys and q:raise PermissionError('OWNED_BUY_EXECUTION_REQUIRED')
        return dict(trial_id=trial,intent=i['intent'],binding_id=b.binding_id,con_id=i['con_id'],quantity=str(q),experiment_profile=c['profile'],recovery_scope=recovery_scope(c),variant_version=variant_version(c),
            buy_exec_ids=sorted(f['exec_id'] for f in buys),buy_perm_ids=sorted({f['perm_id'] for f in buys}),
            quote=s['quote'],active_session=s['active_session'],open_orders=s['open_orders'],reservation=l.state['reservation'],
            close_previously_attempted=i['sell_attempted'],journal_hash=j.db.execute('SELECT hash FROM events ORDER BY revision DESC LIMIT 1').fetchone()[0],orders_sent=0)
    finally:
        if wire:wire.disconnect()
        j.close()

class RecoveryGuard(TrialGuard):
    def grant(self,management=False):
        if not management:raise PermissionError('RECOVERY_CANNOT_OPEN_POSITION')
        stock.check_live();g=unseal(folder(self.root,self.trial)/'recovery.dpapi')
        b=AccountBinding(unseal(self.root/'.local/ibkr-account-binding.dpapi'));i=self.ledger.state['intent']
        if g.get('scope')!=recovery_scope(self.c) or g.get('trial_id')!=self.trial or g.get('binding_id')!=b.binding_id or g.get('account')!=b.account or g.get('environment')!='PAPER_TRADING' or g.get('live_enabled') is not False or g.get('revoked') is not False or g.get('source_hashes')!=hashes(self.root,self.c['profile']) or not i or g.get('intent')!=i['intent'] or g.get('con_id')!=i['con_id']:
            raise PermissionError('RECOVERY_POSITION_BOUND_AUTHORIZATION_REQUIRED')
        if self.c['profile']==R3_PROFILE and g.get('variant_version')!=variant_version(self.c):raise PermissionError('R3_VARIANT_AUTHORIZATION_REQUIRED')
        buys=[f for f in i['executions'].values() if f['side']=='BUY']
        if g.get('buy_exec_ids')!=sorted(f['exec_id'] for f in buys) or g.get('buy_perm_ids')!=sorted({f['perm_id'] for f in buys}) or not 0<=stock.number(i['position'])<=stock.number(g['quantity']):raise PermissionError('RECOVERY_OWNED_QUANTITY_CHANGED')
        if not stock.at(g['issued_at'])<=self.clock()<stock.at(g['expires_at']) or not 0<(stock.at(g['expires_at'])-stock.at(g['issued_at'])).total_seconds()<=1800:raise PermissionError('RECOVERY_AUTHORIZATION_EXPIRED')
        SessionConfiguration.load(self.root).matches(g)
        if not same_process(g['tws_pid'],g['tws_start_filetime']):raise PermissionError('TWS_PROTECTED_SESSION_CHANGED')
        return g
    def admission(self,*a):raise PermissionError('RECOVERY_CANNOT_OPEN_POSITION')

def recovery_run(root,trial):
    c=trial_config(root,trial);p=folder(root,trial);b=AccountBinding(unseal(Path(root)/'.local/ibkr-account-binding.dpapi'))
    if not (p/'journal.sqlite3').exists():raise PermissionError('NO_OWNED_TRIAL_INVENTORY')
    with run_lock(p/'runner.lock'):
        j=stock.Journal(p/'journal.sqlite3',b.binding_id);l=TrialLedger(j,trial,profile_config=c);g=RecoveryGuard(root,trial,l);wire=None
        try:
            g.grant(True);wire=wire_read(root,c,b,False);b.select(wire.connect());wire.bind_execution(g,l)
            s=snapshot_owned(wire,l,b);drain(wire,l);l.reconcile(s);i=l.state['intent']
            if not i or stock.number(i['position'])==0:return dict(state='FLAT_OR_COMMISSION_PENDING',orders_sent=0,reservation=l.state['reservation'])
            g.grant(True)
            if s['open_orders']:
                for order in s['open_orders']:
                    if order['status']!='PendingCancel':wire.cancel_owned(order['order_id'])
                return dict(state='CANCEL_PENDING_RECONCILE_BEFORE_CLOSE',close_sent=False)
            if i['sell_attempted']:raise PermissionError('PREVIOUS_CLOSE_ATTEMPT_REQUIRES_RECONCILIATION_NO_RETRY')
            wire.close_owned(s,s['quote']['bid'],'EXPLICIT_SUPERVISED_RECOVERY_CLOSE_ONLY')
            # No retry or order modification. Persist SELL attempt before send;
            # actual flat/final commission state is reconciled in RecoveryInspect.
            return dict(state='RECOVERY_EXIT_SENT_RECONCILIATION_REQUIRED',repeat=False,emergency_unchanged=True)
        except BaseException:
            if l.state['intent']:l.suspend('RECOVERY_RECONCILIATION_REQUIRED')
            raise
        finally:
            if wire:wire.disconnect()
            j.close()

def cancel_pending(root,trial):
    """Reduce pending order risk using the original management-only consent.

    Parent first; never remove children while any owned long could remain.
    No BUY, SELL, order modification, or implicit recovery authorization.
    """
    c=trial_config(root,trial);p=folder(root,trial);b=AccountBinding(unseal(Path(root)/'.local/ibkr-account-binding.dpapi'))
    if not (p/'journal.sqlite3').exists():raise PermissionError('NO_PENDING_TRIAL')
    with run_lock(p/'runner.lock'):
        j=stock.Journal(p/'journal.sqlite3',b.binding_id);l=TrialLedger(j,trial,profile_config=c);wire=None
        try:
            g=TrialGuard(root,trial,l);g.grant(True);wire=wire_read(root,c,b,False);b.select(wire.connect());wire.bind_execution(g,l)
            s=snapshot_owned(wire,l,b);drain(wire,l);l.reconcile(s)
            ids=pending_cancel_ids(l,s)
            for oid in ids:wire.cancel_owned(oid)
            return dict(state='CANCEL_REQUESTED_RECONCILE_REQUIRED' if ids else 'NO_CANCEL_SENT_REVIEW_RECONCILIATION',
                cancellation_requests=len(ids),new_orders_sent=0,emergency_unchanged=True)
        finally:
            if wire:wire.disconnect()
            j.close()

def pending_cancel_ids(ledger,snapshot):
    i=ledger.state['intent']
    if not i:return []
    if stock.number(i['position'])!=0:raise PermissionError('OWNED_LONG_REQUIRES_POSITION_RECOVERY_KEEP_PROTECTION')
    parent=next((o for o in snapshot['open_orders'] if o['order_id']==i['order_ids'][0]),None)
    if parent:return [] if parent['status']=='PendingCancel' else [parent['order_id']]
    acknowledged=i['orders'].get(str(i['order_ids'][0]))
    if not acknowledged or acknowledged['status'] not in stock.TERMINAL:raise PermissionError('PARENT_TERMINAL_RECONCILIATION_REQUIRED')
    return [o['order_id'] for o in snapshot['open_orders'] if o['status']!='PendingCancel']

def main():
    a=argparse.ArgumentParser();a.add_argument('action',choices=('Prepare','Inspect','Diagnose','Assess','Status','Run','Stop','Revoke','RecoveryInspect','RecoveryRun','CancelPending'))
    a.add_argument('--root',default=str(Path(__file__).resolve().parents[2]));a.add_argument('--trial');a.add_argument('--evidence');a.add_argument('--profile',choices=(R2_PROFILE,R3_PROFILE),default=R2_PROFILE)
    v=a.parse_args();root=Path(v.root);config(root,v.profile)
    if v.action=='Prepare':result=prepare(root,v.profile)
    else:
        protocol(root,v.trial)
        if v.action=='Inspect':result=inspect(root,v.trial)
        elif v.action=='Diagnose':result=diagnose(root,v.trial)
        elif v.action=='Assess':
            c=trial_config(root,v.trial);s=inspect(root,v.trial);e=evidence(root,v.evidence,s['binding_id'],expected_scope=entry_scope(c))
            result=dict(blockers=blockers(s,c,e,bootstrap=True),binding_id=s['binding_id'],scope=entry_scope(c),experiment_profile=c['profile'],variant_version=variant_version(c),
                evidence_sha256=stock.sha(v.evidence),paper_evidence=e,orders_sent=0)
        elif v.action=='Status':result=status(root,v.trial)
        elif v.action=='Run':result=run(root,v.trial)
        elif v.action=='RecoveryInspect':result=recovery_read(root,v.trial)
        elif v.action=='RecoveryRun':result=recovery_run(root,v.trial)
        elif v.action=='CancelPending':result=cancel_pending(root,v.trial)
        else:
            stop= root/'.local/h40-paper-trial.stop';stop.parent.mkdir(exist_ok=True);stop.write_text(stock.now().isoformat())
            grant=folder(root,v.trial)/'authorization.dpapi'
            if v.action=='Revoke' and grant.exists():
                g=unseal(grant);g['revoked']=True;tmp=grant.with_suffix('.tmp');tmp.write_bytes(protect(stock.encoded(g)));tmp.replace(grant)
            result=dict(stopped_new_entries=True,revoked=v.action=='Revoke',owned_management_required=True,emergency_unchanged=True,live_enabled=False)
    print(json.dumps(result,default=str,allow_nan=False))

if __name__=='__main__':
    try:main()
    except Exception as e:
        msg=str(e);print(json.dumps(dict(state='BLOCKED',reason=msg if re.fullmatch('[A-Z][A-Z0-9_]{1,100}',msg) else 'H40_TRIAL_FAILED',reason_type=type(e).__name__,live_enabled=False)))
        raise SystemExit(1)
