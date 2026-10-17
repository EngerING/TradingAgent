"""Reproduccion causal de senales Forex V2.

Investigacion solamente:
- No calcula P&L.
- No mantiene posiciones.
- No consulta API.
- No concede permisos Paper/Live.
"""

import copy
import json
from datetime import datetime, timedelta, timezone
from math import sin
from pathlib import Path

from ..market import Candle
from .strategy_bundle_v2 import validate_bundle
from .strategy_indicators_v2 import build_indicator_snapshots
from .strategy_rules_v2 import evaluate_rules


EXPECTED_SHA = (
    "9cf7f49481d3e1908f0af9187b5c998857ad752e6144fffa2f4fee6a1ce524c3"
)

EXPECTED_ID = "eurusd_short_rechazo_ema20_tendencia_bajista"

MINUTES = {"15M": 15, "1H": 60, "4H": 240}


class SignalReplayError(ValueError):
    pass


def load_saved_strategy(path):
    path = Path(path)

    if not path.is_file():
        raise SignalReplayError("SAVED_STRATEGY_NOT_FOUND")

    if path.name != EXPECTED_SHA + ".json":
        raise SignalReplayError("STRATEGY_FILE_IDENTITY_MISMATCH")

    bundle = json.loads(path.read_text(encoding="utf-8-sig"))

    validate_bundle(bundle)

    if bundle["bundle_sha256"] != EXPECTED_SHA:
        raise SignalReplayError("STRATEGY_HASH_MISMATCH")

    candidate = bundle["candidate"]

    if (
        candidate["strategy_id"] != EXPECTED_ID
        or candidate["instrument"] != "EUR/USD"
        or candidate["timeframe"] != "1H"
        or candidate["direction"] != "SHORT"
        or candidate["research_capital_usd"] != 100
    ):
        raise SignalReplayError("UNEXPECTED_STRATEGY")

    if (
        bundle["execution_authority"] is not False
        or bundle["paper_execution_eligible"] is not False
        or bundle["live_enabled"] is not False
        or bundle["trading_decision"] != "NO_TRADE"
    ):
        raise SignalReplayError("EXECUTION_AUTHORITY_FORBIDDEN")

    return bundle


def replay_signals(bundle, candles, *, as_of):
    """Cuenta condiciones tecnicas, sin simular posiciones."""

    validate_bundle(bundle)

    if not isinstance(candles, (list, tuple)) or not candles:
        raise SignalReplayError("CANDLES_REQUIRED")

    candidate = bundle["candidate"]

    if candidate["instrument"] != "EUR/USD":
        raise SignalReplayError("INSTRUMENT_UNSUPPORTED")

    expected_minutes = MINUTES.get(candidate["timeframe"])

    if expected_minutes is None:
        raise SignalReplayError("TIMEFRAME_UNSUPPORTED")

    if any(c.minutes != expected_minutes for c in candles):
        raise SignalReplayError("CANDLE_TIMEFRAME_MISMATCH")

    if (
        bundle["execution_authority"] is not False
        or bundle["paper_execution_eligible"] is not False
        or bundle["live_enabled"] is not False
        or bundle["trading_decision"] != "NO_TRADE"
    ):
        raise SignalReplayError("EXECUTION_AUTHORITY_FORBIDDEN")

    snapshots = build_indicator_snapshots(candles, as_of=as_of)

    signals = []
    ready = 0
    entries = 0
    exits = 0
    conflicts = 0

    for candle, snapshot in zip(candles, snapshots):
        if snapshot is None:
            continue

        if (
            snapshot.get("bar_closed") is not True
            or snapshot.get("closed_at") != candle.closed_at.isoformat()
        ):
            raise SignalReplayError("SNAPSHOT_ALIGNMENT_INVALID")

        if candle.closed_at > as_of:
            raise SignalReplayError("FUTURE_SNAPSHOT_FORBIDDEN")

        result = evaluate_rules(bundle["rules"], snapshot)

        if result["trading_decision"] != "NO_TRADE":
            raise SignalReplayError("TRADING_DECISION_FORBIDDEN")

        entry = result["entry_condition_met"] is True
        exit_condition = result["exit_condition_met"] is True

        ready += 1
        entries += int(entry)
        exits += int(exit_condition)
        conflicts += int(entry and exit_condition)

        if entry or exit_condition:
            signals.append({
                "closed_at": snapshot["closed_at"],
                "entry_condition_met": entry,
                "exit_condition_met": exit_condition,
                "research_state": result["research_state"],
            })

    return {
        "schema": "FOREX_SIGNAL_REPLAY_V2",
        "strategy_id": candidate["strategy_id"],
        "bundle_sha256": bundle["bundle_sha256"],
        "candles": len(candles),
        "snapshots_ready": ready,
        "entry_conditions_met": entries,
        "exit_conditions_met": exits,
        "conflicting_conditions": conflicts,
        "signals": signals,
        "position_simulation": False,
        "economic_validation": "NOT_PERFORMED",
        "backtested": False,
        "trading_decision": "NO_TRADE",
        "ibkr_orders": 0,
    }


def synthetic_candles():
    """Serie artificial; no representa un mercado real."""

    start = datetime(2026, 1, 5, tzinfo=timezone.utc)
    candles = []
    previous_close = 1.1200

    for i in range(180):
        # Oscilaciones sobre una tendencia bajista artificial.
        close = (
            1.1200
            - i * 0.000035
            + sin(i / 4.0) * 0.00037
        )

        candles.append(Candle(
            opened_at=start + timedelta(hours=i),
            minutes=60,
            open=previous_close,
            high=max(previous_close, close) + 0.00015,
            low=min(previous_close, close) - 0.00015,
            close=close,
        ))

        previous_close = close

    return candles


def main():
    path = (
        Path.cwd()
        / ".local"
        / "sol-kronos-research"
        / "design-candidates"
        / (EXPECTED_SHA + ".json")
    )

    bundle = load_saved_strategy(path)
    candles = synthetic_candles()

    result = replay_signals(
        bundle,
        candles,
        as_of=candles[-1].closed_at,
    )

    # Prueba temporal: incorporar velas posteriores no cambia
    # las senales historicas ya calculadas.
    prefix = candles[:130]

    earlier = replay_signals(
        bundle,
        prefix,
        as_of=prefix[-1].closed_at,
    )

    original_period = [
        event for event in result["signals"]
        if event["closed_at"] <= prefix[-1].closed_at.isoformat()
    ]

    assert original_period == earlier["signals"]
    assert result["snapshots_ready"] == 130
    assert result["trading_decision"] == "NO_TRADE"
    assert result["ibkr_orders"] == 0

    # Una manipulacion del bundle invalida su identidad.
    altered = copy.deepcopy(bundle)
    altered["rules"]["entry"]["all"][0]["operator"] = ">"

    try:
        validate_bundle(altered)
    except (ValueError, TypeError, KeyError):
        tamper_rejected = True
    else:
        tamper_rejected = False

    assert tamper_rejected

    # Rechazar datos de una temporalidad distinta.
    wrong_timeframe = [
        Candle(
            opened_at=c.opened_at,
            minutes=15,
            open=c.open,
            high=c.high,
            low=c.low,
            close=c.close,
        )
        for c in candles
    ]

    try:
        replay_signals(
            bundle,
            wrong_timeframe,
            as_of=candles[-1].closed_at,
        )
    except SignalReplayError:
        timeframe_rejected = True
    else:
        timeframe_rejected = False

    assert timeframe_rejected

    print("FOREX_V2_SIGNAL_REPLAY_OK")
    print("STRATEGY_ID:", result["strategy_id"])
    print("BUNDLE_SHA256:", result["bundle_sha256"])
    print("BUNDLE_INTEGRITY: VERIFIED")
    print("CANDLES_SYNTHETIC:", result["candles"])
    print("SNAPSHOTS_READY:", result["snapshots_ready"])
    print("ENTRY_CONDITIONS_MET:", result["entry_conditions_met"])
    print("EXIT_CONDITIONS_MET:", result["exit_conditions_met"])
    print("CONFLICTING_CONDITIONS:", result["conflicting_conditions"])
    print("HISTORICAL_SIGNALS_STABLE: True")
    print("MODIFIED_BUNDLE_REJECTED:", tamper_rejected)
    print("WRONG_TIMEFRAME_REJECTED:", timeframe_rejected)
    print("POSITION_SIMULATION: False")
    print("ECONOMIC_VALIDATION: NOT_PERFORMED")
    print("BACKTESTED: False")
    print("TRADING_DECISION: NO_TRADE")
    print("OPENAI_API_CALL: False")
    print("IBKR_ORDERS: 0")


if __name__ == "__main__":
    main()
