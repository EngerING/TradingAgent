"""Preregistered R20 research domain. Pure Decimal calculations; no broker capability."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_FLOOR
import hashlib
import json
from pathlib import Path

PROFILE = 'AGGRESSIVE_GROWTH_R20'
STRATEGY = 'AGGRESSIVE_TREND_BREAKOUT_V1'
CLASSIFICATION = 'SHADOW_SIMULATED'
CONFIG = 'config/aggressive-growth-r20.json'


def number(value):
    if isinstance(value, bool): raise ValueError('INVALID_DECIMAL')
    n = Decimal(str(value))
    if not n.is_finite(): raise ValueError('NONFINITE_DECIMAL')
    return n


N = number


def instant(value):
    d = value if isinstance(value, datetime) else datetime.fromisoformat(value.replace('Z', '+00:00'))
    if d.tzinfo is None: raise ValueError('UTC_TIMESTAMP_REQUIRED')
    return d.astimezone(timezone.utc)


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def sha(value): return hashlib.sha256(encoded(value)).hexdigest()


def configuration(root):
    c = json.loads((Path(root)/CONFIG).read_bytes())
    fixed = dict(initial_capital_usd='100', price_risk_fraction='.20', max_leverage='10', baseline_leverage='1',
                 stop_atr='1.5', reward_risk='2', opening_fee_usd='2', closing_fee_usd='2',
                 spread_floor_usd_per_eur='.0014', slippage_per_side_usd_per_eur='.00045', financing_reserve_usd='.25',
                 initial_margin_fraction='.10', maintenance_margin_fraction='.05', minimum_quantity='.01', quantity_increment='.01', openai_budget_usd='0')
    if any(N(c[k]) != N(v) for k, v in fixed.items()): raise ValueError('PREREGISTERED_R20_PARAMETERS_REQUIRED')
    if c['profile'] != PROFILE or c['strategy'] != STRATEGY or c['symbol'] != 'EUR/USD' or c['timeframes'] != [60,240]:
        raise ValueError('PREREGISTERED_R20_SCOPE_REQUIRED')
    if any(c[k] != v for k,v in dict(ema_fast=20,ema_slow=50,breakout_bars=20,atr_period=14,max_positions=1,quote_max_age_seconds=30,signal_max_age_seconds=180,poll_seconds=15).items()):
        raise ValueError('PREREGISTERED_R20_RULES_REQUIRED')
    if c['live_enabled'] is not False or c['broker_orders_enabled'] is not False: raise PermissionError('R20_SHADOW_ONLY')
    return c


def ema(values, period):
    value = sum(values[:period])/period
    alpha = N(2)/N(period+1)
    for price in values[period:]: value += alpha*(price-value)
    return value


def closed_bars(rows, minutes, as_of):
    cutoff = instant(as_of); out = []; previous = None
    for b in rows:
        opened = instant(b['opened_at'])
        if opened+timedelta(minutes=minutes)>cutoff: continue
        if b.get('minutes', minutes) != minutes: raise ValueError('BAR_TIMEFRAME_MISMATCH')
        if previous is not None and opened <= previous: raise ValueError('DUPLICATE_OR_UNORDERED_BARS')
        if opened.timestamp() % (minutes*60): raise ValueError('PARTIAL_OR_UNALIGNED_BAR')
        prices = {k:N(b[k]) for k in ('open','high','low','close')}
        if min(prices.values())<=0 or prices['high']<max(prices.values()) or prices['low']>min(prices.values()): raise ValueError('INVALID_OHLC')
        out.append(dict(prices, opened_at=opened)); previous=opened
    return out


def signal(c, rows, minutes, as_of):
    result = dict(strategy=STRATEGY, timeframe=minutes, side=None, at=None, reason=None)
    try:
        if minutes not in c['timeframes']: raise ValueError('UNSUPPORTED_TIMEFRAME')
        bs = closed_bars(rows, minutes, as_of)
        if bs: result['at']=(bs[-1]['opened_at']+timedelta(minutes=minutes)).isoformat()
        if len(bs)<c['ema_slow']: result['reason']='INSUFFICIENT_CLOSED_BARS'; return result
        closes=[b['close'] for b in bs]; fast=ema(closes,c['ema_fast']); slow=ema(closes,c['ema_slow'])
        trs=[]
        for i,b in enumerate(bs):
            prev=bs[i-1]['close'] if i else b['open']
            trs.append(max(b['high']-b['low'], abs(b['high']-prev), abs(b['low']-prev)))
        atr=sum(trs[:c['atr_period']])/c['atr_period']
        for tr in trs[c['atr_period']:]: atr=(atr*(c['atr_period']-1)+tr)/c['atr_period']
        window=bs[-c['breakout_bars']-1:-1]; upper=max(b['high'] for b in window); lower=min(b['low'] for b in window)
        side='LONG' if fast>slow and closes[-1]>upper else 'SHORT' if fast<slow and closes[-1]<lower else None
        if atr<=0: result['reason']='ATR_UNAVAILABLE'; return result
        distance=atr*N(c['stop_atr'])
        result.update(side=side, reason=None if side else 'NO_BREAKOUT', ema20=str(fast), ema50=str(slow), atr14=str(atr),
                      prior_high=str(upper), prior_low=str(lower), close=str(closes[-1]), stop_distance=str(distance), target_distance=str(distance*N(c['reward_risk'])))
    except (KeyError,ValueError,TypeError,AttributeError,ArithmeticError): result.update(side=None,reason='INVALID_MARKET_DATA')
    return result


def assess(c, quote, signal, equity, leverage=None, conditions=None):
    d=dict(admitted=False, reason=None, quantity='0', research_eligible=False, economically_viable=None,
           statistically_validated=False, paper_execution_eligible=False, warnings=[], classification=CLASSIFICATION)
    try:
        equity=N(equity); cap=N(leverage if leverage is not None else c['max_leverage']); cond=conditions or {}
        if equity<=0: d['reason']='EQUITY_EXHAUSTED'; return d
        if cond.get('margin_allowed') is False: d['reason']='MARGIN_REJECTION'; return d
        if not 0<cap<=N(c['max_leverage']): raise ValueError('LEVERAGE_OUTSIDE_PROTOCOL')
        bid,ask=N(quote['bid']),N(quote['ask']); mid=(bid+ask)/2
        stop_distance,target_distance=N(signal['stop_distance']),N(signal['target_distance']); side=signal['side']
        if min(bid,stop_distance,target_distance)<=0 or ask<bid or stop_distance>=mid or side not in ('LONG','SHORT'): raise ValueError('INVALID_GEOMETRY')
        if side=='SHORT' and target_distance>=mid: raise ValueError('NONPOSITIVE_SHORT_TARGET')
        step=max(N(c['quantity_increment']),N(cond.get('quantity_increment',c['quantity_increment'])))
        minimum=max(N(c['minimum_quantity']),N(cond.get('minimum_quantity',c['minimum_quantity'])))
        initial_margin=max(N(c['initial_margin_fraction']),1/cap,N(cond.get('initial_margin_fraction',c['initial_margin_fraction'])))
        if min(step,minimum,initial_margin)<=0: raise ValueError('INVALID_RESTRICTION')
        fees=N(c['opening_fee_usd'])+N(c['closing_fee_usd']); financing=N(c['financing_reserve_usd'])
        spread=max(ask-bid,N(c['spread_floor_usd_per_eur'])); slip=2*N(c['slippage_per_side_usd_per_eur']); fixed=fees+financing
        budget=equity*N(c['price_risk_fraction'])
        maximum=min(budget/stop_distance,equity*cap/mid,(equity-fixed)/(mid*initial_margin+spread+slip))
        quantity=max(N(0),(maximum/step).to_integral_value(rounding=ROUND_FLOOR)*step)
        if quantity<minimum: d['reason']='CAPITAL_MARGIN_OR_MINIMUM_QUANTITY'; return d
        notional=quantity*mid; risk=quantity*stop_distance; costs=fixed+quantity*(spread+slip); direction=1 if side=='LONG' else -1
        d.update(admitted=True,research_eligible=True,quantity=str(quantity),entry=str(mid),side=side,stop=str(mid-direction*stop_distance),target=str(mid+direction*target_distance),
                 notional=str(notional),price_risk_budget=str(budget),price_risk=str(risk),fees=str(fees),spread_cost=str(quantity*spread),
                 slippage_cost=str(quantity*slip),financing_cost=str(financing),estimated_costs=str(costs),anticipated_total_loss=str(risk+costs),
                 margin=str(notional*initial_margin),maintenance_margin=str(notional*N(c['maintenance_margin_fraction'])),initial_margin_fraction=str(initial_margin),
                 leverage=str(notional/equity),gross_target=str(quantity*target_distance),net_target=str(quantity*target_distance-costs),
                 stop_distance=str(stop_distance),target_distance=str(target_distance),cost_status=c['cost_status'],margin_status=c['margin_status'],quantity_status=c['quantity_status'],
                 liquidation_risk='POSSIBLE_GAPS_AND_EQUITY_DECLINE_NO_GUARANTEED_MAXIMUM',economically_viable=quantity*target_distance>costs)
        if not d['economically_viable']: d['warnings'].append('TARGET_DOES_NOT_COVER_MODELED_COSTS_EXPLORATORY_ALLOWED')
        d['warnings'].extend(['EXPECTANCY_UNKNOWN','COSTS_AND_MARGIN_MODELED_NOT_EFFECTIVE_BROKER_PERMISSION','STOP_IS_NOT_GUARANTEED_MAXIMUM_LOSS'])
    except (KeyError,ValueError,TypeError,ArithmeticError): d.update(admitted=False,research_eligible=False,reason='INVALID_COST_SIZE_OR_GEOMETRY')
    return d


def portfolio():
    return dict(initial_capital='100',cash_equity='100',equity='100',realized_gross='0',realized_net='0',fees='0',spread_cost='0',slippage_cost='0',
                financing_cost='0',consumed_loss='0',peak_equity='100',maximum_drawdown='0',current_drawdown='0',active=None,trades=[],equity_curve=[])


def paper_plan(assessment=None, capabilities=None):
    return dict(profile=PROFILE,strategy=STRATEGY,state='BLOCKED',classification='IBKR_PAPER',execution_authorized=False,broker_orders_enabled=False,live_enabled=False,
                single_use=True,max_openings=1,max_minutes=30,authorization_granted=False,previous_r10_authorizations_reusable=False,emergency_stop_untouched=True,
                assessment=assessment,observed_capabilities=capabilities or {},consent=None,
                consent_binding_fields=['experiment','strategy_version','account_binding','paper_environment','contract_id','side','quantity','stop','target','fees','incremental_margin','evidence_hash','expires_at','nonce'],
                conditions=['EXACT_PAPER_ACCOUNT_BINDING','FRESH_FLAT_RECONCILIATION','EFFECTIVE_FOREX_PERMISSION','MINIMUM_AND_INCREMENT','INCREMENTAL_MARGIN','OPEN_CLOSE_FEES','BRACKET_ACK_PROTECTION','PARTIAL_FILL_RECONCILIATION','DISCONNECT_RECOVERY','RESTART_IDEMPOTENCY','OWNED_REDUCE_ONLY_RECOVERY'],
                blockers=['NO_EXECUTION_ADAPTER_IN_R20','NEW_SPECIFIC_SINGLE_USE_CONSENT_REQUIRED','EFFECTIVE_BROKER_CONDITIONS_UNVERIFIED','PROTECTION_AND_RECOVERY_REQUIRE_SUPERVISED_VERIFICATION'])


def initial_state(c, engine_hash, at, run_kind='FORWARD'):
    if run_kind not in ('FORWARD','HISTORICAL'): raise ValueError('RUN_KIND_REQUIRED')
    return dict(protocol=deepcopy(c),engine_hash=engine_hash,strategy_version=sha({'strategy':STRATEGY,'parameters':c}),status='PREPARED_SHADOW',run_kind=run_kind,
                started_at=at,updated_at=at,portfolios={'R20':portfolio(),'BASELINE_1X':portfolio()},seen=[],signals=[],events=[],last_quote=None,last_assessment=None,
                latest_kronos=None,paper=paper_plan(),last_no_trade=None,stop_requested=False,opportunities=0)


def quote_valid(q, at, c, historical=False):
    try:
        return (q.get('type')==('HISTORICAL_MODELED' if historical else 'LIVE') and q.get('market_status')=='OPEN'
                and q.get('available_for_execution') is True and 0<=(instant(at)-instant(q['at'])).total_seconds()<=c['quote_max_age_seconds']
                and N(q['ask'])>=N(q['bid'])>0)
    except (KeyError,ValueError,TypeError,ArithmeticError): return False


def kronos_evidence(value, at):
    k=deepcopy(value or {}); source=k.get('latest') or k; timestamp=source.get('candle_timestamp')
    created=source.get('created_at');end=source.get('prediction_end')
    try:
        fresh=(timestamp is not None and created is not None and end is not None and instant(created)<=instant(at)<instant(end)
               and 0<=(instant(at)-instant(timestamp)).total_seconds()<=min(3900,int(source.get('max_prediction_age_seconds') or 3900)))
    except (ValueError,TypeError,AttributeError): fresh=False
    # Metadata belongs to the same forecast as its timestamps; never infer from the R20 signal.
    source_timeframe=source.get('timeframe'); horizon=source.get('pred_len')
    timeframe={'1H':60,'4H':240}.get(source_timeframe) if isinstance(source_timeframe,str) else None
    compatible=False
    try:
        compatible=(timeframe is not None and type(horizon) is int and 1<=horizon<=128
                    and source.get('partition')=='FORWARD'
                    and instant(source['prediction_start'])==instant(timestamp)
                    and instant(end)-instant(source['prediction_start'])==timedelta(minutes=timeframe*horizon))
    except (KeyError,ValueError,TypeError,AttributeError): pass
    return dict(status=k.get('status','KRONOS_UNAVAILABLE'),prediction_id=source.get('prediction_id'),candle_timestamp=timestamp,
                created_at=created,prediction_end=end,as_of=instant(at).isoformat(),
                source_timeframe=source_timeframe,timeframe=timeframe,horizon_bars=horizon if type(horizon) is int and 1<=horizon<=128 else None,
                prediction_start=source.get('prediction_start'),partition=source.get('partition'),temporal_compatible=compatible,
                fresh=fresh,calibration_state='RAW_ONLY',calibrated_probability=None,direction=source.get('direction') or source.get('consensus',{}).get('kronos_direction'),
                support='UNAVAILABLE_OR_STALE' if not fresh else 'RAW_OBSERVATION_ONLY',execution_authority=False)


def mark(p, midpoint, at):
    t=p['active']; net=N(0)
    if t:
        direction=1 if t['side']=='LONG' else -1
        gross=N(t['quantity'])*(midpoint-N(t['entry']))*direction
        net=gross-N(t['assessment']['estimated_costs'])
        equity=N(p['cash_equity'])+net; notional=N(t['quantity'])*midpoint
        t.update(unrealized_gross_pnl=str(gross),unrealized_net_pnl=str(net),current_notional=str(notional),
                 effective_leverage=str(notional/equity) if equity>0 else None,
                 liquidation_risk=equity<=0 or notional>equity*N(t['leverage_limit']) or equity<notional*N(t['maintenance_margin_fraction']))
    else: equity=N(p['cash_equity'])
    p['equity']=str(equity);p['peak_equity']=str(max(N(p['peak_equity']),equity));p['current_drawdown']=str(N(p['peak_equity'])-equity)
    p['maximum_drawdown']=str(max(N(p['maximum_drawdown']),N(p['current_drawdown'])))


def close(p, price, quote, at, reason, c):
    t=p['active'];d=t['assessment'];qty=N(t['quantity']);direction=1 if t['side']=='LONG' else -1
    gross=qty*(price-N(t['entry']))*direction
    spread=qty*max(N(c['spread_floor_usd_per_eur']),(N(t['quote']['ask'])-N(t['quote']['bid'])+N(quote['ask'])-N(quote['bid']))/2)
    fees=N(d['fees']);slip=N(d['slippage_cost']);financing=N(d['financing_cost']);net=gross-fees-spread-slip-financing
    t.update(exit=str(price),closed_at=at,exit_reason=reason,gross_pnl=str(gross),net_pnl=str(net),fees=str(fees),spread_cost=str(spread),slippage_cost=str(slip),financing_cost=str(financing),
             realized_loss=str(max(N(0),-net)),price_loss=str(max(N(0),-gross)),loss_exceeded_price_risk=-net>N(t['price_risk']),cost_status=c['cost_status'])
    for key,value in [('realized_gross',gross),('realized_net',net),('fees',fees),('spread_cost',spread),('slippage_cost',slip),('financing_cost',financing),('consumed_loss',max(N(0),-net))]: p[key]=str(N(p[key])+value)
    p['cash_equity']=str(N(p['cash_equity'])+net);p['trades'].append(t);p['active']=None;mark(p,price,at)
    p['equity_curve'].append(dict(at=at,equity=p['equity'],drawdown=p['current_drawdown'],trade_id=t['id']))
    return t


def exit_check(t, rows, q, at, c, stop=False):
    direction=1 if t['side']=='LONG' else -1;barrier=N(t['stop']);target=N(t['target'])
    for b in closed_bars(rows,t['timeframe'],at):
        if b['opened_at']<instant(t['at']): continue
        if direction==1:
            if b['low']<=barrier:return min(b['open'],barrier),'STOP_OR_GAP'
            if b['high']>=target:return target,'TARGET'
        else:
            if b['high']>=barrier:return max(b['open'],barrier),'STOP_OR_GAP'
            if b['low']<=target:return target,'TARGET'
    midpoint=(N(q['bid'])+N(q['ask']))/2
    if stop:return midpoint,'OPERATOR_STOP'
    if t.get('liquidation_risk'):return midpoint,'MODELED_LIQUIDATION_RISK'
    if (midpoint-barrier)*direction<=0:return midpoint,'OBSERVED_STOP_OR_GAP'
    if (midpoint-target)*direction>=0:return midpoint,'OBSERVED_TARGET'
    return None,None


def consume(s, observation, at, kronos=None, stop=False):
    """Mutate a private candidate state; caller durably commits before accepting it."""
    if s['status']=='STOPPED': return []
    if instant(at)<max(instant(s['started_at']),instant(s['updated_at'])): raise ValueError('OBSERVATION_TIME_CANNOT_REWIND')
    c=s['protocol'];time=instant(at);q=deepcopy(observation['quote']);s['last_quote']=q;s['updated_at']=time.isoformat();s['latest_kronos']=kronos_evidence(kronos,time)
    s['stop_requested']=s.get('stop_requested',False) or stop;emitted=[]
    def event(kind,detail): emitted.append(dict(kind=kind,at=time.isoformat(),detail=detail,classification=CLASSIFICATION))
    def reject(reason,**details):
        s['last_no_trade']=dict(reason=reason,at=time.isoformat(),**details);event('NO_TRADE',s['last_no_trade'])
    if not quote_valid(q,time,c,s['run_kind']=='HISTORICAL'):
        s['status']='STOPPING_MANAGING_SHADOW' if s['stop_requested'] and any(p['active'] for p in s['portfolios'].values()) else 'DATA_UNAVAILABLE'
        reject('QUOTE_STALE_MISSING_OR_CLOSED');return emitted
    analysis=observation.get('analysis') or {};rows=analysis.get('normalized') or {};mid=(N(q['bid'])+N(q['ask']))/2
    for name,p in s['portfolios'].items():
        mark(p,mid,time.isoformat())
        if p['active']:
            try:price,reason=exit_check(p['active'],rows.get(str(p['active']['timeframe']),[]),q,time,c,s['stop_requested'])
            except (KeyError,ValueError,TypeError,AttributeError,ArithmeticError):
                reject('INVALID_EXIT_BARS',portfolio=name)
                # Invalid bars cannot imply a historical fill. A fresh observed quote may still manage inventory.
                price,reason=exit_check(p['active'],[],q,time,c,s['stop_requested'])
            if price is not None:event('SHADOW_CLOSE',dict(portfolio=name,trade=close(p,price,q,time.isoformat(),reason,c)))
    if s['stop_requested']:
        s['status']='STOPPING_MANAGING_SHADOW' if any(p['active'] for p in s['portfolios'].values()) else 'STOPPED'
        event('SHADOW_STOPPED',dict(inventory_retained=any(p['active'] for p in s['portfolios'].values())));return emitted
    s['status']='SHADOW_RUNNING' if N(s['portfolios']['R20']['equity'])>0 else 'HALTED_EQUITY'
    opportunities=[]
    for minutes in c['timeframes']:
        series=rows.get(str(minutes),[])
        try:
            closed_bars(series,minutes,time)
            cutoffs=[instant(b['opened_at'])+timedelta(minutes=minutes) for b in series
                     if instant(s['started_at'])-timedelta(seconds=c['signal_max_age_seconds'])<=instant(b['opened_at'])+timedelta(minutes=minutes)<=time]
        except (KeyError,ValueError,TypeError,AttributeError,ArithmeticError):
            reject('INVALID_MARKET_DATA',timeframe=minutes);continue
        # Before the next close, still explain the most recent candle as stale/no trade.
        if not cutoffs:
            latest=signal(c,series,minutes,time)
            if latest['at'] is None:reject(latest['reason'],timeframe=minutes);continue
            cutoffs=[instant(latest['at'])]
        for cutoff in cutoffs:
            identity=sha([STRATEGY,minutes,cutoff.isoformat()])
            if identity in s['seen']:continue
            sig=signal(c,series,minutes,cutoff)
            opportunities.append((cutoff,minutes,identity,sig))
    for closed,minutes,identity,sig in sorted(opportunities):
        s['seen'].append(identity);s['opportunities']+=1
        record=dict(id=identity,at=sig['at'],observed_at=time.isoformat(),strategy=STRATEGY,timeframe=minutes,side=sig['side'],signal=sig,decisions={},quote=deepcopy(q),source=observation.get('history_source'),kronos=s['latest_kronos'])
        reason=sig['reason']
        try:
            missing=analysis['quality'][str(minutes)]['missing_expected_openings']
            if not isinstance(missing,list): raise ValueError('QUALITY_LIST_REQUIRED')
            missing=[instant(t) for t in missing]
            # EMA and Wilder ATR depend on the entire supplied prefix, not just its last 50 bars.
            first=instant(rows[str(minutes)][0]['opened_at'])
            if any(first<=t<closed for t in missing):reason='MISSING_EXPECTED_BARS'
        except (KeyError,ValueError,TypeError,AttributeError,IndexError):reason='BAR_QUALITY_UNAVAILABLE'
        if not reason and (time-closed).total_seconds()>c['signal_max_age_seconds']:reason='SIGNAL_STALE'
        if not reason and instant(q['at'])<=closed:reason='QUOTE_NOT_AFTER_SIGNAL_CLOSE'
        for name,p in s['portfolios'].items():
            why=reason or ('POSITION_OCCUPIED' if p['active'] else None)
            if why:d=dict(admitted=False,reason=why,classification=CLASSIFICATION)
            else:
                conditions={};minimum=observation.get('capabilities',{}).get('minimum',{})
                if isinstance(minimum,dict):
                    if minimum.get('quantity') or minimum.get('value'):conditions['minimum_quantity']=minimum.get('quantity') or minimum.get('value')
                    if minimum.get('increment'):conditions['quantity_increment']=minimum['increment']
                d=assess(c,q,sig,p['equity'],c['max_leverage'] if name=='R20' else c['baseline_leverage'],conditions)
            record['decisions'][name]=d
            if name=='R20':s['last_assessment']=d
            if not d['admitted']:reject(d['reason'],signal_id=identity,portfolio=name);continue
            p['active']=dict(id=sha([identity,name]),signal_id=identity,classification=CLASSIFICATION,run_kind=s['run_kind'],strategy=STRATEGY,timeframe=minutes,side=sig['side'],
                             quantity=d['quantity'],entry=d['entry'],entry_equity=p['equity'],stop=d['stop'],target=d['target'],notional=d['notional'],price_risk=d['price_risk'],margin=d['margin'],
                             at=time.isoformat(),signal_at=sig['at'],assessment=deepcopy(d),source=observation.get('history_source'),quote=deepcopy(q),kronos=s['latest_kronos'],
                             leverage_limit=c['max_leverage'] if name=='R20' else c['baseline_leverage'],maintenance_margin_fraction=c['maintenance_margin_fraction'],protection='VIRTUAL_BRACKET_ONLY')
            mark(p,mid,time.isoformat());event('SHADOW_OPEN',dict(portfolio=name,position=deepcopy(p['active'])))
        s['signals'].append(record);event('CANDLE_EVALUATED',record)
    s['paper']=paper_plan(s['last_assessment'],observation.get('capabilities'))
    return emitted
