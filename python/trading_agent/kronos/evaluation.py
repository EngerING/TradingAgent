from .contracts import finite, instant, validate_signal

def economic_profiles(signal, calibration, config, equities=None, profile_state=None):
    """Independent observation-only cost gate. Never calls or changes RiskEngine."""
    validate_signal(signal); equities = equities or {'R1':100., 'R5':100., 'R10':100.}
    out = {}
    for name, fraction in [('R1', .01), ('R5', .05), ('R10', .10)]:
        state = profile_state.get(name, {}) if profile_state is not None else None
        unavailable = state is not None and state.get('quality') != 'VERIFIED_SHADOW_JOURNAL'
        equity = finite(state['equity']) if state and not unavailable else finite(equities[name])
        consumed = finite(state['consumed_loss']) if state and not unavailable else 0.
        reserved = finite(state['reserved_usd']) if state and not unavailable else 0.
        if min(equity, consumed, reserved) < 0: raise ValueError('INVALID_PROFILE_STATE')
        budget = max(0., min(equity*fraction, 100*fraction, config['cumulative_loss_cap_usd']-consumed)); entry = signal['entry']
        variable = config['spread_usd_per_eur']+2*config['slippage_usd_per_eur_per_side']+config['gap_usd_per_eur']
        fees = config['commission_round_trip_usd']; distance = abs(entry-signal['stop_loss'])
        blocked = ('PROFILE_STATE_UNKNOWN' if unavailable else 'RESULT_RECONCILIATION_PENDING' if state and state['pending'] else
            'FIRST_LOSS_STOPS_DAY' if state and state['stopped_day'] else 'CUMULATIVE_LOSS_LIMIT' if consumed >= config['cumulative_loss_cap_usd'] else None)
        quantity = 0. if blocked else max(0., min((budget-fees)/(distance+variable), (min(equity,100)-reserved-fees)/(entry+variable)))
        quantity = int(quantity*100)/100; costs = fees + quantity*variable
        gross = quantity*abs(signal['take_profit']-entry); win = gross-costs; loss = quantity*distance+costs
        p = calibration['calibrated_probability']; ev = p*win-(1-p)*loss if p is not None else None
        lo = calibration.get('lower95'); lower_ev = lo*win-(1-lo)*loss if lo is not None else None
        reason = blocked or ('COMMISSION_EXCEEDS_RISK_BUDGET' if quantity==0 else 'TARGET_DOES_NOT_COVER_COSTS' if win <= config['economic_uncertainty_usd'] else 'INSUFFICIENT_EVIDENCE' if p is None else 'EV_NOT_POSITIVE_WITH_UNCERTAINTY' if lower_ev is None or lower_ev <= config['economic_uncertainty_usd'] else None)
        out[name] = dict(quantity=quantity, equity=equity if not unavailable else None, reserved_usd=reserved if not unavailable else None,
            consumed_loss=consumed if not unavailable else None, risk_budget=budget if not unavailable else None,
            risk=loss if quantity else 0., costs=costs, fees=fees, gross_expected_win=gross,
            net_expected_win=win, expected_loss=loss, reward_risk=win/loss if loss else None,
            expected_value=ev, lower_bound_expected_value=lower_ev,
            break_even_win_rate=loss/(win+loss) if win>0 else None, decision='NO_TRADE' if reason else 'SHADOW_ELIGIBLE_ONLY', reason=reason,
            execution_authority=False, costs_evidence='ESTIMATED_FROM_ONE_PRIOR_PAPER_CYCLE_AND_CONSERVATIVE_FRICTION')
    return out

def consensus(signal, prediction, calibration, config, technical_features=None, profile_state=None):
    median = prediction['predicted_return_median']; direction = 'LONG' if median>0 else 'SHORT' if median<0 else 'FLAT'
    disagreements = ['TECHNICAL_KRONOS_DIRECTION_CONFLICT'] if signal and signal['direction'] != direction else []
    return dict(technical_signal=signal['direction'] if signal else None, technical_score=None, kronos_direction=direction,
        kronos_raw_tp_frequency=prediction.get('raw_tp_frequency'), kronos_calibrated_tp_probability=calibration['calibrated_probability'],
        market_regime=prediction['regime'], disagreements=disagreements, consensus='CONFLICT' if disagreements else 'SUPPORTIVE' if signal else 'NO_TECHNICAL_SIGNAL',
        indicators=technical_features or {}, economic_profiles=economic_profiles(signal,calibration,config,profile_state=profile_state) if signal else {},
        sol_authority='CONTEXT_ONLY', risk_engine_required=True, execution_guard_required=True, paper_authorization_required=True)

def required_gate(prediction, now, maximum_age, required):
    stale = prediction is None or not 0 <= (instant(now)-instant(prediction['candle_timestamp'])).total_seconds() <= maximum_age
    return {'decision':'NO_TRADE' if required and stale else 'OBSERVATION_ONLY',
            'reason':'KRONOS_REQUIRED_BUT_UNAVAILABLE' if required and stale else 'DEGRADED_MODE' if stale else None,
            'execution_authority':False}

def trade_metrics(nets, gross=None, fees=None, costs=None):
    n = len(nets); wins = [x for x in nets if x>0]; losses=[x for x in nets if x<0]
    equity=peak=100.; dd=0
    for x in nets: equity+=x; peak=max(peak,equity); dd=max(dd,peak-equity)
    return dict(trades=n, net_pnl=sum(nets), gross_pnl=sum(gross) if gross is not None else None,
        commissions=sum(fees) if fees is not None else None, net_win_rate=len(wins)/n if n else None,
        total_costs=sum(costs) if costs is not None else None,
        friction_costs=sum(costs)-sum(fees) if costs is not None and fees is not None else None,
        cost_to_gross_profit_ratio=sum(costs)/sum(max(0.,g) for g in gross) if costs is not None and gross is not None and sum(max(0.,g) for g in gross)>0 else None,
        expectancy=sum(nets)/n if n else None, profit_factor=sum(wins)/-sum(losses) if losses else None,
        maximum_drawdown=dd, remaining_equity=equity)

def paired_benchmark(records, config):
    """Frozen comparator. Calibration rows never count as out-of-sample trades.

    Actual first-bar open for entry; real adverse gaps; finite horizon end mark.
    Same signals/stops/costs/daily policy. Kronos only adds a calibrated EV filter.
    """
    from zoneinfo import ZoneInfo
    from .calibration import wilson
    result={}; rows=sorted((r for r in records if r.get('partition')=='VALIDATION'),key=lambda r:r['prediction_start'])
    for name, fraction in [('R1',.01),('R5',.05),('R10',.10)]:
        arms={}
        for arm in ('BASELINE_ACTUAL','BASELINE_PLUS_KRONOS'):
            equity=100.; consumed=0.; stopped=set(); until=None; nets=[]; gross=[]; fees=[]; costs=[]; outcomes=[]; rejection={};pending=[]
            for r in rows:
                start=instant(r['prediction_start']); day=start.astimezone(ZoneInfo('America/Santo_Domingo')).date().isoformat()
                reason=None
                if until and start<until: reason='POSITION_PENDING'
                elif day in stopped: reason='FIRST_LOSS_STOPS_DAY'
                elif consumed>=config['cumulative_loss_cap_usd']: reason='CUMULATIVE_LOSS_LIMIT'
                elif not r.get('signal') or not r.get('future_bars'): reason='NO_SIGNAL_OR_INCOMPLETE_OUTCOME'
                if reason: rejection[reason]=rejection.get(reason,0)+1; continue
                s=dict(r['signal']); s['entry']=float(r['future_bars'][0]['open'])
                state={k:dict(equity=equity,consumed_loss=consumed,reserved_usd=0.,pending=False,stopped_day=False,quality='VERIFIED_SHADOW_JOURNAL') for k in ('R1','R5','R10')}
                try: size=economic_profiles(s,r['calibration'],config,profile_state=state)[name]
                except ValueError: rejection['GAP_INVALIDATED_GEOMETRY']=rejection.get('GAP_INVALIDATED_GEOMETRY',0)+1; continue
                # Baseline also needs a positive potential net target; never bypass numeric risk.
                bad=size['quantity']<=0 or size['net_expected_win']<=config['economic_uncertainty_usd']
                if arm=='BASELINE_PLUS_KRONOS':bad=bad or size['decision']!='SHADOW_ELIGIBLE_ONLY' or r['consensus']['disagreements']!=[]
                if bad: rejection[size['reason'] or 'Kronos_CONFLICT']=rejection.get(size['reason'] or 'Kronos_CONFLICT',0)+1;continue
                long=s['direction']=='LONG'; exit_price=None; exit_at=None; outcome=None
                market=r.get('strategy_future_bars',r['future_bars']);deadline=instant(s['hold_until']) if s.get('hold_until') else instant(r['prediction_end'])
                for b in market:
                    o,h,l=(float(b[k]) for k in ('open','high','low')); sl=s['stop_loss'];tp=s['take_profit']
                    if (o<=sl if long else o>=sl):exit_price=o;outcome='SL_FIRST'
                    elif (l<=sl if long else h>=sl):exit_price=sl;outcome='SL_FIRST'
                    elif (h>=tp if long else l<=tp):exit_price=tp;outcome='TP_FIRST'
                    elif instant(b['opened_at'])>=deadline:exit_price=o;outcome='ORIGINAL_HOLD_NEXT_OPEN'
                    else:continue
                    exit_at=instant(b['opened_at'])+__import__('datetime').timedelta(seconds=3600);break
                if exit_price is None:
                    pending.append(dict(signal_id=s['signal_id'],quantity=size['quantity'],risk=size['risk'],mark_at=market[-1]['opened_at'],unrealized_pnl=size['quantity']*(float(market[-1]['close'])-s['entry'])*(1 if long else -1)))
                    # No definite exit: inventory stays pending even across subsequent opportunity windows.
                    until=__import__('datetime').datetime.max.replace(tzinfo=__import__('datetime').timezone.utc);continue
                g=size['quantity']*(exit_price-s['entry'])*(1 if long else -1); net=g-size['costs']
                gross.append(g);fees.append(size['fees']);costs.append(size['costs']);nets.append(net);outcomes.append(outcome);equity+=net;consumed+=max(0,-net);until=exit_at
                if net<=0:stopped.add(exit_at.astimezone(ZoneInfo('America/Santo_Domingo')).date().isoformat())
            arms[arm]=dict(**trade_metrics(nets,gross,fees,costs),raw_win_rate=outcomes.count('TP_FIRST')/len(outcomes) if outcomes else None,
                confidence_interval=wilson(sum(x>0 for x in nets),len(nets)),opportunities=len(rows),rejected=rejection,days_stopped=len(stopped),
                policy='WIN_TO_CONTINUE / FIRST_LOSS_STOPS_DAY',timeframe='1H',costs_evidence='CONSERVATIVE_ESTIMATED',risk_fraction=fraction,pending_positions=pending)
        arms['delta_expectancy']=arms['BASELINE_PLUS_KRONOS']['expectancy']-arms['BASELINE_ACTUAL']['expectancy'] if all(arms[a]['expectancy'] is not None for a in ('BASELINE_ACTUAL','BASELINE_PLUS_KRONOS')) else None
        result[name]=arms
    return dict(state='INSUFFICIENT_EVIDENCE',profiles=result,automatic_promotion=False,final_test='SEALED',parameter_changes=False)
