"""One independently authorized Ford Paper execution measurement, not a strategy.

Prepare/Inspect/WhatIf/Assess/Status never submit market orders. Run requires a
separate protected grant. UNKNOWN is not a permission and preview is not a fill.
"""
import argparse
import copy
from contextvars import ContextVar
from datetime import timedelta
from decimal import Decimal, ROUND_CEILING
import json
from pathlib import Path
import queue
import re
import sqlite3
import subprocess
import threading
import time
import uuid
from . import stock_paper_forward as stock
from .broker import PaperOptions
from .ibkr_session import AccountBinding, SessionConfiguration
from .paper_lab import unseal, same_process
from .paper_identity import protect
from .stock_paper_forward_runner import run_lock
from .stock_paper_forward_wire import stock_forward_wire
from .ford_whatif import whatif_wire
from .ai_strategy_researcher.costs import commission_details

D=Decimal
SCOPE='FORD_EXECUTION_DIAGNOSTIC_ONE_SHARE_V1'
RECOVERY_SCOPE='FORD_DIAGNOSTIC_OWNED_RECOVERY_ONLY_V1'
FOLDER='artifacts/paper-diagnostics/ford'
CAPS=tuple(k for k in stock.CAPABILITIES if k not in ('corporate_actions','protection_acceptance','partial_fill_protection'))
STOP_NAMES=('paper-lab.emergency','paper-auto.stop','stock-paper-forward.stop','h40-paper-trial.stop','ford-diagnostic.stop')
EXPECTED=dict(schema_version=1,scope=SCOPE,environment='PAPER_TRADING',symbol='F',con_id=9599491,
    capital_usd=100,risk_budget_usd=3,external_forecast_ceiling_usd=10,maximum_quantity=1,
    maximum_opening_attempts=1,authorization_minutes=30,entry_lifetime_seconds=30,
    initiate_close_seconds=30,maximum_close_initiation_seconds=60,minimum_rth_remaining_seconds=180,protection_ack_seconds=5,
    stop_fraction=.01,target_fraction=.02,gap_fraction=.02,slippage_fraction_per_side=.0005,
    fee_contingency_usd=1,default_commission_cap='UNKNOWN',client_id=94,physical_client_id=93,
    request_timeout_seconds=20,poll_seconds=1,supervised=True,live_enabled=False)

R10_SCOPE='FORD_DIAGNOSTIC_R10'
PROFILE=ContextVar('ford_diagnostic_profile',default=SCOPE)

def active_scope():return PROFILE.get()
def recovery_scope():return RECOVERY_SCOPE if active_scope()==SCOPE else 'FORD_DIAGNOSTIC_R10_RECOVERY_CLOSE_ONLY'
def selected_budget():return 10 if active_scope()==R10_SCOPE else 3

def configuration(root):
    stock.check_live();filename='ford-diagnostic-r10.json' if active_scope()==R10_SCOPE else 'ford-execution-diagnostic.json'
    c=json.loads((Path(root)/'config'/filename).read_text())
    expected={**EXPECTED,'scope':active_scope(),'risk_budget_usd':selected_budget()}
    if c!=expected:raise PermissionError('FORD_DIAGNOSTIC_PREREGISTERED_LIMITS_CHANGED')
    return c

def folder(root,trial):
    if not re.fullmatch('ford-diag-[a-f0-9]{32}',trial or ''):raise PermissionError('INVALID_FORD_DIAGNOSTIC_ID')
    return Path(root)/FOLDER/trial

def sources(root):
    paths=('config/ford-diagnostic-r10.json','python/trading_agent/ford_diagnostic_evidence.py','src/TradingAgent.Infrastructure/FordDiagnosticStore.cs','src/TradingAgent.Infrastructure/Migrations/005_ford_diagnostic.sql','src/TradingAgent.Api/FordDiagnosticEvidenceCommand.cs','python/trading_agent/ai_strategy_researcher/execution_memory.py','config/ford-execution-diagnostic.json','python/trading_agent/ford_execution_diagnostic.py',
        'python/trading_agent/ford_whatif.py','scripts/ford-execution-diagnostic.ps1',
        'python/trading_agent/stock_paper_forward.py','python/trading_agent/stock_paper_forward_wire.py',
        'python/trading_agent/stock_paper_forward_runner.py','python/trading_agent/ai_strategy_researcher/costs.py',
        'src/TradingAgent.Core/FordDiagnosticRisk.cs','src/TradingAgent.Core/Risk.cs',
        'src/TradingAgent.Core/ExecutionFeasibility.cs','src/TradingAgent.Api/FordDiagnosticCommand.cs',
        'src/TradingAgent.Api/Program.cs','src/TradingAgent.Api/bin/Debug/net9.0/TradingAgent.Api.dll',
        'src/TradingAgent.Core/bin/Debug/net9.0/TradingAgent.Core.dll',
        'src/TradingAgent.Infrastructure/bin/Debug/net9.0/TradingAgent.Infrastructure.dll')
    return {p:stock.sha(Path(root)/p) for p in paths}

def save_new(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as f:f.write(stock.encoded(value));f.flush();__import__('os').fsync(f.fileno())
    path.with_suffix('.sha256').write_text(stock.sha(path),encoding='ascii')
    return str(path)

def seal_new(path,value):
    data=protect(stock.encoded(value))
    with Path(path).open('xb') as f:f.write(data);f.flush();__import__('os').fsync(f.fileno())

def prepare(root):
    c=configuration(root);trial='ford-diag-'+uuid.uuid4().hex;p=folder(root,trial)
    p.mkdir(parents=True,exist_ok=False)
    value=dict(trial_id=trial,scope=active_scope(),configuration=c,created_at=stock.now().isoformat(),
        classification='EXECUTION_DIAGNOSTICS',strategy_version=None,source_hashes=sources(root),
        strategy_success=False,execution_authorized=False,live_enabled=False)
    save_new(p/'protocol.json',value)
    return dict(trial_id=trial,protocol_sha256=stock.sha(p/'protocol.json'),orders_sent=0)

def protocol(root,trial):
    p=folder(root,trial);v=json.loads((p/'protocol.json').read_text())
    if (p/'protocol.sha256').read_text()!=stock.sha(p/'protocol.json') or v['trial_id']!=trial or v['scope']!=active_scope() or v['configuration']!=configuration(root) or v['source_hashes']!=sources(root) or v['strategy_version'] is not None or v['classification']!='EXECUTION_DIAGNOSTICS':
        raise PermissionError('FORD_DIAGNOSTIC_PROTOCOL_OR_DEPLOYMENT_CHANGED')
    return v

def binding(root):return AccountBinding(unseal(Path(root)/'.local/ibkr-account-binding.dpapi'))

def wire_for(root,b,preview=False,mutable=False):
    c=configuration(root);e=SessionConfiguration.load(root)
    o=PaperOptions(b.account,host=e.host,port=e.port,verified_tws_port=e.port,configured_endpoint=True,
        paper_mode_attested=True,read_only=not mutable,client_id=c['physical_client_id'] if mutable else c['client_id'],timeout=c['request_timeout_seconds'])
    if preview:return whatif_wire(o)
    return execution_wire(o)

def execution_wire(options,sdk_types=None):
    base=stock_forward_wire(options,sdk_types);original=base.build
    # Preserve the adapter instance captured by its guarded SDK client closure.
    def build(self,i,index,quantity=None,price=None):
        order,fields=original(i,index,quantity,price)
        if index==0:
            order.goodTillDate=stock.at(i['opening_deadline']).strftime('%Y%m%d-%H:%M:%S')
            fields['goodTillDate']=order.goodTillDate
        return order,fields
    base.build=__import__('types').MethodType(build,base)
    original_ack=base.openOrder
    def ack(self,oid,contract,order,state):
        original_ack(oid,contract,order,state)
        if oid in self.ack_rows and order.account==options.account:
            self.ack_rows[oid].update(limit_price=str(stock.number(order.lmtPrice)),stop_price=str(stock.number(order.auxPrice)))
    base.openOrder=__import__('types').MethodType(ack,base)
    original_close=base.close_owned
    def close(self,s,price,reason):
        i=self.ledger.state['intent']
        if i:
            i['close_limit_expected']=str(stock.number(price));self.ledger.write('DIAGNOSTIC_EXIT_EXPECTATION',dict(limit=str(price),reason=reason))
        return original_close(s,price,reason)
    base.close_owned=__import__('types').MethodType(close,base)
    return base

def snapshot(wire,b,ledger=None):
    b.select(wire.accounts);s=wire.snapshot();b.select(wire.accounts);s['binding_id']=b.binding_id
    if ledger:
        i=ledger.state['intent'];ref=i['intent'] if i else None
        s['completed_orders']=[o for o in s['completed_orders'] if o.get('order_ref')==ref]
        s['executions']=[f for f in s['executions'] if f.get('order_ref')==ref]
        ids={f['exec_id'] for f in s['executions']};s['commissions']=[f for f in s['commissions'] if f['exec_id'] in ids]
    return s

def receipts(root,path,bid,clock=stock.now):
    if not path:return {}
    v=json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if v.get('environment')!='PAPER_TRADING' or v.get('binding_id')!=bid or v.get('scope')!=active_scope():raise PermissionError('DIAGNOSTIC_PAPER_RECEIPTS_SCOPE_REQUIRED')
    for k,r in v.get('capabilities',{}).items():
        if k not in CAPS+('commission_cap',) or r.get('status')!='VERIFIED' or r.get('compatible') is not True or r.get('source') not in ('OPERATOR_PAPER_TWS','OPERATOR_PAPER_CLIENT_PORTAL') or not r.get('reference') or not 0<=(clock()-stock.at(r['observed_at'])).total_seconds()<=86400:
            raise PermissionError('DIAGNOSTIC_RECEIPT_INVALID')
        value=r.get('value')
        if k in ('available_funds','settled_cash') and stock.number(value)<100 or k in ('whole_share_minimum','quantity_increment') and stock.number(value)!=1 or k=='contract_margin' and not 0<=stock.number(value)<=1:raise PermissionError('DIAGNOSTIC_RECEIPT_RESTRICTED')
        expected={'stock_permission':True,'account_restrictions':'WHOLE_SHARE_CASH_LONG_ALLOWED','commission_cap':'FIXED_1_PERCENT_CAP_WITH_ADDONS_VERIFIED'}
        if k in expected and value!=expected[k] or k=='effective_fees' and value not in ('FIXED','TIERED'):raise PermissionError('DIAGNOSTIC_RECEIPT_RESTRICTED')
    return v

def cap_confirmed(e):return e.get('capabilities',{}).get('commission_cap',{}).get('value')=='FIXED_1_PERCENT_CAP_WITH_ADDONS_VERIFIED'

def fee_estimate(price,side,cap=False):
    details=commission_details(1,price,'FIXED_FEE_STRESS',side)
    if cap:return stock.commission(1,price,'FIXED_FEE_STRESS',side)+D('.5')
    raw=sum(v for k,v in details['components'].items() if k!='rounding_reserve')
    raw+=max(D(1),details['base_rate'])-details['components']['base_commission']
    return raw.quantize(D('.01'),rounding=ROUND_CEILING)+D('.5')

def scenario(quote,c,cap=False):
    ask=stock.number(quote['ask']);bid=stock.number(quote['bid'])
    if not 0<bid<=ask:raise ValueError('DIAGNOSTIC_INVALID_QUOTE')
    spread=max(ask-bid,ask*D('.0005'));slip=ask*D(str(c['slippage_fraction_per_side']))
    entry=stock.tick(ask+spread/2+slip,True)
    stop=stock.tick(bid-max(bid*D(str(c['stop_fraction'])),D('.02')))
    target=stock.tick(entry*(1+D(str(c['target_fraction']))),True)
    opening=fee_estimate(entry,'BUY',cap);closing=fee_estimate(target,'SELL',cap)
    fees=opening+closing;gap=ask*D(str(c['gap_fraction']))
    geometry=abs((entry+bid)/2-stop)+(entry-bid)
    risk=geometry+fees+2*slip+D('.02')+gap
    reserve=entry+fees
    return dict(quantity=1,entry=str(entry),stop=str(stop),target=str(target),opening_fee=str(opening),
        closing_fee=str(closing),fees=str(fees),risk=str(risk),reserved_cash=str(reserve),
        slippage_per_unit=str(2*slip+D('.02')),gap_per_unit=str(gap),budget=str(c['risk_budget_usd']),cap_confirmed=cap,
        fits_budget=risk<=D(str(c['risk_budget_usd'])) and reserve<=100,status='ESTIMATED_NOT_EXECUTION_VERIFIED',
        friction=dict(spread=str(spread),slippage=str(2*slip),gap=str(gap)),
        adverse_scenarios=dict(gap_10_percent_loss=str(geometry+fees+2*slip+D('.02')+ask*D('.10')),
            protection_failure_25_percent_loss=str(entry*D('.25')+fees),total_inventory_loss=str(reserve),
            losses_can_exceed_stop_and_budget=True),strategy_success=False)

def blockers(s,c,e=None,bootstrap=False,clock=stock.now):
    e=e or {};s=copy.deepcopy(s);caps=s.setdefault('capabilities',{})
    for k,r in e.get('capabilities',{}).items():
        if caps.get(k,{}).get('status')=='UNKNOWN':caps[k]=r
    v=stock.readiness(s,dict(maximum_quote_age_seconds=15),clock())
    v=[b for b in v if b not in ('H40_RISK_2_PERCENT_EXCEEDS_PRODUCTIVE_0_5_PERCENT','CORPORATE_ACTIONS_UNKNOWN_OR_RESTRICTED')]
    if s.get('active_session'):
        try:
            if (stock.at(s['active_session']['end'])-clock()).total_seconds()<c['minimum_rth_remaining_seconds']:v.append('DIAGNOSTIC_TOO_NEAR_RTH_CLOSE')
        except (KeyError,ValueError):v.append('DIAGNOSTIC_SESSION_END_UNKNOWN')
    if bootstrap:
        v=[b for b in v if b not in ('PROTECTION_ACCEPTANCE_UNKNOWN_OR_RESTRICTED','PARTIAL_FILL_PROTECTION_UNKNOWN_OR_RESTRICTED')]
        if not {'LMT','STP','OCA'}<=set(s.get('declared_protection',{}).get('order_types','').split(',')):v.append('DECLARED_PROTECTIVE_TYPES_UNAVAILABLE')
        for k in ('protection_acceptance','partial_fill_protection'):
            r=caps.get(k,{})
            if r.get('status')!='UNKNOWN' and (r.get('status')!='VERIFIED' or r.get('compatible') is not True):v.append('PROTECTION_PREVIOUSLY_RESTRICTED')
    for k in CAPS:
        r=caps.get(k,{})
        if r.get('status')=='VERIFIED':
            try:
                if not 0<=(clock()-stock.at(r['observed_at'])).total_seconds()<=86400:v.append(k.upper()+'_EVIDENCE_EXPIRED')
            except (KeyError,ValueError):v.append(k.upper()+'_TIME_UNKNOWN')
    try:
        if not scenario(s['quote'],c,cap_confirmed(e))['fits_budget']:v.append('DIAGNOSTIC_COSTS_GAPS_EXCEED_SELECTED_'+str(c['risk_budget_usd'])+'_USD_BUDGET')
    except (KeyError,ValueError,TypeError):v.append('DIAGNOSTIC_COST_GEOMETRY_UNKNOWN')
    return list(dict.fromkeys(v))

def readonly(root,trial,preview=False,path=None):
    protocol(root,trial);c=configuration(root);b=binding(root);wire=None
    value=dict(environment='PAPER_TRADING',scope=active_scope(),classification='EXECUTION_DIAGNOSTICS',
        strategy_version=None,strategy_success=False,market_orders_sent=0,live_enabled=False)
    stem=stock.now().strftime('%Y%m%dT%H%M%S%f')+'-'+uuid.uuid4().hex[:8]
    out=folder(root,trial)/'evidence'/stem
    try:
        wire=wire_for(root,b,preview=preview);b.select(wire.connect());s=snapshot(wire,b);value['snapshot']=s
        e=receipts(root,path,b.binding_id);value['binding_id']=b.binding_id
        if s['quote'].get('ask') and s['quote'].get('bid'):
            value['conservative_no_cap']=scenario(s['quote'],c)
            value['published_cap_sensitivity']=scenario(s['quote'],c,True)
        if preview:
            value['what_if']=wire.preview(s,s['quote']['ask'],lambda v:save_new(out.with_name(stem+'-whatif-attempt.json'),v))
            value['after_preview']=snapshot(wire,b)
            if value['after_preview']['positions'] or value['after_preview']['open_orders']:raise PermissionError('WHAT_IF_POSTCHECK_UNEXPECTED_INVENTORY_OR_ORDER')
            value['what_if_available']=True;value['executed_commission']=None
            value['closing_commission_estimate']='UNKNOWN_NO_SELL_PREVIEW_ON_FLAT_ACCOUNT'
        value['blockers']=blockers(s,c,e,bootstrap=True)
        if active_scope()==R10_SCOPE:
            from .ford_diagnostic_evidence import probe
            try:value['postgres_journal']=probe(root,trial,b.binding_id,active_scope())
            except PermissionError:
                value['postgres_journal']='UNKNOWN_UNAVAILABLE_OR_MIGRATION_REQUIRED'
                value['blockers'].append('R10_POSTGRES_JOURNAL_UNAVAILABLE')
            try:other_reservations(root)
            except PermissionError:value['blockers'].append('ANOTHER_EXPERIMENTAL_ALLOCATION_IS_RESERVED')
        if any((Path(root)/'.local'/n).exists() for n in STOP_NAMES):value['blockers'].append('PROTECTED_EMERGENCY_OR_STOP_ACTIVE')
        value['blockers'].append('INDEPENDENT_DIAGNOSTIC_AUTHORIZATION_NOT_GRANTED')
        value['paper_evidence']=e
    except Exception as exc:
        value['error_type']=type(exc).__name__;code=str(exc)
        value['error']=code if re.fullmatch('[A-Z][A-Z0-9_]{1,100}',code) else 'DIAGNOSTIC_READ_OR_PREVIEW_FAILED'
        value['what_if_available']=False
    finally:
        if wire:value['ibkr_events']=wire.events[:];wire.disconnect()
    value['evidence_path']=str(out.with_suffix('.json').relative_to(root))
    save_new(out.with_suffix('.json'),value);return value

class Journal(stock.Journal):
    """Reuse append/CAS implementation with an independent non-strategy scope."""
    def __init__(self,path,bid,trial):
        self.mirror=None
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True);self.binding=bid;self.trial=trial
        self.db=sqlite3.connect(self.path,timeout=10,check_same_thread=False);self.lock=threading.RLock()
        self.db.execute('PRAGMA journal_mode=WAL');self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('CREATE TABLE IF NOT EXISTS events (revision INTEGER PRIMARY KEY, at TEXT NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL, previous TEXT NOT NULL, hash TEXT NOT NULL)');self.db.commit()
        if not self.db.execute('SELECT 1 FROM events LIMIT 1').fetchone():
            s=stock.initial(bid);s.update(strategy_version=None,scope=active_scope(),classification='EXECUTION_DIAGNOSTICS',trial_id=trial,opening_consumed=False)
            self.commit(0,s,'DIAGNOSTIC_INITIAL_ALLOCATION')
        try:self.load()
        except BaseException:self.db.close();raise
    def load(self):
        previous='';revision=0;state=None
        for r,stamp,kind,payload,prior,h in self.db.execute('SELECT * FROM events ORDER BY revision'):
            if r!=revision+1 or prior!=previous or stock.digest([r,stamp,kind,json.loads(payload),prior])!=h:raise PermissionError('DIAGNOSTIC_JOURNAL_INTEGRITY_FAILURE')
            state=json.loads(payload)['state'];previous=h;revision=r
        if not state or state['binding_id']!=self.binding or state['trial_id']!=self.trial or state['scope']!=active_scope() or state['environment']!='PAPER_TRADING' or state['strategy_version'] is not None or state['classification']!='EXECUTION_DIAGNOSTICS':raise PermissionError('DIAGNOSTIC_JOURNAL_SCOPE_MISMATCH')
        return revision,state

class Ledger(stock.Ledger):
    def __init__(self,j,consume=lambda:None):super().__init__(j);self.consume=consume
    def write(self,kind,details=None):
        d=copy.deepcopy(details or {});d.update(scope=active_scope(),classification='EXECUTION_DIAGNOSTICS',strategy_version=None,strategy_success=False)
        if kind=='FILL':
            i=self.state['intent'];sent=i.get('first_send_at')
            d['time_from_opening_send_seconds']=(stock.at(d['at'])-stock.at(sent)).total_seconds() if sent else None
        if kind=='TRADE_SETTLED':
            kind='DIAGNOSTIC_CYCLE_SETTLED';d['commission_evidence']='OBSERVED_SIMULATED_PAPER_EXECUTION'
        super().write(kind,d)
    def reconcile(self,s):
        if s.get('connected') is not True:raise PermissionError('DIAGNOSTIC_CONNECTED_RECONCILIATION_REQUIRED')
        i=self.state['intent']
        if i:
            rows=list(i['executions'].values())+s['executions']
            for o in s['open_orders']+s['completed_orders']+list(i['orders'].values()):
                if o['order_id']==i['order_ids'][0] and (o['status']=='Filled' or D(o.get('filled','0'))>0) and not any(f['side']=='BUY' for f in rows):
                    self.write('FILL_STATUS_WITHOUT_EXEC_DETAILS_RESERVATION_HELD',o)
                    raise PermissionError('DIAGNOSTIC_FILL_DETAILS_PENDING')
            self.write('BROKER_RECONCILIATION_EVIDENCE',{k:s.get(k) for k in ('at','quote','positions','open_orders','account_queries','capabilities')})
        result=super().reconcile(s)
        if self.journal.mirror and self.journal.mirror.sync():
            from .ford_diagnostic_evidence import completed_receipt
            completed_receipt(self.journal.mirror.root,self.journal,self.journal.mirror)
        return result
    def entry_block(self,stamp):return 'ONE_DIAGNOSTIC_ONLY' if self.state['opening_consumed'] or self.state['completed'] else super().entry_block(stamp)
    def order(self,row):
        i=self.state['intent'];oid=row['order_id']
        if not i:raise PermissionError('DIAGNOSTIC_ACK_WITHOUT_INTENT')
        expected_type='STP' if oid==i['order_ids'][2] else 'LMT'
        price_key='stop_price' if expected_type=='STP' else 'limit_price'
        expected=i['stop'] if expected_type=='STP' else i['entry'] if oid==i['order_ids'][0] else i['target'] if oid==i['order_ids'][1] else i.get('close_limit_expected')
        if row.get('order_type')!=expected_type or expected is None or row.get(price_key) is None or D(row[price_key])!=D(expected):raise PermissionError('DIAGNOSTIC_BROKER_PROTECTION_TYPE_OR_PRICE_CHANGED')
        return super().order(row)
    def reserve(self,p):
        if self.entry_block(p['at']):raise PermissionError(self.entry_block(p['at']))
        spent=D(p['entry'])+D(p['fees'])
        if self.state['scope']!=active_scope() or p.get('diagnostic_scope')!=active_scope() or p.get('strategy_version') is not None or p.get('classification')!='EXECUTION_DIAGNOSTICS' or p['quantity']!=1 or p['side']!='BUY' or not 0<D(p['risk'])<=selected_budget() or spent>min(D(100),D(self.state['cash']),D(self.state['equity'])) or not D(p['stop'])<D(p['entry'])<D(p['target']):raise PermissionError('DIAGNOSTIC_RESERVATION_LIMITS')
        if len(set(p['order_ids']))!=3 or min(p['order_ids'])<self.state['next_order_id']:raise PermissionError('ORDER_ID_COLLISION')
        self.state['next_order_id']=max(p['order_ids'])+1;self.state['reservation']=str(spent)
        self.state['diagnostic_estimated_fees']=p['fees']
        self.state['intent']={**copy.deepcopy(p),'state':'PREPARED','orders':{},'executions':{},'fees_observed':{},'attempted':[],
            'sell_attempted':False,'first_fill_at':None,'uncertain':False,'last_reconciled_at':None,'position':'0'}
        self.write('DIAGNOSTIC_RESERVED',dict(risk=p['risk']))
    def pre_send(self,oid):
        i=self.state['intent']
        if not i or oid in i['attempted'] or i['uncertain']:raise PermissionError('NO_BLIND_DIAGNOSTIC_RETRY')
        if not self.state['opening_consumed']:
            if oid!=i['order_ids'][0]:raise PermissionError('DIAGNOSTIC_BUY_MUST_BE_FIRST')
            self.consume();self.state['opening_consumed']=True;self.write('ONE_USE_CONSUMED_BEFORE_SEND')
            i['first_send_at']=stock.now().isoformat()
        super().pre_send(oid)
        # SEND_PENDING is durable locally AND in PG before the one opening.
        # An outage must not prevent owned protection/reduction after a send.
        if self.journal.mirror:self.journal.mirror.sync(required=oid==i['order_ids'][0])

def request(p,s):
    r=stock.risk_request(p,s);r['proposedRisk']=D(selected_budget())/100;r['execution']['source']=active_scope()
    r['execution']['takeProfit']=None # diagnostic measurement, not H40/economic approval
    return r

def risk(root,state,p,s):
    stamp=stock.now().isoformat()
    if state['intent'] or state['completed'] or D(state['consumed_loss']) or D(state['equity'])!=100:raise PermissionError('DIAGNOSTIC_ALLOCATION_ALREADY_USED')
    a=dict(accountId='PAPER-FORD-EXECUTION-DIAGNOSTIC',equity=100,units=1,dayNav=100,weekNav=100,highNav=100,at=stamp,
        capital=dict(initialCapital=100,lossAllowance=20,environment='PAPER_TRADING'))
    raw=dict(account=a,request=request(p,s),diagnostic_scope=active_scope(),cash=state['cash'],reservations=state['reservation'])
    result=subprocess.run(['dotnet',str(Path(root)/'src/TradingAgent.Api/bin/Debug/net9.0/TradingAgent.Api.dll'),'--ford-diagnostic-risk'],input=stock.encoded(raw).decode(),capture_output=True,text=True,timeout=20,cwd=root)
    if result.returncode:raise PermissionError('DIAGNOSTIC_RISK_PROTOCOL_UNAVAILABLE')
    v=json.loads(result.stdout)
    if v.get('allowed') is True and (D(str(v['quantity']))!=1 or D(str(v['estimatedLoss']))>D(p['risk'])):raise PermissionError('DIAGNOSTIC_RISK_RESERVATION_BELOW_ENGINE')
    return v

class Guard:
    def __init__(self,root,trial,ledger,clock=stock.now,loader=None,recovery=False,cancel_only=False):
        self.root=Path(root);self.trial=trial;self.ledger=ledger;self.clock=clock;self.loader=loader;self.recovery=recovery;self.cancel_only=cancel_only
    def grant(self,management=False):
        protocol(self.root,self.trial);b=binding(self.root)
        g=self.loader() if self.loader else unseal(folder(self.root,self.trial)/('recovery.dpapi' if self.recovery else 'authorization.dpapi'))
        scope=recovery_scope() if self.recovery else active_scope()
        if g.get('scope')!=scope or g.get('trial_id')!=self.trial or g.get('account')!=b.account or g.get('binding_id')!=b.binding_id or g.get('environment')!='PAPER_TRADING' or g.get('live_enabled') is not False or g.get('source_hashes')!=sources(self.root) or g.get('protocol_sha256')!=stock.sha(folder(self.root,self.trial)/'protocol.json') or g.get('read_only_disabled_checked') is not True:raise PermissionError('DIAGNOSTIC_PROTECTED_SCOPE_REQUIRED')
        SessionConfiguration.load(self.root).matches(g)
        if not same_process(g['tws_pid'],g['tws_start_filetime']):raise PermissionError('DIAGNOSTIC_TWS_PROCESS_CHANGED')
        if self.recovery:
            if not management:raise PermissionError('RECOVERY_CANNOT_OPEN')
            i=self.ledger.state['intent'];buys=[f for f in i['executions'].values() if f['side']=='BUY'] if i else []
            if not buys or g.get('intent')!=i['intent'] or g.get('con_id')!=i['con_id'] or g.get('buy_exec_ids')!=sorted(f['exec_id'] for f in buys) or g.get('buy_perm_ids')!=sorted({f['perm_id'] for f in buys}) or not 0<=D(i['position'])<=D(g['quantity']):raise PermissionError('RECOVERY_OWNED_INVENTORY_REQUIRED')
        if not management or self.recovery:
            if g.get('revoked') is not False or not stock.at(g['issued_at'])<=self.clock()<stock.at(g['expires_at']) or not 0<(stock.at(g['expires_at'])-stock.at(g['issued_at'])).total_seconds()<=1800:raise PermissionError('DIAGNOSTIC_GRANT_EXPIRED_OR_REVOKED')
        if not management:
            if (folder(self.root,self.trial)/'revoked.json').exists():raise PermissionError('DIAGNOSTIC_AUTHORIZATION_REVOKED')
            if any((self.root/'.local'/n).exists() for n in STOP_NAMES):raise PermissionError('DIAGNOSTIC_EMERGENCY_OR_STOP_ACTIVE')
            if (self.root/'.local/ford-diagnostic-consumed.dpapi').exists() and (not self.ledger or not self.ledger.state['opening_consumed'] or not self.ledger.state['intent']):raise PermissionError('ONE_DIAGNOSTIC_GLOBAL_ONLY')
            if g.get('supervised_protection_bootstrap') is not True or g.get('tail_risk_acknowledged') is not True:raise PermissionError('SUPERVISED_PROTECTION_CONSENT_REQUIRED')
        elif self.ledger and self.ledger.state['suspended'] and not self.recovery and not self.cancel_only:raise PermissionError('SUSPENDED_DIAGNOSTIC_REQUIRES_OWNED_RECOVERY')
        return g
    def admission(self,s,p):
        if self.recovery or self.cancel_only:raise PermissionError('REDUCING_RECOVERY_CANNOT_OPEN')
        other_reservations(self.root)
        g=self.grant();c=configuration(self.root)
        if active_scope()==R10_SCOPE:
            if not self.ledger.journal.mirror:raise PermissionError('R10_POSTGRES_JOURNAL_REQUIRED')
            self.ledger.journal.mirror.sync(required=True)
        e=receipts(self.root,g['evidence_path'],g['binding_id'],self.clock)
        if g['evidence_sha256']!=stock.sha(g['evidence_path']):raise PermissionError('DIAGNOSTIC_RECEIPTS_CHANGED')
        blocks=blockers(s,c,e,bootstrap=True,clock=self.clock)
        if blocks:raise PermissionError(blocks[0])
        contract=s['contract'];stamp=self.clock()
        if (contract['con_id'],contract['symbol'],contract['security_type'],contract['currency'])!=(9599491,'F','STK','USD') or p.get('con_id')!=9599491 or p.get('trial_id')!=self.trial or p.get('intent')!='FDIAG-'+self.trial[-32:] or p.get('side')!='BUY' or p.get('classification')!='EXECUTION_DIAGNOSTICS' or p.get('strategy_version') is not None:raise PermissionError('DIAGNOSTIC_GEOMETRY_OR_CLASSIFICATION_CHANGED')
        if not 0<=(stamp-stock.at(p['at'])).total_seconds()<=15 or p['entry_session']!=s['active_session']['start'] or not stamp<stock.at(p['opening_deadline'])<=stamp+timedelta(seconds=30):raise PermissionError('DIAGNOSTIC_LATE_ENTRY_FORBIDDEN')
        expected=scenario(s['quote'],c,cap_confirmed(e))
        for k in ('quantity','entry','stop','target','fees','opening_fee','closing_fee','risk','slippage_per_unit','gap_per_unit'):
            if D(str(p[k]))!=D(str(expected[k])):raise PermissionError('DIAGNOSTIC_PLAN_NOT_REPRODUCIBLE')
        decision=risk(self.root,self.ledger.state,p,s);self.ledger.write('DIAGNOSTIC_RISK_AND_EXECUTION_FEASIBILITY',decision)
        if decision.get('allowed') is not True:raise PermissionError(decision.get('reason','DIAGNOSTIC_RISK_DENIED'))
        if (self.clock()-stock.at(s['quote']['received_at'])).total_seconds()>15 or self.clock()>=stock.at(p['opening_deadline']):raise PermissionError('DIAGNOSTIC_QUOTE_OR_ENTRY_EXPIRED_DURING_RISK_CHECK')
        if (stock.at(s['active_session']['end'])-self.clock()).total_seconds()<c['minimum_rth_remaining_seconds']:raise PermissionError('DIAGNOSTIC_TOO_NEAR_RTH_CLOSE')

def drain(wire,l):
    while True:
        try:kind,row=wire.callback_events.get_nowait()
        except queue.Empty:return
        i=l.state['intent']
        if kind in ('order','fill') and (not i or row.get('order_ref')!=i['intent']):continue
        if kind=='order':l.order(row)
        elif kind=='fill':l.fill(row)
        elif kind=='fee' and i and row['exec_id'] in i['executions']:l.fee(row)
        elif kind=='error':
            if i:i['uncertain']=True
            l.suspend('DIAGNOSTIC_IBKR_ERROR_RECONCILE_REQUIRED')
        elif kind=='status_without_contract' and i and row['order_id'] in i['order_ids']+[i.get('close_id')]:
            i['uncertain']=True;l.write('STATUS_NEEDS_CONTRACT_RECONCILIATION',row)

def manage(wire,l,s,c,clock=stock.now):
    i=l.state['intent']
    if not i:return 'FINISHED'
    q=D(i['position']);parent=i['orders'].get(str(i['order_ids'][0]));stamp=clock()
    if parent and parent['status'] not in stock.TERMINAL:
        if i['first_fill_at'] or stamp>=stock.at(i['opening_deadline']):
            if parent['status']!='PendingCancel':wire.cancel_owned(i['order_ids'][0])
        return 'PARENT_RECONCILIATION_REQUIRED'
    if not parent:return 'ACK_RECONCILIATION_REQUIRED'
    if q==0:
        for o in s['open_orders']:
            if o['status']!='PendingCancel':wire.cancel_owned(o['order_id'])
        return 'FLAT_RECONCILIATION_OR_FEES_PENDING'
    if not i['first_fill_at']:raise PermissionError('EXECUTION_TIMESTAMP_UNKNOWN')
    children=[o for o in s['open_orders'] if o['order_id'] in i['order_ids'][1:]]
    if not i.get('close_initiated_at'):
        if len(children)!=2 or any(D(o['quantity'])!=q or o.get('perm_id',0)<=0 or o['status'] not in ('Submitted','PreSubmitted') for o in children):
            l.suspend('DIAGNOSTIC_PROTECTION_NOT_CONFIRMED_RECOVERY_REQUIRED');return 'SUSPENDED'
        if (stamp-stock.at(i['first_fill_at'])).total_seconds()<c['initiate_close_seconds']:return 'OPEN_PROTECTION_RECONCILED'
        i['close_initiated_at']=stamp.isoformat();l.write('DIAGNOSTIC_CLOSE_INITIATED',dict(seconds_after_fill=(stamp-stock.at(i['first_fill_at'])).total_seconds()))
        if (stamp-stock.at(i['first_fill_at'])).total_seconds()>60:l.suspend('DIAGNOSTIC_CLOSE_DEADLINE_MISSED');return 'SUSPENDED'
    try:
        session=s.get('active_session');qv=s['quote']
        if not session or not stock.at(session['start'])<=stamp<stock.at(session['end']) or qv['market_data_type']!=1 or not 0<D(qv['bid'])<=D(qv['ask']) or any(not 0<=(stamp-stock.at(qv['field_received_at'][k])).total_seconds()<=15 for k in ('bid','ask')):raise ValueError()
    except (KeyError,ValueError,TypeError):
        l.suspend('DIAGNOSTIC_EXIT_MARKET_UNUSABLE_KEEP_PROTECTION');return 'SUSPENDED'
    if s['open_orders']:
        for o in s['open_orders']:
            if o['status']!='PendingCancel':wire.cancel_owned(o['order_id'])
        return 'CANCEL_PENDING_RECONCILE_BEFORE_CLOSE'
    if i['sell_attempted']:return 'EXIT_ALREADY_ATTEMPTED_NO_RETRY'
    wire.close_owned(s,s['quote']['bid'],'EXECUTION_DIAGNOSTIC_CONTROLLED_CLOSE')
    return 'OWNED_REDUCING_EXIT_SENT'

def other_reservations(root):
    paths=list((Path(root)/'artifacts/paper-trials/h40').glob('*/journal.sqlite3'))
    paths+=list((Path(root)/FOLDER).glob('*/journal.sqlite3'))
    paths.append(Path(root)/stock.FOLDER/'journal.sqlite3')
    for p in paths:
        if not p.exists():continue
        db=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True)
        try:
            row=db.execute('SELECT payload FROM events ORDER BY revision DESC LIMIT 1').fetchone()
            if row:
                s=json.loads(row[0])['state']
                if s['intent'] or D(s['reservation']):raise PermissionError('ANOTHER_EXPERIMENTAL_ALLOCATION_IS_RESERVED')
        finally:db.close()

def run(root,trial):
    p=folder(root,trial);c=configuration(root);protocol(root,trial)
    Guard(root,trial,None).grant();other_reservations(root);b=binding(root)
    with run_lock(Path(root)/FOLDER/'execution.lock'):
        j=Journal(p/'journal.sqlite3',b.binding_id,trial)
        if active_scope()==R10_SCOPE:
            from .ford_diagnostic_evidence import PostgresMirror
            j.mirror=PostgresMirror(root,j)
        l=Ledger(j,lambda:seal_new(Path(root)/'.local/ford-diagnostic-consumed.dpapi',dict(trial_id=trial,binding_id=b.binding_id,at=stock.now().isoformat())))
        g=Guard(root,trial,l);wire=None
        try:
            if l.state['intent'] or l.state['opening_consumed']:raise PermissionError('USE_RECONCILE_OR_OWNED_RECOVERY_NO_RERUN')
            wire=wire_for(root,b,mutable=True);b.select(wire.connect());wire.bind_execution(g,l)
            s=snapshot(wire,b,l);l.reconcile(s);e=g.grant()['paper_evidence']
            blocks=blockers(s,c,e,bootstrap=True)
            if blocks:return dict(state='BLOCKED',blockers=blocks,orders_sent=0)
            plan=scenario(s['quote'],c,cap_confirmed(e));first=max(wire.next_order_id,l.state['next_order_id']);stamp=stock.now()
            plan.update(at=stamp.isoformat(),intent='FDIAG-'+trial[-32:],signal_key=trial,trial_id=trial,
                diagnostic_scope=active_scope(),classification='EXECUTION_DIAGNOSTICS',strategy_version=None,side='BUY',
                signal=dict(diagnostic=True,no_strategy_signal=True),cash=l.state['cash'],con_id=9599491,
                order_ids=[first,first+1,first+2],entry_session=s['active_session']['start'],
                opening_deadline=(stamp+timedelta(seconds=c['entry_lifetime_seconds'])).isoformat())
            l.write('DIAGNOSTIC_PRE_ENTRY_SNAPSHOT',{k:s.get(k) for k in ('at','quote','positions','open_orders','account_queries','capabilities')})
            wire.bracket(s,plan)
            # ACK collection is bounded independently of slower account queries.
            end=time.monotonic()+5
            while time.monotonic()<end:
                drain(wire,l);i=l.state['intent']
                if not wire.connected or i['uncertain'] or l.state['suspended']:break
                if all(str(oid) in i['orders'] and i['orders'][str(oid)].get('perm_id',0)>0 and i['orders'][str(oid)]['status'] in ('Submitted','PreSubmitted','Filled') for oid in i['order_ids']):break
                time.sleep(.05)
            else:l.suspend('DIAGNOSTIC_ACK_DEADLINE_RECONCILE_REQUIRED')
            if l.state['suspended']:return dict(state='SUSPENDED',reason=l.state['suspended'])
            while True:
                g.grant(management=True);s=snapshot(wire,b,l);drain(wire,l);l.reconcile(s)
                if not l.state['intent']:return dict(state='COMPLETED_ONE_DIAGNOSTIC',strategy_success=False,repeat=False,emergency_unchanged=True,
                    postgres_pending=j.mirror.pending if j.mirror else None)
                manage(wire,l,s,c)
                if l.state['suspended']:return dict(state='SUSPENDED',reason=l.state['suspended'],recovery_required=True)
                if l.state['intent']['state']=='FLAT_COMMISSION_PENDING':return dict(state='FLAT_COMMISSION_PENDING',reservation=l.state['reservation'],repeat=False)
                time.sleep(c['poll_seconds'])
        except BaseException:
            if l.state['intent']:l.suspend('DIAGNOSTIC_RECONCILE_OR_RECOVERY_REQUIRED')
            raise
        finally:
            if wire:wire.disconnect()
            j.close()

def reconcile(root,trial,recover=False,cancel=False):
    protocol(root,trial);p=folder(root,trial);b=binding(root)
    if not (p/'journal.sqlite3').exists():raise PermissionError('NO_DIAGNOSTIC_INVENTORY_OR_JOURNAL')
    with run_lock(Path(root)/FOLDER/'execution.lock'):
        j=Journal(p/'journal.sqlite3',b.binding_id,trial);l=Ledger(j);w=None
        if active_scope()==R10_SCOPE:
            from .ford_diagnostic_evidence import PostgresMirror
            j.mirror=PostgresMirror(root,j)
        try:
            g=Guard(root,trial,l,recovery=recover,cancel_only=cancel)
            if recover or cancel:g.grant(management=True)
            w=wire_for(root,b,mutable=recover or cancel);b.select(w.connect())
            if recover or cancel:w.bind_execution(g,l)
            s=snapshot(w,b,l);drain(w,l);l.reconcile(s);i=l.state['intent']
            if not i:return dict(position='0',open_orders=[],reservation=l.state['reservation'],market_orders_sent=0)
            buys=[f for f in i['executions'].values() if f['side']=='BUY']
            if recover:
                g.grant(True)
                if D(i['position'])==0:return dict(state='FLAT_NO_SELL',reservation=l.state['reservation'])
                if i['sell_attempted']:raise PermissionError('PREVIOUS_EXIT_RECONCILE_NO_BLIND_RETRY')
                if s['open_orders']:
                    for o in s['open_orders']:
                        if o['status']!='PendingCancel':w.cancel_owned(o['order_id'])
                    return dict(state='CANCEL_PENDING_RECONCILE_BEFORE_CLOSE')
                w.close_owned(s,s['quote']['bid'],'INDEPENDENT_OWNED_DIAGNOSTIC_RECOVERY');return dict(state='RECOVERY_SELL_SENT_RECONCILE_REQUIRED')
            if cancel:
                if D(i['position'])!=0:raise PermissionError('KEEP_PROTECTION_USE_OWNED_RECOVERY')
                parent=next((o for o in s['open_orders'] if o['order_id']==i['order_ids'][0]),None)
                if parent:ids=[] if parent['status']=='PendingCancel' else [parent['order_id']]
                elif i['orders'].get(str(i['order_ids'][0]),{}).get('status') in stock.TERMINAL:ids=[o['order_id'] for o in s['open_orders'] if o['status']!='PendingCancel']
                else:raise PermissionError('PARENT_TERMINAL_RECONCILIATION_REQUIRED')
                for oid in ids:w.cancel_owned(oid)
                return dict(state='CANCEL_REQUESTED_RECONCILE_REQUIRED',cancellations=len(ids))
            return dict(trial_id=trial,binding_id=b.binding_id,scope=recovery_scope(),intent=i['intent'],con_id=i['con_id'],quantity=i['position'],
                buy_exec_ids=sorted(f['exec_id'] for f in buys),buy_perm_ids=sorted({f['perm_id'] for f in buys}),
                close_previously_attempted=i['sell_attempted'],open_orders=s['open_orders'],quote=s['quote'],reservation=l.state['reservation'],
                journal_hash=j.db.execute('SELECT hash FROM events ORDER BY revision DESC LIMIT 1').fetchone()[0],market_orders_sent=0)
        except BaseException:
            if l.state['intent']:l.suspend('DIAGNOSTIC_RECONCILIATION_REQUIRED')
            raise
        finally:
            if w:w.disconnect()
            j.close()

def status(root,trial):
    protocol(root,trial);p=folder(root,trial)
    s=dict(trial_id=trial,scope=active_scope(),classification='EXECUTION_DIAGNOSTICS',authorized=(p/'authorization.dpapi').exists(),
        emergency=any((Path(root)/'.local'/n).exists() for n in STOP_NAMES),global_consumed=(Path(root)/'.local/ford-diagnostic-consumed.dpapi').exists(),
        strategy_success=False,live_enabled=False,execution_ready=False)
    if (p/'journal.sqlite3').exists():
        j=Journal(p/'journal.sqlite3',binding(root).binding_id,trial)
        try:s['revision'],s['ledger']=j.load()
        finally:j.close()
    if active_scope()==R10_SCOPE:
        s['postgres_replication']='REQUIRES_RECONCILE_NO_DATABASE_ASSUMPTION'
        s['paper_auto_authorized']=False
    return s

def main():
    a=argparse.ArgumentParser();a.add_argument('action',choices=('Prepare','Inspect','WhatIf','Assess','Status','Run','Reconcile','RecoveryInspect','RecoveryRun','CancelPending','Stop','Revoke'))
    a.add_argument('--profile',choices=(SCOPE,R10_SCOPE),default=SCOPE);a.add_argument('--root',default=str(Path(__file__).resolve().parents[2]));a.add_argument('--trial');a.add_argument('--evidence');v=a.parse_args();root=Path(v.root);PROFILE.set(v.profile);configuration(root)
    try:
        if v.action=='Prepare':out=prepare(root)
        elif v.action in ('Inspect','WhatIf','Assess'):
            out=readonly(root,v.trial,v.action=='WhatIf',v.evidence)
            if v.action=='Assess' and 'error' not in out:
                # The protected script separately checks current emergency.
                out['blockers']=[b for b in out['blockers'] if b!='INDEPENDENT_DIAGNOSTIC_AUTHORIZATION_NOT_GRANTED']
        elif v.action=='Status':out=status(root,v.trial)
        elif v.action=='Run':out=run(root,v.trial)
        elif v.action in ('Reconcile','RecoveryInspect','RecoveryRun','CancelPending'):out=reconcile(root,v.trial,v.action=='RecoveryRun',v.action=='CancelPending')
        elif v.action=='Stop':
            protocol(root,v.trial);save_new(root/'.local/ford-diagnostic.stop',dict(at=stock.now().isoformat(),trial_id=v.trial));out=dict(new_entries_stopped=True,emergency_unchanged=True)
        else:
            protocol(root,v.trial);p=folder(root,v.trial)/'revoked.json';save_new(p,dict(at=stock.now().isoformat(),revoked=True));out=dict(revoked=True,emergency_unchanged=True)
    except Exception as exc:
        reason=str(exc);out=dict(state='BLOCKED',reason=reason if re.fullmatch('[A-Z][A-Z0-9_]{1,100}',reason) else 'DIAGNOSTIC_COMMAND_FAILED',reason_type=type(exc).__name__,live_enabled=False);raise SystemExit(print(json.dumps(out)) or 1)
    print(json.dumps(out,default=str))

if __name__=='__main__':main()
