"""Read-only broker recovery: archive owned executions, never send/cancel or clear emergency."""
import argparse
import copy
import json
import subprocess
import os
import re
from pathlib import Path
from .paper_lab import Authorization,DotnetJournal,PaperLab,date,key,num,stamp,unseal,utc
from .paper_execution_wire import execution_wire
from .paper_data_diagnostics import currency_cash,exposure_check
from .paper_eur_reconciliation import initial_absence_evidence,AbsentEurAuthorization

def safe_reason(error):
    s=str(error)
    if s=='PAPER_AUTO_BLOCKED: TWS API is read-only.':return s
    return s if s and s.isupper() and not re.search(r'DU(?:R)?[0-9]{4,}',s) and all(c.isascii() and (c.isalnum() or c=='_') for c in s) else type(error).__name__


def pending_journal_orders(state,owned_reconciliation):
    """Retain history; only a freshly reconciled, settled journal is flat."""
    if (owned_reconciliation.get('status')!='RECONCILED_WITH_EMERGENCY_RETAINED'
            or state.get('pending_commissions') or state.get('unavailable_commissions') or state.get('unresolved_executions')
            or any(num(s.get('reserved',0))!=0 for s in state.get('sessions',{}).values())):
        return state['orders']
    return {k:o for k,o in state['orders'].items() if o['state']!='CLOSED'
            and not (o['state'] in ('CANCELLED_NO_FILL','REJECTED') and o.get('cancellation_reconciled_at'))}

class InspectionAuthorization:
    """Fresh read-only process binding. Historical protected identity is only an account anchor."""
    def __init__(self,root):
        self.root=Path(root)
        from .ibkr_session import SessionConfiguration
        self.configuration=SessionConfiguration.load(root)
        # No account identifier or credential enters PowerShell arguments/output.
        command="$listeners=@(Get-NetTCPConnection -State Listen -LocalPort "+str(self.configuration.port)+" | Select-Object -ExpandProperty OwningProcess -Unique); if($listeners.Count -ne 1){exit 1}; $p=Get-Process -Id $listeners[0]; @{pid=$p.Id;started=$p.StartTime.ToFileTimeUtc().ToString()} | ConvertTo-Json -Compress"
        result=subprocess.run(['powershell','-NoProfile','-NonInteractive','-Command',command],capture_output=True,text=True,timeout=10)
        if result.returncode:raise PermissionError('CURRENT_TWS_PROCESS_UNVERIFIED')
        self.process=json.loads(result.stdout)
    def read(self,management=False):
        from .paper_lab import same_process
        if not management:raise PermissionError('INSPECTION_ONLY_NO_EXECUTION')
        if os.environ.get('LIVE_TRADING','false').lower()!='false':raise PermissionError('LIVE_DISABLED')
        a=unseal(self.root/'.local/paper-lab-authorization.dpapi')
        candidate=unseal(self.root/'.local/ibkr-paper-candidate.dpapi')
        if a.get('environment')!='PAPER_TRADING' or a.get('live_enabled') is not False or a.get('paper_checked') is not True or a.get('identity_manual_match') is not True:
            raise PermissionError('PROTECTED_PAPER_IDENTITY_REQUIRED')
        self.configuration.matches(candidate)
        if candidate.get('account')!=a.get('account') or not 0<=(utc()-date(candidate['observed_at'])).total_seconds()<=120:
            raise PermissionError('FRESH_EXACT_IDENTITY_REQUIRED')
        if not same_process(self.process['pid'],self.process['started']):raise PermissionError('CURRENT_TWS_PROCESS_UNVERIFIED')
        a.update(host=self.configuration.host,port=self.configuration.port,tws_pid=self.process['pid'],tws_start_filetime=self.process['started'],inspection_only=True)
        return a

def record_owned_reconciliation(lab,owned):
    # Observing a reconciled historical order must preserve the operator's
    # emergency state. Only an actual reconciliation failure latches it.
    if owned['status']=='BLOCKED':lab.stop('READ_ONLY_OWNED_ORDER_RECONCILIATION',owned)
    else:lab.persist('READ_ONLY_OWNED_ORDER_RECONCILIATION',owned)

def inspect(root,*,strategy_market=False):
    import msvcrt
    root=Path(root);auth_path=root/'.local/paper-lab-authorization.dpapi'
    auth=InspectionAuthorization(root)
    # An expired/revoked grant still identifies the owner-attested process for read-only inspection.
    # It is not extended; the adapter rejects all mutation methods, including raw Protobuf.
    a=auth.read(management=True)
    lock_path=root/'.local/paper-lab.run.lock'
    with lock_path.open('a+b') as lock:
        lock.seek(0);lock.write(b'0');lock.flush();lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        wire=None
        try:
            journal=DotnetJournal(root);scope=key(a['account']);saved=journal.load(scope)
            if saved['state'] is None:raise PermissionError('LAB_JOURNAL_MISSING')
            state=copy.deepcopy(saved['state']);session=state['sessions'].get(a['session_id'],{})
            report={'observed_at':stamp(),'account_suffix':a['account'][-4:],'orders_sent':0,'live_enabled':False,'execution_enabled':False,
                    'authorization_expired':utc()>=date(a['expires_at']),'authorization_expires_at':a['expires_at'],
                    'inspection_only':True,'current_paper_ui_attestation_required':True,
                    'journal_emergency':state['emergency'],'local_emergency':(root/'.local/paper-lab.emergency').exists(),
                    'diagnostic_budget_usd':str(num(a['diagnostic_loss_budget'])),'experiments_used':session.get('count',0),
                    'reserved_usd':session.get('reserved','0'),'consumed_loss_usd':session.get('consumed_loss','0'),
                    'strategy_capital':state['strategy_capital'],'errors':[]}
            def blocked(**kwargs):raise PermissionError('DIAGNOSTIC_NO_ORDERS')
            from .ibkr_session import session_guard,ExecutionMode
            wire=execution_wire(auth,blocked,read_only=True,session=session_guard(root,ExecutionMode.Research))
            report['exact_identity_match']=wire.connect(a)==[a['account']];report['server_version']=wire.client.serverVersion()
            try:
                snapshot=wire.snapshot(diagnostic=True);report['snapshot']=snapshot
                cash=snapshot['cash_reconciliation']
                report['cash_state']=cash['state']
                report['additional_exposure']=wire.additional_exposure()
                if state['orders']:
                    lab=PaperLab(auth,journal,wire,stop_file=root/'.local/paper-lab.emergency')
                    lab.ingest(snapshot['events'])
                    try:
                        if snapshot['eur_cash'] is None:
                            if not lab.reconcile_owned_prefill(snapshot,report['additional_exposure']):
                                raise PermissionError('EUR_CASH_RECONCILIATION_UNAVAILABLE')
                        else:lab.exposure(snapshot)
                        for o in lab.state['orders'].values():lab.protection(o,snapshot['orders'])
                        owned={'status':'RECONCILED_WITH_EMERGENCY_RETAINED'}
                    except Exception as error:
                        owned={'status':'BLOCKED','reason':safe_reason(error)}
                    record_owned_reconciliation(lab,owned)
                    saved['revision']=lab.revision;state=copy.deepcopy(lab.state)
                    report['owned_reconciliation']=owned
                    report['owned_orders']=copy.deepcopy(state['orders'])
                    report['journal_emergency']=state['emergency']
                    report['reserved_usd']=state['sessions'].get(a['session_id'],{}).get('reserved','0')
                report['exposure_check']=exposure_check(snapshot,report['additional_exposure'],
                    pending_journal_orders(state,report.get('owned_reconciliation',{})))
                report['reconciliation']=report['exposure_check']['status']
                if report.get('owned_reconciliation',{}).get('status')=='BLOCKED':report['reconciliation']='BLOCKED'
                report['initial_absence_route']=initial_absence_evidence(snapshot,report['additional_exposure'],state,utc())
                report['strategy_initial_absence_route']=initial_absence_evidence(snapshot,report['additional_exposure'],state,utc(),strategy=True)
                exception_path=root/'.local/paper-lab-eur-exception.dpapi'
                report['initial_absence_route']['protected_exception']='NOT_REGISTERED'
                if exception_path.exists():
                    try:
                        e=AbsentEurAuthorization(lambda:unseal(exception_path)).read(a,for_review=True)
                        report['initial_absence_route'].update(protected_exception='REVIEW_ONLY_VALID',exception_expires_at=e['expires_at'])
                    except Exception:report['initial_absence_route']['protected_exception']='INVALID_OR_EXPIRED'
            except Exception as error:
                report['errors'].append({'stage':'snapshot','reason_type':type(error).__name__,'reason':safe_reason(error)})
                report['reconciliation']='BLOCKED'
                if 'snapshot' not in report:
                    report['incomplete_cash_observation']=currency_cash(wire.account_rows,wire.account_completed,
                        errors=wire.account_errors,expected_sources=wire.account_expected)
                    report['cash_state']=report['incomplete_cash_observation']['state']
            try:
                report['contract']=wire.contract_details()
                report['contract']['session']=wire.trading_session
                try:report['paper_auto_calendar']=wire.calendar()
                except (AttributeError,PermissionError,TimeoutError,ValueError):report['paper_auto_calendar']={'status':'UNVERIFIED'}
                if strategy_market:
                    calendar=wire.calendar()
                    originals={str(m):wire.history(m) for m in (60,240,15)}
                    from .research_analysis import analyze
                    indicators=json.loads((root/'config/research-indicators.json').read_text(encoding='utf-8-sig'))
                    market={'observed_at':stamp(),'calendar':calendar,'originals':originals,
                        'analysis':analyze({'instrument':'EUR/USD','source':'IBKR_TWS','what_to_show':'MIDPOINT',
                            'as_of':stamp(),'indicators':indicators,'calendar':calendar,'originals':originals}),
                        'orders_sent':0,'live_enabled':False,'execution_enabled':False}
                    target=root/'artifacts/paper-lab/market-evidence.json'
                    target.write_text(json.dumps(market,indent=2),encoding='utf-8')
                    report['market_evidence_path']=str(target);report['calendar']=calendar
                report['quote']=wire.observe_quote()
                report['strategy_initial_absence_route']['protected_exception']='NOT_REGISTERED' if not (root/'.local/paper-lab-eur-exception.dpapi').exists() else 'REQUIRES_STRATEGY_SCOPE_VERIFICATION'
                if 'SUBSCRIPTION_MISSING' in report['quote']['reasons']:
                    report['delayed_observation']=wire.observe_quote(market_type=3)
            except Exception as error:report['errors'].append({'stage':'quote','reason_type':type(error).__name__,'reason':safe_reason(error)})
            report['api_events']=wire.api_events
            report['wire_reads']=wire.read_diagnostics()
            blocks=[]
            if report['authorization_expired'] or a.get('revoked') or a.get('emergency'):blocks.append('SESSION_STOPPED_OR_EXPIRED')
            if state['emergency'] or report['local_emergency']:blocks.append('EMERGENCY_STOP')
            if a.get('mode')!='StrategyPaper' or a.get('strategy_requirements_verified') is not True:blocks.append('STRATEGY_EVIDENCE_REQUIRED')
            if report.get('reconciliation')!='FLAT_CONFIRMED':blocks.append('RECONCILIATION_REQUIRED')
            report['account_binding']={'account':wire.session.binding.masked_account,'verified':wire.connected,'scope':'IDENTITY_ONLY'}
            report['paper_auto']={'state':'PAPER_AUTO_BLOCKED','reasons':blocks or ['PROTECTED_RUN_REQUIRED'],
                'live_enabled':False,'risk_policy_changed':False}
            auth.read(management=True) # The same owner-attested TWS process must still be present.
            journal.commit(scope,saved['revision'],state,{'event':'READ_ONLY_ACCOUNT_QUOTE_DIAGNOSTIC','at':stamp(),'data':report})
            target=root/'artifacts/paper-lab/data-diagnostics.json';target.parent.mkdir(parents=True,exist_ok=True)
            target.write_text(json.dumps(report,indent=2),encoding='utf-8')
            print(json.dumps({'report':str(target),'account_suffix':report['account_suffix'],'reconciliation':report.get('reconciliation','BLOCKED'),
                'cash_state':report.get('cash_state','UNKNOWN'),'exposure_check':report.get('exposure_check'),'quote':report.get('quote'),'orders_sent':0,'execution_enabled':False,
                'journal_emergency':report['journal_emergency'],'local_emergency':report['local_emergency'],
                'account_binding':report['account_binding'],'paper_auto':report['paper_auto']}))
        finally:
            if wire:wire.disconnect()
            lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',required=True);parser.add_argument('--strategy-market',action='store_true');args=parser.parse_args()
    try:inspect(args.root,strategy_market=args.strategy_market)
    except Exception as error:
        print(json.dumps({'state':'DIAGNOSTIC_BLOCKED','reason_type':type(error).__name__,'reason':safe_reason(error),'orders_sent':0,'live_enabled':False}));raise SystemExit(1)
