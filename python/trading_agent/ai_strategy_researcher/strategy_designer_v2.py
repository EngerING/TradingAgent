"""Strategy Designer V2: propuestas de Sol, nunca ordenes.

Construye solicitudes estructuradas y valida candidatos mediante
los contratos Forex V2 existentes. Sin llamadas automaticas.
"""

import json

from .strategy_bundle_v2 import build_bundle, validate_bundle
from .strategy_contracts_v2 import DIRECTIONS, PROFILES


MODEL = "gpt-6.1-sol"
FIELDS = [
    "close", "ema20", "ema50", "rsi14", "atr14",
    "prev_close", "prev_ema20", "prev_ema50",
]


class StrategyDesignerError(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise StrategyDesignerError(code)


def object_schema(properties):
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def string_enum(values):
    return {"type": "string", "enum": list(values)}


def condition_schema():
    return object_schema({
        "left": string_enum(FIELDS),
        "operator": string_enum([">", "<", ">=", "<="]),
        "right": {
            "anyOf": [
                string_enum(FIELDS),
                {"type": "number"},
            ]
        },
    })


def rule_schema():
    return object_schema({
        "all": {
            "type": "array",
            "items": condition_schema(),
        }
    })


def proposal_schema():
    candidate = object_schema({
        "schema": string_enum(["FOREX_STRATEGY_CANDIDATE_V2"]),
        "strategy_id": {"type": "string"},
        "version": {"type": "integer"},
        "instrument": string_enum(["EUR/USD"]),
        "timeframe": string_enum(["15M", "1H", "4H"]),
        "direction": string_enum(["LONG", "SHORT"]),
        "risk_profile": string_enum([
            "CONSERVATIVE", "MODERATE", "AGGRESSIVE"
        ]),
        "hypothesis": {"type": "string"},
        "entry_spec": object_schema({
            "description": {"type": "string"}
        }),
        "exit_spec": object_schema({
            "description": {"type": "string"}
        }),
        "research_capital_usd": {"type": "integer", "enum": [100]},
        "execution_authority": {"type": "boolean", "enum": [False]},
        "paper_execution_eligible": {"type": "boolean", "enum": [False]},
        "live_enabled": {"type": "boolean", "enum": [False]},
    })

    rules = object_schema({
        "schema": string_enum(["FOREX_STRATEGY_RULES_V2"]),
        "direction": string_enum(["LONG", "SHORT"]),
        "entry": rule_schema(),
        "exit": rule_schema(),
    })

    return object_schema({
        "candidate": candidate,
        "rules": rules,
    })


def build_design_request(config, *, direction, risk_profile):
    """Una candidata por solicitud; sin bucles ni ejecucion."""

    require(
        direction in DIRECTIONS,
        "DESIGN_DIRECTION_INVALID",
    )
    require(
        risk_profile in PROFILES,
        "DESIGN_RISK_PROFILE_INVALID",
    )
    require(
        config.get("model") == MODEL,
        "DESIGN_MODEL_INVALID",
    )

    tokens = config.get("max_output_tokens")

    require(
        type(tokens) is int and 512 <= tokens <= 4096,
        "DESIGN_TOKEN_LIMIT_INVALID",
    )

    instructions = (
        "Eres un investigador cuantitativo de Forex. "
        "Propone exactamente UNA hipotesis de estrategia EUR/USD. "
        "Debes cumplir el esquema JSON proporcionado. "
        "Utiliza exclusivamente indicadores y operadores "
        "admitidos por el esquema. "
        "Crea entre 1 y 8 condiciones para entrada y salida. "
        "Las reglas deben ser verificables mediante datos "
        "de velas cerradas. "
        "No inventes rendimientos, probabilidades, "
        "backtests, datos actuales ni autorizaciones. "
        "El perfil de riesgo es una categoria de investigacion, "
        "no un porcentaje de riesgo autorizado. "
        "No indiques que la estrategia es rentable o aprobada. "
        "El capital experimental es USD 100. "
        "Comisiones, margen y viabilidad estan por evaluar. "
        "No utilices evidencia degradada de Kronos "
        "para justificar predicciones ni operaciones. "
        "No concedas permisos Paper ni Live."
    )

    task = (
        f"Direccion obligatoria: {direction}. "
        f"Perfil solicitado: {risk_profile}. "
        "Define condiciones de entrada y salida "
        "distintas y economicamente investigables. "
        "Usa un identificador descriptivo en minusculas, "
        "version 1, e incluye una hipotesis comprobable. "
        "Las especificaciones en texto deben corresponder "
        "a las reglas estructuradas."
    )

    return {
        "model": MODEL,
        "store": False,
        "max_output_tokens": tokens,
        "input": [
            {"role": "developer", "content": instructions},
            {"role": "user", "content": task},
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "forex_strategy_design_v2",
                "strict": True,
                "schema": proposal_schema(),
            }
        },
    }


def validate_design_proposal(
    proposal_text, *, direction, risk_profile
):
    """Acepta solo contratos compatibles; nunca promueve Paper."""

    require(
        type(proposal_text) is str
        and len(proposal_text) <= 20000,
        "DESIGN_RESPONSE_INVALID",
    )

    try:
        proposal = json.loads(
            proposal_text,
            parse_constant=lambda _: (_ for _ in ()).throw(
                ValueError("NONFINITE_VALUE")
            ),
        )
    except (ValueError, TypeError):
        raise StrategyDesignerError(
            "DESIGN_JSON_INVALID"
        ) from None

    require(
        type(proposal) is dict
        and set(proposal) == {"candidate", "rules"},
        "DESIGN_RESPONSE_STRUCTURE_INVALID",
    )

    try:
        bundle = build_bundle(
            proposal["candidate"], proposal["rules"]
        )
        validate_bundle(bundle)
    except (ValueError, TypeError, KeyError):
        raise StrategyDesignerError(
            "DESIGN_CONTRACT_REJECTED"
        ) from None

    require(
        bundle["candidate"]["direction"] == direction
        and bundle["candidate"]["risk_profile"] == risk_profile,
        "DESIGN_REQUEST_MISMATCH",
    )

    require(
        bundle["execution_authority"] is False
        and bundle["paper_execution_eligible"] is False
        and bundle["live_enabled"] is False
        and bundle["trading_decision"] == "NO_TRADE",
        "DESIGN_AUTHORITY_FORBIDDEN",
    )

    return bundle


if __name__ == "__main__":
    config = {
        "model": MODEL,
        "max_output_tokens": 2048,
    }

    request = build_design_request(
        config,
        direction="SHORT",
        risk_profile="AGGRESSIVE",
    )

    # Respuesta simulada: no se consulta OpenAI.
    mock = {
        "candidate": {
            "schema": "FOREX_STRATEGY_CANDIDATE_V2",
            "strategy_id": "eurusd-ema-short-test",
            "version": 1,
            "instrument": "EUR/USD",
            "timeframe": "1H",
            "direction": "SHORT",
            "risk_profile": "AGGRESSIVE",
            "hypothesis": (
                "Investigar continuacion bajista utilizando "
                "alineacion EMA y filtro de RSI."
            ),
            "entry_spec": {
                "description": "EMA20 menor que EMA50 y RSI superior a 30."
            },
            "exit_spec": {
                "description": "Salir cuando EMA20 supere EMA50."
            },
            "research_capital_usd": 100,
            "execution_authority": False,
            "paper_execution_eligible": False,
            "live_enabled": False,
        },
        "rules": {
            "schema": "FOREX_STRATEGY_RULES_V2",
            "direction": "SHORT",
            "entry": {"all": [
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
            ]},
            "exit": {"all": [
                {
                    "left": "ema20",
                    "operator": ">",
                    "right": "ema50",
                },
            ]},
        },
    }

    bundle = validate_design_proposal(
        json.dumps(mock),
        direction="SHORT",
        risk_profile="AGGRESSIVE",
    )

    assert request["store"] is False
    assert bundle["status"] == "RESEARCH_ONLY"
    assert bundle["backtested"] is False

    altered = json.loads(json.dumps(mock))
    altered["candidate"]["execution_authority"] = True

    try:
        validate_design_proposal(
            json.dumps(altered),
            direction="SHORT",
            risk_profile="AGGRESSIVE",
        )
    except StrategyDesignerError:
        pass
    else:
        raise AssertionError("UNSAFE_PROPOSAL_ACCEPTED")

    print("FOREX_V2_STRATEGY_DESIGNER_TEST_OK")
    print("MODEL:", request["model"])
    print("DIRECTION:", bundle["candidate"]["direction"])
    print("RISK_PROFILE:", bundle["candidate"]["risk_profile"])
    print("CAPITAL_USD:", bundle["candidate"]["research_capital_usd"])
    print("STRATEGY_BUNDLE_VALID: True")
    print("UNSAFE_PROPOSAL_REJECTED: True")
    print("BACKTESTED: False")
    print("TRADING_DECISION: NO_TRADE")
    print("OPENAI_API_CALL: False")
    print("IBKR_ORDERS: 0")
