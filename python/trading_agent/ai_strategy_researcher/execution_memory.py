"""Immutable infrastructure observations. No orders, providers or final holdout."""
import hashlib
import json
from pathlib import Path
import sqlite3
from .contracts import encoded,digest
from .data import FOLDER,safe_path

DIRECTORY=FOLDER+'/execution-observations'

def save(root,value):
    raw=encoded(value);sha=hashlib.sha256(raw).hexdigest();p=safe_path(root,DIRECTORY+'/'+sha+'.json')
    p.parent.mkdir(parents=True,exist_ok=True)
    if p.exists():
        if p.read_bytes()!=raw:raise ValueError('EXECUTION_MEMORY_CONFLICT')
    else:
        with p.open('xb') as f:f.write(raw);f.flush();__import__('os').fsync(f.fileno())
    return sha

def load(root):
    try:return _load(root)
    except (KeyError,TypeError,sqlite3.Error) as exc:raise ValueError('EXECUTION_MEMORY_INVALID_OR_UNAVAILABLE') from None

def _load(root):
    out=[];paths=sorted(safe_path(root,DIRECTORY).glob('*.json'))
    if len(paths)>100:raise ValueError('EXECUTION_MEMORY_LIMIT')
    for p in paths:
        raw=p.read_bytes()
        if len(raw)>4_000_000 or hashlib.sha256(raw).hexdigest()!=p.stem:raise ValueError('EXECUTION_MEMORY_HASH_MISMATCH')
        v=json.loads(raw)
        if v['scope'] not in ('FORD_DIAGNOSTIC_R10','FORD_EXECUTION_DIAGNOSTIC_ONE_SHARE_V1') or v['classification']!='EXECUTION_DIAGNOSTICS' or v['environment']!='PAPER_TRADING' or v['strategy_version'] is not None or v['strategy_success'] is not False or v['profitability_evidence'] is not False or v['execution_authorized'] is not False:raise ValueError('EXECUTION_MEMORY_NOT_STRATEGY_EVIDENCE')
        source=v['source'];relative=source['journal_path']
        if relative!=f"artifacts/paper-diagnostics/ford/{v['trial_id']}/journal.sqlite3":raise ValueError('EXECUTION_MEMORY_SOURCE_SCOPE')
        db=sqlite3.connect(safe_path(root,relative).as_uri()+'?mode=ro',uri=True)
        try:
            rows=db.execute('SELECT * FROM events WHERE revision<=? ORDER BY revision LIMIT 20001',(source['reconciled_revision'],)).fetchall()
            if len(rows)>20000:raise ValueError('EXECUTION_MEMORY_SOURCE_LIMIT')
            previous='';report=None
            for index,(r,t,k,payload,prior,h) in enumerate(rows,1):
                state=json.loads(payload)['state']
                if r!=index or prior!=previous or digest([r,t,k,json.loads(payload),prior])!=h or state['scope']!=v['scope'] or state['trial_id']!=v['trial_id'] or state['binding_id']!=v['binding_id']:raise ValueError('EXECUTION_MEMORY_SOURCE_INTEGRITY')
                if r==source['revision']:
                    if k!='DIAGNOSTIC_CYCLE_SETTLED' or h!=source['event_hash']:raise ValueError('EXECUTION_MEMORY_RESULT_SOURCE')
                    report=json.loads(payload)['details']
                previous=h
            if not rows or rows[-1][0]!=source['reconciled_revision'] or previous!=source['reconciled_hash'] or state['intent'] or state['reservation']!='0' or report!=v['report'] or source['postgres_mirrored'] is not True:raise ValueError('EXECUTION_MEMORY_RESULT_NOT_DEFINITIVE')
        finally:db.close()
        out.append(dict(evidence_id='execution_'+p.stem,**v))
    return out

def compact(records):
    # No favorable-outcome selection. All sources remain in immutable storage.
    ordered=sorted(records,key=lambda r:(r['at'],r['evidence_id']))
    return [dict(evidence_id=r['evidence_id'],scope=r['scope'],status=r['evidence_status'],
        observed=r['observed'],expected=r['expected'],discrepancies=r['discrepancies'],
        net=r['report']['net_pnl'],decision=r['report']['decision'],limitations=r['limitations'],
        strategy_sample_size=0,profitability_evidence=False) for r in ordered[-2:]]
