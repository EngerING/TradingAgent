"""Vincula candidatas Forex V2 con reglas deterministas.

Investigacion exclusivamente. Los hashes identifican contenido,
no autentican su origen ni conceden permisos de ejecucion.
"""

import hashlib
import hmac
import json
from copy import deepcopy

from .strategy_contracts_v2 import validate_candidate
from .strategy_rules_v2 import validate_rules, evaluate_rules


SCHEMA = "FOREX_STRATEGY_BUNDLE_V2"


class ForexBundleError(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise ForexBundleError(code)


def fingerprint(value):
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")

    return hashlib.sha256(payload).hexdigest()


def build_bundle(candidate, rules):
    """Construye una candidata identificable, nunca ejecutable."""

    validated = validate_candidate(candidate)
    validate_rules(rules)

    require(
        validated["direction"] == rules["direction"],
        "CANDIDATE_RULE_DIRECTION_MISMATCH",
    )

    require(
        validated["contract_status"] == "RESEARCH_CANDIDATE_ONLY",
        "CANDIDATE_NOT_RESEARCH_ONLY",
    )

    candidate_copy = deepcopy(candidate)
    rules_copy = deepcopy(rules)

    candidate_hash = fingerprint(candidate_copy)
    rules_hash = fingerprint(rules_copy)

    identity = {
        "strategy_id": candidate_copy["strategy_id"],
        "version": candidate_copy["version"],
        "candidate_sha256": candidate_hash,
        "rules_sha256": rules_hash,
    }

    return {
        "schema": SCHEMA,
        "candidate": candidate_copy,
        "rules": rules_copy,
        "candidate_sha256": candidate_hash,
        "rules_sha256": rules_hash,
        "bundle_sha256": fingerprint(identity),
        "status": "RESEARCH_ONLY",
        "rules_compiled": False,
        "backtested": False,
        "trading_decision": "NO_TRADE",
        "execution_authority": False,
        "paper_execution_eligible": False,
        "live_enabled": False,
    }


def validate_bundle(bundle):
    """Detecta cambios respecto de las huellas declaradas."""

    require(type(bundle) is dict, "BUNDLE_REQUIRED")

    require(
        set(bundle) == {
            "schema",
            "candidate",
            "rules",
            "candidate_sha256",
            "rules_sha256",
            "bundle_sha256",
            "status",
            "rules_compiled",
            "backtested",
            "trading_decision",
            "execution_authority",
            "paper_execution_eligible",
            "live_enabled",
        },
        "BUNDLE_FIELDS_INVALID",
    )

    require(bundle["schema"] == SCHEMA, "BUNDLE_SCHEMA_INVALID")

    expected = build_bundle(
        bundle["candidate"],
        bundle["rules"],
    )

    for field in (
        "candidate_sha256",
        "rules_sha256",
        "bundle_sha256",
    ):
        value = bundle[field]
        require(
            isinstance(value, str)
            and hmac.compare_digest(value, expected[field]),
            "BUNDLE_INTEGRITY_MISMATCH",
        )

    require(
        bundle == expected,
        "BUNDLE_STATE_INVALID",
    )

    return deepcopy(expected)


def evaluate_bundle(bundle, snapshot):
    """Evaluacion tecnica sin decision ni permisos de trading."""

    verified = validate_bundle(bundle)

    result = evaluate_rules(
        verified["rules"],
        snapshot,
    )

    return {
        "bundle_sha256": verified["bundle_sha256"],
        "strategy_id": verified["candidate"]["strategy_id"],
        "version": verified["candidate"]["version"],
        "technical_evaluation": result,
        "economic_validation": "NOT_PERFORMED",
        "backtested": False,
        "trading_decision": "NO_TRADE",
        "execution_authority": False,
        "paper_execution_eligible": False,
        "live_enabled": False,
    }


if __name__ == "__main__":
    candidate = {
        "schema": "FOREX_STRATEGY_CANDIDATE_V2",
        "strategy_id": "eurusd-ema-short-v1",
        "version": 1,
        "instrument": "EUR/USD",
        "timeframe": "1H",
        "direction": "SHORT",
        "risk_profile": "AGGRESSIVE",
        "hypothesis": (
            "Investigar continuidad bajista mediante "
            "EMA20 y EMA50 con confirmacion RSI."
        ),
        "entry_spec": {
            "description": "EMA20 inferior a EMA50 y RSI mayor que 30."
        },
        "exit_spec": {
            "description": "Salida cuando EMA20 supera EMA50."
        },
        "research_capital_usd": 100,
        "execution_authority": False,
        "paper_execution_eligible": False,
        "live_enabled": False,
    }

    rules = {
        "schema": "FOREX_STRATEGY_RULES_V2",
        "direction": "SHORT",
        "entry": {
            "all": [
                {
                    "left": "ema20",
                    "operator": "<",
                    "right": "ema50",
                },
                {
                    "left": "rsi14",
                    "operator": ">",
                    "right": 30,
                },
            ]
        },
        "exit": {
            "all": [
                {
                    "left": "ema20",
                    "operator": ">",
                    "right": "ema50",
                }
            ]
        },
    }

    bundle = build_bundle(candidate, rules)

    assert validate_bundle(bundle) == bundle

    snapshot = {
        "bar_closed": True,
        "ema20": 1.1180,
        "ema50": 1.1230,
        "rsi14": 45,
    }

    result = evaluate_bundle(bundle, snapshot)

    assert (
        result["technical_evaluation"]["entry_condition_met"]
        is True
    )
    assert result["trading_decision"] == "NO_TRADE"

    # Cambiar una regla sin actualizar su identidad debe fallar.
    altered = deepcopy(bundle)
    altered["rules"]["entry"]["all"][1]["right"] = 50

    try:
        validate_bundle(altered)
    except ForexBundleError as exc:
        assert str(exc) == "BUNDLE_INTEGRITY_MISMATCH"
    else:
        raise AssertionError("TAMPERED_BUNDLE_ACCEPTED")

    # Nunca aceptar autoridad de ejecucion.
    unsafe = deepcopy(bundle)
    unsafe["execution_authority"] = True

    try:
        validate_bundle(unsafe)
    except ForexBundleError:
        pass
    else:
        raise AssertionError("EXECUTION_AUTHORITY_ACCEPTED")

    print("FOREX_V2_BUNDLE_TEST_OK")
    print("STRATEGY_ID:", result["strategy_id"])
    print("DIRECTION:", candidate["direction"])
    print("RISK_PROFILE:", candidate["risk_profile"])
    print(
        "ENTRY_CONDITION:",
        result["technical_evaluation"]["entry_condition_met"],
    )
    print("HASH_INTEGRITY: VERIFIED")
    print("MODIFIED_RULE_REJECTED: True")
    print("EXECUTION_AUTHORITY_REJECTED: True")
    print("ECONOMIC_VALIDATION: NOT_PERFORMED")
    print("TRADING_DECISION: NO_TRADE")
    print("IBKR_ORDERS: 0")
