"""Prueba de senales Forex V2 sobre captura real autenticada.

Captura desde ReadOnlyObserver en el mismo proceso.
Sin archivos de mercado importados, sin Kronos, sin ordenes.
No calcula P&L ni promueve estrategias.
"""

from pathlib import Path
from math import isfinite

from ..market import validate
from ..research_indicators import calculate, settings
from .strategy_historical_source_v2 import capture_verified_1h
from .strategy_signal_replay_v2 import (
    EXPECTED_SHA,
    load_saved_strategy,
)
from .strategy_rules_v2 import evaluate_rules


class RealSignalProbeError(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise RealSignalProbeError(code)


def run(root):
    root = Path(root).resolve()

    strategy_path = (
        root / ".local"
        / "sol-kronos-research"
        / "design-candidates"
        / (EXPECTED_SHA + ".json")
    )

    # Verificar la estrategia ANTES de conectar con IBKR.
    bundle = load_saved_strategy(strategy_path)

    require(
        bundle["candidate"]["timeframe"] == "1H"
        and bundle["candidate"]["direction"] == "SHORT",
        "STRATEGY_SCOPE_INVALID",
    )

    require(
        bundle["execution_authority"] is False
        and bundle["paper_execution_eligible"] is False
        and bundle["live_enabled"] is False,
        "EXECUTION_FORBIDDEN",
    )

    print("STRATEGY_BUNDLE_VERIFIED", flush=True)
    print("IBKR_READ_ONLY_CAPTURE_START", flush=True)

    # Esta funcion inicia la consulta real al observador.
    # La evidencia de procedencia solo se acepta aqui,
    # en el mismo proceso de captura confiable.
    history = capture_verified_1h(root)

    require(
        history["schema"] == "FOREX_VERIFIED_HISTORY_V2"
        and history["symbol"] == "EUR/USD"
        and history["timeframe"] == "1H"
        and history["source_provider"]
            == "R20_IBKR_PAPER_READ_ONLY"
        and history["capture_scope"]
            == "TRUSTED_IN_PROCESS_OBSERVER"
        and history["calendar_status"]
            == "IBKR_AUTHENTIC_SESSIONS"
        and history["calendar_missing_expected"] == 0
        and history["ibkr_orders"] == 0,
        "HISTORY_VERIFICATION_INVALID",
    )

    candles = history["candles"]
    segments = history["contiguous_segments"]

    require(
        bool(candles)
        and tuple(
            candle
            for segment in segments
            for candle in segment
        ) == tuple(candles),
        "SEGMENT_IDENTITY_INVALID",
    )

    require(
        len(candles) == history["bar_count"]
        and len(segments) == history["segment_count"],
        "HISTORY_COUNT_INVALID",
    )

    # Los huecos ya fueron contrastados con el calendario
    # dentro de capture_verified_1h. Nunca permitirlos
    # directamente en datos de procedencia desconocida.
    validate(
        candles,
        history["as_of"],
        allow_session_gaps=True,
    )

    config = settings()

    require(
        (
            config["ema_fast"],
            config["ema_slow"],
            config["rsi"],
            config["atr"],
        ) == (20, 50, 14, 14),
        "INDICATOR_PERIOD_INVALID",
    )

    # Calculo causal sobre TODAS las velas observadas.
    # No reinicia EMA/RSI al cambiar de sesion,
    # ni fabrica velas para cubrir cierres del mercado.
    points = calculate(candles, config)

    require(
        len(points) == len(candles),
        "INDICATOR_LENGTH_INVALID",
    )

    evaluated = 0
    warmup = 0
    entries = 0
    exits = 0
    conflicts = 0

    examples = []

    for index, (candle, point) in enumerate(
        zip(candles, points)
    ):
        if index == 0 or point["status"] != "READY":
            warmup += 1
            continue

        previous = points[index - 1]

        values = {
            "close": candle.close,
            "ema20": point["ema_fast"],
            "ema50": point["ema_slow"],
            "rsi14": point["rsi"],
            "atr14": point["atr"],
            "prev_close": candles[index - 1].close,
            "prev_ema20": previous["ema_fast"],
            "prev_ema50": previous["ema_slow"],
        }

        require(
            all(
                type(value) in (int, float)
                and isfinite(value)
                for value in values.values()
            ),
            "INVALID_INDICATOR_VALUE",
        )

        require(
            candle.closed_at <= history["as_of"]
            and point["closed_at"]
                == candle.closed_at.isoformat(),
            "FUTURE_OR_MISALIGNED_BAR",
        )

        snapshot = {
            "bar_closed": True,
            "closed_at": candle.closed_at.isoformat(),
            **values,
        }

        evaluation = evaluate_rules(
            bundle["rules"],
            snapshot,
        )

        require(
            evaluation["trading_decision"] == "NO_TRADE"
            and evaluation["execution_authority"] is False,
            "TRADING_DECISION_FORBIDDEN",
        )

        entry = evaluation["entry_condition_met"] is True
        exit_condition = (
            evaluation["exit_condition_met"] is True
        )

        evaluated += 1
        entries += int(entry)
        exits += int(exit_condition)
        conflicts += int(entry and exit_condition)

        if entry and len(examples) < 3:
            examples.append(snapshot["closed_at"])

    require(
        evaluated + warmup == len(candles),
        "EVALUATION_COUNT_MISMATCH",
    )

    return {
        "bars": len(candles),
        "segments": len(segments),
        "ready": evaluated,
        "warmup": warmup,
        "entries": entries,
        "exits": exits,
        "conflicts": conflicts,
        "examples": examples,
        "first": candles[0].opened_at.isoformat(),
        "last": candles[-1].closed_at.isoformat(),
    }


def main():
    report = run(Path.cwd())

    print("")
    print("FOREX_V2_REAL_IBKR_SIGNAL_PROBE_OK")
    print("STRATEGY_BUNDLE_SHA256:", EXPECTED_SHA)
    print("SOURCE: AUTHENTIC_IBKR_PAPER_READ_ONLY")
    print("TIMEFRAME: EUR/USD 1H")
    print("BARS_VERIFIED:", report["bars"])
    print("CALENDAR_SEGMENTS:", report["segments"])
    print("SNAPSHOTS_READY:", report["ready"])
    print("WARMUP_BARS:", report["warmup"])
    print("SHORT_ENTRY_SIGNALS:", report["entries"])
    print("EXIT_CONDITIONS:", report["exits"])
    print("CONFLICTS:", report["conflicts"])
    print("ENTRY_TIMESTAMPS_UTC:", report["examples"])
    print("FIRST_BAR_UTC:", report["first"])
    print("LAST_BAR_CLOSE_UTC:", report["last"])
    print("HISTORICAL_DATA_SAVED: False")
    print("BACKTEST_EXECUTED: False")
    print("ECONOMIC_VALIDATION: NOT_PERFORMED")
    print("TRADING_DECISION: NO_TRADE")
    print("OPENAI_API_CALL: False")
    print("IBKR_ORDERS: 0")


if __name__ == "__main__":
    main()
