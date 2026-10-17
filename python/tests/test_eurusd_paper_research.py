from copy import deepcopy
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest

from trading_agent.eurusd_paper_research import Simulator, load_profile, exit_decision, instant, number, replay, PROFILE
from trading_agent.paper_lab import DotnetJournal
from trading_agent.ai_strategy_researcher import simulation_memory

ROOT = Path(__file__).resolve().parents[2]
AT = '2026-10-06T14:00:00+00:00'
COSTS = dict(openingCommission='.1', closingCommission='.1', spread='.0001', slippage='.0002', adverseGap='.0001', minimumQuantity='1', quantityStep='1')
STRATEGY = dict(strategy_version='fixture_not_a_real_strategy', version=1)


def signal(at=AT, **updates):
    value = dict(strategy_id='trend', side='BUY', signal_at=at, entry_at=at, entry_midpoint='1.1',
                 stop_distance='.005', take_profit_distance='.025', reasons=[], context={})
    value.update(updates); return value


def bar(at=AT, **updates):
    value = dict(opened_at=at, minutes=15, open='1.1', high='1.101', low='1.099', close='1.1')
    value.update(updates); return value


class InternalSimulatorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.path = Path(self.tmp.name)/'journal.sqlite3'
        self.profile = load_profile(ROOT)
        self.sim = Simulator(self.path, self.profile, COSTS, STRATEGY, positive_expectancy_evidence=True)

    def tearDown(self):
        self.sim.db.close(); self.tmp.cleanup()

    def reopen(self):
        self.sim.db.close(); self.sim = Simulator(self.path, self.profile, COSTS, STRATEGY, positive_expectancy_evidence=True)

    def test_observed_fees_cannot_be_funded_by_one_percent(self):
        self.sim.costs = {**COSTS, 'openingCommission':'2','closingCommission':'2'}
        d = self.sim.enter(signal())
        self.assertEqual('COMMISSION_EXCEEDS_RISK_BUDGET', d['reason']); self.assertEqual('1.00', d['budget'])
        self.assertIsNone(self.sim.state['position'])

    def test_position_size_includes_all_costs_and_gap(self):
        d = self.sim.enter(signal()); q = Decimal(d['quantity'])
        self.assertTrue(d['admitted']); self.assertLessEqual(Decimal(d['risk']), 1)
        self.assertEqual(Decimal('.2')+q*Decimal('.0054'), Decimal(d['risk']))
        self.assertLessEqual(Decimal(d['notional'])+Decimal(d['costs']), 100)

    def test_no_positive_expectancy_evidence_rejected(self):
        self.sim.expectancy = False
        self.assertEqual('NET_EXPECTANCY_EVIDENCE_INSUFFICIENT', self.sim.enter(signal())['reason'])

    def test_one_position_only(self):
        self.sim.enter(signal())
        self.assertEqual('RESULT_RECONCILIATION_PENDING', self.sim.enter(signal('2026-10-06T14:15:00+00:00'))['reason'])

    def test_loss_stops_day_and_restart_cannot_erase_it(self):
        self.sim.enter(signal()); self.sim.close('1.095','2026-10-06T14:15:00+00:00','STOP')
        consumed = self.sim.state['consumed_loss']; self.reopen()
        self.assertEqual(consumed,self.sim.state['consumed_loss'])
        self.assertEqual('DAILY_FIRST_LOSS_STOP',self.sim.enter(signal('2026-10-06T14:30:00+00:00'))['reason'])

    def test_profit_allows_another_signal(self):
        self.sim.enter(signal()); self.sim.close('1.12','2026-10-06T14:15:00+00:00','TAKE_PROFIT')
        self.assertTrue(self.sim.enter(signal('2026-10-06T14:30:00+00:00'))['admitted'])

    def test_gains_never_restore_consumed_losses(self):
        self.sim.enter(signal()); self.sim.close('1.095','2026-10-06T14:15:00+00:00','STOP')
        loss = self.sim.state['consumed_loss']
        self.sim.enter(signal('2026-10-07T14:00:00+00:00')); self.sim.close('1.12','2026-10-07T14:15:00+00:00','TAKE_PROFIT')
        self.assertEqual(loss,self.sim.state['consumed_loss'])

    def test_break_even_ends_day(self):
        self.sim.costs = {**COSTS,'spread':'0','slippage':'0','openingCommission':'0','closingCommission':'0'}
        self.sim.enter(signal()); t = self.sim.close('1.1','2026-10-06T14:15:00+00:00','BREAK_EVEN')
        self.assertEqual(Decimal(0),Decimal(t['net_pnl']))
        self.assertEqual('DAILY_NON_POSITIVE_STOP',self.sim.enter(signal('2026-10-06T14:30:00+00:00'))['reason'])

    def test_commission_pending_retains_position_after_restart(self):
        self.sim.enter(signal()); self.sim.close('1.12','2026-10-06T14:15:00+00:00','TARGET',commission_pending=True)
        self.reopen(); self.assertEqual([],self.sim.state['trades'])
        self.assertEqual('RESULT_RECONCILIATION_PENDING',self.sim.enter(signal('2026-10-07T14:00:00+00:00'))['reason'])

    def test_pending_exit_price_cannot_be_rewritten_when_fees_arrive(self):
        self.sim.enter(signal());self.sim.close('1.095','2026-10-06T14:15:00+00:00','STOP',commission_pending=True)
        self.reopen()
        with self.assertRaisesRegex(ValueError,'PENDING_EXIT_CANNOT_BE_REWRITTEN'):
            self.sim.close('1.12','2026-10-06T14:30:00+00:00','STOP')
        t=self.sim.close('1.095','2026-10-07T14:15:00+00:00','STOP')
        self.assertEqual('2026-10-06T14:15:00+00:00',t['exit_at']);self.assertIn('2026-10-06',self.sim.state['stopped_days'])

    def test_local_midnight_resets_day_but_not_pending_position(self):
        self.sim.enter(signal('2026-10-07T03:30:00+00:00')); self.sim.close('1.095','2026-10-07T03:45:00+00:00','STOP')
        self.assertTrue(self.sim.enter(signal('2026-10-07T04:00:00+00:00'))['admitted'])

    def test_daily_loss_budget_is_not_reset_by_a_profit(self):
        def preset():
            self.sim.state['daily_losses']['2026-10-06']='1.8'; self.sim.append('FIXTURE',{})
        self.sim.atomic(preset)
        self.assertEqual('COMMISSION_EXCEEDS_RISK_BUDGET',self.sim.enter(signal())['reason'])

    def test_cumulative_loss_limit_prevents_another_day(self):
        def preset():
            self.sim.state['consumed_loss']='20'; self.sim.append('FIXTURE',{})
        self.sim.atomic(preset)
        self.assertEqual('LOSS_BUDGET_EXHAUSTED',self.sim.enter(signal())['reason'])

    def test_duplicate_signal_after_restart(self):
        self.sim.enter(signal()); self.reopen()
        self.assertEqual('DUPLICATE_SIGNAL',self.sim.enter(signal())['reason'])

    def test_no_trade_does_not_count_as_an_operation(self):
        self.assertEqual('NO_TRADE',self.sim.enter(signal(reasons=['WARMUP']))['reason'])
        self.assertEqual(0,self.sim.metrics()['completed_trades']); self.assertEqual({},self.sim.state['stopped_days'])

    def test_model_pnl_counts_each_fee_and_friction_once(self):
        self.sim.enter(signal()); p = self.sim.state['position']; q = Decimal(p['decision']['quantity'])
        t = self.sim.close('1.12','2026-10-06T14:15:00+00:00','TARGET')
        self.assertEqual(q*Decimal('.02'),Decimal(t['gross_pnl']))
        self.assertEqual(q*Decimal('.0197')-Decimal('.2'),Decimal(t['net_pnl']))
        self.assertEqual(q*(Decimal(t['exit_fill'])-Decimal(t['entry_fill']))-Decimal('.2'),Decimal(t['net_pnl']))
        self.assertEqual('SIMULATED',t['fill_classification'])

    def test_complete_trade_metrics_include_friction_and_realized_reward_risk(self):
        self.sim.enter(signal());loss=self.sim.close('1.095','2026-10-06T14:15:00+00:00','STOP')
        self.sim.enter(signal('2026-10-07T14:00:00+00:00'));win=self.sim.close('1.12','2026-10-07T14:15:00+00:00','TARGET')
        m=self.sim.metrics()
        self.assertEqual(1,m['longest_losing_streak']);self.assertEqual(0,m['current_losing_streak'])
        self.assertEqual(Decimal(win['net_pnl'])/-Decimal(loss['net_pnl']),Decimal(m['realized_reward_risk']))
        self.assertEqual(Decimal(win['spread_cost'])+Decimal(loss['spread_cost']),Decimal(m['spread_cost']))
        self.assertEqual(Decimal(win['slippage_cost'])+Decimal(loss['slippage_cost']),Decimal(m['slippage_cost']))

    def test_no_trade_statistics_are_undefined(self):
        m=self.sim.metrics()
        for k in ('win_rate','net_expectancy','net_profit_factor','ibkr_execution_differences'): self.assertIsNone(m[k])

    def test_gap_can_breach_forecast_and_stops_day(self):
        self.sim.enter(signal()); self.sim.mark(bar('2026-10-06T14:15:00+00:00',open='1.08',high='1.09',low='1.07',close='1.08'),[])
        self.assertTrue(self.sim.state['trades'][0]['risk_budget_breached'])
        self.assertIn('2026-10-06',self.sim.state['stopped_days'])

    def test_window_boundary_retains_inventory_not_a_winner(self):
        self.sim.enter(signal()); self.sim.mark(bar(),[])
        self.assertEqual(0,self.sim.metrics()['completed_trades']); self.assertIsNotNone(self.sim.metrics()['pending_position'])
        self.assertLess(Decimal(self.sim.metrics()['pending_net_liquidation_pnl']),0)

    def test_protocol_change_cannot_reuse_journal(self):
        with self.assertRaisesRegex(ValueError,'SIMULATION_PROTOCOL_CHANGED'):
            Simulator(self.path,self.profile,{**COSTS,'spread':'.1'},STRATEGY)

    def test_out_of_order_signal_rejected(self):
        self.sim.enter(signal())
        with self.assertRaisesRegex(ValueError,'NON_CHRONOLOGICAL_INPUT'): self.sim.enter(signal('2026-10-05T14:00:00+00:00'))

    def test_future_indicators_rejected(self):
        with self.assertRaisesRegex(ValueError,'LOOK_AHEAD_CONTEXT'):
            self.sim.enter(signal(context={'15':{'as_of':'2026-10-06T14:15:00+00:00'}}))

    def test_invalid_numbers_and_non_utc_rejected(self):
        for x in ('NaN','Infinity',True):
            with self.subTest(x=x),self.assertRaises(ValueError): number(x)
        for x in ('2026-10-06T14:00:00','2026-10-06T14:00:00-04:00'):
            with self.subTest(x=x),self.assertRaises(ValueError): instant(x)

    def test_delayed_quote_cannot_create_forward_fill(self):
        self.assertEqual('FORWARD_QUOTE_UNUSABLE',self.sim.enter(signal(),forward=True,quote={'type':'DELAYED'})['reason'])

    def test_late_next_open_quote_rejected(self):
        q=dict(type='LIVE',market_status='OPEN',available_for_execution=True,at='2026-10-06T14:00:06+00:00',bid='1.1',ask='1.1001')
        self.assertEqual('LATE_NEXT_OPEN_ENTRY',self.sim.enter(signal(),forward=True,quote=q)['reason'])

    def test_journal_is_immutable(self):
        with self.assertRaisesRegex(Exception,'IMMUTABLE_SIMULATION_JOURNAL'):
            self.sim.db.execute('DELETE FROM events')

    def test_incremental_restore_still_detects_checkpoint_tampering(self):
        self.sim.enter(signal())
        self.sim.db.execute('DROP TRIGGER immutable_UPDATE')
        self.sim.db.execute("UPDATE events SET payload=replace(payload,'100','999') WHERE revision=?",(self.sim.revision,))
        with self.assertRaisesRegex(ValueError,'SIMULATION_JOURNAL_INTEGRITY_FAILED'):self.sim.restore()

    def test_rollback_cannot_leave_an_unpersisted_position(self):
        def fail():
            self.sim.state['position']={'invented':'position'};self.sim.append('FAULT',{});raise ValueError('FAULT')
        with self.assertRaisesRegex(ValueError,'FAULT'):self.sim.atomic(fail)
        self.assertIsNone(self.sim.state['position']);self.reopen();self.assertIsNone(self.sim.state['position'])

    def test_replay_cannot_reorder_protective_exit_to_authorize_entry(self):
        second=signal('2026-10-06T14:15:00+00:00')
        result=replay(self.sim,[bar(),bar(second['entry_at'],low='1.09')],[signal(),second],[])
        self.assertEqual(1,result['admitted']); self.assertEqual(1,result['metrics']['completed_trades'])
        self.assertEqual({'RESULT_RECONCILIATION_PENDING':1},result['rejections'])


class ExitParityTests(unittest.TestCase):
    def test_same_sequences_match_original_csharp_semantics(self):
        # Real deterministic existing C# command, no DB or broker.
        p=dict(strategy='trend',side='BUY',entry_at=AT,entry_midpoint='1.1',stop='1.095',target='1.125')
        sequences=[(bar(low='1.09'),False,[]),(bar(low='1.09',high='1.13'),False,[]),
                   (bar(open='1.08',low='1.07',high='1.1'),False,[]),(bar(high='1.13'),False,[]),
                   (bar('2026-10-06T14:15:00+00:00'),True,[dict(strategy_id='trend',side='BUY',at='2026-10-06T14:15:00+00:00')])]
        core=DotnetJournal(ROOT)
        for b,opening,exits in sequences:
            with self.subTest(b=b,opening=opening):
                expected=core.command(dict(operation='research-exit',position=dict(strategyId='trend',side='BUY',entry='1.1',stop='1.095',target='1.125',entryAt=AT),
                    bar=dict(openedAt=b['opened_at'],minutes=15,**{k:b[k] for k in ('open','high','low','close')}),previousOpenedAt=AT,
                    exits=[dict(strategyId=e['strategy_id'],side=e['side'],at=e['at']) for e in exits],opening=opening))
                actual=exit_decision(p,b,AT,exits,opening)
                self.assertEqual(expected['exit'],actual is not None)
                if actual:
                    self.assertEqual(Decimal(str(expected['price'])),Decimal(actual[0]));self.assertEqual(expected['reason'],actual[1])


class SimulationMemoryTests(unittest.TestCase):
    def test_scope_rejects_real_or_authorized_execution(self):
        with self.assertRaisesRegex(ValueError,'SIMULATION_MEMORY_SCOPE_REQUIRED'):
            simulation_memory.validate({'classification':'IBKR_FILL'})

    def test_sealed_final_and_no_openai_are_required(self):
        report=dict(classification='SIMULATED_RESEARCH',profile={'profile':PROFILE},broker_orders=0,openai_calls=0,final_holdout_opened=False,parameters_changed=False)
        self.assertEqual(report,simulation_memory.validate(report))
        for k in ('broker_orders','openai_calls','final_holdout_opened','parameters_changed'):
            with self.subTest(k=k),self.assertRaises(ValueError): simulation_memory.validate({**report,k:1})

    def test_memory_keeps_explicit_simulation_label(self):
        v=dict(evidence_id='fixture',classification='SIMULATED_NOT_IBKR_EXECUTION',decision='NO_VIABLE_STRATEGY_FOUND',
               fixed_round_trip_fee_usd='4',initial_risk_budget_usd='1',admitted=0,completed_trades=0,cost_status='ESTIMATED',conclusion='BLOCKED')
        compact=simulation_memory.compact([v])[0]
        self.assertEqual(v['classification'],compact['classification']);self.assertEqual(0,compact['n_closed'])
        self.assertEqual('4',compact['fees_usd']);self.assertEqual('1',compact['risk_usd'])
