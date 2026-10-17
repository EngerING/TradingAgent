"""Transporte HTTPS de Sol V2 con credencial DPAPI.

No modifica variables de entorno ni otorga permisos de trading.
"""

import http.client
import re
import ssl

from .providers import encoded, parse_response
from .secure_credentials import load_openai_api_key


def secure_openai_response(body, timeout, connection_factory=None):
    """Una solicitud a Responses API con credencial recuperada de DPAPI."""

    key = load_openai_api_key()

    if (
        not isinstance(key, str)
        or not key
        or "\n" in key
        or "\r" in key
        or len(key) > 512
    ):
        raise ValueError("SOL_API_KEY_INVALID")

    conn = None

    try:
        conn = (connection_factory or http.client.HTTPSConnection)(
            "api.openai.com",
            timeout=timeout,
            context=ssl.create_default_context(),
        )

        conn.request(
            "POST",
            "/v1/responses",
            body=encoded(body),
            headers={
                "Authorization": "Bearer " + key,
                "Content-Type": "application/json",
            },
        )

        response = conn.getresponse()

        if response.status != 200:
            return {
                "usage": None,
                "error": f"OPENAI_HTTP_{response.status}",
                "metadata": {},
            }

        raw = response.read(1_000_001)

        if len(raw) > 1_000_000:
            return {
                "usage": None,
                "error": "PROVIDER_RESPONSE_TOO_LARGE",
                "metadata": {},
            }

        result = parse_response(raw, body["model"])

        request_id = response.getheader("x-request-id")

        if request_id and re.fullmatch(
            r"[A-Za-z0-9_-]{1,120}", request_id
        ):
            result["metadata"]["request_id"] = request_id

        return result

    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return {
            "usage": None,
            "error": "OPENAI_TRANSPORT_OR_RESPONSE_INVALID",
            "metadata": {},
        }

    finally:
        if conn is not None:
            conn.close()
