"""Contrato de candidatas Forex V2: investigacion, nunca ejecucion."""

import re
from copy import deepcopy

SCHEMA = "FOREX_STRATEGY_CANDIDATE_V2"

DIRECTIONS = frozenset(("LONG", "SHORT"))
TIMEFRAMES = frozenset(("15M", "1H", "4H"))
PROFILES = frozenset(("CONSERVATIVE", "MODERATE", "AGGRESSIVE"))

REQUIRED = frozenset((
    "schema",
    "strategy_id",
    "version",
    "instrument",
    "timeframe",
    "direction",
    "risk_profile",
    "hypothesis",
    "entry_spec",
    "exit_spec",
    "research_capital_usd",
    "execution_authority",
    "paper_execution_eligible",
    "live_enabled",
))

class ForexV2ContractError(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise ForexV2ContractError(code)


def validate_candidate(candidate):
    """Valida el sobre de investigacion, no compila reglas operativas."""
    require(type(candidate) is dict, "CANDIDATE_OBJECT_REQUIRED")
    require(set(candidate) == REQUIRED, "CANDIDATE_FIELDS_INVALID")

    require(candidate["schema"] == SCHEMA, "SCHEMA_INVALID")
    require(
        isinstance(candidate["strategy_id"], str)
        and re.fullmatch(r"[a-z][a-z0-9_-]{2,63}", candidate["strategy_id"])
        is not None,
        "STRATEGY_ID_INVALID",
    )
    require(
        type(candidate["version"]) is int and candidate["version"] >= 1,
        "STRATEGY_VERSION_INVALID",
    )
    require(candidate["instrument"] == "EUR/USD", "INSTRUMENT_INVALID")
    require(candidate["timeframe"] in TIMEFRAMES, "TIMEFRAME_INVALID")
    require(candidate["direction"] in DIRECTIONS, "DIRECTION_INVALID")
    require(candidate["risk_profile"] in PROFILES, "RISK_PROFILE_INVALID")
    require(
        isinstance(candidate["hypothesis"], str)
        and 20 <= len(candidate["hypothesis"]) <= 2000,
        "HYPOTHESIS_INVALID",
    )

    for name in ("entry_spec", "exit_spec"):
        spec = candidate[name]
        require(
            type(spec) is dict
            and set(spec) == {"description"}
            and isinstance(spec["description"], str)
            and 10 <= len(spec["description"]) <= 1000,
            f"{name.upper()}_INVALID",
        )

    require(
        type(candidate["research_capital_usd"]) is int
        and candidate["research_capital_usd"] == 100,
        "RESEARCH_CAPITAL_INVALID",
    )

    require(
        candidate["execution_authority"] is False
        and candidate["paper_execution_eligible"] is False
        and candidate["live_enabled"] is False,
        "EXECUTION_AUTHORITY_FORBIDDEN",
    )

    result = deepcopy(candidate)
    result["contract_status"] = "RESEARCH_CANDIDATE_ONLY"
    result["rules_compiled"] = False
    result["backtested"] = False
    result["risk_approved"] = False
    result["trading_decision"] = "NO_TRADE"
    return result


if __name__ == "__main__":
    example = {
        "schema": SCHEMA,
        "strategy_id": "eurusd-fvg-research-v1",
        "version": 1,
        "instrument": "EUR/USD",
        "timeframe": "15M",
        "direction": "SHORT",
        "risk_profile": "AGGRESSIVE",
        "hypothesis": (
            "Investigar retrocesos FVG durante la apertura "
            "de Nueva York bajo condiciones de volatilidad."
        ),
        "entry_spec": {
            "description": "Retroceso hacia FVG bajista confirmado."
        },
        "exit_spec": {
            "description": "Stop y objetivo sujetos a evaluacion economica."
        },
        "research_capital_usd": 100,
        "execution_authority": False,
        "paper_execution_eligible": False,
        "live_enabled": False,
    }

    result = validate_candidate(example)

    assert result["risk_profile"] == "AGGRESSIVE"
    assert result["direction"] == "SHORT"
    assert result["trading_decision"] == "NO_TRADE"
    assert result["rules_compiled"] is False

    unsafe = deepcopy(example)
    unsafe["execution_authority"] = True

    try:
        validate_candidate(unsafe)
    except ForexV2ContractError as exc:
        assert str(exc) == "EXECUTION_AUTHORITY_FORBIDDEN"
    else:
        raise AssertionError("UNSAFE_CANDIDATE_ACCEPTED")

    print("FOREX_V2_CONTRACT_TEST_OK")
    print("DIRECTION:", result["direction"])
    print("RISK_PROFILE:", result["risk_profile"])
    print("CAPITAL_USD:", result["research_capital_usd"])
    print("CONTRACT_STATUS:", result["contract_status"])
    print("RULES_COMPILED:", result["rules_compiled"])
    print("TRADING_DECISION:", result["trading_decision"])
    print("UNSAFE_AUTHORITY_REJECTED: True")
