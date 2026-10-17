"""Acceso local de solo lectura a la credencial OpenAI protegida con DPAPI.

No administra permisos de IBKR, no envia solicitudes y no registra secretos.
"""

import os
from pathlib import Path

from ..paper_lab import unseal


class SolCredentialError(RuntimeError):
    """Error controlado; nunca incluye el secreto original."""


def credential_path() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        raise SolCredentialError("LOCALAPPDATA_UNAVAILABLE")

    return (
        Path(base)
        / "TradingAgent"
        / "secrets"
        / "openai-sol-credentials.dpapi"
    )


def load_openai_api_key() -> str:
    path = credential_path()

    if not path.is_file():
        raise SolCredentialError("SOL_CREDENTIAL_MISSING")

    if path.stat().st_size == 0:
        raise SolCredentialError("SOL_CREDENTIAL_EMPTY")

    try:
        record = unseal(path)
    except Exception:
        raise SolCredentialError("SOL_CREDENTIAL_DECRYPTION_FAILED") from None

    if not isinstance(record, dict):
        raise SolCredentialError("SOL_CREDENTIAL_INVALID_STRUCTURE")

    key = record.get("api_key")

    if (
        record.get("schema_version") != 1
        or record.get("provider") != "openai"
        or not isinstance(key, str)
        or not key.startswith("sk-")
    ):
        raise SolCredentialError("SOL_CREDENTIAL_INVALID_STRUCTURE")

    return key


def credential_status() -> dict:
    load_openai_api_key()

    return {
        "status": "SOL_CREDENTIAL_READY",
        "storage": "WINDOWS_DPAPI_CURRENT_USER",
        "source": "LOCAL_APPDATA",
        "secret_exposed": False,
        "execution_authority": False,
    }


if __name__ == "__main__":
    print("SOL_SECURE_CREDENTIALS_MODULE_OK")
    for name, value in credential_status().items():
        print(f"{name.upper()}: {value}")
