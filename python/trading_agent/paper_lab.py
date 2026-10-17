"""Bounded Paper execution service. No entry point activates a session implicitly."""
import copy
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time


def utc(): return datetime.now(timezone.utc)
def stamp(at=None): return (at or utc()).isoformat()
def date(value):
    at=datetime.fromisoformat(value.replace('Z','+00:00'))
    if at.tzinfo is None: raise PermissionError('TIMESTAMP_ZONE_REQUIRED')
    return at
def num(value):
    v=Decimal(str(value))
    if not v.is_finite() or abs(v)>Decimal('1e12'): raise ValueError('INVALID_LAB_NUMBER')
    return v
def encoded(value): return json.dumps(value,default=lambda v:str(v) if isinstance(v,Decimal) else None,sort_keys=True,allow_nan=False)
def key(account): return 'PAPER-'+hashlib.sha256(account.encode()).hexdigest()[:16]
EXPERIMENTAL='PAPER_EXPERIMENTAL_10_PERCENT'


def unseal(path):
    if os.name!='nt': raise PermissionError('WINDOWS_DPAPI_REQUIRED')
    class Blob(ctypes.Structure): _fields_=[('size',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_ubyte))]
    data=Path(path).read_bytes();buffer=(ctypes.c_ubyte*len(data)).from_buffer_copy(data);source=Blob(len(data),buffer);target=Blob()
    crypt=ctypes.WinDLL('crypt32',use_last_error=True);kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    crypt.CryptUnprotectData.argtypes=[ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(Blob)]
    crypt.CryptUnprotectData.restype=wintypes.BOOL;kernel.LocalFree.argtypes=[ctypes.c_void_p]
    if not crypt.CryptUnprotectData(ctypes.byref(source),None,None,None,None,1,ctypes.byref(target)): raise PermissionError('AUTHORIZATION_UNREADABLE')
    try: return json.loads(ctypes.string_at(target.data,target.size))
    finally:
        ctypes.memset(target.data,0,target.size);kernel.LocalFree(ctypes.cast(target.data,ctypes.c_void_p))


def same_process(pid,started):
    if os.name!='nt': return False
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.GetProcessTimes.argtypes=[wintypes.HANDLE]+[ctypes.POINTER(wintypes.FILETIME)]*4
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    handle=kernel.OpenProcess(0x1000,False,int(pid))
    if not handle: return False
    try:
        times=[wintypes.FILETIME() for _ in range(4)]
        return bool(kernel.GetProcessTimes(handle,*[ctypes.byref(t) for t in times])) and (times[0].dwHighDateTime<<32|times[0].dwLowDateTime)==int(started)
    finally: kernel.CloseHandle(handle)


class Authorization:
    def __init__(self,loader,session_alive=same_process,clock=utc,endpoint=None):
        self.loader,self.session_alive,self.clock=loader,session_alive,clock
        from .ibkr_session import SessionConfiguration
        self.endpoint=endpoint or SessionConfiguration()
    def read(self,management=False):
        a=self.loader();now=self.clock()
        if a.get('review_only') and not management:raise PermissionError('REVIEW_ONLY_NO_EXECUTION')
        if os.environ.get('LIVE_TRADING','false').lower()!='false' or a.get('live_enabled') is not False or a.get('environment')!='PAPER_TRADING': raise PermissionError('LIVE_DISABLED')
        if a.get('schema_version')!=1 or a.get('authorized') is not True or a.get('paper_checked') is not True or a.get('read_only_disabled_checked') is not True or a.get('identity_manual_match') is not True or a.get('forex_permission_checked') is not True:
            raise PermissionError('PAPER_EXECUTION_NOT_AUTHORIZED')
        self.endpoint.matches(a)
        if not re.fullmatch(r'DU(?:R)?[0-9]+',a.get('account','')) or a.get('client_id')!=82 or not self.session_alive(a.get('tws_pid'),a.get('tws_start_filetime')):
            raise PermissionError('UNVERIFIED_PAPER_SESSION')
        if a.get('instruments')!=['EUR/USD'] or set(a.get('order_types',[]))!={'LMT','STP'} or a.get('mode') not in ('StrategyPaper','ExecutionDiagnostics'):
            raise PermissionError('AUTHORIZATION_SCOPE_INVALID')
        start,end=date(a['confirmed_at']),date(a['expires_at'])
        if start>now or not start<end<=start+timedelta(hours=24): raise PermissionError('AUTHORIZATION_TIME_INVALID')
        if not 1<=a.get('max_experiments',0)<=10 or not 0<num(a.get('max_quantity',0))<=100 or not 1<=a.get('max_hold_seconds',0)<=300:
            raise PermissionError('UNBOUNDED_DIAGNOSTIC')
        if not 0<num(a.get('max_notional_usd',0))<=250:raise PermissionError('UNBOUNDED_EXPOSURE')
        if not re.fullmatch(r'[a-f0-9]{32}',a.get('session_id','')): raise PermissionError('INVALID_SESSION_ID')
        if a['mode']=='ExecutionDiagnostics' and not 0<num(a.get('diagnostic_loss_budget',0))<=100: raise PermissionError('DIAGNOSTIC_BUDGET_REQUIRED')
        if a['mode']=='ExecutionDiagnostics' and (a['max_experiments']!=1 or num(a['diagnostic_loss_budget'])!=10 or
            num(a['max_notional_usd'])>150 or a['max_hold_seconds']>60 or end>start+timedelta(minutes=30)):
            raise PermissionError('SINGLE_DIAGNOSTIC_SCOPE_REQUIRED')
        if a.get('risk_profile', 'PAPER_CONSERVATIVE') not in ('PAPER_CONSERVATIVE',EXPERIMENTAL):raise PermissionError('UNKNOWN_PAPER_RISK_PROFILE')
        if a.get('risk_profile')==EXPERIMENTAL:
            if a['mode']!='StrategyPaper':raise PermissionError('STRATEGY_PAPER_PROFILE_SCOPE_REQUIRED')
            from .paper_strategy import validate_plan
            validate_plan(a.get('strategy_plan'),now,a.get('strategy_versions',[]),allow_expired=management)
            if a.get('strategy_requirements_verified') is not True:raise PermissionError('STRATEGY_EVIDENCE_REQUIRED')
        if a.get('emergency') is not False or a.get('revoked') is not False or now>=end:
            if not management or a.get('manage_owned_positions_after_stop') is not True: raise PermissionError('SESSION_STOPPED_OR_EXPIRED')
        return a


class DotnetJournal:
    def __init__(self,root,profile='PAPER_CONSERVATIVE'): self.root=Path(root);self.profile=profile
    def operation(self,name):return ('experimental-' if self.profile==EXPERIMENTAL else 'strategy-')+name
    def command(self,data):
        result=subprocess.run(['dotnet',str(self.root/'src/TradingAgent.Api/bin/Debug/net9.0/TradingAgent.Api.dll'),'--paper-lab-journal'],
            input=encoded(data),text=True,capture_output=True,timeout=20,cwd=self.root)
        value=json.loads(result.stdout)
        if result.returncode or 'error' in value:
            reason=value.get('reason','LAB_JOURNAL_FAILED')
            raise RuntimeError(reason if re.fullmatch(r'[A-Z][A-Z0-9_]{1,127}',reason) and not re.search(r'DU(?:R)?[0-9]{4,}',reason) else 'LAB_JOURNAL_FAILED')
        return value
    def load(self,account_key): return self.command({'operation':'load','account_key':account_key})
    def commit(self,account_key,revision,state,event): return self.command({'operation':'commit','account_key':account_key,'revision':revision,'state':state,'event':event})['revision']
    def strategy_risk(self,account,request):
        try:return self.command({'operation':self.operation('risk'),'account':account,'request':request})
        except RuntimeError as error:
            # An explicit prerequisite veto is a normal rejection, not engine
            # unavailability. Keep every unknown broker constraint unknown.
            if str(error)!='STRATEGY_PAPER_EVIDENCE_REQUIRED':raise
            return {'allowed':False,'reason':str(error),'decision':'REJECT',
                    'quantity':0,'source':'PAPER_RISK_PROFILE_PREREQUISITE'}
    def strategy_initial(self): return self.command({'operation':self.operation('initial')})
    def strategy_mark(self,account): return self.command({'operation':self.operation('mark'),'account':account})
    def strategy_reserve(self,account,request,intent):return self.command({'operation':self.operation('reserve'),'account':account,'request':request,'intent':intent})
    def strategy_release_unfilled(self,account,intent):return self.command({'operation':self.operation('release-unfilled'),'account':account,'intent':intent})
    def strategy_settle(self,account,net,fees,intent=None): return self.command({'operation':self.operation('settle'),'account':account,'net':str(net),'fees':str(fees),'intent':intent})


class PaperLab:
    def __init__(self,authorization,journal,wire,clock=utc,stop_file=None,eur_exception=None,exception_review=False):
        self.auth,self.journal,self.wire,self.clock=authorization,journal,wire,clock
        self.stop_file=Path(stop_file) if stop_file else None
        self.eur_exception=eur_exception;self.exception_review=exception_review;self.absence_entry_intent=None;self.reconciliation_kind='STRICT'
        a=self.auth.read(management=True);self.scope=key(a['account']);self.session_id=a['session_id'];self.mode=a['mode']
        self.experimental=self.mode=='StrategyPaper' and a.get('risk_profile')==EXPERIMENTAL
        saved=journal.load(self.scope);self.revision=saved['revision'];self.state=saved['state'] or {
            'environment':'PAPER_TRADING','live_enabled':False,'account_key':self.scope,'emergency':False,
            'next_order_id':0,'orders':{},'sessions':{},'experiences':{},'strategy_capital':{'initial':100,'loss_allowance':20,'consumed_loss':'0','equity':'100'}}
        self.reconciled=False
        if self.mode=='StrategyPaper' and 'strategy_account' not in self.state:
            if num(self.state['strategy_capital']['consumed_loss'])!=0 or num(self.state['strategy_capital']['equity'])!=100:raise PermissionError('STRATEGY_CAPITAL_HISTORY_REQUIRED')
            self.state['strategy_account']=journal.strategy_initial()
        for o in self.state['orders'].values():
            if o['state'] in ('SEND_PENDING','ACKNOWLEDGED','PARTIALLY_FILLED','CANCEL_PENDING'): o['state']='UNKNOWN'
        self.persist('START_SUSPENDED')
    def persist(self,event,data=None):
        names={'INTENT_RESERVED_BEFORE_TRANSMISSION':'ORDER_INTENT_CREATED','STRATEGY_RISK_REJECTION':'ORDER_BLOCKED_BY_RISK',
               'RECONCILED':'RECONCILIATION_COMPLETED','INITIAL_EUR_ABSENCE_ACCEPTED_WITH_UNCERTAINTY':'RECONCILIATION_COMPLETED',
               'BROKER_DISCONNECTED':'IBKR_DISCONNECTED',
               'OWNER_FLAT_REVIEW_CLEARED_EMERGENCY':'EMERGENCY_STOP_CLEARED'}
        self.revision=self.journal.commit(self.scope,self.revision,self.state,{'event':event,'at':stamp(self.clock()),
            'structured_event':names.get(event,event),'data':data})
    def stop(self,reason,data=None):
        self.state['emergency']=True;self.reconciled=False;self.persist(reason,data)
    def check(self,management=False):
        a=self.auth.read(management=management)
        if a['session_id']!=self.session_id or a['mode']!=self.mode or key(a['account'])!=self.scope or (a.get('risk_profile')==EXPERIMENTAL)!=self.experimental: raise PermissionError('SESSION_CHANGED')
        # Refresh durable revocation/emergency state; a conflicting writer prevents any transmission.
        saved=self.journal.load(self.scope)
        if saved['revision']!=self.revision: raise PermissionError('JOURNAL_CHANGED_RECONCILE_REQUIRED')
        if self.state.get('unresolved_executions'):raise PermissionError('UNRECOGNIZED_EXECUTION_REVIEW_REQUIRED')
        if not management and (self.state['emergency'] or self.stop_file and self.stop_file.exists()): raise PermissionError('EMERGENCY_STOP')
        if not self.reconciled and self.reconciliation_kind=='STRICT_REQUIRED_AFTER_FIRST_FILL':raise PermissionError('STRICT_RECONCILIATION_REQUIRED_AFTER_FIRST_FILL')
        if not self.wire.connected or not self.reconciled: raise PermissionError('RECONCILIATION_REQUIRED')
        if not management and self.reconciliation_kind=='OWNED_PREFILL_EUR_ABSENCE':raise PermissionError('EUR_EXCEPTION_ALREADY_BOUND_NO_NEW_ENTRY')
        if not management and self.reconciliation_kind=='INITIAL_EUR_ABSENCE_EXCEPTION':
            if self.exception_review:raise PermissionError('EUR_EXCEPTION_REVIEW_NEVER_TRANSMITS')
            e=self.eur_exception.read(a)
            if e['record_id']!=self.state['initial_eur_absence']['record_id']:raise PermissionError('EUR_EXCEPTION_CHANGED')
            if not 0<=(self.clock()-date(self.state['initial_eur_absence']['accepted_at'])).total_seconds()<=30:raise PermissionError('EUR_EXCEPTION_BASELINE_STALE')
            consumed=self.state.get('eur_absence_consumed',{}).get(e['record_id'])
            if consumed and consumed['intent']!=self.absence_entry_intent:raise PermissionError('EUR_EXCEPTION_ALREADY_CONSUMED')
            if consumed and self.state['orders'][consumed['intent']]['fills']:raise PermissionError('STRICT_RECONCILIATION_REQUIRED_AFTER_FIRST_FILL')
            if consumed:self.wire.validate_quote(self.state['orders'][self.absence_entry_intent]['quote'])
        return a
    def authorize_transport(self,o,role,order_id,quantity=None):
        """Bind every mutation to the persisted intention; SELL is never an entry."""
        a=self.check(management=role not in ('BRACKET_ENTRY','BRACKET_PROTECTION'))
        saved=self.journal.load(self.scope)['state'];registered=(saved or {}).get('orders',{}).get(o.get('intent'))
        immutable=('intent','session_id','category','contract_id','client_id','order_ids','quantity','entry','stop','target','payload')
        if not registered or any(encoded(registered.get(k))!=encoded(o.get(k)) for k in immutable):
            raise PermissionError('ORDER_NOT_DURABLY_REGISTERED')
        if registered['fills']!=o['fills'] or registered['statuses']!=o['statuses']:raise PermissionError('ORDER_STATE_CHANGED_RECONCILE_REQUIRED')
        ids=registered['order_ids'];qty=self.inventory(registered)
        if role in ('BRACKET_ENTRY','BRACKET_PROTECTION'):
            if (registered['state']!='SEND_PENDING' or registered['fills'] or registered['session_id']!=self.session_id or
                order_id not in ([ids[0]] if role=='BRACKET_ENTRY' else ids[1:]) or num(quantity)!=num(registered['quantity'])):
                raise PermissionError('BRACKET_ALREADY_ATTEMPTED_OR_CHANGED')
        elif role=='OWNED_CLOSE':
            if (order_id!=ids[1] or qty<=0 or num(quantity)!=qty or registered['statuses'].get(str(ids[0])) not in ('Filled','Cancelled','ApiCancelled') or
                not (registered.get('timeout_close_sent') or registered.get('strategy_close_sent'))):
                raise PermissionError('NO_EXACT_OWNED_POSITION_TO_CLOSE')
            for field in ('closing_quote','close_requested_at','close_requested_price','close_requested_quantity','timeout_close_sent','strategy_close_sent'):
                if encoded(registered.get(field))!=encoded(o.get(field)):raise PermissionError('CLOSE_REQUEST_CHANGED_RECONCILE_REQUIRED')
        elif role=='CANCEL_PARENT':
            if order_id!=ids[0] or not registered.get('cancel_parent_sent'):raise PermissionError('CANCEL_NOT_DURABLY_REGISTERED')
        else:raise PermissionError('UNSCOPED_MUTATION_DISABLED')
        return a
    def collect_snapshot(self):
        # Receive executions before applying cash gates; missing EUR must not discard a late fill.
        return self.wire.snapshot(diagnostic=True) if any(o.get('initial_eur_uncertainty') for o in self.state['orders'].values()) else self.wire.snapshot()
    def bound_prefill_order(self,a):
        if len(self.state['orders'])!=1:return None
        o=next(iter(self.state['orders'].values()));baseline=o.get('initial_eur_uncertainty',{})
        binding=self.state.get('eur_absence_consumed',{}).get(baseline.get('record_id'),{})
        if (o['fills'] or not baseline or baseline.get('evidence',{}).get('eligible') is not True or
            binding.get('intent')!=o['intent'] or binding.get('session_id')!=o['session_id'] or
            a.get('eur_absence_exception_id')!=baseline.get('record_id') or o['session_id']!=a['session_id']):return None
        return o
    def reconcile_owned_prefill(self,snapshot,additional):
        o=self.bound_prefill_order(self.auth.read(management=True))
        if not o:return False
        from .paper_eur_reconciliation import owned_prefill_absence_evidence
        evidence=owned_prefill_absence_evidence(snapshot,additional,o,self.clock())
        if self.state.get('unresolved_executions') or self.state.get('pending_commissions') or self.state.get('unavailable_commissions') or not evidence['eligible']:
            self.stop('OWNED_PREFILL_RECONCILIATION_BLOCKED',evidence);raise PermissionError('OWNED_PREFILL_RECONCILIATION_BLOCKED')
        self.reconciliation_kind='OWNED_PREFILL_EUR_ABSENCE';self.reconciled=True
        o['prefill_reconciliation']={'at':stamp(self.clock()),'evidence':evidence}
        # A local ApiCancelled with permId=0 is not server proof that all three legs were cancelled.
        confirmations=o.get('completed_orders',{})
        if (not snapshot['orders'] and all(confirmations.get(str(i),{}).get('status') in ('Cancelled','Rejected') and confirmations[str(i)].get('perm_id',0)>0 for i in o['order_ids'])):
            o.setdefault('cancellation_reconciled_at',stamp(self.clock()));o.setdefault('final_snapshot',copy.deepcopy(snapshot))
            self.state['sessions'][o['session_id']]['reserved']='0'
        return True
    def connect_and_reconcile(self):
        self.reconciled=False;self.persist('RECONCILIATION_STARTED')
        a=self.auth.read(management=True);accounts=self.wire.connect(a)
        if accounts!=[a['account']]: raise PermissionError('EXACT_IDENTITY_MISMATCH')
        self.reconciled=False;self.reconciliation_kind='STRICT'
        can_prepare=self.eur_exception is not None and (self.exception_review or a.get('eur_absence_exception_id')) and not self.state['orders']
        if can_prepare:self.eur_exception.read(a,for_review=self.exception_review)
        snapshot=self.wire.snapshot(diagnostic=True) if can_prepare else self.collect_snapshot()
        self.ingest(snapshot['events'])
        if any(o['fills'] for o in self.state['orders'].values()):can_prepare=False
        ids={int(o['order_id']) for o in snapshot['orders']}
        owned={i for o in self.state['orders'].values() for i in o['order_ids']+o.get('recovery_order_ids',[])}
        closed_ids={i for o in self.state['orders'].values() if o['state']=='CLOSED' or o['state'] in ('REJECTED','CANCELLED_NO_FILL') and (not o.get('diagnostic_evidence_version') or o.get('cancellation_reconciled_at')) for i in o['order_ids']+o.get('recovery_order_ids',[])}
        if ids-owned or ids&closed_ids:
            self.stop('FOREIGN_OR_UNRECONCILED_EXPOSURE');raise PermissionError('FOREIGN_OR_UNRECONCILED_EXPOSURE')
        prefill=self.bound_prefill_order(a)
        additional=self.wire.additional_exposure() if can_prepare or prefill else None
        exposure_rows=(additional or {}).get('positions',[])+snapshot.get('positions',[])+snapshot.get('portfolio',[])
        if can_prepare and (not self.wire.connected or additional.get('status')!='COMPLETE' or additional.get('errors') or (any(num(p.get('quantity',1))!=0 for p in exposure_rows) if self.experimental or self.eur_exception.read(a,for_review=self.exception_review).get('mode')=='StrategyPaper' else exposure_rows)):
            raise PermissionError('INITIAL_EXPOSURE_NOT_EMPTY_OR_INCOMPLETE')
        if can_prepare and snapshot['eur_cash'] is None:
            from .paper_eur_reconciliation import initial_absence_evidence
            e=self.eur_exception.read(a,for_review=self.exception_review)
            evidence=initial_absence_evidence(snapshot,additional,self.state,self.clock(),strategy=e.get('mode')=='StrategyPaper')
            if not self.wire.connected or not evidence['eligible']:raise PermissionError('INITIAL_EUR_EXCEPTION_EVIDENCE_BLOCKED')
            self.state['initial_eur_absence']={'record_id':e['record_id'],'eur_balance':None,'eur_state':'EUR_ROW_ABSENT','accepted_at':stamp(self.clock()),'evidence':evidence,'additional':additional}
            self.reconciliation_kind='INITIAL_EUR_ABSENCE_EXCEPTION'
        elif snapshot['eur_cash'] is None and self.reconcile_owned_prefill(snapshot,additional):pass
        else:
            self.reconciliation_kind='STRICT';self.exposure(snapshot)
        for o in self.state['orders'].values():
            if o['state']=='UNKNOWN' and not any(i in ids for i in o['order_ids']) and not o['fills']:
                self.stop('AMBIGUOUS_SEND_MANUAL_REVIEW');raise PermissionError('AMBIGUOUS_SEND_MANUAL_REVIEW')
            self.protection(o,snapshot['orders'])
            if self.experimental and o['category']=='PAPER_STRATEGY' and o['state'] in ('REJECTED','CANCELLED_NO_FILL') and not any(i in ids for i in o['order_ids']) and not o['fills'] and self.state['strategy_account'].get('reservationId')==o['intent']:
                self.state['strategy_account']=self.journal.strategy_release_unfilled(self.state['strategy_account'],o['intent'])
        self.state['next_order_id']=max(self.state['next_order_id'],self.wire.next_order_id,max(ids,default=0)+1)
        self.reconciled=True;self.persist('INITIAL_EUR_ABSENCE_ACCEPTED_WITH_UNCERTAINTY' if self.reconciliation_kind=='INITIAL_EUR_ABSENCE_EXCEPTION' else 'RECONCILED',
            {'session_events':getattr(self.wire,'session_events',[])})
        if hasattr(self.wire,'session_events'):self.wire.session_events.clear()
        return snapshot
    @staticmethod
    def inventory(order):
        return sum((num(e['quantity'])*(1 if e['side']=='BUY' else -1) for e in order['fills'].values()),Decimal(0))
    def exposure(self,snapshot):
        if not self.wire.connected:
            self.stop('BROKER_DISCONNECTED');raise PermissionError('BROKER_DISCONNECTED')
        if snapshot['eur_cash'] is None:
            self.stop('EUR_CASH_RECONCILIATION_UNAVAILABLE');raise PermissionError('EUR_CASH_RECONCILIATION_UNAVAILABLE')
        self.reconciliation_kind='STRICT'
        owned={i:o for o in self.state['orders'].values() for i in o['order_ids']+o.get('recovery_order_ids',[])}
        if any(r.get('order_id') not in owned for r in snapshot['orders']):
            self.stop('FOREIGN_OR_UNRECONCILED_ORDER');raise PermissionError('FOREIGN_OR_UNRECONCILED_ORDER')
        expected=sum((self.inventory(o) for o in self.state['orders'].values()),Decimal(0))
        euro_fees=sum((num(c['amount']) for o in self.state['orders'].values() for c in o['commissions'].values() if c['currency']=='EUR'),Decimal(0))
        if snapshot['foreign_positions'] or snapshot.get('foreign_currency_balances') or abs(num(snapshot['eur_cash'])-(expected-euro_fees))>Decimal('0.000001'):
            self.stop('FOREIGN_OR_UNRECONCILED_EXPOSURE');raise PermissionError('FOREIGN_OR_UNRECONCILED_EXPOSURE')
        cash=snapshot.get('cash_reconciliation',{})
        if cash and (cash.get('query_status')!='COMPLETE' or cash.get('account_ready') is not True):
            self.stop('ACCOUNT_QUERY_INCOMPLETE');raise PermissionError('ACCOUNT_QUERY_INCOMPLETE')
        post_positions=snapshot.get('positions',[])+snapshot.get('portfolio',[])
        if cash.get('state')=='CONFIRMED_ZERO' and cash.get('query_status')=='COMPLETE' and cash.get('account_ready') is True and snapshot.get('exposure_reads_complete') is True and not snapshot['orders'] and not any(num(p['quantity'])!=0 for p in post_positions) and not self.state.get('pending_commissions') and not self.state.get('unavailable_commissions'):
            for o in self.state['orders'].values():
                if (o.get('initial_eur_uncertainty') or o.get('diagnostic_evidence_version')==2) and o['fills'] and self.inventory(o)==0 and all(e in o['commissions'] for e in o['fills']):
                    o.setdefault('post_eur_reconciled_at',stamp(self.clock()))
                    o.setdefault('final_snapshot',copy.deepcopy(snapshot));self.derive(o)
                elif o.get('diagnostic_evidence_version')==2 and not o['fills'] and o['state'] in ('REJECTED','CANCELLED_NO_FILL') and all(o.get('completed_orders',{}).get(str(i),{}).get('status') in ('Cancelled','Rejected') and o['completed_orders'][str(i)].get('perm_id',0)>0 for i in o['order_ids']):
                    o.setdefault('cancellation_reconciled_at',stamp(self.clock()))
                    o.setdefault('final_snapshot',copy.deepcopy(snapshot))
                    self.state['sessions'][o['session_id']]['reserved']='0'
        self.reconciled=True
    def protection(self,o,orders):
        qty=self.inventory(o)
        if qty<0: self.stop('OVERSELL_DETECTED');raise PermissionError('OVERSELL_DETECTED')
        if qty>0:
            stop_filled=sum((num(e['quantity']) for e in o['fills'].values() if e['order_id']==o['order_ids'][2]),Decimal(0))
            stops=[r for r in orders if r['order_id']==o['order_ids'][2] and r['status'] in ('Submitted','PreSubmitted') and r['order_type']=='STP' and r['side']=='SELL' and r['oca_type']==2 and r['oca_group']==o['intent'] and r['client_id']==82 and r['contract_id']==12087792 and r['parent_id']==o['order_ids'][0] and r['reference']==o['intent'] and num(r['quantity'])-stop_filled==qty]
            if not stops or any(o.get('held_orders',{}).get(str(r['order_id'])) for r in stops): self.stop('PROTECTION_UNCONFIRMED');raise PermissionError('PROTECTION_UNCONFIRMED')
    def begin(self,intent,quantity,quote,market_context=None,strategy_version='diagnostic-v1',strategy_account=None,strategy_request=None):
        if not re.fullmatch(r'[a-f0-9]{64}',intent): raise ValueError('INVALID_INTENT')
        payload={'quantity':str(num(quantity)),'strategy_version':strategy_version,'mode':self.mode,'context':market_context or {}}
        prior=self.state['orders'].get(intent)
        if prior:
            if prior['payload']!=payload: raise PermissionError('IDEMPOTENCY_CONFLICT')
            return prior  # Never retransmit an existing intention, including UNKNOWN.
        if self.mode=='ExecutionDiagnostics' and any(o['category']=='PAPER_DIAGNOSTIC' for o in self.state['orders'].values()):
            raise PermissionError('DIAGNOSTIC_ALREADY_ATTEMPTED')
        snapshot=self.connect_and_reconcile();a=self.check();q=num(quantity)
        self.wire.validate_quote(quote)
        if not 0<q<=num(a['max_quantity']) or q%Decimal('0.01'): raise PermissionError('QUANTITY_OUTSIDE_AUTHORIZATION')
        if quote['type']!='LIVE' or not 0<= (self.clock()-date(quote['at'])).total_seconds()<=5 or num(quote['bid'])<=0 or num(quote['ask'])<num(quote['bid']): raise PermissionError('QUOTE_UNUSABLE')
        if q*num(quote['ask'])>num(a['max_notional_usd']):raise PermissionError('NOTIONAL_LIMIT')
        contract=self.wire.contract_details()
        if self.experimental:
            minimum=num(contract.get('minimum_size_metadata',0));step=num(contract.get('size_increment_metadata',0))
            if minimum<=0 or step<=0:raise PermissionError('CONTRACT_QUANTITY_UNVERIFIED')
            if q<minimum or (q-minimum)%step:raise PermissionError('CONTRACT_QUANTITY_INCREMENT')
        if any(o['state'] not in ('CLOSED','REJECTED','CANCELLED_NO_FILL') for o in self.state['orders'].values()): raise PermissionError('EXISTING_ORDER_OR_POSITION')
        if (self.experimental or self.mode=='ExecutionDiagnostics') and (self.state.get('pending_commissions') or self.state.get('unavailable_commissions')):raise PermissionError('PAPER_RESULT_UNRESOLVED')
        session=self.state['sessions'].get(self.session_id,{'count':0,'consumed_loss':'0','reserved':'0','budget':str(a.get('diagnostic_loss_budget',0))})
        if not self.experimental and session['count']>=a['max_experiments']: raise PermissionError('EXPERIMENT_LIMIT')
        if self.mode=='ExecutionDiagnostics':
            # Reserve the entire independent allowance for this experiment, including unresolved charges.
            reserve=num(session['budget'])-num(session['consumed_loss'])
            if reserve<Decimal('8.50') or num(session['reserved'])>0: raise PermissionError('DIAGNOSTIC_BUDGET_EXHAUSTED')
            risk=None
        else:
            if a.get('strategy_requirements_verified') is not True or strategy_version not in a.get('strategy_versions',[]):raise PermissionError('STRATEGY_EVIDENCE_REQUIRED')
            if strategy_account is None or strategy_request is None: raise PermissionError('STRATEGY_EVIDENCE_REQUIRED')
            execution_ask=(num(quote['ask'])/Decimal('0.00005')).to_integral_value(rounding='ROUND_CEILING')*Decimal('0.00005') if self.experimental else num(quote['ask'])
            if strategy_request['side']!='BUY' or num(strategy_request['bid'])!=num(quote['bid']) or num(strategy_request['ask'])!=execution_ask:raise PermissionError('STRATEGY_QUOTE_OR_SIDE_MISMATCH')
            # Caller does not supply fresh/reset capital: compare against persisted strategy allocation.
            if encoded(strategy_account)!=encoded(self.state.get('strategy_account')): raise PermissionError('STRATEGY_ALLOCATION_NOT_REGISTERED')
            strategy_account=self.journal.strategy_mark(strategy_account)
            self.state['strategy_account']=strategy_account
            risk=self.journal.strategy_risk(strategy_account,strategy_request)
            if not risk.get('allowed') or q>num(risk['quantity']): raise PermissionError('STRATEGY_RISK_REJECTED')
            reserve=num(risk['estimatedLoss']);session['budget']='20'
            if self.experimental and q!=num(risk['quantity']):raise PermissionError('STRATEGY_AUTOMATIC_QUANTITY_REQUIRED')
        tick=Decimal('0.00005');entry=(num(quote['ask'])/tick).to_integral_value(rounding='ROUND_CEILING')*tick
        stop=(num(quote['bid'])-Decimal('0.001'))//tick*tick;target=(entry+Decimal('0.0015'))//tick*tick
        if self.mode=='StrategyPaper':
            stop=num(strategy_request['stop']);target=num(strategy_request['execution']['takeProfit'])
            if not self.experimental and entry!=num(quote['ask']) or stop%tick or target%tick:raise PermissionError('STRATEGY_PRICE_GRID_MISMATCH')
        if stop<=0: raise PermissionError('INVALID_STOP')
        if q*entry>num(a['max_notional_usd']):raise PermissionError('NOTIONAL_LIMIT')
        if self.mode=='ExecutionDiagnostics':
            estimated=q*(entry-stop+Decimal('0.00045')+Decimal('0.00005'))+4
            if estimated>reserve:raise PermissionError('DIAGNOSTIC_ESTIMATED_RISK_EXCEEDS_BUDGET')
        # Contract/risk preparation may race with new broker exposure. Refresh every admission gate.
        snapshot=self.connect_and_reconcile();a=self.check();self.wire.validate_quote(quote)
        if hasattr(self.wire,'assert_mutation_allowed'):self.wire.assert_mutation_allowed(a)
        if not 0<=(self.clock()-date(quote['at'])).total_seconds()<=5:raise PermissionError('QUOTE_UNUSABLE')
        base=max(self.state['next_order_id'],self.wire.next_order_id);self.state['next_order_id']=base+3
        order={'intent':intent,'payload':payload,'session_id':self.session_id,'category':'PAPER_DIAGNOSTIC' if self.mode=='ExecutionDiagnostics' else 'PAPER_STRATEGY',
            'contract_id':12087792,'client_id':82,'order_ids':[base,base+1,base+2],'perm_ids':{},'state':'SEND_PENDING','statuses':{},
            'quantity':str(q),'entry':str(entry),'stop':str(stop),'target':str(target),'quote':quote,'fills':{},'commissions':{},'reserve':str(reserve),
            'sent_at':stamp(self.clock()),'max_hold_seconds':a['max_hold_seconds'],'incidents':[],'risk':risk,'timeout_close_sent':False}
        order['margin_before']=snapshot.get('initial_margin')
        if self.mode=='ExecutionDiagnostics':
            order.update(diagnostic_evidence_version=2,contract_evidence=copy.deepcopy(contract),initial_snapshot=copy.deepcopy(snapshot),
                diagnostic_estimated_risk_usd=str(estimated),diagnostic_cost_estimate_status='ESTIMATED_NOT_ACCOUNT_VERIFIED')
        if self.reconciliation_kind=='INITIAL_EUR_ABSENCE_EXCEPTION':
            e=self.eur_exception.read(a)
            if e['record_id'] in self.state.get('eur_absence_consumed',{}):raise PermissionError('EUR_EXCEPTION_ALREADY_CONSUMED')
            order['initial_eur_uncertainty']=copy.deepcopy(self.state['initial_eur_absence'])
            self.state.setdefault('eur_absence_consumed',{})[e['record_id']]={'intent':intent,'session_id':self.session_id,'used_at':stamp(self.clock()),'eur_balance':None}
            self.absence_entry_intent=intent
        if self.experimental:self.state['strategy_account']=self.journal.strategy_reserve(strategy_account,strategy_request,intent)
        self.state['orders'][intent]=order;self.state['sessions'][self.session_id]=session;session['count']+=1;session['reserved']=str(reserve);self.persist('INTENT_RESERVED_BEFORE_TRANSMISSION')
        try:
            self.check();self.wire.bracket(order,a)  # Sequential parent/TP/stop; SDK transmit flags false,false,true.
        except Exception:
            order['state']='UNKNOWN';order['incidents'].append('SEND_UNCERTAIN');self.stop('DISCONNECTED_OR_SEND_UNCERTAIN');raise
        return order
    def strategy_proposal(self,proposal,quote):
        if not self.reconciled:self.connect_and_reconcile()
        a=self.check()
        if self.mode!='StrategyPaper' or a.get('strategy_requirements_verified') is not True:
            raise PermissionError('STRATEGY_EVIDENCE_REQUIRED')
        requirements=a.get('execution_requirements')
        if not isinstance(requirements,dict):raise PermissionError('STRATEGY_EVIDENCE_REQUIRED')
        if set(proposal)!={'strategy_version','signal_at','stop','target','market_context'} or proposal['strategy_version'] not in a.get('strategy_versions',[]):raise PermissionError('STRATEGY_VERSION_NOT_AUTHORIZED')
        if not 0<=(self.clock()-date(proposal['signal_at'])).total_seconds()<=30:raise PermissionError('STRATEGY_SIGNAL_STALE')
        # Proposals supply geometry only. Fees, quantities, margin and real restrictions come from the sealed owner record.
        request=copy.deepcopy(requirements)
        request.update(instrument='EUR/USD',side='BUY',bid=quote['bid'],ask=quote['ask'],stop=proposal['stop'],marketAt=quote['at'])
        if self.experimental:request['ask']=str((num(quote['ask'])/Decimal('0.00005')).to_integral_value(rounding='ROUND_CEILING')*Decimal('0.00005'))
        request['execution'].update(environment='PAPER_TRADING',quoteStatus='LIVE',at=quote['at'],takeProfit=proposal['target'])
        account=self.journal.strategy_mark(self.state['strategy_account'])
        if self.experimental:
            request['availableMargin']=str(min(num(request['availableMargin']),num(account['equity'])))
            request['maximumQuantity']=str(min(num(a['max_quantity']),num(a['max_notional_usd'])/num(request['ask'])))
        self.state['strategy_account']=account;self.persist('STRATEGY_VIRTUAL_MARK')
        risk=self.journal.strategy_risk(account,request)
        if not risk.get('allowed'):
            self.persist('STRATEGY_RISK_REJECTION',risk);return {'state':'STRATEGY_REJECTED','risk':risk}
        quantity=min(num(risk['quantity']),num(a['max_quantity']))
        intent=hashlib.sha256(encoded({'scope':self.scope,'version':proposal['strategy_version'],'signal_at':proposal['signal_at'],'contract':12087792,'side':'BUY'}).encode()).hexdigest()
        return self.begin(intent,quantity,quote,proposal['market_context'],proposal['strategy_version'],account,request)
    def ingest(self,events):
        changed=False
        for e in events:
            if e['kind']=='disconnect': self.stop('BROKER_DISCONNECTED');continue
            if e['kind']=='readonly': self.stop('READ_ONLY_API_BLOCKED');continue
            if e['kind']=='commission_unavailable':
                self.state.setdefault('unavailable_commissions',{})[e['exec_id']]=e;changed=True;continue
            if e['kind']=='commission':
                self.state.setdefault('unavailable_commissions',{}).pop(e['exec_id'],None)
                owners=[o for o in self.state['orders'].values() if e['exec_id'] in o['fills']]
                if not owners:
                    # Fee may precede fill: retain it durably and attach once the execution arrives.
                    self.state.setdefault('pending_commissions',{})[e['exec_id']]=e;changed=True;continue
                o=owners[0];old=o['commissions'].get(e['exec_id'])
                if old and any(old.get(k)!=e.get(k) for k in ('exec_id','amount','currency')): self.stop('COMMISSION_CONFLICT');raise ValueError('COMMISSION_CONFLICT')
                if not old: o['commissions'][e['exec_id']]=e;changed=True
                continue
            o=next((o for o in self.state['orders'].values() if e.get('order_id') in o['order_ids']+o.get('recovery_order_ids',[])),None)
            if not o:
                if e['kind']=='fill':
                    self.state.setdefault('unresolved_executions',{})[e['exec_id']]=e
                    self.stop('UNRECOGNIZED_EXECUTION');raise PermissionError('UNRECOGNIZED_EXECUTION')
                continue
            recovery=o.get('recovery_orders',{}).get(str(e.get('order_id')))
            if e['kind']=='fill':
                if e['client_id']!=82 or e['contract_id']!=12087792 or e['side']!=('BUY' if e['order_id']==o['order_ids'][0] else 'SELL') or num(e['quantity'])<=0 or num(e['price'])<=0:
                    self.stop('INVALID_EXECUTION');raise ValueError('INVALID_EXECUTION')
                old=o['fills'].get(e['exec_id'])
                if old and any(old.get(k)!=e.get(k) for k in ('exec_id','order_id','perm_id','client_id','contract_id','side','quantity','price','broker_time_raw')): self.stop('EXECUTION_CONFLICT');raise ValueError('EXECUTION_CONFLICT')
                if not old:
                    if o['state']=='CLOSED':
                        self.state.setdefault('unresolved_executions',{})[e['exec_id']]=e
                        self.stop('LATE_EXECUTION_AFTER_CLOSED');raise PermissionError('LATE_EXECUTION_AFTER_CLOSED')
                    if not o['fills']:
                        self.reconciled=False;self.reconciliation_kind='STRICT_REQUIRED_AFTER_FIRST_FILL'
                        if o['state'] in ('CANCELLED_NO_FILL','REJECTED'):
                            self.state['emergency']=True;self.state['sessions'][o['session_id']]['reserved']=o['reserve'];o['incidents'].append('LATE_FILL_AFTER_CANCEL')
                        if o.get('initial_eur_uncertainty'):
                            binding=self.state['eur_absence_consumed'][o['initial_eur_uncertainty']['record_id']]
                            binding.update(first_fill_at=e['at'],phase='STRICT_REQUIRED_AFTER_FIRST_FILL')
                    o['fills'][e['exec_id']]=e
                    if e.get('perm_id'):o['perm_ids'][str(e['order_id'])]=e['perm_id']
                    changed=True
                    o.setdefault('fill_request_prices',{})[e['exec_id']]=str(num(o['entry'] if e['side']=='BUY' else
                        recovery['price'] if recovery else o['stop'] if e['order_id']==o['order_ids'][2] else o.get('close_requested_price',o['target'])))
                    if e['side']=='BUY' and not o.get('first_open_fill_received_at'):
                        o['first_open_fill_received_at']=e['at']
                        # A missing/unverified broker clock falls back to the earlier submission bound.
                        anchor=e.get('broker_at') or o['sent_at']
                        o['close_deadline_at']=stamp(min(date(anchor),date(e['at']))+timedelta(seconds=o['max_hold_seconds']))
                    pending=self.state.setdefault('pending_commissions',{}).pop(e['exec_id'],None)
                    if pending:o['commissions'][e['exec_id']]=pending
            elif e['kind'] in ('status','open_order','completed_order','reject'):
                if e['kind']=='completed_order':
                    index=1 if recovery else o['order_ids'].index(e['order_id'])
                    if (e.get('client_id')!=82 or e.get('contract_id')!=12087792 or e.get('reference')!=(recovery['reference'] if recovery else o['intent']) or
                        e.get('side')!=('BUY' if index==0 else 'SELL') or e.get('parent_id')!=(0 if recovery or index==0 else o['order_ids'][0])):
                        self.stop('COMPLETED_ORDER_LINK_UNVERIFIED');raise PermissionError('COMPLETED_ORDER_LINK_UNVERIFIED')
                    o.setdefault('completed_orders',{})[str(e['order_id'])]=e
                    if e['status'] in ('Filled','Cancelled','Rejected'):o['statuses'][str(e['order_id'])]=e['status']
                if e['kind']=='reject':
                    o['incidents'].append('IBKR_'+str(e['code']));o['statuses'][str(e['order_id'])]='Rejected'
                    # A rejected child is not a rejected, flat parent.
                    if e['order_id']!=o['order_ids'][0]: self.state['emergency']=True
                else:
                    old=o['statuses'].get(str(e['order_id']))
                    terminal=('Filled','Cancelled','ApiCancelled','Rejected')
                    if old not in terminal:o['statuses'][str(e['order_id'])]=e['status']
                    if e.get('perm_id'):o['perm_ids'][str(e['order_id'])]=e['perm_id']
                    if 'why_held' in e:o.setdefault('held_orders',{})[str(e['order_id'])]=e['why_held']
                    if e['kind']=='open_order':o.setdefault('broker_orders',{})[str(e['order_id'])]=e
                changed=True
        for o in self.state['orders'].values():self.derive(o)
        if changed:self.persist('BROKER_EVENTS',events)
    def derive(self,o):
        if o['state']=='CLOSED': return
        buys=sum((num(e['quantity']) for e in o['fills'].values() if e['side']=='BUY'),Decimal(0));sells=sum((num(e['quantity']) for e in o['fills'].values() if e['side']=='SELL'),Decimal(0))
        if buys>num(o['quantity']) or sells>buys:self.state['emergency']=True;o['state']='UNKNOWN';return
        parent=o['statuses'].get(str(o['order_ids'][0]))
        if buys==0:
            o['state']='REJECTED' if parent=='Rejected' else 'CANCELLED_NO_FILL' if parent in ('Cancelled','ApiCancelled') else 'ACKNOWLEDGED' if parent in ('Submitted','PreSubmitted') else o['state']
            if o['state'] in ('REJECTED','CANCELLED_NO_FILL') and o.get('diagnostic_evidence_version')!=2:
                self.state['sessions'][o['session_id']]['reserved']='0'
            return
        o['state']='FILLED' if buys==num(o['quantity']) else 'PARTIALLY_FILLED'
        if sells==buys:
            o['state']='AWAITING_COMMISSIONS'
            # Confirm parent no longer working; fills alone do not prove cancellation of a partial remainder.
            terminal=('Filled','Cancelled','ApiCancelled','Rejected')
            if parent not in terminal or any(i not in o['commissions'] for i in o['fills']): return
            if any(c['currency']!='USD' or num(c['amount'])<0 for c in o['commissions'].values()):
                self.state['emergency']=True;return  # Foreign-currency fee conversion remains unresolved.
            known_gross=sum((num(e['quantity'])*num(e['price'])*(1 if e['side']=='SELL' else -1) for e in o['fills'].values()),Decimal(0))
            known_net=known_gross-sum((num(c['amount']) for c in o['commissions'].values()),Decimal(0))
            if -known_net>num(o['reserve']):self.state['emergency']=True
            if (o.get('initial_eur_uncertainty') or o.get('diagnostic_evidence_version')==2) and not o.get('post_eur_reconciled_at'):
                o['state']='AWAITING_POST_RECONCILIATION';return
            gross=sum((num(e['quantity'])*num(e['price'])*(1 if e['side']=='SELL' else -1) for e in o['fills'].values()),Decimal(0))
            fees=sum((num(c['amount']) for c in o['commissions'].values()),Decimal(0));net=gross-fees
            session=self.state['sessions'][o['session_id']]
            if o['category']=='PAPER_STRATEGY':
                # Settlement is delegated to the unchanged C# capital/risk rules, never the diagnostic ledger.
                updated=self.journal.strategy_settle(self.state['strategy_account'],net,fees,o['intent']) if self.experimental else self.journal.strategy_settle(self.state['strategy_account'],net,fees)
                self.state['strategy_account']=updated
                self.state['strategy_capital'].update(equity=str(updated['equity']),consumed_loss=str(updated['capital']['consumedLoss']))
            session['consumed_loss']=str(num(session['consumed_loss'])+max(0,-net));session['reserved']='0'
            if num(session['consumed_loss'])>=num(session['budget']) or -net>num(o['reserve']): self.state['emergency']=True
            o['state']='CLOSED'
            self.state['experiences'][o['intent']]={'category':o['category'],'simulated':True,'live_fee_verified':False,
                'instrument':'EUR/USD','timeframe':o['payload']['context'].get('timeframe'),'strategy_version':o['payload']['strategy_version'],'reason':'BOUNDED_EXECUTION_DIAGNOSTIC' if o['category']=='PAPER_DIAGNOSTIC' else 'RISK_APPROVED_STRATEGY_SIGNAL',
                'market':o['payload']['context'],'quote':o['quote'],'requested_price':o['entry'],'quantity':str(buys),
                'fills':copy.deepcopy(o['fills']),'commissions':copy.deepcopy(o['commissions']),'gross_usd':str(gross),'net_usd':str(net),
                'sent_at':o['sent_at'],'closed_at':stamp(self.clock()),'closing_reason':o.get('strategy_close_reason') or ('RECOVERY_CLOSE_ONLY' if o.get('recovery_order_ids') else 'TIME_LIMIT' if o['timeout_close_sent'] else 'STOP' if any(e['order_id']==o['order_ids'][2] for e in o['fills'].values()) else 'TAKE_PROFIT'),
                'research_exit_decision':copy.deepcopy(o.get('research_exit_decision')),
                'margin_before':o.get('margin_before'),'margin_after':o.get('margin_after'),'incidents':o['incidents'],
                'arrival_spread':str(num(o['quote']['ask'])-num(o['quote']['bid'])),
                'execution_differences':[{'exec_id':e['exec_id'],'difference':str(num(e['price'])-num(o['entry'] if e['side']=='BUY' else o.get('closing_quote',{}).get('bid',o['stop'] if e['order_id']==o['order_ids'][2] else o['target'])))} for e in o['fills'].values()],
                'economically_viable_with_100_usd':False,
                'initial_eur_uncertainty':copy.deepcopy(o.get('initial_eur_uncertainty')),'post_eur_reconciled_at':o.get('post_eur_reconciled_at')}
            if o['category']=='PAPER_STRATEGY':
                a=self.state['strategy_account'];continuation=a.get('paperContinuation',{})
                decision='CUMULATIVE_LOSS_LIMIT' if num(a['capital'].get('remainingLoss',20))<=0 else 'DAILY_FIRST_LOSS_STOP' if net<0 else 'DAILY_WIN_REQUIRED' if net==0 else 'WIN_TO_CONTINUE'
                self.state['experiences'][o['intent']].update(strategy_name=o['payload']['context'].get('strategy_name'),
                    signal_at=o['payload']['context'].get('signal_at'),indicators=o['payload']['context'].get('indicators'),
                    stop=o['stop'],target=o['target'],equity_after=str(a['equity']),
                    remaining_loss_after=str(a['capital'].get('remainingLoss',20)),continuation_decision=decision,
                    trading_day=continuation.get('day'),risk_profile=EXPERIMENTAL if self.experimental else 'PAPER_CONSERVATIVE')
                self.state['experiences'][o['intent']]['estimated_slippage_usd']=str(o.get('risk',{}).get('slippageCost',0))
            elif o.get('diagnostic_evidence_version')==2:
                from .paper_diagnostic_evidence import evidence
                self.state['experiences'][o['intent']]['execution_diagnostic']=evidence(o)
    def supervise(self):
        self.ingest(self.wire.drain())
        for o in self.state['orders'].values():
            if self.inventory(o)==0:self.wire.operation_deadline_at=None
            if o['state'] in ('CLOSED','REJECTED','CANCELLED_NO_FILL'):continue
            if o['state']=='AWAITING_POST_RECONCILIATION':
                try:snapshot=self.collect_snapshot();self.ingest(snapshot['events']);self.exposure(snapshot)
                except Exception:self.stop('POST_DIAGNOSTIC_RECONCILIATION_UNAVAILABLE');raise
                self.persist('POST_DIAGNOSTIC_RECONCILIATION');continue
            qty=self.inventory(o)
            if qty<0:
                self.stop('OVERSELL_DETECTED');raise PermissionError('OVERSELL_DETECTED')
            if o.get('diagnostic_evidence_version')==2:o['api_events']=copy.deepcopy(getattr(self.wire,'api_events',[]))
            if qty>0:
                self.wire.operation_deadline_at=o.get('close_deadline_at') if o.get('diagnostic_evidence_version')==2 and not o.get('timeout_close_sent') else None
                snapshot=self.collect_snapshot();self.ingest(snapshot['events']);self.exposure(snapshot)
                qty=self.inventory(o)
                if qty<=0:
                    self.wire.operation_deadline_at=None
                    continue  # An exit can arrive while collecting the broker snapshot.
                o['margin_after']=snapshot.get('initial_margin')
                elapsed=(self.clock()-date(o['sent_at'])).total_seconds()
                if o.get('diagnostic_evidence_version')==2:
                    o.setdefault('opening_snapshot',copy.deepcopy(snapshot))
                    elapsed=o['max_hold_seconds']-(date(o['close_deadline_at'])-self.clock()).total_seconds()
                if o['state']=='PARTIALLY_FILLED' and not o.get('cancel_parent_sent'):
                    self.check(management=True);o['cancel_parent_sent']=True;self.persist('CANCEL_PARENT_REMAINDER');self.wire.cancel_parent(o)
                self.protection(o,snapshot['orders'])
                exact=self.experimental and self.auth.read(management=True).get('strategy_plan',{}).get('exit_policy')=='RESEARCH_D_V1'
                # Begin preparation early enough for quote + strict broker reconciliation before the deadline.
                close_after=0 if o.get('diagnostic_evidence_version')==2 else o['max_hold_seconds']
                if not exact and elapsed>=close_after and not o['timeout_close_sent']:
                    a=self.check(management=True)
                    if o['statuses'].get(str(o['order_ids'][0])) not in ('Filled','Cancelled','ApiCancelled'):continue
                    quote=self.wire.quote();self.wire.validate_quote(quote)
                    # Market data collection can race with a protective fill: reconcile again before modifying a child.
                    snapshot=self.collect_snapshot();self.ingest(snapshot['events']);self.exposure(snapshot)
                    qty=self.inventory(o)
                    if qty<=0:
                        self.wire.operation_deadline_at=None
                        continue
                    if o.get('diagnostic_evidence_version')==2 and self.clock()>date(o['close_deadline_at']):
                        self.stop('DIAGNOSTIC_CLOSE_DEADLINE_EXPIRED');raise TimeoutError('DIAGNOSTIC_CLOSE_DEADLINE_EXPIRED')
                    self.protection(o,snapshot['orders']);self.wire.validate_quote(quote)
                    if not self.confirm_close_child(o,snapshot['orders']):
                        self.stop('CLOSE_CHILD_UNCONFIRMED');raise PermissionError('CLOSE_CHILD_UNCONFIRMED')
                    o['closing_quote']=quote
                    o['timeout_close_sent']=True;o['close_requested_at']=stamp(self.clock())
                    o['close_requested_price']=str(num(quote['bid'])//Decimal('0.00005')*Decimal('0.00005'))
                    o['close_requested_quantity']=str(qty);self.persist('OWNED_CLOSE_MODIFICATION_PENDING')
                    # Modify the existing TP in its OCA group; never send a naked SELL or cancel the stop.
                    self.wire.close_owned(o,qty,quote,a)
                    self.wire.operation_deadline_at=None
            elif (self.clock()-date(o['sent_at'])).total_seconds()>10 and not o.get('cancel_parent_sent') and o['statuses'].get(str(o['order_ids'][0])) not in ('Filled','Cancelled','ApiCancelled','Rejected'):
                snapshot=self.collect_snapshot();self.ingest(snapshot['events'])
                if snapshot['eur_cash'] is None:
                    if not self.reconcile_owned_prefill(snapshot,self.wire.additional_exposure()):
                        self.stop('EUR_CASH_RECONCILIATION_UNAVAILABLE');raise PermissionError('EUR_CASH_RECONCILIATION_UNAVAILABLE')
                else:self.exposure(snapshot)
                self.protection(o,snapshot['orders'])
                if self.inventory(o)>0:continue
                if not any(r['order_id']==o['order_ids'][0] and r.get('perm_id',0)>0 for r in snapshot['orders']):
                    self.stop('ACK_UNCONFIRMED_RECONCILE_REQUIRED');raise PermissionError('ACK_UNCONFIRMED_RECONCILE_REQUIRED')
                self.check(management=True);o['cancel_parent_sent']=True;self.persist('CANCEL_UNFILLED_ENTRY');self.wire.cancel_parent(o)
    @staticmethod
    def confirm_close_child(o,orders):
        already=sum((num(e['quantity']) for e in o['fills'].values() if e['order_id']==o['order_ids'][1]),Decimal(0))
        return any(r['order_id']==o['order_ids'][1] and r['status'] in ('Submitted','PreSubmitted') and
            r.get('side')=='SELL' and r.get('order_type')=='LMT' and r.get('client_id')==82 and r.get('contract_id')==12087792 and
            r.get('parent_id')==o['order_ids'][0] and r.get('reference')==o['intent'] and r.get('oca_group')==o['intent'] and
            r.get('oca_type')==2 and num(r['quantity'])-already==PaperLab.inventory(o) for r in orders)
    def research_close(self,o,decision):
        if o.get('strategy_close_sent') or self.inventory(o)<=0:return
        if not self.reconciled:self.connect_and_reconcile()
        a=self.check(management=True)
        if not self.experimental or a.get('strategy_plan',{}).get('exit_policy')!='RESEARCH_D_V1':
            raise PermissionError('RESEARCH_EXIT_PLAN_REQUIRED')
        if decision.get('exit') is not True or decision.get('reason') not in ('RULE_EXIT_NEXT_OPEN','STOP','TAKE_PROFIT','EMERGENCY_STOP','SESSION_STOPPED_OR_EXPIRED'):
            raise PermissionError('RESEARCH_EXIT_INVALID')
        quote=self.wire.quote();self.wire.validate_quote(quote)
        snapshot=self.wire.snapshot();self.ingest(snapshot['events']);self.exposure(snapshot)
        qty=self.inventory(o)
        if qty<=0:return
        self.protection(o,snapshot['orders']);self.wire.validate_quote(quote)
        if o['statuses'].get(str(o['order_ids'][0])) not in ('Filled','Cancelled','ApiCancelled'):return
        if not self.confirm_close_child(o,snapshot['orders']):
            self.stop('CLOSE_CHILD_UNCONFIRMED');raise PermissionError('CLOSE_CHILD_UNCONFIRMED')
        o.update(closing_quote=quote,strategy_close_sent=True,strategy_close_reason=decision['reason'],
                 research_exit_decision=copy.deepcopy(decision))
        self.persist('RESEARCH_EXIT_MODIFICATION_PENDING',decision)
        # Retain the stop/OCA protection; modify only this session's existing TP child.
        self.wire.close_owned(o,qty,quote,a)
    def review_flat(self,owner_review_guard=None):
        if self.state.get('unresolved_executions'):raise PermissionError('UNRECOGNIZED_EXECUTION_REVIEW_REQUIRED')
        if self.state.get('pending_commissions') or self.state.get('unavailable_commissions'):raise PermissionError('NOT_FLAT_OR_COSTS_UNRESOLVED')
        snapshot=self.connect_and_reconcile()
        if self.reconciliation_kind=='OWNED_PREFILL_EUR_ABSENCE':raise PermissionError('STRICT_FLAT_REVIEW_REQUIRED')
        if any(o.get('diagnostic_evidence_version')==2 and not o['fills'] and not o.get('cancellation_reconciled_at') for o in self.state['orders'].values()):raise PermissionError('BRACKET_CANCELLATION_UNCONFIRMED')
        if snapshot['orders'] or any(self.inventory(o)!=0 or o['state'] not in ('CLOSED','REJECTED','CANCELLED_NO_FILL') for o in self.state['orders'].values()):
            raise PermissionError('NOT_FLAT_OR_COSTS_UNRESOLVED')
        if owner_review_guard is not None:owner_review_guard()
        if self.reconciliation_kind=='INITIAL_EUR_ABSENCE_EXCEPTION':
            self.eur_exception.read(self.auth.read(management=True),for_review=self.exception_review)
            self.state['emergency']=False;self.persist('OWNER_INITIAL_UNCERTAINTY_REVIEW_CLEARED_EMERGENCY')
            return {'state':'INITIAL_BASELINE_EXCEPTION_REVIEWED','exception_id':self.state['initial_eur_absence']['record_id'],'eur_balance':None}
        self.state['emergency']=False;self.persist('OWNER_FLAT_REVIEW_CLEARED_EMERGENCY',{'environment':'PAPER_TRADING'})
        if getattr(self.wire,'session',None):self.wire.session.event('EMERGENCY_STOP_CLEARED',environment='PAPER_TRADING')
        return {'state':'FLAT_REVIEWED'}
