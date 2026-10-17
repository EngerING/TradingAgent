"""Simulador experimental SHORT Forex V2.

Sin broker, sin ordenes, sin permisos de ejecucion.
Resultados sinteticos NO demuestran rentabilidad.
"""

from dataclasses import dataclass
from datetime import datetime
from math import floor, isfinite
from pathlib import Path

from .strategy_bundle_v2 import validate_bundle
from .strategy_indicators_v2 import build_indicator_snapshots
from .strategy_rules_v2 import evaluate_rules
from .strategy_signal_replay_v2 import (
    EXPECTED_SHA,
    load_saved_strategy,
    synthetic_candles,
)


class PositionSimulationError(ValueError):
    pass


@dataclass(frozen=True)
class SimulationConfig:
    capital_usd: float = 100.0
    risk_fraction: float = 0.10
    max_leverage: float = 1.0
    atr_stop_multiple: float = 2.0
    spread: float = 0.00010
    slippage: float = 0.00005
    commission_per_side_usd: float = 2.0
    minimum_quantity_eur: int = 1


def validate_config(config):
    if not isinstance(config, SimulationConfig):
        raise PositionSimulationError("CONFIG_INVALID")

    positive = (
        config.capital_usd,
        config.risk_fraction,
        config.max_leverage,
        config.atr_stop_multiple,
        config.minimum_quantity_eur,
    )

    nonnegative = (
        config.spread,
        config.slippage,
        config.commission_per_side_usd,
    )

    if any(
        type(v) not in (int, float)
        or not isfinite(v)
        or v <= 0
        for v in positive
    ):
        raise PositionSimulationError("POSITIVE_CONFIG_INVALID")

    if any(
        type(v) not in (int, float)
        or not isfinite(v)
        or v < 0
        for v in nonnegative
    ):
        raise PositionSimulationError("COST_CONFIG_INVALID")

    if (
        config.capital_usd != 100
        or config.risk_fraction > 0.10
        or config.max_leverage > 1.0
        or type(config.minimum_quantity_eur) is not int
    ):
        raise PositionSimulationError("RESEARCH_BOUND_EXCEEDED")


def simulate_short(bundle, candles, *, as_of, config):
    validate_config(config)
    validate_bundle(bundle)

    candidate = bundle["candidate"]

    if (
        candidate["instrument"] != "EUR/USD"
        or candidate["timeframe"] != "1H"
        or candidate["direction"] != "SHORT"
        or candidate["research_capital_usd"] != 100
        or bundle["execution_authority"] is not False
        or bundle["paper_execution_eligible"] is not False
        or bundle["live_enabled"] is not False
    ):
        raise PositionSimulationError("STRATEGY_UNSUPPORTED")

    if not isinstance(as_of, datetime):
        raise PositionSimulationError("AS_OF_INVALID")

    if not candles or any(c.minutes != 60 for c in candles):
        raise PositionSimulationError("CANDLES_TIMEFRAME_INVALID")

    snapshots = build_indicator_snapshots(
        candles,
        as_of=as_of,
    )

    cash = config.capital_usd
    position = None
    pending_entry = False
    pending_exit = False
    trades = []
    rejected = 0
    stop_count = 0
    peak = cash
    max_drawdown = 0.0
    equity_curve = []

    def execution_price(mid, *, side):
        adjustment = config.spread / 2 + config.slippage
        return mid + adjustment if side == "BUY" else mid - adjustment

    def close_position(mid, at, reason):
        nonlocal cash, position, stop_count

        if position is None:
            raise PositionSimulationError("NO_POSITION_TO_CLOSE")

        price = execution_price(mid, side="BUY")
        gross = (
            position["entry_price"] - price
        ) * position["quantity_eur"]

        fees = 2 * config.commission_per_side_usd
        net = gross - fees
        cash += net

        trades.append({
            "entry_at": position["entry_at"],
            "exit_at": at,
            "quantity_eur": position["quantity_eur"],
            "entry_price": position["entry_price"],
            "exit_price": price,
            "gross_usd": round(gross, 6),
            "fees_usd": fees,
            "net_usd": round(net, 6),
            "reason": reason,
        })

        if reason == "PROTECTIVE_STOP":
            stop_count += 1

        position = None

    for i, candle in enumerate(candles):
        # La orden hipotetica se procesa al abrir esta vela
        # a partir de una senal de la vela anterior.
        if pending_exit and position is not None:
            close_position(
                candle.open,
                candle.opened_at.isoformat(),
                "SOL_EXIT_NEXT_OPEN",
            )

        elif pending_entry and position is None and cash > 0:
            previous = snapshots[i - 1] if i else None

            if previous is None:
                rejected += 1
            else:
                atr_value = previous["atr14"]
                entry = execution_price(candle.open, side="SELL")

                # Stop sobre el precio medio; el cierre SHORT
                # compra al ask e incluye deslizamiento.
                stop_mid = candle.open + (
                    config.atr_stop_multiple * atr_value
                )
                stop_fill = execution_price(
                    stop_mid, side="BUY"
                )

                unit_risk = stop_fill - entry
                fees = 2 * config.commission_per_side_usd

                risk_budget = cash * config.risk_fraction
                max_exposure_usd = cash * config.max_leverage

                if unit_risk <= 0 or risk_budget <= fees:
                    quantity = 0
                else:
                    risk_quantity = (
                        risk_budget - fees
                    ) / unit_risk

                    exposure_quantity = (
                        max_exposure_usd / candle.open
                    )

                    quantity = floor(
                        min(risk_quantity, exposure_quantity)
                    )

                if (
                    quantity < config.minimum_quantity_eur
                    or quantity * candle.open > max_exposure_usd
                    or cash <= fees
                ):
                    rejected += 1
                else:
                    position = {
                        "entry_at": candle.opened_at.isoformat(),
                        "entry_price": entry,
                        "quantity_eur": quantity,
                        "stop_mid": stop_mid,
                    }

        pending_entry = False
        pending_exit = False

        # La proteccion intrabar se evalua despues de abrir.
        # Para SHORT, una subida golpea el stop.
        # Si hay gap por encima del stop, se usa la apertura
        # mas desfavorable, no el stop teorico.
        if (
            position is not None
            and candle.high >= position["stop_mid"]
        ):
            stop_mid = max(
                candle.open,
                position["stop_mid"],
            )

            close_position(
                stop_mid,
                candle.closed_at.isoformat(),
                "PROTECTIVE_STOP",
            )

        snapshot = snapshots[i]

        if snapshot is not None:
            evaluation = evaluate_rules(
                bundle["rules"],
                snapshot,
            )

            if evaluation["trading_decision"] != "NO_TRADE":
                raise PositionSimulationError(
                    "EXECUTION_DECISION_FORBIDDEN"
                )

            entry_met = (
                evaluation["entry_condition_met"] is True
            )
            exit_met = (
                evaluation["exit_condition_met"] is True
            )

            if entry_met and exit_met:
                raise PositionSimulationError(
                    "CONFLICTING_SIGNALS"
                )

            if position is not None and exit_met:
                pending_exit = True

            elif position is None and entry_met:
                pending_entry = True

        # Valoracion conservadora de la posicion abierta,
        # incluyendo el costo estimado de cerrarla.
        equity = cash

        if position is not None:
            exit_mark = execution_price(
                candle.close, side="BUY"
            )

            equity += (
                position["entry_price"] - exit_mark
            ) * position["quantity_eur"]

            equity -= 2 * config.commission_per_side_usd

        peak = max(peak, equity)

        if peak > 0:
            max_drawdown = max(
                max_drawdown,
                (peak - equity) / peak,
            )

        equity_curve.append({
            "closed_at": candle.closed_at.isoformat(),
            "equity_usd": round(equity, 6),
        })

    # Liquidacion teorica al final de la muestra;
    # no supone ejecucion garantizada en mercado.
    if position is not None:
        last = candles[-1]

        close_position(
            last.close,
            last.closed_at.isoformat(),
            "END_OF_DATA",
        )

    total_net = cash - config.capital_usd

    return {
        "schema": "FOREX_POSITION_SIMULATION_V2",
        "strategy_id": candidate["strategy_id"],
        "bundle_sha256": bundle["bundle_sha256"],
        "capital_initial_usd": config.capital_usd,
        "capital_final_usd": round(cash, 6),
        "net_usd": round(total_net, 6),
        "return_pct": round(
            total_net / config.capital_usd * 100, 4
        ),
        "risk_fraction": config.risk_fraction,
        "max_leverage": config.max_leverage,
        "trades_closed": len(trades),
        "rejected_entries": rejected,
        "protective_stops": stop_count,
        "max_drawdown_close_mark_pct": round(
            max_drawdown * 100, 4
        ),
        "trades": trades,
        "equity_curve": equity_curve,
        "data_source": "CALLER_SUPPLIED",
        "real_market_data_verified": False,
        "broker_executability_verified": False,
        "trading_decision": "NO_TRADE",
        "execution_authority": False,
        "paper_execution_eligible": False,
        "live_enabled": False,
        "ibkr_orders": 0,
    }


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

    # La prueba anterior usa 180 velas con cero senales.
    # Aqui construimos una serie controlada con cruces.
    from math import sin
    from datetime import timedelta

    start = candles[0].opened_at
    test_candles = []
    previous_close = 1.1200

    from ..market import Candle

    for i in range(240):
        close = (
            1.1200
            - i * 0.000025
            + sin(i / 3.5) * 0.0008
        )

        test_candles.append(Candle(
            opened_at=start + timedelta(hours=i),
            minutes=60,
            open=previous_close,
            high=max(previous_close, close) + 0.00015,
            low=min(previous_close, close) - 0.00015,
            close=close,
        ))

        previous_close = close

    conservative = simulate_short(
        bundle,
        test_candles,
        as_of=test_candles[-1].closed_at,
        config=SimulationConfig(risk_fraction=0.01),
    )

    aggressive = simulate_short(
        bundle,
        test_candles,
        as_of=test_candles[-1].closed_at,
        config=SimulationConfig(risk_fraction=0.10),
    )

    assert conservative["trades_closed"] == 0
    assert conservative["rejected_entries"] > 0
    assert aggressive["trades_closed"] > 0

    for result in (conservative, aggressive):
        assert result["execution_authority"] is False
        assert result["paper_execution_eligible"] is False
        assert result["live_enabled"] is False
        assert result["ibkr_orders"] == 0
        assert result["trading_decision"] == "NO_TRADE"

        assert abs(
            sum(t["net_usd"] for t in result["trades"])
            - result["net_usd"]
        ) < 0.0001

        assert all(
            t["fees_usd"] == 4.0
            for t in result["trades"]
        )

    print("FOREX_V2_POSITION_SIMULATION_OK")
    print("STRATEGY_ID:", aggressive["strategy_id"])
    print("DATA: SYNTHETIC")
    print("CAPITAL_USD: 100")
    print("COMMISSION_ROUND_TRIP_USD: 4")
    print("MAX_LEVERAGE: 1")

    print("")
    print("RISK_1_PERCENT")
    print("TRADES:", conservative["trades_closed"])
    print("REJECTED_ENTRIES:", conservative["rejected_entries"])
    print("NET_USD:", conservative["net_usd"])

    print("")
    print("RISK_10_PERCENT_EXPERIMENT")
    print("TRADES:", aggressive["trades_closed"])
    print("REJECTED_ENTRIES:", aggressive["rejected_entries"])
    print("PROTECTIVE_STOPS:", aggressive["protective_stops"])
    print("NET_USD:", aggressive["net_usd"])
    print("RETURN_PCT:", aggressive["return_pct"])
    print(
        "CLOSE_MARK_DRAWDOWN_PCT:",
        aggressive["max_drawdown_close_mark_pct"],
    )

    print("")
    print("REAL_MARKET_DATA_VERIFIED: False")
    print("BROKER_EXECUTABILITY_VERIFIED: False")
    print("PAPER_EXECUTION_ELIGIBLE: False")
    print("TRADING_DECISION: NO_TRADE")
    print("OPENAI_API_CALL: False")
    print("IBKR_ORDERS: 0")


if __name__ == "__main__":
    main()
