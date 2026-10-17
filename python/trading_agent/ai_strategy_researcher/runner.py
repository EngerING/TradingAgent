"""Bounded autonomous proposal -> deterministic experiment -> persistent conclusion."""
from pathlib import Path
import hashlib
import time
from .contracts import encoded,digest,parse_proposal,ProposalValidationError,candidate_version,utc
from .configuration import load
from .data import load_dataset,context,write,FOLDER,safe_path
from .journal import Journal,exclusive,session_name
from .providers import request_body,simulated_response
from .tools import run_worker,worker_environment
from .memory import build as build_memory,compact,persist,validate_plan


def tool_hash(root):
    folder=Path(root)/'python/trading_agent/ai_strategy_researcher'
    return digest({p.name:digest(p.read_text(encoding='utf-8')) for p in sorted(folder.glob('*.py'))})


def ranking(status):
    rows=[]
    for e in status['experiments']:
        r=e['result']
        if e['state']!='COMPLETED' or not r:continue
        m=r['results']['TIERED_BASE']['validation']['metrics']
        worst=min(r['results'][cost]['validation']['metrics']['net_pnl'] for cost in r['results'])
        rows.append(dict(version=e['version'],name=r['candidate']['name'],status=r['status'],
            risk_percent=r['candidate']['risk_percent'],metrics=m,confidence=r['confidence'],
            robustness_worst_net_pnl=worst,rejection_reasons=r['rejection_reasons'],
            independent_validation_required=True,execution_authorized=False,live_approved=False))
    # Lexicographic and transparent: evidence, net expectation, cost robustness, drawdown, win rate.
    rows.sort(key=lambda x:(x['status']=='INDEPENDENT_VALIDATION_REQUIRED',
        x['metrics']['net_expectancy'] if x['metrics']['net_expectancy'] is not None else -1e12,
        x['robustness_worst_net_pnl'],-x['metrics']['maximum_drawdown'],
        x['metrics']['win_rate'] if x['metrics']['win_rate'] is not None else -1),reverse=True)
    return rows


def report(root,journal,session,dataset_sha):
    s=journal.status(session);rows=ranking(s)
    result=dict(module='AI_Strategy_Researcher',mode='SIMULATION_ONLY',at=utc(),session=session,
        decision='INDEPENDENT_VALIDATION_REQUIRED' if any(r['status']=='INDEPENDENT_VALIDATION_REQUIRED' for r in rows)
            else 'NO_VIABLE_STRATEGY_FOUND',
        dataset_sha256=dataset_sha,session_state=s['state'],stop_reason=s['reason'],
        consumption={k:s[k] for k in ('provider_calls','input_tokens','output_tokens','estimated_or_reserved_cost_usd',
            'backtests_reserved','candidates')},ranking=rows,
        openai_requests=sum(c['provider']=='openai' for c in s['calls']),
        hypotheses=[dict(version=e['version'],proposal=e['proposal'],state=e['state']) for e in s['experiments']],
        cost_status='ESTIMATED_FROM_API_USAGE_AND_CONFIGURED_CEILINGS; UNKNOWN_CALLS_RETAIN_FULL_RESERVE',
        conclusion='Exploratory research only. Fresh independent evidence, corporate actions and verified IBKR capabilities required.',
        memory_is_persistent_experiments_not_model_retraining=True,
        final_holdout_sealed=True,paper_auto_granted=False,orders_sent=0,live_approved=False,
        execution_authorized=False)
    relative=FOLDER+'/sessions/'+session+'/report.json';write(root,relative,result)
    lines=['# AI_Strategy_Researcher — simulación','',f"**{result['decision']}**. Sesión `{session}`: {s['state']} ({s['reason']}).",
        '', 'La clasificación es exploratoria. Ningún candidato recibe promoción, autorización Paper o aprobación Live.',
        'Desarrollo histórico 2021–2023 ya examinado; validación 2022–2023 y tres folds causales sin reajuste. El modelo puede aprender del registro de resultados; esos folds dejan de ser evidencia independiente. Prueba final 2025–2026 y selección 2024 no se exportan a herramientas ni al modelo. Los resúmenes antiguos de selección ya conocidos están etiquetados como evidencia previa.',
        'SCHX excluido por cuarentena. F/SPY: acciones enteras, exposición 1×, capital US$100, riesgo 1–15%, pérdidas acumuladas US$20, costos y gaps conservadores, fondos T+1 simulado y una posición. Permisos, tarifa efectiva, margen/intradía, fracciones, liquidez y protección IBKR UNKNOWN; no se declara viabilidad ejecutable.',
        '', '| Candidato | Riesgo % | N validación | Win neto | Expectativa | P&L neto | Comisiones | DD | Peor neto por costos | Estado |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|---|']
    def fmt(x):return 'N/D' if x is None else f'{x:.4f}'
    for r in rows:
        m=r['metrics'];lines.append(f"| {r['name']} | {r['risk_percent']} | {m['admitted']} | {fmt(m['win_rate'])} | {fmt(m['net_expectancy'])} | {fmt(m['net_pnl'])} | {fmt(m['commissions'])} | {fmt(m['maximum_drawdown'])} | {fmt(r['robustness_worst_net_pnl'])} | {r['status']} |")
        lines.append('')
    lines+=['', 'Ranking: evidencia suficiente, expectativa neta, robustez a costos, menor drawdown y acierto. No elegir por acierto aislado. N=0 no es una estrategia ganadora.',
        'Rechazos, intervalos Wilson95/ajustados, bootstrap diario aproximado, PF, pérdidas medias, gaps, días detenidos y muestras de operaciones en el journal/resultados. Drawdown incluye marcado conservador intrabar; stops no limitan gaps.',
        '', 'Consumo: '+encoded(result['consumption']).decode()+'. Costos estimados, no factura verificada. Proveedor simulado consume cero tokens/costo API.',
        'Los candidatos son JSON declarativos inmutables con versión/hash; no se ejecuta código generado. Herramientas fijas con timeout y entorno sin credenciales IBKR. La memoria contiene hipótesis/experimentos/conclusiones, no reentrenamiento automático.',
        'Emergencia sin cambios. PaperAuto no concedido. Cero órdenes. Live bloqueado. Validación final formal requiere un proceso independiente futuro; este CLI no puede abrirla.']
    safe_path(root,FOLDER+'/sessions/'+session+'/report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return result


def run(root,session,provider='simulated',provider_fn=None,tool_fn=None):
    session_name(session)
    if provider not in ('simulated','openai'):raise ValueError('PROVIDER_NOT_ALLOWED')
    config=load(root,provider=='openai');package,sha=load_dataset(root)
    evidence=None
    if provider=='openai' and provider_fn is None:
        from ..paper_evidence_observer import research_preflight
        evidence=research_preflight(root)
        if evidence['decision']!='EVIDENCE_READY_FOR_RESEARCH':raise ValueError('NEW_EVIDENCE_REQUIRED_BEFORE_OPENAI')
    if provider=='openai' and provider_fn is None:worker_environment(root,True)  # require key before creating a session
    tool_fn=tool_fn or run_worker
    with exclusive(root):
        journal=Journal(root)
        try:
            s=journal.bind(session,dict(config=config,dataset_sha256=sha,provider=provider,tool_sha256=tool_hash(root)))
            streak=journal.failure_state(session);failures=streak['count'];feedback=streak['feedback']
            while s['state']=='ACTIVE':
                if failures>=config['max_consecutive_provider_failures']:
                    journal.stop(session,'SUSPENDED',streak['reason'] or 'INVALID_PROPOSAL_CIRCUIT_OPEN');break
                if s['candidates']>=config['max_candidates']:
                    journal.stop(session,'COMPLETED','CANDIDATE_LIMIT_REACHED');break
                if journal.remaining_seconds(session)<=0:
                    journal.stop(session,'BUDGET_STOP','TIME_BUDGET_EXHAUSTED');break
                try:
                    memory=build_memory(root,journal.memory_records(),package,journal.verify_chain(),journal.memory_rejections(),journal.memory_decisions())
                    if evidence:
                        memory['new_readonly_evidence']=[dict(evidence_id='paper_observation_'+r['chain_head'][:20],
                            **{k:r[k] for k in ('study','spec_sha256','chain_head','decision','research_summary')}) for r in evidence['ready_studies']]
                    memory_sha=persist(root,memory);summary=compact(memory)
                except (ValueError,OSError):
                    journal.stop(session,'SUSPENDED','RESEARCH_MEMORY_INTEGRITY_OR_LIMIT_FAILURE');break
                for memory_limit in range(7500,2499,-250):
                    try:summary=compact(memory,memory_limit)
                    except ValueError:break
                    ctx=context(package,[],summary)
                    if evidence:
                        ctx['new_readonly_evidence']=memory['new_readonly_evidence']
                        ctx['evidence_ids']+=[r['evidence_id'] for r in memory['new_readonly_evidence']]
                    if feedback is not None:ctx['proposal_validation_feedback']=feedback
                    body=request_body(ctx,config)
                    if len(encoded(body))<=config['max_prompt_bytes']:break
                if len(encoded(body))>config['max_prompt_bytes']:
                    journal.stop(session,'BUDGET_STOP','PROMPT_BOUND_EXCEEDED');break
                # UTF-8 byte bound plus framing reserve; no tools/hidden conversations/cache writes.
                i_bound=len(encoded(body))+2048 if provider=='openai' else 0
                o_bound=config['max_output_tokens'] if provider=='openai' else 0
                try:call_id=journal.reserve_call(session,provider,digest(body),i_bound,o_bound)
                except ValueError as exc:
                    journal.stop(session,'BUDGET_STOP',str(exc));break
                journal.event(session,'RESEARCH_MEMORY_CONSULTED',dict(call_id=call_id,snapshot_sha256=memory_sha,
                    history_sha256=memory['history_sha256'],evidence_ids=[e['evidence_id'] for e in summary['records']],
                    omitted_records=summary['omitted_records']))
                started=time.monotonic()
                try:
                    timeout=min(config['provider_timeout_seconds'],journal.remaining_seconds(session))
                    reply=provider_fn(ctx,s['provider_calls']) if provider_fn else (
                        simulated_response(ctx,s['provider_calls']) if provider=='simulated' else
                        tool_fn(root,'provider',dict(body=body,timeout=timeout),timeout))
                except Exception:
                    reply=dict(usage=None,error='PROVIDER_FAILED_OR_TIMED_OUT',metadata={})
                exceeded=journal.finish_call(call_id,reply.get('usage'),time.monotonic()-started,reply.get('error'))
                journal.event(session,'PROVIDER_METADATA',dict(call_id=call_id,metadata=reply.get('metadata',{})))
                if exceeded:break
                if reply.get('error'):
                    failures+=1;feedback=None
                    if failures>=config['max_consecutive_provider_failures']:
                        journal.stop(session,'SUSPENDED','PROVIDER_CIRCUIT_OPEN');break
                    s=journal.status(session);continue
                raw=reply.get('proposal_text')
                try:proposal_hash=hashlib.sha256(raw.encode('utf-8')).hexdigest() if type(raw) is str else None
                except UnicodeError:proposal_hash=None
                try:
                    proposal=parse_proposal(raw,ctx['evidence_ids'])
                    assessment=validate_plan(proposal,memory)
                except ProposalValidationError as exc:
                    feedback=exc.diagnostic()
                    journal.event(session,'PROPOSAL_REJECTED',dict(reason='UNTRUSTED_PROPOSAL_INVALID',
                        call_id=call_id,proposal_sha256=proposal_hash,**feedback))
                    failures+=1
                    if failures>=config['max_consecutive_provider_failures']:
                        journal.stop(session,'SUSPENDED','INVALID_PROPOSAL_CIRCUIT_OPEN');break
                    s=journal.status(session);continue
                failures=0;feedback=None
                if assessment['classification']=='RESEARCH_DEFERRED':
                    journal.event(session,'RESEARCH_DEFERRED',dict(call_id=call_id,proposal_sha256=proposal_hash,
                        research_plan=proposal['research_plan'],memory_sha256=memory_sha))
                    journal.stop(session,'COMPLETED','RESEARCH_DEFERRED_INSUFFICIENT_EVIDENCE');break
                c=proposal['candidate'];version=candidate_version(c)
                journal.event(session,'PROPOSAL_ACCEPTED',dict(call_id=call_id,proposal_sha256=proposal_hash,version=version))
                journal.event(session,'RESEARCH_HYPOTHESIS_PLANNED',dict(version=version,
                    research_plan=proposal['research_plan'],assessment=assessment,memory_sha256=memory_sha))
                key=digest(dict(version=version,dataset=sha,tools=tool_hash(root)))
                existing=journal.lookup(key)
                if existing:
                    journal.event(session,'DUPLICATE_HYPOTHESIS',dict(version=version,experiment=key))
                    if existing['state']!='COMPLETED':
                        journal.stop(session,'SUSPENDED','UNRESOLVED_PRIOR_EXPERIMENT');break
                    s=journal.status(session);continue
                try:journal.reserve_experiment(session,key,version,proposal)
                except ValueError as exc:
                    journal.stop(session,'BUDGET_STOP',str(exc));break
                payload=dict(candidate=c,proposal=proposal,evidence_ids=ctx['evidence_ids'],
                    rows=package['series'][c['symbol']][str(c['timeframe_minutes'])],
                    spread_ratio=package['spread_ratios'][c['symbol']],
                    family_comparisons=journal.family_size(session),limitations=package['limitations'])
                try:
                    timeout=min(config['simulation_timeout_seconds'],journal.remaining_seconds(session))
                    result=tool_fn(root,'simulation',payload,timeout)
                    if result.get('version')!=version or result.get('execution_authorized') is not False or result.get('live_approved') is not False or result.get('final_holdout_evaluated') is not False:
                        raise ValueError('SIMULATION_RESULT_CONTRACT_INVALID')
                    journal.finish_experiment(key,result)
                    write(root,FOLDER+'/candidates/'+key+'.json',dict(proposal=proposal,result=result,version=version,
                        dataset_sha256=sha,tool_sha256=tool_hash(root),created_at=utc()))
                    journal.event(session,'RESEARCH_CONCLUSION_RECORDED',dict(version=version,
                        status=result['status'],reasons=result['rejection_reasons'],
                        metrics=result['results']['TIERED_BASE']['validation']['metrics'],
                        conclusion_scope='SIMULATED_OBSERVATION_NOT_GENERAL_CAUSAL_REFUTATION',
                        next_decision='RECONSULT_MEMORY_WITHIN_REMAINING_BUDGET'))
                except Exception:
                    journal.stop(session,'SUSPENDED','SIMULATION_FAILED_OR_TIMED_OUT');break
                s=journal.status(session)
            return report(root,journal,session,sha)
        finally:journal.close()
