"""Explicitly activated worker. Default is status, never order submission."""
import argparse
import hashlib
import json
from pathlib import Path
import time
from .paper_lab import Authorization,DotnetJournal,PaperLab,unseal,stamp,utc,date,EXPERIMENTAL,num
from .paper_execution_wire import execution_wire
from .paper_eur_reconciliation import AbsentEurAuthorization,validate_review_permit
from .ibkr_session import session_guard,ExecutionMode,SessionConfiguration,SessionReconnect

def paper_auto_ready(lab):
    """Readiness requires the existing gates, not merely an identity match."""
    a=lab.check()
    if lab.mode!='StrategyPaper' or a.get('strategy_requirements_verified') is not True:
        raise PermissionError('STRATEGY_EVIDENCE_REQUIRED')
    if (any(o['state'] not in ('CLOSED','REJECTED','CANCELLED_NO_FILL') for o in lab.state['orders'].values())
            or lab.state.get('pending_commissions') or lab.state.get('unavailable_commissions')):
        raise PermissionError('PAPER_RESULT_UNRESOLVED')
    account=lab.journal.strategy_mark(lab.state['strategy_account'])
    lab.state['strategy_account']=account
    if num(account['capital']['remainingLoss'])<=0:
        lab.persist('STRATEGY_RISK_REJECTION',{'reason':'CUMULATIVE_LOSS_LIMIT'})
        raise PermissionError('CUMULATIVE_LOSS_LIMIT')
    if hasattr(lab.wire,'assert_mutation_allowed'):lab.wire.assert_mutation_allowed(a)
    lab.persist('PAPER_AUTO_READY',{'execution_mode':'PaperAuto','risk_loaded':True})
    if getattr(lab.wire,'session',None):lab.wire.session.event('PAPER_AUTO_READY',risk_loaded=True)


def review_authorization(previous,permit,now):
    import copy
    if permit.get('current_paper_review_attested') is not True:raise PermissionError('CURRENT_PAPER_REVIEW_ATTESTATION_REQUIRED')
    a=copy.deepcopy(previous)
    a.update(tws_pid=permit['tws_pid'],tws_start_filetime=permit['tws_start_filetime'],
             confirmed_at=permit['confirmed_at'],expires_at=permit['expires_at'],revoked=True,emergency=True,
             authorized=True,review_only=True,manage_owned_positions_after_stop=True)
    validate_review_permit(permit,a,now,exception_id=permit.get('exception_id'))
    return a

def strategy_cycle(lab,plan,originals,quote):
    """One causal decision, no quota. A stopped day still records market."""
    from .paper_strategy import signal
    now=lab.clock();grant=lab.auth.read(management=True);account=lab.journal.strategy_mark(lab.state['strategy_account'])
    lab.state['strategy_account']=account
    c=account.get('paperContinuation',{});reason=None
    if num(account['capital'].get('remainingLoss',0))<=0:reason='CUMULATIVE_LOSS_LIMIT'
    elif lab.state['emergency'] or lab.stop_file and lab.stop_file.exists():reason='EMERGENCY_STOP'
    elif grant.get('revoked') or grant.get('emergency'):reason='SESSION_STOPPED_OR_EXPIRED'
    elif any(o['state'] not in ('CLOSED','REJECTED','CANCELLED_NO_FILL') for o in lab.state['orders'].values()) or c.get('pendingId') or c.get('resultPending') or lab.state.get('pending_commissions') or lab.state.get('unavailable_commissions'):reason='PAPER_RESULT_UNRESOLVED'
    elif c.get('firstLossStopped'):reason='DAILY_FIRST_LOSS_STOP'
    elif c.get('closedTrades',0)>0 and not num(c.get('lastNet') or 0)>0:reason='DAILY_WIN_REQUIRED'
    lab.persist('STRATEGY_MARKET_MONITOR',{'quote':quote,'trading_day':c.get('day'),'entry_block':reason})
    if reason:return {'state':'MONITORING','reason':reason}
    if quote.get('available_for_execution',True) is not True:return {'state':'MONITORING','reason':'QUOTE_UNUSABLE'}
    try:proposal=signal(plan,originals,quote,now)
    except PermissionError as error:
        if str(error)!='STRATEGY_PRICE_GRID_NOT_EQUIVALENT':raise
        lab.persist('STRATEGY_ELIGIBILITY_BLOCKED',{'reason':str(error)})
        return {'state':'MONITORING','reason':str(error)}
    if proposal is None:
        lab.persist('NO_TRADE',{'strategy_version':plan['strategy_version'],'reason':'NO_VALID_SIGNAL_OR_UNSUPPORTED_SIDE'})
        return {'state':'MONITORING','reason':'NO_VALID_APPROVED_SIGNAL','decision':'NO_TRADE'}
    try:result=lab.strategy_proposal(proposal,quote)
    except PermissionError as error:
        if str(error) not in ('QUOTE_UNUSABLE','STRATEGY_SIGNAL_STALE','STRATEGY_RISK_REJECTED'):raise
        lab.persist('STRATEGY_ELIGIBILITY_BLOCKED',{'reason':str(error)})
        return {'state':'MONITORING','reason':str(error)}
    return result

def continuous_strategy(lab,a,*,sleep=time.sleep,monotonic=time.monotonic,max_cycles=None):
    # All market reads participate in reconnect handling, including history and
    # quotes. Restarting observation never retransmits a persisted intention.
    for attempt in range(3):
        try:return _continuous_strategy(lab,a,sleep=sleep,monotonic=monotonic,max_cycles=max_cycles)
        except PermissionError:raise
        except (ConnectionError,TimeoutError,OSError):
            if attempt==2:
                lab.stop('PAPER_AUTO_READ_RECOVERY_EXHAUSTED');raise
            SessionReconnect(lab,sleep=sleep).reconcile();sleep(.25 * 2**attempt)


def _continuous_strategy(lab,a,*,sleep=time.sleep,monotonic=time.monotonic,max_cycles=None):
    from .paper_strategy import validate_plan,exit_decision
    plan=a['strategy_plan'];originals=None;next_history=0;cycles=0
    while max_cycles is None or cycles<max_cycles:
        cycles+=1
        if not lab.wire.connected:SessionReconnect(lab,sleep=sleep).reconcile()
        try:lab.supervise() # Always manage owned protection before contemplating an entry.
        except PermissionError:raise
        except (ConnectionError,TimeoutError,OSError):
            SessionReconnect(lab,sleep=sleep).reconcile();sleep(.25);continue
        held=[o for o in lab.state['orders'].values() if lab.inventory(o)>0]
        if getattr(lab.auth,'paper_auto',False) and lab.stop_file and lab.stop_file.with_name('paper-auto.stop').exists():
            if all(o['state'] in ('CLOSED','REJECTED','CANCELLED_NO_FILL') for o in lab.state['orders'].values()):
                lab.stop('PAPER_AUTO_OPERATOR_STOPPED');return
        exact=plan['exit_policy']=='RESEARCH_D_V1'
        if held and not exact:sleep(.25);continue
        now=lab.clock()
        if now>=date(a['expires_at']) or now>=date(plan['evidence_expires_at']):
            lab.persist('STRATEGY_SESSION_EXPIRED_NO_NEW_ENTRIES')
            if held and exact:
                for o in held:lab.research_close(o,{'exit':True,'reason':'SESSION_STOPPED_OR_EXPIRED','at':stamp(now)})
            if all(o['state'] in ('CLOSED','REJECTED','CANCELLED_NO_FILL') for o in lab.state['orders'].values()):return
            sleep(.25);continue
        grant=lab.auth.read(management=True)
        if held and exact and (lab.state['emergency'] or grant.get('revoked') or grant.get('emergency') or lab.stop_file and lab.stop_file.exists()):
            for o in held:lab.research_close(o,{'exit':True,'reason':'EMERGENCY_STOP','at':stamp(now)})
            sleep(.25);continue
        validate_plan(plan,now,a['strategy_versions'])
        if monotonic()>=next_history:
            # Fetch higher frames first; the 15m signal is sampled last. Never reuse an old signal.
            previous=originals or {};originals={}
            for m in (60,240,15):
                latest=previous.get(str(m),[])
                expected=int(now.timestamp()//(m*60))*(m*60)
                up_to_date=latest and date(latest[-1]['opened_at']).timestamp()+m*60>=expected
                originals[str(m)]=latest if m!=15 and up_to_date else lab.wire.history(m)
            next_history=monotonic()+900-(lab.clock().timestamp()%900)+1
            lab.persist('STRATEGY_CLOSED_MARKET_BARS',originals)
        lab.connect_and_reconcile()
        import copy
        runtime_plan=copy.deepcopy(plan)
        try:
            runtime_plan['calendar']=lab.wire.calendar()
        except (PermissionError,ValueError,KeyError,TypeError,TimeoutError):
            quote=lab.wire.observe_quote()
            lab.persist('STRATEGY_MARKET_MONITOR',{'quote':quote,'entry_block':'IBKR_CALENDAR_UNVERIFIED'})
            sleep(5);continue
        quote=lab.wire.observe_quote()
        if held and exact:
            lab.wire.validate_quote(quote)
            for o in held:
                position=o['payload']['context'].get('research_position')
                if not position:raise PermissionError('RESEARCH_EXIT_POSITION_MISSING')
                decision=exit_decision(runtime_plan,originals,quote,lab.clock(),position,lab.journal)
                if decision:lab.research_close(o,decision)
        else:strategy_cycle(lab,runtime_plan,originals,quote)
        sleep(.25 if any(lab.inventory(o)>0 for o in lab.state['orders'].values()) else 5)


def run(root,review=False,allow_absent_eur=False,execution_mode=ExecutionMode.PaperAuto,authorization=None):
    root=Path(root);configuration=SessionConfiguration.load(root)
    auth=authorization or Authorization(lambda:unseal(root/'.local/paper-lab-authorization.dpapi'),endpoint=configuration)
    if review:
        auth=Authorization(lambda:review_authorization(unseal(root/'.local/paper-lab-authorization.dpapi'),
            unseal(root/'.local/paper-lab-review-permit.dpapi'),utc()),endpoint=configuration)
    a=auth.read(management=True);lock_path=root/'.local/paper-lab.run.lock';lock_path.parent.mkdir(parents=True,exist_ok=True)
    # OS-held byte lock releases on crash; the journal still starts suspended and reconciles.
    import msvcrt
    with lock_path.open('a+b') as lock:
        lock.seek(0);lock.write(b'0');lock.flush();lock.seek(0)
        try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:raise PermissionError('LAB_ALREADY_RUNNING')
        lab=None;wire=None
        try:
            journal=DotnetJournal(root,a.get('risk_profile','PAPER_CONSERVATIVE'))
            wire=execution_wire(auth,lambda management=False:lab.check(management),read_only=review,
                                intent_guard=lambda o,role,order_id,quantity=None:lab.authorize_transport(o,role,order_id,quantity),
                                session=session_guard(root,ExecutionMode.Research if review else execution_mode))
            use_exception=allow_absent_eur if review else bool(a.get('eur_absence_exception_id'))
            exception=AbsentEurAuthorization(lambda:unseal(root/'.local/paper-lab-eur-exception.dpapi')) if use_exception else None
            lab=PaperLab(auth,journal,wire,stop_file=root/'.local/paper-lab.emergency',eur_exception=exception,exception_review=review and allow_absent_eur)
            SessionReconnect(lab).reconcile()
            if getattr(auth,'paper_auto',False):
                wire.calendar() # Authenticated native schedule; no provisional fallback.
                lab.check()
            if not review and ExecutionMode(execution_mode)!=ExecutionMode.PaperAuto:
                print(json.dumps({'state':'ORDER_TRANSPORT_BLOCKED','execution_mode':ExecutionMode(execution_mode).value,
                    'orders_sent':0,'live_enabled':False}));return
            if review:
                exception_id=exception.read(a,for_review=True)['record_id'] if allow_absent_eur else None
                permit=unseal(root/'.local/paper-lab-review-permit.dpapi')
                permit_id=validate_review_permit(permit,a,utc(),exception_id=exception_id)
                if permit_id in lab.state.get('review_permits_used',{}):raise PermissionError('OWNER_REVIEW_ALREADY_CONSUMED')
                lab.state.setdefault('review_permits_used',{})[permit_id]=stamp();lab.persist('OWNER_REVIEW_PERMIT_CONSUMED')
                def review_guard():
                    checked=validate_review_permit(unseal(root/'.local/paper-lab-review-permit.dpapi'),auth.read(management=True),utc(),exception_id=exception_id)
                    if checked!=permit_id:raise PermissionError('OWNER_REVIEW_CHANGED')
                result=lab.review_flat(review_guard);print(json.dumps({**result,'orders_sent':0,'live_enabled':False}));return
            # Recover and manage already-owned orders before considering another experiment.
            recovery_deadline=time.monotonic()+390
            while any(o['state'] not in ('CLOSED','REJECTED','CANCELLED_NO_FILL') for o in lab.state['orders'].values()):
                lab.supervise()
                if time.monotonic()>recovery_deadline:raise TimeoutError('RECOVERY_MANAGEMENT_TIMEOUT')
                time.sleep(.25)
            auth.read() # Expiry/revocation may allow bounded cleanup, never fresh entries.
            lab.check()
            if a['mode']=='StrategyPaper':
                if a.get('strategy_requirements_verified') is True:paper_auto_ready(lab)
                if a.get('risk_profile')==EXPERIMENTAL and a.get('continuous') is True:
                    continuous_strategy(lab,a);return
                if a.get('strategy_requirements_verified') is not True:
                    lab.persist('STRATEGY_EVIDENCE_BLOCKED')
                    print(json.dumps({'state':'STRATEGY_BLOCKED','reason':'EXECUTION_EVIDENCE_INCOMPLETE','orders_sent':0,'live_enabled':False}));return
                proposals=json.loads((root/'.local/paper-strategy-proposals.json').read_text(encoding='utf-8'))
                if not isinstance(proposals,list) or len(proposals)>a['max_experiments']:raise PermissionError('UNBOUNDED_STRATEGY_QUEUE')
                for proposal in proposals:
                    result=lab.strategy_proposal(proposal,wire.quote())
                    if result['state']=='STRATEGY_REJECTED':continue
                    deadline=time.monotonic()+a['max_hold_seconds']+90
                    while result['state'] not in ('CLOSED','REJECTED','CANCELLED_NO_FILL'):
                        lab.supervise()
                        if time.monotonic()>deadline:raise TimeoutError('STRATEGY_MANAGEMENT_TIMEOUT')
                        time.sleep(.25)
                    lab.connect_and_reconcile()
                print(json.dumps({'state':'STRATEGY_QUEUE_COMPLETED','live_enabled':False}));return
            for n in range(1): # ExecutionDiagnostics is one lifetime attempt; no retry or experiment loop.
                intent=hashlib.sha256(f"{a['session_id']}|diagnostic-v1|12087792|{n}".encode()).hexdigest()
                if intent not in lab.state['orders']:
                    q=wire.quote();lab.begin(intent,a['max_quantity'],q,{'purpose':'EXECUTION_COSTS_NOT_100_USD_STRATEGY','observed_at':stamp()})
                deadline=time.monotonic()+a['max_hold_seconds']+90
                while lab.state['orders'][intent]['state'] not in ('CLOSED','REJECTED','CANCELLED_NO_FILL'):
                    lab.supervise()
                    if time.monotonic()>deadline:
                        lab.stop('MANAGEMENT_TIMEOUT_PROTECTION_RETAINED');raise TimeoutError('MANAGEMENT_TIMEOUT')
                    time.sleep(.25)
                lab.connect_and_reconcile() # Protective siblings must be cancelled/absent before the next experiment.
            print(json.dumps({'mode':a['mode'],'experiments':len(lab.state['experiences']),'orders_simulated':True,'live_enabled':False}))
        except Exception as error:
            if lab:
                from .paper_lab_diagnostics import safe_reason
                try:lab.stop('WORKER_SUSPENDED',{'error':safe_reason(error),'wire':wire.read_diagnostics() if wire else None})
                except Exception:pass
            raise
        finally:
            try:
                if lab and a['mode']=='ExecutionDiagnostics' and not review:
                    from .paper_diagnostic_evidence import evidence
                    records=[evidence(o) for o in lab.state['orders'].values() if o['category']=='PAPER_DIAGNOSTIC']
                    target=root/'artifacts/paper-lab/execution-diagnostic.json';target.parent.mkdir(parents=True,exist_ok=True)
                    temporary=target.with_suffix('.json.tmp')
                    temporary.write_text(json.dumps({'environment':'PAPER_TRADING','live_enabled':False,
                        'emergency':lab.state['emergency'],'diagnostics':records},indent=2),encoding='utf-8');temporary.replace(target)
            finally:
                if wire:wire.disconnect()
                lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--review',action='store_true');p.add_argument('--allow-absent-eur',action='store_true')
    p.add_argument('--execution-mode',choices=[m.value for m in ExecutionMode],default=ExecutionMode.PaperAuto.value)
    p.add_argument('--paper-auto',action='store_true');args=p.parse_args()
    try:
        if args.allow_absent_eur and not args.review:raise PermissionError('EUR_EXCEPTION_REQUIRES_PROTECTED_EXECUTION_BINDING')
        if args.paper_auto and (args.review or args.allow_absent_eur or args.execution_mode!='PaperAuto'):raise PermissionError('PAPER_AUTO_SCOPE_INVALID')
        from .paper_auto import operational_authorization
        run(args.root,args.review,args.allow_absent_eur,args.execution_mode,
            operational_authorization(args.root) if args.paper_auto else None)
    except Exception as e:
        from .paper_lab_diagnostics import safe_reason
        print(json.dumps({'state':'SUSPENDED','reason_type':type(e).__name__,'reason':safe_reason(e),'live_enabled':False}))
        raise SystemExit(1)
