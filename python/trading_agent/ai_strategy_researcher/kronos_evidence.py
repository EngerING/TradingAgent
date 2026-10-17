
"""Convierte pronósticos Kronos en evidencia acotada para investigación.

No genera señales, no estima costos y no concede permisos de ejecución.
"""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import math
import re
from typing import Any, Mapping


EVIDENCE_SCHEMA = "KRONOS_RESEARCH_EVIDENCE_V1"

_CALIBRATION_STATES = frozenset({
    "RAW_ONLY",
    "CALIBRATION_INSUFFICIENT",
    "CALIBRATION_DEGRADED",
    "CALIBRATED",
})

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_ID = re.compile(r"[A-Za-z0-9_./:@+-]{1,160}\Z")


class KronosEvidenceError(ValueError):
    """Error con código estable; no incluye datos sensibles."""


def _require(condition: bool, code: str) -> None:
    """Rechaza entradas inválidas con un código identificable."""
    if not condition:
        raise KronosEvidenceError(code)


def _identifier(value: Any, code: str) -> str:
    """Valida identificadores sin caracteres de control."""
    _require(
        isinstance(value, str) and _ID.fullmatch(value) is not None,
        code,
    )
    return value


def _timestamp(value: Any, code: str) -> datetime:
    """Convierte un timestamp con zona horaria explícita a UTC."""
    _require(isinstance(value, str), code)

    try:
        parsed = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
    except ValueError:
        raise KronosEvidenceError(code) from None

    _require(parsed.tzinfo is not None, code)

    return parsed.astimezone(timezone.utc)


def _instant(value: Any) -> datetime:
    """Acepta datetime o timestamp ISO para el reloj de validación."""
    if isinstance(value, datetime):
        _require(
            value.tzinfo is not None,
            "NOW_MUST_BE_TIMEZONE_AWARE",
        )
        return value.astimezone(timezone.utc)

    return _timestamp(value, "NOW_INVALID")


def _finite(value: Any, code: str) -> float:
    """Exige números finitos y rechaza booleanos."""
    _require(
        type(value) in (int, float) and math.isfinite(value),
        code,
    )
    return float(value)


def _probability(
    value: Any,
    code: str,
    *,
    optional: bool = False,
) -> float | None:
    """Una probabilidad debe pertenecer al intervalo [0, 1]."""
    if value is None and optional:
        return None

    n = _finite(value, code)

    _require(0.0 <= n <= 1.0, code)

    return n


def _count(value: Any, code: str) -> int:
    """Valida contadores de muestras."""
    _require(
        type(value) is int and 0 <= value <= 1_000_000,
        code,
    )
    return value


def build_kronos_evidence(
    prediction: Mapping[str, Any],
    *,
    now: datetime | str,
    expected_symbol: str,
    expected_timeframe: str | int,
    max_prediction_age_seconds: int,
    max_candle_age_seconds: int,
    expected_signal_id: str | None = None,
    expected_strategy_id: str | None = None,
) -> dict[str, Any]:
    """Prepara evidencia de Kronos para investigación con Sol.

    No concede autoridad de ejecución.

    Las ventanas de frescura provienen de la política externa.
    El hash de las muestras es una referencia; aquí no se leen
    ni verifican los bytes del artefacto original.
    """

    # 1. Contrato y permisos de la predicción.
    _require(
        isinstance(prediction, Mapping),
        "PREDICTION_REQUIRED",
    )

    _require(
        type(max_prediction_age_seconds) is int
        and max_prediction_age_seconds > 0,
        "PREDICTION_AGE_POLICY_REQUIRED",
    )

    _require(
        type(max_candle_age_seconds) is int
        and max_candle_age_seconds > 0,
        "CANDLE_AGE_POLICY_REQUIRED",
    )

    _require(
        prediction.get("scope") == "KRONOS_OBSERVATION_ONLY",
        "UNEXPECTED_PREDICTION_SCOPE",
    )

    _require(
        prediction.get("execution_authority") is False
        and prediction.get("live_enabled") is False,
        "EXECUTION_AUTHORITY_NOT_ALLOWED",
    )

    # 2. Identidad del instrumento y modelo.
    symbol = _identifier(
        prediction.get("symbol"),
        "SYMBOL_INVALID",
    )

    _require(
        symbol == expected_symbol,
        "SYMBOL_MISMATCH",
    )

    timeframe = prediction.get("timeframe")

    _require(
        type(timeframe) in (str, int)
        and timeframe == expected_timeframe,
        "TIMEFRAME_MISMATCH",
    )

    prediction_id = _identifier(
        prediction.get("prediction_id"),
        "PREDICTION_ID_INVALID",
    )

    model_version = _identifier(
        prediction.get("model_version"),
        "MODEL_VERSION_INVALID",
    )

    tokenizer_version = _identifier(
        prediction.get("tokenizer_version"),
        "TOKENIZER_VERSION_INVALID",
    )

    config_hash = prediction.get("config_hash")
    samples_hash = prediction.get("samples_sha256")

    _require(
        isinstance(config_hash, str)
        and _SHA256.fullmatch(config_hash) is not None,
        "CONFIG_HASH_INVALID",
    )

    _require(
        isinstance(samples_hash, str)
        and _SHA256.fullmatch(samples_hash) is not None,
        "SAMPLES_HASH_INVALID",
    )

    # 3. Vinculación con la señal y la estrategia.
    signal_id = prediction.get("signal_id")

    if signal_id is not None:
        _identifier(signal_id, "SIGNAL_ID_INVALID")

    if expected_signal_id is not None:
        _require(
            signal_id == expected_signal_id,
            "SIGNAL_MISMATCH",
        )

    strategy_id = prediction.get("strategy_id")

    if strategy_id is not None:
        _identifier(strategy_id, "STRATEGY_ID_INVALID")

    if expected_strategy_id is not None:
        _require(
            strategy_id == expected_strategy_id,
            "STRATEGY_MISMATCH",
        )

    # 4. Validación temporal.
    current = _instant(now)

    created = _timestamp(
        prediction.get("created_at"),
        "PREDICTION_CREATED_AT_INVALID",
    )

    candle = _timestamp(
        prediction.get("candle_timestamp"),
        "CANDLE_TIMESTAMP_INVALID",
    )

    _require(
        candle <= created <= current,
        "PREDICTION_TIME_ORDER_INVALID",
    )

    prediction_age = (
        current - created
    ).total_seconds()

    candle_age = (
        current - candle
    ).total_seconds()

    _require(
        prediction_age <= max_prediction_age_seconds,
        "PREDICTION_STALE",
    )

    _require(
        candle_age <= max_candle_age_seconds,
        "MARKET_DATA_STALE",
    )

    # Esta versión del puente acepta evidencia forward.
    # Los resultados históricos usarán otro contrato explícito.
    partition = prediction.get(
        "partition",
        "FORWARD",
    )

    _require(
        partition == "FORWARD",
        "FORWARD_EVIDENCE_REQUIRED",
    )

    # 5. Estado de salud y calidad de las muestras.
    status = prediction.get("status")

    _require(
        status in ("KRONOS_READY", "KRONOS_DEGRADED"),
        "KRONOS_STATUS_INVALID",
    )

    diagnostics = prediction.get("diagnostics")

    _require(
        isinstance(diagnostics, Mapping),
        "DIAGNOSTICS_REQUIRED",
    )

    valid_paths = _count(
        diagnostics.get("valid_paths"),
        "VALID_PATH_COUNT_INVALID",
    )

    invalid_paths = _count(
        diagnostics.get("invalid_paths"),
        "INVALID_PATH_COUNT_INVALID",
    )

    total_paths = _count(
        diagnostics.get("total_paths"),
        "TOTAL_PATH_COUNT_INVALID",
    )

    _require(
        total_paths > 0
        and valid_paths + invalid_paths == total_paths
        and valid_paths > 0,
        "SAMPLE_COUNTS_INCONSISTENT",
    )

    invalid_frequency = _probability(
        prediction.get("invalid_frequency"),
        "INVALID_FREQUENCY_INVALID",
    )

    _require(
        abs(
            invalid_frequency
            - invalid_paths / total_paths
        ) <= 1e-6,
        "INVALID_FREQUENCY_MISMATCH",
    )

    _require(
        status != "KRONOS_READY"
        or invalid_paths == 0,
        "READY_WITH_INVALID_PATHS",
    )

    degraded = (
        status == "KRONOS_DEGRADED"
        or invalid_paths > 0
        or diagnostics.get("provider_degraded") is True
    )

    # 6. Estadísticas brutas del pronóstico.
    raw_tp = _probability(
        prediction.get("raw_tp_frequency"),
        "RAW_TP_FREQUENCY_INVALID",
        optional=True,
    )

    raw_sl = _probability(
        prediction.get("raw_sl_frequency"),
        "RAW_SL_FREQUENCY_INVALID",
        optional=True,
    )

    neither = _probability(
        prediction.get("neither_frequency"),
        "NEITHER_FREQUENCY_INVALID",
        optional=True,
    )

    sample_count = _count(
        prediction.get("sample_count"),
        "SAMPLE_COUNT_INVALID",
    )

    _require(
        sample_count == total_paths,
        "SAMPLE_COUNT_MISMATCH",
    )

    frequencies = (raw_tp, raw_sl, neither)

    if any(value is not None for value in frequencies):
        _require(
            all(value is not None for value in frequencies),
            "INCOMPLETE_SIGNAL_FREQUENCIES",
        )

        total_frequency = (
            raw_tp + raw_sl + neither + invalid_frequency
        )

        _require(
            abs(total_frequency - 1.0) <= 1e-6,
            "FREQUENCIES_DO_NOT_SUM_TO_ONE",
        )

    median_return = _finite(
        prediction.get("predicted_return_median"),
        "PREDICTED_RETURN_INVALID",
    )

    # 7. Calibración histórica.
    calibration = prediction.get("calibration")

    _require(
        isinstance(calibration, Mapping),
        "CALIBRATION_REQUIRED",
    )

    state = calibration.get("state")

    _require(
        state in _CALIBRATION_STATES,
        "CALIBRATION_STATE_INVALID",
    )

    _require(
        prediction.get("calibration_state") == state,
        "CALIBRATION_STATE_MISMATCH",
    )

    comparable = _count(
        calibration.get("comparable_samples"),
        "COMPARABLE_SAMPLE_COUNT_INVALID",
    )

    count = _count(
        calibration.get("sample_size"),
        "BUCKET_SAMPLE_COUNT_INVALID",
    )

    _require(
        count <= comparable,
        "CALIBRATION_SAMPLE_COUNTS_INCONSISTENT",
    )

    p = _probability(
        calibration.get("calibrated_probability"),
        "CALIBRATED_PROBABILITY_INVALID",
        optional=True,
    )

    lo = _probability(
        calibration.get("lower95"),
        "LOWER_95_INVALID",
        optional=True,
    )

    hi = _probability(
        calibration.get("upper95"),
        "UPPER_95_INVALID",
        optional=True,
    )

    _require(
        prediction.get("calibrated_probability")
        == calibration.get("calibrated_probability"),
        "CALIBRATION_PROBABILITY_MISMATCH",
    )

    if state == "CALIBRATED":
        _require(
            p is not None
            and lo is not None
            and hi is not None
            and lo <= p <= hi
            and count > 0,
            "CALIBRATION_INTERVAL_INVALID",
        )
    else:
        _require(
            p is None
            and lo is None
            and hi is None,
            "UNCALIBRATED_PROBABILITY_NOT_ALLOWED",
        )

    # Sin señal técnica no debe haber métricas de TP/SL.
    if signal_id is None:
        _require(
            raw_tp is None
            and raw_sl is None
            and state == "RAW_ONLY",
            "SIGNAL_FREE_PREDICTION_HAS_SIGNAL_METRICS",
        )

    # Si Kronos está degradado, no exponemos una
    # probabilidad calibrada como evidencia utilizable.
    effective_p = p if not degraded else None
    effective_lo = lo if not degraded else None
    effective_hi = hi if not degraded else None

    # 8. Evidencia estructurada para Sol.
    payload = {
        "schema": EVIDENCE_SCHEMA,
        "prediction_id": prediction_id,
        "symbol": symbol,
        "timeframe": timeframe,
        "signal_id": signal_id,
        "strategy_id": strategy_id,
        "source_partition": partition,
        "model_version": model_version,
        "tokenizer_version": tokenizer_version,
        "config_hash": config_hash,
        "samples_sha256": samples_hash,
        "artifact_integrity": (
            "HASH_REFERENCE_ONLY_NOT_VERIFIED_HERE"
        ),
        "created_at_utc": created.isoformat(),
        "candle_timestamp_utc": candle.isoformat(),
        "prediction_age_seconds": prediction_age,
        "candle_age_seconds": candle_age,
        "health": (
            "DEGRADED" if degraded else "READY"
        ),
        "valid_paths": valid_paths,
        "invalid_paths": invalid_paths,
        "predicted_return_median": median_return,
        "raw_tp_frequency": raw_tp,
        "raw_sl_frequency": raw_sl,
        "neither_frequency": neither,
        "sample_count": sample_count,
        "calibration_state": state,
        "comparable_samples": comparable,
        "bucket_samples": count,
        "calibrated_tp_probability": effective_p,
        "calibrated_lower95": effective_lo,
        "calibrated_upper95": effective_hi,
        "raw_frequencies_are_calibrated": False,
        "research_usable": not degraded,
        "execution_authority": False,
        "paper_execution_eligible": False,
        "live_enabled": False,
    }

    # 9. Huella reproducible del contenido.
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")

    payload["evidence_sha256"] = (
        sha256(canonical).hexdigest()
    )

    return payload
