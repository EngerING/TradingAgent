"""Hash-linked Forex simulation evidence, separate from observed Paper fills."""
import hashlib
import json
from pathlib import Path
from .contracts import encoded
from .data import FOLDER, safe_path

DIRECTORY = FOLDER+'/simulation-observations'


def validate(report):
    if (report.get('classification') != 'SIMULATED_RESEARCH' or report.get('profile', {}).get('profile') != 'EURUSD_PAPER_RESEARCH_100'
            or report.get('broker_orders') != 0 or report.get('openai_calls') != 0
            or report.get('final_holdout_opened') is not False or report.get('parameters_changed') is not False):
        raise ValueError('SIMULATION_MEMORY_SCOPE_REQUIRED')
    return report


def save(root, path):
    root = Path(root).resolve(); path = Path(path).resolve()
    if not path.is_relative_to(root/'artifacts/research/eurusd-paper-research-100') or path.name != 'report.json':
        raise ValueError('SIMULATION_MEMORY_SOURCE_REQUIRED')
    raw = path.read_bytes(); report = validate(json.loads(raw))
    value = dict(evidence_id='eurusd_simulation_'+hashlib.sha256(raw).hexdigest(),
                 classification='SIMULATED_NOT_IBKR_EXECUTION', source_path=str(path.relative_to(root)).replace('\\', '/'),
                 source_sha256=hashlib.sha256(raw).hexdigest(), decision=report['selection'],
                 fixed_round_trip_fee_usd=str(__import__('decimal').Decimal(report['costs']['openingCommission'])+__import__('decimal').Decimal(report['costs']['closingCommission'])),
                 initial_risk_budget_usd='1', admitted=sum(r['admitted'] for r in report['results']),
                 completed_trades=sum(r['metrics']['completed_trades'] for r in report['results']),
                 parameters_changed=False, fresh_oos=False, execution_authorized=False,
                 cost_status='OBSERVED_ONE_PAPER_CYCLE_FEES_CONSERVATIVE_MODELED_FRICTION_OTHER_SIZES_UNKNOWN',
                 conclusion='COSTS_EXCEED_ONE_PERCENT_RISK_NO_FORCED_TRADES', strategy_versions=report['strategy_versions'])
    data = encoded(value); digest = hashlib.sha256(data).hexdigest(); target = safe_path(root, DIRECTORY+'/'+digest+'.json')
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        with target.open('xb') as f: f.write(data)
    elif target.read_bytes() != data: raise ValueError('SIMULATION_MEMORY_CONFLICT')
    return digest


def load(root):
    out = []; paths = sorted(safe_path(root, DIRECTORY).glob('*.json'))
    if len(paths) > 100: raise ValueError('SIMULATION_MEMORY_LIMIT')
    for path in paths:
        raw = path.read_bytes()
        if len(raw) > 100000 or hashlib.sha256(raw).hexdigest() != path.stem: raise ValueError('SIMULATION_MEMORY_HASH_MISMATCH')
        value = json.loads(raw); source = safe_path(root, value['source_path'])
        if not value['source_path'].startswith('artifacts/research/eurusd-paper-research-100/run-') or source.name != 'report.json': raise ValueError('SIMULATION_MEMORY_SOURCE_REQUIRED')
        report_raw = source.read_bytes()
        if len(report_raw) > 8000000 or hashlib.sha256(report_raw).hexdigest() != value['source_sha256']: raise ValueError('SIMULATION_MEMORY_SOURCE_CHANGED')
        report = validate(json.loads(report_raw))
        if value['classification'] != 'SIMULATED_NOT_IBKR_EXECUTION' or value['execution_authorized'] is not False or value['admitted'] != sum(r['admitted'] for r in report['results']): raise ValueError('SIMULATION_MEMORY_CLASSIFICATION_INVALID')
        if value['evidence_id'] != 'eurusd_simulation_'+value['source_sha256']: raise ValueError('SIMULATION_MEMORY_IDENTITY_INVALID')
        out.append(value)
    return out+load_shadow(root)


def save_shadow(root,study,revision,head,handoff):
    import re
    if not re.fullmatch(r'eurusd-shadow-[a-f0-9]{32}',study):raise ValueError('SHADOW_MEMORY_SCOPE')
    directory=safe_path(root,FOLDER+'/shadow-observations')
    for existing in directory.glob('*.json'):
        data=existing.read_bytes()
        if hashlib.sha256(data).hexdigest()!=existing.stem:raise ValueError('SHADOW_MEMORY_HASH')
        if json.loads(data).get('evidence_id')=='shadow_'+handoff['sha256']:return existing.stem
    # Caller invokes only after successful PostgreSQL mirroring. The referenced
    # SQLite event is also verified independently whenever AI memory is loaded.
    value=dict(evidence_id='shadow_'+handoff['sha256'],classification='SIMULATED_SHADOW_NOT_BROKER_EXECUTION',
        study=study,journal_path=f'artifacts/research/eurusd-shadow/{study}/journal.sqlite3',revision=revision,
        event_hash=head,postgres_mirrored=True,handoff=handoff)
    raw=encoded(value);digest=hashlib.sha256(raw).hexdigest();p=safe_path(root,FOLDER+'/shadow-observations/'+digest+'.json')
    p.parent.mkdir(parents=True,exist_ok=True)
    if not p.exists():
        with p.open('xb') as f:f.write(raw)


def load_shadow(root):
    import sqlite3
    from trading_agent.eurusd_paper_research import sha
    out=[];paths=sorted(safe_path(root,FOLDER+'/shadow-observations').glob('*.json'))
    if len(paths)>100:raise ValueError('SHADOW_MEMORY_LIMIT')
    for p in paths:
        raw=p.read_bytes()
        if len(raw)>10000 or hashlib.sha256(raw).hexdigest()!=p.stem:raise ValueError('SHADOW_MEMORY_HASH')
        v=json.loads(raw);source=safe_path(root,v['journal_path'])
        if v['journal_path']!=f"artifacts/research/eurusd-shadow/{v['study']}/journal.sqlite3" or v['postgres_mirrored'] is not True:raise ValueError('SHADOW_MEMORY_SOURCE')
        db=sqlite3.connect(source.as_uri()+'?mode=ro',uri=True);head='';state=None
        try:
            rows=db.execute('SELECT * FROM events WHERE revision<=? ORDER BY revision LIMIT 100001',(v['revision'],)).fetchall()
            if len(rows)!=v['revision'] or len(rows)>100000:raise ValueError('SHADOW_MEMORY_CHAIN_LENGTH')
            for i,(revision,payload,previous,h) in enumerate(rows,1):
                event=json.loads(payload)
                if revision!=i or previous!=head or sha([revision,event,previous])!=h or event['study_id']!=v['study'] or event['classification']!='SIMULATED_SHADOW' or event['broker_orders']!=0 or event['execution_authorized'] is not False:raise ValueError('SHADOW_MEMORY_CHAIN')
                head=h;state=event['state']
        finally:db.close()
        if head!=v['event_hash'] or state['research_handoff']!=v['handoff']:raise ValueError('SHADOW_MEMORY_HANDOFF_LINK')
        path=safe_path(root,v['handoff']['path']);report=json.loads(path.read_bytes())
        if sha(report)!=v['handoff']['sha256'] or report['classification']!='SIMULATED_SHADOW' or report['execution_authorized'] is not False or report['automatic_adoption'] is not False or report['broker_orders']!=0:raise ValueError('SHADOW_MEMORY_HANDOFF_INTEGRITY')
        out.append(dict(evidence_id=v['evidence_id'],classification=v['classification'],decision='INDEPENDENT_VALIDATION_REQUIRED',
                        fixed_round_trip_fee_usd='4_ESTIMATED_OTHER_SIZES',initial_risk_budget_usd='R1_1_R5_5_R10_10',
                        admitted=report['calibration']['sample_size'],completed_trades=report['calibration']['sample_size'],
                        cost_status='SIMULATED_FEES_SPREAD_SLIPPAGE_NOT_BROKER_MEASUREMENTS',conclusion='NEW_SHADOW_EVIDENCE_NOT_AUTOMATIC_APPROVAL'))
    return out


def compact(values):
    # Recency of content-addressed imports is not a performance ranking.
    return [dict(evidence_id=v['evidence_id'],classification=v['classification'],decision=v['decision'],
                 fees_usd=v['fixed_round_trip_fee_usd'],risk_usd=v['initial_risk_budget_usd'],n_closed=v['completed_trades'])
            for v in values[-1:]]
