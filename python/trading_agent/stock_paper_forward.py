"""H40 stock Paper boundary. Studies never authorize execution or change H40.

The production RiskEngine remains mandatory, including its 0.5% ceiling.
All unknown broker capabilities veto entry. This is not a strategy promotion.
"""
import argparse
import copy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import threading
import time
from types import FunctionType,SimpleNamespace
from zoneinfo import ZoneInfo

from .paper_lab import unseal, same_process
from .ibkr_session import AccountBinding, SessionConfiguration
from .ai_strategy_researcher.contracts import number, at, digest, candidate_version, FOLDS, MODELS
from .ai_strategy_researcher.simulation import signals, exit_event, validated, tick, simulate
from .ai_strategy_researcher.costs import commission, cost_assumptions

D=Decimal
VERSION='2459b8fbe73d4dec3bff7a1baaf3e382b9473fa5908d25e6d6b58ffd151072d8'
EXPERIMENT='6093d4afc8961b5278cecea356a2b31c705fe6e51cf1ca343a01d030984c48b8'
CANDIDATE=dict(name='F_Daily_MEAN_REVERSION_Hold40_R4',symbol='F',timeframe_minutes=1440,
    pattern='MEAN_REVERSION',fast=10,slow=30,lookback=20,atr_period=14,stop_atr=2,target_r=1,
    max_hold_bars=40,risk_percent=2)
FOLDER='artifacts/paper-forward/h40'
CAPABILITIES=('stock_permission','account_restrictions','settled_cash','available_funds',
    'whole_share_minimum','quantity_increment','contract_margin','effective_fees',
    'protection_acceptance','partial_fill_protection','corporate_actions')
TERMINAL=('Filled','Cancelled','ApiCancelled','Inactive')

def now():return datetime.now(timezone.utc)
def encoded(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False,
    default=lambda v:str(v) if isinstance(v,D) else (_ for _ in ()).throw(TypeError())).encode()
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def source_hashes(root):
    paths=('config/stock-paper-forward.json','src/TradingAgent.Core/Risk.cs','src/TradingAgent.Core/ExecutionFeasibility.cs',
        'src/TradingAgent.Core/StockPaperForwardRisk.cs','python/trading_agent/stock_paper_forward.py',
        'python/trading_agent/stock_paper_forward_wire.py','python/trading_agent/stock_paper_forward_runner.py',
        'python/trading_agent/ai_strategy_researcher/simulation.py',
        'scripts/stock-paper-forward.ps1','src/TradingAgent.Api/StockPaperForwardCommand.cs',
        'src/TradingAgent.Api/bin/Debug/net9.0/TradingAgent.Api.dll',
        'src/TradingAgent.Core/bin/Debug/net9.0/TradingAgent.Core.dll',
        'artifacts/research/ai-strategy-research/candidates/'+EXPERIMENT+'.json')
    return {p:sha(Path(root)/p) for p in paths}
def check_live():
    if os.environ.get('LIVE_TRADING','false').lower()!='false':raise PermissionError('LIVE_DISABLED')

def configuration(root):
    c=json.loads((Path(root)/'config/stock-paper-forward.json').read_text(encoding='utf-8-sig'))
    if c['environment']!='PAPER_TRADING' or c['symbol']!='F' or c['capital_usd']!=100 or c['maximum_exposure']!=1 or c['loss_allowance_usd']!=20 or c['strategy_version']!=VERSION:
        raise PermissionError('STOCK_FORWARD_SCOPE_REQUIRED')
    if not 1<=c['request_timeout_seconds']<=30 or not 1<=c['poll_seconds']<=60 or not 1<=c['entry_window_seconds']<=60 or not 1<=c['maximum_quote_age_seconds']<=15 or not 1<=c['authorization_hours']<=8 or c['client_id']!=93 or c['research_risk_percent']!=[3,5,10,15]:
        raise PermissionError('STOCK_FORWARD_LIMITS_INVALID')
    candidate=json.loads((Path(root)/c['candidate_artifact']).read_text(encoding='utf-8'))['proposal']['candidate']
    if candidate!=CANDIDATE or candidate_version(candidate)!=VERSION:raise PermissionError('H40_ORIGINAL_PARAMETERS_REQUIRED')
    return c

def initial(binding):
    return dict(environment='PAPER_TRADING',strategy_version=VERSION,binding_id=binding,
        cash='100',equity='100',realized_equity='100',consumed_loss='0',reservation='0',intent=None,
        completed=[],stopped_days={},next_order_id=0,suspended=None)

class Journal:
    """Append-only, hash-chained events + revision CAS in a FULL-sync transaction."""
    def __init__(self,path,binding):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(self.path,timeout=10,check_same_thread=False)
        self.db.execute('PRAGMA journal_mode=WAL');self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('CREATE TABLE IF NOT EXISTS events (revision INTEGER PRIMARY KEY, at TEXT NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL, previous TEXT NOT NULL, hash TEXT NOT NULL)')
        self.db.commit();self.lock=threading.RLock();self.binding=binding
        if not self.db.execute('SELECT 1 FROM events LIMIT 1').fetchone():self.commit(0,initial(binding),'INITIAL_ALLOCATION')
        try:self.load()
        except BaseException:self.db.close();raise
    def load(self):
        with self.lock:
            previous='';revision=0;state=None
            for r,stamp,kind,payload,prior,h in self.db.execute('SELECT * FROM events ORDER BY revision'):
                if r!=revision+1 or prior!=previous or digest([r,stamp,kind,json.loads(payload),prior])!=h:
                    raise PermissionError('STOCK_JOURNAL_INTEGRITY_FAILURE')
                state=json.loads(payload)['state'];previous=h;revision=r
            if state['binding_id']!=self.binding or state['environment']!='PAPER_TRADING' or state['strategy_version']!=VERSION:
                raise PermissionError('STOCK_JOURNAL_SCOPE_MISMATCH')
            return revision,state
    def commit(self,revision,state,kind,details=None):
        with self.lock:
            try:
                self.db.execute('BEGIN IMMEDIATE')
                last=self.db.execute('SELECT revision,hash FROM events ORDER BY revision DESC LIMIT 1').fetchone()
                if (last[0] if last else 0)!=revision:raise PermissionError('STOCK_JOURNAL_CHANGED_RECONCILE_REQUIRED')
                stamp=now().isoformat();payload=dict(state=state,details=details or {});prior=last[1] if last else ''
                h=digest([revision+1,stamp,kind,payload,prior])
                self.db.execute('INSERT INTO events VALUES (?,?,?,?,?,?)',(revision+1,stamp,kind,encoded(payload).decode(),prior,h));self.db.commit()
                return revision+1
            except BaseException:self.db.rollback();raise
    def close(self):self.db.close()

class Ledger:
    def __init__(self,journal):self.journal=journal;self.revision,self.state=journal.load()
    def write(self,kind,details=None):self.revision=self.journal.commit(self.revision,self.state,kind,details)
    def suspend(self,reason):self.state['suspended']=reason;self.write('SUSPENDED',dict(reason=reason))
    def entry_block(self,stamp):
        if self.state['suspended']:return self.state['suspended']
        if number(self.state['consumed_loss'])>=20:return 'CUMULATIVE_LOSS_STOP'
        if self.state['intent'] or number(self.state['reservation'])!=0:return 'PREVIOUS_RESULT_NOT_DEFINITIVE'
        return self.state['stopped_days'].get(at(stamp).astimezone(ZoneInfo('America/Santo_Domingo')).date().isoformat())
    def reserve(self,plan):
        if self.entry_block(plan['at']):raise PermissionError(self.entry_block(plan['at']))
        if plan['signal_key'] in self.state['completed']:raise PermissionError('DUPLICATE_SIGNAL')
        q=number(plan['quantity']);spent=q*number(plan['entry'])+number(plan['fees'])
        if q<1 or q%1 or spent>min(D(100),number(self.state['cash']),number(self.state['equity'])) or plan['side']!='BUY':
            raise PermissionError('STOCK_ALLOCATION_OR_LONG_ONLY_VIOLATION')
        if not 0<number(plan['risk'])<=min(number(self.state['equity'])*D('.005'),D(20)-number(self.state['consumed_loss'])):
            raise PermissionError('PROTECTED_RISK_LIMIT')
        if len(set(plan['order_ids']))!=3 or min(plan['order_ids'])<self.state['next_order_id']:
            raise PermissionError('ORDER_ID_COLLISION')
        self.state['next_order_id']=max(plan['order_ids'])+1
        self.state['reservation']=str(spent)
        self.state['intent']={**copy.deepcopy(plan),'state':'PREPARED','orders':{},'executions':{},'fees_observed':{},'attempted':[],
            'sell_attempted':False,'first_fill_at':None,'uncertain':False,'last_reconciled_at':None,'position':'0'}
        self.write('RESERVED',dict(signal=plan['signal_key'],strategy_version=VERSION))
    def pre_send(self,order_id):
        i=self.state['intent']
        if not i or order_id in i['attempted'] or i['uncertain']:raise PermissionError('NO_BLIND_RETRY')
        i['attempted'].append(order_id);i['state']='SEND_PENDING';self.write('SEND_PENDING',dict(order_id=order_id))
    def order(self,row):
        i=self.state['intent']
        if not i or row['order_id'] not in i['order_ids']+([i['close_id']] if i.get('close_id') else []) or row.get('order_ref')!=i['intent']:
            raise PermissionError('UNRECOGNIZED_ORDER')
        index=i['order_ids'].index(row['order_id']) if row['order_id'] in i['order_ids'] else 3
        if row.get('con_id')!=i['con_id'] or (row.get('symbol'),row.get('security_type'),row.get('currency'))!=('F','STK','USD') or row.get('side')!=('BUY' if index==0 else 'SELL') or row.get('parent_id')!=(i['order_ids'][0] if index in (1,2) else 0) or not 0<number(row['quantity'])<=number(i['quantity']):
            raise PermissionError('BROKER_ORDER_GEOMETRY_CHANGED')
        if index in (1,2) and (row.get('oca_group')!=i['intent'] or row.get('oca_type')!=2):raise PermissionError('BROKER_OCA_LINK_CHANGED')
        old=i['orders'].get(str(row['order_id']))
        if old and old.get('perm_id') and row.get('perm_id') and old['perm_id']!=row['perm_id']:
            raise PermissionError('PERM_ID_CHANGED')
        i['orders'][str(row['order_id'])]=row;i['state']='ACKNOWLEDGED';self.write('ORDER_ACK',row)
    def fill(self,row):
        i=self.state['intent'];order_ids=i['order_ids']+([i['close_id']] if i.get('close_id') else []) if i else []
        if not i or row['order_id'] not in order_ids or row['order_ref']!=i['intent'] or row['con_id']!=i['con_id'] or row['side']!=('BUY' if row['order_id']==i['order_ids'][0] else 'SELL'):
            raise PermissionError('UNRECOGNIZED_EXECUTION')
        q,p=number(row['quantity']),number(row['price'])
        if q<=0 or q%1 or p<=0 or row.get('perm_id',0)<=0:raise PermissionError('INVALID_STOCK_FILL')
        old=i['executions'].get(row['exec_id'])
        ack=i['orders'].get(str(row['order_id']))
        if ack and ack.get('perm_id') and ack['perm_id']!=row['perm_id']:raise PermissionError('EXECUTION_PERM_ID_MISMATCH')
        if old:
            if old!=row:raise PermissionError('EXEC_ID_CHANGED')
            return
        buys=sum(number(f['quantity']) for f in i['executions'].values() if f['side']=='BUY')
        sells=sum(number(f['quantity']) for f in i['executions'].values() if f['side']=='SELL')
        if row['side']=='BUY' and buys+q>number(i['quantity']) or row['side']=='SELL' and sells+q>buys:
            raise PermissionError('OVERFILL_OR_SHORT_POSITION')
        i['executions'][row['exec_id']]=row;i['first_fill_at']=i['first_fill_at'] or row['at'];i['state']='FILL_RECONCILIATION_REQUIRED'
        i['last_reconciled_at']=None;self.write('FILL',row)
    def fee(self,row):
        i=self.state['intent']
        if not i:raise PermissionError('COMMISSION_WITHOUT_INTENT')
        if row['currency']!='USD' or number(row['commission'])<0:raise PermissionError('COMMISSION_NOT_DEFINITIVE')
        previous=i['fees_observed'].get(row['exec_id'])
        if previous and previous!=row:raise PermissionError('COMMISSION_CHANGED_RECONCILE_REQUIRED')
        if previous:return
        i['fees_observed'][row['exec_id']]=row;self.write('COMMISSION',row)
    def reconcile(self,snapshot):
        if snapshot.get('identity_verified') is not True or snapshot.get('complete') is not True:
            raise PermissionError('STRICT_BROKER_RECONCILIATION_REQUIRED')
        i=self.state['intent'];positions=[p for p in snapshot['positions'] if number(p['quantity'])!=0]
        if not i:
            if positions or snapshot['open_orders']:raise PermissionError('UNKNOWN_POSITION_OR_ORDER')
            return
        for row in snapshot['executions']:self.fill(row)
        for row in snapshot.get('commissions',[]):self.fee(row)
        for row in snapshot['completed_orders']+snapshot['open_orders']:self.order(row)
        for p in positions:
            if p['con_id']!=i['con_id'] or p['symbol']!='F' or p['security_type']!='STK' or p['currency']!='USD':raise PermissionError('FOREIGN_POSITION')
        if len(positions)>1:raise PermissionError('AMBIGUOUS_POSITION')
        q=number(positions[0]['quantity']) if positions else D(0)
        own=list(i['executions'].values());b=sum(number(f['quantity']) for f in own if f['side']=='BUY');s=sum(number(f['quantity']) for f in own if f['side']=='SELL')
        if q!=b-s or not 0<=q<=number(i['quantity']):raise PermissionError('POSITION_EXECUTION_MISMATCH')
        if any(o['order_id'] not in i['order_ids']+([i['close_id']] if i.get('close_id') else []) for o in snapshot['open_orders']):raise PermissionError('UNKNOWN_OPEN_ORDER')
        i['position']=str(q);i['last_reconciled_at']=snapshot['at'];i['uncertain']=False
        parent=i['orders'].get(str(i['order_ids'][0]))
        # A partially filled parent must be cancelled and confirmed before an
        # independent close. Partial protection acceptance is required at entry.
        if q and parent and parent['status'] not in TERMINAL:
            i['state']='PARTIAL_PARENT_MANAGEMENT_REQUIRED'
        elif q:i['state']='OPEN_PROTECTED'
        elif not parent or parent['status'] not in TERMINAL:i['state']='PENDING'
        elif snapshot['open_orders']:i['state']='FLAT_ORDERS_PENDING'
        elif b==0:
            self.state['completed'].append(i['signal_key']);self.state['reservation']='0';self.state['intent']=None
            self.write('RELEASE_UNFILLED_NO_TRADE');return
        else:
            missing=set(i['executions'])-set(i['fees_observed'])
            if missing:i['state']='FLAT_COMMISSION_PENDING'
            else:
                gross=sum(number(f['quantity'])*number(f['price'])*(1 if f['side']=='SELL' else -1) for f in own)
                fees=sum(number(i['fees_observed'][f['exec_id']]['commission']) for f in own);net=gross-fees
                equity=number(self.state['realized_equity'])+net
                self.state['equity']=str(equity);self.state['realized_equity']=str(equity);self.state['cash']=str(min(D(100),max(D(0),equity)))
                self.state['consumed_loss']=str(number(self.state['consumed_loss'])+max(D(0),-net))
                # No reuse of proceeds until the next authentic session's broker
                # settled-cash check. USD Paper buying power is never sizing capital.
                stamp=max(at(f['at']) for f in own if f['side']=='SELL');day=stamp.astimezone(ZoneInfo('America/Santo_Domingo')).date().isoformat()
                if net<=0:self.state['stopped_days'][day]='DAILY_FIRST_LOSS_STOP' if net<0 else 'DAILY_BREAK_EVEN_STOP'
                self.state['settlement_after']=snapshot.get('next_session_start')
                report=dict(intent=i['intent'],strategy_version=VERSION,signal=i['signal'],quantity=i['quantity'],entry=i['entry'],stop=i['stop'],target=i['target'],
                    executions=own,fees=i['fees_observed'],gross_pnl=str(gross),net_pnl=str(net),equity=str(equity),remaining_loss=str(max(D(0),20-number(self.state['consumed_loss']))),
                    decision=self.state['stopped_days'].get(day,'WIN_CAN_SEEK_SIGNAL_AFTER_SETTLEMENT'),reason=i.get('close_reason','BROKER_PROTECTION'),estimated_friction=i['friction'],risk_breach=-net>number(i['risk']))
                if -net>number(i['risk']):self.state['suspended']='OBSERVED_LOSS_EXCEEDS_RESERVED_RISK'
                self.state['completed'].append(i['signal_key']);self.state['intent']=None;self.state['reservation']='0';self.write('TRADE_SETTLED',report);return
        if q and snapshot.get('quote',{}).get('bid'):
            mark=number(snapshot['quote']['bid']);bought=sum(number(f['quantity'])*number(f['price']) for f in own if f['side']=='BUY')
            sold=sum(number(f['quantity'])*number(f['price']) for f in own if f['side']=='SELL')
            observed_fees=sum(number(f['commission']) for f in i['fees_observed'].values())
            unrealized=q*mark+sold-bought-observed_fees
            i['inventory_mark']=dict(bid=str(mark),remaining_quantity=str(q),market_value=str(q*mark),
                net_contribution=str(unrealized),fees_complete=set(i['executions'])<=set(i['fees_observed']),
                quote_type=snapshot['quote'].get('market_data_type'),at=snapshot['quote'].get('received_at'),status='MARK_NOT_A_REALIZED_RESULT')
            self.state['equity']=str(number(self.state['realized_equity'])+unrealized)
        self.write('RECONCILED',dict(quantity=str(q),state=i['state']))

def estimate(entry,stop,target,risk_percent,cash=100,equity=100,spread=None,model='TIERED_BASE',losses=0):
    """Isolated cash-only study. No registration, grant or RiskEngine policy edit."""
    p,stop,target=map(number,(entry,stop,target));rate=number(risk_percent)
    if rate not in (D(2),D(3),D(5),D(10),D(15)) or not 0<stop<p<target:raise ValueError('STUDY_GEOMETRY_OR_PROFILE_INVALID')
    cash=min(D(100),number(cash),number(equity));spread=max(number(spread or 0),p*D('.0005'))
    slip=p*D('.0005');gap=p*D('.005');paid=tick(p+spread/2+slip,True)
    budget=min(number(equity)*rate/100,D(15),D(20)-number(losses))
    for q in range(max(0,int(cash/paid)),0,-1):
        opening=commission(q,paid,model,'BUY');closing=commission(q,max(paid,target),model,'SELL');fees=opening+closing
        risk=q*(paid-stop+spread+2*slip+gap+D('.02'))+fees
        if q*paid+fees<=cash and risk<=budget:
            return dict(profile_percent=float(rate),quantity=q,entry=str(paid),notional=str(q*paid),reserved_cash=str(q*paid+fees),
                risk_budget=str(budget),estimated_loss=str(risk),opening_fee=str(opening),closing_fee=str(closing),fees=str(fees),
                remaining_cash=str(cash-q*paid-fees),spread=str(q*spread),slippage=str(2*q*slip),gap=str(q*gap),
                target_net=str(q*(target-paid-spread-2*slip-gap-D('.02'))-fees),status='ESTIMATED_SIMULATION_ONLY',
                tail_loss_not_bounded=True,execution_authorized=False)
    return dict(profile_percent=float(rate),quantity=0,risk_budget=str(budget),reason='COSTS_RISK_OR_CASH',status='ESTIMATED_SIMULATION_ONLY',execution_authorized=False)

def h40_next_signal(completed,opening,session,c):
    """Original simulator signal, evaluated only at its actual next RTH open."""
    rows=validated(completed+[opening]);events,_=signals(rows,CANDIDATE)
    event=next((s for s in events if s['index']==len(rows)-1),None)
    if not event:return None
    if at(opening['opened_at'])!=at(session['start']) or at(completed[-1]['closed_at'])>=at(session['start']):raise PermissionError('NEXT_OPEN_CAUSALITY_REQUIRED')
    return event

def h40_exit(rows,signal):
    rows=validated(rows);_,fs=signals(rows,CANDIDATE)
    return exit_event(rows,fs,signal,CANDIDATE)

def risk_request(plan,snapshot):
    at_time=snapshot['quote']['received_at']
    f=dict(source='IBKR_PAPER_STOCK_FORWARD',environment='PAPER_TRADING',mode='ODD_LOT',at=at_time,
        openingCommission=plan['opening_fee'],closingCommission=plan['closing_fee'],costsReliable=True,
        marginReliable=True,contractReliable=True,brokerPermitsEntry=True,quoteStatus='LIVE',takeProfit=plan['target'])
    return dict(instrument='F',side='BUY',bid=snapshot['quote']['bid'],ask=plan['entry'],stop=plan['stop'],
        quoteToAccountFx=1,multiplier=1,minQuantity=1,quantityStep=1,marginRate=1,
        availableMargin=plan['cash'],commissionFixedRoundTrip=plan['fees'],commissionPerUnitRoundTrip=0,
        slippagePerUnit=plan['slippage_per_unit'],adverseGapPerUnit=plan['gap_per_unit'],marketAt=at_time,
        proposedRisk=D(CANDIDATE['risk_percent'])/100,execution=f,maximumQuantity=plan['quantity'])

def core_risk(root,state,request):
    at_time=now().isoformat();eq=number(state['equity']);loss=number(state['consumed_loss'])
    capital=dict(initialCapital=100,lossAllowance=20,realizedGrossPnl=str(eq-100),cumulativeRealizedLoss=str(loss),environment='PAPER_TRADING')
    # Conservative NAV references retained from initial allocation; daily/weekly
    # production halts are never relaxed by this separate daily-entry policy.
    account=dict(accountId='PAPER-H40',equity=str(eq),units=1,dayNav=100,weekNav=100,highNav=max(100,float(eq)),at=at_time,
        halts=[],openPositions=[],pendingOrders=[],capital=capital)
    payload=dict(account=account,request=request,strategy_version=VERSION,cash=state['cash'],reservations=state['reservation'])
    result=subprocess.run(['dotnet',str(Path(root)/'src/TradingAgent.Api/bin/Debug/net9.0/TradingAgent.Api.dll'),'--stock-paper-forward-risk'],
        input=encoded(payload).decode(),capture_output=True,text=True,timeout=20,cwd=root)
    if result.returncode:raise PermissionError('STOCK_FORWARD_RISK_ENGINE_UNAVAILABLE')
    value=json.loads(result.stdout)
    if value.get('allowed') is not True:return value
    if not value.get('feasibility',{}).get('allowed') or number(value['quantity'])!=number(request['maximumQuantity']):
        return dict(allowed=False,reason='RISK_ENGINE_QUANTITY_MISMATCH')
    return value

class PaperExecutionGuard:
    def __init__(self,root,c,ledger,grant_loader=None,clock=now):
        self.root=Path(root);self.c=c;self.ledger=ledger;self.clock=clock
        self.grant_loader=grant_loader or (lambda:unseal(self.root/'.local/stock-paper-forward.dpapi'))
    def grant(self,management=False):
        check_live();g=self.grant_loader();binding=AccountBinding(unseal(self.root/'.local/ibkr-account-binding.dpapi'))
        if g.get('scope')!='H40_STOCK_PAPER_FORWARD_ONLY' or g.get('environment')!='PAPER_TRADING' or g.get('live_enabled') is not False or g.get('strategy_version')!=VERSION or g.get('account')!=binding.account or g.get('binding_id')!=binding.binding_id or g.get('config_sha256')!=sha(self.root/'config/stock-paper-forward.json') or g.get('source_hashes')!=source_hashes(self.root) or g.get('capital_usd')!=100 or g.get('maximum_exposure')!=1 or g.get('risk_percent')!=2 or g.get('manage_owned_after_stop') is not True:
            raise PermissionError('STOCK_FORWARD_AUTHORIZATION_SCOPE_INVALID')
        SessionConfiguration.load(self.root).matches(g)
        if g.get('read_only_disabled_checked') is not True or not same_process(g['tws_pid'],g['tws_start_filetime']):raise PermissionError('TWS_PROTECTED_SESSION_CHANGED')
        if not management:
            if g.get('revoked') is not False or not at(g['issued_at'])<=self.clock()<at(g['expires_at']) or (at(g['expires_at'])-at(g['issued_at'])).total_seconds()>8*3600:
                raise PermissionError('STOCK_FORWARD_AUTHORIZATION_EXPIRED_OR_REVOKED')
            for name in ('paper-lab.emergency','paper-auto.stop','stock-paper-forward.stop'):
                if (self.root/'.local'/name).exists():raise PermissionError('EMERGENCY_OR_ENTRY_STOP_ACTIVE')
        return g
    def admission(self,snapshot,plan):
        self.grant();stamp=self.clock();block=self.ledger.entry_block(stamp.isoformat())
        if block:raise PermissionError(block)
        readiness(snapshot,self.c,stamp,strict=True)
        if snapshot['positions'] and any(number(p['quantity']) for p in snapshot['positions']) or snapshot['open_orders']:
            raise PermissionError('ACCOUNT_NOT_FLAT')
        session=snapshot['active_session']
        if not at(session['start'])<=stamp<=at(session['start'])+timedelta(seconds=self.c['entry_window_seconds']):raise PermissionError('H40_NEXT_OPEN_ENTRY_EXPIRED')
        if at(plan['signal']['signal_at'])>=at(session['start']) or plan['strategy_version']!=VERSION or plan['side']!='BUY':raise PermissionError('H40_SIGNAL_INVALID')
        expected=h40_next_signal(plan['completed_bars'],plan['opening_bar'],session,self.c)
        if expected is None or expected!=plan['signal']:raise PermissionError('H40_SIGNAL_NOT_REPRODUCIBLE')
        settlement=self.ledger.state.get('settlement_after')
        if self.ledger.state['completed'] and (not settlement or stamp<at(settlement)):raise PermissionError('SETTLEMENT_NOT_VERIFIED')
        # The independent guard invokes the engine itself. A caller-supplied
        # ALLOW or the isolated 3/5/10/15% study is never an admission decision.
        decision=core_risk(self.root,self.ledger.state,risk_request(plan,snapshot))
        if decision.get('allowed') is not True:raise PermissionError(decision.get('reason','RISK_ENGINE_DENIED'))

def readiness(snapshot,c,stamp=None,strict=False):
    stamp=stamp or now();blocks=[]
    if snapshot.get('identity_verified') is not True:blocks.append('EXACT_PAPER_IDENTITY_NOT_VERIFIED')
    if snapshot.get('connected') is not True or snapshot.get('complete') is not True:blocks.append('BROKER_RECONCILIATION_INCOMPLETE')
    if not snapshot.get('active_session'):blocks.append('AUTHENTIC_IBKR_RTH_NOT_OPEN')
    quote=snapshot.get('quote',{})
    try:
        age=(stamp-at(quote['received_at'])).total_seconds()
        field_ages=[(stamp-at(quote['field_received_at'][k])).total_seconds() for k in ('bid','ask')]
        if quote['market_data_type']!=1 or not 0<=age<=c['maximum_quote_age_seconds'] or any(not 0<=a<=c['maximum_quote_age_seconds'] for a in field_ages) or not 0<number(quote['bid'])<=number(quote['ask']):raise ValueError()
    except (KeyError,ValueError,TypeError):blocks.append('LIVE_BID_ASK_UNAVAILABLE_OR_STALE')
    for name in CAPABILITIES:
        f=snapshot.get('capabilities',{}).get(name,{})
        if f.get('status')!='VERIFIED' or f.get('compatible') is not True:blocks.append(name.upper()+'_UNKNOWN_OR_RESTRICTED')
    if CANDIDATE['risk_percent']>D('.5'):blocks.append('H40_RISK_2_PERCENT_EXCEEDS_PRODUCTIVE_0_5_PERCENT')
    if snapshot.get('positions') and any(number(p['quantity'])!=0 for p in snapshot['positions']) or snapshot.get('open_orders'):blocks.append('EXISTING_POSITION_OR_ORDER_REQUIRES_REVIEW')
    if strict and blocks:raise PermissionError(blocks[0])
    return blocks

def inspect(root,c,wire_factory=None):
    """No grant, permission changes or orders. Evidence files are uniquely named."""
    check_live();root=Path(root);wire=None
    value=dict(at=now().isoformat(),environment='PAPER_TRADING',identity_verified=False,connected=False,complete=False,
        positions=[],open_orders=[],completed_orders=[],executions=[],commissions=[],quote={},capabilities={},orders_sent=0,live_enabled=False)
    try:
        binding=AccountBinding(unseal(root/'.local/ibkr-account-binding.dpapi'))
        from .stock_paper_forward_wire import stock_forward_wire
        from .broker import PaperOptions
        endpoint=SessionConfiguration.load(root)
        wire=(wire_factory or stock_forward_wire)(PaperOptions(binding.account,host=endpoint.host,port=endpoint.port,
            verified_tws_port=endpoint.port,paper_mode_attested=True,configured_endpoint=True,read_only=True,
            client_id=c['client_id'],timeout=c['request_timeout_seconds']))
        binding.select(wire.connect());value.update(wire.snapshot())
        value['binding_id']=binding.binding_id
        try:
            raw=wire.history();source=encoded(raw);session_by_day={s['day']:s for s in value['sessions']}
            closed=[b for b in raw if b['broker_date'] in session_by_day and at(session_by_day[b['broker_date']]['end'])<=now()]
            days=[s['day'] for s in value['sessions'] if at(s['end'])<=now()]
            if len(closed)<15 or [b['broker_date'] for b in closed[-15:]]!=days[-15:]:raise ValueError('LATEST_15_AUTHENTIC_SESSIONS_INCOMPLETE')
            recent=closed[-15:];ranges=[]
            for before,b in zip(recent,recent[1:]):
                high,low,prior=number(b['high']),number(b['low']),number(before['close'])
                ranges.append(max(high-low,abs(high-prior),abs(low-prior)))
            atr=sum(ranges)/14;p=number(recent[-1]['close']);stop=tick(p-2*atr);target=tick(p+2*atr)
            value['risk_input']=dict(status='ESTIMATED_REFERENCE_NOT_A_SIGNAL',source='IBKR_PAPER_HISTORICAL_TRADES',
                source_sha256=hashlib.sha256(source).hexdigest(),last_completed_session=recent[-1]['broker_date'],
                atr14=str(atr),reference_close=str(p),stop=str(stop),target=str(target),bars=recent,
                corporate_actions='UNKNOWN',signal_confirmed=False)
            # Refresh BID/ASK after the historical request. Delayed data remain
            # delayed: these reference quantities cannot authorize execution.
            value['quote']=wire.sample()
            value['profile_reference_sizes']=[estimate(value['quote']['ask'],stop,target,r,
                spread=number(value['quote']['ask'])-number(value['quote']['bid'])) for r in c['research_risk_percent']]
        except Exception as exc:value['risk_input']=dict(status='UNKNOWN',reason_type=type(exc).__name__)
    except Exception as exc:
        value['error_type']=type(exc).__name__
        code=str(exc);value['error']=code if re.fullmatch('[A-Z][A-Z0-9_]{1,90}',code) else 'READ_ONLY_INSPECTION_FAILED'
    finally:
        if wire:value['ibkr_events']=wire.events[:];wire.disconnect()
    value['blockers']=readiness(value,c)
    value['max_whole_shares_nominal_only']=int(D(100)/number(value['quote']['ask'])) if value['quote'].get('ask') else None
    value['executable_shares']=0 if value['blockers'] else None
    folder=root/FOLDER/'inspections';folder.mkdir(parents=True,exist_ok=True)
    name=now().strftime('%Y%m%dT%H%M%S%f')+'-'+os.urandom(4).hex()+'.json'
    path=folder/name
    with path.open('xb') as f:f.write(encoded(value))
    path.with_suffix('.sha256').write_text(sha(path),encoding='utf-8')
    value['evidence_path']=str(path.relative_to(root));return value

def study(root,c):
    from .ai_strategy_researcher.data import load_dataset
    p,dataset_sha=load_dataset(root);rows=validated(p['series']['F']['1440']);prepared=signals(rows,CANDIDATE)
    result=dict(mode='SIMULATION_ONLY',strategy_version=VERSION,original_parameters=CANDIDATE,dataset_sha256=dataset_sha,
        final_holdout_evaluated=False,capital=100,maximum_exposure=1,costs=cost_assumptions(),results={},orders_sent=0)
    for rate in c['research_risk_percent']:
        # Local sizing scenario only: entry/exit parameters and all signal and
        # exit arrays are identical. Never registered as a new StrategyVersion.
        scenario={**CANDIDATE,'risk_percent':rate}
        result['results'][str(rate)]={model:{name:simulate_cash_capped(rows,scenario,model,start,end,prepared=prepared)
            for name,start,end in FOLDS} for model in MODELS}
    folder=Path(root)/FOLDER/'studies';folder.mkdir(parents=True,exist_ok=True)
    path=folder/(now().strftime('%Y%m%dT%H%M%S%f')+'.json')
    with path.open('xb') as f:f.write(encoded(result))
    path.with_suffix('.sha256').write_text(sha(path));return dict(evidence_path=str(path.relative_to(root)),
        results={r:{m:{f:v['metrics'] for f,v in folds.items()} for m,folds in models.items()} for r,models in result['results'].items()})

def simulate_cash_capped(*args,**kwargs):
    """Separate simulator globals add a $100 cash cap, without editing H40.

    Profits cannot enlarge exposure. Original signals/exits remain unchanged.
    """
    from .ai_strategy_researcher.simulation import size
    def capped(entry,stop,target,rate,ledger,model,observed_spread=None):
        proxy=SimpleNamespace(equity=ledger.equity,cash=min(D(100),ledger.cash),losses=ledger.losses)
        return size(entry,stop,target,rate,proxy,model,observed_spread)
    namespace={**simulate.__globals__,'size':capped}
    scoped=FunctionType(simulate.__code__,namespace,simulate.__name__,simulate.__defaults__,simulate.__closure__)
    return scoped(*args,**kwargs)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('Inspect','Study','Status','Run','Stop','Revoke'))
    parser.add_argument('--root',default=str(Path(__file__).resolve().parents[2]));args=parser.parse_args()
    root=Path(args.root);check_live();c=configuration(root)
    if args.action=='Inspect':result=inspect(root,c)
    elif args.action=='Study':result=study(root,c)
    elif args.action in ('Stop','Revoke'):
        (root/'.local').mkdir(exist_ok=True);(root/'.local/stock-paper-forward.stop').write_text(now().isoformat())
        if args.action=='Revoke' and (root/'.local/stock-paper-forward.dpapi').exists():
            from .paper_identity import protect
            g=unseal(root/'.local/stock-paper-forward.dpapi');g['revoked']=True
            p=root/'.local/stock-paper-forward.dpapi';tmp=p.with_suffix('.tmp');tmp.write_bytes(protect(encoded(g)));tmp.replace(p)
        result=dict(new_entries_stopped=True,revoked=args.action=='Revoke',manage_owned_inventory_required=True,emergency_unchanged=True)
    elif args.action=='Status':
        p=root/FOLDER/'journal.sqlite3';result=dict(environment='PAPER_TRADING',live_enabled=False,
            authorization_present=(root/'.local/stock-paper-forward.dpapi').exists(),execution_ready=False,entry_stop=(root/'.local/stock-paper-forward.stop').exists(),
            emergency=any((root/'.local'/n).exists() for n in ('paper-lab.emergency','paper-auto.stop')),
            strategy_version=VERSION,original_risk_percent=2,productive_maximum_risk_percent=.5)
        if p.exists():
            b=AccountBinding(unseal(root/'.local/ibkr-account-binding.dpapi'));j=Journal(p,b.binding_id)
            try:result['revision'],result['ledger']=j.load()
            finally:j.close()
    else:
        from .stock_paper_forward_runner import run
        result=run(root,c)
    print(json.dumps(result,default=str,allow_nan=False))

if __name__=='__main__':
    try:main()
    except Exception as exc:
        code=str(exc);print(json.dumps(dict(state='BLOCKED',reason=code if re.fullmatch('[A-Z][A-Z0-9_]{1,100}',code) else 'STOCK_FORWARD_FAILED',reason_type=type(exc).__name__,orders_sent='UNKNOWN_CHECK_JOURNAL',live_enabled=False)))
        raise SystemExit(1)
