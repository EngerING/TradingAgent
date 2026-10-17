"""Continuous read-only EURUSD research; three isolated shadow portfolios.

Probability is a past-only empirical TP-before-SL estimator, never model prose.
No order API is exposed. PostgreSQL and a local immutable outbox must agree
before admitting another shadow operation. Model advice is veto-only.
"""
import argparse
import hashlib
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import time
from uuid import uuid4
from .eurusd_paper_research import Simulator, load_profile, number, instant, encoded, sha, exit_decision, FOLDER, ZONE
from .progressive_risk_research import authentic_inputs, cost_evidence, wilson, walk_forward

SCOPE = 'EURUSD_SHADOW_R1_R5_R10'
PROFILES = ('EURUSD_R1','EURUSD_R5','EURUSD_R10')
FOLDER = 'artifacts/research/eurusd-shadow'
BUCKETS = ((.5,.55),(.55,.6),(.6,.65),(.65,.7),(.7,.75),(.75,.8),(.8,1.000001))
ENGINE_FILES = ('python/trading_agent/eurusd_shadow_research.py','python/trading_agent/eurusd_paper_research.py',
                'python/trading_agent/research_analysis.py','python/trading_agent/research_indicators.py',
                'config/eurusd-shadow-research.json','config/eurusd-paper-research-100.json')


def engine_hashes(root):
    return {name:hashlib.sha256((Path(root)/name).read_bytes()).hexdigest() for name in ENGINE_FILES}


def configuration(root):
    c = json.loads((Path(root)/'config/eurusd-shadow-research.json').read_bytes())
    rates = ('0.01','0.05','0.10'); caps = ('1','5','10'); days = ('2','5','10')
    if (c['scope'] != SCOPE or c['initial_capital_per_portfolio'] != '100' or c['exposure_ceiling_usd'] != '100'
            or c['broker_orders_enabled'] is not False or c['live_enabled'] is not False
            or c['automatic_strategy_changes'] is not False or c['strategy'] != 'trend'
            or tuple(c['profiles']) != PROFILES): raise ValueError('SHADOW_SCOPE_REQUIRED')
    for i,p in enumerate(PROFILES):
        if c['profiles'][p] != dict(risk_fraction=rates[i],trade_risk_cap_usd=caps[i],daily_loss_budget_usd=days[i]): raise ValueError('SHADOW_RISK_PROFILE_CHANGED')
    if c['probability'] != dict(minimum_samples=100,minimum_days=30,minimum_folds=3,maximum_censor_fraction='0.10'): raise ValueError('PROBABILITY_PROTOCOL_CHANGED')
    a=c['openai']
    if a['model'] != 'gpt-6.1-sol' or not 0 <= number(a['max_cost_usd']) <= 1 or not 1 <= a['max_calls'] <= 10 or a['max_output_tokens'] != 512 or a['max_prompt_bytes'] != 6000 or a['timeout_seconds'] != 20:
        raise ValueError('CONTEXTUAL_BUDGET_INVALID')
    if not 5 <= c['poll_seconds'] <= 60: raise ValueError('POLL_INTERVAL_INVALID')
    return c


def regime(point, anomalous=False):
    if anomalous or point.get('status') != 'READY': return 'ANOMALOUS_OR_INSUFFICIENT_DATA'
    volatility = point.get('volatility')
    if volatility == 'HIGH': return 'HIGH_VOLATILITY'
    if volatility == 'LOW': return 'LOW_VOLATILITY'
    return {'UPTREND':'UPTREND','DOWNTREND':'DOWNTREND','SIDEWAYS':'RANGE'}.get(point.get('trend'),'ANOMALOUS_OR_INSUFFICIENT_DATA')


def feature_engine(analysis, quote, at):
    cutoff=instant(at)
    bars=[b for b in analysis['normalized']['15'] if instant(b['opened_at'])+timedelta(minutes=15)<=cutoff]
    points=[p for p in analysis['indicator_points']['15'] if instant(p['closed_at'])<=cutoff]
    p=points[-1] if points else {}; window=bars[-20:]
    quote_ok=quote.get('type')=='LIVE' and quote.get('market_status')=='OPEN' and quote.get('available_for_execution') is True and 0 <= (cutoff-instant(quote['at'])).total_seconds() <= 5
    gap=bool(len(bars)>1 and instant(bars[-1]['opened_at'])-instant(bars[-2]['opened_at'])>timedelta(minutes=15))
    # A scheduled break is distinct from an unexplained missing bar.
    missing=analysis.get('quality',{}).get('15',{}).get('missing_expected_openings',[])
    recent_missing=any(cutoff-timedelta(hours=4)<instant(t)<=cutoff for t in missing)
    hh=None; hl=None
    if len(window)>=4:
        a,b=window[-4:-2],window[-2:]
        hh=max(number(x['high']) for x in b)>max(number(x['high']) for x in a)
        hl=min(number(x['low']) for x in b)>min(number(x['low']) for x in a)
    return dict(at=at, indicators={k:p.get(k) for k in ('ema_fast','ema_slow','rsi','macd','macd_signal','macd_histogram','atr','ema_fast_slope','log_return_std','atr_ratio','trend','volatility')},
        regime=regime(p,not quote_ok or recent_missing), structure=dict(higher_high=hh,higher_low=hl),
        momentum_4_bars=float(number(bars[-1]['close'])/number(bars[-5]['close'])-1) if len(bars)>=5 else None,
        support=str(min(number(b['low']) for b in window)) if window else None,
        resistance=str(max(number(b['high']) for b in window)) if window else None,
        spread=str(number(quote['ask'])-number(quote['bid'])) if quote_ok else None,
        liquidity=None,liquidity_status='UNKNOWN_CASH_MIDPOINT_HAS_NO_TRADED_VOLUME_OR_ORDER_BOOK_DEPTH',
        macro_risk='UNKNOWN_NO_AUTHENTIC_MACRO_FEED', quote_quality='LIVE' if quote_ok else quote.get('type','MISSING'),
        quote_timestamp_kind='LOCAL_CALLBACK_RECEIPT_NOT_EXCHANGE_TIMESTAMP',local_hour=cutoff.astimezone(ZONE).hour,
        session_utc_hour=cutoff.hour, scheduled_or_missing_gap=gap, unexplained_recent_gaps=recent_missing,
        feature_source='PYTHON_CLOSED_BARS_NO_CHARTS_NO_FUTURE')


def historical_labels(analysis, strategy='trend'):
    """Counterfactual price-path labels, not admitted trades or strategy wins."""
    bars=analysis['normalized']['15']; positions={b['opened_at']:i for i,b in enumerate(bars)}; out=[]
    points={p['closed_at']:p for p in analysis['indicator_points']['15']}
    exits=[e for e in analysis['exit_signals'] if e['strategy_id']==strategy]
    for s in analysis['candidates']:
        if s['strategy_id']!=strategy or s['reasons'] or s['entry_at'] not in positions: continue
        direction=1 if s['side']=='BUY' else -1; mid=number(s['entry_midpoint'])
        p=dict(strategy=strategy,side=s['side'],entry_at=s['entry_at'],stop=str(mid-direction*number(s['stop_distance'])),target=str(mid+direction*number(s['take_profit_distance'])))
        i=positions[s['entry_at']]; label='CENSORED'; resolved=None
        for j in range(i,len(bars)):
            b=bars[j]
            d=exit_decision(p,b,bars[j-1]['opened_at'] if j>i else b['opened_at'],exits,j>i) if j>i else None
            d=d or exit_decision(p,b,bars[j-1]['opened_at'] if j>i else b['opened_at'],exits,False)
            if d:
                resolved=d[2]; label='TP' if d[1]=='TAKE_PROFIT' else 'SL' if d[1].startswith('STOP') else 'COMPETING_EXIT'; break
        out.append(dict(signal_at=s['signal_at'],resolved_at=resolved,side=s['side'],strategy=strategy,
                        regime=regime(points.get(s['signal_at'],{})),outcome=label,
                        source='SIMULATED_COUNTERFACTUAL_PRICE_PATH_NOT_EXECUTED_TRADE'))
    return out


class Calibrator:
    def __init__(self, labels, protocol, folds):
        self.labels,self.protocol,self.folds=labels,protocol,folds

    def estimate(self, opportunity, at):
        cutoff=instant(at)
        comparable=[r for r in self.labels if r['strategy']==opportunity['strategy'] and r['side']==opportunity['side'] and r['regime']==opportunity['regime']
                    and r['resolved_at'] and instant(r['resolved_at'])<cutoff and instant(r['signal_at'])<cutoff]
        n=len(comparable); tp=sum(r['outcome']=='TP' for r in comparable); competing=sum(r['outcome']=='COMPETING_EXIT' for r in comparable)
        days=len({instant(r['signal_at']).astimezone(ZONE).date() for r in comparable})
        # Treat competing exits conservatively as full stop outcomes for sizing
        # EV, rather than dropping them and overstating the win probability.
        p=tp/n if n else None; interval=wilson(tp,n) if n else None
        completed_folds=sum(instant(f['test_end'])<cutoff and any(instant(f['test_start'])<=instant(r['signal_at'])<instant(f['test_end']) for r in comparable) for f in self.folds)
        wf=[]
        for fold in self.folds:
            predictions=[]
            if instant(fold['test_end'])>=cutoff:continue
            for row in comparable:
                if not instant(fold['test_start'])<=instant(row['signal_at'])<instant(fold['test_end']):continue
                prior=[r for r in comparable if instant(r['resolved_at'])<instant(row['signal_at'])]
                if len(prior)<30:continue
                forecast=sum(r['outcome']=='TP' for r in prior)/len(prior)
                predictions.append(dict(probability=forecast,outcome='TP' if row['outcome']=='TP' else 'SL'))
            diagnostics=calibration_metrics(predictions)
            wf.append(dict(fold=fold['name'],sample_size=len(predictions),brier=diagnostics['brier_score'],
                           predicted_mean=sum(r['probability'] for r in predictions)/len(predictions) if predictions else None,
                           observed_tp_rate=sum(r['outcome']=='TP' for r in predictions)/len(predictions) if predictions else None))
        wf=wf[-3:] # Fixed chronological recency, never the most favorable folds.
        reliability=len(wf)>=3 and all(f['sample_size']>=10 and f['brier']<=.25 and abs(f['predicted_mean']-f['observed_tp_rate'])<=.15 for f in wf)
        sufficient=n>=self.protocol['minimum_samples'] and days>=self.protocol['minimum_days'] and completed_folds>=self.protocol['minimum_folds'] and competing/n<=float(self.protocol['maximum_censor_fraction']) and reliability
        return dict(status='CALIBRATED_RESEARCH_ESTIMATE' if sufficient else 'INSUFFICIENT_EVIDENCE',probability=p,
                    lower_95=interval[0] if interval else None,upper_95=interval[1] if interval else None,sample_size=n,
                    sample_days=days,completed_walk_forward_folds=completed_folds,competing_exits=competing,
                    comparison=dict(strategy=opportunity['strategy'],side=opportunity['side'],regime=opportunity['regime']),
                    target='TP_BEFORE_SL_WITH_COMPETING_EXITS_CONSERVATIVELY_AS_LOSS',
                    uncertainty='WILSON_IID_REFERENCE_DEPENDENT_SIGNALS_NOT_INDEPENDENT_CONFIDENCE_PROOF',
                    walk_forward_reliability=wf,reliability_pass=reliability,
                    model_generated_probability=False,fresh_oos=False)


def economic_gate(size, probability, advice):
    if not size['admitted']: return dict(decision='NO_TRADE',reason=size['reason'],expected_value=None,conservative_ev=None)
    if probability['status']!='CALIBRATED_RESEARCH_ESTIMATE': return dict(decision='NO_TRADE',reason='INSUFFICIENT_EVIDENCE',expected_value=None,conservative_ev=None)
    p=number(probability['probability']); lower=number(probability['lower_95']); win=number(size['net_target']); loss=number(size['risk'])
    ev=p*win-(1-p)*loss; conservative=lower*win-(1-lower)*loss
    result=dict(decision='NO_TRADE',reason=None,expected_value=str(ev),conservative_ev=str(conservative))
    if ev<=0 or conservative<=0: result['reason']='NET_EV_NOT_POSITIVE'
    elif advice['recommendation']!='TRADE': result['reason']='CONTEXTUAL_'+advice['recommendation']
    else: result.update(decision='TRADE',reason='SHADOW_ONLY_ALL_GATES_PASSED')
    return result


def calibration_metrics(records):
    settled=[r for r in records if r.get('outcome') in ('TP','SL') and r.get('probability') is not None]
    buckets=[]
    for lo,hi in BUCKETS:
        rows=[r for r in settled if lo<=r['probability']<hi]; n=len(rows)
        buckets.append(dict(bucket=f'{lo:.0%}-{min(hi,1):.0%}',samples=n,observed_tp_rate=sum(r['outcome']=='TP' for r in rows)/n if n else None,
                            mean_probability=sum(r['probability'] for r in rows)/n if n else None,wilson_95=wilson(sum(r['outcome']=='TP' for r in rows),n)))
    return dict(sample_size=len(settled),brier_score=sum((r['probability']-(r['outcome']=='TP'))**2 for r in settled)/len(settled) if settled else None,
                buckets=buckets,censored=sum(r.get('outcome') not in ('TP','SL') for r in records),
                status='INSUFFICIENT_EVIDENCE' if len(settled)<100 else 'RESEARCH_RELIABILITY_MEASUREMENT_NOT_LIVE_APPROVAL')


def postgres(root, study, events):
    result=subprocess.run(['dotnet',str(Path(root)/'src/TradingAgent.Api/bin/Debug/net9.0/TradingAgent.Api.dll'),'--eurusd-shadow-journal'],
                          input=encoded(dict(study=study,events=events)).decode(),capture_output=True,text=True,timeout=15,cwd=root)
    try: output=json.loads(result.stdout)
    except (ValueError,TypeError): raise ValueError('SHADOW_POSTGRES_UNAVAILABLE') from None
    if result.returncode or 'error' in output: raise ValueError('SHADOW_POSTGRES_UNAVAILABLE_OR_CONFLICT')
    return output


class Study:
    def __init__(self,root,study,mirror=postgres):
        if not re.fullmatch(r'eurusd-shadow-[a-f0-9]{32}',study): raise ValueError('STUDY_ID_INVALID')
        self.root,self.study,self.mirror=Path(root).resolve(),study,mirror
        self.folder=self.root/FOLDER/study; self.folder.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(self.folder/'journal.sqlite3',isolation_level=None,timeout=10)
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('CREATE TABLE IF NOT EXISTS events(revision INTEGER PRIMARY KEY,payload TEXT,previous TEXT,hash TEXT)')
        for action in ('UPDATE','DELETE'):
            self.db.execute(f"CREATE TRIGGER IF NOT EXISTS immutable_{action} BEFORE {action} ON events BEGIN SELECT RAISE(ABORT,'IMMUTABLE_SHADOW_JOURNAL'); END")
        try:
            self.restore(); self.sync()
        except Exception:
            self.db.close(); raise

    def restore(self):
        self.head='';self.revision=0;self.state=None
        for revision,payload,previous,h in self.db.execute('SELECT * FROM events ORDER BY revision'):
            value=json.loads(payload)
            if revision!=self.revision+1 or previous!=self.head or sha([revision,value,previous])!=h: raise ValueError('SHADOW_JOURNAL_INTEGRITY')
            self.head,self.revision,self.state=h,revision,value['state']

    def sync(self):
        remote=self.mirror(self.root,self.study,[])
        if remote['revision']>self.revision: raise ValueError('LOCAL_SHADOW_JOURNAL_MISSING_BROKER_STATE_NOT_ASSUMED')
        for start in range(remote['revision']+1,self.revision+1,20):
            events=[]
            for r,p,previous,h in self.db.execute('SELECT * FROM events WHERE revision>=? AND revision<? ORDER BY revision',(start,start+20)):
                events.append(dict(revision=r,payload=p,previous=previous,hash=h,material=encoded([r,json.loads(p),previous]).decode()))
            remote=self.mirror(self.root,self.study,events)
        if remote['hash']!=self.head: raise ValueError('POSTGRES_SHADOW_HEAD_CONFLICT')

    def append(self,event,details):
        value=dict(study_id=self.study,scope=SCOPE,classification='SIMULATED_SHADOW',broker_orders=0,
                   execution_authorized=False,live_enabled=False,event=event,at=datetime.now(timezone.utc).isoformat(),state=self.state,details=details)
        revision=self.revision+1; h=sha([revision,value,self.head]); payload=encoded(value).decode()
        self.db.execute('INSERT INTO events VALUES(?,?,?,?)',(revision,payload,self.head,h));self.revision,self.head=revision,h
        self.sync()


class ReadOnlyIdentity:
    def __init__(self,root):
        from .paper_lab_diagnostics import InspectionAuthorization
        from .ibkr_session import AccountBinding
        anchor=InspectionAuthorization(root) # process lookup only, no old grant.
        self.root,self.process,self.configuration=Path(root),anchor.process,anchor.configuration
        self.binding=AccountBinding.load_or_migrate(root)

    def read(self,management=False):
        from .ibkr_session import AccountBinding
        from .paper_lab import same_process
        if not management or os.environ.get('LIVE_TRADING','false').lower()!='false': raise PermissionError('RESEARCH_READ_ONLY_REQUIRED')
        binding=AccountBinding.load_or_migrate(self.root)
        if binding.binding_id!=self.binding.binding_id or not same_process(self.process['pid'],self.process['started']): raise PermissionError('READ_ONLY_IDENTITY_OR_TWS_CHANGED')
        return dict(account=binding.account,environment='PAPER_TRADING',live_enabled=False,paper_checked=True,
                    identity_manual_match=True,inspection_only=True,client_id=86,host=self.configuration.host,port=self.configuration.port)


class MarketReader:
    def __init__(self,root):
        from .ibkr_session import session_guard,ExecutionMode
        from .paper_execution_wire import execution_wire
        self.root=Path(root);self.auth=ReadOnlyIdentity(root);self.cached={};self.updated={}
        def deny(*args,**kwargs): raise PermissionError('SHADOW_RESEARCH_NO_BROKER_MUTATION')
        self.wire=execution_wire(self.auth,deny,read_only=True,session=session_guard(root,ExecutionMode.Research))
        a=self.auth.read(management=True)
        if self.wire.connect(a)!=[a['account']]: raise PermissionError('EXACT_PAPER_IDENTITY_REQUIRED')
        self.contract=self.wire.contract_details();self.calendar=self.wire.calendar()
        self.snapshot=self.wire.snapshot(diagnostic=True)
        self.capabilities=dict(identity=dict(status='VERIFIED',source='AccountBinding + managedAccounts exact match'),
            reconciliation=dict(status='VERIFIED' if not self.snapshot['orders'] and not self.snapshot['positions'] and self.snapshot['exposure_reads_complete'] else 'UNKNOWN',source='READ_ONLY_ACCOUNT_CALLBACKS'),
            minimum=dict(status='VERIFIED_DECLARED_NOT_EFFECTIVE_PERMISSION',value=self.contract['minimum_size_metadata'],increment=self.contract['size_increment_metadata']),
            idealpro_standard_minimum=dict(status='VERIFIED_PUBLIC_NOT_ODD_LOT_PERMISSION',eur='20000',source='https://investors.interactivebrokers.com/en/?f=5479'),
            margin=dict(status='UNKNOWN_FOR_THIS_SIZE',account_total=self.snapshot['initial_margin'],source='ACCOUNT_TOTAL_IS_NOT_ORDER_MARGIN'),
            settled_cash=dict(status='VERIFIED' if any(r['tag']=='SettledCash' for r in self.wire.account_rows) else 'UNKNOWN',
                              observations=[r for r in self.wire.account_rows if r['tag']=='SettledCash']),
            permissions=dict(status='UNKNOWN',source='CONTRACT_EXISTENCE_IS_NOT_SPECULATIVE_FOREX_PERMISSION'),
            effective_small_size_fees=dict(status='UNKNOWN_OTHER_QUANTITIES',source='ONE_PREVIOUS_100_EUR_PAPER_CYCLE_2_USD_PER_SIDE'),
            protection=dict(status='UNKNOWN_EFFECTIVE_ACCEPTANCE',source='PREVIOUS_CHILDREN_CANCELLED_NOT_ACTIVE_PROTECTION_EVIDENCE'),
            partial_fills=dict(status='UNKNOWN_CURRENT_SMALL_SIZE_EXECUTION',source='NOT_TESTED_WITH_NEW_ORDERS'))
        self.initialized=False

    def observe(self):
        from .research_analysis import analyze
        self.auth.read(management=True)
        if not self.wire.connected: raise ConnectionError('PAPER_READ_ONLY_DISCONNECTED')
        now=datetime.now(timezone.utc)
        if not self.initialized:
            for minutes in (240,60,15):
                self.cached[str(minutes)]=self.wire.history(minutes);self.updated[minutes]=int(time.time()//(minutes*60))
            self.initialized=True
        else:
            # 15m first gives a chance to receive the authentic closing bar and
            # next-open quote within five seconds on non-hourly boundaries.
            for minutes in (15,60,240):
                bucket=int(time.time()//(minutes*60))
                if bucket!=self.updated[minutes]:
                    self.cached[str(minutes)]=self.wire.history(minutes);self.updated[minutes]=bucket
        if (now-instant(self.calendar['received_at'])).total_seconds()>240:
            self.contract=self.wire.contract_details();self.calendar=self.wire.calendar()
        quote=self.wire.observe_quote();at=datetime.now(timezone.utc).isoformat()
        raw=dict(originals=self.cached,calendar=self.calendar,contract=self.contract,source='AUTHENTIC_IBKR_PAPER_READ_ONLY')
        source_sha=sha(raw);path=self.root/FOLDER/'market-data'/(source_sha+'.json');path.parent.mkdir(parents=True,exist_ok=True)
        if not path.exists():
            with path.open('xb') as f:f.write(encoded(raw))
        elif path.read_bytes()!=encoded(raw):raise ValueError('MARKET_DATA_ARCHIVE_CONFLICT')
        analysis=analyze(dict(instrument='EUR/USD',source='IBKR_TWS',what_to_show='MIDPOINT',as_of=at,
            indicators=json.loads((self.root/'config/research-indicators.json').read_bytes()),calendar=self.calendar,originals=self.cached))
        return dict(at=at,quote=quote,analysis=analysis,capabilities=self.capabilities,calendar=self.calendar,
                    source='IBKR_PAPER_READ_ONLY',history_source=dict(path=str(path.relative_to(self.root)),sha256=source_sha),
                    api_events=self.wire.api_events[-20:],broker_orders=0)

    def close(self): self.wire.disconnect()


def contextual(study,opportunity,enabled_budget=None,provider=None):
    """Reserve worst-case usage durably before a single Responses request."""
    a=study.state['protocol']['configuration']['openai']; budget=number(a['max_cost_usd'])
    usage=study.state['openai']; default=dict(recommendation='INSUFFICIENT_EVIDENCE',reasons=['OPENAI_DISABLED_OR_DETERMINISTIC_BLOCK'],limitations=['NO_SUBJECTIVE_PROBABILITY'])
    if not a['enabled'] or budget<=0 or usage['circuit_open'] or usage.get('pending_opportunity'): return default
    if opportunity['probability']['status']!='CALIBRATED_RESEARCH_ESTIMATE': return default
    prompt=encoded(opportunity)
    if len(prompt)>a['max_prompt_bytes']: return {**default,'reasons':['CONTEXT_TOO_LARGE']}
    # Conservative configured price upper bounds (5/15), above the official
    # 2026-10-07 Standard 2/10 price. No cache discount or tools assumed.
    input_bound=len(prompt)+3000; reserve=(Decimal(input_bound)*5+Decimal(a['max_output_tokens'])*15)/1000000
    if usage['calls']>=a['max_calls'] or number(usage['reserved_usd'])+reserve>budget: return {**default,'reasons':['OPENAI_BUDGET_EXHAUSTED']}
    schema=dict(type='object',additionalProperties=False,required=['recommendation','reasons','limitations'],properties={
        'recommendation':dict(type='string',enum=['TRADE','NO_TRADE','INSUFFICIENT_EVIDENCE']),
        'reasons':dict(type='array',items=dict(type='string')),'limitations':dict(type='array',items=dict(type='string'))})
    body=dict(model=a['model'],instructions='Evaluate structured Forex research context. Return only recommendation, reasons, limitations. Never generate probabilities or alter risk, strategy, permissions or execution controls. UNKNOWN macro and liquidity remain UNKNOWN. A contextual TRADE cannot override deterministic costs, calibrated probability, EV or sizing gates.',
        input=prompt.decode(),store=False,service_tier='default',reasoning={'effort':'low'},max_output_tokens=a['max_output_tokens'],
        text={'format':{'type':'json_schema','name':'eurusd_contextual_veto','strict':True,'schema':schema}})
    usage['calls']+=1;usage['reserved_usd']=str(number(usage['reserved_usd'])+reserve);usage['pending_opportunity']=opportunity['id']
    study.append('OPENAI_COST_RESERVED',dict(opportunity_id=opportunity['id'],reserved=str(reserve),input_token_bound=input_bound))
    if provider is None:
        from .ai_strategy_researcher.providers import openai_response
        provider=openai_response
    try: response=provider(body,a['timeout_seconds'])
    except Exception:
        usage['circuit_open']=True
        study.append('OPENAI_UNCERTAIN_NO_RETRY',dict(opportunity_id=opportunity['id'],reservation_retained=True))
        return {**default,'reasons':['CONTEXTUAL_TRANSPORT_UNCERTAIN_NO_RETRY']}
    u=response.get('usage')
    if u:
        usage['input_tokens']+=u['input_tokens'];usage['output_tokens']+=u['output_tokens']
        usage['observed_cost_upper_estimate']=str(number(usage['observed_cost_upper_estimate'])+(Decimal(u['input_tokens'])*5+Decimal(u['output_tokens'])*15)/1000000)
    try:
        if response.get('error') or not u or u['input_tokens']>input_bound or u['output_tokens']>a['max_output_tokens']: raise ValueError('CONTEXTUAL_RESPONSE_UNCERTAIN')
        result=json.loads(response['proposal_text'])
        if set(result)!={'recommendation','reasons','limitations'} or result['recommendation'] not in ('TRADE','NO_TRADE','INSUFFICIENT_EVIDENCE'): raise ValueError('CONTEXTUAL_SCHEMA_INVALID')
        for k in ('reasons','limitations'):
            if type(result[k]) is not list or len(result[k])>10 or any(type(x) is not str or len(x)>400 for x in result[k]): raise ValueError('CONTEXTUAL_SCHEMA_INVALID')
    except (ValueError,TypeError,KeyError):
        usage['circuit_open']=True;result={**default,'reasons':[response.get('error') or 'CONTEXTUAL_SCHEMA_OR_USAGE_INVALID']}
    usage['pending_opportunity']=None
    study.append('OPENAI_CONTEXTUAL_RESULT',dict(opportunity_id=opportunity['id'],result=result,usage=u))
    return result


def prepare(root,study=None,budget='0'):
    root=Path(root).resolve(); c=configuration(root); budget=number(budget)
    if not 0<=budget<=1: raise ValueError('EXPLICIT_SESSION_BUDGET_REQUIRED')
    c['openai']['max_cost_usd']=str(budget);c['openai']['enabled']=budget>0
    analysis,ids,provenance=authentic_inputs(root);costs,evidence=cost_evidence(root,provenance)
    labels=historical_labels(analysis); folds=walk_forward(analysis['extension']['split'])
    forward_start=datetime.now(timezone.utc)
    folds += [dict(name=f'preregistered_forward_{i+1}',test_start=(forward_start+timedelta(days=30*i)).isoformat(),
                   test_end=(forward_start+timedelta(days=30*(i+1))).isoformat(),training='PAST_RESOLVED_LABELS_ONLY',parameters_refitted=False) for i in range(3)]
    study=study or 'eurusd-shadow-'+uuid4().hex;s=Study(root,study)
    try:
        if s.revision: raise ValueError('STUDY_ALREADY_PREREGISTERED')
        label_file=s.folder/'labels.json';label_file.write_bytes(encoded(labels))
        s.state=dict(protocol=dict(configuration=c,strategy=ids['trend'],costs=costs,provenance=provenance,cost_evidence=evidence,
                                    label_sha256=sha(labels),folds=folds,initial_capital='100',shadow_only=True,engine_hashes=engine_hashes(root)),
                     openai=dict(calls=0,reserved_usd='0',observed_cost_upper_estimate='0',input_tokens=0,output_tokens=0,circuit_open=False,pending_opportunity=None),
                     seen=[],last_observation=None,portfolio_heads={},portfolio_metrics={},calibration_records=[],
                     forward_labels=[],settled_opportunity_ids=[],
                     pending_counterfactual=None,resolved_label_ids=[],
                     status='PREPARED_NOT_RUNNING',research_handoff=None)
        for name,config in c['profiles'].items():
            p=load_profile(root);p.update(profile=name,risk_fraction=config['risk_fraction'],maximum_trade_risk_usd=config['trade_risk_cap_usd'],daily_loss_budget_usd=config['daily_loss_budget_usd'])
            sim=Simulator(s.folder/(name+'.sqlite3'),p,costs,ids['trend'],positive_expectancy_evidence=True)
            s.state['portfolio_heads'][name]=sim.head;s.state['portfolio_metrics'][name]=sim.metrics();sim.db.close()
        s.append('IMMUTABLE_STUDY_PREREGISTERED',dict(strategy='trend_V1_UNPROMOTED',label_count=len(labels),openai_budget=str(budget)))
        return dict(study=study,status='PREPARED_NOT_RUNNING',profiles=list(PROFILES),broker_orders=0,openai_calls=0)
    finally: s.db.close()


def compare(root):
    """Frozen chronological replay, not strategy selection or a model call."""
    from .eurusd_paper_research import replay
    root=Path(root).resolve();c=configuration(root);a,ids,provenance=authentic_inputs(root);costs,evidence=cost_evidence(root,provenance)
    split=a['extension']['split'];windows=[dict(name='development',test_start=split['start'],test_end=split['validation_start']),
        dict(name='validation',test_start=split['validation_start'],test_end=split['end']),*walk_forward(split)]
    folder=root/FOLDER/('comparison-'+uuid4().hex);folder.mkdir(parents=True,exist_ok=False);results=[]
    for strategy in ids:
        exits=[e for e in a['exit_signals'] if e['strategy_id']==strategy]
        for w in windows:
            start,end=instant(w['test_start']),instant(w['test_end'])
            bars=[b for b in a['normalized']['15'] if start<=instant(b['opened_at']) and instant(b['opened_at'])+timedelta(minutes=15)<=end]
            signals=[s for s in a['candidates'] if s['strategy_id']==strategy and start<=instant(s['entry_at'] or s['signal_at'])<end]
            for name,limits in c['profiles'].items():
                p=load_profile(root);p.update(profile=name,risk_fraction=limits['risk_fraction'],maximum_trade_risk_usd=limits['trade_risk_cap_usd'],daily_loss_budget_usd=limits['daily_loss_budget_usd'])
                sim=Simulator(folder/(strategy+'-'+w['name']+'-'+name+'.sqlite3'),p,costs,ids[strategy])
                try: results.append(dict(strategy=strategy,strategy_version=ids[strategy]['strategy_version'],profile=name,window=w,**replay(sim,bars,signals,exits),journal_hash=sim.head))
                finally: sim.db.close()
    labels=historical_labels(a);calibrator=Calibrator(labels,c['probability'],walk_forward(split))
    calibration=[calibrator.estimate(dict(strategy='trend',side=side,regime=r),split['end']) for side in ('BUY','SELL') for r in ('UPTREND','DOWNTREND','RANGE','HIGH_VOLATILITY','LOW_VOLATILITY')]
    report=dict(scope=SCOPE,classification='SIMULATED_SHADOW',configuration=c,costs=costs,cost_evidence=evidence,provenance=provenance,
                source_split=split,strategy_versions=ids,results=results,calibration=calibration,counterfactual_label_count=len(labels),
                decision='NO_VIABLE_STRATEGY_FOUND',fresh_oos=False,final_holdout_opened=False,broker_orders=0,openai_calls=0,
                no_trade_metrics_are_undefined=True,baseline_strategy='trend_V1_REFERENCE_NOT_PROFITABILITY_SELECTION')
    with (folder/'report.json').open('xb') as f:f.write(encoded(report))
    return dict(report=str((folder/'report.json').relative_to(root)),decision=report['decision'],scenarios=len(results),admitted=sum(r['admitted'] for r in results),broker_orders=0,openai_calls=0)


def process(s,observation,calibrator,provider=None):
    s.sync();at=observation['at'];quote=observation['quote'];analysis=observation['analysis'];features=feature_engine(analysis,quote,at)
    protocol=s.state['protocol'];c=protocol['configuration'];costs=protocol['costs']; sims={}
    try:
        pending=s.state.get('pending_counterfactual')
        if pending:
            for b in analysis['normalized']['15']:
                if instant(b['opened_at'])<instant(pending['entry_at']) or instant(b['opened_at'])+timedelta(minutes=15)>instant(at):continue
                if pending.get('last_opened_at') and instant(b['opened_at'])<=instant(pending['last_opened_at']):continue
                previous=pending.get('last_opened_at',pending['entry_at'])
                d=exit_decision(pending,b,previous,analysis['exit_signals'],True) if b['opened_at']!=pending['entry_at'] else None
                d=d or exit_decision(pending,b,previous,analysis['exit_signals'],False)
                pending['last_opened_at']=b['opened_at']
                if d:
                    label=dict(opportunity_id=pending['id'],strategy='trend',side=pending['side'],regime=pending['regime'],signal_at=pending['entry_at'],resolved_at=d[2],
                               outcome='TP' if d[1]=='TAKE_PROFIT' else 'SL' if d[1].startswith('STOP') else 'COMPETING_EXIT',
                               source='FORWARD_COUNTERFACTUAL_NOT_A_TRADE_NOT_A_STRATEGY_WIN')
                    s.state.setdefault('forward_labels',[]).append(label)
                    s.state.setdefault('resolved_label_ids',[]).append(pending['id'])
                    if pending['probability'] is not None:
                        s.state['calibration_records'].append(dict(opportunity_id=pending['id'],probability=pending['probability'],outcome=label['outcome'],classification=label['source']))
                    s.state['pending_counterfactual']=None;break
        for name,config in c['profiles'].items():
            p=load_profile(s.root);p.update(profile=name,risk_fraction=config['risk_fraction'],maximum_trade_risk_usd=config['trade_risk_cap_usd'],daily_loss_budget_usd=config['daily_loss_budget_usd'])
            sim=Simulator(s.folder/(name+'.sqlite3'),p,costs,protocol['strategy'],positive_expectancy_evidence=True);sims[name]=sim
            if sim.head!=s.state['portfolio_heads'][name]: raise ValueError('SHADOW_PORTFOLIO_HEAD_CONFLICT_RECONCILE_FIRST')
            for b in analysis['normalized']['15']:
                if instant(b['opened_at'])+timedelta(minutes=15)<=instant(at): sim.mark(b,analysis['exit_signals'])
            for trade in sim.state['trades']:
                identity=trade['signal'].get('opportunity_id')
                if not identity or identity in s.state.get('settled_opportunity_ids',[]): continue
                outcome='TP' if trade['close_reason']=='TAKE_PROFIT' else 'SL' if trade['close_reason'].startswith('STOP') else 'COMPETING_EXIT'
                prediction=trade['signal']['probability']['probability']
                label=dict(opportunity_id=identity,signal_at=trade['signal']['signal_at'],resolved_at=trade['exit_at'],side=trade['side'],strategy='trend',
                           regime=trade['signal']['regime'],outcome=outcome,source='SIMULATED_SHADOW_NOT_BROKER_FILL')
                if identity not in s.state.setdefault('resolved_label_ids',[]):
                    s.state.setdefault('forward_labels',[]).append(label);s.state['resolved_label_ids'].append(identity)
                s.state.setdefault('settled_opportunity_ids',[]).append(identity)
                if not any(r['opportunity_id']==identity for r in s.state['calibration_records']):
                    s.state['calibration_records'].append(dict(opportunity_id=identity,probability=prediction,outcome=outcome))
        current=next((deepcopy(x) for x in reversed(analysis['candidates']) if x['strategy_id']=='trend' and 0<=(instant(at)-instant(x['signal_at'])).total_seconds()<900),None)
        decisions={}; opportunity=None
        if current:
            current['entry_at']=current['signal_at'];current['reasons']=[r for r in current['reasons'] if r!='NO_NEXT_CLOSED_BAR']
            current['entry_midpoint']=str((number(quote['bid'])+number(quote['ask']))/2) if quote.get('bid') and quote.get('ask') else None
            identity=sha(dict(signal_at=current['signal_at'],strategy=protocol['strategy']['strategy_version'],side=current['side']))
            opportunity=dict(id=identity,at=current['signal_at'],strategy='trend',side=current['side'],regime=features['regime'],features=features,
                             stop_distance=current['stop_distance'],target_distance=current['take_profit_distance'],raw_reward_risk=str(number(current['take_profit_distance'])/number(current['stop_distance'])))
            opportunity['probability']=calibrator.estimate(opportunity,current['signal_at'])
            if identity not in s.state['seen']:
                size={name:sim.size(current,current['entry_at']) if current['entry_midpoint'] else dict(admitted=False,reason='QUOTE_MISSING') for name,sim in sims.items()}
                any_ev=any(d['admitted'] and opportunity['probability']['status']=='CALIBRATED_RESEARCH_ESTIMATE' and number(opportunity['probability']['lower_95'])*number(d['net_target'])-(1-number(opportunity['probability']['lower_95']))*number(d['risk'])>0 for d in size.values())
                advice=contextual(s,opportunity,provider=provider) if any_ev else dict(recommendation='INSUFFICIENT_EVIDENCE',reasons=['DETERMINISTIC_ECONOMIC_OR_SAMPLE_BLOCK'],limitations=['NO_BILLABLE_CALL'])
                opportunity['contextual']=advice
                # Observe price-path outcomes even for an economically rejected
                # signal. These are never portfolio trades or profitability.
                timely=quote.get('type')=='LIVE' and quote.get('market_status')=='OPEN' and quote.get('at') and 0<=(instant(quote['at'])-instant(current['entry_at'])).total_seconds()<=5
                if not current['reasons'] and timely and not s.state.get('pending_counterfactual') and current['entry_midpoint']:
                    direction=1 if current['side']=='BUY' else -1;mid=number(current['entry_midpoint'])
                    s.state['pending_counterfactual']=dict(id=identity,strategy='trend',side=current['side'],regime=features['regime'],entry_at=current['entry_at'],
                        stop=str(mid-direction*number(current['stop_distance'])),target=str(mid+direction*number(current['take_profit_distance'])),
                        probability=opportunity['probability']['probability'],classification='COUNTERFACTUAL_NO_TRADE_PRICE_PATH')
                for name,sim in sims.items():
                    gate=economic_gate(size[name],opportunity['probability'],advice)
                    if gate['decision']=='TRADE':
                        current['probability']=opportunity['probability'];current['regime']=features['regime'];current['opportunity_id']=identity
                        admitted=sim.enter(current,forward=True,quote=quote)
                        if not admitted['admitted']: gate.update(decision='NO_TRADE',reason=admitted['reason'])
                    decisions[name]=dict(**gate,size=size[name],opportunity_id=identity,signal_timestamp=current['signal_at'],stop_distance=current['stop_distance'],target_distance=current['take_profit_distance'],reference_midpoint=current['entry_midpoint'],regime=features['regime'])
                s.state['seen'].append(identity)
            else: decisions={name:dict(decision='NO_TRADE',reason='OPPORTUNITY_ALREADY_EVALUATED',opportunity_id=identity) for name in PROFILES}
        else: decisions={name:dict(decision='NO_TRADE',reason='NO_VALID_STRATEGY_SIGNAL') for name in PROFILES}
        for name,sim in sims.items():
            s.state['portfolio_heads'][name]=sim.head;s.state['portfolio_metrics'][name]=sim.metrics()
        s.state['calibration_metrics']=calibration_metrics(s.state['calibration_records'])
        calibrator.labels=[r for r in calibrator.labels if r['source'] not in ('SIMULATED_SHADOW_NOT_BROKER_FILL','FORWARD_COUNTERFACTUAL_NOT_A_TRADE_NOT_A_STRATEGY_WIN')]+s.state.get('forward_labels',[])
        n=len(s.state.get('settled_opportunity_ids',[]))
        if n>=100 and s.state['research_handoff'] is None:
            # A consolidated handoff is prepared, not a billed research session.
            value=dict(study=s.study,classification='SIMULATED_SHADOW',portfolio_metrics=s.state['portfolio_metrics'],
                       calibration=s.state['calibration_metrics'],execution_authorized=False,automatic_adoption=False,
                       broker_orders=0,openai_calls=0,final_holdout_opened=False,
                       required_validation=['BACKTEST','WALK_FORWARD','INDEPENDENT_SHADOW_FORWARD','SEALED_FINAL_REVIEW'])
            target=s.folder/'research-handoff.json'
            with target.open('xb') as f: f.write(encoded(value))
            s.state['research_handoff']=dict(path=str(target.relative_to(s.root)),sha256=sha(value),billed=False)
        s.state['last_observation']=at;s.state['status']='SHADOW_RESEARCH_RUNNING'
        s.append('COMMON_MARKET_OPPORTUNITY_EVALUATED',dict(observation_source=observation['source'],observation_sha256=sha(observation),history_source=observation.get('history_source'),quote=quote,features=features,opportunity=opportunity,decisions=decisions,capabilities=observation.get('capabilities'),api_events=observation.get('api_events',[])))
        if s.state.get('research_handoff'):
            from .ai_strategy_researcher.simulation_memory import save_shadow
            save_shadow(s.root,s.study,s.revision,s.head,s.state['research_handoff'])
        return dict(study=s.study,at=at,decisions=decisions,metrics=s.state['portfolio_metrics'],broker_orders=0,openai_calls=s.state['openai']['calls'])
    finally:
        for sim in sims.values(): sim.db.close()


def run(root,study,once=False):
    from .stock_paper_forward_runner import run_lock
    root=Path(root).resolve();s=Study(root,study);reader=None
    stop=s.folder/'stop.request'
    try:
        if not s.state: raise ValueError('PREREGISTERED_STUDY_REQUIRED')
        if s.state['protocol'].get('engine_hashes')!=engine_hashes(root):raise ValueError('SHADOW_ENGINE_CHANGED_NEW_PREREGISTRATION_REQUIRED')
        if stop.exists(): raise ValueError('SHADOW_STUDY_STOPPED_CREATE_NEW_STUDY_OR_REVIEW')
        labels=json.loads((s.folder/'labels.json').read_bytes())
        if sha(labels)!=s.state['protocol']['label_sha256']: raise ValueError('CALIBRATION_EVIDENCE_CHANGED')
        calibration=Calibrator(labels+s.state.get('forward_labels',[]),s.state['protocol']['configuration']['probability'],s.state['protocol']['folds'])
        with run_lock(s.folder/'runner.lock'):
            reader=MarketReader(root)
            while not stop.exists():
                result=process(s,reader.observe(),calibration);print(json.dumps(result,allow_nan=False),flush=True)
                if once: break
                # Wake on every bar boundary; chunked waits permit cancellation.
                wait=min(s.state['protocol']['configuration']['poll_seconds'],900-time.time()%900)
                deadline=time.monotonic()+wait
                while not stop.exists() and time.monotonic()<deadline: time.sleep(min(1,max(0,deadline-time.monotonic())))
            s.state['status']='STOPPED_SHADOW_ONLY' if stop.exists() else 'BOUNDED_READ_ONLY_STEP_COMPLETED'
            s.append('RUNNER_STOPPED',dict(pending_positions={p:m['pending_position'] for p,m in s.state['portfolio_metrics'].items()},emergency_untouched=True))
    except Exception as error:
        if not s.state: raise
        s.state['status']='SUSPENDED_READ_ONLY_OR_PERSISTENCE_UNCERTAINTY'
        reason=str(error) if re.fullmatch('[A-Z0-9_]{1,100}',str(error)) else type(error).__name__
        s.append('RUNNER_SUSPENDED',dict(reason=reason,no_order_retry=True));raise
    finally:
        if reader: reader.close()
        s.db.close()


def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['Prepare','Comparison','Run','Once','Status','Stop']);p.add_argument('--root',default='.');p.add_argument('--study');p.add_argument('--openai-budget',default='0');args=p.parse_args()
    if args.action=='Comparison': result=compare(args.root)
    elif args.action=='Prepare': result=prepare(args.root,args.study,args.openai_budget)
    elif args.action in ('Run','Once'): run(args.root,args.study,args.action=='Once');return
    else:
        s=Study(args.root,args.study)
        try:
            if args.action=='Stop':
                with (s.folder/'stop.request').open('a') as f: f.write('OPERATOR_REQUESTED_SHADOW_STOP\n')
                result=dict(study=args.study,stop_requested=True,broker_orders=0)
            else: result=dict(study=args.study,state=s.state,postgres_revision=s.revision,broker_orders=0)
        finally: s.db.close()
    print(json.dumps(result,allow_nan=False))


if __name__=='__main__':
    try: main()
    except Exception as error:
        reason=str(error) if re.fullmatch('[A-Z0-9_]{1,100}',str(error)) else type(error).__name__
        print(json.dumps(dict(state='SUSPENDED',reason=reason,broker_orders=0,live_enabled=False)));raise SystemExit(1)
