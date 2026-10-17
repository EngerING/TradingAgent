"""Fuente historica Forex V2: solo investigacion.

La captura autentica solo se realiza desde ReadOnlyObserver,
en el mismo proceso. No autenticar JSON importados mediante hash.
No ejecuta Kronos, OpenAI ni ordenes.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..market import Candle, validate
from ..research_calendar import ForexCalendar, normalize, stamp
from ..kronos.contracts import TIMEFRAMES


class HistoricalSourceError(ValueError):
    pass


def _require(condition, code):
    if not condition:
        raise HistoricalSourceError(code)


def _split_contiguous(candles):
    """Separa tramos sin huecos; no inventa barras."""

    groups = []
    current = []

    for candle in candles:
        if current and candle.opened_at != current[-1].closed_at:
            groups.append(tuple(current))
            current = []

        current.append(candle)

    if current:
        groups.append(tuple(current))

    return tuple(groups)


def _verify_export_identity(candles, exported):
    """Compara el sufijo exportado con las barras normalizadas."""

    _require(
        isinstance(exported, list)
        and bool(exported)
        and len(candles) >= len(exported),
        "EXPORT_LENGTH_INVALID",
    )

    suffix = candles[-len(exported):]

    for candle, row in zip(suffix, exported):
        _require(
            stamp(row["opened_at"]) == candle.opened_at,
            "EXPORT_TIMESTAMP_MISMATCH",
        )

        for field in ("open", "high", "low", "close"):
            _require(
                float(row[field]) == getattr(candle, field),
                "EXPORT_PRICE_MISMATCH",
            )

    return tuple(suffix)


def _convert_verified_observation(observation, config, *, now):
    """Solo debe llamarse con una observacion del proceso confiable.

    Las verificaciones de procedencia se delegan al contrato R20.
    Esta funcion no autentica por si sola datos externos.
    """

    from ..kronos.r20_source import build_request

    _require(
        isinstance(now, datetime) and now.tzinfo is not None,
        "NOW_INVALID",
    )

    timeframe = config.get("timeframe")

    _require(
        timeframe in TIMEFRAMES
        and TIMEFRAMES[timeframe] == 3600,
        "ONLY_1H_SUPPORTED",
    )

    # Contrato R20: estado, cuenta, modo lectura, cotizacion LIVE,
    # frescura, hash consistente, calendario y lookback.
    request = build_request(
        observation,
        config,
        now=now,
    )

    _require(
        request["symbol"] == "EUR/USD"
        and request["timeframe"] == timeframe
        and request["source"]["broker_orders"] == 0,
        "VERIFIED_REQUEST_SCOPE_INVALID",
    )

    raw = observation["source"]
    as_of = stamp(request["as_of"])

    calendar = ForexCalendar(raw["calendar"])

    candles, audit = normalize(
        raw["bars"]["60"],
        60,
        as_of,
        calendar,
    )

    _require(
        not audit["missing_expected_openings"],
        "MISSING_EXPECTED_MARKET_BARS",
    )

    selected = _verify_export_identity(
        candles,
        request["bars"],
    )

    # Se permiten gaps aqui SOLO despues de que normalize()
    # verifico las aperturas esperadas del calendario.
    validate(
        selected,
        as_of,
        allow_session_gaps=True,
    )

    groups = _split_contiguous(selected)

    _require(
        all(
            group
            and all(
                b.opened_at == a.closed_at
                for a, b in zip(group, group[1:])
            )
            for group in groups
        ),
        "SEGMENT_CONTINUITY_INVALID",
    )

    return {
        "schema": "FOREX_VERIFIED_HISTORY_V2",
        "symbol": "EUR/USD",
        "timeframe": "1H",
        "as_of": as_of,
        "candles": selected,
        "contiguous_segments": groups,
        "bar_count": len(selected),
        "segment_count": len(groups),
        "calendar_missing_expected": 0,
        "calendar_status": audit["calendar_status"],
        "source_sha256": request["source"]["sha256"],
        "source_provider": "R20_IBKR_PAPER_READ_ONLY",
        "capture_scope": "TRUSTED_IN_PROCESS_OBSERVER",
        "trading_decision": "NO_TRADE",
        "execution_authority": False,
        "paper_execution_eligible": False,
        "live_enabled": False,
        "ibkr_orders": 0,
    }


def capture_verified_1h(root):
    """Una captura explicita; no se llama al importar el modulo."""

    from ..kronos.config import load
    from ..r20_runner import ReadOnlyObserver

    root = Path(root).resolve()
    config = load(root)

    _require(
        TIMEFRAMES.get(config["timeframe"]) == 3600,
        "CONFIG_MUST_USE_1H",
    )

    observer = ReadOnlyObserver(
        root,
        client_id=196,
    )

    try:
        observation = observer.poll()
    finally:
        observer.source.close()

    return _convert_verified_observation(
        observation,
        config,
        now=datetime.now(timezone.utc),
    )


def main():
    # Autoprueba local: no crea observaciones falsas de IBKR.
    start = datetime(2026, 1, 5, tzinfo=timezone.utc)

    first = Candle(
        start, 60, 1.12, 1.1203, 1.1198, 1.1201
    )

    second = Candle(
        start + timedelta(hours=1),
        60, 1.1201, 1.1204, 1.1199, 1.1202
    )

    third = Candle(
        start + timedelta(days=2),
        60, 1.1202, 1.1205, 1.1200, 1.1203
    )

    candles = [first, second, third]

    exported = [
        {
            "opened_at": c.opened_at.isoformat(),
            "open": c.open,
            "high": c.high,
            "low": c.low,
            "close": c.close,
        }
        for c in candles
    ]

    verified = _verify_export_identity(candles, exported)
    assert verified == tuple(candles)

    segments = _split_contiguous(verified)

    assert len(segments) == 2
    assert tuple(map(len, segments)) == (2, 1)

    altered = [dict(item) for item in exported]
    altered[1]["close"] += 0.0001

    try:
        _verify_export_identity(candles, altered)
    except HistoricalSourceError:
        tampering_rejected = True
    else:
        tampering_rejected = False

    assert tampering_rejected

    print("FOREX_V2_HISTORICAL_SOURCE_TEST_OK")
    print("CANDLES_SYNTHETIC:", len(candles))
    print("CONTIGUOUS_SEGMENTS:", len(segments))
    print("SEGMENT_LENGTHS:", [len(x) for x in segments])
    print("EXPORT_IDENTITY_VERIFIED: True")
    print("ALTERED_EXPORT_REJECTED:", tampering_rejected)
    print("SESSION_CALENDAR_AUTHENTICATED: False")
    print("IBKR_CAPTURE_PERFORMED: False")
    print("OPENAI_API_CALL: False")
    print("IBKR_ORDERS: 0")


if __name__ == "__main__":
    main()
