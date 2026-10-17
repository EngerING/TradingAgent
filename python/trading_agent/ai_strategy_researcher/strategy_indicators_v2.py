"""Adaptador causal de indicadores para Forex Strategy V2.

Solo investigacion. No consulta IBKR ni envia ordenes.
Los datos deben ser velas cerradas, ordenadas y continuas.
Los gaps de sesion requieren una futura validacion de calendario.
"""

from datetime import datetime, timedelta, timezone
from math import isfinite

from ..market import Candle, validate
from ..research_indicators import calculate, settings


class ForexIndicatorError(ValueError):
    pass


def build_indicator_snapshots(candles, *, as_of):
    """Genera snapshots alineados; None durante warmup."""

    if type(candles) not in (list, tuple) or not candles:
        raise ForexIndicatorError("CANDLES_REQUIRED")

    if not all(isinstance(c, Candle) for c in candles):
        raise ForexIndicatorError("CANDLE_TYPE_INVALID")

    if not isinstance(as_of, datetime) or as_of.tzinfo is None:
        raise ForexIndicatorError("AS_OF_UTC_REQUIRED")

    # Mantiene las validaciones originales: OHLC, alineacion,
    # velas cerradas, orden temporal y ausencia de huecos.
    # No permite gaps sin una verificacion externa de calendario.
    validate(candles, as_of, allow_session_gaps=False)

    config = settings()

    if not (
        config["ema_fast"] == 20
        and config["ema_slow"] == 50
        and config["rsi"] == 14
        and config["atr"] == 14
    ):
        raise ForexIndicatorError("INDICATOR_PERIOD_MISMATCH")

    points = calculate(candles, config)

    if len(points) != len(candles):
        raise ForexIndicatorError("INDICATOR_ALIGNMENT_INVALID")

    snapshots = []

    for i, (candle, point) in enumerate(zip(candles, points)):
        if i == 0 or point["status"] != "READY":
            snapshots.append(None)
            continue

        previous = points[i - 1]

        values = {
            "close": candle.close,
            "ema20": point["ema_fast"],
            "ema50": point["ema_slow"],
            "rsi14": point["rsi"],
            "atr14": point["atr"],
            "prev_close": candles[i - 1].close,
            "prev_ema20": previous["ema_fast"],
            "prev_ema50": previous["ema_slow"],
        }

        if any(
            type(value) not in (int, float)
            or not isfinite(value)
            for value in values.values()
        ):
            raise ForexIndicatorError("INDICATOR_VALUE_INVALID")

        snapshots.append({
            "bar_closed": True,
            "closed_at": candle.closed_at.isoformat(),
            **values,
        })

    return snapshots


if __name__ == "__main__":
    from ..research_indicators import calculate, settings

    start = datetime(2026, 1, 5, tzinfo=timezone.utc)

    # Datos sinteticos solo para probar alineacion y causalidad.
    candles = []

    for i in range(120):
        price = 1.12 + i * 0.00001
        candles.append(Candle(
            opened_at=start + timedelta(hours=i),
            minutes=60,
            open=price,
            high=price + 0.0002,
            low=price - 0.0002,
            close=price + 0.00005,
        ))

    as_of = candles[-1].closed_at
    snapshots = build_indicator_snapshots(candles, as_of=as_of)

    assert len(snapshots) == len(candles)
    assert snapshots[0] is None
    assert snapshots[-1] is not None

    original = calculate(candles, settings())
    last = snapshots[-1]

    assert last["ema20"] == original[-1]["ema_fast"]
    assert last["ema50"] == original[-1]["ema_slow"]
    assert last["rsi14"] == original[-1]["rsi"]
    assert last["atr14"] == original[-1]["atr"]

    assert last["prev_close"] == candles[-2].close
    assert last["prev_ema20"] == original[-2]["ema_fast"]
    assert last["prev_ema50"] == original[-2]["ema_slow"]

    # Causalidad: agregar una vela futura no debe cambiar
    # los indicadores previamente calculados.
    next_price = candles[-1].close

    future = Candle(
        opened_at=candles[-1].closed_at,
        minutes=60,
        open=next_price,
        high=next_price + 0.0002,
        low=next_price - 0.0002,
        close=next_price + 0.0001,
    )

    extended = build_indicator_snapshots(
        candles + [future],
        as_of=future.closed_at,
    )

    assert extended[:-1] == snapshots

    # Rechazar cualquier vela aun no cerrada.
    try:
        build_indicator_snapshots(
            candles,
            as_of=candles[-1].opened_at,
        )
    except ValueError:
        pass
    else:
        raise AssertionError("UNCLOSED_CANDLE_ACCEPTED")

    # Rechazar un hueco no validado por calendario.
    with_gap = candles[:60] + candles[61:]

    try:
        build_indicator_snapshots(
            with_gap,
            as_of=as_of,
        )
    except ValueError:
        pass
    else:
        raise AssertionError("UNVERIFIED_SESSION_GAP_ACCEPTED")

    print("FOREX_V2_INDICATOR_ADAPTER_OK")
    print("CANDLES_TESTED:", len(candles))
    print("SNAPSHOTS_READY:", sum(x is not None for x in snapshots))
    print("EMA20_MATCHES_SOURCE: True")
    print("EMA50_MATCHES_SOURCE: True")
    print("RSI14_MATCHES_SOURCE: True")
    print("ATR14_MATCHES_SOURCE: True")
    print("PREVIOUS_CANDLE_ALIGNMENT: VERIFIED")
    print("NO_LOOKAHEAD_TEST: PASSED")
    print("UNCLOSED_CANDLE_REJECTED: True")
    print("UNVERIFIED_GAP_REJECTED: True")
    print("TRADING_DECISION: NO_TRADE")
    print("OPENAI_API_CALL: False")
    print("IBKR_ORDERS: 0")
