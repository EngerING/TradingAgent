"""Protected exploratory orchestration; commands never implicitly grant permits."""
import argparse
from contextlib import contextmanager
from copy import deepcopy
from datetime import timedelta
import hashlib
import json
import os
from pathlib import Path
import time
from uuid import uuid4
from .eurusd_exploratory import MODE,PROFILES,Rotator,Journal,now,N,sha,encoded,instant,TERMINAL
from .paper_lab import unseal,same_process,DotnetJournal,key
from .paper_lab_diagnostics import safe_reason
from .ibkr_session import AccountBinding,SessionConfiguration,ExecutionMode,session_guard
from .eurusd_shadow_research import ReadOnlyIdentity,MarketReader,feature_engine

FOLDER='artifacts/research/eurusd-exploratory'
ENGINE=('python/trading_agent/eurusd_exploratory.py','python/trading_agent/eurusd_exploratory_runner.py','python/trading_agent/eurusd_exploratory_wire.py','python/trading_agent/eurusd_exploratory_evidence.py')

def failure_summary(action,exc):
    # A transport failure may occur after transmission. Never report zero sends
    # for a mutation-capable command without first reconciling its durable intent.
    read_only_transport=action not in ('Run','Once','Recovery')
    return dict(state='BLOCKED',reason=safe_reason(exc),live_enabled=False,orders_sent=0 if read_only_transport else None,
                reconciliation_required=not read_only_transport)
def engine_hashes(root):return {p:hashlib.sha256((Path(root)/p).read_bytes()).hexdigest() for p in ENGINE}
def grant_path(root,cohort):return Path(root)/'.local'/('eurusd-exploratory-'+cohort+'.dpapi')
def save_protected(path,data):
    import ctypes
    from ctypes import wintypes
    class Blob(ctypes.Structure):_fields_=[('length',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_byte))]
    raw=encoded(data);buffer=ctypes.create_string_buffer(raw);source=Blob(len(raw),ctypes.cast(buffer,ctypes.POINTER(ctypes.c_byte)));out=Blob()
    if not ctypes.windll.crypt32.CryptProtectData(ctypes.byref(source),None,None,None,None,0,ctypes.byref(out)):raise PermissionError('PROTECTED_WRITE_FAILED')
    try:
        path.parent.mkdir(parents=True,exist_ok=True);temp=path.with_suffix('.tmp');temp.write_bytes(ctypes.string_at(out.data,out.length));temp.replace(path)
    finally:ctypes.windll.kernel32.LocalFree(out.data)

class Authorization:
    def __init__(self,root,cohort,loader=None,clock=now):
        self.root,self.cohort,self.clock=Path(root),cohort,clock;self.loader=loader or (lambda:unseal(grant_path(root,cohort)))
        self.recovery_context=False
    def read(self,management=False):
        a=deepcopy(self.loader());binding=AccountBinding.load_or_migrate(self.root);endpoint=SessionConfiguration.load(self.root)
        if os.environ.get('LIVE_TRADING','false').lower()!='false' or a.get('environment')!='PAPER_TRADING' or a.get('live_enabled') is not False:raise PermissionError('LIVE_DISABLED')
        if a.get('mode')!=MODE or a.get('scope')!=MODE or a.get('cohort')!=self.cohort or a.get('binding_id')!=binding.binding_id or a.get('account')!=binding.account:raise PermissionError('EXPLORATORY_BINDING_REQUIRED')
        endpoint.matches(a)
        if any(a.get(k) is not True for k in ('authorized','paper_checked','identity_manual_match','read_only_disabled_checked','forex_permission_checked','owned_reduce_only_management')) or a.get('client_id')!=82 or a.get('max_quantity')!='100' or a.get('max_notional_usd')!='100' or a.get('order_types')!=['LMT','STP'] or not same_process(a.get('tws_pid'),a.get('tws_start_filetime')):
            raise PermissionError('EXPLORATORY_GRANT_INVALID')
        start,end=instant(a['confirmed_at']),instant(a['expires_at'])
        if not start<=self.clock() or not start<end<=start+timedelta(hours=24):raise PermissionError('EXPLORATORY_GRANT_TIME_INVALID')
        if a.get('protocol_version')!=2 or a.get('single_use') is not True or a.get('max_openings')!=1 or a.get('profile') not in PROFILES or a.get('purpose') not in ('PAPER_EXECUTION_DIAGNOSTIC','PAPER_EXPLORATORY_RESEARCH') or end>start+timedelta(minutes=30):raise PermissionError('SUPERVISED_SINGLE_USE_GRANT_REQUIRED')
        # Revocation/expiry never grants a new entry. An explicitly preapproved
        # reduction can still manage the original inventory for 24h after expiry.
        if not management and (a.get('revoked') is not False or self.clock()>=end):raise PermissionError('EXPLORATORY_REVOKED_OR_EXPIRED')
        if management and self.clock()>=end+timedelta(hours=24):raise PermissionError('INDEPENDENT_RECOVERY_AUTHORIZATION_REQUIRED')
        if self.recovery_context:
            a.update(mode='RecoveryClose',scope='RECOVERY_CLOSE_ONLY') # SDK's existing close-only serialization capability; same new grant, never old authorization.
        return a

class ExploratoryReadIdentity(ReadOnlyIdentity):
    def __init__(self,root,client_id):super().__init__(root);self.client_id=client_id
    def read(self,management=False):
        a=super().read(management);a['client_id']=self.client_id;return a

class ExploratoryReader(MarketReader):
    """Separate read-only client; never displaces the original Shadow observer."""
    def __init__(self,root):
        from .paper_execution_wire import execution_wire
        self.root=Path(root);self.auth=ExploratoryReadIdentity(root,89);self.cached={};self.updated={};self.initialized=False
        def deny(**kw):raise PermissionError('EXPLORATORY_READER_NO_ORDERS')
        self.wire=execution_wire(self.auth,deny,read_only=True,session=session_guard(root,ExecutionMode.Research))
        a=self.auth.read(management=True);self.wire.connect(a);self.contract=self.wire.contract_details();self.calendar=self.wire.calendar()
        self.snapshot=self.wire.snapshot(diagnostic=True);self.capabilities=dict(identity='VERIFIED',permissions='UNKNOWN',protection='UNKNOWN',margin='UNKNOWN')

class RecoveryAuthorization(Authorization):
    def __init__(self,root,cohort,r):
        super().__init__(root,cohort,loader=lambda:unseal(Path(root)/'.local'/('eurusd-exploratory-recovery-'+cohort+'.dpapi')));self.r=r
    def read(self,management=False):
        if not management:raise PermissionError('RECOVERY_NEVER_OPENS_POSITION')
        a=deepcopy(self.loader());binding=AccountBinding.load_or_migrate(self.root);endpoint=SessionConfiguration.load(self.root);t=self.r.state['active']
        if os.environ.get('LIVE_TRADING','false').lower()!='false' or a.get('environment')!='PAPER_TRADING' or a.get('live_enabled') is not False:raise PermissionError('LIVE_DISABLED')
        if a.get('mode')!='EXPLORATORY_RECOVERY_CLOSE_ONLY' or a.get('cohort')!=self.cohort or a.get('binding_id')!=binding.binding_id or a.get('account')!=binding.account or not t or a.get('source_signature')!=sha(sorted((e for e in t['fills'].values() if e['side']=='BUY'),key=lambda e:e['exec_id'])) or a.get('source_intent')!=t['intent']:
            raise PermissionError('RECOVERY_SOURCE_BINDING_REQUIRED')
        endpoint.matches(a);start,end=instant(a['confirmed_at']),instant(a['expires_at'])
        if a.get('revoked') is not False or not start<=self.clock()<end<=start+timedelta(minutes=30) or not same_process(a['tws_pid'],a['tws_start_filetime']):raise PermissionError('RECOVERY_PERMIT_EXPIRED_OR_REVOKED')
        if not 0<=self.r.inventory(t)<=N(a['max_quantity'])<=N(100) or not a.get('single_use'):raise PermissionError('RECOVERY_REDUCE_ONLY_REQUIRED')
        if self.recovery_context:a.update(mode='RecoveryClose',scope='RECOVERY_CLOSE_ONLY')
        return a

@contextmanager
def account_lock(root):
    import msvcrt
    path=Path(root)/'.local/paper-lab.run.lock';path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a+b') as stream:
        stream.seek(0);stream.write(b'0');stream.flush();stream.seek(0);msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
        try:yield
        finally:stream.seek(0);msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)

def legacy_state(root,binding):
    h=DotnetJournal(root).load(key(binding.account));s=h.get('state') or {}
    pending=[o for o in s.get('orders',{}).values() if o.get('state') not in ('CLOSED','CANCELLED_NO_FILL','REJECTED')]
    settled=not pending and not s.get('pending_commissions') and not s.get('unavailable_commissions') and not s.get('unresolved_executions') and all(N(v.get('reserved',0))==0 for v in s.get('sessions',{}).values())
    history=[]
    for o in s.get('orders',{}).values():
        fills=list(o.get('fills',{}).values());inventory=sum((N(f['quantity'])*(1 if f['side']=='BUY' else -1) for f in fills),N(0))
        history.append(dict(intent=o.get('intent'),state=o.get('state'),order_ids=o.get('order_ids'),recovery_order_ids=o.get('recovery_order_ids'),
            perm_ids=o.get('perm_ids'),statuses=o.get('statuses'),inventory=str(inventory),incident_flags=o.get('incidents',[]),
            gross_pnl=str(sum((N(f['quantity'])*N(f['price'])*(1 if f['side']=='SELL' else -1) for f in fills),N(0))) if inventory==0 else None,
            commissions=o.get('commissions'),fills=fills))
    return dict(revision=h['revision'],emergency=s.get('emergency',True),settled=settled,historical_orders=history,
                pending_intents=len(pending),pending_commissions=len(s.get('pending_commissions',{})),
                reservation=str(sum((N(v.get('reserved',0)) for v in s.get('sessions',{}).values()),N(0))),
                incident='HISTORICAL_EUR_INCIDENT_REQUIRES_HUMAN_REVIEW_OF_JOURNAL_AND_PAPER_PENDING_BRACKET_REPORT',
                cause_report='docs/architecture/paper-pending-bracket-recovery.md')

def inspect(root,r):
    """Fresh identity/snapshots/contract/calendar/quotes only. Zero placeOrder/What-If."""
    from .paper_execution_wire import execution_wire
    root=Path(root);auth=ExploratoryReadIdentity(root,90);binding=auth.binding;legacy=legacy_state(root,binding)
    def deny(**kw):raise PermissionError('INSPECT_NO_ORDERS')
    wire=execution_wire(auth,deny,read_only=True,session=session_guard(root,ExecutionMode.Research))
    result=dict(cohort=r.journal.cohort,at=now().isoformat(),binding_id=binding.binding_id,orders_sent=0,live_enabled=False,
                legacy=legacy,emergency=legacy['emergency'] or (root/'.local/paper-lab.emergency').exists(),evidence={},sizes={})
    try:
        a=auth.read(management=True);wire.connect(a);contract=wire.contract_details();calendar=wire.calendar()
        snap=wire.snapshot(diagnostic=True);additional=wire.additional_exposure();quote=wire.observe_quote();r.ingest(snap['events'],quote)
        reconciled=r.reconcile({**snap,'events':[]},additional)
        from .eurusd_exploratory_wire import capability_summary
        funds=capability_summary(wire)
        e=dict(identity='VERIFIED' if wire.connected else 'UNKNOWN',account_reconciled='VERIFIED' if reconciled and wire.connected else 'UNKNOWN',
            positions_flat='VERIFIED' if not any(N(x['quantity'])!=0 for x in snap['positions']) else 'UNKNOWN',
            orders_clear='VERIFIED' if not snap['orders'] else 'UNKNOWN',journal_reconciled='VERIFIED' if legacy['settled'] else 'UNKNOWN',
            permissions='UNKNOWN',margin='UNKNOWN',settled_funds='UNKNOWN',minimum_size='UNKNOWN',fees_bounded='UNKNOWN',
            protection='UNKNOWN',calendar='VERIFIED' if quote.get('market_status')=='OPEN' else 'UNKNOWN',
            old_incident_resolved='VERIFIED' if legacy['settled'] else 'UNKNOWN')
        settled=[x for x in funds['rows'] if x['tag']=='SettledCash' and x['currency']=='USD']
        if funds['status']=='COMPLETE' and settled and len({x['value'] for x in settled})==1 and N(settled[0]['value'])>=0:
            e.update(settled_funds='VERIFIED',settled_usd=settled[0]['value'])
        rows=[x for x in wire.account_rows if x['tag'] in ('SettledCash','AvailableFunds','InitMarginReq','BuyingPower','AccountType')]
        signal=deepcopy(r.state['protocol'].get('reference_signal'))
        if signal and quote.get('bid') and quote.get('ask'):
            signal['entry_midpoint']=str((N(quote['bid'])+N(quote['ask']))/2)
            result['sizes']={p:r.size(p,signal,quote) for p in PROFILES}
        result.update(evidence=e,quote=quote,contract=contract,calendar=calendar,account_observations=rows,capability_summary=funds,
            snapshot=dict(positions=snap['positions'],orders=snap['orders'],cash_reconciliation=snap['cash_reconciliation']),
            numeric_geometry='AUTHENTIC_HISTORICAL_TREND_SIGNAL_REPRICED_FOR_FEASIBILITY_ONLY_NOT_A_CURRENT_SIGNAL',reference_signal=signal,process=auth.process,
            capabilities_note='Contract minSize/orderTypes are declared, not effective permissions, margin or protection acceptance.')
        for p in PROFILES:
            r.state['profiles'][p]['blockers']=[*(['EMERGENCY_STOP_ACTIVE'] if result['emergency'] else []),
                'PAPER_EXPLORATORY_AUTHORIZATION_REQUIRED',*[k.upper()+'_UNVERIFIED' for k,v in e.items() if v!='VERIFIED'],
                *([result['sizes'][p]['reason']] if result['sizes'].get(p,{}).get('reason') else [])]
        r.state['last_quote']=quote;r.state['last_inspect']=dict(at=result['at'],evidence=e,sizes=result['sizes'],emergency=result['emergency'])
        r.append('READ_ONLY_INSPECT',result)
    except Exception as exc:
        result['reason']=safe_reason(exc);result['diagnostics']=wire.read_diagnostics();r.append('READ_ONLY_INSPECT_UNAVAILABLE',result)
    finally:wire.disconnect()
    folder=root/FOLDER/r.journal.cohort;folder.mkdir(parents=True,exist_ok=True)
    path=folder/('inspect-'+uuid4().hex+'.json');path.write_bytes(encoded(result));result['artifact']=str(path.relative_to(root));return result

class Service:
    def __init__(self,root,r,auth):
        from .eurusd_exploratory_wire import exploratory_wire
        self.root,self.r,self.auth=Path(root),r,auth;self.certificate=None;self.attempted=set()
        self.wire=exploratory_wire(auth,self.gate,self.guard,session_guard(root,ExecutionMode.PaperAuto))
        # The new adapter permits cancellations only for this cohort's persisted
        # exact orders after fresh reconciliation, never global or foreign ones.
        self.wire.guard_cancel=self.cancel_guard
    def suspend(self,reason):
        self.r.fail(reason)
        stop=self.root/'.local/paper-lab.emergency'
        if not stop.exists():stop.write_text(now().isoformat(),encoding='utf-8')
        binding=AccountBinding.load_or_migrate(self.root);j=DotnetJournal(self.root);h=j.load(key(binding.account))
        if h.get('state') and not h['state'].get('emergency'):
            state=h['state'];state['emergency']=True;j.commit(key(binding.account),h['revision'],state,dict(event='EXPLORATORY_INCIDENT_EMERGENCY',at=now().isoformat(),data=dict(cohort=self.r.journal.cohort,reason=reason,live_enabled=False)))
    def gate(self,management=False):
        a=self.auth.read(management=management)
        if a['protocol_hash']!=sha(self.r.state['protocol']) or engine_hashes(self.root)!=self.r.state['protocol']['engine_hashes']:raise PermissionError('COHORT_PROTOCOL_CHANGED')
        if not self.certificate or not self.wire.connected or not 0<=(now()-instant(self.certificate['at'])).total_seconds()<=5:raise PermissionError('FRESH_RECONCILIATION_REQUIRED')
        if not management:
            if (self.root/'.local/paper-lab.emergency').exists() or (self.root/'.local'/('eurusd-exploratory-'+self.r.journal.cohort+'.stop')).exists() or self.r.state['global_stop']:raise PermissionError('EXPLORATORY_STOPPED')
            if not self.r.state.get('emergency_review') or self.r.state['emergency_review']['authorization_id']!=a['session_id']:raise PermissionError('PROTECTED_EMERGENCY_REVIEW_REQUIRED')
            if legacy_state(self.root,AccountBinding.load_or_migrate(self.root))['emergency']:raise PermissionError('LEGACY_EMERGENCY_ACTIVE')
            if a.get('profile')!=PROFILES[self.r.state['rotation']] or a.get('purpose')!=self.r.state['protocol']['purpose']:raise PermissionError('PROFILE_SCOPED_AUTHORIZATION_REQUIRED')
        return a
    def guard(self,*args):self.gate(management=args[1] not in ('BRACKET_ENTRY','BRACKET_PROTECTION'));self.r.authorize_transport(*args)
    def cancel_guard(self,order_id):
        a=self.gate(management=True);self.wire.assert_mutation_allowed(a,management=True)
        t=self.r.state['active'];h=self.r.journal.load()
        if not t or order_id not in t['order_ids'] or order_id not in t['cancellations'] or h['revision']!=self.r.revision or h['hash']!=self.r.head:raise PermissionError('FOREIGN_OR_UNPERSISTED_CANCEL')
        row=next((x for x in self.certificate['orders'] if x['order_id']==order_id),None)
        if not row or row.get('perm_id',0)<=0 or row.get('reference')!=t['intent'] or row.get('client_id')!=82 or row.get('contract_id')!=12087792:raise PermissionError('CANCEL_BROKER_ACK_RECONCILE_REQUIRED')
        token=('CANCEL',order_id)
        if token in self.attempted:raise PermissionError('CANCEL_ALREADY_ATTEMPTED_RECONCILE_REQUIRED')
        self.attempted.add(token)
    def poll(self):
        self.certificate=None
        a=self.auth.read(management=True);self.wire.connect(a)
        marker=self.r.revision
        quote=self.wire.observe_quote();self.r.state['last_quote']=quote
        self.r.state['quote_history']=[*self.r.state.get('quote_history',[]),quote][-512:]
        snap=self.wire.snapshot(diagnostic=True);self.r.ingest(snap['events'],quote);additional=self.wire.additional_exposure();self.r.ingest(self.wire.drain(),quote)
        result=self.r.reconcile({**snap,'events':[]},additional)
        # Reconciliation failures never certify a mutation, even for recovery.
        last=self.r.state.get('last_reconciliation')
        if last and self.r.revision>marker and 0<=(now()-instant(last['at'])).total_seconds()<=5:
            self.certificate=deepcopy(last)
        return result,quote
    def reduce(self,recovery=False):
        from ibapi.order_cancel import OrderCancel
        self.poll();t=self.r.state['active']
        if not t:return dict(result='ALREADY_FLAT',orders_sent=0)
        if not self.certificate:raise PermissionError('RECOVERY_RECONCILIATION_REQUIRED')
        # Cancel parent before reducing a partial. Broker acknowledgement and
        # reconciled terminal children precede a standalone IOC close.
        if recovery:
            for row in list(self.certificate['orders']):
                oid=row['order_id']
                if oid in t['cancellations']:continue
                t['cancellations'].append(oid);self.r.append('OWNED_CANCEL_PENDING',dict(order_id=oid));self.wire.client.cancelOrder(oid,OrderCancel())
                return dict(result='CANCEL_ACK_RECONCILE_REQUIRED')
            if any(t['statuses'].get(str(i)) not in TERMINAL or t['completed'].get(str(i),{}).get('perm_id',0)<=0 or t['completed'].get(str(i),{}).get('status') not in TERMINAL for i in t['order_ids']):raise PermissionError('RECOVERY_CHILDREN_TERMINAL_REQUIRED')
            q=self.r.inventory(t)
            if q<=0:return dict(result='FLAT_WAITING_FEES')
            grant=self.auth.read(management=True)
            if any(rec['authorization_id']==grant['session_id'] for rec in t['recovery_orders'].values()):return dict(result='RECOVERY_ALREADY_ATTEMPTED_RECONCILE_REQUIRED')
            if any(t['completed'].get(oid,{}).get('status') not in TERMINAL or t['completed'].get(oid,{}).get('perm_id',0)<=0 for oid in t['recovery_orders']):raise PermissionError('PRIOR_RECOVERY_UNCERTAIN_RECONCILE_REQUIRED')
            quote=self.wire.quote();self.gate(management=True);oid=self.wire.next_order_id
            record=dict(authorization_id=self.auth.read(management=True)['session_id'],intent=t['intent'],order_id=oid,
                reference='RECOVERY-'+t['trial_id'][:32],quantity=str(q),price=str((N(quote['bid'])/N('0.00005')).to_integral_value(rounding='ROUND_FLOOR')*N('0.00005')),quote=quote,
                source_perm_ids=sorted({x['perm_id'] for x in t['fills'].values() if x['side']=='BUY'}))
            t['recovery_orders'][str(oid)]=record;self.r.append('OWNED_RECOVERY_SEND_PENDING',record)
            self.auth.recovery_context=True
            try:self.wire.recovery_close(record,self.auth.read(management=True))
            finally:self.auth.recovery_context=False
            return dict(result='RECOVERY_SENT_RECONCILE_REQUIRED')
        if t['close_attempted']:return dict(result='CLOSE_ALREADY_ATTEMPTED_RECONCILE_REQUIRED')
        if t['statuses'].get(str(t['order_ids'][0])) not in TERMINAL:raise PermissionError('PARENT_REMAINDER_UNRESOLVED')
        quote=self.wire.quote();t.update(close_attempted=True,closing_quote=quote);self.r.append('OWNED_RULE_EXIT_PENDING')
        self.wire.close_owned(t,self.r.inventory(t),quote,self.auth.read(management=True));return dict(result='OWNED_RULE_EXIT_SENT')

def prepare(root,purpose='PAPER_EXPLORATORY_RESEARCH'):
    from .progressive_risk_research import authentic_inputs,cost_evidence
    analysis,ids,provenance=authentic_inputs(root);costs,_=cost_evidence(root,provenance)
    reference=next((deepcopy(s) for s in reversed(analysis['candidates']) if s['strategy_id']=='trend' and s['side']=='BUY' and not s['reasons']),None)
    cohort='eurusd-explore-'+uuid4().hex;r=Rotator(Journal(root,cohort));binding=AccountBinding.load_or_migrate(root)
    return r.prepare(ids['trend'],costs,provenance,binding.binding_id,engine_hashes(root),reference,purpose)

def run(root,r,once=False,recovery=False):
    if recovery and not r.state['active']:return dict(result='ALREADY_FLAT_NO_ORDER',**r.status())
    recovery_path=Path(root)/'.local'/('eurusd-exploratory-recovery-'+r.journal.cohort+'.dpapi')
    auth=RecoveryAuthorization(root,r.journal.cohort,r) if recovery and recovery_path.exists() else Authorization(root,r.journal.cohort)
    service=Service(root,r,auth);reader=None
    try:
        auth.read(management=recovery)
        if not recovery:reader=ExploratoryReader(root)
        while True:
            try:
                settled,quote=service.poll();t=r.state['active'];stop=(Path(root)/'.local'/('eurusd-exploratory-'+r.journal.cohort+'.stop')).exists()
                if t:
                    expired=False
                    try:auth.read()
                    except PermissionError:expired=True
                    protection_timeout=t['fills'] and not t['protection_confirmed'] and (now()-instant(t['first_fill_received_at'])).total_seconds()>=10
                    if stop or expired or r.state['global_stop'] or protection_timeout or recovery:
                        service.suspend(r.state['global_stop'] or 'RECOVERY_REQUIRED');service.reduce(recovery=True)
                    elif t.get('purpose')=='PAPER_EXECUTION_DIAGNOSTIC' and t['entry_at'] and (now()-instant(t['entry_at'])).total_seconds()>=r.state['protocol']['diagnostic_close_seconds']:
                        service.reduce()
                    elif reader and t['entry_at'] and t['protection_confirmed']:
                        observation=reader.observe();analysis=observation['analysis']
                        r.mark_twins(analysis,observation['at'])
                        # Original contrarian EMA/context exits execute at the next observed opening.
                        exits=[e for e in analysis['exit_signals'] if e['strategy_id']=='trend' and e['side']=='BUY' and instant(t['entry_at'])<instant(e['at'])<=now()]
                        if exits:service.reduce()
                elif stop or recovery:return r.status()
                elif r.state.get('opening_attempts',0)>=r.state['protocol'].get('max_openings',1):
                    r.state['status']='SUPERVISED_TRIAL_FINISHED_NEW_APPROVAL_REQUIRED';r.append('SUPERVISED_TRIAL_FINISHED');return r.status()
                elif reader:
                    o=reader.observe();analysis=o['analysis'];features=feature_engine(analysis,o['quote'],o['at'])
                    s=next((deepcopy(x) for x in reversed(analysis['candidates']) if x['strategy_id']=='trend' and 0<=(now()-instant(x['signal_at'])).total_seconds()<=5),None)
                    if r.state['protocol'].get('purpose')=='PAPER_EXECUTION_DIAGNOSTIC':
                        s=deepcopy(r.state['protocol']['reference_signal']);s.update(side='BUY',reasons=[],signal_at=o['at'],execution_purpose='PAPER_EXECUTION_DIAGNOSTIC',predictive_validation=False)
                    r.state['features']=features
                    if s:
                        s.update(strategy_version=r.state['protocol']['strategy']['strategy_version'],entry_at=s['signal_at'],regime=features['regime'],
                            entry_midpoint=str((N(o['quote']['bid'])+N(o['quote']['ask']))/2),
                            opportunity_id=sha([r.journal.cohort,s['signal_at'],s['side']]),probability=None,probability_status='INSUFFICIENT_EVIDENCE_NO_SUBJECTIVE_CONFIDENCE')
                        # The closed signal bar is available; execution is at the next observed opening, not a fabricated backtest fill.
                        s['reasons']=[x for x in s['reasons'] if x!='NO_NEXT_CLOSED_BAR']
                        from .eurusd_exploratory_evidence import observer_context
                        s['kronos']=observer_context(root,s['signal_at'])
                        a=auth.read();service.gate();e=deepcopy(a['capabilities']);e.update(account_reconciled='VERIFIED',positions_flat='VERIFIED',orders_clear='VERIFIED',journal_reconciled='VERIFIED')
                        r.begin(s,o['quote'],e,a,False,service.wire.next_order_id,service.wire.bracket)
                    else:r.append('NO_NEW_ORIGINAL_SIGNAL',dict(quote=o['quote'],features=features))
                if once:return r.status()
                time.sleep(5)
            except Exception as exc:
                service.suspend(safe_reason(exc))
                # Broker-uncertain recovery cannot issue an order; keep recording
                # and retry READS only. No new entry after any incident.
                if once or recovery:raise
                time.sleep(5)
    finally:
        if reader:reader.close()
        service.wire.disconnect()

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['Prepare','Inspect','Assess','RecoveryInspect','Status','Run','Once','Recovery','Authorize','AuthorizeRecovery','Revoke','Stop','ReviewEmergency']);p.add_argument('--root',required=True);p.add_argument('--cohort');p.add_argument('--evidence');p.add_argument('--profile',choices=PROFILES);p.add_argument('--purpose',choices=['PAPER_EXECUTION_DIAGNOSTIC','PAPER_EXPLORATORY_RESEARCH'],default='PAPER_EXPLORATORY_RESEARCH');p.add_argument('--minutes',type=int,default=30);p.add_argument('--confirmed',action='store_true');args=p.parse_args();root=Path(args.root)
    try:
        if args.action=='Prepare':result=prepare(root,args.purpose)
        else:
            r=Rotator(Journal(root,args.cohort))
            if not r.state:raise PermissionError('COHORT_NOT_PREPARED')
            if args.action=='Status':result=r.status()
            elif args.action=='Stop':
                path=root/'.local'/('eurusd-exploratory-'+args.cohort+'.stop');path.write_text(now().isoformat());r.fail('OPERATOR_STOP');result=r.status()
            elif args.action=='Revoke':
                for path in (grant_path(root,args.cohort),root/'.local'/('eurusd-exploratory-recovery-'+args.cohort+'.dpapi')):
                    if path.exists():
                        a=unseal(path);a['revoked']=True;save_protected(path,a);r.append('AUTHORIZATION_REVOKED',dict(session_id=a['session_id']))
                r.state['authorization']=dict(status='REVOKED',expires_at=r.state.get('authorization',{}).get('expires_at'));r.append('AUTHORIZATION_STATE_REVOKED')
                result=r.status()
            elif args.action in ('Inspect','Assess','RecoveryInspect','Run','Once','Recovery'):
                with account_lock(root):
                    result=inspect(root,r) if args.action in ('Inspect','Assess','RecoveryInspect') else run(root,r,args.action=='Once',args.action=='Recovery')
                    if args.action=='Assess' and result.get('reference_signal') and result.get('quote'):
                        signal=result['reference_signal'];signal['opportunity_id']='ASSESS-'+result['at'];r.select_profile(signal,result['quote'])
                        result.update(next_profile=PROFILES[r.state['rotation']],eligibility={p:r.state['profiles'][p].get('eligibility','UNKNOWN') for p in PROFILES},assessment_only=True)
            elif args.action=='AuthorizeRecovery':
                if not args.confirmed or not 1<=args.minutes<=30:raise PermissionError('LOCAL_RECOVERY_CONFIRMATION_REQUIRED')
                with account_lock(root):
                    observation=inspect(root,r);t=r.state['active'];cert=r.state.get('last_reconciliation')
                    if not t or not cert or not 0<=(now()-instant(cert['at'])).total_seconds()<=30 or r.inventory(t)<=0 or not any(e['side']=='BUY' and e['perm_id']>0 for e in t['fills'].values()):raise PermissionError('EXACT_OWNED_RECOVERY_POSITION_REQUIRED')
                    binding=AccountBinding.load_or_migrate(root);endpoint=SessionConfiguration.load(root);start=now()
                    a=dict(mode='EXPLORATORY_RECOVERY_CLOSE_ONLY',scope='RECOVERY_CLOSE_ONLY',cohort=args.cohort,environment='PAPER_TRADING',live_enabled=False,binding_id=binding.binding_id,account=binding.account,
                        authorized=True,revoked=False,single_use=True,session_id=uuid4().hex,confirmed_at=start.isoformat(),expires_at=(start+timedelta(minutes=args.minutes)).isoformat(),
                        source_intent=t['intent'],source_signature=sha(sorted((e for e in t['fills'].values() if e['side']=='BUY'),key=lambda e:e['exec_id'])),paper_checked=True,identity_manual_match=True,read_only_disabled_checked=True,
                        client_id=82,max_quantity=str(r.inventory(t)),order_types=['LMT','STP'],host=endpoint.host,port=endpoint.port,tws_pid=observation['process']['pid'],tws_start_filetime=observation['process']['started'],protocol_hash=sha(r.state['protocol']))
                    r.append('SINGLE_USE_RECOVERY_AUTHORIZATION',dict(session_id=a['session_id'],source_signature=a['source_signature'],quantity=a['max_quantity'],emergency_retained=True))
                    save_protected(root/'.local'/('eurusd-exploratory-recovery-'+args.cohort+'.dpapi'),a);result=dict(cohort=args.cohort,quantity_to_reduce=a['max_quantity'],new_entry_authorized=False,emergency_retained=True)
            elif args.action=='Authorize':
                if not args.confirmed or not 1<=args.minutes<=30 or not args.evidence or not args.profile:raise PermissionError('LOCAL_EXPLICIT_SINGLE_USE_PROFILE_CONFIRMATION_REQUIRED')
                with account_lock(root):
                    observation=inspect(root,r);operator=json.loads(Path(args.evidence).read_bytes())
                    from .eurusd_exploratory_evidence import verify_operator_evidence
                    e=verify_operator_evidence(root,operator,r,observation,args.profile)
                    if r.state['active'] or not observation['legacy']['settled'] or any(e[k]!='VERIFIED' for k in ('identity','account_reconciled','positions_flat','orders_clear','journal_reconciled','calendar')):raise PermissionError('FRESH_FLAT_RECONCILIATION_REQUIRED')
                    if r.state.get('opening_attempts',0):raise PermissionError('SUPERVISED_TRIAL_CONSUMED_NEW_COHORT_REQUIRED')
                    r.select_profile(dict(observation['reference_signal'],opportunity_id='AUTHORIZE-'+observation['at']),observation['quote'])
                    if args.profile!=PROFILES[r.state['rotation']]:raise PermissionError('ROTATION_PROFILE_REVIEW_REQUIRED')
                    binding=AccountBinding.load_or_migrate(root);endpoint=SessionConfiguration.load(root);start=now();session=uuid4().hex
                    a=dict(mode=MODE,scope=MODE,cohort=args.cohort,environment='PAPER_TRADING',live_enabled=False,binding_id=binding.binding_id,account=binding.account,
                        authorized=True,revoked=False,session_id=session,confirmed_at=start.isoformat(),expires_at=(start+timedelta(minutes=args.minutes)).isoformat(),
                        paper_checked=True,identity_manual_match=True,read_only_disabled_checked=True,forex_permission_checked=True,owned_reduce_only_management=True,
                        client_id=82,max_quantity='100',max_notional_usd='100',order_types=['LMT','STP'],host=endpoint.host,port=endpoint.port,
                        tws_pid=observation['process']['pid'],tws_start_filetime=observation['process']['started'],protocol_hash=sha(r.state['protocol']),capabilities=e,
                        protocol_version=2,single_use=True,max_openings=1,profile=args.profile,purpose=r.state['protocol']['purpose'])
                    r.append('EXPLICIT_AUTHORIZATION_PREPARED',dict(session_id=session,evidence_sha=sha(operator),expires_at=a['expires_at']))
                    save_protected(grant_path(root,args.cohort),a)
                    r.state['authorization']=dict(status='REGISTERED_NOT_READY',session_id=session,profile=args.profile,expires_at=a['expires_at'],single_use=True)
                    r.append('SINGLE_USE_AUTHORIZATION_REGISTERED');result=dict(cohort=args.cohort,authorized=True,emergency_unchanged=True,live_enabled=False)
            elif args.action=='ReviewEmergency':
                if not args.confirmed:raise PermissionError('LOCAL_EXPLICIT_EMERGENCY_REVIEW_REQUIRED')
                with account_lock(root):
                    auth=Authorization(root,args.cohort);a=auth.read();observation=inspect(root,r)
                    if r.state['active'] or not observation['legacy']['settled'] or observation['evidence'].get('account_reconciled')!='VERIFIED' or observation['evidence'].get('orders_clear')!='VERIFIED' or observation['evidence'].get('positions_flat')!='VERIFIED':raise PermissionError('EMERGENCY_REVIEW_FRESH_FLAT_REQUIRED')
                    binding=AccountBinding.load_or_migrate(root);journal=DotnetJournal(root);h=journal.load(key(binding.account));state=h['state']
                    if not state or state.get('pending_commissions') or any(N(v.get('reserved',0))!=0 for v in state.get('sessions',{}).values()):raise PermissionError('LEGACY_JOURNAL_REVIEW_REQUIRED')
                    review=dict(authorization_id=a['session_id'],cohort=args.cohort,protocol_hash=a['protocol_hash'],at=now().isoformat(),
                        historical_cause=observation['legacy']['incident'],inspection_artifact=observation['artifact'],operator_confirmed=True,scope=MODE,live_enabled=False)
                    # Separate protected local confirmation; no old grant is read,
                    # renewed or made valid by this narrowly scoped Paper review.
                    r.state['emergency_review']=review;r.state['global_stop']=None;r.append('EXPLICIT_PAPER_EMERGENCY_REVIEW',review)
                    state['emergency']=False;journal.commit(key(binding.account),h['revision'],state,dict(event='EXPLICIT_EXPLORATORY_PAPER_REVIEW',at=now().isoformat(),data=review))
                    stop=root/'.local/paper-lab.emergency'
                    if stop.exists():stop.unlink()
                    result=dict(cohort=args.cohort,review=review,live_enabled=False)
        print(json.dumps(result,allow_nan=False))
    except Exception as exc:print(json.dumps(failure_summary(args.action,exc)));raise SystemExit(1)

if __name__=='__main__':main()
