"""Independent, owner-authorized, single-use reduction of confirmed Paper inventory."""
import argparse
import copy
import hashlib
import json
import os
import re
import time
from datetime import timedelta
from decimal import Decimal, ROUND_FLOOR
from pathlib import Path
from .paper_lab import PaperLab,DotnetJournal,num,date,stamp,utc,same_process,unseal,encoded
from .paper_lab_diagnostics import InspectionAuthorization,safe_reason
from .paper_execution_wire import execution_wire

MODE='RecoveryClose'
SCOPE='RECOVERY_CLOSE_ONLY'
TERMINAL={'Filled','Cancelled','Rejected'}

class RecoveryAuthorization:
    def __init__(self,loader,session_alive=same_process,clock=utc,endpoint=None):
        self.loader,self.session_alive,self.clock=loader,session_alive,clock
        from .ibkr_session import SessionConfiguration
        self.endpoint=endpoint or SessionConfiguration()
    def read(self,management=False):
        a=self.loader();now=self.clock()
        if os.environ.get('LIVE_TRADING','false').lower()!='false' or a.get('environment')!='PAPER_TRADING' or a.get('live_enabled') is not False:
            raise PermissionError('LIVE_DISABLED')
        if (a.get('schema_version')!=1 or a.get('mode')!=MODE or a.get('scope')!=SCOPE or a.get('authorized') is not True or
            any(a.get(k) is not True for k in ('paper_checked','identity_manual_match','read_only_disabled_checked','forex_permission_checked','single_use','emergency_retained'))):
            raise PermissionError('RECOVERY_AUTHORIZATION_REQUIRED')
        self.endpoint.matches(a)
        if (not re.fullmatch(r'DU(?:R)?[0-9]+',a.get('account','')) or a.get('client_id')!=82 or
            not self.session_alive(a.get('tws_pid'),a.get('tws_start_filetime'))):raise PermissionError('UNVERIFIED_PAPER_SESSION')
        if (a.get('contract_id')!=12087792 or a.get('instrument')!='EUR/USD CASH IDEALPRO' or a.get('side')!='SELL' or
            a.get('order_types')!=['LMT'] or a.get('tif')!='IOC' or a.get('revoked') is not False or
            not re.fullmatch(r'[a-f0-9]{32}',a.get('session_id','')) or not re.fullmatch(r'[a-f0-9]{64}',a.get('intent','')) or
            not re.fullmatch(r'[a-f0-9]{64}',a.get('source_signature','')) or not isinstance(a.get('opening_order_id'),int) or
            not isinstance(a.get('opening_perm_id'),int) or a['opening_perm_id']<=0 or
            not 0<num(a.get('max_quantity',0))<=num(a.get('opening_quantity',0))<=100):raise PermissionError('RECOVERY_SCOPE_INVALID')
        start,end=date(a['confirmed_at']),date(a['expires_at'])
        if not start<=now<end<=start+timedelta(minutes=30):raise PermissionError('RECOVERY_AUTHORIZATION_EXPIRED')
        return a

class RecoveryClose:
    def __init__(self,auth,journal,wire,*,intent=None,clock=utc,stop_file=None):
        self.auth,self.journal,self.wire,self.clock=auth,journal,wire,clock
        self.lab=PaperLab(auth,journal,wire,clock=clock,stop_file=stop_file)
        self.lab.state['emergency']=True;self.lab.persist('RECOVERY_CLOSE_START_EMERGENCY_RETAINED')
        a=auth.read(management=True);self.grant_id=a['session_id']
        candidates=[o for o in self.lab.state['orders'].values() if o['category']=='PAPER_DIAGNOSTIC']
        chosen=intent or a.get('intent')
        candidates=[o for o in candidates if not chosen or o['intent']==chosen]
        if len(candidates)!=1:raise PermissionError('RECOVERY_SOURCE_AMBIGUOUS')
        self.o=candidates[0];self.certificate=None
    def source(self):
        o=self.o;buys=[e for e in o['fills'].values() if e['side']=='BUY']
        if (o.get('contract_id')!=12087792 or o.get('client_id')!=82 or not buys or
            any(e['order_id']!=o['order_ids'][0] or e['client_id']!=82 or e['contract_id']!=12087792 or e['perm_id']<=0 for e in buys) or
            len({e['perm_id'] for e in buys})!=1):raise PermissionError('RECOVERY_OPENING_FILL_UNVERIFIED')
        quantity=sum((num(e['quantity']) for e in buys),num(0))
        if not 0<quantity<=100 or quantity>num(o['quantity']):raise PermissionError('RECOVERY_OPENING_QUANTITY_INVALID')
        signature=hashlib.sha256(encoded(sorted([{k:e[k] for k in ('exec_id','order_id','perm_id','client_id','contract_id','side','quantity','price')} for e in buys],key=lambda e:e['exec_id'])).encode()).hexdigest()
        return {'intent':o['intent'],'opening_order_id':o['order_ids'][0],'opening_perm_id':buys[0]['perm_id'],
            'opening_quantity':str(quantity),'source_signature':signature,'opening_exec_ids':sorted(e['exec_id'] for e in buys)}
    def ingest(self,events):
        owned=set(self.o['order_ids']+self.o.get('recovery_order_ids',[]))
        failure=None
        for e in events:
            if e['kind'] in ('disconnect','readonly'):failure='RECOVERY_BROKER_UNAVAILABLE'
            if e['kind']=='open_order' and e['order_id'] not in owned and e['status'] not in TERMINAL:
                failure='RECOVERY_UNKNOWN_ORDER'
        # Preserve executions/fees even if the same callback batch also suspends the broker.
        self.lab.ingest(events)
        if failure:raise PermissionError(failure)
        if self.lab.state.get('unresolved_executions'):raise PermissionError('RECOVERY_UNKNOWN_EXECUTION')
    @staticmethod
    def position(rows):
        if rows is None:raise PermissionError('RECOVERY_POSITION_QUERY_INCOMPLETE')
        relevant=[]
        for r in rows:
            q=num(r['quantity'])
            if r.get('contract_id')==12087792 and r.get('security_type')=='CASH' and r.get('currency')=='USD':relevant.append(q)
            elif q!=0:raise PermissionError('RECOVERY_DIFFERENT_POSITION')
        if len(relevant)>1:raise PermissionError('RECOVERY_POSITION_AMBIGUOUS')
        return relevant[0] if relevant else num(0)
    def reconcile(self):
        self.certificate=None;a=self.auth.read(management=True)
        if self.wire.connect(a)!=[a['account']]:raise PermissionError('EXACT_IDENTITY_MISMATCH')
        try:
            snapshot=self.wire.snapshot(diagnostic=True);self.ingest(snapshot['events'])
            additional=self.wire.additional_exposure();self.ingest(self.wire.drain())
        except Exception:
            self.ingest(self.wire.drain());raise
        cash=snapshot['cash_reconciliation']
        if (not self.wire.connected or snapshot.get('exposure_reads_complete') is not True or
            additional.get('status')!='COMPLETE' or additional.get('errors') or cash.get('query_status')!='COMPLETE' or
            cash.get('account_ready') is not True or cash.get('base_currency')!='USD' or cash.get('errors') or
            snapshot['eur_cash'] is None or cash.get('value') is None or
            set(cash.get('completed_sources',[]))!=set(cash.get('expected_sources',[])) or
            len([s for s in cash.get('completed_sources',[]) if s.startswith('SUMMARY_')])!=2 or
            not {'ACCOUNT_UPDATES','ACCOUNT_UPDATES_MULTI'}<=set(cash.get('completed_sources',[]))):
            raise PermissionError('RECOVERY_ACCOUNT_RECONCILIATION_INCOMPLETE')
        if not all(0<=(self.clock()-date(s['received_at'])).total_seconds()<=30 for s in (snapshot,additional)):
            raise PermissionError('RECOVERY_RECONCILIATION_STALE')
        source=self.source();q=self.position(snapshot.get('positions'));multi=self.position(additional.get('positions'))
        for id in self.o['order_ids']:
            completed=self.o.get('completed_orders',{}).get(str(id),{})
            if completed.get('status') not in TERMINAL or completed.get('perm_id',0)<=0:
                raise PermissionError('RECOVERY_ORIGINAL_BRACKET_UNRESOLVED')
        inventory=self.lab.inventory(self.o)
        if q<0 or q>num(source['opening_quantity']) or q!=multi or q!=inventory:
            raise PermissionError('RECOVERY_POSITION_NOT_OWNED_REMAINING_LONG')
        if snapshot.get('portfolio') and self.position(snapshot['portfolio'])!=q:raise PermissionError('RECOVERY_PORTFOLIO_MISMATCH')
        if snapshot.get('foreign_positions') or snapshot.get('foreign_currency_balances'):raise PermissionError('RECOVERY_DIFFERENT_POSITION')
        records=self.o.get('recovery_orders',{})
        for r in snapshot['orders']:
            record=records.get(str(r['order_id']))
            if not record or (r.get('client_id'),r.get('contract_id'),r.get('side'),r.get('order_type'),r.get('parent_id'),r.get('reference'),r.get('tif'))!=(82,12087792,'SELL','LMT',0,record['reference'],'IOC') or num(r['quantity'])!=num(record['quantity']) or num(r.get('limit_price',0))!=num(record['price']):
                raise PermissionError('RECOVERY_UNKNOWN_ORDER')
            sold=sum((num(e['quantity']) for e in self.o['fills'].values() if e['order_id']==r['order_id']),num(0))
            if num(r['quantity'])-sold>q:raise PermissionError('RECOVERY_WORKING_SELL_EXCEEDS_LONG')
        if len(snapshot['orders'])>1:raise PermissionError('RECOVERY_MULTIPLE_WORKING_ORDERS')
        self.lab.exposure(snapshot)
        self.o['recovery_last_reconciliation']={'snapshot':copy.deepcopy(snapshot),'additional':copy.deepcopy(additional),'quantity':str(q)}
        self.lab.persist('RECOVERY_STRICT_RECONCILIATION',{'quantity':str(q),'open_orders':snapshot['orders']})
        self.certificate={'at':stamp(self.clock()),'quantity':str(q),'orders':copy.deepcopy(snapshot['orders'])}
        return snapshot,q
    def report(self,snapshot,q,quote=None):
        from .paper_diagnostic_evidence import evidence
        e=evidence(self.o);a=self.auth.read(management=True)
        return {'mode':SCOPE,'observed_at':stamp(self.clock()),**self.source(),'account_suffix':a['account'][-4:],
            'tws_pid':a['tws_pid'],'tws_start_filetime':a['tws_start_filetime'],
            'quantity_eur':str(q),'quantity_to_close':str(q),'position':'LONG' if q>0 else 'FLAT','quote':quote,
            'state':self.o['state'],'open_orders':snapshot['orders'],'emergency':True,'live_enabled':False,
            'strategy_enabled':False,'gross_pnl_usd':e['gross_pnl_usd'],'net_pnl_usd':e['net_pnl_usd'],
            'sell_commission_status':'COMPLETE' if e['sell']['commissions_complete'] else 'PENDING' if num(e['sell']['executed_quantity_eur']) else 'NO_SELL_FILL',
            'sell':e['sell'],'reserved_usd':self.lab.state['sessions'][self.o['session_id']]['reserved'],'orders_sent':0}
    def preview(self):
        snapshot,q=self.reconcile();quote=self.wire.observe_quote() if q>0 else None
        uncertain=any(self.o.get('completed_orders',{}).get(str(id),{}).get('status') not in TERMINAL or self.o['completed_orders'][str(id)].get('perm_id',0)<=0 for id in self.o.get('recovery_order_ids',[]))
        result=self.report(snapshot,q,quote);result['ready']=q>0 and not snapshot['orders'] and not uncertain and quote.get('available_for_execution') is True
        result['uncertain_previous_recovery']=uncertain
        self.lab.persist('RECOVERY_READ_ONLY_PREVIEW',result);return result
    def validate_grant(self,a,q):
        if a.get('mode')!=MODE or a.get('scope')!=SCOPE:raise PermissionError('RECOVERY_AUTHORIZATION_REQUIRED')
        s=self.source()
        if any(a.get(k)!=s[k] for k in ('intent','opening_order_id','opening_perm_id','opening_quantity','source_signature')):
            raise PermissionError('RECOVERY_SOURCE_BINDING_CHANGED')
        if not 0<q<=num(a['max_quantity']):raise PermissionError('RECOVERY_QUANTITY_OUTSIDE_AUTHORIZATION')
        if a['session_id']!=self.grant_id:raise PermissionError('RECOVERY_AUTHORIZATION_CHANGED')
    def gate(self,management=False):
        a=self.auth.read();cert=self.certificate
        if not cert or not self.wire.connected or not 0<=(self.clock()-date(cert['at'])).total_seconds()<=5:
            raise PermissionError('RECOVERY_RECONCILIATION_REQUIRED')
        if self.journal.load(self.lab.scope)['revision']!=self.lab.revision:raise PermissionError('JOURNAL_CHANGED_RECONCILE_REQUIRED')
        self.validate_grant(a,num(cert['quantity']));return a
    def authorize_transport(self,record,role,order_id,quantity=None):
        self.ingest(self.wire.drain());a=self.gate()
        registered=self.o.get('recovery_orders',{}).get(str(order_id))
        binding=self.lab.state.get('recovery_authorizations',{}).get(a['session_id'])
        if (role!='RECOVERY_CLOSE' or registered!=record or not binding or binding!=record or binding['order_id']!=order_id or
            record['authorization_id']!=a['session_id'] or record['source_perm_id']!=a['opening_perm_id'] or
            record['intent']!=self.o['intent'] or num(quantity)!=num(record['quantity']) or
            num(record['quantity'])!=num(self.certificate['quantity']) or num(quantity)!=self.lab.inventory(self.o) or self.certificate['orders']):
            raise PermissionError('RECOVERY_REDUCE_ONLY_SCOPE_INVALID')
        self.wire.validate_quote(record['quote']);return a
    def execute(self,*,max_polls=30,sleep=time.sleep):
        a=self.auth.read();snapshot,q=self.reconcile()
        if q==0:return self.report(snapshot,q)
        self.validate_grant(a,q)
        if a['session_id'] in self.lab.state.get('recovery_authorizations',{}):
            raise PermissionError('RECOVERY_AUTHORIZATION_ALREADY_USED')
        if snapshot['orders']:raise PermissionError('RECOVERY_PENDING_ORDER_RECONCILE_REQUIRED')
        # A previously consumed IOC must be terminal at the server before another owner permit can be used.
        for id in self.o.get('recovery_order_ids',[]):
            completed=self.o.get('completed_orders',{}).get(str(id),{})
            if completed.get('status') not in TERMINAL or completed.get('perm_id',0)<=0:
                raise PermissionError('RECOVERY_PREVIOUS_SEND_UNCERTAIN')
        quote=self.wire.quote();snapshot,q=self.reconcile()
        if q==0:return self.report(snapshot,q,quote)
        a=self.gate();self.wire.validate_quote(quote)
        if snapshot['orders']:raise PermissionError('RECOVERY_PENDING_ORDER_RECONCILE_REQUIRED')
        order_id=max(self.lab.state['next_order_id'],self.wire.next_order_id)
        record={'authorization_id':a['session_id'],'intent':self.o['intent'],'source_perm_id':a['opening_perm_id'],'source_signature':a['source_signature'],
            'order_id':order_id,'reference':'RECOVERY-'+a['session_id'],'quantity':str(q),
            'price':str((num(quote['bid'])/Decimal('0.00005')).to_integral_value(rounding=ROUND_FLOOR)*Decimal('0.00005')),
            'quote':quote,'sent_at':stamp(self.clock()),'side':'SELL','tif':'IOC','environment':'PAPER_TRADING'}
        self.lab.state['next_order_id']=order_id+1
        self.o.setdefault('recovery_order_ids',[]).append(order_id);self.o.setdefault('recovery_orders',{})[str(order_id)]=record
        self.lab.state.setdefault('recovery_authorizations',{})[a['session_id']]=copy.deepcopy(record)
        self.lab.persist('RECOVERY_SEND_PENDING_AUTHORIZATION_CONSUMED',record)
        self.certificate['quantity']=str(q)
        try:self.wire.recovery_close(record,a)
        except Exception:
            self.lab.stop('RECOVERY_SEND_UNCERTAIN_RECONCILE_REQUIRED');raise
        for _ in range(max_polls):
            sleep(.25);snapshot,q=self.reconcile()
            completed=self.o.get('completed_orders',{}).get(str(order_id),{})
            if not snapshot['orders'] and (q==0 or completed.get('status') in TERMINAL and completed.get('perm_id',0)>0):
                result=self.report(snapshot,q,quote);result['orders_sent']=1
                result['recovery_result']='CLOSED' if q==0 and self.o['state']=='CLOSED' else 'FLAT_COMMISSION_PENDING' if q==0 else 'PARTIAL_OR_NO_FILL_RECONCILED'
                self.lab.stop('RECOVERY_FINISHED_EMERGENCY_RETAINED',result);return result
        self.lab.stop('RECOVERY_MONITOR_LIMIT_RECONCILE_REQUIRED');raise TimeoutError('RECOVERY_MONITOR_LIMIT_RECONCILE_REQUIRED')

def main(root,inspect_only=False,intent=None):
    import msvcrt
    from .ibkr_session import session_guard,ExecutionMode,SessionConfiguration
    root=Path(root);auth=InspectionAuthorization(root) if inspect_only else RecoveryAuthorization(lambda:unseal(root/'.local/paper-recovery-close.dpapi'),endpoint=SessionConfiguration.load(root))
    # Share the laboratory mutex; recovery cannot race an autonomous runner.
    with (root/'.local/paper-lab.run.lock').open('a+b') as lock:
        lock.seek(0);lock.write(b'0');lock.flush();lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        wire=None;service=None
        try:
            def gate(**kw):return service.gate(**kw)
            def guard(*args):return service.authorize_transport(*args)
            wire=execution_wire(auth,gate,read_only=inspect_only,intent_guard=guard,
                session=session_guard(root,ExecutionMode.Research if inspect_only else ExecutionMode.PaperAuto))
            service=RecoveryClose(auth,DotnetJournal(root),wire,intent=intent,stop_file=root/'.local/paper-lab.emergency')
            result=service.preview() if inspect_only else service.execute()
            target=root/'artifacts/paper-lab/recovery-close-preview.json' if inspect_only else root/'artifacts/paper-lab/recovery-close-result.json'
            target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(result,indent=2),encoding='utf-8')
            print(json.dumps(result))
        except Exception as error:
            if service:service.lab.stop('RECOVERY_SUSPENDED',{'reason':safe_reason(error),'wire':wire.read_diagnostics()})
            raise
        finally:
            if wire:wire.disconnect()
            lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--inspect',action='store_true');p.add_argument('--intent');args=p.parse_args()
    try:main(args.root,args.inspect,args.intent)
    except Exception as error:
        print(json.dumps({'state':'RECOVERY_SUSPENDED','reason':safe_reason(error),'emergency':True,'live_enabled':False}));raise SystemExit(1)
