"""Bounded, source-linked research memory. Never broker data or model training."""
from copy import deepcopy
import hashlib
import sqlite3
from .contracts import encoded,digest,strict_json,text,number,candidate_version,ProposalValidationError,validate_research_plan
from .data import FOLDER,safe_path,read
from .journal import verify_event_chain,memory_rows,memory_rejections,memory_decisions
from .costs import cost_assumptions
from .execution_memory import load as load_execution,compact as compact_execution
from .simulation_memory import load as load_simulation,compact as compact_simulation

AUDIT='artifacts/test-results/ai-strategy-research/h40-accounting-audit'
METRICS=('admitted','rejected','net_pnl','gross_pnl','commissions','spread_slippage',
         'win_rate','net_expectancy','profit_factor','maximum_drawdown','pending_position',
         'opening_commissions','closing_commissions','commissions_incurred','portfolio_net_pnl')


def metric_summary(metrics):
    return {k:metrics[k] for k in METRICS if k in metrics}


def family(candidate):
    # Risk, name, inert EMA windows for MR, and one/two-bar parameter nudges
    # cannot escape a family. Genuine horizon/pattern/instrument changes can.
    return digest({k:candidate[k] for k in ('symbol','timeframe_minutes','pattern')})


def record(entry_id,session,proposal,result,state,provider):
    c=proposal['candidate']
    for k in ('hypothesis','rationale'):text(proposal[k],2000)
    folds=result.get('results',{}) if result else {}
    validation=folds.get('TIERED_BASE',{}).get('validation',{})
    m=metric_summary(validation.get('metrics',{}))
    reasons=result.get('rejection_reasons',[]) if result else ['RESULT_NOT_DEFINITIVE']
    economics=m.get('net_expectancy')
    failed=state=='COMPLETED' and economics is not None and number(economics)<=0
    return dict(evidence_id='memory_'+entry_id,session=session,version=candidate_version(c),
        family=family(c),candidate=c,hypothesis=proposal['hypothesis'],rationale=proposal['rationale'],
        research_plan=proposal.get('research_plan'),
        state=state,metrics=m,reasons=reasons,
        confidence=result.get('confidence',{}) if result else {},
        windows={model:{fold:metric_summary(r['metrics']) for fold,r in results.items()}
                 for model,results in folds.items()},
        pending_inventory={model:{fold:r.get('inventory',{}).get('positions',[]) for fold,r in results.items()
                          if r['metrics'].get('pending_position')} for model,results in folds.items()},
        pending_detail_status='AVAILABLE' if result and result.get('cost_version') else 'LEGACY_NOT_RECORDED',
        limitations=result.get('validation_limitations',[]) if result else [],
        cost_version=result.get('cost_version','LEGACY_UNSEGREGATED_ESTIMATE') if result else 'UNKNOWN',
        proposal_origin='REAL_OPENAI_PROPOSAL' if provider=='openai' else 'SIMULATED_PROVIDER_PROPOSAL',
        evidence_status=dict(record='CONFIRMED_HASH_LINKED_RECORD',performance='SIMULATED',costs='ESTIMATED',execution='UNKNOWN'),
        conclusion='OBSERVED_NET_OBJECTIVE_FAILED' if failed else 'INSUFFICIENT_OR_UNRESOLVED_EVIDENCE',
        refutation_scope='FIXED_EXECUTABLE_CANDIDATE_IN_THIS_COST_DATA_SCENARIO_ONLY_NOT_CAUSAL_HYPOTHESIS',
        hypothesis_text_is_untrusted_not_executable=True,fresh_out_of_sample=False)


def build(root,rows,package,chain_hash,rejections=None,decisions=None):
    entries=[record(r['id'],r['session'],r['proposal'],r['result'],r['state'],r['provider']) for r in rows]
    for entry,row in zip(entries,rows):
        entry['dataset_sha256']=strict_json(row['binding'])['dataset_sha256']
        entry['result_sha256']=digest(row['result']) if row['result'] else None
    audit_path=safe_path(root,AUDIT+'/verification.json');sources=[]
    if audit_path.exists() or safe_path(root,AUDIT+'/revalidation-final.json').exists():
        proof,proof_sha=read(root,AUDIT+'/verification.json',maximum=200000)
        audited,result_sha=read(root,AUDIT+'/revalidation-final.json',maximum=4_000_000)
        if proof.get('artifact_hashes',{}).get('revalidation-final.json')!=result_sha or proof.get('final_holdout_sealed') is not True or audited.get('final_holdout_evaluated') is not False:
            raise ValueError('RESEARCH_MEMORY_AUDIT_INTEGRITY_FAILED')
        matches=[r for r in rows if candidate_version(r['proposal']['candidate'])==audited.get('version')]
        if not matches or any(r['proposal']['candidate']!=audited['candidate'] for r in matches):
            raise ValueError('RESEARCH_MEMORY_AUDIT_BINDING_FAILED')
        prior=matches[-1]
        if audited.get('execution_authorized') is not False or audited.get('live_approved') is not False:
            raise ValueError('RESEARCH_MEMORY_AUDIT_NOT_SIMULATION')
        imported=record('audit_'+result_sha[:20],prior['session'],prior['proposal'],audited,'COMPLETED',prior['provider'])
        imported.update(supersedes_evidence_id='memory_'+prior['id'],source_sha256=result_sha,
                        dataset_sha256=strict_json(prior['binding'])['dataset_sha256'],
                        audit_notes=['BOTH_LEGACY_FEE_SIDES_COUNTED_ONCE','PENDING_BUY_AND_NAV_OMITTED_FROM_LEGACY_PORTFOLIO',
                                     'AUDITED_COSTS_NOT_VERIFIED_ACCOUNT_FEES'])
        entries.append(imported);sources.append(dict(path=AUDIT+'/revalidation-final.json',sha256=result_sha,verification_sha256=proof_sha))
    decisions=decisions or dict(deferred=[],sessions=[],calls=[])
    for d in decisions['deferred']:
        raw=safe_path(root,FOLDER+'/memory/'+d['memory_sha256']+'.json').read_bytes()
        if len(raw)>8_000_000 or hashlib.sha256(raw).hexdigest()!=d['memory_sha256']:
            raise ValueError('RESEARCH_DEFER_MEMORY_INTEGRITY_FAILED')
        original=strict_json(raw)
        ids=[e['evidence_id'] for e in original['entries']]+[e['evidence_id'] for e in original.get('deferred_decisions',[])]
        ids+=[e['evidence_id'] for e in original.get('new_readonly_evidence',[])]
        ids+=['authentic_development_prices','data_integrity_773']+[e['evidence_id'] for e in package['previous_failures']]
        validate_research_plan(d['research_plan'],ids)
        if d['research_plan']['action']!='DEFER_RESEARCH':raise ValueError('RESEARCH_DEFER_ACTION_INVALID')
    snapshot=dict(schema_version=2,mode='SIMULATION_ONLY',entries=entries,sources=sources,
        history_sha256=digest(rows),event_chain_head=chain_hash,limitations=package['limitations'],
        proposal_rejections=rejections or [],
        deferred_decisions=decisions['deferred'],session_conclusions=decisions['sessions'],provider_outcomes=decisions['calls'],
        broker_constraints=package['broker_constraints'],cost_assumptions=cost_assumptions(),
        learning='PERSISTENT_EVIDENCE_AND_FEEDBACK_NOT_MODEL_RETRAINING',
        specification_authority='FIXED_EXECUTABLE_CANDIDATE_NOT_UNTRUSTED_MODEL_DESCRIPTION',
        data_policy='ALREADY_USED_2021_2023__NO_FRESH_INDEPENDENT_OOS__FINAL_SEALED',
        final_holdout_sealed=True,execution_authorized=False)
    snapshot['execution_observations']=load_execution(root)
    snapshot['simulation_observations']=load_simulation(root)
    return snapshot


def load_readonly(root,package):
    path=safe_path(root,FOLDER+'/journal.sqlite3')
    if not path.exists():return build(root,[],package,'0'*64)
    db=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
    try:
        db.execute('BEGIN')
        return build(root,memory_rows(db),package,verify_event_chain(db),memory_rejections(db),memory_decisions(db))
    finally:db.close()


def persist(root,snapshot):
    raw=encoded(snapshot);sha=hashlib.sha256(raw).hexdigest()
    if len(raw)>8_000_000:raise ValueError('RESEARCH_MEMORY_SIZE_LIMIT')
    path=safe_path(root,FOLDER+'/memory/'+sha+'.json');path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        if path.read_bytes()!=raw:raise ValueError('RESEARCH_MEMORY_TAMPERED')
    else:
        with path.open('xb') as f:f.write(raw)
    return sha


def compact(snapshot,limit=6500):
    superseded={e.get('supersedes_evidence_id') for e in snapshot['entries']}
    # Recency + real provenance, never favorable P&L. Keep all history for gates;
    # only the prompt is compacted. Audit replaces old H40 only in the prompt.
    ordered=sorted(enumerate(snapshot['entries']),key=lambda x:(x[1]['proposal_origin']=='REAL_OPENAI_PROPOSAL',x[0]),reverse=True)
    out=dict(schema_version=1,learning=snapshot['learning'],history_sha256=snapshot['history_sha256'],
             total_records=len(snapshot['entries']),omitted_records=0,records=[],
             data_policy=snapshot['data_policy'],execution_constraints=snapshot['broker_constraints'],
             cost_status='ESTIMATED_EFFECTIVE_ACCOUNT_UNKNOWN_MINIMUM_CAN_BE_OVERRIDDEN_BY_CAP',
             refutation_scope='OBSERVED_CANDIDATE_OBJECTIVE_FAILURE_NOT_GENERAL_PROOF')
    out['specification_authority']='CANDIDATE_FIELDS_AND_FIXED_ENGINE_NOT_MODEL_NARRATIVE'
    if snapshot.get('simulation_observations'):
        out['simulation_observations']=compact_simulation(snapshot['simulation_observations'])
    if snapshot.get('execution_observations'):
        out['execution_observations']=compact_execution(snapshot['execution_observations'])
        out['execution_observation_count']=len(snapshot['execution_observations'])
    out['contract_rejection_counts']={code:sum(r['code']==code for r in snapshot.get('proposal_rejections',[]))
        for code in sorted({r['code'] for r in snapshot.get('proposal_rejections',[])})}
    out['metric_keys']=dict(n='admitted',gross='gross_pnl',net='net_pnl',fees='commissions',
        friction='spread_slippage',win='win_rate',ev='net_expectancy',pf='profit_factor',dd='maximum_drawdown',pending='pending_position')
    reason_keys=sorted({reason for e in snapshot['entries'] for reason in e['reasons']})
    out['rejection_reason_keys']=reason_keys
    # Every unique executable spec is visible; duplicate runs and superseded
    # accounting remain in full memory. Never omit a specification silently.
    unique={}
    for _,e in ordered:
        if e['evidence_id'] not in superseded and e['version'] not in unique:unique[e['version']]=e
    out['specifications']=[dict(evidence_id=e['evidence_id'],session=e['session'],spec={k:v for k,v in e['candidate'].items() if k!='name'},
                                conclusion=e['conclusion'],metrics={k:e['metrics'].get(k) for k in ('admitted','net_pnl','commissions')}) for e in unique.values()]
    out['deferred_decisions']=[dict(evidence_id=d['evidence_id'],session=d['session'],at=d['at'],
        **{k:d['research_plan'][k][:80] for k in ('problem','insufficient_evidence','novelty','why_evaluate')})
        for d in snapshot.get('deferred_decisions',[])[-3:]]
    out['deferred_decision_count']=len(snapshot.get('deferred_decisions',[]))
    out['session_outcomes']=[dict(session=s['session'],state=s['state'],reason=s['reason']) for s in snapshot.get('session_conclusions',[])[-5:]]
    audited=[e for e in snapshot['entries'] if e.get('supersedes_evidence_id')]
    if audited:
        e=audited[-1];out['audited_accounting']=dict(net=e['metrics'].get('net_pnl'),fees=e['metrics'].get('commissions'),
            win=e['metrics'].get('win_rate'),pf=e['metrics'].get('profit_factor'),
            walk_forward={f:{k:m.get(k) for k in ('net_pnl','portfolio_net_pnl','pending_position')} for f,m in e['windows'].get('TIERED_BASE',{}).items() if f.startswith('wf')})
    if len(encoded(out))>limit:raise ValueError('RESEARCH_MEMORY_PROMPT_BOUND')
    for _,e in ordered:
        if e['evidence_id'] in superseded:continue
        summary={k:deepcopy(e[k]) for k in ('evidence_id','session','version','candidate','conclusion','cost_version')}
        summary['reasons']=[reason_keys.index(reason) for reason in e['reasons']]
        summary['metrics']={short:e['metrics'].get(full) for short,full in out['metric_keys'].items()}
        summary.update(hypothesis=e['hypothesis'][:100],evidence_status='SIMULATED_PERFORMANCE_ESTIMATED_COSTS_UNKNOWN_EXECUTION',
            confidence={k:e['confidence'].get(k) for k in ('sample_size','trade_days','net_win_wilson_95','net_expectancy_block_bootstrap_95')},
            walk_forward={fold:dict(n=m.get('admitted'),net=m.get('net_pnl'),pending=m.get('pending_position'),nav_net=m.get('portfolio_net_pnl'))
                          for fold,m in e['windows'].get('TIERED_BASE',{}).items() if fold.startswith('wf')},
            cost_sensitivity={model:m.get('validation',{}).get('net_pnl') for model,m in e['windows'].items()},
            fresh_out_of_sample=False)
        if 'portfolio_net_pnl' in e['metrics']:summary['portfolio_net_pnl']=e['metrics']['portfolio_net_pnl']
        if e.get('research_plan'):
            summary['prior_problem']=e['research_plan']['problem'][:100]
            summary['prior_refutation_test']=e['research_plan']['refutation_test'][:100]
        if e.get('audit_notes'):summary['audit_notes']=e['audit_notes']
        if len(encoded({**out,'records':out['records']+[summary]}))<=limit:out['records'].append(summary)
    out['omitted_records']=len(snapshot['entries'])-len(out['records'])
    # The complete spec ledger is sufficient when rich metrics cannot fit.
    if len(encoded(out))>limit:raise ValueError('RESEARCH_MEMORY_PROMPT_BOUND')
    return out


def validate_plan(proposal,snapshot):
    plan=proposal.get('research_plan')
    if plan is None:raise ProposalValidationError('RESEARCH_PLAN_REQUIRED','$.research_plan','EVIDENCE')
    entries=snapshot['entries'];refs=set(plan['prior_evidence_ids'])
    referenced=[e for e in entries if e['evidence_id'] in refs]
    if entries and not referenced:
        raise ProposalValidationError('PRIOR_RESEARCH_REFERENCE_REQUIRED','$.research_plan.prior_evidence_ids','EVIDENCE')
    if plan['action']=='DEFER_RESEARCH':return dict(classification='RESEARCH_DEFERRED',referenced=[e['evidence_id'] for e in referenced])
    related=[e for e in entries if e['family']==family(proposal['candidate'])]
    if any(e['state']!='COMPLETED' for e in related):
        raise ProposalValidationError('PRIOR_FAMILY_RESULT_NOT_DEFINITIVE','$.candidate','EVIDENCE')
    if not related:return dict(classification='NEW_EXECUTABLE_FAMILY',referenced=[e['evidence_id'] for e in referenced])
    prior=[e for e in related if e['evidence_id'] in refs]
    if not prior:raise ProposalValidationError('RELEVANT_PRIOR_REFERENCE_REQUIRED','$.research_plan.prior_evidence_ids','EVIDENCE')
    c=proposal['candidate']
    if any(e['version']==candidate_version(c) for e in related):
        raise ProposalValidationError('PREVIOUS_BEHAVIOR_ALREADY_RESEARCHED','$.candidate','EVIDENCE')
    # Closest related prior, not the most profitable one. Risk-only, names,
    # and parameters inert in the fixed MR grammar are not new hypotheses.
    inert={'name','risk_percent'}|({'fast'} if c['pattern']=='MEAN_REVERSION' else set())
    nearest=min(enumerate(related),key=lambda pair:(sum(pair[1]['candidate'][k]!=c[k] for k in c if k not in inert),-pair[0]))[1]
    changed=[k for k in c if k not in inert and nearest['candidate'][k]!=c[k]]
    if not changed:raise ProposalValidationError('MATERIALLY_EQUIVALENT_RESEARCH','$.candidate','EVIDENCE')
    if set(plan['changed_fields'])!=set(changed) or nearest['evidence_id'] not in refs:
        raise ProposalValidationError('MATERIAL_CHANGE_REFERENCE_REQUIRED','$.research_plan.changed_fields','EVIDENCE')
    if all(abs(number(c[k])-number(nearest['candidate'][k]))/max(abs(number(nearest['candidate'][k])),number('.0001'))<number('.2') for k in changed):
        raise ProposalValidationError('REPETITIVE_PARAMETER_NUDGE','$.candidate','EVIDENCE')
    return dict(classification='BOUNDED_NEW_HYPOTHESIS_IN_PRIOR_FAMILY',referenced=[e['evidence_id'] for e in referenced],changed_fields=changed)
