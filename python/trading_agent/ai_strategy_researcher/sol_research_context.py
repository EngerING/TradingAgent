
"""Contexto verificable Kronos -> Sol, exclusivamente para investigacion.

No importa OpenAI, IBKR ni el ejecutor de operaciones. No verifica por si
solo el origen de IBKR ni los bytes de las trayectorias de Kronos.
"""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import math
import re
from typing import Any, Mapping


CONTEXT_SCHEMA = "SOL_KRONOS_RESEARCH_CONTEXT_V1"
EVIDENCE_SCHEMA = "KRONOS_RESEARCH_EVIDENCE_V1"

_SHA256 = re.compile(r"[a-f0-9]{64}\Z")
_IDENTIFIER = re.compile(r"[A-Za-z0-9_./:@+-]{1,160}\Z")

_CALIBRATION_STATES = frozenset({
    "RAW_ONLY",
    "CALIBRATION_INSUFFICIENT",
    "CALIBRATION_DEGRADED",
    "CALIBRATED",
})


class SolResearchContextError(ValueError):
    """Codigo fijo de rechazo, sin incluir datos del modelo."""


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise SolResearchContextError(code)


def _canonical(value: Any) -> bytes:
    """Serializa de forma reproducible para verificar hashes."""
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError):
        raise SolResearchContextError(
            "INVALID_JSON_EVIDENCE"
        ) from None


def _utc(value: datetime | str, code: str) -> datetime:
    """Exige un timestamp con zona horaria y convierte a UTC."""
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, str):
        try:
            result = datetime.fromisoformat(
                value.replace("Z", "+00:00")
            )
        except ValueError:
            raise SolResearchContextError(code) from None
    else:
        raise SolResearchContextError(code)

    _require(result.tzinfo is not None, code)
    return result.astimezone(timezone.utc)


def _identifier(value: Any, code: str) -> str:
    """No permite contenido libre en campos de identidad."""
    _require(
        isinstance(value, str)
        and _IDENTIFIER.fullmatch(value) is not None,
        code,
    )
    return value


def _hash(value: Any, code: str) -> str:
    """Comprueba el formato de un SHA-256 hexadecimal."""
    _require(
        isinstance(value, str)
        and _SHA256.fullmatch(value) is not None,
        code,
    )
    return value


def _count(value: Any, code: str) -> int:
    """Acepta contadores enteros no negativos y acotados."""
    _require(
        type(value) is int
        and 0 <= value <= 1_000_000,
        code,
    )
    return value


def _finite(value: Any, code: str) -> float:
    """Rechaza booleanos, NaN e infinitos."""
    _require(
        type(value) in (int, float)
        and math.isfinite(value),
        code,
    )
    return float(value)


def _probability(value: Any, code: str) -> float | None:
    """Las probabilidades deben estar entre cero y uno."""
    if value is None:
        return None

    number = _finite(value, code)
    _require(0 <= number <= 1, code)
    return number


def build_sol_research_context(
    evidence: Mapping[str, Any],
    *,
    now: datetime | str,
    max_prediction_age_seconds: int,
    max_candle_age_seconds: int,
) -> dict[str, Any]:
    """Prepara contexto para investigar, nunca para operar.

    Evidencia degradada o caducada: solo diagnostico.
    RAW_ONLY: permite investigar hipotesis, no afirmar
    probabilidades reales de operaciones ganadoras.
    """

    # 1. Contrato y limites de antiguedad.
    _require(
        isinstance(evidence, Mapping),
        "EVIDENCE_REQUIRED",
    )
    _require(
        type(max_prediction_age_seconds) is int
        and max_prediction_age_seconds > 0,
        "PREDICTION_AGE_POLICY_INVALID",
    )
    _require(
        type(max_candle_age_seconds) is int
        and max_candle_age_seconds > 0,
        "CANDLE_AGE_POLICY_INVALID",
    )

    # 2. Integridad del resumen recibido.
    supplied_hash = _hash(
        evidence.get("evidence_sha256"),
        "EVIDENCE_HASH_INVALID",
    )

    material = dict(evidence)
    material.pop("evidence_sha256", None)

    _require(
        sha256(_canonical(material)).hexdigest()
        == supplied_hash,
        "EVIDENCE_HASH_MISMATCH",
    )

    _require(
        evidence.get("schema") == EVIDENCE_SCHEMA,
        "EVIDENCE_SCHEMA_INVALID",
    )

    _require(
        evidence.get("artifact_integrity")
        == "HASH_REFERENCE_ONLY_NOT_VERIFIED_HERE",
        "ARTIFACT_INTEGRITY_CLAIM_INVALID",
    )

    # 3. Ninguna autoridad financiera.
    _require(
        evidence.get("execution_authority") is False
        and evidence.get("paper_execution_eligible") is False
        and evidence.get("live_enabled") is False,
        "EXECUTION_AUTHORITY_FORBIDDEN",
    )

    _require(
        evidence.get("source_partition") == "FORWARD",
        "EVIDENCE_PARTITION_INVALID",
    )

    _require(
        evidence.get("raw_frequencies_are_calibrated")
        is False,
        "RAW_CALIBRATION_CLAIM_INVALID",
    )

    # 4. Identidad del instrumento y modelo.
    prediction_id = _identifier(
        evidence.get("prediction_id"),
        "PREDICTION_ID_INVALID",
    )

    _require(
        evidence.get("symbol") == "EUR/USD",
        "INSTRUMENT_SCOPE_INVALID",
    )

    _require(
        evidence.get("timeframe") in ("1H", "4H"),
        "TIMEFRAME_SCOPE_INVALID",
    )

    model_version = _identifier(
        evidence.get("model_version"),
        "MODEL_VERSION_INVALID",
    )

    _identifier(
        evidence.get("tokenizer_version"),
        "TOKENIZER_VERSION_INVALID",
    )

    _hash(
        evidence.get("config_hash"),
        "CONFIG_HASH_INVALID",
    )
    _hash(
        evidence.get("samples_sha256"),
        "SAMPLES_HASH_INVALID",
    )

    # 5. Vigencia real, calculada de nuevo.
    current = _utc(now, "NOW_INVALID")

    created = _utc(
        evidence.get("created_at_utc"),
        "CREATED_AT_INVALID",
    )

    candle = _utc(
        evidence.get("candle_timestamp_utc"),
        "CANDLE_AT_INVALID",
    )

    _require(
        candle <= created <= current,
        "EVIDENCE_TIME_ORDER_INVALID",
    )

    prediction_age = (
        current - created
    ).total_seconds()

    candle_age = (
        current - candle
    ).total_seconds()

    fresh = (
        prediction_age <= max_prediction_age_seconds
        and candle_age <= max_candle_age_seconds
    )

    # 6. Calidad de las trayectorias.
    health = evidence.get("health")

    _require(
        health in ("READY", "DEGRADED"),
        "HEALTH_INVALID",
    )

    valid = _count(
        evidence.get("valid_paths"),
        "VALID_PATHS_INVALID",
    )

    invalid = _count(
        evidence.get("invalid_paths"),
        "INVALID_PATHS_INVALID",
    )

    total = _count(
        evidence.get("sample_count"),
        "SAMPLE_COUNT_INVALID",
    )

    _require(
        total > 0
        and valid > 0
        and valid + invalid == total,
        "SAMPLE_COUNTS_INCONSISTENT",
    )

    _require(
        health != "READY" or invalid == 0,
        "READY_WITH_INVALID_PATHS",
    )

    _require(
        evidence.get("research_usable")
        is (health == "READY"),
        "RESEARCH_HEALTH_MISMATCH",
    )

    # 7. Calibracion y frecuencias.
    state = evidence.get("calibration_state")

    _require(
        state in _CALIBRATION_STATES,
        "CALIBRATION_STATE_INVALID",
    )

    comparable = _count(
        evidence.get("comparable_samples"),
        "COMPARABLE_SAMPLES_INVALID",
    )

    bucket = _count(
        evidence.get("bucket_samples"),
        "BUCKET_SAMPLES_INVALID",
    )

    _require(
        bucket <= comparable,
        "CALIBRATION_COUNTS_INVALID",
    )

    raw_tp = _probability(
        evidence.get("raw_tp_frequency"),
        "RAW_TP_INVALID",
    )

    raw_sl = _probability(
        evidence.get("raw_sl_frequency"),
        "RAW_SL_INVALID",
    )

    neither = _probability(
        evidence.get("neither_frequency"),
        "NEITHER_INVALID",
    )

    p = _probability(
        evidence.get("calibrated_tp_probability"),
        "CALIBRATED_P_INVALID",
    )

    lower = _probability(
        evidence.get("calibrated_lower95"),
        "CALIBRATED_LOWER_INVALID",
    )

    upper = _probability(
        evidence.get("calibrated_upper95"),
        "CALIBRATED_UPPER_INVALID",
    )

    signal_id = evidence.get("signal_id")

    if signal_id is not None:
        _identifier(
            signal_id,
            "SIGNAL_ID_INVALID",
        )

    if signal_id is None:
        _require(
            raw_tp is None
            and raw_sl is None
            and neither is None,
            "SIGNAL_FREE_FREQUENCIES_INVALID",
        )

        _require(
            state == "RAW_ONLY",
            "SIGNAL_FREE_CALIBRATION_INVALID",
        )
    else:
        _require(
            all(
                x is not None
                for x in (raw_tp, raw_sl, neither)
            ),
            "INCOMPLETE_SIGNAL_FREQUENCIES",
        )

        _require(
            abs(
                raw_tp
                + raw_sl
                + neither
                + invalid / total
                - 1
            ) <= 1e-6,
            "FREQUENCIES_INCONSISTENT",
        )

    # Una probabilidad no calibrada no debe
    # convertirse en evidencia operativa.
    if state != "CALIBRATED" or health != "READY":
        _require(
            p is None
            and lower is None
            and upper is None,
            "UNSUPPORTED_CALIBRATION_CLAIM",
        )
    else:
        _require(
            p is not None
            and lower is not None
            and upper is not None
            and lower <= p <= upper
            and bucket > 0,
            "CALIBRATION_INTERVAL_INVALID",
        )

    median_return = _finite(
        evidence.get("predicted_return_median"),
        "MEDIAN_RETURN_INVALID",
    )

    # 8. Motivos por los que no debe tomarse
    # una decision de trading.
    blockers = []

    if not fresh:
        blockers.append("STALE_EVIDENCE")

    if health == "DEGRADED":
        blockers.append("DEGRADED_MODEL_TRAJECTORIES")

    if state != "CALIBRATED":
        blockers.append("NO_CALIBRATED_TP_PROBABILITY")

    if signal_id is None:
        blockers.append("NO_TECHNICAL_SIGNAL")

    # 9. Determinar la actividad de investigacion.
    if not fresh or health == "DEGRADED":
        action = "DIAGNOSE_ONLY"

    elif state != "CALIBRATED":
        action = "PROPOSE_TESTABLE_HYPOTHESES_ONLY"

    else:
        action = "EVALUATE_RESEARCH_HYPOTHESIS_ONLY"

    # 10. Contexto final que recibira Sol.
    result = {
        "schema": CONTEXT_SCHEMA,
        "purpose": "RESEARCH_ONLY_NOT_TRADING_ADVICE",
        "evidence_sha256": supplied_hash,
        "prediction_id": prediction_id,
        "instrument": "EUR/USD",
        "timeframe": evidence["timeframe"],
        "model_version": model_version,
        "as_of_utc": current.isoformat(),
        "prediction_created_at_utc": created.isoformat(),
        "last_closed_candle_utc": candle.isoformat(),
        "prediction_age_seconds": prediction_age,
        "candle_age_seconds": candle_age,
        "fresh": fresh,
        "health": health,
        "sample_count": total,
        "valid_paths": valid,
        "invalid_paths": invalid,
        "predicted_return_median": median_return,
        "signal_id": signal_id,
        "raw_tp_frequency": raw_tp,
        "raw_sl_frequency": raw_sl,
        "neither_frequency": neither,
        "calibration_state": state,
        "comparable_samples": comparable,
        "bucket_samples": bucket,
        "calibrated_tp_probability": p,
        "calibrated_lower95": lower,
        "calibrated_upper95": upper,
        "research_action": action,
        "blocking_reasons": blockers,
        "independent_backtest_required": True,
        "economic_validation_required": True,
        "execution_authority": False,
        "paper_execution_eligible": False,
        "live_enabled": False,
        "trading_decision": "NO_TRADE",
        "provenance_note":
            "EVIDENCE_HASH_ONLY_SOURCE_AND_ARTIFACT_NOT_REVERIFIED",
    }

    # 11. Identidad del contexto de investigacion.
    result["context_sha256"] = sha256(
        _canonical(result)
    ).hexdigest()

    return result
