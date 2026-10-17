
"""Puente de observacion R20 (Python principal) a Kronos (Python aislado).

Solo investigacion: no ordenes, no escritura al diario y no llamadas OpenAI.
La procedencia autentica exige invocar Once desde el observador de confianza;
los hashes JSON no autentican por si solos a un emisor arbitrario.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from datetime import datetime, timezone


CONTRACT = "R20_KRONOS_BRIDGE_V1"
MAX_INPUT_BYTES = 1_000_000
MAX_OUTPUT_BYTES = 100_000
TIMEOUT_SECONDS = 240
_SAFE_ERROR = re.compile(r"[A-Z][A-Z0-9_]{2,100}\Z")


class BridgeError(RuntimeError):
    """Error clasificado; nunca contiene secretos ni datos completos."""


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise BridgeError(code)


def _json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _parse_json(data: bytes) -> dict:
    _require(len(data) <= MAX_INPUT_BYTES, "BRIDGE_INPUT_TOO_LARGE")

    try:
        def unique_pairs(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("DUPLICATE_JSON_KEY")
                result[key] = value
            return result

        value = json.loads(
            data,
            object_pairs_hook=unique_pairs,
            parse_constant=lambda _: (
                _ for _ in ()
            ).throw(ValueError()),
        )

    except (ValueError, UnicodeDecodeError):
        raise BridgeError("BRIDGE_JSON_INVALID") from None

    _require(type(value) is dict, "BRIDGE_ENVELOPE_INVALID")
    return value


def _isolated_environment(root: Path) -> dict[str, str]:
    """Allowlist: no transfiere contrasenas, claves IBKR ni credenciales DB."""
    allowed = (
        "SystemRoot",
        "WINDIR",
        "PATH",
        "TEMP",
        "TMP",
        "USERPROFILE",
        "LOCALAPPDATA",
        "APPDATA",
        "PROGRAMDATA",
        "CUDA_VISIBLE_DEVICES",
    )

    env = {
        key: os.environ[key]
        for key in allowed
        if key in os.environ
    }

    env.update({
        "PYTHONPATH": str(root / "python"),
        "HF_HOME": str(root / ".local" / "kronos" / "hf-cache"),
        "HF_HUB_OFFLINE": "1",
        "HF_HUB_DISABLE_TELEMETRY": "1",
        "LIVE_TRADING": "false",
        "TOKENIZERS_PARALLELISM": "false",
    })

    return env


def _require_isolation() -> None:
    forbidden = {
        "OPENAI_API_KEY",
        "TRADING_DB",
        "TRADING_LAB_DB",
        "HF_TOKEN",
        "HUGGING_FACE_HUB_TOKEN",
    }

    _require(
        not any(
            name.upper() in forbidden
            or name.upper().startswith(
                ("IBKR_", "TRADING_IBKR_")
            )
            for name in os.environ
        ),
        "KRONOS_WORKER_ENV_NOT_ISOLATED",
    )

    _require(
        os.environ.get("LIVE_TRADING") == "false",
        "LIVE_DISABLED",
    )

    _require(
        os.environ.get("HF_HUB_OFFLINE") == "1",
        "KRONOS_OFFLINE_REQUIRED",
    )


def _verify_request(envelope: dict, config: dict) -> dict:
    """Validacion repetida en el proceso Kronos, antes de cargar pesos."""
    from .contracts import digest
    from .features import validate_input

    _require(
        set(envelope) == {
            "contract",
            "request",
            "request_sha256",
        },
        "BRIDGE_ENVELOPE_FIELDS_INVALID",
    )

    _require(
        envelope["contract"] == CONTRACT,
        "BRIDGE_CONTRACT_MISMATCH",
    )

    request = envelope["request"]

    _require(
        type(request) is dict,
        "BRIDGE_REQUEST_INVALID",
    )

    _require(
        envelope["request_sha256"] == digest(request),
        "BRIDGE_REQUEST_HASH_MISMATCH",
    )

    _require(
        request.get("partition") == "FORWARD",
        "BRIDGE_FORWARD_ONLY",
    )

    _require(
        request.get("signal") is None,
        "BRIDGE_SIGNAL_NOT_SUPPORTED_V1",
    )

    source = request.get("source")

    _require(
        type(source) is dict
        and source.get("provider") == "R20_IBKR_PAPER_READ_ONLY"
        and source.get("provenance_scope")
        == "TRUSTED_IN_PROCESS_R20_OBSERVER"
        and source.get("broker_orders") == 0,
        "BRIDGE_SOURCE_INVALID",
    )

    validate_input(request, config)

    return request


def _worker(root: Path) -> dict:
    """Sin imports de IBKR, sin conexion DB y sin permisos de ordenes."""
    _require_isolation()

    from .config import load
    from .contracts import instant
    from .adapter import LocalKronosAdapter
    from .predictor import KronosPredictionService
    from trading_agent.ai_strategy_researcher.kronos_evidence import (
        build_kronos_evidence,
    )

    config = load(root)

    envelope = _parse_json(
        sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
    )

    request = _verify_request(envelope, config)

    now = datetime.now(timezone.utc)

    _require(
        0 <= (
            now - instant(request["as_of"])
        ).total_seconds() <= config["max_input_age_seconds"],
        "BRIDGE_SOURCE_STALE",
    )

    service = KronosPredictionService(
        root,
        config,
        LocalKronosAdapter(root, config),
    )

    try:
        # Sin senal y sin registros de calibracion: observacion pura.
        prediction = service.predict(
            request,
            records=[],
        )
    finally:
        service.close()

    evidence = build_kronos_evidence(
        prediction,
        now=datetime.now(timezone.utc),
        expected_symbol=config["symbol"],
        expected_timeframe=config["timeframe"],
        max_prediction_age_seconds=config[
            "max_prediction_age_seconds"
        ],
        max_candle_age_seconds=config[
            "max_input_age_seconds"
        ],
    )

    _require(
        evidence["execution_authority"] is False,
        "BRIDGE_EXECUTION_NOT_ALLOWED",
    )

    # No se persiste el resultado en PostgreSQL ni se llama a Sol.
    return {
        "status": "KRONOS_EVIDENCE_GENERATED",
        "evidence": evidence,
    }


def _once(root: Path) -> dict:
    """Lectura real de IBKR desde .venv y subprocess Kronos aislado."""
    from .config import load
    from .contracts import digest
    from .r20_source import build_request
    from trading_agent.r20_runner import ReadOnlyObserver

    config = load(root)

    observer = ReadOnlyObserver(
        root,
        client_id=196,
    )

    try:
        observation = observer.poll()
    finally:
        observer.source.close()

    _require(
        observation.get("status") == "READ_ONLY_DIAGNOSTIC",
        "R20_DATA_UNAVAILABLE",
    )

    request = build_request(
        observation,
        config,
        now=datetime.now(timezone.utc),
    )

    envelope = {
        "contract": CONTRACT,
        "request": request,
        "request_sha256": digest(request),
    }

    data = _json_bytes(envelope)

    _require(
        len(data) <= MAX_INPUT_BYTES,
        "BRIDGE_INPUT_TOO_LARGE",
    )

    python = (
        root
        / ".local"
        / "kronos"
        / "venv"
        / "Scripts"
        / "python.exe"
    )

    _require(
        python.is_file(),
        "KRONOS_ISOLATED_ENVIRONMENT_MISSING",
    )

    try:
        completed = subprocess.run(
            [
                str(python),
                "-m",
                "trading_agent.kronos.r20_bridge",
                "_Worker",
                "--root",
                str(root),
            ],
            input=data,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=_isolated_environment(root),
            cwd=root,
            timeout=TIMEOUT_SECONDS,
            check=False,
        )

    except subprocess.TimeoutExpired:
        raise BridgeError("KRONOS_WORKER_TIMEOUT") from None

    except OSError:
        raise BridgeError("KRONOS_WORKER_LAUNCH_FAILED") from None

    _require(
        len(completed.stdout) <= MAX_OUTPUT_BYTES,
        "KRONOS_WORKER_OUTPUT_TOO_LARGE",
    )

    if completed.returncode != 0:
        # Mostrar solamente el codigo clasificado; nunca stderr del hijo.
        try:
            failure = _parse_json(completed.stdout)
        except BridgeError:
            raise BridgeError("KRONOS_WORKER_FAILED") from None

        reason = failure.get("reason")

        if (
            failure.get("status") == "BRIDGE_FAILED"
            and isinstance(reason, str)
            and _SAFE_ERROR.fullmatch(reason)
        ):
            raise BridgeError(reason)

        raise BridgeError("KRONOS_WORKER_FAILED")

    try:
        result = _parse_json(completed.stdout)
    except BridgeError:
        raise BridgeError("KRONOS_WORKER_OUTPUT_INVALID") from None

    _require(
        result.get("status") == "KRONOS_EVIDENCE_GENERATED",
        "KRONOS_WORKER_RESULT_INVALID",
    )

    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="R20 -> Kronos (solo investigacion)"
    )

    parser.add_argument(
        "action",
        choices=("Once", "_Worker"),
    )

    parser.add_argument(
        "--root",
        default=".",
    )

    args = parser.parse_args(argv)
    root = Path(args.root).resolve()

    try:
        if args.action == "_Worker":
            output = _worker(root)
        else:
            output = _once(root)

        print(
            _json_bytes(output).decode("utf-8"),
            flush=True,
        )

        return 0

    except Exception as exc:
        # No imprimir traceback, stderr ni cadenas con posibles secretos.
        code = (
           str(exc)
    if isinstance(exc, BridgeError)
    else "BRIDGE_" + type(exc).__name__.upper()
        )

        if not _SAFE_ERROR.fullmatch(code):
            code = "BRIDGE_UNEXPECTED_ERROR"

        print(
            _json_bytes({
                "status": "BRIDGE_FAILED",
                "reason": code,
            }).decode("utf-8"),
            flush=True,
        )

        return 1


if __name__ == "__main__":
    raise SystemExit(main())
