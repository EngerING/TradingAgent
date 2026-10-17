"""Operator-granted persistent Paper-only permission and aggregate readiness.

No implicit grants or emergency clearing. Run uses the existing risk/runner path.
"""
import argparse
import copy
import json
import os
from pathlib import Path
from datetime import timedelta
from .paper_lab import Authorization,DotnetJournal,EXPERIMENTAL,unseal,stamp,utc,date,key,same_process
from .ibkr_session import AccountBinding,SessionConfiguration,StructuredSessionEvents
from .paper_eligibility import source_hashes,evaluate,validate_structure

PERMISSION='PAPER_AUTO_ONLY'

def audit(root,b,event,**data):
    StructuredSessionEvents(Path(root)/'artifacts/paper-lab/session-events.jsonl')(
        {'event':event,'at':stamp(),'account':b.masked_account,'environment':'PAPER_TRADING','live_enabled':False,**data})

def binding(root):return AccountBinding(unseal(Path(root)/'.local/ibkr-account-binding.dpapi'))

def permission_status(record,b,now):
    if not record:return 'NOT_GRANTED'
    if (record.get('schema_version')!=1 or record.get('scope')!=PERMISSION
        or record.get('environment')!='PAPER_TRADING' or record.get('live_enabled') is not False
        or record.get('account_binding_id')!=b.binding_id or record.get('account')!=b.account
        or record.get('execution_mode')!='PaperAuto' or record.get('granted_by') is None):return 'INVALID'
    if record.get('status')=='Revoked' or record.get('revoked') is True:return 'REVOKED'
    if record.get('status')!='Granted' or record.get('authorized') is not True:return 'INVALID'
    try:
        start,end=date(record['confirmed_at']),date(record['expires_at'])
        if start>now or not start<end<=start+timedelta(hours=24):return 'INVALID'
        return 'EXPIRED' if now>=end else 'VALID'
    except (ValueError,KeyError,TypeError):return 'INVALID'

def read_permission(root):
    path=Path(root)/'.local/paper-auto-authorization.dpapi'
    return unseal(path) if path.exists() else None

def selected(report,id=None):
    id=id or report['preferred'];rows=[x for x in report['strategies'] if x['strategy_id']==id and x['state']=='PaperEligible']
    if len(rows)!=1:raise PermissionError('STRATEGY_PAPER_INELIGIBLE')
    return rows[0]

def strategy_allowed(strategy,environment):
    return (environment=='PAPER_TRADING' and strategy.get('state')=='PaperEligible'
        and strategy.get('live_approved') is False and strategy.get('registered') is True
        and strategy.get('enabled') is True and strategy.get('tests_passed') is True)

def aggregate(conditions):
    expected={'IBKR_CONNECTED','ACCOUNT_VERIFIED','ENVIRONMENT_PAPER','RECONCILIATION',
              'EMERGENCY_STOP','PAPER_AUTHORIZATION','STRATEGY_PAPER_ELIGIBLE','RISK_ENGINE','EXECUTION_GUARD'}
    if set(conditions)!=expected:raise PermissionError('PAPER_READINESS_CONDITIONS_INCOMPLETE')
    return {'conditions':conditions,'paper_auto_ready':all(x=='PASS' for x in conditions.values()),
            'environment':'PAPER_TRADING','live_enabled':False}

def owned_reconciled(inspection,record):
    """Restart management is limited to this permission's journal-owned inventory."""
    if not record or inspection.get('owned_reconciliation',{}).get('status')!='RECONCILED_WITH_EMERGENCY_RETAINED':return False
    snapshot=inspection.get('snapshot',{});cash=snapshot.get('cash_reconciliation',{});extra=inspection.get('additional_exposure',{})
    if (cash.get('query_status')!='COMPLETE' or cash.get('account_ready') is not True or snapshot.get('eur_cash') is None
        or snapshot.get('exposure_reads_complete') is not True or extra.get('status')!='COMPLETE' or extra.get('errors')):return False
    from .paper_lab import num
    expected=0;ids=set()
    for o in inspection.get('owned_orders',{}).values():
        if o['state'] in ('CLOSED','REJECTED','CANCELLED_NO_FILL'):continue
        if o.get('session_id')!=record['session_id'] or o.get('payload',{}).get('mode')!='StrategyPaper':return False
        ids.update(o['order_ids']+o.get('recovery_order_ids',[]))
        expected+=sum((num(f['quantity'])*(1 if f['side']=='BUY' else -1) for f in o['fills'].values()),num(0))
    if any(o.get('order_id') not in ids for o in snapshot.get('orders',[])):return False
    for rows in (snapshot.get('positions',[]),extra.get('positions',[])):
        active=[p for p in rows if num(p['quantity'])!=0]
        if any(p.get('contract_id')!=12087792 for p in active) or sum((num(p['quantity']) for p in active),num(0))!=expected:return False
    return True

def readiness(root,inspection,eligibility,b,record):
    auth=permission_status(record,b,utc())
    try:strategy=selected(eligibility,(record or {}).get('selected_strategy'))
    except PermissionError:strategy=None
    if record and strategy and (record.get('strategy_version')!=strategy['strategy_version']
        or record.get('source_hashes')!=eligibility.get('source_hashes')):auth='INVALID'
    fresh=0<=(utc()-date(inspection['observed_at'])).total_seconds()<=120
    conditions={
      'IBKR_CONNECTED':'PASS' if fresh and inspection.get('exact_identity_match') is True else 'BLOCKED',
      'ACCOUNT_VERIFIED':'PASS' if fresh and inspection.get('account_binding',{}).get('verified') is True else 'BLOCKED',
      'ENVIRONMENT_PAPER':'PASS' if inspection.get('live_enabled') is False else 'BLOCKED',
      'RECONCILIATION':'PASS' if not inspection.get('errors') and (inspection.get('reconciliation')=='FLAT_CONFIRMED'
        or owned_reconciled(inspection,record)) else 'BLOCKED',
      'EMERGENCY_STOP':'BLOCKED' if inspection.get('journal_emergency') or (Path(root)/'.local/paper-lab.emergency').exists()
        or (Path(root)/'.local/paper-auto.stop').exists() else 'PASS',
      'PAPER_AUTHORIZATION':'PASS' if auth=='VALID' else auth,
      'STRATEGY_PAPER_ELIGIBLE':'PASS' if strategy else 'BLOCKED',
      'RISK_ENGINE':'PASS' if strategy and isinstance((strategy.get('risk_probe') or {}).get('allowed'),bool) else 'BLOCKED',
      'EXECUTION_GUARD':'PASS' if strategy and strategy['tests_passed']
        and inspection.get('paper_auto_calendar',{}).get('status') in ('IBKR_HISTORICAL_SCHEDULE','IBKR_AUTHENTIC_SESSIONS')
        and not any(e.get('event')=='PAPER_AUTO_BLOCKED' for e in inspection.get('wire_reads',{}).get('session_events',[])) else 'BLOCKED'}
    result=aggregate(conditions)
    result.update(account=b.masked_account,authorization=auth,strategy=strategy,
        positions=[{'contract_id':p.get('contract_id'),'quantity':p.get('quantity')} for p in inspection['snapshot']['positions']],
        open_orders=len(inspection['snapshot']['orders']),diagnostic_reserve=inspection.get('reserved_usd'),
        calendar=inspection.get('paper_auto_calendar',{}),orders_sent=0)
    return result

class PaperAutoAuthorization:
    """Persistent permission; fresh process certification is ephemeral, not renewal."""
    paper_auto=True
    def __init__(self,loader,binding_loader,eligibility_loader,process_loader,*,clock=utc,session_alive=same_process,endpoint=None):
        self.loader,self.binding_loader,self.eligibility_loader,self.process_loader=loader,binding_loader,eligibility_loader,process_loader
        self.clock,self.session_alive,self.endpoint=clock,session_alive,endpoint or SessionConfiguration()
        self.process=None
    def read(self,management=False):
        record=self.loader();b=self.binding_loader();status=permission_status(record,b,self.clock())
        if status not in ('VALID','EXPIRED','REVOKED'):raise PermissionError('PAPER_AUTO_AUTHORIZATION_'+status)
        if status!='VALID' and not management:raise PermissionError('PAPER_AUTO_AUTHORIZATION_'+status)
        report=self.eligibility_loader();s=selected(report,record['selected_strategy'])
        if record['strategy_version']!=s['strategy_version'] or record['source_hashes']!=report['source_hashes']:
            raise PermissionError('PAPER_ELIGIBILITY_CHANGED')
        if self.process is None or not self.session_alive(self.process['tws_pid'],self.process['tws_start_filetime']):
            self.process=self.process_loader()
        a=copy.deepcopy(record);a.update(tws_pid=self.process['tws_pid'],tws_start_filetime=self.process['tws_start_filetime'])
        a['strategy_plan']['calendar']=self.process['calendar']
        a['strategy_plan']['evidence_expires_at']=a['expires_at']
        if status=='REVOKED':a['revoked']=True
        # The sealed consent owns execution rights; the process certificate only
        # confirms endpoint/process identity, and cannot renew that permission.
        return Authorization(lambda:a,self.session_alive,self.clock,endpoint=self.endpoint).read(management)

def eligibility_loader(root):
    root=Path(root);report=json.loads((root/'artifacts/paper-lab/paper-eligibility.json').read_text())
    if report['source_hashes']!=source_hashes(root):raise PermissionError('PAPER_ELIGIBILITY_STALE')
    # A disabled/changed registration invalidates an existing permission as well.
    rows=DotnetJournal(root).command({'operation':'paper-strategy-registry','account_key':key(binding(root).account)})
    current={r['hash']:r for r in rows}
    for s in report['strategies']:
        row=current.get(s['strategy_version'])
        if not row or row['registration'].get('enabled',True) is not True or row['registration'].get('state')=='SUSPENDED':
            raise PermissionError('PAPER_REGISTERED_STRATEGY_DISABLED_OR_CHANGED')
    return report

def operational_authorization(root):
    root=Path(root)
    def process():
        from .paper_lab_diagnostics import InspectionAuthorization
        current=InspectionAuthorization(root).read(management=True)
        inspection=json.loads((root/'artifacts/paper-lab/data-diagnostics.json').read_text())
        calendar=inspection.get('paper_auto_calendar')
        if not calendar or calendar.get('status') not in ('IBKR_HISTORICAL_SCHEDULE','IBKR_AUTHENTIC_SESSIONS'):
            raise PermissionError('IBKR_CALENDAR_UNVERIFIED')
        return {**current,'calendar':calendar}
    return PaperAutoAuthorization(lambda:read_permission(root),lambda:binding(root),lambda:eligibility_loader(root),process,
        endpoint=SessionConfiguration.load(root))

def proposal(root,inspection,eligibility,b,minutes=480,strategy=None):
    if not 1<=minutes<=1440:raise PermissionError('PAPER_AUTO_EXPIRY_OUT_OF_BOUNDS')
    if (inspection.get('reconciliation')!='FLAT_CONFIRMED' or inspection.get('journal_emergency')
        or (Path(root)/'.local/paper-lab.emergency').exists() or inspection['snapshot']['orders']):
        raise PermissionError('PAPER_AUTO_GRANT_REQUIRES_OWNER_CLEAR_AND_RECONCILIATION')
    s=selected(eligibility,strategy);now=utc()
    from .paper_strategy import ENGINE
    plan={'schema_version':1,'engine':ENGINE,'strategy_version':s['strategy_version'],'strategy_id':s['strategy_id'],
          'name':s['name'],'instrument':'EUR/USD','side':'BUY','exit_policy':'RESEARCH_D_V1',
          'indicators':eligibility['parameters'],'calendar':inspection['paper_auto_calendar'],
          'evidence_at':stamp(now),'evidence_expires_at':stamp(now+timedelta(minutes=minutes)),
          'execution_requirements':eligibility['execution_requirements'],'paper_eligibility':s}
    validate_structure(plan)
    endpoint=SessionConfiguration.load(root)
    return {'schema_version':1,'scope':PERMISSION,'execution_mode':'PaperAuto','status':'Granted','authorized':True,
        'environment':'PAPER_TRADING','live_enabled':False,'account':b.account,'account_binding_id':b.binding_id,
        'granted_by':os.environ.get('USERNAME','local-operator'),'confirmed_at':stamp(now),'granted_at':stamp(now),
        'expires_at':stamp(now+timedelta(minutes=minutes)),'revoked':False,'emergency':False,
        'paper_checked':True,'identity_manual_match':True,'read_only_disabled_checked':True,'forex_permission_checked':True,
        'host':endpoint.host,'port':endpoint.port,'client_id':82,'session_id':__import__('uuid').uuid4().hex,
        'mode':'StrategyPaper','risk_profile':EXPERIMENTAL,'continuous':True,'diagnostic_loss_budget':0,
        'instruments':['EUR/USD'],'order_types':['LMT','STP'],'max_experiments':1,'max_quantity':100,
        'max_notional_usd':250,'max_hold_seconds':300,'manage_owned_positions_after_stop':True,
        'strategy_versions':[s['strategy_version']],'strategy_version':s['strategy_version'],
        'selected_strategy':s['strategy_id'],'strategy_requirements_verified':True,'strategy_plan':plan,
        'execution_requirements':eligibility['execution_requirements'],'source_hashes':eligibility['source_hashes']}

def save_permission(root,record):
    from .paper_identity import protect
    path=Path(root)/'.local/paper-auto-authorization.dpapi'
    data=json.dumps(record).encode();temporary=path.with_suffix('.'+__import__('uuid').uuid4().hex+'.tmp')
    try:
        with temporary.open('xb') as stream:stream.write(protect(data));stream.flush();os.fsync(stream.fileno())
        temporary.replace(path)
    finally:temporary.unlink(missing_ok=True)

def summary(result):
    strategy=result.get('strategy')
    return {**{k:v for k,v in result.items() if k not in ('calendar','strategy')},
        'calendar':result.get('calendar',{}).get('status','UNVERIFIED'),
        'strategy':{k:strategy[k] for k in ('strategy_id','strategy_version','state','risk_probe')} if strategy else None}

def main(root,action='status',minutes=480,strategy=None,owner_consent=False):
    root=Path(root);b=binding(root)
    if action=='revoke':
        record=read_permission(root)
        if record:
            record.update(status='Revoked',revoked=True,revoked_at=stamp());save_permission(root,record)
        audit(root,b,'PAPER_AUTO_AUTHORIZATION_REVOKED')
        print(json.dumps({'event':'PAPER_AUTO_AUTHORIZATION_REVOKED','account':b.masked_account,'live_enabled':False}));return
    inspection=json.loads((root/'artifacts/paper-lab/data-diagnostics.json').read_text())
    eligibility=evaluate(root,inspection,b)
    result=readiness(root,inspection,eligibility,b,read_permission(root))
    if action=='grant':
        if not owner_consent:raise PermissionError('EXPLICIT_PAPER_AUTO_OWNER_CONSENT_REQUIRED')
        if not all(result['conditions'][k]=='PASS' for k in result['conditions'] if k!='PAPER_AUTHORIZATION'):
            raise PermissionError('PAPER_AUTO_GRANT_PREFLIGHT_BLOCKED')
        record=proposal(root,inspection,eligibility,b,minutes,strategy);save_permission(root,record)
        (root/'.local/paper-auto.stop').unlink(missing_ok=True)
        audit(root,b,'PAPER_AUTO_AUTHORIZATION_GRANTED',expires_at=record['expires_at'],strategy_version=record['strategy_version'])
        result=readiness(root,inspection,eligibility,b,record)
    path=root/'artifacts/paper-lab/paper-auto-status.json';path.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(summary(result)))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--action',choices=['status','grant','revoke'],default='status')
    p.add_argument('--minutes',type=int,default=480);p.add_argument('--strategy');p.add_argument('--owner-consent',action='store_true');a=p.parse_args()
    try:main(a.root,a.action,a.minutes,a.strategy,a.owner_consent)
    except Exception as e:
        from .paper_lab_diagnostics import safe_reason
        print(json.dumps({'state':'PAPER_AUTO_BLOCKED','reason':safe_reason(e),'orders_sent':0,'live_enabled':False}));raise SystemExit(1)
