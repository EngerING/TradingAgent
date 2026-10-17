"""Technical Paper eligibility of registered, unchanged research strategies.

This is independent of profitability/promotion/Live approval. Risk and execution
feasibility may reject every signal of a technically eligible strategy.
"""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
from enum import Enum
from .paper_lab import DotnetJournal,EXPERIMENTAL,num,stamp,utc,key,date
from .research_analysis import digest,STRATEGIES,analyze
from .research_indicators import DEFAULTS,settings

class StrategyEligibility(str,Enum):
    Candidate='Candidate'
    PaperEligible='PaperEligible'
    LiveApproved='LiveApproved'

SOURCE_FILES=('python/trading_agent/paper_eligibility.py','python/trading_agent/paper_auto.py',
 'python/trading_agent/paper_execution_wire.py','python/trading_agent/paper_strategy.py',
 'python/trading_agent/paper_lab.py','python/trading_agent/paper_lab_runner.py',
 'python/trading_agent/paper_lab_diagnostics.py','scripts/paper-lab.ps1',
 'python/trading_agent/research_analysis.py','python/trading_agent/research_indicators.py',
 'src/TradingAgent.Core/Risk.cs','src/TradingAgent.Core/PaperRiskProfile.cs',
 'src/TradingAgent.Core/ExecutionFeasibility.cs','src/TradingAgent.Core/ResearchExitSemantics.cs',
 'src/TradingAgent.Api/PaperLabCommand.cs','python/tests/test_paper_auto.py',
 'python/tests/test_paper_exact_exits.py','python/tests/test_strategy_continuous.py',
 'config/research-indicators.json','config/research-policy.json','config/paper-eligibility.json')

def source_hashes(root):
    return {name:hashlib.sha256((Path(root)/name).read_bytes()).hexdigest() for name in SOURCE_FILES}

def validate_structure(plan):
    from .paper_strategy import ENGINE
    if (plan.get('engine')!=ENGINE or plan.get('strategy_id') not in {s['id'] for s in STRATEGIES}
        or plan.get('instrument')!='EUR/USD' or plan.get('side')!='BUY' or plan.get('exit_policy')!='RESEARCH_D_V1'
        or not plan.get('strategy_version') or set(plan.get('indicators',{}))!=set(DEFAULTS)):
        raise PermissionError('PAPER_STRATEGY_STRUCTURE_INVALID')
    settings(plan['indicators'])
    receipt=plan.get('paper_eligibility',{})
    if (receipt.get('state')!='PaperEligible' or receipt.get('environment')!='PAPER_TRADING'
        or receipt.get('live_approved') is not False or receipt.get('registered') is not True
        or receipt.get('enabled') is not True or receipt.get('tests_passed') is not True
        or receipt.get('strategy_version')!=plan['strategy_version']
        or receipt.get('strategy_id')!=plan['strategy_id']):
        raise PermissionError('STRATEGY_PAPER_INELIGIBLE')
    return plan

def validate_runtime_plan(plan,now,versions,allow_expired=False):
    """Structural gate only. ExecutionFacts reliability remains RiskEngine's veto."""
    validate_structure(plan)
    if plan['strategy_version'] not in versions:raise PermissionError('STRATEGY_VERSION_NOT_AUTHORIZED')
    from .research_calendar import ForexCalendar
    calendar=ForexCalendar(plan['calendar'])
    if plan['calendar'].get('status') not in ('IBKR_HISTORICAL_SCHEDULE','IBKR_AUTHENTIC_SESSIONS','VERIFIED_EXPLICIT_SESSIONS'):
        raise PermissionError('IBKR_CALENDAR_UNVERIFIED')
    if not allow_expired and not calendar.start<=now.date()<=calendar.end:raise PermissionError('STRATEGY_CALENDAR_EXPIRED')
    if not allow_expired and now>=date(plan['evidence_expires_at']):raise PermissionError('STRATEGY_EVIDENCE_EXPIRED')
    r=plan['execution_requirements']
    for name in ('quoteToAccountFx','multiplier','minQuantity','quantityStep','marginRate','availableMargin',
                 'commissionFixedRoundTrip','commissionPerUnitRoundTrip','slippagePerUnit','adverseGapPerUnit'):
        num(r[name])
    if num(r['marginRate'])!=1 or num(r['availableMargin'])>100 or r['execution'].get('environment')!='PAPER_TRADING':
        raise PermissionError('PAPER_RISK_CONFIGURATION_CHANGED')
    return plan

def tests_receipt(root):
    root=Path(root);path=root/'artifacts/test-results/paper-eligibility-tests.json';hashes=source_hashes(root)
    if path.exists():
        old=json.loads(path.read_text(encoding='utf-8-sig'))
        if old.get('passed') is True and old.get('source_hashes')==hashes:return old
    env=__import__('os').environ.copy();env['PYTHONPATH']=str(root/'python')+';'+str(root/'python/tests')
    names=['test_paper_auto','test_paper_exact_exits.ExactExitTests','test_paper_exact_exits.ExactRunnerTests',
           'test_strategy_continuous.ContinuousPaperTests','test_paper_execution_wire.ExecutionWireTests']
    result=subprocess.run([str(root/'.venv/Scripts/python.exe'),'-m','unittest',*names],
        cwd=root,env=env,capture_output=True,text=True,timeout=120)
    proof={'passed':result.returncode==0,'at':stamp(),'source_hashes':hashes,'test_classes':names,
           'scope':'STRUCTURAL_PAPER_ONLY_NOT_EXECUTION_EQUIVALENCE_OR_LIVE'}
    path.parent.mkdir(parents=True,exist_ok=True)
    (path.with_suffix('.txt')).write_text(result.stdout+result.stderr,encoding='utf-8')
    path.write_text(json.dumps(proof,indent=2),encoding='utf-8');return proof

def requirements(inspection):
    # Observe simulated fees without representing them as real Live costs.
    r={'quoteToAccountFx':1,'multiplier':1,'minQuantity':inspection['contract']['minimum_size_metadata'],
       'quantityStep':inspection['contract']['size_increment_metadata'],'marginRate':1,'availableMargin':100,
       'commissionFixedRoundTrip':4,'commissionPerUnitRoundTrip':0,'slippagePerUnit':'.00045','adverseGapPerUnit':'.00005',
       'execution':{'source':'PAPER_OBSERVED_USD2_PER_SIDE_CONSERVATIVE_SLIPPAGE_UNVERIFIED_MARGIN',
        'environment':'PAPER_TRADING','mode':'ODD_LOT','openingCommission':2,'closingCommission':2,
        'costsReliable':False,'marginReliable':False,'contractReliable':True,'brokerPermitsEntry':False,
        'equivalentRealAccount':{'minimumQuantity':None,'quantityStep':None,'marginRate':None,'maximumLeverage':1,
            'instrumentPermitted':None,'executionModePermitted':None,'accountEligible':None}}}
    # Unknown conditions are intentionally retained for unchanged ExecutionFeasibility.
    return r

def evaluate_registered(rows,analysis,enabled,proof,risk_probe):
    records=[]
    for row in rows:
        version=row['strategy'];spec=json.loads(version['parametersJson']);id=spec.get('id');reasons=[]
        expected=next((s for s in analysis['strategies'] if s['id']==id),None)
        if expected is None or spec!=expected:reasons.append('REGISTERED_PARAMETERS_NOT_EQUIVALENT')
        if id not in enabled or row.get('registration',{}).get('enabled',True) is not True or row.get('registration',{}).get('state')=='SUSPENDED':reasons.append('STRATEGY_DISABLED')
        if not proof.get('passed'):reasons.append('ASSOCIATED_TESTS_NOT_PASSED')
        if version.get('instrument')!='EUR/USD' or version.get('version')!=1:reasons.append('UNSUPPORTED_REGISTERED_STRATEGY')
        if set(analysis['parameters'])!=set(DEFAULTS):reasons.append('REQUIRED_PARAMETERS_MISSING')
        try:
            settings(analysis['parameters'])
            risk=risk_probe()
            if not isinstance(risk.get('allowed'),bool):raise ValueError()
        except Exception:reasons.append('RISK_ENGINE_UNHEALTHY');risk=None
        records.append({'strategy_id':id,'strategy_version':row['hash'],'name':version['name'],
            'state':'Candidate' if reasons else 'PaperEligible','registered':True,'enabled':id in enabled,
            'tests_passed':proof.get('passed') is True,'environment':'PAPER_TRADING','live_approved':False,
            'event':'STRATEGY_PAPER_INELIGIBLE' if reasons else 'STRATEGY_PAPER_ELIGIBLE','reasons':reasons,
            'parameters_hash':spec.get('parameters_hash'),'risk_probe':risk})
    return records

def evaluate(root,inspection,binding,*,proof=None):
    root=Path(root);core=DotnetJournal(root,EXPERIMENTAL)
    rows=core.command({'operation':'paper-strategy-registry','account_key':key(binding.account)})
    from .paper_economic_sweep import ARTIFACT
    analysis=json.loads((root/ARTIFACT).read_text(encoding='utf-8-sig'))['research']['analysis']
    # Registry also contains earlier research configurations. Bind the exact
    # already-investigated six-month versions, never choose by name or newest.
    rows=[r for r in rows if r['strategy']['version']==1 and
        r['strategy']['strategyId']==f"research-d-{json.loads(r['strategy']['parametersJson']).get('id')}-{analysis['config_hash'][:12]}"]
    config=json.loads((root/'config/paper-eligibility.json').read_text())
    if config.get('schema_version')!=1 or set(config['enabled'])-{'trend','pullback','mean_reversion'}:
        raise PermissionError('PAPER_ELIGIBILITY_CONFIGURATION_INVALID')
    proof=proof or tests_receipt(root)
    # Replay real stored Signal/NoSignal production analysis; never revive a signal.
    replay=analyze({'instrument':'EUR/USD','source':'IBKR_TWS','what_to_show':'MIDPOINT','as_of':analysis['as_of'],
        'indicators':analysis['parameters'],'calendar':analysis['calendar'],
        'originals':{m:[{**b,'opened_at':b['opened_at']} for b in analysis['normalized'][m]] for m in ('15','60','240')}})
    if replay['strategies']!=analysis['strategies']:raise PermissionError('STRATEGY_SIGNAL_REPLAY_MISMATCH')
    account=core.strategy_initial();r=requirements(inspection);q=inspection['quote']
    probe=copy.deepcopy(r);probe.update(instrument='EUR/USD',side='BUY',bid=q['bid'],ask=q['ask'],
        stop=str(num(q['bid'])-num('.001')),marketAt=q['at'])
    probe['execution'].update(at=q['at'],takeProfit=str(num(q['ask'])+num('.0015')),quoteStatus=q['type'])
    records=evaluate_registered(rows,analysis,config['enabled'],proof,lambda:core.strategy_risk(account,probe))
    if len({x['strategy_id'] for x in records})!=len(records):raise PermissionError('PAPER_REGISTRY_AMBIGUOUS')
    result={'at':stamp(),'strategies':records,'preferred':config['preferred'],'source_hashes':source_hashes(root),
            'scope':'STRUCTURAL_PAPER_ELIGIBILITY_NOT_PROMOTION_OR_LIVE','risk_profile':EXPERIMENTAL,
            'parameters':analysis['parameters'],'execution_requirements':r}
    from .ibkr_session import StructuredSessionEvents
    audit=StructuredSessionEvents(root/'artifacts/paper-lab/session-events.jsonl')
    for s in records:
        audit({'event':s['event'],'at':stamp(),'account':binding.masked_account,'environment':'PAPER_TRADING',
            'strategy_id':s['strategy_id'],'strategy_version':s['strategy_version'],'reasons':s['reasons'],'live_enabled':False})
    path=root/'artifacts/paper-lab/paper-eligibility.json';path.write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result
