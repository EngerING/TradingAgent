"""Bounded EUR/USD hypotheses, historical research only. No AI or order transport.

The catalogue is frozen before results, never widened until a winner appears.
The incumbent runner/configuration remain untouched. New arms are research
allocations, not active strategy changes or approvals.
"""
import argparse
from bisect import bisect_left
from collections import Counter
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
from pathlib import Path
from uuid import uuid4
from .eurusd_paper_research import Simulator, number, instant, encoded, sha, exit_decision, load_profile
from .eurusd_shadow_research import Calibrator, PROFILES, configuration, regime, ENGINE_FILES as SHADOW_ENGINE_FILES
from .progressive_risk_research import authentic_inputs, cost_evidence, walk_forward, wilson

SCOPE = 'EURUSD_COST_AWARE_RESEARCH_V1'
FOLDER = 'artifacts/research/eurusd-cost-aware'
MAX_CANDIDATES = 16
MIN_EV_BUFFER = Decimal('.25')
ENGINE_FILES = ('python/trading_agent/eurusd_cost_aware_search.py',
                'python/trading_agent/eurusd_cost_aware_forward.py', *SHADOW_ENGINE_FILES)


def catalogue():
    result = []
    for family in ('trend', 'breakout', 'momentum', 'mean_reversion'):
        for minutes in (60, 240):
            for horizon, target_atr, days in (('swing', 12, 5), ('position', 36, 20)):
                candidate = dict(family=family, minutes=minutes, horizon=horizon,
                    indicators=dict(ema_fast=20, ema_slow=50, rsi=14, macd=[12,26,9], atr=14),
                    stop_atr=2, target_atr=target_atr, hold_calendar_days=days,
                    structure_lookback=20, entry_utc_hours=[7,20],
                    stop_policy='MAX_2_ATR_PRIOR_STRUCTURE_DISTANCE',
                    target_policy='ATR_MULTIPLE_FROZEN_AT_SIGNAL' if family != 'mean_reversion' else 'MIN_EMA20_REVERSION_DISTANCE_ATR_MULTIPLE',
                    exit_policy='STOP_FIRST_ON_AMBIGUITY_ADVERSE_OPEN_GAP_TARGET_NO_FAVORABLE_GAP_CREDIT_HOLD_NEXT_OBSERVED_OPEN',
                    stage='PROPOSED_OFFLINE_NOT_ACTIVE', version=1)
                candidate['strategy_version'] = sha(candidate)
                candidate['id'] = f"eurusd-{family}-{minutes}-{horizon}-{candidate['strategy_version'][:12]}"
                result.append(candidate)
    assert len(result) == MAX_CANDIDATES
    return result


def profile(root, name):
    c = configuration(root)['profiles'][name]
    p = load_profile(root)
    p.update(profile=name, risk_fraction=c['risk_fraction'],
             maximum_trade_risk_usd=c['trade_risk_cap_usd'], daily_loss_budget_usd=c['daily_loss_budget_usd'])
    return p


def signals(analysis, candidate):
    """Every scheduled decision, including warmup/session/regime/no-signal vetoes.

    ATR/structure/target are computed at the closed signal bar, never by solving
    backwards for costs. Entry reference is the next authentic 15m opening.
    """
    minutes = candidate['minutes']; bars = analysis['normalized'][str(minutes)]
    points = analysis['indicator_points'][str(minutes)]
    if len(bars) != len(points): raise ValueError('INDICATOR_BAR_ALIGNMENT_REQUIRED')
    entries = {b['opened_at']:b for b in analysis['normalized']['15']}
    gaps = [instant(t) for t in analysis.get('quality',{}).get(str(minutes),{}).get('missing_expected_openings',[])]
    rows = []
    for i, (bar, p) in enumerate(zip(bars,points)):
        at = p['closed_at']; reasons = []; side = None; stop = target = None
        previous = points[i-1] if i else {}; prior = bars[max(0,i-20):i]
        if instant(at) != instant(bar['opened_at'])+timedelta(minutes=minutes): raise ValueError('CAUSAL_CLOSED_BAR_REQUIRED')
        if p['status'] != 'READY' or len(prior)<20 or previous.get('status')!='READY': reasons.append('INDICATOR_WARMUP')
        elif any(instant(prior[0]['opened_at'])<=t<instant(at) for t in gaps): reasons.append('UNEXPLAINED_DATA_GAP')
        else:
            close = number(bar['close']); atr = number(p['atr']); fast = number(p['ema_fast'])
            hi = max(number(x['high']) for x in prior); lo = min(number(x['low']) for x in prior)
            family = candidate['family']; rsi = number(p['rsi']); macd = number(p['macd_histogram'])
            if family == 'trend':
                if previous['ema_fast']<=previous['ema_slow'] and p['ema_fast']>p['ema_slow'] and macd>0 and 45<=rsi<=70: side='BUY'
                if previous['ema_fast']>=previous['ema_slow'] and p['ema_fast']<p['ema_slow'] and macd<0 and 30<=rsi<=55: side='SELL'
            elif family == 'breakout':
                if close>hi and p['trend']!='DOWNTREND' and macd>0: side='BUY'
                if close<lo and p['trend']!='UPTREND' and macd<0: side='SELL'
            elif family == 'momentum':
                momentum = close-number(bars[i-4]['close'])
                if momentum>2*atr and p['trend']=='UPTREND' and macd>0 and 55<=rsi<=75: side='BUY'
                if momentum<-2*atr and p['trend']=='DOWNTREND' and macd<0 and 25<=rsi<=45: side='SELL'
            elif p['trend']=='SIDEWAYS' and p['volatility']!='HIGH':
                if previous['rsi']<=30<p['rsi'] and close<fast: side='BUY'
                if previous['rsi']>=70>p['rsi'] and close>fast: side='SELL'
            if side:
                stop = max(Decimal('.00005'), atr*2, close-lo if side=='BUY' else hi-close)
                target = atr*candidate['target_atr']
                if family=='mean_reversion': target=min(target,abs(fast-close))
                if min(stop,target)<=0 or stop>=close: reasons.append('INVALID_STOP_TARGET_STRUCTURE')
            else: reasons.append('NO_FAMILY_SIGNAL_OR_REGIME_MISMATCH')
            if not candidate['entry_utc_hours'][0]<=instant(at).hour<candidate['entry_utc_hours'][1]: reasons.append('SESSION_FILTER')
        entry = entries.get(at)
        if entry is None: reasons.append('NO_AUTHENTIC_NEXT_OPEN')
        rows.append(dict(strategy_id=candidate['id'], strategy_version=candidate['strategy_version'],
            side=side, signal_at=at, entry_at=at, entry_midpoint=str(entry['open']) if entry else None,
            stop_distance=str(stop) if stop is not None else None,
            take_profit_distance=str(target) if target is not None else None, reasons=reasons,
            regime=regime(p), horizon=candidate['horizon'],
            indicators={k:p.get(k) for k in ('ema_fast','ema_slow','rsi','macd','macd_signal','macd_histogram','atr','trend','volatility')},
            structure=dict(prior_high=str(max(number(b['high']) for b in prior)) if prior else None,
                           prior_low=str(min(number(b['low']) for b in prior)) if prior else None),
            opportunity_id=sha([candidate['strategy_version'],at,side]),
            classification='HISTORICAL_DECISION_NOT_EXECUTED_TRADE'))
    return rows


def path_exit(position, bar, candidate):
    if instant(bar['opened_at']) < instant(position['entry_at']): return None
    deadline = instant(position['entry_at'])+timedelta(days=candidate['hold_calendar_days'])
    if instant(bar['opened_at'])>=deadline:
        o=number(bar['open']);buy=position['side']=='BUY';stop=number(position['stop']);target=number(position['target'])
        if o<=stop if buy else o>=stop:return str(o),'STOP_GAP_AT_HORIZON',bar['opened_at']
        if o>=target if buy else o<=target:return str(target),'TAKE_PROFIT',bar['opened_at']
        return str(bar['open']), 'HORIZON_NEXT_OBSERVED_OPEN', bar['opened_at']
    return exit_decision(position,bar,bar['opened_at'],[],False)


def labels_for(analysis, candidate, rows):
    """One counterfactual position per candidate; overlapping signals not samples.

    Rejected opportunities still have observations, but they cannot multiply
    identical price paths into apparently independent calibration evidence.
    """
    bars = analysis['normalized']['15']; times = [instant(b['opened_at']) for b in bars]
    labels=[]; busy_until=None
    for s in rows:
        if s['reasons']: continue
        at=instant(s['entry_at'])
        eligible=not busy_until or at>=busy_until
        direction=1 if s['side']=='BUY' else -1; mid=number(s['entry_midpoint'])
        pos=dict(strategy=candidate['id'], side=s['side'], entry_at=s['entry_at'],
                 stop=str(mid-direction*number(s['stop_distance'])),target=str(mid+direction*number(s['take_profit_distance'])))
        outcome='CENSORED'; resolved=None; exit_price=None; reason=None
        for b in bars[bisect_left(times,at):]:
            d=path_exit(pos,b,candidate)
            if d:
                exit_price,reason,resolved=d
                outcome='TP' if reason=='TAKE_PROFIT' else 'SL' if reason.startswith('STOP') else 'COMPETING_EXIT'
                break
        if eligible: busy_until=instant(resolved) if resolved else times[-1]+timedelta(minutes=15)
        labels.append(dict(strategy=candidate['id'], side=s['side'], regime=s['regime'],
            signal_at=s['signal_at'], resolved_at=resolved, outcome=outcome, exit_price=exit_price,
            exit_reason=reason, opportunity_id=s['opportunity_id'], signal=s,
            calibration_eligible=eligible,source='COUNTERFACTUAL_NOT_A_TRADE_OR_NET_WIN_OVERLAPS_EXCLUDED_FROM_CALIBRATION'))
    return labels


def calibrated(labels, protocol, folds, signal, at):
    labels=[label for label in labels if label.get('calibration_eligible',True)]
    result=Calibrator(labels,protocol,folds).estimate(dict(strategy=signal['strategy_id'],side=signal['side'],regime=signal['regime']),at)
    comparable=[l for l in labels if l['strategy']==signal['strategy_id'] and l['side']==signal['side'] and l['regime']==signal['regime'] and instant(l['signal_at'])<instant(at)]
    unfinished=[l for l in comparable if not l['resolved_at'] or instant(l['resolved_at'])>=instant(at)]
    fraction=len(unfinished)/len(comparable) if comparable else None
    wins=sum(l['outcome']=='TP' for l in comparable if l['resolved_at'] and instant(l['resolved_at'])<instant(at))
    family_interval=wilson(wins,result['sample_size'],.05/MAX_CANDIDATES)
    # Keep the original 100/30/3 reliability checks; strengthen uncertainty for
    # all preregistered candidate comparisons and unknown unfinished paths.
    if fraction is None or fraction>float(protocol['maximum_censor_fraction']): result['status']='INSUFFICIENT_EVIDENCE'
    result.update(family_adjusted_interval=family_interval, censor_fraction=fraction,
        calibration_error=sum(abs(x['predicted_mean']-x['observed_tp_rate']) for x in result['walk_forward_reliability'] if x['sample_size'])/sum(bool(x['sample_size']) for x in result['walk_forward_reliability']) if any(x['sample_size'] for x in result['walk_forward_reliability']) else None,
        confidence_bucket=next((f'{a:.0%}-{min(b,1):.0%}' for a,b in ((.5,.55),(.55,.6),(.6,.65),(.65,.7),(.7,.75),(.75,.8),(.8,1.000001)) if result['probability'] is not None and a<=result['probability']<b),'BELOW_50_OR_UNAVAILABLE'),
        regime=signal['regime'], family_tests=MAX_CANDIDATES, independence='NONOVERLAPPING_PATHS_STILL_SERIAL_DEPENDENCE',
        forward_requirement='NEW_UNEXAMINED_FORWARD_EVIDENCE_REQUIRED')
    return result


def economics(size, probability):
    win=number(size['net_target']) if size.get('net_target') is not None else None
    loss=number(size['risk']) if size.get('net_target') is not None else None
    p=number(probability['probability']) if probability.get('probability') is not None else None
    ci=probability.get('family_adjusted_interval') or ([probability['lower_95'],probability.get('upper_95')] if probability.get('lower_95') is not None else None)
    lower=number(ci[0]) if ci else None
    ev=p*win-(1-p)*loss if p is not None and win is not None else None
    low_ev=lower*win-(1-lower)*loss if lower is not None and win is not None else None
    reason=size.get('reason') if not size['admitted'] else 'INSUFFICIENT_EVIDENCE' if probability['status']!='CALIBRATED_RESEARCH_ESTIMATE' else 'NET_EV_NOT_ABOVE_UNCERTAINTY_BUFFER' if ev is None or low_ev is None or min(ev,low_ev)<=MIN_EV_BUFFER else None
    def decimal(v): return str(v) if v is not None else None
    return dict(decision='NO_TRADE' if reason else 'TRADE',reason=reason or 'ISOLATED_SHADOW_GATES_PASSED',
        gross_expected_win=size.get('gross_target'), net_expected_win=decimal(win), expected_loss=decimal(loss),
        fees=size.get('commissions'), spread=size.get('spread'), slippage=size.get('slippage'), gap_uncertainty=size.get('gap_reserve'),
        reward_risk=size.get('net_reward_risk'), expected_value=decimal(ev), conservative_expected_value=decimal(low_ev),
        break_even_win_rate=decimal(loss/(loss+win)) if win is not None and win>0 else None,
        break_even_status='COMPUTABLE' if win is not None and win>0 else 'UNACHIEVABLE_OR_NO_SIZE',
        minimum_ev_buffer_usd=str(MIN_EV_BUFFER), conditional_win_not_unconditional_forecast=True,
        execution_authorized=False, ibkr_executability='UNKNOWN', model_probability_allowed=False)


class ResearchSimulator(Simulator):
    """Reuse all original sizing, funding, daily stops and settlement rules.

    The added gate can only reject. Indicators/exit rules belong to this new
    candidate, never overwrite Trend/Pullback/MR V1 or the current study.
    """
    def __init__(self, path, p, costs, candidate):
        self.candidate=candidate
        super().__init__(path,p,costs,candidate,positive_expectancy_evidence=True)

    def size(self, signal, at):
        if signal['strategy_id']!=self.candidate['id'] or signal.get('strategy_version',self.candidate['strategy_version'])!=self.candidate['strategy_version']:
            raise ValueError('CANDIDATE_SIGNAL_BINDING_REQUIRED')
        size=super().size(signal,at)
        gate=economics(size,signal.get('calibration',dict(status='INSUFFICIENT_EVIDENCE',probability=None)))
        gate['holding_cost_status']=self.costs.get('holdingCostStatus','UNKNOWN')
        if gate['decision']=='TRADE' and gate['holding_cost_status']=='UNKNOWN':
            gate.update(decision='NO_TRADE',reason='HOLDING_COST_EVIDENCE_UNKNOWN')
        size['economic_gate']=gate
        if gate['decision']!='TRADE': size.update(admitted=False,reason=gate['reason'])
        return size

    def advance(self, bar):
        if self.state['last_bar'] and instant(bar['opened_at'])<=instant(self.state['last_bar']['opened_at']): return
        p=self.state['position']
        if p and p['result_state']=='OPEN_SIMULATED':
            d=path_exit(p,bar,self.candidate)
            if d: self.close(d[0],d[2],d[1])
        if self.state['position']:
            def update():
                self.state['last_bar']=bar
                self.state['last_at']=(instant(bar['opened_at'])+timedelta(minutes=15)).isoformat()
                self.append('CLOSED_BAR_OBSERVED',dict(bar=bar,classification='AUTHENTIC_PRICE_SIMULATED_EXECUTION'))
            self.atomic(update)


class MemorySimulator(ResearchSimulator):
    """Deterministic offline replay; evidence streamed to a separate hash journal."""
    def __init__(self,p,costs,candidate):
        self.candidate=candidate;self.profile=p;self.costs=costs;self.strategy=candidate;self.expectancy=True
        self.state=dict(equity='100',consumed_loss='0',daily_losses={},stopped_days={},position=None,
                        trades=[],seen=[],last_at=None,last_bar=None,peak='100',drawdown='0')
        self.revision=0;self.head=''
    def restore(self,full=False): pass
    def append(self,event,details): self.revision+=1;self.head=sha([self.revision,event,details,self.head])
    def atomic(self,callback): return callback()


class EvidenceLog:
    def __init__(self,path): self.file=Path(path).open('xb');self.head='';self.revision=0
    def add(self,event,details):
        self.revision+=1;value=dict(revision=self.revision,event=event,details=details,previous=self.head)
        self.head=sha(value);value['hash']=self.head
        self.file.write(encoded(value)+b'\n')
    def close(self): self.file.flush();self.file.close()


def replay(root, candidate, rows, labels, analysis, costs, window, log):
    start,end=instant(window['test_start']),instant(window['test_end'])
    portfolios={name:MemorySimulator(profile(root,name),costs,candidate) for name in PROFILES}
    protocol=configuration(root)['probability'];folds=walk_forward(analysis['extension']['split'])
    schedule={r['entry_at']:r for r in rows if start<=instant(r['entry_at'])<end}
    rejected={name:Counter() for name in PROFILES};signals_count=0
    for bar in analysis['normalized']['15']:
        at=instant(bar['opened_at'])
        if not start<=at or at+timedelta(minutes=15)>end: continue
        # Horizon exits at the open precede the new signal, never same-bar future
        # protective outcomes. Intrabar outcomes happen after admission.
        for sim in portfolios.values():
            p=sim.state['position']
            if p and p['result_state']=='OPEN_SIMULATED' and at>=instant(p['entry_at'])+timedelta(days=candidate['hold_calendar_days']): sim.close(str(bar['open']),bar['opened_at'],'HORIZON_NEXT_OBSERVED_OPEN')
        s=schedule.get(bar['opened_at'])
        if s:
            s=deepcopy(s); signals_count+=not bool(s['reasons'])
            s['calibration']=calibrated(labels,protocol,folds,s,s['signal_at']) if not s['reasons'] else dict(status='INSUFFICIENT_EVIDENCE',probability=None)
            decisions={name:sim.enter(s) for name,sim in portfolios.items()}
            for name,d in decisions.items():
                if not d['admitted']: rejected[name][d['reason']]+=1
            log.add('COMMON_CANDIDATE_DECISION',dict(candidate=candidate['id'],window=window['name'],signal=s,profiles=decisions,broker_orders=0))
        for name,sim in portfolios.items():
            before=len(sim.state['trades']);sim.advance(bar)
            if len(sim.state['trades'])>before: log.add('SIMULATED_OUTCOME_RECONCILED',dict(candidate=candidate['id'],window=window['name'],profile=name,trade=sim.state['trades'][-1]))
    result=[]
    for name,sim in portfolios.items():
        metrics=sim.metrics();n=metrics['completed_trades'];wins=metrics['wins']
        result.append(dict(profile=name,window=window,signal_count=signals_count,admitted=n+int(bool(sim.state['position'])),
            rejected=dict(rejected[name]),metrics=metrics,win_rate_interval_95=wilson(wins,n),
            evidence_status='INSUFFICIENT_EVIDENCE' if n<100 else 'RETROSPECTIVE_REQUIRES_FRESH_CONFIRMATION',
            portfolio_hash=sim.head,ibkr_executability='UNKNOWN'))
    return result


def movement_requirements(root, costs, mid, stop):
    rows=[]
    signal=dict(strategy_id='economic-geometry-not-a-trading-signal',side='BUY',entry_midpoint=str(mid),stop_distance=str(stop),
        take_profit_distance=str(number(mid)*Decimal('.20')),entry_at='2026-10-01T12:00:00+00:00',signal_at='2026-10-01T12:00:00+00:00',reasons=[])
    for name in PROFILES:
        sim=MemorySimulator(profile(root,name),costs,catalogue()[0])
        # Only reuse sizing arithmetic: not an entry or candidate admission.
        d=Simulator.size(sim,signal,signal['entry_at']);qty=number(d['quantity'])
        uncertainty=qty*number(costs['adverseGap']);friction=number(d['commissions'])+qty*(number(costs['spread'])+number(costs['slippage']))+uncertainty
        required={}
        for gain in (0,1,3,5):
            move=(friction+gain)/qty if qty>0 else None
            required[f'net_{gain}_usd']=dict(movement_usd_per_eur=str(move) if move is not None else None,
                pips=str(move/Decimal('.0001')) if move is not None else None,
                price_return_percent=str(move/number(mid)*100) if move is not None else None,capital_return_percent=gain)
        rows.append(dict(profile=name,reference_midpoint=str(mid),reference_status='LAST_AUTHENTIC_HISTORICAL_CLOSE_NOT_LIVE_QUOTE',
            stop_distance=str(stop),quantity_eur=str(qty),notional_usd=d.get('notional'),
            risk_budget_usd=d['budget'],expected_stop_loss_usd=d['risk'] if qty>0 else None,
            costs_and_uncertainty_usd=str(friction),movements=required,
            size_status='GEOMETRIC_SIZE_NOT_EXECUTION_APPROVAL' if qty>0 else d['reason'],ibkr_executability='UNKNOWN',
            no_leverage=True,exposure_and_reservations_ceiling_usd='100'))
    return rows


def sol_request_contract(report):
    """Prepared bounded input only. This function has no provider or API key.

    Model commentary cannot supply the calibration used by ResearchSimulator.
    Hypotheses are text in a separate proposal, never executable parameters.
    """
    context=dict(scope=SCOPE,decision=report['decision'],fresh_oos=report['fresh_oos'],
        candidates=[dict(id=r['candidate']['id'],family=r['candidate']['family'],minutes=r['candidate']['minutes'],
            horizon=r['candidate']['horizon'],calibration_samples=max(e['sample_size'] for e in r['calibration']),
            price_paths=r['counterfactual'],geometry_passes=r['geometry_passes'],
            net_validation=[dict(profile=s['profile'],trades=s['metrics']['completed_trades'],expectancy=s['metrics']['net_expectancy'],profit_factor=s['metrics']['net_profit_factor']) for s in r['scenarios'] if s['window']['name']=='validation']) for r in report['results']],
        model_probability_allowed=False,unknowns=['IBKR margin and permissions','Other odd-lot execution','Overnight financing/cash-debit costs','Effective protection'],
        research_memory_refs=['research-openai-001','research-openai-002','research-openai-003 DEFER_RESEARCH','H40 cost and pending-inventory audit'])
    if len(encoded(context))>24000:raise ValueError('COMPACT_SOL_CONTEXT_LIMIT')
    return dict(model='gpt-6.1-sol',state='NOT_RUNNING_BUDGET_ZERO',budget_usd='0',api_calls=0,
        context=context,instructions='Analyse net economics and evidence limitations. TP frequency is not net win rate. Never invent probability or confidence. Do not propose materially equivalent rejected hypotheses without identifying materially new evidence. Proposals remain separate: backtest -> walk-forward -> independent shadow-forward. No risk/execution overrides, tools, orders or active strategy changes.',
        schema=dict(type='object',additionalProperties=False,required=['recommendation','reasons','hypothesis'],properties={
            'recommendation':dict(type='string',enum=['TRADE','NO_TRADE','INSUFFICIENT_EVIDENCE']),
            'reasons':dict(type='array',items=dict(type='string')),'hypothesis':dict(type=['string','null'])}))


def validate_sol_advice(value):
    if type(value) is not dict or set(value)!={'recommendation','reasons','hypothesis'} or value['recommendation'] not in ('TRADE','NO_TRADE','INSUFFICIENT_EVIDENCE'):raise ValueError('SOL_RESEARCH_CONTRACT_INVALID')
    if type(value['reasons']) is not list or len(value['reasons'])>5 or any(type(r) is not str or len(r)>400 for r in value['reasons']):raise ValueError('SOL_RESEARCH_CONTRACT_INVALID')
    if value['hypothesis'] is not None and (type(value['hypothesis']) is not str or len(value['hypothesis'])>1200):raise ValueError('SOL_RESEARCH_CONTRACT_INVALID')
    return dict(proposal=deepcopy(value),stage='UNVALIDATED_SEPARATE_HYPOTHESIS',execution_authorized=False,
        automatic_adoption=False,probability_source='DETERMINISTIC_HISTORICAL_CALIBRATION_ONLY')


def run_search(root):
    root=Path(root).resolve();candidates=catalogue();analysis,_,provenance=authentic_inputs(root)
    costs,evidence=cost_evidence(root,provenance);split=analysis['extension']['split'];folds=walk_forward(split)
    costs['holdingCostStatus']='UNKNOWN'
    evidence['holding_costs']='UNKNOWN_OVERNIGHT_FINANCING_CASH_DEBITS_AND_REPEATED_ORDER_MINIMA_NOT_SUBSTITUTED_WITH_ZERO'
    folder=root/FOLDER/('search-'+uuid4().hex);folder.mkdir(parents=True,exist_ok=False)
    protocol=dict(scope=SCOPE,candidates=candidates,maximum_candidates=MAX_CANDIDATES,
        capital_per_arm_usd='100',profiles=configuration(root)['profiles'],exposure_ceiling_usd='100',
        minimum_ev_buffer_usd=str(MIN_EV_BUFFER),costs=costs,cost_evidence=evidence,provenance=provenance,split=split,folds=folds,
        parameters_refitted=False,fresh_oos=False,final_holdout_opened=False,automatic_strategy_adoption=False,
        openai_budget_usd='0',openai_calls=0,broker_orders=0,execution_authorized=False,live_enabled=False,
        engine_hashes={p:sha((root/p).read_text(encoding='utf-8')) for p in ENGINE_FILES})
    (folder/'protocol.json').write_bytes(encoded(protocol))
    windows=[dict(name='development',test_start=split['start'],test_end=split['validation_start']),
             dict(name='validation',test_start=split['validation_start'],test_end=split['end']),*folds]
    log=EvidenceLog(folder/'opportunities.jsonl');results=[]
    try:
        for candidate in candidates:
            rows=signals(analysis,candidate);labels=labels_for(analysis,candidate,rows)
            for label in labels: log.add('COUNTERFACTUAL_PRICE_PATH_NOT_PORTFOLIO_TRADE',label)
            scenarios=[]
            for window in windows: scenarios.extend(replay(root,candidate,rows,labels,analysis,costs,window,log))
            estimates=[calibrated(labels,configuration(root)['probability'],folds,dict(strategy_id=candidate['id'],side=side,regime=r),split['end']) for side in ('BUY','SELL') for r in ('UPTREND','DOWNTREND','RANGE','HIGH_VOLATILITY','LOW_VOLATILITY')]
            valid=[r for r in rows if not r['reasons']]; probes=[]
            for s in valid:
                sim=MemorySimulator(profile(root,'EURUSD_R10'),costs,candidate)
                d=Simulator.size(sim,s,s['entry_at'])
                if d.get('net_target') is not None: probes.append(dict(opportunity_id=s['opportunity_id'],at=s['signal_at'],**d))
            comparable=[l for l in labels if l['calibration_eligible']]
            resolved=[l for l in comparable if l['resolved_at']];tp=sum(l['outcome']=='TP' for l in resolved)
            validation=[s for s in scenarios if s['window']['name']=='validation']
            eligible=[]
            for scenario in validation:
                m=scenario['metrics'];name=scenario['profile'];reasons=[]
                if m['completed_trades']<100:reasons.append('INSUFFICIENT_NET_OOS_TRADE_SAMPLE')
                if m['net_expectancy'] is None or number(m['net_expectancy'])<=0:reasons.append('NET_OOS_EXPECTANCY_UNPROVEN_OR_NONPOSITIVE')
                if m['net_profit_factor'] is None or number(m['net_profit_factor'])<=1:reasons.append('NET_PROFIT_FACTOR_UNPROVEN')
                if not any(e['status']=='CALIBRATED_RESEARCH_ESTIMATE' for e in estimates):reasons.append('COMPARABLE_PROBABILITY_NOT_CALIBRATED')
                if any(s['metrics']['completed_trades']==0 or number(s['metrics']['net_pnl'])<=0 for s in scenarios if s['profile']==name and s['window']['name'].startswith('walk_forward')):reasons.append('WALK_FORWARD_NET_PROFITABILITY_UNPROVEN')
                reasons+=['FRESH_UNEXAMINED_FORWARD_REQUIRED','IBKR_EXECUTABILITY_UNKNOWN']
                eligible.append(dict(profile=name,eligible_for_activation=False,reasons=reasons))
            results.append(dict(candidate=candidate,scenarios=scenarios,calibration=estimates,selection=eligible,
                opportunities=len(rows),raw_signals=len(valid),signal_rejections=dict(Counter(reason for s in rows for reason in s['reasons'])),
                counterfactual=dict(all_rejected_signal_paths=len(labels),nonoverlapping_samples=len(comparable),resolved=len(resolved),tp_rate=tp/len(resolved) if resolved else None,
                    wilson_95=wilson(tp,len(resolved)),censored=len(comparable)-len(resolved),net_win_rate=False),
                economically_screened_signals=len(probes),targets_covering_costs=sum(number(p['net_target'])>0 for p in probes),
                geometry_passes=sum(p['admitted'] for p in probes),
                maximum_potential_net_target=max((number(p['net_target']) for p in probes),default=None),
                best_geometry=max(probes,key=lambda p:number(p['net_target'])) if probes else None,
                decision='REJECTED_NO_STATISTICAL_OR_ECONOMIC_APPROVAL',promotion=False))
        for row in results:
            if row['maximum_potential_net_target'] is not None: row['maximum_potential_net_target']=str(row['maximum_potential_net_target'])
        last=analysis['normalized']['15'][-1];atr=analysis['indicator_points']['240'][-1]['atr']
        movements=movement_requirements(root,costs,number(last['close']),number(atr)*2)
        report=dict(protocol_hash=sha(protocol),classification='OFFLINE_SIMULATED_RESEARCH_NOT_BROKER_EXECUTION',
            decision='NO_VIABLE_STRATEGY_FOUND',best_approved_candidate=None,results=results,movements=movements,
            statistical_rank=None,no_forced_winner=True,log_head=log.head,log_events=log.revision,
            fresh_oos=False,final_holdout_opened=False,openai_calls=0,broker_orders=0,
            limitations=['Validation was previously examined; no untouched final proof.',
                'Nonoverlapping paths remain serially dependent; Wilson intervals are reference only.',
                'Potential target profitability is not realized expectancy; do not rank by maximum target.',
                'Margin, speculative permissions, odd-lot sizes and effective protection remain UNKNOWN.',
                'Adverse gap reserve is a scenario, not a guaranteed maximum loss.',
                'Overnight financing/cash-debit and other holding costs UNKNOWN; USD4 is not a verified all-in long-horizon tariff.'])
        (folder/'labels.json').write_bytes(encoded({r['candidate']['id']:labels_for(analysis,r['candidate'],signals(analysis,r['candidate'])) for r in results}))
        (folder/'report.json').write_bytes(encoded(report))
        handoff=dict(scope=SCOPE,report=str((folder/'report.json').relative_to(root)),report_hash=sha(report),
            decision=report['decision'],openai_state='NOT_RUNNING_BUDGET_ZERO',subjective_confidence_forbidden=True,
            required_validation=['BACKTEST','WALK_FORWARD','NEW_SHADOW_FORWARD'],automatic_adoption=False,
            candidate_summaries=[dict(id=r['candidate']['id'],family=r['candidate']['family'],raw_signals=r['raw_signals'],
                resolved_price_paths=r['counterfactual']['resolved'],counterfactual_tp_rate=r['counterfactual']['tp_rate'],
                geometry_passes=r['geometry_passes'],selection=r['selection'],
                net_results=[dict(profile=s['profile'],window=s['window']['name'],net_expectancy=s['metrics']['net_expectancy'],net_pnl=s['metrics']['net_pnl'],sample=s['metrics']['completed_trades']) for s in r['scenarios'] if s['window']['name']=='validation'],
                decision=r['decision']) for r in results],
            model_contract=dict(allowed_recommendations=['TRADE','NO_TRADE','INSUFFICIENT_EVIDENCE'],
                probability='DETERMINISTIC_CALIBRATION_ONLY_DO_NOT_GENERATE',
                candidate_changes='HYPOTHESES_ONLY_SEPARATE_UNTIL_VALIDATED',
                tools=[],order_authority=False,risk_override=False))
        (folder/'sol-handoff.json').write_bytes(encoded(handoff))
        (folder/'sol-request-prepared.json').write_bytes(encoded(sol_request_contract(report)))
    finally:log.close()
    return dict(search=folder.name,report=str((folder/'report.json').relative_to(root)),candidates=len(candidates),
        decision=report['decision'],broker_orders=0,openai_calls=0)


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',default='.')
    args=p.parse_args();print(json.dumps(run_search(args.root),allow_nan=False))

if __name__=='__main__':main()
