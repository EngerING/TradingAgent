"""Isolated LONG equity research. Never imports an order adapter or authorizes trades."""
import argparse
from bisect import bisect_right
from collections import Counter
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_FLOOR, ROUND_CEILING
import hashlib
import json
from pathlib import Path
from statistics import mean, pstdev
from zoneinfo import ZoneInfo
from .progressive_risk_research import uncertainty

RATES=(1,2,3,5,7.5,10,12.5,15)
FAMILIES=('EQ_TREND_R0','EQ_PULLBACK_R0','EQ_BREAKOUT_R0','EQ_MEAN_REVERSION_R0')
TIMEFRAMES=(60,1440)
MODELS=('TIERED_BASE','TIERED_SPREAD_SLIPPAGE_STRESS','FIXED_FEE_STRESS')
FAMILY_TESTS=len(RATES)*len(FAMILIES)*len(TIMEFRAMES)*len(MODELS)
PARAMETERS={'fast':10,'slow':20,'context':50,'atr':14,'breakout':20,'volume_confirmation':1.5,
    'mean_z':2,'trend_stop_atr':1.5,'trend_target_r':2,'pullback_stop_atr':1,
    'pullback_target_r':2,'breakout_stop_atr':1.5,'breakout_target_r':2,
    'mean_stop_atr':1,'maximum_hold_bars':20,'mean_slope_ceiling':.005,'research_price_tick':.01}
ZONE=ZoneInfo('America/Santo_Domingo')
NY=ZoneInfo('America/New_York')
D=Decimal


def at(value):
    result=datetime.fromisoformat(value.replace('Z','+00:00'))
    if result.tzinfo is None:raise ValueError('UTC_TIMESTAMP_REQUIRED')
    return result.astimezone(timezone.utc)


def num(value):
    v=D(str(value))
    if not v.is_finite() or abs(v)>D('1e12'):raise ValueError('INVALID_RESEARCH_NUMBER')
    return v


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def price_tick(price,buy=False):
    tick=num(PARAMETERS['research_price_tick'])
    return (num(price)/tick).to_integral_value(rounding=ROUND_CEILING if buy else ROUND_FLOOR)*tick


def candidate_versions():
    return {name:digest({'strategy':name,'parameters':PARAMETERS,'engine':'equity-research-v1',
        'side':'LONG','timeframes':TIMEFRAMES,'rule':'completed_bar_next_open_stop_first'}) for name in FAMILIES}


def commission(q,price,model):
    # Published US schedule; applicable account plan still UNKNOWN.
    if model not in MODELS:raise ValueError('COST_MODEL_REQUIRED')
    q,price=num(q),num(price)
    if q<=0 or price<=0:raise ValueError('POSITIVE_TRADE_REQUIRED')
    rate,minimum=(D('.005'),D('1')) if model=='FIXED_FEE_STRESS' else (D('.0035'),D('.35'))
    base=min(max(q*rate,minimum),q*price*D('.01'))
    # Route/clearing/regulatory envelope, NOT an observed/account-specific tariff.
    extra=D('.02')+q*D('.01')
    return base+extra


def costs(price,model,observed_relative_spread=None):
    price=num(price)
    if price<=0 or model not in MODELS:raise ValueError('INVALID_COST_SCENARIO')
    floor=max(D('.0005'),num(observed_relative_spread or 0))
    spread=price*floor*(2 if model=='TIERED_SPREAD_SLIPPAGE_STRESS' else 1)
    slip=price*(D('.0015') if model=='TIERED_SPREAD_SLIPPAGE_STRESS' else D('.0005'))
    gap=price*(D('.01') if model=='TIERED_SPREAD_SLIPPAGE_STRESS' else D('.005'))
    return spread,slip,gap


class Ledger:
    def __init__(self,snapshot=None):
        self.equity=D('100');self.cash=D('100');self.consumed=D('0');self.stop_days={};self.unsettled=[];self.pending=None
        if snapshot:
            for key in ('equity','cash','consumed'):setattr(self,key,num(snapshot[key]))
            self.stop_days=dict(snapshot['stop_days']);self.unsettled=list(snapshot['unsettled']);self.pending=snapshot['pending']

    def snapshot(self):
        return {**{k:str(getattr(self,k)) for k in ('equity','cash','consumed')},
            'stop_days':self.stop_days,'unsettled':self.unsettled,'pending':self.pending}

    def day(self,t):return at(t).astimezone(ZONE).date().isoformat()

    def available(self,t):
        day=at(t).astimezone(NY).date().isoformat();remaining=[]
        for lot in self.unsettled:
            if lot['settles'] is not None and lot['settles']<=day:self.cash+=num(lot['amount'])
            else:remaining.append(lot)
        self.unsettled=remaining
        return self.cash

    def gate(self,t):
        if self.pending is not None:return 'PREVIOUS_TRADE_NOT_RECONCILED'
        if self.consumed>=20 or self.equity<=0:return 'CUMULATIVE_LOSS_OR_CAPITAL_STOP'
        return self.stop_days.get(self.day(t))

    def begin(self,token,spent):
        if self.pending is not None:raise ValueError('ONE_POSITION_ONLY')
        spent=num(spent)
        if spent<0 or spent>self.cash:raise ValueError('SETTLED_FUNDS_REQUIRED')
        self.cash-=spent;self.pending={'token':token,'spent':str(spent)}

    def settle(self,token,net,proceeds,t,settles,definitive=True):
        if not self.pending or self.pending['token']!=token:raise ValueError('OWNED_POSITION_REQUIRED')
        if not definitive:return False
        net=num(net);proceeds=num(proceeds)
        self.equity+=net;self.consumed+=max(D('0'),-net)
        self.unsettled.append({'settles':settles,'amount':str(proceeds)})
        if net<=0:self.stop_days[self.day(t)]='DAILY_FIRST_LOSS_STOP' if net<0 else 'DAILY_BREAK_EVEN_STOP'
        self.pending=None;return True


def validated_bars(rows):
    result=[];previous=None
    for row in rows:
        opened,closed=at(row['opened_at']),at(row['closed_at'])
        o,h,l,c=[num(row[k]) for k in ('open','high','low','close')];volume=num(row['volume'])
        if not opened<closed or (previous is not None and opened<previous) or min(o,h,l,c)<=0 or h<max(o,l,c) or l>min(o,h,c) or volume<0:
            raise ValueError('INVALID_OR_OVERLAPPING_EQUITY_BARS')
        previous=closed
        result.append({**row,'open':float(o),'high':float(h),'low':float(l),'close':float(c),'volume':float(volume)})
    return result


def features(rows):
    result=[];closes=[];ranges=[];fast=None;slow=None
    for index,r in enumerate(rows):
        c=r['close'];closes.append(c)
        tr=max(r['high']-r['low'],abs(r['high']-closes[index-1]),abs(r['low']-closes[index-1])) if index else r['high']-r['low']
        ranges.append(tr);fast=c if fast is None else fast+2/(PARAMETERS['fast']+1)*(c-fast)
        slow=c if slow is None else slow+2/(PARAMETERS['slow']+1)*(c-slow)
        result.append(dict(fast=fast,slow=slow,context=mean(closes[-PARAMETERS['context']:]),center=mean(closes[-PARAMETERS['slow']:]),
            sigma=pstdev(closes[-PARAMETERS['slow']:]),atr=mean(ranges[-PARAMETERS['atr']:]),ready=index>=PARAMETERS['context']))
    return result


def signals(rows,family):
    if family not in FAMILIES:raise ValueError('EXPERIMENTAL_FAMILY_REQUIRED')
    fs=features(rows);result=[]
    for i in range(PARAMETERS['context'],len(rows)-1):
        r,p=rows[i],rows[i-1];f,prev=fs[i],fs[i-1];atr=f['atr'];valid=False
        if atr<=0:continue
        if family=='EQ_TREND_R0':
            valid=prev['fast']<=prev['slow'] and f['fast']>f['slow'] and r['close']>f['context']
            distance=PARAMETERS['trend_stop_atr']*atr
            stop=r['close']-distance;target=r['close']+PARAMETERS['trend_target_r']*distance
        elif family=='EQ_PULLBACK_R0':
            valid=f['fast']>f['slow'] and r['close']>f['context'] and p['low']<=prev['slow'] and p['close']<=prev['slow'] and r['close']>f['slow']
            distance=PARAMETERS['pullback_stop_atr']*atr
            stop=r['close']-distance;target=r['close']+PARAMETERS['pullback_target_r']*distance
        elif family=='EQ_BREAKOUT_R0':
            high=max(x['high'] for x in rows[i-PARAMETERS['breakout']:i]);vol=mean(x['volume'] for x in rows[i-PARAMETERS['breakout']:i])
            valid=r['close']>high and r['close']>f['context'] and vol>0 and r['volume']>=PARAMETERS['volume_confirmation']*vol
            distance=PARAMETERS['breakout_stop_atr']*atr
            stop=r['close']-distance;target=r['close']+PARAMETERS['breakout_target_r']*distance
        else:
            valid=p['close']<prev['center']-PARAMETERS['mean_z']*prev['sigma'] and r['close']>p['close'] and abs(f['context']/fs[i-5]['context']-1)<=PARAMETERS['mean_slope_ceiling']
            stop=r['close']-PARAMETERS['mean_stop_atr']*atr;target=f['center']
        stop,target=float(price_tick(stop)),float(price_tick(target))
        if valid and 0<stop<r['close']<target:
            result.append(dict(index=i,entry_index=i+1,at=r['closed_at'],stop=stop,target=target,
                indicators=f,reason=family+'_COMPLETED_BAR',source_price=r['close']))
    return result,fs


def exit_price(rows,fs,signal,entry_index,family):
    stop,target=signal['stop'],signal['target']
    for j in range(entry_index,min(len(rows),entry_index+PARAMETERS['maximum_hold_bars'])):
        r=rows[j]
        # Prior completed bar's context/crossover exit acts at this open.
        trend_invalid=family!='EQ_MEAN_REVERSION_R0' and (fs[j-1]['fast']<fs[j-1]['slow'] or rows[j-1]['close']<fs[j-1]['context'])
        if j>entry_index and (j-entry_index>=PARAMETERS['maximum_hold_bars']-1 or trend_invalid):
            return j,r['open'],'RULE_NEXT_OPEN',r['opened_at']
        if r['open']<=stop:return j,r['open'],'STOP_GAP',r['opened_at']
        if r['low']<=stop:return j,stop,'STOP_FIRST_IF_AMBIGUOUS',r['closed_at']
        if r['high']>=target:return j,target,'TARGET_LIMIT_CONSERVATIVE',r['closed_at']
    return None


def size(entry,stop,target,rate,ledger,model,spread_ratio):
    if rate not in RATES:raise ValueError('RISK_OUTSIDE_PROTOCOL')
    price=num(entry);stop=num(stop);target=num(target)
    if not 0<stop<price<target:return None,'ENTRY_GAP_INVALIDATES_GEOMETRY'
    spread,slip,gap=costs(price,model,spread_ratio)
    budget=min(ledger.equity*num(rate)/100,D('20')-ledger.consumed)
    upper=int((min(ledger.equity,ledger.cash)/price).to_integral_value(rounding=ROUND_FLOOR))
    if upper<1:return None,'WHOLE_SHARE_OR_SETTLED_FUNDS_UNAFFORDABLE'
    for q in range(upper,0,-1):
        paid_entry=price_tick(price+spread/2+slip,buy=True)
        fees=commission(q,paid_entry,model)+commission(q,target,model)
        risk=q*(price-stop+spread+2*slip+gap+D('.02'))+fees
        cash_required=q*paid_entry+fees
        net_target=q*(target-price-spread-2*slip-gap-D('.02'))-fees
        if risk<=budget and cash_required<=ledger.cash and net_target>0:
            return dict(quantity=q,risk=float(risk),budget=float(budget),fees_reserved=float(fees),
                spread=float(spread),slippage_each=float(slip),gap_reserved=float(gap),rounding_reserve_each=.01,
                target_net=float(net_target),notional=float(q*price)),None
    return None,'COSTS_RISK_FUNDS_OR_TARGET_FAIL'


def metrics(trades,rejections,ledger,max_dd,days,risk_breaches):
    nets=[x['netPnl'] for x in trades];wins=[x for x in nets if x>0];losses=[x for x in nets if x<0]
    return dict(admitted=len(trades),rejected=sum(rejections.values()),rejection_reasons=dict(rejections),
        win_rate=len(wins)/len(nets) if nets else None,average_profit=mean(wins) if wins else None,
        average_loss=mean(losses) if losses else None,net_expectancy=mean(nets) if nets else None,
        profit_factor=sum(wins)/abs(sum(losses)) if losses else None,
        gross_pnl=sum(t['grossPnl'] for t in trades),net_pnl=sum(nets),commissions=sum(t['commissions'] for t in trades),
        spread_slippage=sum(t['spreadSlippage'] for t in trades),maximum_drawdown=max_dd,
        stopped_days=len(ledger.stop_days),first_loss_days=sum(x=='DAILY_FIRST_LOSS_STOP' for x in ledger.stop_days.values()),
        trade_days=len(days),equity=float(ledger.equity),consumed_loss=float(ledger.consumed),
        risk_budget_breaches=risk_breaches,capital_exhausted=ledger.equity<=0,
        capital_ruin_probability=None,execution_probability=None,pending_position=ledger.pending,
        unsettled_proceeds=ledger.unsettled,settled_cash=float(ledger.cash),
        execution_verified=False,execution_authorized=False)


def simulate(series,family,rate,model,start,end,spread_ratios=None,prepared=None):
    start,end=at(start),at(end);ledger=Ledger();events=[];reject=Counter();features_by={}
    session_days=sorted({at(r['opened_at']).astimezone(NY).date().isoformat() for rows in series.values() for r in rows})
    for symbol,rows in series.items():
        candidates,fs=prepared[symbol] if prepared is not None else signals(rows,family);features_by[symbol]=fs
        for s in candidates:
            i=s['entry_index'];t=at(rows[i]['opened_at'])
            # Purge: signal itself must be fully inside test window; feature warm-up only is shared.
            if start<=at(s['at'])<=t<end:events.append((t,symbol,s))
    events.sort(key=lambda x:(x[0],x[1]));busy_until=None;trades=[];peak=D('100');dd=0.;days=set();breaches=0
    for t,symbol,s in events:
        rows=series[symbol];i=s['entry_index'];stamp=t.isoformat()
        if busy_until is not None and t<=busy_until:reject['ONE_POSITION_OR_UNCERTAIN_INTRABAR_CLOSE']+=1;continue
        gate=ledger.gate(stamp)
        if gate:reject[gate]+=1;continue
        ledger.available(stamp)
        plan,reason=size(rows[i]['open'],s['stop'],s['target'],rate,ledger,model,(spread_ratios or {}).get(symbol))
        if plan is None:reject[reason]+=1;continue
        exit=exit_price(rows,features_by[symbol],s,i,family)
        q=plan['quantity'];raw_entry=num(rows[i]['open']);spread=num(plan['spread']);slip=num(plan['slippage_each'])
        fill_entry=price_tick(raw_entry+spread/2+slip,buy=True);opening=commission(q,fill_entry,model)
        # Ensure actual modeled paid BUY and closing reserve also fit fully funded cash.
        if q*fill_entry+opening+commission(q,num(s['target']),model)>ledger.cash:
            reject['EXECUTED_BUY_AND_CLOSING_RESERVE_EXCEED_SETTLED_CASH']+=1;continue
        token=digest({'symbol':symbol,'family':family,'entry':stamp,'risk':rate,'cost':model})
        ledger.begin(token,q*fill_entry+opening)
        if exit is None or at(exit[3])>=end:
            busy_until=end;reject['PENDING_AT_PARTITION_BOUNDARY']+=1
            continue
        j,raw_exit,why,exit_at=exit;fill_exit=price_tick(num(raw_exit)-spread/2-slip)
        closing=commission(q,fill_exit,model)
        gross=q*(num(raw_exit)-raw_entry);price_cost=gross-q*(fill_exit-fill_entry);net=gross-price_cost-opening-closing
        exit_day=at(exit_at).astimezone(NY).date().isoformat();next_idx=bisect_right(session_days,exit_day)
        settles=session_days[next_idx] if next_idx<len(session_days) else None
        before=ledger.equity
        # Mark-to-low, including both commissions, before closing; gap losses are NOT capped.
        # Do not use a bar's later low when an exit occurred at that bar's open.
        marked=rows[i:j] if why in ('RULE_NEXT_OPEN','STOP_GAP') else rows[i:j+1]
        lows=[r['low'] for r in marked]+[float(raw_exit)]
        worst=before+q*(num(min(lows))-raw_entry)-price_cost-opening-closing
        dd=max(dd,float((peak-worst)/peak));busy_until=at(exit_at)
        ledger.settle(token,net,q*fill_exit-closing,exit_at,settles)
        peak=max(peak,ledger.equity);dd=max(dd,float((peak-ledger.equity)/peak));days.add(ledger.day(exit_at))
        breach=-net>num(plan['budget']);breaches+=breach
        trades.append(dict(symbol=symbol,strategy=family,side='LONG',entryAt=stamp,exitAt=exit_at,
            signalAt=s['at'],indicators=s['indicators'],reason=s['reason'],quantity=q,
            expected_entry=float(raw_entry),entry_fill=float(fill_entry),exit_fill=float(fill_exit),
            stop=s['stop'],target=s['target'],close_reason=why,grossPnl=float(gross),netPnl=float(net),
            commissions=float(opening+closing),opening_commission=float(opening),closing_commission=float(closing),
            spreadSlippage=float(price_cost),equity=float(ledger.equity),remaining_loss=float(20-ledger.consumed),
            planned_risk=plan['risk'],risk_budget=plan['budget'],risk_breach=breach,settles=settles,
            continue_decision='WIN_CAN_SEEK_SIGNAL_WITH_SETTLED_FUNDS' if net>0 else 'DAILY_FIRST_LOSS_STOP' if net<0 else 'DAILY_BREAK_EVEN_STOP'))
    return dict(metrics=metrics(trades,reject,ledger,dd,days,breaches),trades=trades,
        confidence=uncertainty(trades,f'{family}:{rate}:{model}:{start}',family_tests=FAMILY_TESTS))


def evidence_checks(result,folds,verified=False):
    m=result['metrics'];ci=result['confidence'];reasons=[]
    if m['admitted']<100 or m['trade_days']<30:reasons.append('INSUFFICIENT_OOS_SAMPLE')
    if m['win_rate'] is None or m['win_rate']<=.8:reasons.append('NET_WIN_RATE_NOT_ABOVE_80_PERCENT')
    if ci['win_wilson_family_adjusted'] is None or ci['win_wilson_family_adjusted'][0]<=.8:reasons.append('WIN_RATE_CONFIDENCE_INSUFFICIENT')
    if m['net_expectancy'] is None or m['net_expectancy']<=0 or m['profit_factor'] is None or m['profit_factor']<=1:reasons.append('NET_ECONOMICS_INSUFFICIENT')
    ev=ci['block_bootstrap_expectancy_ci']
    if ev is None or ev[0]<=0:reasons.append('EXPECTANCY_CONFIDENCE_INSUFFICIENT')
    if m['maximum_drawdown']>.2 or m['risk_budget_breaches']:reasons.append('DRAWDOWN_OR_GAP_RISK')
    if m['pending_position']:reasons.append('PARTITION_END_POSITION_UNRESOLVED')
    if len(folds)!=3 or any(f['metrics']['admitted']==0 or f['metrics']['net_pnl']<=0 for f in folds):reasons.append('WALK_FORWARD_INSUFFICIENT')
    if not verified:reasons.append('IBKR_PERMISSIONS_TARIFF_SETTLEMENT_AND_PROTECTION_UNVERIFIED')
    reasons.extend(['LIMITED_SURVIVING_UNIVERSE','CORPORATE_ACTION_AND_DELISTED_DATA_INCOMPLETE',
        'NEW_UNEXAMINED_CONFIRMATION_REQUIRED','PRODUCTION_STOCK_ADAPTER_NOT_IMPLEMENTED'])
    return dict(status='NO_VIABLE_STRATEGY_FOUND',reasons=reasons,execution_authorized=False,live_approved=False)


def run(root):
    root=Path(root);folder=root/'artifacts/research/us-equities';raw=(folder/'ibkr-readonly.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=(folder/'ibkr-readonly.sha256').read_text().strip():raise ValueError('DATASET_HASH_MISMATCH')
    data=json.loads(raw);versions=candidate_versions();rows=[];spreads={};datasets={};limits=[]
    account_path=folder/'account-details-readonly.json'
    if account_path.exists():
        detail_raw=account_path.read_bytes();detail=json.loads(detail_raw)
        if detail.get('identity_verified') is not True or detail.get('account')!=data.get('account') or detail.get('orders_sent')!=0:
            raise ValueError('READONLY_ACCOUNT_EVIDENCE_MISMATCH')
        data['account_details']=detail.get('account_details')
        data['account_details_sha256']=hashlib.sha256(detail_raw).hexdigest()
        codes=[v['value'] for v in (data.get('account_details') or {}).get('values',[]) if v['tag']=='TradingType-S']
        data['account_margin_interpretation']=dict(observed_codes=codes,
            inference='CONSISTENT_WITH_REG_T_MARGIN' if codes==['STKNOPT'] else 'UNKNOWN',
            applicable_intraday_restrictions_verified=False,
            source='https://www.interactivebrokers.com/campus/trading-lessons/risk-navigator-alternative-margin-calculator/')
    for symbol,record in data['symbols'].items():
        quote=record.get('quote',{})
        if quote.get('bid') and quote.get('ask'):
            mid=(num(quote['bid'])+num(quote['ask']))/2;spreads[symbol]=float((num(quote['ask'])-num(quote['bid']))/mid)
        for tf,bars in record.get('bars',{}).items():datasets[(symbol,int(tf))]=validated_bars(bars)
    coverage={}
    for symbol,record in data['symbols'].items():
        expected={s['day'] for s in record.get('sessions',[])}
        coverage[symbol]={}
        for tf in TIMEFRAMES:
            actual={at(b['opened_at']).astimezone(NY).strftime('%Y%m%d') for b in datasets.get((symbol,tf),[])}
            coverage[symbol][str(tf)]=dict(expected_sessions=len(expected),observed_sessions=len(actual),
                missing_sessions=sorted(expected-actual),unexpected_sessions=sorted(actual-expected))
    partitions=[('continuous','2026-04-03T00:00:00Z','2026-10-03T00:00:00Z'),
        ('development','2026-04-03T00:00:00Z','2026-08-03T00:00:00Z'),
        ('validation','2026-08-03T00:00:00Z','2026-10-03T00:00:00Z'),
        ('walk_forward_1','2026-08-03T00:00:00Z','2026-08-23T08:00:00Z'),
        ('walk_forward_2','2026-08-23T08:00:00Z','2026-09-12T16:00:00Z'),
        ('walk_forward_3','2026-09-12T16:00:00Z','2026-10-03T00:00:00Z')]
    for tf in TIMEFRAMES:
        series={s:r for (s,t),r in datasets.items() if t==tf}
        if set(series)!=set(data['universe']) or any(len(r)<100 for r in series.values()):
            limits.append(f'AUTHENTIC_DATASET_INCOMPLETE_{tf}');continue
        for family in FAMILIES:
            prepared={s:signals(r,family) for s,r in series.items()}
            for rate in RATES:
                for model in MODELS:
                    results={name:simulate(series,family,rate,model,start,end,spreads,prepared) for name,start,end in partitions}
                    selection=evidence_checks(results['validation'],[results[f'walk_forward_{i}'] for i in range(1,4)])
                    rows.append(dict(strategy=family,version=versions[family],minutes=tf,risk_percent=rate,cost_model=model,
                        results=results,selection=selection))
    report=dict(status='NO_VIABLE_STRATEGY_FOUND',capital_usd=100,maximum_research_risk_percent=15,
        exposure_limit=1,loss_allowance_usd=20,rates=RATES,parameters=PARAMETERS,versions=versions,
        policy='WIN_TO_CONTINUE / FIRST_LOSS_STOPS_DAY',day_timezone='America/Santo_Domingo',
        funding_policy='T_PLUS_1_AUTHENTIC_NEXT_SESSION_ONLY',optimization=False,
        dataset_sha256=hashlib.sha256(raw).hexdigest(),family_tests=FAMILY_TESTS,
        universe=data['universe'],timeframes=TIMEFRAMES,configurations=len(rows),partitions=partitions,
        scenario_results=len(rows)*len(partitions),dataset_counts={f'{s}:{t}':len(r) for (s,t),r in datasets.items()},
        session_coverage=coverage,
        incomplete_data=limits,broker_observations={k:v for k,v in data.items() if k not in ('symbols','receipts')},
        observed_spread_ratios=spreads,spread_source='ONE_IBKR_OBSERVATION_NOT_HISTORICAL_OR_EXECUTABLE',
        execution_authorized=False,live_enabled=False,orders_sent=0,rows=rows,
        caveats=['Development/validation and candidates defined before examining equity bars; not a preregistered external study.',
            'SCHX, SPY, F are a fixed surviving convenience sample, not a point-in-time liquid universe. No generalization to all stocks.',
            'TRADES split adjustment and corporate actions/dividends not independently reconciled; no dividend/interest income credited.',
            'Hourly gaps, missing sessions and historical quote/liquidity depth are not independently verified.',
            'Risk scenarios and cost families are multiple comparisons, not optimization; adjusted family=192.',
            '2000 bootstrap resamples have limited resolution at extreme family-adjusted tails; intervals remain approximate and insufficient for promotion.',
            'Walk-forward uses preceding bars only for causal warm-up; no refit. Purged signal boundaries; independent $100/$20 fold allocations.',
            'Commission minima plus conservative extra-fee envelope are estimates; real tiered plan, venue fees, fractional permissions unknown.',
            'Orders are modeled as one fill per side. Partial-fill modifications/overnight minimum resets, tax and market-data subscriptions are not account-verified; fixed-fee stress is not a bound on every possible fee.',
            '100 OOS trades / 30 days / 3 positive folds are research thresholds, not guarantees. Ruin probability unidentifiable.',
            'Targets are assumed limit fills with conservative stop priority; actual liquidity/queue probability not measured.',
            'Cash-account T+1 model is conservative. No reuse of sale proceeds before settlement; margin intraday regime unknown.'])
    (folder/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
    render(root,report,data)
    return report


def render(root,report,data):
    lines=['# Investigación LONG de acciones y ETF — capital virtual US$100','',
        '**NO_VIABLE_STRATEGY_FOUND.** Ningún candidato aprobado; emergencia y límites productivos intactos. Órdenes enviadas: 0.','',
        f"Configuraciones: {report['configurations']}; resultados por partición: {report['scenario_results']}; familia estadística: {FAMILY_TESTS}.",
        'Riesgos: 1%, 2%, 3%, 5%, 7.5%, 10%, 12.5%, 15%. Exposición 1×; presupuesto acumulado de pérdidas US$20, sin reposición por ganancias.',
        '', '## Verificación de IBKR (solo lectura)','',
        f"Identidad Paper coincidente: {data.get('identity_verified',False)}. API: {data.get('server_version','UNKNOWN')}. Cuenta: {data.get('account','UNKNOWN')}. Consultas de cuenta completas: {data.get('account_query_completed',False)}.",
        'AccountType de AccountSummary no acredita por sí mismo Cash/Margin, entidad ni régimen intradía. El saldo Paper no alimenta el dimensionamiento.',
        '', '| Símbolo | conId | Mínimo / incremento publicados por contrato | Órdenes declaradas | Datos | Barras 1h / diario |',
        '|---|---:|---|---|---|---|']
    for s,r in data['symbols'].items():
        c=r.get('contract',{});q=r.get('quote',{});b=r.get('bars',{})
        relevant=','.join(t for t in ('LMT','STP','STPLMT','OCA') if t in c.get('order_types','').split(',')) or 'UNKNOWN'
        lines.append(f"| {s} | {c.get('con_id','UNKNOWN')} | {c.get('minimum_size','UNKNOWN')} / {c.get('size_increment','UNKNOWN')} | {relevant} | {q.get('data_type','UNKNOWN')} | {len(b.get('60',[]))} / {len(b.get('1440',[]))} |")
    total_bars=sum(report['dataset_counts'].values())
    coverage_ok=all(not c['missing_sessions'] and not c['unexpected_sessions'] for by_tf in report['session_coverage'].values() for c in by_tf.values())
    lines+=['',f"Cobertura de sesiones completa: {coverage_ok}; {total_bars} velas originales. Detalle por instrumento y temporalidad en session_coverage del JSON. Precios OHLC y volumen preservados, duración de vela ajustada únicamente a las fronteras auténticas de sesión/siguiente vela.",
        'Cotizaciones: SCHX/SPY sin BID/ASK (IBKR_READ_TIMEOUT); F DELAYED. Ninguna cotización ejecutable. Spread de F observado usado conservadoramente; para SCHX/SPY, estimación de 5 bps y stress, sin atribuirla a una observación histórica.',
        f"Avisos 2188 conservados: solo se aceptaron datos históricos archivados con historicalDataEnd. Códigos 162/366 también observados; se conservaron códigos/timestamps, sin texto bruto de broker. No se atribuye una causa definitiva al 162 sin su texto. 366 indica ausencia de consulta histórica al cancelar; {len(data.get('receipts',[]))} consultas de velas terminaron con callback y {sum(bool(x.get('sessions')) for x in data['symbols'].values())} SCHEDULE devolvieron sesiones.",
        'Mínimo/incremento 0.0001 es metadato del contrato, no autorización de fracciones. La simulación admite únicamente cantidades enteras. SPY cuesta más de US$100 por acción en este histórico y queda fuera de acceso entero.']
    lines+=['','AccountSummary observado (no capital de estrategia):', '', '| Campo | Valor | Moneda |','|---|---|---|']
    for r in data.get('account_values',[]):lines.append(f"| {r['tag']} | {r['value']} | {r['currency']} |")
    if data.get('account_details'):
        lines+=['','AccountDownloadEnd adicional completado; campos seleccionados:', '', '| Campo | Valor | Moneda |','|---|---|---|']
        for r in data['account_details']['values']:lines.append(f"| {r['tag']} | {r['value']} | {r['currency']} |")
        lines.append(f"Portfolio recibido: {data['account_details']['portfolio']}. TradingType-S se conserva literalmente. STKNOPT es consistente con Reg T Margin según la nomenclatura publicada de IBKR (inferencia documentada); no acredita permisos geográficos ni restricciones intradía aplicables.")
        lines.append('SettledCash / DayTradesRemaining ausentes permanecen UNKNOWN; AvailableFunds/BuyingPower no los sustituyen.')
    lines+=['','Permisos de acciones/ETF, plan Tiered aplicable, residencia/entidad, capacidad intradía, fracciones/API y restricciones efectivas de cuenta: **UNKNOWN**. Resolver contrato o recibir datos no confirma permiso de negociación. El modelo usa efectivo liquidado conservadoramente; no presupone préstamo o reutilización inmediata aun si STKNOPT corresponde a margen.',
        'No se usó what-if: requiere placeOrder. Las capacidades stop/limit declaradas no prueban un bracket, OCA o protección efectiva en esta cuenta.',
        '', '## Protocolo congelado y candidatos','',
        'Universo de conveniencia congelado: SCHX (ETF amplio), SPY (ETF de control de accesibilidad) y F (acción). Liquidez histórica completa y universo sin supervivencia no demostrados.',
        'LONG exclusivamente. Señal con vela completa; entrada siguiente apertura. EMA 10/20, SMA 50 de contexto, ATR 14. Stop antes de target si ambos se alcanzan; gap adverso al precio de apertura, sin limitar artificialmente pérdidas. Salida por EMA/contexto contrario en apertura siguiente (excepto reversión a la media) o máximo 20 velas. Tick de investigación US$0.01: BUY redondeado arriba, SELL/stop/target abajo; reserva adicional de dos ticks en riesgo y filtro de target.',
        '| Candidato | Señal | Stop / target | Versión experimental |','|---|---|---|---|']
    rules=[('EQ_TREND_R0','Cruce EMA10 sobre EMA20 y cierre sobre SMA50','1.5 ATR / 3 ATR'),
        ('EQ_PULLBACK_R0','Contexto alcista; retroceso EMA20 y recuperación confirmada','1 ATR / 2 ATR'),
        ('EQ_BREAKOUT_R0','Cierre sobre máximo previo de 20 velas; volumen ≥1.5× media previa','1.5 ATR / 3 ATR'),
        ('EQ_MEAN_REVERSION_R0','Rebote desde banda −2σ previa; SMA50 relativamente plana','1 ATR / media20 congelada')]
    for name,rule,exits in rules:lines.append(f"| {name} | {rule} | {exits} | `{report['versions'][name]}` |")
    lines+=['','Se conserva 1 posición entre símbolos. T+1 según siguiente sesión IBKR auténtica: una ganancia habilita buscar señal, pero no vuelve líquidos sus ingresos inmediatamente. Una pérdida o break-even detiene entradas en America/Santo_Domingo. Datos/saldo ausentes no se convierten en cero.',
        'Costo Tiered simulado: min(max(0.0035×acciones, 0.35), 1% notional) por lado, más envolvente conservadora de terceros US$0.02 + US$0.01/acción por lado. No representa la tarifa verificada de esta cuenta.',
        'Spread: máximo de 5 bps y una observación IBKR; slippage 5 bps por lado; gap presupuestado 50 bps. Stress: doble spread, slippage 15 bps por lado, gap 100 bps. Fixed: mínimo público US$1 sujeto al techo 1%, mismos costos adicionales conservadores.',
        '', '## Comparación fuera de muestra — Tiered base','',
        '| Estrategia | TF | Riesgo % | Admitidas / rechazadas | Win % / Wilson95 | P&L neto | EV | PF | DD % | Comisiones | Días primer loss |',
        '|---|---|---:|---:|---|---:|---:|---:|---:|---:|---:|']
    def fmt(v):return 'N/D' if v is None else f'{v:.4f}'
    for row in report['rows']:
        if row['cost_model']!='TIERED_BASE':continue
        result=row['results']['validation'];m=result['metrics'];ci=result['confidence']['win_wilson_95']
        conf='N/D' if ci is None else f'[{100*ci[0]:.1f}, {100*ci[1]:.1f}]'
        lines.append(f"| {row['strategy']} | {row['minutes']}m | {row['risk_percent']} | {m['admitted']} / {m['rejected']} | {fmt(None if m['win_rate'] is None else 100*m['win_rate'])} / {conf} | {fmt(m['net_pnl'])} | {fmt(m['net_expectancy'])} | {fmt(m['profit_factor'])} | {fmt(100*m['maximum_drawdown'])} | {fmt(m['commissions'])} | {m['first_loss_days']} |")
    lines+=['','## Robustez y walk-forward','',
        'Tres folds cronológicos de validación; sin ajustar parámetros. Warm-up causal del pasado, señales purgadas en frontera. Asignaciones independientes, no sumar sus ganancias como un único portfolio. Todos los costos, riesgos, métricas, rechazos, operaciones, intervalos ajustados y resultados continuos/desarrollo/validación/folds están en `artifacts/research/us-equities/report.json`.',
        '| Candidato / TF | Costo | Mejor P&L validación descriptivo (entre riesgos; no selección) | Fold 1 / 2 / 3 neto | N validación |',
        '|---|---|---:|---|---:|']
    for family in FAMILIES:
        for tf in TIMEFRAMES:
            for model in MODELS:
                choices=[r for r in report['rows'] if (r['strategy'],r['minutes'],r['cost_model'])==(family,tf,model)]
                if not choices:continue
                best=max(choices,key=lambda r:r['results']['validation']['metrics']['net_pnl'])
                vals=[best['results'][f'walk_forward_{i}']['metrics']['net_pnl'] for i in range(1,4)]
                lines.append(f"| {family} / {tf}m | {model} | {fmt(best['results']['validation']['metrics']['net_pnl'])} | {' / '.join(fmt(v) for v in vals)} | {best['results']['validation']['metrics']['admitted']} |")
    lines+=['','## Bloqueos y próxima fase','',
        'No existe candidato seleccionado ni tamaño autorizado. Los parámetros son nuevos R0 de investigación, nunca versiones Forex V1 ni estrategias PaperEligible.',
        'Pendiente: confirmar plan/comisiones reales, permisos/entidad/régimen intradía, settled USD, mínimos/fracciones y soporte de protección por contrato. Datos tardíos/frozen no habilitan ejecución.',
        'Adapter productivo pendiente (sin implementar): contratos STK/SMART/conId, ticks/reglas de precio, sesiones y acciones corporativas, MarketData real time, inventario/settled cash por divisa y T+1, guard de intradía, bracket/OCA y close-only por posición, fills parciales/comisiones y reconciliación bursátil. El adapter actual admite exclusivamente EUR/USD CASH IDEALPRO; no basta con cambiar un símbolo.',
        'Próxima fase: universo point-in-time con bajas y acciones corporativas, históricos BID/ASK/liquidez, más muestra OOS nueva y auditoría solo lectura de permisos/tarifas. No optimizar para alcanzar 80%; repetir protocolo congelado. Riesgo de ruina no estimable con esta muestra; stops no garantizan pérdida máxima frente a gaps.',
        '', '## Fuentes primarias consultadas','',
        '- [Tarifas de acciones y cargos de terceros IBKR](https://www.interactivebrokers.com/en/pricing/commissions-stocks.php). Tarifas públicas; plan de cuenta desconocido. No se asume Lite.',
        '- [Paper: permisos/datos heredados y limitaciones de simulación](https://www.ibkrguides.com/advisorportal/aboutpapertradingaccount.htm).',
        '- [Liquidación T+1 y fondos en la divisa necesaria](https://www.interactivebrokers.com/campus/traders-insight/t1-settlement-what-it-means-for-traders-and-investors/). El modelo no presupone acceso a facilidades de crédito ni reutilización instantánea.',
        '- [Margen de acciones y transición del régimen intradía](https://www.interactivebrokers.com/en/trading/margin-stocks.php). La transición hasta octubre 2027 impide aplicar indiscriminadamente una regla PDT única; verificar la cuenta.',
        '- [API oficial: cuenta, históricos, contratos y órdenes](https://www.interactivebrokers.com/docs/tws-api/doc/introduction).',
        '- [Códigos IBKR 2188/162/366](https://www.interactivebrokers.com/docs/tws-api/doc/error-handling/error-codes).',
        '- [Restricciones intradía en transición](https://www.ibkrguides.com/ibkrdesktop/available-for-trading.htm). No inferir un número de day trades permitidos cuando el campo está ausente.',
        '- [Código STKNOPT y nomenclatura Reg T de IBKR](https://www.interactivebrokers.com/campus/trading-lessons/risk-navigator-alternative-margin-calculator/). Interpretación del código observado, no prueba de permisos de ejecución.',
        '', '## Limitaciones explícitas','']
    lines.extend('- '+x for x in report['caveats'])
    if report['incomplete_data']:lines.extend('- '+x for x in report['incomplete_data'])
    verification=Path(root)/'artifacts/test-results/us-equities/verification.json'
    if verification.exists():
        v=json.loads(verification.read_text());lines+=['','## Verificación ejecutada','',
            f"{v['python_passed']} Python + {v['csharp_passed']} C# = **{v['total_passed']} aprobadas**, fallos {v['failed']}, omitidas {v['skipped']}. Compilación .NET: {v['build_errors']} errores, {v['build_warnings']} advertencias.",
            'Controles protegidos comparados por SHA256; DB de regresiones detenida. No se modificó el ejecutor, Forex V1, AccountBinding, EmergencyStop ni autorizaciones. Live bloqueado.']
    (Path(root)/'docs/architecture/us-equity-strategy-research.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',default='.')
    result=run(parser.parse_args().root)
    print(json.dumps({'status':result['status'],'configurations':result['configurations'],'scenario_results':result['scenario_results']}))
