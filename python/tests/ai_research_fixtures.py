from datetime import datetime,timedelta,timezone
import copy
import json
from pathlib import Path
from trading_agent.ai_strategy_researcher.data import write,FOLDER


def config():return json.loads(Path('config/ai-strategy-research.json').read_bytes())


def candidate():return dict(name='AI_Test',symbol='F',timeframe_minutes=60,pattern='TREND_CROSS',
    fast=8,slow=24,lookback=48,atr_period=14,stop_atr=1.5,target_r=3,max_hold_bars=12,risk_percent=15)


def proposal(ctx=None):
    p=dict(hypothesis='Falsifiable cost-aware hypothesis.',rationale='Independent validation required.',
        evidence_ids=['authentic_development_prices'],candidate=candidate())
    if ctx is not None:add_plan(p,ctx)
    return p


def add_plan(p,ctx):
    c=p['candidate'];records=ctx.get('research_memory',{}).get('records',[])
    inert={'name','risk_percent'}|({'fast'} if c['pattern']=='MEAN_REVERSION' else set())
    same=[r for r in records if all(c[k]==r['candidate'][k] for k in ('symbol','timeframe_minutes','pattern'))]
    nearest=min(same,key=lambda r:sum(c[k]!=r['candidate'][k] for k in c if k not in inert)) if same else None
    p['research_plan']=dict(action='PROPOSE_EXPERIMENT',problem='Prior cost and sample limitations.',
        prior_failure_analysis='Observed net failure does not prove a causal explanation.',novelty='Test a distinct prespecified mechanism or material parameter change.',
        why_evaluate='One bounded falsifiable experiment.',insufficient_evidence='Independent data and actual fees are missing.',
        refutation_test='Nonpositive net expectation or insufficient evidence rejects approval.',alternatives='Verify fees and collect independent data.',
        prior_evidence_ids=[nearest['evidence_id']] if nearest else [records[0]['evidence_id']] if records else [],
        changed_fields=[k for k in c if k not in inert and nearest['candidate'][k]!=c[k]] if nearest else [])
    return p


def bars(n=150,start='2021-01-04T14:30:00+00:00'):
    begin=datetime.fromisoformat(start)
    return [dict(opened_at=(begin+timedelta(hours=2*i)).isoformat(),closed_at=(begin+timedelta(hours=2*i+1)).isoformat(),
        open=10.,high=10.4,low=9.8,close=10.,volume=1000.) for i in range(n)]


def fixture(root):
    root=Path(root);(root/'config').mkdir();(root/'config/ai-strategy-research.json').write_text(json.dumps(config()))
    refs={'prices':'artifacts/research/equity-evidence/readonly.json',
        'quality':'artifacts/research/equity-operational/data-integrity.json',
        'previous_research':'artifacts/research/equity-evidence/report.json'}
    hashes={k:write(root,v,{}) for k,v in refs.items()}
    package=dict(schema_version=1,mode='SIMULATION_ONLY',series={s:{tf:bars() for tf in ('60','1440')} for s in ('F','SPY')},
        spread_ratios={'F':None,'SPY':None},source_hashes=hashes,
        development_start='2021-01-01T00:00:00+00:00',development_end='2024-01-01T00:00:00+00:00',
        final_holdout_sealed=True,final_data_exported=False,previous_failures=[],
        quarantined_symbols=['SCHX'],limitations=['ALREADY_EXAMINED_DEVELOPMENT_NOT_INDEPENDENT_OOS'],
        broker_constraints={'permissions':'UNKNOWN'})
    sha=write(root,FOLDER+'/dataset.json',package)
    return package,sha


def binding():return dict(config=config(),dataset_sha256='a'*64,provider='openai',tool_sha256='b'*64)


def metric(ev=1,win=.9):
    return dict(admitted=10,rejected=1,net_pnl=10*ev,net_expectancy=ev,win_rate=win,commissions=2,
        maximum_drawdown=.1,profit_factor=1.5)


def result(c=None):
    from trading_agent.ai_strategy_researcher.contracts import candidate_version,MODELS,FOLDS
    c=c or candidate()
    return dict(version=candidate_version(c),candidate=c,results={m:{f:dict(metrics=metric()) for f,_,_ in FOLDS} for m in MODELS},
        confidence={},status='DISCARDED_RESEARCH_EVIDENCE',rejection_reasons=['INSUFFICIENT_SAMPLE'],
        independent_validation_required=True,final_holdout_evaluated=False,backtests=15,
        execution_authorized=False,live_approved=False)
