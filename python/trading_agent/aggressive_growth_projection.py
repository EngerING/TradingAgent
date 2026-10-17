"""Read-only R20 journal projection. No market, broker, database or model calls."""
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from .aggressive_growth import CLASSIFICATION, PROFILE, STRATEGY, instant


def decimal_text(value):
    """Missing or malformed evidence is unknown, never an implicit zero."""
    if not isinstance(value, str):
        return None
    try:
        return value if Decimal(value).is_finite() else None
    except InvalidOperation:
        return None


def fresh(at, now, seconds):
    try:
        return 0 <= (instant(now) - instant(at)).total_seconds() <= seconds
    except (ValueError, TypeError, AttributeError):
        return False


def trade_view(trade, run_kind):
    if trade['classification'] != CLASSIFICATION:
        raise ValueError('R20_FILL_CLASSIFICATION_REQUIRED')
    assessment = trade.get('assessment') or {}
    result = dict(id=trade['id'], classification=CLASSIFICATION, runKind=run_kind,
                  side=trade['side'], timeframe=trade['timeframe'], at=trade['at'],
                  closedAt=trade.get('closed_at'), reason=trade.get('exit_reason'))
    for target, source in dict(entry='entry', quantity='quantity', exposure='notional',
                               stop='stop', target='target', priceRisk='price_risk',
                               exit='exit', grossPnl='gross_pnl', netPnl='net_pnl').items():
        result[target] = decimal_text(trade.get(source))
    result.update(leverage=decimal_text(assessment.get('leverage')),
                  commissions=decimal_text(trade.get('fees', assessment.get('fees'))),
                  totalExpectedLoss=decimal_text(assessment.get('anticipated_total_loss')))
    return result


def kronos_view(state, now):
    signals = [s for s in state['signals'] if s.get('side') in ('LONG', 'SHORT')]
    signal = signals[-1] if signals else None
    # Agreement can only use the evidence frozen with that signal, never a later forecast.
    evidence = (signal.get('kronos') if signal else state.get('latest_kronos')) or {}
    decision_at = signal.get('observed_at') if signal else evidence.get('as_of')
    usable = False
    try:
        usable = (evidence.get('fresh') is True and decision_at is not None
                  and instant(evidence['created_at']) <= instant(decision_at) <= instant(now)
                  and instant(decision_at) < instant(evidence['prediction_end'])
                  and instant(now) < instant(evidence['prediction_end'])
                  and fresh(evidence['candle_timestamp'], decision_at, 3900)
                  and fresh(evidence['candle_timestamp'], now, 3900))
    except (KeyError, ValueError, TypeError, AttributeError):
        pass
    agreement = None
    if usable and signal and evidence.get('temporal_compatible') is True and evidence.get('timeframe') in (signal['timeframe'], str(signal['timeframe']), f"{signal['timeframe']}m"):
        direction = evidence.get('direction')
        if direction in ('LONG', 'SHORT'):
            agreement = 'AGREE' if direction == signal['side'] else 'DISAGREE'
    return dict(status=evidence.get('status', 'KRONOS_UNAVAILABLE') if usable else 'KRONOS_UNAVAILABLE',
                calibration='RAW_ONLY', calibratedProbability=None,
                predictionId=evidence.get('prediction_id'), createdAt=evidence.get('created_at'),
                candleAt=evidence.get('candle_timestamp'), decisionAt=decision_at, expiresAt=evidence.get('prediction_end'),
                agreement=agreement, reason=None if agreement else
                'NO_COMPARABLE_SIGNAL_EVIDENCE' if usable else 'FORECAST_MISSING_STALE_OR_NOT_AVAILABLE_AT_DECISION')


def project(payload, now=None):
    now = instant(now or datetime.now(timezone.utc))
    if (payload['scope'] != PROFILE or payload['classification'] != CLASSIFICATION
            or payload['broker_orders'] != 0 or payload['live_enabled'] is not False):
        raise ValueError('R20_SHADOW_SCOPE_REQUIRED')
    state = payload['state']; config = state['protocol']; paper = state['paper']
    if (config['profile'] != PROFILE or state['run_kind'] not in ('FORWARD', 'HISTORICAL')
            or paper['state'] != 'BLOCKED' or paper['authorization_granted'] is not False):
        raise ValueError('R20_PAPER_AUTHORITY_FORBIDDEN')
    portfolio = state['portfolios']['R20']; baseline = state['portfolios']['BASELINE_1X']
    closed = portfolio['trades']; active = portfolio['active']; assessment = (active or {}).get('assessment') or {}
    last_assessment = state.get('last_assessment') or {}
    recent = fresh(state['updated_at'], now, 180)
    status = 'SHADOW_HEARTBEAT_STALE' if not recent and state['status'] == 'SHADOW_RUNNING' else state['status']
    view = dict(experiment=payload['experiment'], profile=PROFILE, strategy=STRATEGY,
                version=state['strategy_version'], classification=CLASSIFICATION, runKind=state['run_kind'],
                status=status, evidenceQuality='RECENT_JOURNAL' if recent else 'STALE',
                startedAt=state['started_at'], updatedAt=state['updated_at'],
                initialCapital=decimal_text(portfolio.get('initial_capital')),
                priceRiskFraction=decimal_text(config.get('price_risk_fraction')),
                maxLeverage=decimal_text(config.get('max_leverage')),
                shadowTrades=len(closed), paperTrades=0, opportunities=state['opportunities'],
                signals=sum(s.get('side') in ('LONG', 'SHORT') for s in state['signals']))
    for target, source in dict(equity='equity', commissions='fees', spread='spread_cost',
                               slippage='slippage_cost', financing='financing_cost', realizedLoss='consumed_loss',
                               grossPnl='realized_gross', netPnl='realized_net', drawdown='current_drawdown',
                               maxDrawdown='maximum_drawdown').items():
        view[target] = decimal_text(portfolio.get(source))
    # Closed cost totals and P&L share a scope. Open-position estimates are in its row/assessment.
    view['costBasis'] = 'CLOSED_SHADOW_TRADES_MODELED_COSTS'
    view.update(exposure=decimal_text(active.get('current_notional')) if active else '0',
                effectiveLeverage=decimal_text(active.get('effective_leverage')) if active else '0',
                priceRisk=decimal_text(active.get('price_risk')) if active else '0',
                margin=decimal_text(active.get('margin')) if active else '0',
                anticipatedTotalLoss=decimal_text(assessment.get('anticipated_total_loss')),
                liquidationRisk=('MODELED_LIQUIDATION_RISK' if active.get('liquidation_risk') is True
                                 else 'GAPS_AND_EQUITY_DECLINE_POSSIBLE') if active else 'NO_OPEN_POSITION')
    results = [decimal_text(t.get('net_pnl')) for t in closed]
    known_results = bool(results) and all(v is not None for v in results)
    view['winRate'] = str(sum(Decimal(v) > 0 for v in results) / Decimal(len(results))) if known_results else None
    view['expectancy'] = str(sum(Decimal(v) for v in results) / len(results)) if known_results else None
    economically_viable = last_assessment.get('economically_viable')
    view['eligibility'] = dict(researchEligible=last_assessment.get('research_eligible') is True,
                              economicallyViable='POSITIVE_TARGET_AFTER_ESTIMATED_COSTS' if economically_viable is True else
                              'NEGATIVE_TARGET_AFTER_ESTIMATED_COSTS' if economically_viable is False else 'UNKNOWN',
                              statisticallyValidated=False, paperExecutionEligible=False)
    quote = state.get('last_quote') or {}
    view['market'] = dict(status='DATA_UNAVAILABLE' if not quote else
                         quote.get('market_status', 'UNKNOWN') if fresh(quote.get('at'), now, 30) else 'STALE',
                         at=quote.get('at'), source=quote.get('source', 'UNKNOWN'))
    view['kronos'] = kronos_view(state, now)
    view['baseline'] = dict(equity=decimal_text(baseline.get('equity')), netPnl=decimal_text(baseline.get('realized_net')),
                            closedTrades=len(baseline['trades']), leverage='1',
                            description='Cartera independiente de US$100: mismas oportunidades y costos, límite 1×; puede rechazar tamaños distintos.')
    rejection = state.get('last_no_trade')
    view['lastNoTrade'] = dict(at=rejection['at'], reason=rejection['reason']) if rejection else None
    view['lastAssessment'] = deepcopy(state.get('last_assessment'))
    view['recentSignals'] = []
    for signal in state['signals'][-200:]:
        decision = signal.get('decisions', {}).get('R20', {})
        view['recentSignals'].append(dict(id=signal['id'], at=signal['at'], timeframe=signal['timeframe'],
                                         side=signal.get('side'), reason=decision.get('reason'),
                                         status='SHADOW_ADMITTED' if decision.get('admitted') is True else 'NO_TRADE'))
    view['trades'] = [trade_view(t, state['run_kind']) for t in closed[-200:] + ([active] if active else [])]
    view['paper'] = dict(classification='IBKR_PAPER', state='BLOCKED', authorizationGranted=False,
                        blockers=list(paper['blockers']), conditions=list(paper['conditions']))
    view['xauStatus'] = config.get('xauusd_status', 'BLOCKED_DATA_QUALITY_AND_BROKER_CONDITIONS_UNVERIFIED')
    return view
