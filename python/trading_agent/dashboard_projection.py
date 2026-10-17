"""Read-only UI projection. No broker, model, write-capable journal or execution imports."""
import hashlib
from contextlib import closing
import json
import math
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo
import re
import sqlite3
import sys

PROFILES = ('EURUSD_R1', 'EURUSD_R5', 'EURUSD_R10')


def encoded(x):
    return json.dumps(x, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()


def safe_text(value):
    text = str(value or '')[:1800]
    return re.sub(r'sk-[A-Za-z0-9_-]+|\bDU(?:R)?[0-9]+\b', '[REDACTED]', text)


def numeric(x):
    if x is None or isinstance(x, bool): return None
    try:
        v = float(x)
        return v if math.isfinite(v) else None
    except (ValueError, TypeError): return None


def moment(x):
    return datetime.fromisoformat(x.replace('Z', '+00:00')) if x else None


def readonly(path):
    if path.is_symlink(): raise ValueError('UI_SOURCE_LINK_REJECTED')
    return sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True, timeout=2)


def portfolio(root, study, name, expected):
    folder = root/'artifacts/research/eurusd-shadow'/study
    # Simulator file is fixed by the existing laboratory; do not create missing sources.
    path = folder/(name+'.sqlite3')
    if not path.exists():
        if expected: raise ValueError('UI_PORTFOLIO_SOURCE_MISSING')
        return None
    state = None; head = ''; revision = 0
    with closing(readonly(path)) as db:
        for r, payload, previous, digest in db.execute('SELECT revision,payload,previous,hash FROM events ORDER BY revision'):
            value = json.loads(payload)
            if r != revision+1 or previous != head or hashlib.sha256(encoded([r,value,previous])).hexdigest() != digest:
                raise ValueError('UI_PORTFOLIO_INTEGRITY_FAILED')
            head, revision, state = digest, r, value['state']
    if head != expected: raise ValueError('UI_PORTFOLIO_POSTGRES_HEAD_MISMATCH')
    return state


def trade_view(profile, p, quote=None, closed=False, fees=None):
    d=p.get('decision', {}); s=p.get('signal', {}); probability=s.get('probability', {})
    quantity=numeric(d.get('quantity')); entry=numeric(p.get('entry_fill')); current=None
    if quote and quote.get('quality') in ('LIVE','DELAYED'):
        current=quote.get('bid') if p.get('side')=='BUY' else quote.get('ask')
    gross=numeric(p.get('gross_pnl')); net=numeric(p.get('net_pnl'))
    if not closed and current is not None and quantity is not None and entry is not None:
        midpoint=(quote['bid']+quote['ask'])/2
        gross=quantity*(midpoint-numeric(p['entry_midpoint']))*(1 if p.get('side')=='BUY' else -1)
        net=gross-(numeric(d.get('costs')) or 0)
    return dict(id=p['id'],profile=profile,symbol='EUR/USD',direction='LONG' if p['side']=='BUY' else 'SHORT',
        quantity=quantity,entry=entry,currentPrice=current,stop=numeric(p.get('stop')),target=numeric(p.get('target')),
        exit=numeric(p.get('exit_fill')),openedAt=p.get('entry_at'),closedAt=p.get('exit_at'),
        durationSeconds=(moment(p['exit_at'])-moment(p['entry_at'])).total_seconds() if p.get('exit_at') else None,
        grossPnl=gross,netPnl=net,commission=numeric(p.get('opening_commission'))+numeric(p.get('closing_commission')) if closed else fees,
        commissionStatus='ESTIMATED',spread=numeric(p.get('spread_cost')),slippage=numeric(p.get('slippage_cost')),
        probability=numeric(probability.get('probability')),expectedValue=numeric(d.get('expected_value')),
        regime=s.get('regime','DATA_UNAVAILABLE'),entryReason=safe_text(s.get('reason') or s.get('reasons') or 'ORIGINAL_STRATEGY_SIGNAL'),
        exitReason=safe_text(p.get('close_reason')),signalId=s.get('opportunity_id',p['id']),strategyVersion=p.get('strategy_version'),
        classification='SIMULATED_SHADOW',environment='INTERNAL_SIMULATION',protection='SIMULATED_ONLY',
        status='CLOSED' if closed else p.get('result_state','PENDING'),
        outcome=('WIN' if net>0 else 'LOSS' if net<0 else 'BREAK_EVEN') if closed and net is not None else None,
        exitCategory=('TP' if 'TARGET' in p.get('close_reason','') else 'SL' if 'STOP' in p.get('close_reason','') else 'OTHER') if closed else None)


def research(root):
    path=root/'artifacts/research/ai-strategy-research/journal.sqlite3'
    if not path.exists(): return dict(status='DATA_UNAVAILABLE',sessions=[],candidates=[],deferred=[])
    from .ai_strategy_researcher.data import load_dataset
    from .ai_strategy_researcher.memory import load_readonly
    package,_=load_dataset(root);memory=load_readonly(root,package)
    superseded={r.get('supersedes_evidence_id') for r in memory['entries']}
    rows=[r for r in memory['entries'] if r['evidence_id'] not in superseded]
    return dict(status='VERIFIED_HASH_LINKED_HISTORY',sessions=memory['session_conclusions'][-20:],
        deferred=[dict(session=r['session'],at=r['at'],plan=r['research_plan']) for r in memory['deferred_decisions'][-5:]],
        candidates=[dict(id=r['evidence_id'],session=r['session'],version=r['version'],state='PROPOSED' if r['state']!='COMPLETED' else 'REJECTED' if r['reasons'] else 'CANDIDATE',
            hypothesis=safe_text(r['hypothesis']),parameters=r['candidate'],reasons=r['reasons'],results=r['windows'],
            evidenceStatus=r['evidence_status'],supersedes=r.get('supersedes_evidence_id'),sourceSha256=r.get('source_sha256')) for r in rows[-20:]],
        finalHoldout='SEALED',automaticPromotion=False)


def project(root, envelope, now=None):
    root=Path(root).resolve();now=now or datetime.now(timezone.utc)
    head=envelope.get('head'); observation=envelope.get('observation')
    if head:
        study=head['study_id']
        if not re.fullmatch(r'eurusd-shadow-[a-f0-9]{32}',study):raise ValueError('UI_STUDY_SCOPE_REQUIRED')
        state=head['state'];protocol=state['protocol']
        if head.get('classification')!='SIMULATED_SHADOW' or head.get('broker_orders')!=0 or head.get('live_enabled') is not False:
            raise ValueError('UI_SHADOW_SCOPE_REQUIRED')
    else: study=None;state={};protocol={}
    details=(observation or {}).get('details',{}); q=details.get('quote') or {};features=details.get('features') or {}
    age=(now-moment(q.get('at'))).total_seconds() if q.get('at') else None
    quality='MISSING' if not q else 'STALE' if age is None or age<0 or age>30 else q.get('type','MISSING')
    market=dict(status='DATA_UNAVAILABLE' if not q else 'AVAILABLE',symbol='EUR/USD',bid=numeric(q.get('bid')),ask=numeric(q.get('ask')),
        last=None,spread=(numeric(q['ask'])-numeric(q['bid'])) if q.get('bid') and q.get('ask') else None,
        at=q.get('at'),ageSeconds=age,quality=quality,marketStatus=q.get('market_status','UNKNOWN'),
        source='IBKR_PAPER_READ_ONLY',timestampKind='CALLBACK_RECEIPT_NOT_EXCHANGE_TIME',features=features,series=[])
    market['series']=sorted({x['at']:{'at':x['at'],'value':(numeric(x['bid'])+numeric(x['ask']))/2} for x in envelope.get('quotes',[])
        if x.get('at') and numeric(x.get('bid')) is not None and numeric(x.get('ask')) is not None and numeric(x['bid'])>0 and numeric(x['ask'])>=numeric(x['bid'])}.values(),key=lambda p:p['at'])
    opportunity=details.get('opportunity') or {}; decisions=details.get('decisions') or {};prediction=opportunity.get('probability') or {}
    experiments=[];opened=[];closed=[];local_day=now.astimezone(ZoneInfo('America/Santo_Domingo')).date().isoformat()
    for name in PROFILES:
        metrics=state.get('portfolio_metrics',{}).get(name); conf=protocol.get('configuration',{}).get('profiles',{}).get(name)
        if metrics is None or conf is None:
            experiments.append(dict(id=name,status='DATA_UNAVAILABLE',metrics=None,risk=None,equityCurve=[]));continue
        equity=numeric(metrics['equity_realized']);risk=max(0,min(equity*numeric(conf['risk_fraction']),numeric(conf['trade_risk_cap_usd'])))
        initial=100;curve=[dict(at=head['at'],equity=initial,netPnl=0,drawdown=0,tradeNumber=0)]
        # The first event timestamp comes from the persisted preregistration, not a manufactured quote.
        start=protocol.get('folds',[{}])[-3].get('test_start') if len(protocol.get('folds',[]))>=3 else head['at']
        curve[0]['at']=start
        peak=initial
        for i,point in enumerate(metrics.get('equity_curve',[])):
            value=numeric(point['equity']);peak=max(peak,value)
            curve.append(dict(at=point['at'],equity=value,netPnl=value-initial,drawdown=peak-value,tradeNumber=i+1))
        decision=decisions.get(name,{})
        status='PAUSED' if state.get('status')!='SHADOW_RESEARCH_RUNNING' else 'INSUFFICIENT_EVIDENCE' if prediction.get('status')!='CALIBRATED_RESEARCH_ESTIMATE' else 'ACTIVE' if decision.get('decision')=='TRADE' else 'NO_TRADE'
        mapped={k:numeric(metrics.get(v)) for k,v in dict(equity='equity_realized',netPnl='net_pnl',grossPnl='gross_pnl',maximumDrawdown='maximum_closed_drawdown_usd',winRate='win_rate',trades='completed_trades',wins='wins',profitFactor='net_profit_factor',expectancy='net_expectancy',fees='commissions',spreadCost='spread_cost',slippageCost='slippage_cost',costRatio='cost_to_gross_profit_ratio',riskOfRuin='risk_of_ruin',averageWin='average_win',averageLoss='average_loss',recoveryFactor='recovery_factor',losingStreak='longest_losing_streak',realizedRewardRisk='realized_reward_risk').items()}
        mapped.update(initialCapital=100,returnOnCapital=(equity/100-1),currentDrawdown=peak-equity,confidence=None,sharpe=None,sortino=None,calibrationError=None,losses=None)
        # Loss counts are derived from definitive trade results, never pending inventory.
        local=portfolio(root,study,name,state.get('portfolio_heads',{}).get(name))
        if local:
            rows=local.get('trades',[]); mapped['losses']=sum(Decimal(t['net_pnl'])<0 for t in rows)
            probabilities=[numeric(t['signal'].get('probability',{}).get('probability')) for t in rows]; probabilities=[v for v in probabilities if v is not None]
            mapped['confidence']=sum(probabilities)/len(probabilities) if probabilities else None
            fees=numeric(protocol['costs']['openingCommission'])+numeric(protocol['costs']['closingCommission'])
            if local.get('position'):opened.append(trade_view(name,local['position'],market,fees=fees))
            closed.extend(trade_view(name,t,closed=True) for t in rows[-500:])
        experiments.append(dict(id=name,status=status,studyId=study,startedAt=start,reason=decision.get('reason',state.get('status')),
            stoppedForDay=(local_day in metrics['daily_stops']) if isinstance(metrics.get('daily_stops'),dict) else None,
            stoppedDay=local_day,dailyStopReason=metrics['daily_stops'].get(local_day) if isinstance(metrics.get('daily_stops'),dict) else None,
            classification='SIMULATED_SHADOW',metrics=mapped,risk=dict(fraction=numeric(conf['risk_fraction']),nextBudget=risk,dailyBudget=numeric(conf['daily_loss_budget_usd']),
                exposureCap=100,consumedLoss=numeric(metrics['consumed_loss']),remainingLossBudget=max(0,20-numeric(metrics['consumed_loss']))),
            equityCurve=curve if len(curve)<=2000 else curve[::math.ceil(len(curve)/1999)]+[curve[-1]]))
    from .eurusd_shadow_research import calibration_metrics
    calibration=state.get('calibration_metrics') or calibration_metrics(state.get('calibration_records',[]))
    calibration={**calibration,'buckets':[{**b,'average_probability':b['mean_probability']} for b in calibration['buckets']]}
    signal=dict(status='DATA_UNAVAILABLE' if not opportunity else 'AVAILABLE',decision='INSUFFICIENT_EVIDENCE' if prediction.get('status')!='CALIBRATED_RESEARCH_ESTIMATE' else 'TRADE' if any(d.get('decision')=='TRADE' for d in decisions.values()) else 'NO_TRADE',
        at=opportunity.get('at'),direction=opportunity.get('side'),probability=numeric(prediction.get('probability')),sampleSize=prediction.get('sample_size'),
        lower95=numeric(prediction.get('lower_95')),upper95=numeric(prediction.get('upper_95')),probabilityStatus=prediction.get('status','DATA_UNAVAILABLE'),
        regime=features.get('regime','DATA_UNAVAILABLE'),decisions=decisions,contextual=opportunity.get('contextual'),features=features)
    result=dict(at=now.isoformat(),studyId=study,revision=envelope.get('revision',0),source='POSTGRESQL_RESEARCH_SHADOW',
        studyStatus=state.get('status','DATA_UNAVAILABLE'),experiments=experiments,market=market,prediction=signal,
        openPositions=opened,trades=sorted(closed,key=lambda t:t['closedAt'],reverse=True)[:500],calibration=calibration,research=research(root),
        notifications=[dict(id='economic-block',kind='warning',text='NO_VIABLE_STRATEGY_FOUND: sin promoción ni autorización de ejecución.'),
                       dict(id='quality',kind='warning' if quality!='LIVE' else 'info',text='Datos de mercado: '+quality)])
    if envelope.get('exploratory'):
        from .eurusd_exploratory_projection import overlay
        result=overlay(result,envelope['exploratory'])
    from .kronos.projection import project as kronos_view
    result['kronos']=kronos_view(envelope.get('kronos') or [],now)
    if envelope.get('priceRisk'):
        p=envelope['priceRisk'];s=p['state']
        if p['scope']!='R10_PRICE_RISK_EXPERIMENTAL' or p['classification']!='SIMULATED_SHADOW' or p['broker_orders']!=0 or p['live_enabled']:raise ValueError('PRICE_RISK_SCOPE_REQUIRED')
        result['priceRisk']=dict(experiment=p['experiment'],classification=p['classification'],**s)
    if envelope.get('aggressiveGrowth'):
        from .aggressive_growth_projection import project as aggressive_growth_view
        result['aggressiveGrowth']=aggressive_growth_view(envelope['aggressiveGrowth'],now)
    return result


def main():
    try:
        request=json.loads(sys.stdin.buffer.read(5_000_001))
        result=project(Path(request['root']),request['envelope'])
        print(json.dumps(result,ensure_ascii=True,allow_nan=False))
    except Exception as exc:
        print(json.dumps(dict(error='UI_SOURCE_UNAVAILABLE',reason=type(exc).__name__)))
        raise SystemExit(1)


if __name__=='__main__':main()
