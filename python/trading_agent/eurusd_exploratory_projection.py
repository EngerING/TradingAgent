"""Pure read model; never imports authorization, account identity or broker adapters."""
from datetime import datetime,timezone
from .dashboard_projection import numeric,moment,safe_text

PROFILES=('EURUSD_R1','EURUSD_R5','EURUSD_R10')
def view_trial(t,quote):
    fills=list(t['fills'].values());buys=[e for e in fills if e['side']=='BUY'];sells=[e for e in fills if e['side']=='SELL']
    q=sum(float(e['quantity']) for e in buys);sold=sum(float(e['quantity']) for e in sells);remaining=q-sold
    entry=sum(float(e['quantity'])*float(e['price']) for e in buys)/q if q else None
    exit=sum(float(e['quantity'])*float(e['price']) for e in sells)/sold if sold else None
    current=numeric(quote.get('bid')) if quote.get('type')=='LIVE' and quote.get('at') and 0<=(datetime.now(timezone.utc)-moment(quote['at'])).total_seconds()<=5 else None
    fee=sum(float(t['commissions'][e['exec_id']]['amount']) for e in fills if e['exec_id'] in t['commissions'])
    known=all(e['exec_id'] in t['commissions'] for e in fills)
    gross=numeric(t.get('gross_pnl'));net=numeric(t.get('net_pnl'));slippage=None
    if t['state']!='CLOSED_RECONCILED' and current is not None and entry is not None:
        gross=sum(float(e['quantity'])*float(e['price'])*(1 if e['side']=='SELL' else -1) for e in fills)+remaining*current
        net=None # Unknown exit commission is never presented as a definitive result.
    opening_slippage=sum(float(e['quantity'])*(float(e['price'])-float(t['quote']['ask'])) for e in buys) if buys else None
    closing_slippage=None
    if sells and t.get('closing_quote') and all(e.get('broker_at') and 0<=(moment(e['broker_at'])-moment(t['closing_quote']['at'])).total_seconds()<=5 for e in sells):
        closing_slippage=sum(float(e['quantity'])*(float(t['closing_quote']['bid'])-float(e['price'])) for e in sells)
    slippage=opening_slippage+closing_slippage if opening_slippage is not None and closing_slippage is not None else None
    exit_reason=('OWNED_RECOVERY_CLOSE' if any(str(e['order_id']) in t['recovery_orders'] for e in sells) else
                 'BROKER_STOP' if any(e['order_id']==t['order_ids'][2] for e in sells) else
                 'RULE_EXIT_NEXT_OBSERVED_OPEN' if t['close_attempted'] else 'BROKER_TAKE_PROFIT' if sells else 'OPEN')
    return dict(id=t['trial_id'],profile=t['profile'],symbol='EUR/USD',direction='LONG',quantity=remaining if t['state']!='CLOSED_RECONCILED' else q,
        requestedQuantity=numeric(t['quantity']),filledQuantity=q,entry=entry,currentPrice=current,stop=numeric(t['stop']),target=numeric(t['target']),exit=exit,
        openedAt=t['entry_at'],closedAt=t.get('closed_at'),durationSeconds=t.get('duration_seconds'),grossPnl=gross,netPnl=net,
        commission=fee if fills else None,commissionStatus='VERIFIED' if known and fills else 'PENDING',
        spread=q*(float(t['quote']['ask'])-float(t['quote']['bid'])),slippage=slippage,openingSlippage=opening_slippage,closingSlippage=closing_slippage,probability=numeric(t['signal'].get('probability')),
        expectedValue=numeric(t['decision'].get('prior_ev')),regime=t['signal'].get('regime','UNKNOWN'),entryReason='SUPERVISED_INFRASTRUCTURE_DIAGNOSTIC_NOT_STRATEGY_SIGNAL' if t.get('purpose')=='PAPER_EXECUTION_DIAGNOSTIC' else 'ORIGINAL_TREND_V1_EXPLORATORY_SIGNAL',
        exitReason=t.get('close_reason',exit_reason),signalId=t['signal']['opportunity_id'],strategyVersion=t['strategy']['strategy_version'],
        classification='BROKER_PAPER_EXECUTION',environment='PAPER_TRADING',purpose=t.get('purpose','PAPER_EXPLORATORY_RESEARCH'),predictiveValidation=False,kronos=t.get('kronos'),protection='ACKNOWLEDGED' if t['protection_confirmed'] else 'PENDING',
        status=t['state'],outcome=('WIN' if net>0 else 'LOSS' if net<0 else 'BREAK_EVEN') if net is not None and t['state']=='CLOSED_RECONCILED' else None,
        exitCategory=None,validation='EXPLORATORY_NOT_VALIDATED',orderRef=t['intent'],orderIds=t['order_ids'],commissions=t['commissions'])

def overlay(result,payload):
    if payload.get('scope')!='EURUSD_PAPER_EXPLORATORY' or payload.get('classification')!='EXPLORATORY_NOT_VALIDATED' or payload.get('live_enabled') is not False:raise ValueError('EXPLORATORY_UI_SCOPE_REQUIRED')
    state=payload['state'];next_profile=PROFILES[state['rotation']];active=state['active'];quote=state.get('last_quote',{})
    observed=result['market']
    if observed.get('quality')=='LIVE' and observed.get('at') and (not quote.get('at') or moment(observed['at'])>moment(quote['at'])):
        quote=dict(bid=observed['bid'],ask=observed['ask'],at=observed['at'],type='LIVE',market_status=observed['marketStatus'])
    if quote:
        age=(datetime.now(timezone.utc)-moment(quote['at'])).total_seconds() if quote.get('at') else None
        result['market'].update(status='AVAILABLE',bid=numeric(quote.get('bid')),ask=numeric(quote.get('ask')),at=quote.get('at'),ageSeconds=age,
            spread=numeric(quote['ask'])-numeric(quote['bid']) if quote.get('ask') and quote.get('bid') else None,
            quality=quote.get('type','MISSING') if age is not None and 0<=age<=5 else 'STALE',marketStatus=quote.get('market_status','UNKNOWN'),features=state.get('features',{}),
            source='IBKR_PAPER_EXPLORATORY_READ_ONLY_QUOTES')
    broker=[view_trial(t,quote) for t in state['trials'] if t['state']=='CLOSED_RECONCILED']
    result['rotation']=dict(cohort=payload['cohort_id'],nextProfile=next_profile,state=state['status'],globalStop=state['global_stop'],
                            validation='EXPLORATORY_NOT_VALIDATED',authorization='INDEPENDENT_OPERATOR_REQUIRED',strategyVersion=state['protocol']['strategy']['strategy_version'])
    auth=state.get('authorization') or {};expired=bool(auth.get('expires_at') and moment(auth['expires_at'])<=datetime.now(timezone.utc))
    last=state.get('last_inspect',{});sizes=state.get('last_opportunity',{}).get('decisions',last.get('sizes',{}))
    feed=state.get('paper_feed',[])
    result['rotation'].update(protocolVersion=state['protocol'].get('protocol_version',1),purpose=state['protocol'].get('purpose','PAPER_EXPLORATORY_RESEARCH'),
        authorizationStatus='EXPIRED' if expired else auth.get('status','NOT_AUTHORIZED'),authorizationExpiresAt=auth.get('expires_at'),
        operationalState='RECOVERY_REQUIRED' if state['global_stop'] and active else 'BLOCKED' if state['global_stop'] or last.get('emergency') else
            'RECONCILING' if active and active['fills'] and RotatorInventory(active)==0 else 'EXITING' if active and active['close_attempted'] else 'PROTECTED' if active and active['protection_confirmed'] else
            'PAPER_EXECUTING' if active else 'AWAITING_AUTHORIZATION',
        eligibility={p:dict(status=state['profiles'][p].get('eligibility','BROKER_INELIGIBLE' if sizes.get(p,{}).get('reason')=='COMMISSION_EXCEEDS_RISK_BUDGET' else 'UNKNOWN'),
            reason=sizes.get(p,{}).get('reason'),quantity=numeric(sizes.get(p,{}).get('quantity')),risk=numeric(sizes.get(p,{}).get('risk'))) for p in PROFILES},
        lastExecutedProfile=broker[-1]['profile'] if broker else None,completedPaper=len(broker),observedFees=sum(b['commission'] or 0 for b in broker),
        shadowTrades=sum(len(p['shadow_trades']) for p in state['profiles'].values()),skipped=len(state.get('skips',[])),events=feed,
        emergency='ACTIVE' if last.get('emergency') else 'UNKNOWN',maxOpenings=state['protocol'].get('max_openings'),
        blockers=list(dict.fromkeys(b for p in state['profiles'].values() for b in p['blockers'])),
        selectionBias=state['protocol'].get('selection_bias','Sequential allocation; not comparable timing'))
    result['trades'].extend(broker)
    for trial in state['trials']:
        if trial['state']!='CLOSED_RECONCILED':continue
        for p,twin in trial['twins'].items():
            if twin['state']!='CLOSED':continue
            result['trades'].append(dict(id=trial['trial_id']+'-'+p,profile=p,symbol='EUR/USD',direction='LONG',quantity=numeric(twin['quantity']),entry=numeric(twin['entry']),
                currentPrice=None,stop=numeric(twin['stop']),target=numeric(twin['target']),exit=numeric(twin['exit']),openedAt=twin['entry_at'],closedAt=twin['exit_at'],
                durationSeconds=(moment(twin['exit_at'])-moment(twin['entry_at'])).total_seconds(),grossPnl=numeric(twin['gross_pnl']),netPnl=numeric(twin['net_pnl']),commission=numeric(twin['fees']),
                commissionStatus='ESTIMATED',spread=None,slippage=None,probability=None,expectedValue=None,regime=trial['signal'].get('regime','UNKNOWN'),entryReason='PAIRED_WITH_BROKER_FILL',exitReason=twin['close_reason'],
                signalId=trial['signal']['opportunity_id'],strategyVersion=trial['strategy']['strategy_version'],classification='SIMULATED_SHADOW',environment='INTERNAL_SIMULATION',protection='SIMULATED_ONLY',status='CLOSED',
                outcome='WIN' if numeric(twin['net_pnl'])>0 else 'LOSS' if numeric(twin['net_pnl'])<0 else 'BREAK_EVEN',exitCategory=None))
    if active and active['fills']:result['openPositions'].append(view_trial(active,quote))
    # Keep the original sealed Shadow cohort's metrics separately; never combine cohorts.
    for e in result['experiments']:
        p=state['profiles'][e['id']];rows=[b for b in broker if b['profile']==e['id']];nets=[b['netPnl'] for b in rows]
        research_nets=[b['netPnl'] for b in rows if b['purpose']!='PAPER_EXECUTION_DIAGNOSTIC']
        fees=sum((b['commission'] or 0) for b in rows);positive=sum(n for n in research_nets if n>0);negative=-sum(n for n in research_nets if n<0)
        e['brokerMetrics']=dict(trades=len(rows),netPnl=sum(nets),grossPnl=sum(b['grossPnl'] for b in rows),fees=fees,
            diagnosticTrades=sum(b['purpose']=='PAPER_EXECUTION_DIAGNOSTIC' for b in rows),researchTrades=len(research_nets),
            winRate=sum(n>0 for n in research_nets)/len(research_nets) if research_nets else None,expectancy=sum(research_nets)/len(research_nets) if research_nets else None,
            profitFactor=positive/negative if negative else None,averageSlippage=sum(b['slippage'] for b in rows if b['slippage'] is not None)/sum(b['slippage'] is not None for b in rows) if any(b['slippage'] is not None for b in rows) else None)
        today=datetime.now(timezone.utc).astimezone(__import__('zoneinfo').ZoneInfo('America/Santo_Domingo')).date().isoformat()
        role='BROKER PAPER' if active and active['profile']==e['id'] else 'SHADOW' if active and e['id'] in active['twins'] and active['twins'][e['id']]['state']=='OPEN' else 'WAITING'
        if today in p['stopped_days']:role='STOPPED_FOR_DAY'
        elif state['global_stop'] or e['id']==next_profile and p['blockers']:role='BLOCKED'
        e.update(executionRole=role,cohortId=payload['cohort_id'],paperEquity=numeric(p['equity']),paperReserved=numeric(p['reserved']),paperBlockers=p['blockers'])
    if active:
        for p,t in active['twins'].items():
            if t['state']!='OPEN':continue
            result['openPositions'].append(dict(id=active['trial_id']+'-'+p,profile=p,symbol='EUR/USD',direction='LONG',quantity=numeric(t['quantity']),
                entry=numeric(t['entry']),currentPrice=numeric(quote.get('bid')),stop=numeric(t['stop']),target=numeric(t['target']),
                grossPnl=None,netPnl=None,commission=None,commissionStatus='ESTIMATED',classification='SIMULATED_SHADOW',environment='INTERNAL_SIMULATION',
                protection='SIMULATED_ONLY',status='OPEN',openedAt=t['entry_at'],closedAt=None,exit=None,spread=None,slippage=None,probability=None,expectedValue=None,
                regime=active['signal'].get('regime','UNKNOWN'),entryReason='PAIRED_WITH_BROKER_FILL',exitReason='',strategyVersion=active['strategy']['strategy_version'],
                signalId=active['signal']['opportunity_id'],durationSeconds=None,outcome=None,exitCategory=None))
    result['notifications'].append(dict(id='paper-exploratory',kind='warning',text='EXPLORATORY_NOT_VALIDATED. Próximo perfil Paper: '+next_profile+'. No promoción automática.'))
    return result

def RotatorInventory(t):
    return sum(float(e['quantity'])*(1 if e['side']=='BUY' else -1) for e in t['fills'].values())
