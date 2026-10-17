from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import isfinite, log, sqrt
from statistics import pstdev


@dataclass(frozen=True)
class Candle:
    opened_at: datetime
    minutes: int
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None
    spread: float | None = None

    @property
    def closed_at(self):
        return self.opened_at + timedelta(minutes=self.minutes)


def validate(candles, as_of, allow_session_gaps=False):
    if not candles or as_of.tzinfo is None:
        raise ValueError("Empty series or timezone missing")
    previous = None
    for c in candles:
        if c.minutes not in (15, 60, 240) or c.opened_at.tzinfo is None:
            raise ValueError("Unsupported timeframe or timezone missing")
        if c.opened_at.timestamp() % (c.minutes * 60) != 0:
            raise ValueError("Misaligned bar")
        if any(not isfinite(v) or v <= 0 for v in (c.open, c.high, c.low, c.close)):
            raise ValueError("Invalid price")
        if c.high < max(c.open, c.close, c.low) or c.low > min(c.open, c.close, c.high):
            raise ValueError("Inconsistent OHLC")
        for value in (c.volume, c.spread):
            if value is not None and (not isfinite(value) or value < 0):
                raise ValueError("Invalid volume/spread")
        if c.closed_at > as_of:
            raise ValueError("Unclosed candle")
        if previous:
            if c.minutes != previous.minutes or c.opened_at < previous.closed_at:
                raise ValueError("Duplicate/out of order/inconsistent series")
            if not allow_session_gaps and c.opened_at != previous.closed_at:
                raise ValueError("Missing candle: validate exchange calendar before permitting a gap")
        previous = c


def ema(values, period):
    if period < 1:
        raise ValueError("Invalid period")
    out = [None] * len(values)
    if len(values) < period:
        return out
    out[period-1] = sum(values[:period]) / period
    alpha = 2 / (period+1)
    for i in range(period, len(values)):
        out[i] = alpha * values[i] + (1-alpha) * out[i-1]
    return out


def rsi(values, period=14):
    out = [None] * len(values)
    if len(values) <= period:
        return out
    deltas = [b-a for a, b in zip(values, values[1:])]
    gain = sum(max(x, 0) for x in deltas[:period])/period
    loss = sum(max(-x, 0) for x in deltas[:period])/period
    def score(g, loss):
        return 50.0 if g == loss == 0 else (100.0 if loss == 0 else 100-100/(1+g/loss))
    out[period] = score(gain, loss)
    for i in range(period+1, len(values)):
        d = deltas[i-1]
        gain = (gain*(period-1)+max(d, 0))/period
        loss = (loss*(period-1)+max(-d, 0))/period
        out[i] = score(gain, loss)
    return out


def atr(candles, period=14):
    tr = [c.high-c.low if i == 0 else max(c.high-c.low, abs(c.high-candles[i-1].close),
          abs(c.low-candles[i-1].close)) for i, c in enumerate(candles)]
    out = [None]*len(tr)
    if len(tr) >= period:
        out[period-1] = sum(tr[:period])/period
        for i in range(period, len(tr)):
            out[i] = (out[i-1]*(period-1)+tr[i])/period
    return out


def analyze(candles, as_of):
    validate(candles, as_of)
    if len(candles) < 51:
        raise ValueError("At least 51 closed bars required")
    closes = [c.close for c in candles]
    e20, e50 = ema(closes, 20), ema(closes, 50)
    e12, e26 = ema(closes, 12), ema(closes, 26)
    macd = [a-b for a, b in zip(e12, e26) if a is not None and b is not None]
    signal = ema(macd, 9)[-1]
    spread_values = [c.spread for c in candles[-20:]]
    spread_change = None if candles[-1].spread is None or candles[-2].spread is None else candles[-1].spread-candles[-2].spread
    returns = [log(b/a) for a, b in zip(closes[-21:-1], closes[-20:])]
    return {"as_of": as_of.isoformat(), "last_closed_at": candles[-1].closed_at.isoformat(),
            "rsi": rsi(closes)[-1], "ema20": e20[-1], "ema50": e50[-1],
            "macd": macd[-1], "macd_signal": signal, "macd_histogram": macd[-1]-signal,
            "atr": atr(candles)[-1], "trend": "UP" if e20[-1] > e50[-1] else "DOWN" if e20[-1] < e50[-1] else "FLAT",
            "volatility_per_bar": pstdev(returns), "support": min(c.low for c in candles[-20:]),
            "resistance": max(c.high for c in candles[-20:]), "spread_change": spread_change,
            "mean_spread": None if any(s is None for s in spread_values) else sum(spread_values)/len(spread_values),
            "volume_available": all(c.volume is not None for c in candles[-20:])}


def analyze_timeframes(series, as_of):
    # No implicit forward filling or resampling incomplete higher-timeframe bars.
    roles = {240: "context", 60: "conditions", 15: "entries"}
    if set(series) != set(roles):
        raise ValueError("Expected 4H, 1H and 15M series")
    result = {}
    for minutes, role in roles.items():
        closed = [c for c in series[minutes] if c.closed_at <= as_of]
        if any(c.minutes != minutes for c in closed):
            raise ValueError("Timeframe mismatch")
        result[role] = analyze(closed, as_of)
    return result
