
"""Adaptador R20 read-only -> entrada Kronos; no acceso al broker ni diario.

IMPORTANTE: la observacion debe provenir del ReadOnlyObserver confiable del
proceso. Un hash calculado a partir de datos recibidos no autentica su origen.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from .contracts import TIMEFRAMES, instant
from .features import validate_input


_MINUTES = {"1H": 60, "4H": 240}


def _need(condition: bool, code: str) -> None:
    if not condition:
        raise ValueError(code)


def _utc_now(now: datetime) -> datetime:
    _need(
        isinstance(now, datetime) and now.tzinfo is not None,
        "R20_NOW_INVALID",
    )
    return now.astimezone(timezone.utc)


def build_request(
    observation: Mapping[str, Any],
    config: Mapping[str, Any],
    *,
    now: datetime,
) -> dict[str, Any]:
    """Convierte una lectura R20 verificada en una solicitud Kronos.

    No llama a IBKR, no escribe eventos Shadow ni ejecuta inferencia.
    Solo acepta 1H y 4H porque son las temporalidades del proveedor R20.
    """
    from ..r20_profiles import digest as r20_digest
    from ..research_calendar import ForexCalendar, normalize

    _need(
        isinstance(observation, Mapping)
        and isinstance(config, Mapping),
        "R20_INPUT_REQUIRED",
    )

    _need(
        observation.get("status") == "READ_ONLY_DIAGNOSTIC",
        "R20_OBSERVATION_NOT_VERIFIED",
    )

    _need(
        observation.get("entryEligible") is False
        and observation.get("cohortStarted") is False
        and type(observation.get("brokerOrders")) is int
        and observation["brokerOrders"] == 0,
        "R20_READ_ONLY_REQUIRED",
    )

    raw = observation.get("source")
    view = observation.get("market")

    _need(
        isinstance(raw, dict) and isinstance(view, dict),
        "R20_MARKET_REQUIRED",
    )

    _need(
        view.get("classification")
        == "AUTHENTIC_IBKR_READ_ONLY_DIAGNOSTIC"
        and view.get("status") == "VERIFIED_AT_CUTOFF"
        and view.get("exactAccountMatch") is True
        and view.get("readOnly") is True
        and view.get("entryEligible") is False
        and type(view.get("brokerOrders")) is int
        and view["brokerOrders"] == 0
        and view.get("cohortStarted") is False,
        "R20_MARKET_NOT_VERIFIED",
    )

    _need(
        raw.get("classification")
        == "AUTHENTIC_IBKR_READ_ONLY_DIAGNOSTIC",
        "R20_RAW_SCOPE_INVALID",
    )

    # Comprobar la consistencia entre los datos y el resumen R20.
    source_hash = r20_digest(raw)

    _need(
        view.get("sourceHash") == source_hash,
        "R20_SOURCE_HASH_MISMATCH",
    )

    _need(
        view.get("quote") == raw.get("quote"),
        "R20_QUOTE_MISMATCH",
    )

    # Verificar la antiguedad de la observacion y de la cotizacion.
    clock = _utc_now(now)

    try:
        observed_at = instant(view["at"])
        raw_at = instant(raw["at"])
        quote = raw["quote"]
        quote_at = instant(quote["at"])
    except (ValueError, TypeError, KeyError, AttributeError):
        raise ValueError("R20_TIMESTAMP_INVALID") from None

    _need(
        raw_at == observed_at
        and 0 <= (clock - observed_at).total_seconds() <= 30
        and 0 <= (observed_at - quote_at).total_seconds() <= 30
        and 0 <= (clock - quote_at).total_seconds() <= 30,
        "R20_OBSERVATION_STALE_OR_FUTURE",
    )

    _need(
        quote.get("source") == "IBKR_PAPER"
        and quote.get("type") == "LIVE"
        and type(quote.get("market_data_type")) is int
        and quote["market_data_type"] == 1
        and quote.get("market_status") == "OPEN"
        and not quote.get("adapter_errors"),
        "R20_QUOTE_NOT_LIVE",
    )

    # Kronos y R20 utilizan representaciones diferentes de temporalidad.
    timeframe = config.get("timeframe")

    _need(
        timeframe in _MINUTES and timeframe in TIMEFRAMES,
        "R20_TIMEFRAME_NOT_SUPPORTED",
    )

    _need(
        config.get("symbol") == "EUR/USD",
        "R20_SYMBOL_SCOPE_MISMATCH",
    )

    minutes = _MINUTES[timeframe]
    key = str(minutes)

    # Volver a aplicar el calendario que utiliza R20.
    try:
        original = raw["bars"][key]
        reported = view["bars"][key]

        calendar = ForexCalendar(raw["calendar"])

        _, audit = normalize(
            original,
            minutes,
            observed_at,
            calendar,
        )

        included = {
            b["opened_at"]
            for b in audit["bars"]
            if b["status"] == "INCLUDED_NATIVE"
        }

        rows = [
            b for b in original
            if b["opened_at"] in included
        ]

    except (KeyError, TypeError, ValueError, AttributeError):
        raise ValueError("R20_BARS_INVALID") from None

    _need(
        not audit["missing_expected_openings"]
        and not reported.get("missing")
        and type(reported.get("count")) is int
        and reported["count"] == len(rows),
        "R20_BAR_QUALITY_MISMATCH",
    )

    _need(
        len(rows) >= config["lookback"],
        "R20_LOOKBACK_INSUFFICIENT",
    )

    # Usar velas originales, sin inventar volumen ni rellenar huecos.
    bars = [
        {
            name: b[name]
            for name in (
                "opened_at",
                "open",
                "high",
                "low",
                "close",
            )
        }
        for b in rows[-config["lookback"]:]
    ]

    step = timedelta(seconds=TIMEFRAMES[timeframe])

    latest_close = (
        instant(bars[-1]["opened_at"]) + step
    )

    _need(
        instant(reported["lastClose"]) == latest_close,
        "R20_LAST_CLOSE_MISMATCH",
    )

    # Construir el contrato esperado por Kronos.
    request = {
        "symbol": "EUR/USD",
        "timeframe": timeframe,
        "as_of": observed_at.isoformat(),
        "bars": bars,
        "signal": None,
        "partition": "FORWARD",
        "regime": "UNKNOWN",
        "source": {
            "quality": "AUTHENTIC",
            "provider": "R20_IBKR_PAPER_READ_ONLY",
            "sha256": source_hash,
            "provenance_scope": "TRUSTED_IN_PROCESS_R20_OBSERVER",
            "missing_bars_not_filled": True,
            "broker_orders": 0,
        },
    }

    # La validacion final corresponde al contrato original de Kronos.
    validate_input(request, config)

    return request
