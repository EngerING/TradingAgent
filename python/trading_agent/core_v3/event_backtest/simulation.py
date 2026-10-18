"""Single-position deterministic event fold. All inputs are verified synthetic records."""
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal, ROUND_FLOOR

from ..contracts import Money, Price, content_hash
from ..economic_contracts import Direction
from ..strategy_v34.signals import Candle, _matches
from .accounting import ExecutionMath, fraction
from .contracts import (BacktestEvent, BacktestMetrics, BacktestResult, EquitySnapshot, EventKind,
                        PositionState, Role, Side, SimulatedOrder, Status, TradeRecord)


class Simulation:
    def __init__(self, request, version, evidence, dataset, policy):
        self.request, self.evidence, self.data, self.policy = request, evidence, dataset, policy
        self.strategy = version.registration.strategy
        self.inputs = version.source.request.inputs
        self.context = self.inputs.context
        self.scenario = self.strategy.scenario
        self.model = ExecutionMath(self.context, self.scenario.quantity)
        portfolio = self.context.portfolio
        self.initial = min(portfolio.equity.amount, portfolio.allocation_available.amount)
        self.cash = self.initial
        self.events, self.orders, self.fills, self.trades, self.equity = [], [], [], [], []
        self.position, self.pending = None, None
        self.rejected, self.started = 0, 0
        self.realized_high, self.mark_high = self.initial, self.initial
        self.realized_dd, self.mark_dd, self.peak = Decimal(0), Decimal(0), Decimal(0)
        self.losses = Decimal(0)

    def event(self, index, at, kind, reason, reference=None):
        event = BacktestEvent(len(self.events)+1, index, at, kind, reason, reference)
        self.events.append(event)
        return event.sequence

    def order(self, role, index, at, sequence, reason):
        long = self.scenario.direction is Direction.LONG
        side = Side.BUY if (long == (role is Role.ENTRY)) else Side.SELL
        order = SimulatedOrder('order-'+str(len(self.orders)+1), role, side, self.scenario.quantity,
                               index, sequence, at, reason)
        self.orders.append(order)
        return order

    def _notional(self, price):
        return self.model.money(price.amount*self.scenario.quantity.amount*self.model.instrument.multiplier).amount

    def _cash_changed(self):
        self.realized_high = max(self.realized_high, self.cash)
        self.realized_dd = max(self.realized_dd, self.realized_high-self.cash)

    def _entry_reason(self, fill):
        scenario, model = self.scenario, self.model
        sign = 1 if scenario.direction is Direction.LONG else -1
        if not (scenario.stop.amount < fill.price.amount < scenario.target.amount if sign == 1 else
                scenario.target.amount < fill.price.amount < scenario.stop.amount):
            return 'ENTRY_GAP_GEOMETRY'
        notional = self._notional(fill.price)
        portfolio, policy = self.context.portfolio, self.inputs.policy
        if notional > portfolio.remaining_exposure.amount:
            return 'EXPOSURE_LIMIT'
        financing = model.financing(fill.at, fill.at+timedelta(hours=scenario.horizon_hours)).amount
        fees = fill.commission.amount + model.commission(Role.EXIT).amount + financing
        margin = notional*self.context.margin.initial_fraction + fees
        if margin > min(self.cash, portfolio.free_margin.amount + self.cash-self.initial):
            return 'INITIAL_MARGIN_LIMIT'
        exit_side = Side.SELL if sign == 1 else Side.BUY
        stop_price = model.execution_price(scenario.stop, exit_side)[0]
        risk = model.money(max(Decimal(0), sign*(fill.price.amount-stop_price.amount))
                           *scenario.quantity.amount*model.instrument.multiplier).amount + fees
        for stress in policy.stresses:
            extra = stress.adverse_gap.money.amount + 2*stress.extra_slippage_per_side.money.amount
            risk = max(risk, model.money(max(Decimal(0), sign*(fill.price.amount-stop_price.amount)+extra)
                                        *scenario.quantity.amount*model.instrument.multiplier).amount+fees)
        if risk > min(portfolio.remaining_risk.amount-self.losses, policy.max_loss.amount):
            return 'RISK_LIMIT'
        if self.cash <= 0:
            return 'CAPITAL_EXHAUSTED'
        return None

    def enter(self, order, index, bar):
        fill = self.model.fill(order, index, bar.opened_at, bar.open)
        reason = self._entry_reason(fill)
        if reason is not None:
            self.rejected += 1
            self.event(index, bar.opened_at, EventKind.REJECTION, reason, order.order_id)
            return
        self.started += 1
        self.fills.append(fill)
        self.peak = max(self.peak, self._notional(fill.price))
        self.cash -= fill.commission.amount
        self._cash_changed()
        self.event(index, fill.at, EventKind.FILL, 'ENTRY', fill.fill_id)
        self.position = PositionState('trade-'+str(self.started), self.scenario.direction, fill,
            self.scenario.stop, self.scenario.target, fill.at+timedelta(hours=self.scenario.horizon_hours),
            self.model.financing(fill.at, fill.at))

    def close(self, index, at, mid, reason, order=None):
        position = self.position
        if order is None:
            # Standing bracket/horizon/end-policy decided before this execution event.
            sequence = next(e.sequence for e in self.events if e.kind is EventKind.FILL
                            and e.reference_id == position.entry.fill_id)
            order = self.order(Role.EXIT, position.entry.bar_index, position.entry.at, sequence, reason)
            self.event(index, at, EventKind.ORDER, 'PREDECLARED_EXIT', order.order_id)
        fill = self.model.fill(order, index, at, mid)
        self.peak = max(self.peak, self._notional(fill.price))
        financing = self.model.financing(position.entry.at, at)
        costs = self.model.costs(position.entry, fill, financing)
        gross = self.model.gross(position.entry, fill)
        net = gross.add(Money(costs.total.amount.copy_negate(), gross.currency))
        notional = self._notional(position.entry.price)
        trade = TradeRecord(position.trade_id, position.direction, position.entry, fill, reason, gross, costs, net,
                            fraction(net.amount, notional, ROUND_FLOOR))
        self.trades.append(trade)
        self.fills.append(fill)
        self.cash += net.amount + position.entry.commission.amount  # opening fee was already charged.
        self._cash_changed()
        self.losses += max(Decimal(0), -net.amount)
        self.event(index, at, EventKind.FILL, reason, fill.fill_id)
        self.position, self.pending = None, None

    def _gap_exit(self, index, bar):
        if self.position is None:
            return
        long, price = self.scenario.direction is Direction.LONG, bar.open.amount
        stop, target = self.scenario.stop.amount, self.scenario.target.amount
        if (price <= stop if long else price >= stop):
            self.close(index, bar.opened_at, bar.open, 'STOP_GAP')
        elif (price >= target if long else price <= target):
            # Trigger-market target: cap the favorable gap at the predeclared mid threshold.
            self.close(index, bar.opened_at, self.scenario.target, 'TARGET_GAP')

    def _intrabar_exit(self, index, bar):
        if self.position is None:
            return
        long = self.scenario.direction is Direction.LONG
        stop_hit = bar.low.amount <= self.scenario.stop.amount if long else bar.high.amount >= self.scenario.stop.amount
        target_hit = bar.high.amount >= self.scenario.target.amount if long else bar.low.amount <= self.scenario.target.amount
        if stop_hit:
            if target_hit:
                self.event(index, bar.closed_at, EventKind.SIGNAL, 'STOP_FIRST_AMBIGUITY', self.position.trade_id)
            self.close(index, bar.closed_at, self.scenario.stop, 'STOP')
        elif target_hit:
            self.close(index, bar.closed_at, self.scenario.target, 'TARGET')

    def valuation(self, index, bar):
        mark, notional, maintenance = self.cash, Decimal(0), Decimal(0)
        if self.position is not None:
            position = self.position
            entry = position.entry
            financing = self.model.financing(entry.at, bar.closed_at)
            self.position = replace(position, financing_accrued=financing)
            side = Side.SELL if entry.side is Side.BUY else Side.BUY
            price = self.model.execution_price(bar.close, side)[0]
            sign = 1 if entry.side is Side.BUY else -1
            pnl = self.model.money(sign*(price.amount-entry.price.amount)*entry.quantity.amount*self.model.instrument.multiplier)
            mark += pnl.amount - self.model.commission(Role.EXIT).amount - financing.amount
            notional = self._notional(bar.close)
            maintenance = notional*self.context.margin.maintenance_fraction
        self.realized_high, self.mark_high = max(self.realized_high, self.cash), max(self.mark_high, mark)
        self.realized_dd = max(self.realized_dd, self.realized_high-self.cash)
        self.mark_dd = max(self.mark_dd, self.mark_high-mark)
        self.peak = max(self.peak, notional)
        money = self.model.account
        self.equity.append(EquitySnapshot(index, bar.closed_at, money(self.cash), money(mark), money(notional),
            money(maintenance), money(self.realized_high-self.cash), money(self.mark_high-mark)))
        self.event(index, bar.closed_at, EventKind.VALUATION, 'CLOSE_MARK')
        return mark, maintenance

    def build_result(self, status, reason):
        money = self.model.account
        gross = sum((t.gross.amount for t in self.trades), Decimal(0))
        costs = sum((t.costs.total.amount for t in self.trades), Decimal(0))
        final_mark = self.equity[-1].mark_equity if self.equity else money(self.cash)
        metrics = BacktestMetrics(len(self.trades), sum(t.net.amount > 0 for t in self.trades),
            sum(t.net.amount < 0 for t in self.trades), sum(t.net.amount == 0 for t in self.trades), self.rejected,
            money(gross), money(costs), money(gross-costs), money(self.initial), money(self.cash), final_mark,
            money(self.realized_dd), money(self.mark_dd), money(self.peak))
        return BacktestResult(content_hash(self.request), status, reason, self.evidence, tuple(self.events),
            tuple(self.orders), tuple(self.fills), tuple(self.trades), tuple(self.equity), metrics, self.position,
            () if self.pending is None else (self.pending,))

    def execute(self):
        bars, strategy = self.data.bars, self.strategy
        warmup = max(r.required_bars for r in strategy.entry_rules+strategy.exit_rules)
        if len(bars) < warmup:
            return self.build_result(Status.INCONCLUSIVE, 'WARMUP_COVERAGE_REQUIRED')
        history = []
        for index, bar in enumerate(bars):
            # Reserve enough space for a whole atomic bar; never truncate a cash-changing event.
            if len(self.events)+12 > self.policy.max_events:
                return self.build_result(Status.INCONCLUSIVE, 'EVENT_LIMIT')
            if bar.available_at != bar.closed_at:
                return self.build_result(Status.INCONCLUSIVE, 'DELAYED_BAR_UNRESOLVED')
            self.event(index, bar.opened_at, EventKind.OPEN, 'SYNTHETIC_OPEN')
            self._gap_exit(index, bar)
            if self.position is not None and bar.opened_at >= self.position.deadline:
                self.close(index, bar.opened_at, bar.open, 'HORIZON')
            if self.pending is not None:
                pending, self.pending = self.pending, None
                if pending.role is Role.ENTRY:
                    self.enter(pending, index, bar)
                elif self.position is not None:
                    self.close(index, bar.opened_at, bar.open, pending.reason, pending)
            self._intrabar_exit(index, bar)
            history.append(Candle(bar.closed_at, bar.available_at, bar.open, bar.high, bar.low, bar.close))
            self.event(index, bar.closed_at, EventKind.CLOSE, 'SYNTHETIC_CLOSE')
            entry_met = exit_met = False
            if len(history) >= warmup:
                entry_met = all(_matches(rule, history) for rule in strategy.entry_rules)
                exit_met = all(_matches(rule, history) for rule in strategy.exit_rules)
                if entry_met and exit_met:
                    self.valuation(index, bar)
                    return self.build_result(Status.INCONCLUSIVE, 'CONFLICTING_RULES')
            if index == len(bars)-1 and self.policy.close_at_end and self.position is not None:
                self.close(index, bar.closed_at, bar.close, 'WINDOW_END')
            mark, maintenance = self.valuation(index, bar)
            if self.position is not None:
                reason = 'MAINTENANCE_MARGIN' if mark < maintenance else 'EXIT_RULE' if exit_met else None
                if reason is not None and not (index == len(bars)-1 and self.policy.close_at_end):
                    sequence = self.event(index, bar.closed_at, EventKind.SIGNAL, reason, self.position.trade_id)
                    self.pending = self.order(Role.EXIT, index, bar.closed_at, sequence, reason)
                    self.event(index, bar.closed_at, EventKind.ORDER, reason, self.pending.order_id)
            elif entry_met:
                if index == len(bars)-1 and self.policy.close_at_end:
                    self.event(index, bar.closed_at, EventKind.SIGNAL, 'ENTRY_RULE')
                    self.rejected += 1
                    self.event(index, bar.closed_at, EventKind.REJECTION, 'ENTRY_AFTER_WINDOW')
                    continue
                if self.started >= self.policy.max_trades:
                    return self.build_result(Status.INCONCLUSIVE, 'TRADE_LIMIT')
                sequence = self.event(index, bar.closed_at, EventKind.SIGNAL, 'ENTRY_RULE')
                self.pending = self.order(Role.ENTRY, index, bar.closed_at, sequence, 'ENTRY_RULE')
                self.event(index, bar.closed_at, EventKind.ORDER, 'ENTRY_RULE', self.pending.order_id)
        if self.position is not None:
            return self.build_result(Status.INCONCLUSIVE, 'OPEN_POSITION_COVERAGE')
        if self.pending is not None:
            return self.build_result(Status.INCONCLUSIVE, 'PENDING_ORDER_COVERAGE')
        return self.build_result(Status.COMPLETE, 'SIMULATED_WINDOW_COMPLETE')
