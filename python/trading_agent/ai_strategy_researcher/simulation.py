"""Pure deterministic LONG simulator, independent of broker/production risk code."""
from bisect import bisect_right
from collections import Counter,defaultdict
from decimal import Decimal,ROUND_FLOOR,ROUND_CEILING
import math
import random
from statistics import mean,pstdev,NormalDist
from zoneinfo import ZoneInfo
from .contracts import at,number,digest,MODELS,FOLDS,candidate_version
from .costs import commission,commission_details,fee_evidence,COST_VERSION,cost_assumptions

D=Decimal
ZONE=ZoneInfo('America/Santo_Domingo')
NY=ZoneInfo('America/New_York')


def tick(value,buy=False):
    return (number(value)/D('.01')).to_integral_value(rounding=ROUND_CEILING if buy else ROUND_FLOOR)*D('.01')


class Ledger:
    def __init__(self):
        self.equity=D(100);self.cash=D(100);self.losses=D(0);self.pending=None
        self.stops={};self.unsettled=[]

    def day(self,stamp):return at(stamp).astimezone(ZONE).date().isoformat()

    def gate(self,stamp):
        if self.pending:return 'PREVIOUS_RESULT_NOT_DEFINITIVE'
        if self.losses>=20 or self.equity<=0:return 'CUMULATIVE_LOSS_STOP'
        return self.stops.get(self.day(stamp))

    def available(self,stamp):
        day=at(stamp).astimezone(NY).date().isoformat();remaining=[]
        for t,amount in self.unsettled:
            if t is not None and t<=day:self.cash+=amount
            else:remaining.append((t,amount))
        self.unsettled=remaining;return self.cash

    def begin(self,spent):
        spent=number(spent)
        if self.pending or spent<0 or spent>self.cash:raise ValueError('ONE_POSITION_AND_FUNDS_REQUIRED')
        self.cash-=spent;self.pending={'spent':str(spent)}

    def finish(self,net,proceeds,stamp,settles,definitive=True):
        if not self.pending:raise ValueError('OWNED_SIMULATED_POSITION_REQUIRED')
        if not definitive:return False
        net,proceeds=number(net),number(proceeds)
        self.equity+=net;self.losses+=max(D(0),-net);self.unsettled.append((settles,proceeds))
        if net<=0:self.stops[self.day(stamp)]='DAILY_FIRST_LOSS_STOP' if net<0 else 'DAILY_BREAK_EVEN_STOP'
        self.pending=None;return True


def validated(rows):
    if not 1<=len(rows)<=20000:raise ValueError('SIMULATION_BAR_LIMIT')
    previous=None;out=[]
    for b in rows:
        opened,closed=at(b['opened_at']),at(b['closed_at'])
        o,h,l,c=[number(b[k]) for k in ('open','high','low','close')];v=number(b['volume'])
        if not opened<closed or (previous and opened<previous) or min(o,h,l,c)<=0 or h<max(o,l,c) or l>min(o,h,c) or v<0:
            raise ValueError('INVALID_CAUSAL_BARS')
        previous=closed;out.append({**b,**dict(zip(('open','high','low','close','volume'),map(float,(o,h,l,c,v))))})
    return out


def signals(rows,c):
    fs=[];events=[];closes=[];trs=[];fast=None;slow=None
    ready=max(c['slow'],c['lookback'],c['atr_period'])+5
    for i,b in enumerate(rows):
        price=b['close'];closes.append(price)
        tr=max(b['high']-b['low'],abs(b['high']-rows[i-1]['close']),abs(b['low']-rows[i-1]['close'])) if i else b['high']-b['low']
        trs.append(tr);fast=price if fast is None else fast+2/(c['fast']+1)*(price-fast)
        slow=price if slow is None else slow+2/(c['slow']+1)*(price-slow)
        window=closes[-c['lookback']:]
        f=dict(fast=fast,slow=slow,center=mean(window),sigma=pstdev(window),atr=mean(trs[-c['atr_period']:]))
        fs.append(f)
        if i<ready or i==len(rows)-1 or f['atr']<=0:continue
        prev=fs[i-1];prior=rows[i-1];pattern=c['pattern'];valid=False
        if pattern=='TREND_CROSS':valid=prev['fast']<=prev['slow'] and fast>slow and price>f['center']
        elif pattern=='PULLBACK':valid=fast>slow and prior['low']<=prev['slow'] and price>slow and price>prior['close']
        elif pattern=='BREAKOUT':
            window_bars=rows[i-c['lookback']:i]
            valid=price>max(x['high'] for x in window_bars) and b['volume']>=1.5*mean(x['volume'] for x in window_bars) and fast>slow
        elif pattern=='MEAN_REVERSION':valid=prior['close']<prev['center']-2*prev['sigma'] and price>prior['close']
        else:raise ValueError('DECLARATIVE_PATTERN_REQUIRED')
        distance=float(number(c['stop_atr']))*f['atr'];stop=float(tick(price-distance));target=float(tick(price+float(number(c['target_r']))*distance))
        if valid and 0<stop<price<target:
            events.append(dict(index=i+1,signal_at=b['closed_at'],stop=stop,target=target,indicators=f))
    return events,fs


def exit_event(rows,fs,s,c):
    i=s['index']
    for j in range(i,min(len(rows),i+c['max_hold_bars'])):
        r=rows[j]
        invalid=j>i and c['pattern']!='MEAN_REVERSION' and fs[j-1]['fast']<fs[j-1]['slow']
        if j>i and (j-i>=c['max_hold_bars']-1 or invalid):return j,r['open'],'RULE_NEXT_OPEN',r['opened_at']
        if r['open']<=s['stop']:return j,r['open'],'STOP_GAP',r['opened_at']
        if r['low']<=s['stop']:return j,s['stop'],'STOP_FIRST_IF_AMBIGUOUS',r['closed_at']
        if r['high']>=s['target']:return j,s['target'],'TARGET_CONSERVATIVE',r['closed_at']
    return None


def size(entry,stop,target,rate,ledger,model,observed_spread=None):
    p,stop,target=number(entry),number(stop),number(target)
    if not 1<=number(rate)<=15:raise ValueError('RESEARCH_RISK_RANGE')
    if not 0<stop<p<target:return None,'ENTRY_GAP_INVALIDATES_GEOMETRY'
    spread=p*max(D('.0005'),number(observed_spread or 0))
    stress=model=='TIERED_SPREAD_SLIPPAGE_STRESS'
    if stress:spread*=2
    slip=p*D('.0015' if stress else '.0005');gap=p*D('.01' if stress else '.005')
    budget=min(ledger.equity*number(rate)/100,D(15),D(20)-ledger.losses)
    paid=tick(p+spread/2+slip,True)
    upper=int(min(ledger.equity,ledger.cash)/paid)
    if upper>10000:return None,'SIMULATION_QUANTITY_RESOURCE_LIMIT'
    if upper<1:return None,'WHOLE_SHARE_OR_SETTLED_FUNDS_UNAFFORDABLE'
    for q in range(upper,0,-1):
        fees=commission(q,paid,model,'BUY')+commission(q,max(target,paid),model,'SELL')
        risk=q*(p-stop+spread+2*slip+gap+D('.02'))+fees
        potential=q*(target-p-spread-2*slip-gap-D('.02'))-fees
        if q*paid<=ledger.equity and q*paid+fees<=ledger.cash and risk<=budget and potential>0:
            return dict(quantity=q,risk=risk,budget=budget,paid_entry=paid,spread=spread,slip=slip,
                gap=gap,fees=fees,target_net=potential),None
    return None,'COSTS_RISK_FUNDS_OR_NET_TARGET_FAIL'


def wilson(wins,n,family=1):
    if n==0:return None
    z=NormalDist().inv_cdf(1-.05/(2*family));p=wins/n;den=1+z*z/n
    mid=(p+z*z/(2*n))/den;half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return [max(0,mid-half),min(1,mid+half)]


def confidence(trades,seed,family):
    n=len(trades);wins=sum(t['net_pnl']>0 for t in trades);by_day=defaultdict(list)
    for t in trades:by_day[t['day']].append(t['net_pnl'])
    values=[];days=sorted(by_day);rng=random.Random(seed)
    # Resample five observed trading-day blocks. Approximate interval, never a guarantee.
    if n>=2 and len(days)>=5:
        blocks=[[v for d in days[i:i+5] for v in by_day[d]] for i in range(0,len(days),5)]
        for _ in range(2000):
            sample=[v for _ in blocks for v in rng.choice(blocks)];values.append(mean(sample))
        values.sort()
    return dict(sample_size=n,trade_days=len(days),net_win_wilson_95=wilson(wins,n),
        net_win_wilson_family_adjusted=wilson(wins,n,family),family_comparisons=family,
        net_expectancy_block_bootstrap_95=[values[49],values[1949]] if values else None,
        bootstrap_repetitions=2000,confidence_scope='APPROXIMATE_EXPLORATORY_ALREADY_USED_DATA')


def inventory_accounting(rows,positions,model,end):
    """Last completed in-window close, no forced liquidation or future prices.

    Realized trade statistics exclude open inventory. NAV includes its BUY fee
    and price movement; a separate estimated liquidation NAV also reserves SELL
    costs. Neither mark is a fill, win, settlement, nor loss-budget restoration.
    Drawdown uses chronological entry, completed closes and actual exit marks.
    A separate conservative low-bar bound can include post-stop lows because
    OHLC cannot establish their intrabar order; it is not a realized loss.
    """
    peak=D(100);dd=D(0);low_dd=D(0);realized=D(0);pending=[];curve=[]

    def observe(stamp,nav,kind,low_nav=None):
        nonlocal peak,dd,low_dd
        if low_nav is not None:low_dd=max(low_dd,(peak-low_nav)/peak)
        peak=max(peak,nav);dd=max(dd,(peak-nav)/peak)
        if len(curve)<1000:curve.append(dict(at=stamp,equity=float(nav),kind=kind))

    for pos in positions:
        q=pos['quantity'];paid=pos['paid'];opening=pos['opening'];base=D(100)+realized
        entered=at(pos['entry_at']);closed=at(pos['exit_at']) if pos.get('exit_at') else None
        observe(pos['entry_at'],base+q*(pos['raw_entry']-paid)-opening,'ENTRY_MARK')
        last=None
        for b in rows[pos['index']:]:
            stamp=at(b['closed_at'])
            if stamp>=end or (closed is not None and stamp>=closed):break
            last=b
            nav=base+q*(number(b['close'])-paid)-opening
            low_nav=base+q*(number(b['low'])-paid)-opening
            observe(b['closed_at'],nav,'COMPLETED_CLOSE',low_nav)
        if closed is not None:
            # The closing bar low may be after a protective exit: retain only
            # a labelled conservative bound, not a claim about the NAV path.
            terminal=rows[pos['exit_index']]
            if pos['close_reason'] not in ('STOP_GAP','RULE_NEXT_OPEN'):
                low_dd=max(low_dd,(peak-(base+q*(number(terminal['low'])-paid)-opening))/peak)
            realized+=pos['net'];observe(pos['exit_at'],D(100)+realized,'REAL_EXIT')
            continue
        item=dict(contract=dict(symbol=pos['symbol'],sec_type='STK',currency='USD',
                    broker_contract_id=None,broker_execution='NOT_ATTEMPTED'),
                  quantity=q,entry_at=pos['entry_at'],entry_fill=float(paid),
                  raw_entry=float(pos['raw_entry']),opening_commission=float(opening),
                  opening_fee_details=pos['opening_fee_details'],stop=pos['stop'],target=pos['target'],
                  planned_risk=float(pos['risk']),risk_budget=float(pos['budget']),
                  entry_spread_cost=float(q*pos['spread']/2),entry_slippage_cost=float(q*pos['slip']),
                  entry_rounding_cost=float(q*(paid-pos['raw_entry']-pos['spread']/2-pos['slip'])),
                  definitive=False,decision='PREVIOUS_RESULT_NOT_DEFINITIVE',
                  market_price=None,mark_at=None,market_value=None,unrealized_price_pnl=None,
                  unrealized_net_contribution=None,estimated_liquidation_net_contribution=None,
                  estimated_closing_commission=None,remaining_stop_risk=None,
                  valuation_status='UNKNOWN_NO_COMPLETED_IN_WINDOW_PRICE')
        if last is not None:
            mark=number(last['close']);value=q*mark
            liquidation=tick(mark-pos['spread']/2-pos['slip'])
            stop_fill=tick(number(pos['stop'])-pos['spread']/2-pos['slip'])
            if min(liquidation,stop_fill)<=0:raise ValueError('NONPOSITIVE_INVENTORY_VALUATION')
            closing=commission(q,liquidation,model,'SELL')
            contribution=q*(mark-paid)-opening
            item.update(market_price=float(mark),mark_at=last['closed_at'],market_value=float(value),
                unrealized_price_pnl=float(q*(mark-paid)),unrealized_net_contribution=float(contribution),
                unrealized_gross_pnl=float(q*(mark-pos['raw_entry'])),
                estimated_closing_commission=float(closing),
                estimated_liquidation_net_contribution=float(q*(liquidation-paid)-opening-closing),
                remaining_stop_risk=float(max(D(0),q*(mark-stop_fill))+commission(q,stop_fill,model,'SELL')+q*pos['gap']),
                valuation_status='MARKED_NOT_CLOSED',cash_cost_basis=float(q*paid+opening))
        pending.append(item)
    unrealized=sum(number(p['unrealized_net_contribution']) for p in pending if p['market_value'] is not None)
    liquid_unrealized=sum(number(p['estimated_liquidation_net_contribution']) for p in pending if p['market_value'] is not None)
    known=all(p['market_value'] is not None for p in pending)
    return dict(policy='LAST_COMPLETED_CLOSE_BEFORE_EXCLUSIVE_WINDOW_END_NO_FORCED_FILL_V2',
        positions=pending,realized_net_pnl=float(realized),
        unrealized_net_contribution=float(unrealized) if known else None,
        portfolio_net_pnl=float(realized+unrealized) if known else None,
        equity=float(D(100)+realized+unrealized) if known else None,
        estimated_liquidation_equity=float(D(100)+realized+liquid_unrealized) if known else None,
        marked_drawdown=float(dd),conservative_intrabar_drawdown=float(max(dd,low_dd)),
        valuation_complete=known,portfolio_definitive=not pending,
        equity_curve_sample=curve,equity_curve_sample_limit=1000)


def simulate(rows,c,model,start,end,spread_ratio=None,prepared=None):
    start,end=at(start+'T00:00:00Z'),at(end+'T00:00:00Z')
    events,fs=prepared or signals(rows,c);ledger=Ledger();busy=None;trades=[];reject=Counter()
    days=sorted({at(b['opened_at']).astimezone(NY).date().isoformat() for b in rows})
    # Exit evaluation is clipped BEFORE inspecting OHLC, including max-hold
    # rules. Bars beyond this window can never decide its inventory valuation.
    window_rows=[b for b in rows if at(b['closed_at'])<end]
    peak=D(100);dd=0.;breaches=0;positions=[]
    for s in events:
        i=s['index'];t=at(rows[i]['opened_at']);stamp=t.isoformat()
        if not start<=at(s['signal_at'])<=t<end or i>=len(window_rows):continue
        if busy and t<=busy:reject['ONE_POSITION_OR_UNCERTAIN_CLOSE']+=1;continue
        gate=ledger.gate(stamp)
        if gate:reject[gate]+=1;continue
        ledger.available(stamp)
        plan,reason=size(rows[i]['open'],s['stop'],s['target'],c['risk_percent'],ledger,model,spread_ratio)
        if not plan:reject[reason]+=1;continue
        q=plan['quantity'];opening_details=commission_details(q,plan['paid_entry'],model,'BUY');opening=opening_details['total']
        ledger.begin(q*plan['paid_entry']+opening)
        position=dict(symbol=c['symbol'],index=i,quantity=q,paid=plan['paid_entry'],
            raw_entry=number(rows[i]['open']),opening=opening,entry_at=stamp,
            opening_fee_details=fee_evidence(opening_details),stop=s['stop'],target=s['target'],
            **{k:plan[k] for k in ('spread','slip','gap','risk','budget')})
        positions.append(position)
        exit=exit_event(window_rows,fs,s,c)
        if exit is None or at(exit[3])>=end:
            busy=end;reject['UNRESOLVED_PARTITION_POSITION']+=1;continue
        j,raw_exit,why,exit_at=exit
        filled=tick(number(raw_exit)-plan['spread']/2-plan['slip'])
        if filled<=0:raise ValueError('NONPOSITIVE_SIMULATED_EXIT')
        closing_details=commission_details(q,filled,model,'SELL');closing=closing_details['total'];gross=q*(number(raw_exit)-number(rows[i]['open']))
        net=q*(filled-plan['paid_entry'])-opening-closing;price_cost=gross-net-opening-closing
        mark=rows[i:j] if why in ('STOP_GAP','RULE_NEXT_OPEN') else rows[i:j+1]
        low=min([b['low'] for b in mark]+[raw_exit]);worst=ledger.equity+q*(number(low)-number(rows[i]['open']))-price_cost-opening-closing
        dd=max(dd,float((peak-worst)/peak));exit_day=at(exit_at).astimezone(NY).date().isoformat()
        next_i=bisect_right(days,exit_day);settles=days[next_i] if next_i<len(days) else None
        ledger.finish(net,q*filled-closing,exit_at,settles);busy=at(exit_at);peak=max(peak,ledger.equity)
        position.update(exit_at=exit_at,exit_index=j,net=net,close_reason=why)
        dd=max(dd,float((peak-ledger.equity)/peak));breach=-net>plan['budget'];breaches+=breach
        trades.append(dict(entry_at=stamp,exit_at=exit_at,day=ledger.day(exit_at),quantity=q,
            stop=s['stop'],target=s['target'],signal_at=s['signal_at'],indicators=s['indicators'],
            entry_fill=float(plan['paid_entry']),exit_fill=float(filled),close_reason=why,
            gross_pnl=float(gross),net_pnl=float(net),commissions=float(opening+closing),
            opening_commission=float(opening),closing_commission=float(closing),
            opening_fee_details=fee_evidence(opening_details),closing_fee_details=fee_evidence(closing_details),
            spread_cost=float(q*plan['spread']),slippage_cost=float(2*q*plan['slip']),
            price_rounding_cost=float(price_cost-q*plan['spread']-2*q*plan['slip']),
            spread_slippage=float(price_cost),planned_risk=float(plan['risk']),risk_budget=float(plan['budget']),
            gap_reserved=float(plan['gap']),risk_breach=breach,equity=float(ledger.equity),
            remaining_loss_budget=float(20-ledger.losses),decision=ledger.stops.get(ledger.day(exit_at),'WIN_CAN_SEEK_SIGNAL_WITH_SETTLED_FUNDS')))
    nets=[t['net_pnl'] for t in trades];wins=[x for x in nets if x>0];losses=[x for x in nets if x<0]
    accounting=inventory_accounting(window_rows,positions,model,end)
    accounting['cash_book']=float(ledger.cash)
    accounting['unsettled_proceeds']=float(sum(amount for _,amount in ledger.unsettled))
    accounting['pending_opening_fee_expense']=sum(p['opening_commission'] for p in accounting['positions'])
    if accounting['valuation_complete']:
        assets=ledger.cash+sum(amount for _,amount in ledger.unsettled)+sum(number(p['market_value']) for p in accounting['positions'])
        if abs(assets-number(accounting['equity']))>D('.00000001'):raise ValueError('SIMULATION_ASSET_NAV_MISMATCH')
        accounting['asset_nav_reconciled']=True
    else:accounting['asset_nav_reconciled']=False
    metrics=dict(admitted=len(trades),rejected=sum(reject.values()),rejection_reasons=dict(reject),
        net_pnl=sum(nets),gross_pnl=sum(t['gross_pnl'] for t in trades),
        win_rate=len(wins)/len(nets) if nets else None,net_expectancy=mean(nets) if nets else None,
        average_profit=mean(wins) if wins else None,average_loss=mean(losses) if losses else None,
        profit_factor=sum(wins)/-sum(losses) if losses else None,
        maximum_drawdown=max(dd,accounting['conservative_intrabar_drawdown']),
        marked_drawdown=accounting['marked_drawdown'],drawdown_scope='CONSERVATIVE_INTRABAR_BOUND_INCLUDES_OPEN_INVENTORY',
        commissions=sum(t['commissions'] for t in trades),spread_slippage=sum(t['spread_slippage'] for t in trades),
        first_loss_days=sum(v=='DAILY_FIRST_LOSS_STOP' for v in ledger.stops.values()),
        break_even_days=sum(v=='DAILY_BREAK_EVEN_STOP' for v in ledger.stops.values()),
        opening_commissions=sum(float(p['opening']) for p in positions),
        closing_commissions=sum(t['closing_commission'] for t in trades),
        commissions_incurred=sum(float(p['opening']) for p in positions)+sum(t['closing_commission'] for t in trades),
        pending_opening_commissions=sum(p['opening_commission'] for p in accounting['positions']),
        spread_cost=sum(t['spread_cost'] for t in trades),slippage_cost=sum(t['slippage_cost'] for t in trades),
        price_rounding_cost=sum(t['price_rounding_cost'] for t in trades),
        realized_equity=float(ledger.equity),portfolio_net_pnl=accounting['portfolio_net_pnl'],
        unrealized_net_contribution=accounting['unrealized_net_contribution'],
        estimated_liquidation_equity=accounting['estimated_liquidation_equity'],
        pnl_scope='CLOSED_TRADES_ONLY_NET_PNL__OPEN_INVENTORY_IN_PORTFOLIO_NET_PNL',
        valuation_complete=accounting['valuation_complete'],
        consumed_loss=float(ledger.losses),equity=accounting['equity'],risk_breaches=breaches,
        pending_position=bool(ledger.pending),capital_ruin_probability=None,execution_probability=None,
        loss_close_reasons=dict(Counter(t['close_reason'] for t in trades if t['net_pnl']<0)),
        gross_wins_turned_net_losses=sum(t['gross_pnl']>0 and t['net_pnl']<=0 for t in trades))
    return dict(metrics=metrics,trades=trades,inventory=accounting)


def evaluate(payload):
    c=payload['candidate'];rows=validated(payload['rows']);prepared=signals(rows,c);results={}
    if any(at(b['closed_at'])>=at('2024-01-01T00:00:00Z') for b in rows):raise ValueError('SEALED_DATA_FORBIDDEN')
    for model in MODELS:
        results[model]={name:simulate(rows,c,model,start,end,payload.get('spread_ratio'),prepared) for name,start,end in FOLDS}
    base=results[MODELS[0]]['validation'];m=base['metrics']
    ci=confidence(base['trades'],candidate_version(c),payload['family_comparisons']);reasons=[]
    if ci['sample_size']<100 or ci['trade_days']<30:reasons.append('INSUFFICIENT_SAMPLE')
    if m['win_rate'] is None or m['win_rate']<=.8:reasons.append('NET_WIN_RATE_NOT_ABOVE_80_PERCENT')
    if ci['net_win_wilson_family_adjusted'] is None or ci['net_win_wilson_family_adjusted'][0]<=.8:reasons.append('WIN_CONFIDENCE_INSUFFICIENT')
    if m['net_expectancy'] is None or m['net_expectancy']<=0 or m['profit_factor'] is None or m['profit_factor']<=1:reasons.append('NET_ECONOMICS_INSUFFICIENT')
    if ci['net_expectancy_block_bootstrap_95'] is None or ci['net_expectancy_block_bootstrap_95'][0]<=0:reasons.append('EXPECTANCY_CONFIDENCE_INSUFFICIENT')
    if any(results[MODELS[0]][f'wf{i}']['metrics']['net_pnl']<=0 for i in (1,2,3)):reasons.append('WALK_FORWARD_INSUFFICIENT')
    if any(results[model]['validation']['metrics']['net_pnl']<=0 for model in MODELS[1:]):reasons.append('COST_ROBUSTNESS_INSUFFICIENT')
    if any(results[model]['validation']['metrics']['maximum_drawdown']>.2 or results[model]['validation']['metrics']['risk_breaches'] for model in MODELS):reasons.append('DRAWDOWN_OR_GAP_RISK')
    if any(r['metrics']['pending_position'] or not r['metrics']['valuation_complete'] for model in results.values() for r in model.values()):reasons.append('RESULT_NOT_DEFINITIVE')
    reasons.append('EFFECTIVE_ACCOUNT_FEES_AND_EXECUTION_UNKNOWN')
    for model in results.values():
        for r in model.values():
            r['trade_sample']=r.pop('trades')[:100]  # bounded evidence; metrics retain every modeled trade
    return dict(version=candidate_version(c),candidate=c,results=results,confidence=ci,cost_version=COST_VERSION,
        cost_assumptions=cost_assumptions(),
        status='DISCARDED_RESEARCH_EVIDENCE' if reasons else 'INDEPENDENT_VALIDATION_REQUIRED',
        rejection_reasons=reasons,validation_limitations=payload['limitations'],
        independent_validation_required=True,folds_independent_allocations=True,
        final_holdout_evaluated=False,backtests=15,execution_authorized=False,live_approved=False)
