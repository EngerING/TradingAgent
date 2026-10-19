"""Actual execution-policy reruns, or a deliberately narrow economic equivalence proof."""
from dataclasses import replace
from decimal import Context, Decimal, DecimalException, Inexact, localcontext

from ..contracts import ContractError, Money, Price, SourceKind, canonical_bytes, content_hash, require
from ..event_backtest.accounting import ExecutionMath
from ..event_backtest.contracts import Role, Side, Status
from ..event_backtest.reader import load
from ..event_backtest.simulation import Simulation
from .contracts import RobustnessMetrics
from .evidence import observe


def _derived(record):
    return replace(record, evidence=replace(record.evidence, source_kind=SourceKind.DERIVED,
                                            content_sha256=record.material_hash()))


def _context(context, scenario):
    """Counterfactual assumptions; never accepted as a freshly authenticated V3.2 source."""
    quote = context.market.instrument.quote_currency
    extras = (scenario.extra_opening_fee, scenario.extra_closing_fee, scenario.extra_financing_fixed,
              scenario.extra_financing_per_unit_hour)
    require(all(m is None or m.currency == quote for m in extras), 'ROBUSTNESS_CURRENCY_MISMATCH')
    def add(money, extra):
        return money if extra is None else money.add(extra)
    market, costs = context.market, context.costs
    half = market.instrument.tick.amount*scenario.extra_half_spread_ticks
    market = _derived(replace(market,
        bid=Price(market.bid.amount-half, market.bid.currency, market.bid.per_unit),
        ask=Price(market.ask.amount+half, market.ask.currency, market.ask.per_unit)))
    costs = _derived(replace(costs,
        opening_minimum=add(costs.opening_minimum, scenario.extra_opening_fee),
        closing_minimum=add(costs.closing_minimum, scenario.extra_closing_fee),
        financing_fixed=add(costs.financing_fixed, scenario.extra_financing_fixed),
        financing_per_unit_per_hour=replace(costs.financing_per_unit_per_hour,
            money=add(costs.financing_per_unit_per_hour.money, scenario.extra_financing_per_unit_hour)),
        slippage_per_side=replace(costs.slippage_per_side, money=add(costs.slippage_per_side.money,
            Money(market.instrument.tick.amount*scenario.extra_slippage_ticks, quote)))))
    return replace(context, market=market, costs=costs)


def _equivalence(observation, scenario, catalog, journal):
    """Prove all cost-sensitive decisions unchanged for exactly one admitted closed trade.

    Signals, mid triggers, gap precedence and timing do not depend on costs in V3.6.
    Recheck admission and every held close's maintenance condition. No multi-trade
    claim is made: changed losses/capital could alter a later entry.
    """
    result = observation.result
    require(result.status is Status.COMPLETE and len(result.trades) == 1
            and len([o for o in result.orders if o.role is Role.ENTRY]) == 1
            and result.trades[0].reason != 'MAINTENANCE_MARGIN', 'ROBUSTNESS_PROOF_SCOPE')
    with localcontext(Context(prec=160)) as arithmetic:
        arithmetic.traps[Inexact] = True
        version, evidence = load(observation.request, catalog, journal, observation.dataset, observation.policy)
        probe = Simulation(observation.request, version, evidence, observation.dataset, observation.policy)
        derived = _context(probe.context, scenario)
        probe.context = derived
        probe.model = model = ExecutionMath(derived, probe.scenario.quantity)
        trade = result.trades[0]
        orders = {o.order_id: o for o in result.orders}
        entry = model.fill(orders[trade.entry.order_id], trade.entry.bar_index, trade.entry.at, trade.entry.mid_price)
        require(probe._entry_reason(entry) is None, 'ROBUSTNESS_ADMISSION_CHANGED')
        exit_fill = model.fill(orders[trade.exit.order_id], trade.exit.bar_index, trade.exit.at, trade.exit.mid_price)
        finance = model.financing(entry.at, exit_fill.at)
        costs = model.costs(entry, exit_fill, finance)
        gross = model.gross(entry, exit_fill)
        net = gross.add(Money(-costs.total.amount, gross.currency))
        sign = 1 if entry.side is Side.BUY else -1
        exit_side = Side.SELL if entry.side is Side.BUY else Side.BUY
        peak, dd, marks = probe.initial, Decimal(0), []
        for snapshot in result.equity:
            index = snapshot.bar_index
            if index < entry.bar_index:
                mark, maintenance = probe.initial, Decimal(0)
            elif index >= exit_fill.bar_index:
                mark, maintenance = probe.initial+net.amount, Decimal(0)
            else:
                bar = observation.dataset.bars[index]
                executable = model.execution_price(bar.close, exit_side)[0]
                pnl = model.money(sign*(executable.amount-entry.price.amount)*entry.quantity.amount
                                  *model.instrument.multiplier).amount
                mark = probe.initial-entry.commission.amount+pnl-model.commission(Role.EXIT).amount \
                    -model.financing(entry.at, bar.closed_at).amount
                maintenance = probe._notional(bar.close)*derived.margin.maintenance_fraction
                require(mark >= maintenance, 'ROBUSTNESS_MAINTENANCE_CHANGED')
            peak = max(peak, mark)
            dd = max(dd, peak-mark)
            marks.append(dict(bar_index=index, mark=model.account(mark), maintenance=model.account(maintenance)))
        realized_dd = max(entry.commission.amount, max(Decimal(0), -net.amount))
        proof = canonical_bytes(dict(scope='COUNTERFACTUAL_EQUIVALENCE_ONLY',
            base_observation_sha256=content_hash(observation), scenario=scenario, derived_context=derived,
            entry=entry, exit=exit_fill, costs=costs, net=net, marks=marks,
            admission='UNCHANGED_FIRST_ENTRY', maintenance='NO_NEW_EXIT',
            realized_drawdown=model.account(realized_dd), mark_drawdown=model.account(dd))).decode('utf-8')
        return net, model.account(realized_dd), model.account(dd), proof


def evaluate(base, scenario, candidate, split, warmup, catalog, journal, policy, manifest_hash, index,
             remaining_trades=256):
    def unknown():
        return RobustnessMetrics(base.observation_id, scenario.scenario_id, content_hash(scenario),
            'NOT_ESTABLISHED', None, None, None, None, None, 'ROBUSTNESS_NOT_ESTABLISHED'), None, None
    if scenario.close_at_end is not None:
        rules = replace(base.policy, policy_id='execution-stress', close_at_end=scenario.close_at_end,
                        max_trades=min(base.policy.max_trades, remaining_trades))
        observation = observe(candidate, split, base.dataset, warmup, rules, manifest_hash,
            catalog, journal, 'observation-'+str(index), scenario.scenario_id, policy.max_observation_bytes)
        metrics = observation.result.metrics
        if observation.result.status is not Status.COMPLETE or metrics is None:
            value, _, proof = unknown()
            return value, observation, proof
        fragile = base.result.metrics is not None and base.result.metrics.net.amount > 0 >= metrics.net.amount
        return RobustnessMetrics(base.observation_id, scenario.scenario_id, content_hash(scenario),
            'RERUN_V36', content_hash(observation), metrics.net, metrics.max_realized_drawdown,
            metrics.max_mark_drawdown, fragile, 'EXECUTION_POLICY_RERUN'), observation, None
    try:
        net, realized, mark, proof = _equivalence(base, scenario, catalog, journal)
        fragile = base.result.metrics.net.amount > 0 >= net.amount
        from hashlib import sha256
        return RobustnessMetrics(base.observation_id, scenario.scenario_id, content_hash(scenario),
            'PROVEN_SINGLE_TRADE_EQUIVALENCE', sha256(proof.encode('utf-8')).hexdigest(), net, realized,
            mark, fragile, 'CONDITIONAL_ECONOMIC_EQUIVALENCE'), None, proof
    except (ContractError, DecimalException):
        return unknown()
