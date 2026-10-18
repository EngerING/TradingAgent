"""Economic bindings cannot be supplied as approval flags."""
from dataclasses import replace
from datetime import timedelta
import unittest

from test_core_v3_research_contracts import AT, request
from test_core_v34_contracts import close, sma
from trading_agent.core_v3.contracts import ContractError, content_hash
from trading_agent.core_v3.economic_contracts import Direction
from trading_agent.core_v3.strategy_v34.contracts import Operator, Rule, Strategy, Timeframe
from trading_agent.core_v3.strategy_v34.designer import SimulatedStrategyDesigner, design
from trading_agent.core_v3.strategy_v34.validation import validate


class StrategyDesignTests(unittest.TestCase):
    def test_deterministic_multiinstrument_both_directions_all_timeframes(self):
        for stock in (False, True):
            for direction in Direction:
                for timeframe in Timeframe:
                    with self.subTest(stock=stock, direction=direction, timeframe=timeframe):
                        req = request(stock=stock, direction=direction)
                        result = design(req, timeframe, SimulatedStrategyDesigner(), now=AT)
                        self.assertEqual(result, design(req, timeframe, SimulatedStrategyDesigner(), now=AT))
                        self.assertEqual(result, Strategy.from_json(result.to_json()))
                        self.assertEqual(content_hash(req), result.request_sha256)
                        checked = validate(result, req, timeframe, now=AT)
                        self.assertEqual(result.scenario, checked.witness)
                        self.assertFalse(checked.execution_authority)
                        self.assertEqual('POSTFLIGHT', checked.stage)
                        self.assertEqual(3600, result.max_holding_bars * timeframe.seconds)

    def test_request_timeframe_and_instrument_are_rigid(self):
        req = request()
        value = design(req, Timeframe.M1, SimulatedStrategyDesigner(), now=AT)
        for other in [request(name='another'), request(stock=True), request(direction=Direction.SHORT)]:
            with self.subTest(other=other.request_id), self.assertRaises(ContractError):
                validate(value, other, Timeframe.M1, now=AT)
        with self.assertRaises(ContractError):
            validate(value, req, Timeframe.M5, now=AT)

    def test_full_geometry_mutation_is_rejected(self):
        req = request()
        value = design(req, Timeframe.M1, SimulatedStrategyDesigner(), now=AT)
        scenario = value.scenario
        for change in [dict(quantity=replace(scenario.quantity, amount=scenario.quantity.amount + 1)),
                       dict(entry=replace(scenario.entry, amount=scenario.entry.amount + req.inputs.context.market.instrument.tick.amount)),
                       dict(stop=replace(scenario.stop, amount=scenario.stop.amount - req.inputs.context.market.instrument.tick.amount)),
                       dict(target=replace(scenario.target, amount=scenario.target.amount + req.inputs.context.market.instrument.tick.amount)),
                       dict(horizon_hours=2), dict(context_sha256='0'*64), dict(policy_sha256='0'*64)]:
            with self.subTest(change=change), self.assertRaises(ContractError):
                validate(replace(value, scenario=replace(scenario, **change)), req, Timeframe.M1, now=AT)

    def test_horizon_and_rule_limits(self):
        value = design(request(), Timeframe.M1, SimulatedStrategyDesigner(), now=AT)
        for change in [dict(max_holding_bars=59), dict(entry_rules=()), dict(exit_rules=()),
                       dict(entry_rules=[value.entry_rules[0]]), dict(entry_rules=value.entry_rules*9),
                       dict(exit_rules=value.exit_rules*2)]:
            with self.subTest(change=change), self.assertRaises(ContractError):
                replace(value, **change)

    def test_expiry_unknown_economics_and_future_request_fail_closed(self):
        req = request()
        value = design(req, Timeframe.M1, SimulatedStrategyDesigner(), now=AT)
        with self.assertRaises(ContractError):
            validate(value, req, Timeframe.M1, now=AT + timedelta(seconds=31))
        for other in [replace(req, inputs=replace(req.inputs, context=replace(req.inputs.context, costs=None))),
                      replace(req, instrument=replace(req.instrument, content_sha256='0'*64))]:
            with self.assertRaises(ContractError):
                design(other, Timeframe.M1, SimulatedStrategyDesigner(), now=AT)
        with self.assertRaises(ContractError):
            design(req, Timeframe.M1, SimulatedStrategyDesigner(), now=AT-timedelta(seconds=1))

    def test_authority_fields_and_source_code_cannot_enter_strategy(self):
        value = design(request(), Timeframe.M1, SimulatedStrategyDesigner(), now=AT)
        for field, content in [('execution_authority', True), ('paper_execution_eligible', True),
                               ('live_enabled', True), ('statistically_validated', True),
                               ('trading_decision', 'BUY'), ('code', 'print(1)'), ('schema_version', 2)]:
            data = value.to_dict()
            data[field] = content
            with self.subTest(field=field), self.assertRaises(ContractError):
                Strategy.from_dict(data)

    def test_plugins_subclasses_and_forged_designer_outputs_are_rejected(self):
        class Plugin(SimulatedStrategyDesigner):
            pass
        for designer in [Plugin(), lambda req: None, object()]:
            with self.assertRaises(ContractError):
                design(request(), Timeframe.M1, designer, now=AT)
        value = design(request(), Timeframe.M1, SimulatedStrategyDesigner(), now=AT)
        changed = replace(value, entry_rules=(Rule(close(), Operator.GT, sma(4)),))
        bad = SimulatedStrategyDesigner(changed.to_json())
        with self.assertRaisesRegex(ContractError, 'SIMULATED_OUTPUT_MISMATCH'):
            design(request(), Timeframe.M1, bad, now=AT)
        with self.assertRaises(ContractError):
            design(request(), Timeframe.M1, SimulatedStrategyDesigner('{bad'), now=AT)

    def test_explicit_custom_rules_can_be_validated_without_claiming_simulated_provenance(self):
        req = request()
        value = design(req, Timeframe.M1, SimulatedStrategyDesigner(), now=AT)
        custom = replace(value, entry_rules=(Rule(close(1), Operator.LT, sma(5)),))
        self.assertEqual(custom.scenario, validate(custom, req, Timeframe.M1, now=AT).witness)
