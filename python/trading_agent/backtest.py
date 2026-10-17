"""Deterministic long-only research engine, never a broker execution engine.

Signals observe closes, entries use the following open; ambiguous bars resolve stop first.
Prices are midpoint OHLC. Round-trip spread/slippage are charged exactly once.
"""
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal, ROUND_FLOOR
import hashlib
import json
from .market import validate, ema


def D(x):
    return Decimal(str(x))


@dataclass(frozen=True)
class Config:
    capital: str = "100"
    risk: str = "0.0025"
    stop: str = "0.001"
    take_profit: str = "0.002"
    spread: str = "0.0002"
    slippage: str = "0.0001"
    gap_reserve: str = "0.0002"
    commission_fixed: str = "0"
    commission_unit: str = "0"
    minimum_quantity: str = "1"
    quantity_step: str = "1"
    margin_rate: str = "1"
    max_leverage: str = "1"
    daily_limit: str = "0.01"
    weekly_limit: str = "0.02"
    drawdown_limit: str = "0.05"
    signal: str = "ema20_50"


def run(candles, config=Config(), *, dataset_role="development"):
    validate(candles, candles[-1].closed_at if candles else datetime.now())
    if dataset_role not in ("development", "validation"):
        raise ValueError("Dataset role required")
    values = {k: D(v) for k, v in asdict(config).items() if k != "signal"}
    if any(not v.is_finite() for v in values.values()):
        raise ValueError("Nonfinite config")
    c = values
    if any(c[k] <= 0 for k in ("capital", "risk", "stop", "take_profit", "minimum_quantity", "quantity_step", "margin_rate", "max_leverage")):
        raise ValueError("Invalid positive config")
    if c["risk"] > D(".005") or c["margin_rate"] > 1 or any(not 0 < c[k] < 1 for k in ("daily_limit","weekly_limit","drawdown_limit")):
        raise ValueError("Risk limit invalid")
    if any(c[k] < 0 for k in ("spread","slippage","gap_reserve","commission_fixed","commission_unit")):
        raise ValueError("Invalid costs")
    if config.signal not in ("ema20_50", "always_long"):
        raise ValueError("Unsupported deterministic signal")
    raw = [{**asdict(b), "opened_at": b.opened_at.isoformat()} for b in candles]
    dataset_hash = hashlib.sha256(json.dumps(raw, sort_keys=True).encode()).hexdigest()
    run_hash = hashlib.sha256(json.dumps([dataset_hash, asdict(config), dataset_role, "engine-v1"], sort_keys=True).encode()).hexdigest()
    cash = c["capital"]
    peak = cash
    day_base = week_base = cash
    current_day = current_week = None
    position = None
    trades, decisions, equity_curve = [], [], []
    halted, streak, maximum_streak = False, 0, 0
    max_drawdown = D(0)
    closes = [b.close for b in candles]
    fast, slow = ema(closes, 20), ema(closes, 50)
    def signal(index):
        return config.signal == "always_long" or (index >= 50 and fast[index-1] <= slow[index-1] and fast[index] > slow[index])
    for i, b in enumerate(candles):
        opening, high, low, close = map(D, (b.open,b.high,b.low,b.close))
        mark_open = cash if position is None else cash+(opening-position["entry"])*position["quantity"]-position["cost"]
        day, week = b.opened_at.date(), b.opened_at.isocalendar()[:2]
        # Use previous close as period baseline, charging overnight gaps to the new period.
        previous_equity = D(equity_curve[-1]["equity"]) if equity_curve else cash
        if day != current_day:
            current_day, day_base = day, previous_equity
        if week != current_week:
            current_week, week_base = week, previous_equity
        if mark_open <= 0 or mark_open <= day_base*(1-c["daily_limit"]) or mark_open <= week_base*(1-c["weekly_limit"]) or mark_open <= peak*(1-c["drawdown_limit"]):
            halted = True
        if position is None and i > 0 and signal(i-1):
            risk_fraction = c["risk"] * (D(".5") if streak >= 3 or 1-cash/peak >= D(".02") else 1)
            room = min(cash-day_base*(1-c["daily_limit"]),cash-week_base*(1-c["weekly_limit"]),cash-peak*(1-c["drawdown_limit"]))
            budget = max(D(0),min(cash*risk_fraction,room))
            # Only previously observed spread is available when the next bar opens.
            spread = D(candles[i-1].spread) if candles[i-1].spread is not None else c["spread"]
            risk_unit = c["stop"]+spread+c["slippage"]+c["gap_reserve"]+c["commission_unit"]
            cap = min((budget-c["commission_fixed"])/risk_unit,
                      (cash-c["commission_fixed"])/(opening*c["margin_rate"]),cash*c["max_leverage"]/opening)
            qty = c["minimum_quantity"]+((cap-c["minimum_quantity"])/c["quantity_step"]).to_integral_value(rounding=ROUND_FLOOR)*c["quantity_step"]
            accepted = not halted and qty >= c["minimum_quantity"] and opening > c["stop"]
            decisions.append({"signal_at":candles[i-1].closed_at.isoformat(),"entry_at":b.opened_at.isoformat(),
                              "accepted":accepted,"reason":"HALTED" if halted else "OK" if accepted else "MINIMUM_OR_MARGIN","budget":str(budget)})
            if accepted:
                position={"entry":opening,"quantity":qty,"stop":opening-c["stop"],"tp":opening+c["take_profit"],
                          "cost":c["commission_fixed"]+qty*(spread+c["slippage"]+c["commission_unit"]),"at":b.opened_at.isoformat()}
        mark = cash
        if position:
            p = position
            stop_hit, tp_hit = low <= p["stop"], high >= p["tp"]
            # Conservative worst mark before exit. After a definite stop exit do not
            # treat a later bar low as continued exposure; gaps still execute worse.
            exit_price, reason = None, None
            if stop_hit:
                exit_price, reason = min(opening,p["stop"]), "STOP_AMBIGUOUS" if tp_hit else "STOP"
            elif tp_hit:
                exit_price, reason = p["tp"], "TAKE_PROFIT"
            elif i == len(candles)-1:
                exit_price, reason = close, "END_OF_DATA"
            worst_price = exit_price if stop_hit else low
            # OHLC does not reveal intrabar ordering. Use an explicitly conservative
            # high-before-low envelope, capped at target, even on ambiguous exits.
            possible_peak=cash+(min(high,p["tp"])-p["entry"])*p["quantity"]-p["cost"]
            peak=max(peak,possible_peak)
            worst_equity = cash+(worst_price-p["entry"])*p["quantity"]-p["cost"]
            max_drawdown = max(max_drawdown,1-worst_equity/peak)
            if worst_equity <= day_base*(1-c["daily_limit"]) or worst_equity <= week_base*(1-c["weekly_limit"]) or worst_equity <= peak*(1-c["drawdown_limit"]):
                halted=True
                if exit_price is None:
                    exit_price, reason = close,"RISK_HALT_CLOSE"  # bar-resolution simulation, no guaranteed limit price
            if exit_price is not None:
                net=(exit_price-p["entry"])*p["quantity"]-p["cost"]
                cash+=net
                streak=streak+1 if net < 0 else 0
                maximum_streak=max(maximum_streak,streak)
                trades.append({"entry_at":p["at"],"exit_at":b.closed_at.isoformat(),"entry":str(p["entry"]),
                               "exit":str(exit_price),"quantity":str(p["quantity"]),"cost":str(p["cost"]),
                               "net":str(net),"reason":reason,"ambiguous":stop_hit and tp_hit})
                position=None
                mark=cash
            else:
                mark=cash+(close-p["entry"])*p["quantity"]-p["cost"]
        peak=max(peak,mark)
        max_drawdown=max(max_drawdown,1-mark/peak)
        equity_curve.append({"at":b.closed_at.isoformat(),"equity":str(mark)})
    nets=[D(t["net"]) for t in trades]
    wins=sum((v for v in nets if v>0),D(0)); losses=-sum((v for v in nets if v<0),D(0))
    return {"engine_version":"engine-v1","run_hash":run_hash,"dataset_hash":dataset_hash,"dataset_role":dataset_role,
            "config":asdict(config),"trades":trades,"decisions":decisions,"equity_curve":equity_curve,
            "net_profit":str(cash-c["capital"]),"net_return":str(cash/c["capital"]-1),"max_drawdown":str(max_drawdown),
            "expectancy":str(sum(nets,D(0))/len(nets)) if nets else None,"profit_factor":str(wins/losses) if losses else None,
            "max_loss_streak":maximum_streak,"halted":halted,"drawdown_method":"conservative OHLC high-before-low envelope; not a tick-path measurement",
            "execution_model":"closed-signal-next-open; stop-first; mid+roundtrip-costs"}


def split_dataset(candles, boundary):
    development=[c for c in candles if c.closed_at <= boundary]
    validation=[c for c in candles if c.opened_at >= boundary]
    if not development or not validation:
        raise ValueError("Nonempty chronological partitions required")
    return development, validation


def compare(candles, configs, dataset_role="validation"):
    if not configs:
        raise ValueError("No candidates")
    comparable=("capital","risk","spread","slippage","gap_reserve","commission_fixed","commission_unit",
                "minimum_quantity","quantity_step","margin_rate","max_leverage","daily_limit","weekly_limit","drawdown_limit")
    if any(any(getattr(c,k)!=getattr(configs[0],k) for k in comparable) for c in configs):
        raise ValueError("Unequal cost/capital/risk assumptions")
    return [run(candles,c,dataset_role=dataset_role) for c in configs]
