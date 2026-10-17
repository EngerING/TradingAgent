"""Reglas deterministas Forex V2, exclusivas de investigacion.

No calcula indicadores, no consulta mercado y no ejecuta ordenes.
Solo acepta datos numericos ya calculados de velas cerradas.
"""

import math

SCHEMA = "FOREX_STRATEGY_RULES_V2"

FIELDS = frozenset((
    "close",
    "ema20",
    "ema50",
    "rsi14",
    "atr14",
    "prev_close",
    "prev_ema20",
    "prev_ema50",
))

OPERATORS = frozenset((">", "<", ">=", "<="))


class ForexRuleError(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise ForexRuleError(code)


def numeric(value):
    require(
        type(value) in (int, float)
        and math.isfinite(value),
        "NUMERIC_VALUE_INVALID",
    )
    return float(value)


def validate_condition(condition):
    require(
        type(condition) is dict,
        "CONDITION_OBJECT_REQUIRED",
    )
    require(
        set(condition) == {"left", "operator", "right"},
        "CONDITION_FIELDS_INVALID",
    )
    require(
        condition["left"] in FIELDS,
        "LEFT_FIELD_NOT_ALLOWED",
    )
    require(
        condition["operator"] in OPERATORS,
        "OPERATOR_NOT_ALLOWED",
    )

    right = condition["right"]

    if isinstance(right, str):
        require(
            right in FIELDS,
            "RIGHT_FIELD_NOT_ALLOWED",
        )
    else:
        numeric(right)

    return True


def validate_rule(rule):
    require(type(rule) is dict, "RULE_OBJECT_REQUIRED")
    require(set(rule) == {"all"}, "RULE_STRUCTURE_INVALID")

    conditions = rule["all"]

    require(
        type(conditions) is list
        and 1 <= len(conditions) <= 8,
        "CONDITION_COUNT_INVALID",
    )

    for condition in conditions:
        validate_condition(condition)

    return True


def validate_rules(rules):
    require(type(rules) is dict, "RULES_OBJECT_REQUIRED")

    require(
        set(rules) == {"schema", "direction", "entry", "exit"},
        "RULES_FIELDS_INVALID",
    )
    require(rules["schema"] == SCHEMA, "RULES_SCHEMA_INVALID")
    require(
        rules["direction"] in ("LONG", "SHORT"),
        "DIRECTION_INVALID",
    )

    validate_rule(rules["entry"])
    validate_rule(rules["exit"])

    return True


def evaluate_condition(condition, snapshot):
    left = numeric(snapshot[condition["left"]])

    right_value = condition["right"]

    if isinstance(right_value, str):
        right = numeric(snapshot[right_value])
    else:
        right = numeric(right_value)

    op = condition["operator"]

    if op == ">":
        return left > right
    if op == "<":
        return left < right
    if op == ">=":
        return left >= right
    return left <= right


def evaluate_rules(rules, snapshot):
    """Evalua condiciones; nunca emite una orden o senal autorizada."""

    validate_rules(rules)

    require(
        type(snapshot) is dict
        and snapshot.get("bar_closed") is True,
        "CLOSED_BAR_REQUIRED",
    )

    used = set()

    for group in ("entry", "exit"):
        for condition in rules[group]["all"]:
            used.add(condition["left"])

            if isinstance(condition["right"], str):
                used.add(condition["right"])

    for field in used:
        require(field in snapshot, "SNAPSHOT_FIELD_MISSING")
        numeric(snapshot[field])

    entry = all(
        evaluate_condition(condition, snapshot)
        for condition in rules["entry"]["all"]
    )

    exit_met = all(
        evaluate_condition(condition, snapshot)
        for condition in rules["exit"]["all"]
    )

    if entry and exit_met:
        state = "CONFLICT_NO_TRADE"
    elif exit_met:
        state = "RESEARCH_EXIT_CONDITION_MET"
    elif entry:
        state = "RESEARCH_ENTRY_CONDITION_MET"
    else:
        state = "NO_CONDITION_MET"

    return {
        "schema": "FOREX_RULE_EVALUATION_V2",
        "direction": rules["direction"],
        "entry_condition_met": entry,
        "exit_condition_met": exit_met,
        "research_state": state,
        "trading_decision": "NO_TRADE",
        "execution_authority": False,
        "paper_execution_eligible": False,
        "live_enabled": False,
    }


if __name__ == "__main__":
    long_rules = {
        "schema": SCHEMA,
        "direction": "LONG",
        "entry": {
            "all": [
                {"left": "ema20", "operator": ">", "right": "ema50"},
                {"left": "rsi14", "operator": "<", "right": 70},
            ]
        },
        "exit": {
            "all": [
                {"left": "ema20", "operator": "<", "right": "ema50"}
            ]
        },
    }

    short_rules = {
        "schema": SCHEMA,
        "direction": "SHORT",
        "entry": {
            "all": [
                {"left": "ema20", "operator": "<", "right": "ema50"},
                {"left": "rsi14", "operator": ">", "right": 30},
            ]
        },
        "exit": {
            "all": [
                {"left": "ema20", "operator": ">", "right": "ema50"}
            ]
        },
    }

    long_snapshot = {
        "bar_closed": True,
        "ema20": 1.1250,
        "ema50": 1.1200,
        "rsi14": 55,
    }

    short_snapshot = {
        "bar_closed": True,
        "ema20": 1.1180,
        "ema50": 1.1230,
        "rsi14": 45,
    }

    long_result = evaluate_rules(long_rules, long_snapshot)
    short_result = evaluate_rules(short_rules, short_snapshot)

    assert long_result["entry_condition_met"] is True
    assert short_result["entry_condition_met"] is True

    for result in (long_result, short_result):
        assert result["trading_decision"] == "NO_TRADE"
        assert result["execution_authority"] is False

    unsafe = {
        "left": "ema20",
        "operator": "__import__",
        "right": "ema50",
    }

    try:
        validate_condition(unsafe)
    except ForexRuleError:
        pass
    else:
        raise AssertionError("UNSAFE_OPERATOR_ACCEPTED")

    try:
        evaluate_rules(long_rules, {
            **long_snapshot,
            "bar_closed": False,
        })
    except ForexRuleError:
        pass
    else:
        raise AssertionError("OPEN_BAR_ACCEPTED")

    print("FOREX_V2_RULE_ENGINE_TEST_OK")
    print("LONG_ENTRY_CONDITION:", long_result["entry_condition_met"])
    print("SHORT_ENTRY_CONDITION:", short_result["entry_condition_met"])
    print("UNSAFE_OPERATOR_REJECTED: True")
    print("OPEN_BAR_REJECTED: True")
    print("TRADING_DECISION: NO_TRADE")
    print("IBKR_ORDERS: 0")
