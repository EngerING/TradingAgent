"""Closed immutable simulation wire; audited financial primitives remain unchanged."""
from dataclasses import dataclass, fields
from datetime import datetime, timedelta
from decimal import Context, Decimal, localcontext
from enum import Enum
from typing import get_args, get_origin

from ..contracts import Money, Price, Quantity, SourceKind, content_hash, decimal_text, identifier, require, utc
from ..economic_contracts import EconomicRecord, Direction, _decode, _hash, _typed_value
from ..research_contracts import InstrumentIdentity
from ..strategy_catalog.contracts import CatalogRef
from ..strategy_v34.contracts import Timeframe


ENGINE_VERSION = 'CORE_V36_EVENT_V1'


class Record(EconomicRecord):
    """Dedicated collection boundary; no change to V3.2's 32-element decoder."""
    __slots__ = ()

    def check_types(self):
        for field in fields(self):
            value = getattr(self, field.name)
            if get_origin(field.type) is tuple:
                require(type(value) is tuple and len(value) <= 1024, 'BACKTEST_COLLECTION_LIMIT')
                for item in value:
                    _typed_value(item, get_args(field.type)[0])
            else:
                _typed_value(value, field.type)

    @classmethod
    def from_dict(cls, data):
        values = cls.payload(data)
        decoded = {}
        for field in fields(cls):
            value = values[field.name]
            if get_origin(field.type) is tuple:
                require(type(value) is list and len(value) <= 1024, 'BACKTEST_COLLECTION_LIMIT')
                decoded[field.name] = tuple(_decode(v, get_args(field.type)[0]) for v in value)
            else:
                decoded[field.name] = _decode(value, field.type)
        return cls(**decoded)


def _nonnegative(*values):
    require(len({v.currency for v in values}) <= 1 and all(v.amount >= 0 for v in values), 'BACKTEST_COST_INVALID')


def _authority(value):
    require(value.scope == 'SYNTHETIC_EVENT_RESEARCH_ONLY' and value.trading_decision == 'NO_TRADE'
            and all(v is False for v in (value.execution_authority, value.paper_execution_eligible,
                                        value.live_enabled, value.statistically_validated)), 'BACKTEST_AUTHORITY_FORBIDDEN')


@dataclass(frozen=True, slots=True)
class SyntheticBar(Record):
    SCHEMA = 'trading.core_v3.backtest.bar'
    bar_id: str
    opened_at: datetime
    closed_at: datetime
    available_at: datetime
    open: Price
    high: Price
    low: Price
    close: Price

    def __post_init__(self):
        self.check_types()
        identifier(self.bar_id)
        for name in ('opened_at', 'closed_at', 'available_at'):
            object.__setattr__(self, name, utc(getattr(self, name)))
        require(self.opened_at < self.closed_at <= self.available_at, 'BACKTEST_BAR_TIME_INVALID')
        prices = self.open, self.high, self.low, self.close
        require(len({(p.currency, p.per_unit) for p in prices}) == 1, 'BACKTEST_PRICE_UNITS')
        require(self.low.amount <= min(p.amount for p in prices)
                and self.high.amount >= max(p.amount for p in prices), 'BACKTEST_OHLC_INVALID')


@dataclass(frozen=True, slots=True)
class SyntheticDataset(Record):
    SCHEMA = 'trading.core_v3.backtest.dataset'
    dataset_id: str
    instrument: InstrumentIdentity
    timeframe: Timeframe
    bars: tuple[SyntheticBar, ...]
    source_kind: SourceKind = SourceKind.SYNTHETIC

    def __post_init__(self):
        self.check_types()
        identifier(self.dataset_id)
        require(self.source_kind is SourceKind.SYNTHETIC, 'SYNTHETIC_DATASET_REQUIRED')
        require(1 <= len(self.bars) <= 128 and len({b.bar_id for b in self.bars}) == len(self.bars), 'BACKTEST_BAR_LIMIT')
        previous = None
        for bar in self.bars:
            end = bar.closed_at
            require(bar.closed_at-bar.opened_at == timedelta(seconds=self.timeframe.seconds)
                    and end.second == end.microsecond == 0
                    and (self.timeframe is not Timeframe.M5 or end.minute % 5 == 0)
                    and (self.timeframe is not Timeframe.H1 or end.minute == 0), 'BACKTEST_ALIGNMENT_INVALID')
            if previous is not None:
                require(bar.opened_at == previous.closed_at and bar.available_at >= previous.available_at,
                        'BACKTEST_SEQUENCE_INVALID')
            previous = bar


@dataclass(frozen=True, slots=True)
class BacktestPolicy(Record):
    SCHEMA = 'trading.core_v3.backtest.policy'
    policy_id: str
    close_at_end: bool
    max_bars: int
    max_events: int
    max_trades: int
    max_duration_hours: int
    max_result_bytes: int
    intrabar: str = 'STOP_FIRST'
    entry_model: str = 'NEXT_OPEN_ABSOLUTE_BRACKET'
    spread_model: str = 'CONSTANT_MID_HALF_SPREAD'
    engine_version: str = ENGINE_VERSION

    def __post_init__(self):
        self.check_types()
        identifier(self.policy_id)
        require(1 <= self.max_bars <= 128 and 1 <= self.max_events <= 1024 and 1 <= self.max_trades <= 16
                and 1 <= self.max_duration_hours <= 720 and 4096 <= self.max_result_bytes <= 131072, 'BACKTEST_POLICY_LIMIT')
        require(self.intrabar == 'STOP_FIRST' and self.entry_model == 'NEXT_OPEN_ABSOLUTE_BRACKET'
                and self.spread_model == 'CONSTANT_MID_HALF_SPREAD' and self.engine_version == ENGINE_VERSION,
                'BACKTEST_MODEL_UNSUPPORTED')


@dataclass(frozen=True, slots=True)
class BacktestRequest(Record):
    SCHEMA = 'trading.core_v3.backtest.request'
    request_id: str
    catalog_ref: CatalogRef
    validation_operation_id: str
    research_cutoff: datetime
    catalog_sequence: int
    catalog_sha256: str
    research_request_sha256: str
    scenario_sha256: str
    economic_sha256: str
    dataset_sha256: str
    policy_sha256: str

    def __post_init__(self):
        self.check_types()
        identifier(self.request_id)
        identifier(self.validation_operation_id)
        object.__setattr__(self, 'research_cutoff', utc(self.research_cutoff))
        require(1 <= self.catalog_sequence <= 2049, 'BACKTEST_CATALOG_SEQUENCE')
        for value in (self.catalog_sha256, self.research_request_sha256, self.scenario_sha256,
                      self.economic_sha256, self.dataset_sha256, self.policy_sha256):
            _hash(value)


class Side(str, Enum):
    BUY = 'BUY'
    SELL = 'SELL'


class Role(str, Enum):
    ENTRY = 'ENTRY'
    EXIT = 'EXIT'


class Status(str, Enum):
    COMPLETE = 'COMPLETE'
    INCONCLUSIVE = 'INCONCLUSIVE'
    REJECTED = 'REJECTED'


class EventKind(str, Enum):
    OPEN = 'OPEN'
    SIGNAL = 'SIGNAL'
    ORDER = 'ORDER'
    FILL = 'FILL'
    REJECTION = 'REJECTION'
    CLOSE = 'CLOSE'
    VALUATION = 'VALUATION'


@dataclass(frozen=True, slots=True)
class BacktestEvent(Record):
    SCHEMA = 'trading.core_v3.backtest.event'
    sequence: int
    bar_index: int
    at: datetime
    kind: EventKind
    reason: str
    reference_id: str | None

    def __post_init__(self):
        self.check_types()
        require(1 <= self.sequence <= 1024 and 0 <= self.bar_index < 128, 'BACKTEST_EVENT_INDEX')
        object.__setattr__(self, 'at', utc(self.at))
        identifier(self.reason)
        if self.reference_id is not None:
            identifier(self.reference_id)


@dataclass(frozen=True, slots=True)
class SimulatedOrder(Record):
    SCHEMA = 'trading.core_v3.backtest.order'
    order_id: str
    role: Role
    side: Side
    quantity: Quantity
    signal_bar: int
    signal_sequence: int
    decided_at: datetime
    reason: str

    def __post_init__(self):
        self.check_types()
        identifier(self.order_id)
        identifier(self.reason)
        require(0 <= self.signal_bar < 128 and 1 <= self.signal_sequence <= 1024, 'BACKTEST_ORDER_INDEX')
        object.__setattr__(self, 'decided_at', utc(self.decided_at))


@dataclass(frozen=True, slots=True)
class SimulatedFill(Record):
    SCHEMA = 'trading.core_v3.backtest.fill'
    fill_id: str
    order_id: str
    role: Role
    side: Side
    quantity: Quantity
    bar_index: int
    at: datetime
    mid_price: Price
    price: Price
    commission: Money
    spread_cost: Money
    slippage_cost: Money
    rounding_cost: Money

    def __post_init__(self):
        self.check_types()
        identifier(self.fill_id)
        identifier(self.order_id)
        require(0 <= self.bar_index < 128, 'BACKTEST_FILL_INDEX')
        object.__setattr__(self, 'at', utc(self.at))
        require((self.mid_price.currency, self.mid_price.per_unit) == (self.price.currency, self.price.per_unit),
                'BACKTEST_FILL_UNITS')
        require(self.quantity.unit == self.price.per_unit
                and (self.price.amount >= self.mid_price.amount if self.side is Side.BUY
                     else self.price.amount <= self.mid_price.amount), 'BACKTEST_FILL_ADVERSE_PRICE')
        _nonnegative(self.commission, self.spread_cost, self.slippage_cost, self.rounding_cost)


@dataclass(frozen=True, slots=True)
class CostBreakdown(Record):
    SCHEMA = 'trading.core_v3.backtest.costs'
    opening_commission: Money
    closing_commission: Money
    spread: Money
    slippage: Money
    rounding: Money
    financing: Money
    total: Money

    def __post_init__(self):
        self.check_types()
        values = (self.opening_commission, self.closing_commission, self.spread, self.slippage, self.rounding, self.financing)
        _nonnegative(*values, self.total)
        require(self.total == Money(Decimal(0), self.total.currency).add(self.opening_commission)
                .add(self.closing_commission).add(self.spread).add(self.slippage).add(self.rounding).add(self.financing),
                'BACKTEST_COST_SUM')


@dataclass(frozen=True, slots=True)
class PositionState(Record):
    SCHEMA = 'trading.core_v3.backtest.position'
    trade_id: str
    direction: Direction
    entry: SimulatedFill
    stop: Price
    target: Price
    deadline: datetime
    financing_accrued: Money

    def __post_init__(self):
        self.check_types()
        identifier(self.trade_id)
        object.__setattr__(self, 'deadline', utc(self.deadline))
        require(self.entry.role is Role.ENTRY and self.entry.at < self.deadline, 'BACKTEST_POSITION_INVALID')
        require(self.entry.side is (Side.BUY if self.direction is Direction.LONG else Side.SELL)
                and (self.stop.currency, self.stop.per_unit) == (self.target.currency, self.target.per_unit)
                == (self.entry.price.currency, self.entry.price.per_unit), 'BACKTEST_POSITION_UNITS')
        require(self.stop.amount < self.entry.price.amount < self.target.amount if self.direction is Direction.LONG else
                self.target.amount < self.entry.price.amount < self.stop.amount, 'BACKTEST_POSITION_GEOMETRY')
        _nonnegative(self.financing_accrued)


@dataclass(frozen=True, slots=True)
class TradeRecord(Record):
    SCHEMA = 'trading.core_v3.backtest.trade'
    trade_id: str
    direction: Direction
    entry: SimulatedFill
    exit: SimulatedFill
    reason: str
    gross: Money
    costs: CostBreakdown
    net: Money
    return_fraction: Decimal

    def __post_init__(self):
        self.check_types()
        identifier(self.trade_id)
        identifier(self.reason)
        require(self.entry.role is Role.ENTRY and self.exit.role is Role.EXIT
                and self.exit.at >= self.entry.at and self.entry.quantity == self.exit.quantity, 'BACKTEST_TRADE_INVALID')
        require(self.entry.side is (Side.BUY if self.direction is Direction.LONG else Side.SELL)
                and self.entry.side is not self.exit.side
                and (self.entry.price.currency, self.entry.price.per_unit) == (self.exit.price.currency, self.exit.price.per_unit),
                'BACKTEST_TRADE_TERMS')
        require(self.gross.currency == self.costs.total.currency == self.net.currency
                and self.gross.add(Money(self.costs.total.amount.copy_negate(), self.net.currency)) == self.net, 'BACKTEST_NET_SUM')
        decimal_text(self.return_fraction)


@dataclass(frozen=True, slots=True)
class EquitySnapshot(Record):
    SCHEMA = 'trading.core_v3.backtest.equity'
    bar_index: int
    at: datetime
    realized_equity: Money
    mark_equity: Money
    notional: Money
    maintenance_margin: Money
    realized_drawdown: Money
    mark_drawdown: Money

    def __post_init__(self):
        self.check_types()
        require(0 <= self.bar_index < 128, 'BACKTEST_EQUITY_INDEX')
        object.__setattr__(self, 'at', utc(self.at))
        _nonnegative(self.notional, self.maintenance_margin, self.realized_drawdown, self.mark_drawdown)
        require(self.realized_equity.currency == self.mark_equity.currency == self.notional.currency, 'BACKTEST_EQUITY_UNITS')


@dataclass(frozen=True, slots=True)
class BacktestMetrics(Record):
    SCHEMA = 'trading.core_v3.backtest.metrics'
    closed_trades: int
    winners: int
    losers: int
    breakeven: int
    rejected_entries: int
    gross: Money
    costs: Money
    net: Money
    initial_capital: Money
    final_realized_capital: Money
    final_mark_capital: Money
    max_realized_drawdown: Money
    max_mark_drawdown: Money
    peak_exposure: Money

    def __post_init__(self):
        self.check_types()
        require(0 <= self.closed_trades <= 16 and self.winners + self.losers + self.breakeven == self.closed_trades
                and min(self.winners, self.losers, self.breakeven, self.rejected_entries) >= 0, 'BACKTEST_METRIC_COUNTS')
        require(self.gross.add(Money(self.costs.amount.copy_negate(), self.costs.currency)) == self.net, 'BACKTEST_METRIC_SUM')
        money_fields = [getattr(self, f.name) for f in fields(self) if f.type is Money]
        require(len({m.currency for m in money_fields}) == 1 and self.initial_capital.amount > 0, 'BACKTEST_METRIC_UNITS')
        _nonnegative(self.costs, self.max_realized_drawdown, self.max_mark_drawdown, self.peak_exposure)


@dataclass(frozen=True, slots=True)
class BacktestEvidence(Record):
    SCHEMA = 'trading.core_v3.backtest.evidence'
    request: BacktestRequest
    strategy_sha256: str
    instrument: InstrumentIdentity
    timeframe: Timeframe
    source_prefix_sequence: int
    source_prefix_sha256: str
    engine_version: str = ENGINE_VERSION
    scope: str = 'SYNTHETIC_EVENT_RESEARCH_ONLY'
    trading_decision: str = 'NO_TRADE'
    execution_authority: bool = False
    paper_execution_eligible: bool = False
    live_enabled: bool = False
    statistically_validated: bool = False

    def __post_init__(self):
        self.check_types()
        _hash(self.strategy_sha256)
        _hash(self.source_prefix_sha256)
        require(1 <= self.source_prefix_sequence <= 2049 and self.engine_version == ENGINE_VERSION, 'BACKTEST_EVIDENCE_INVALID')
        _authority(self)


@dataclass(frozen=True, slots=True)
class BacktestResult(Record):
    SCHEMA = 'trading.core_v3.backtest.result'
    request_sha256: str
    status: Status
    reason: str
    evidence: BacktestEvidence | None
    events: tuple[BacktestEvent, ...]
    orders: tuple[SimulatedOrder, ...]
    fills: tuple[SimulatedFill, ...]
    trades: tuple[TradeRecord, ...]
    equity: tuple[EquitySnapshot, ...]
    metrics: BacktestMetrics | None
    open_position: PositionState | None
    pending_orders: tuple[SimulatedOrder, ...]
    scope: str = 'SYNTHETIC_EVENT_RESEARCH_ONLY'
    trading_decision: str = 'NO_TRADE'
    execution_authority: bool = False
    paper_execution_eligible: bool = False
    live_enabled: bool = False
    statistically_validated: bool = False

    def __post_init__(self):
        self.check_types()
        _hash(self.request_sha256)
        identifier(self.reason)
        _authority(self)
        require(len(self.trades) <= 16 and len(self.equity) <= 128, 'BACKTEST_RESULT_LIMIT')
        require(tuple(e.sequence for e in self.events) == tuple(range(1, len(self.events)+1)), 'BACKTEST_EVENT_SEQUENCE')
        for values, name in ((self.orders, 'order_id'), (self.fills, 'fill_id'), (self.trades, 'trade_id')):
            require(len({getattr(v, name) for v in values}) == len(values), 'BACKTEST_DUPLICATE_EVENT')
        require(self.status is not Status.COMPLETE or (self.open_position is None and not self.pending_orders
                and self.metrics is not None), 'BACKTEST_COMPLETION_INVALID')
        require(self.evidence is None or content_hash(self.evidence.request) == self.request_sha256, 'BACKTEST_EVIDENCE_MISMATCH')
        require(all(a.at <= b.at for a, b in zip(self.events, self.events[1:])), 'BACKTEST_EVENT_TIME')
        orders = {order.order_id: order for order in self.orders}
        fills = {fill.fill_id: fill for fill in self.fills}
        fill_events = {e.reference_id: e for e in self.events if e.kind is EventKind.FILL}
        require(sum(e.kind is EventKind.FILL for e in self.events) == len(self.fills)
                and len(fill_events) == len(self.fills) and set(fill_events) == set(fills), 'BACKTEST_FILL_EVENTS')
        order_events = [e.reference_id for e in self.events if e.kind is EventKind.ORDER]
        require(len(order_events) == len(self.orders) and set(order_events) == set(orders), 'BACKTEST_ORDER_EVENTS')
        require(len({f.order_id for f in self.fills}) == len(self.fills), 'BACKTEST_DUPLICATE_ORDER_FILL')
        for order in self.orders:
            require(order.signal_sequence <= len(self.events), 'BACKTEST_SIGNAL_REFERENCE')
            cause = self.events[order.signal_sequence-1]
            require(cause.kind in (EventKind.SIGNAL, EventKind.FILL) and cause.at == order.decided_at
                    and cause.bar_index == order.signal_bar, 'BACKTEST_SIGNAL_REFERENCE')
        for fill in self.fills:
            require(fill.order_id in orders, 'BACKTEST_FILL_ORDER_REFERENCE')
            order, event = orders[fill.order_id], fill_events[fill.fill_id]
            require((order.role, order.side, order.quantity) == (fill.role, fill.side, fill.quantity)
                    and event.bar_index == fill.bar_index and event.at == fill.at and event.sequence > order.signal_sequence
                    and fill.at >= order.decided_at and (fill.bar_index > order.signal_bar if fill.role is Role.ENTRY
                    else fill.bar_index >= order.signal_bar), 'BACKTEST_FILL_CAUSALITY')
        for trade in self.trades:
            require(fills.get(trade.entry.fill_id) == trade.entry and fills.get(trade.exit.fill_id) == trade.exit,
                    'BACKTEST_TRADE_FILL_REFERENCE')
        used_fills = [fill.fill_id for trade in self.trades for fill in (trade.entry, trade.exit)]
        if self.open_position is not None:
            used_fills.append(self.open_position.entry.fill_id)
        require(len(used_fills) == len(set(used_fills)) and set(used_fills) == set(fills), 'BACKTEST_FILL_ACCOUNTING')
        require(len(self.fills) == 2*len(self.trades) + int(self.open_position is not None), 'BACKTEST_POSITION_FILL_COUNT')
        if self.open_position is not None:
            require(fills.get(self.open_position.entry.fill_id) == self.open_position.entry, 'BACKTEST_OPEN_FILL_REFERENCE')
        for pending in self.pending_orders:
            require(orders.get(pending.order_id) == pending and all(f.order_id != pending.order_id for f in self.fills),
                    'BACKTEST_PENDING_ORDER_REFERENCE')
        if self.metrics is not None:
            require(self.evidence is not None, 'BACKTEST_EVIDENCE_REQUIRED')
            metrics = self.metrics
            with localcontext(Context(prec=160)):
                require(metrics.closed_trades == len(self.trades)
                        and metrics.winners == sum(t.net.amount > 0 for t in self.trades)
                        and metrics.losers == sum(t.net.amount < 0 for t in self.trades)
                        and metrics.gross.amount == sum((t.gross.amount for t in self.trades), Decimal(0))
                        and metrics.costs.amount == sum((t.costs.total.amount for t in self.trades), Decimal(0)),
                        'BACKTEST_AGGREGATE_MISMATCH')
                opening_fee = Decimal(0) if self.open_position is None else self.open_position.entry.commission.amount
                require(metrics.final_realized_capital.amount == metrics.initial_capital.amount+metrics.net.amount-opening_fee,
                        'BACKTEST_CAPITAL_RECONCILIATION')
                require(metrics.final_mark_capital == (self.equity[-1].mark_equity if self.equity
                        else metrics.final_realized_capital), 'BACKTEST_MARK_RECONCILIATION')
