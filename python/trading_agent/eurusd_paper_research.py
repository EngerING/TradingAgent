"""USD100 internal execution only. No order transport, authorization or AI client.

The optional collector imports a mutation-disabled Paper wire locally. A Paper
quote is market evidence; every execution produced here is explicitly SIMULATED.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_FLOOR
import hashlib
import json
from pathlib import Path
import sqlite3
from uuid import uuid4
from zoneinfo import ZoneInfo

PROFILE = 'EURUSD_PAPER_RESEARCH_100'
FOLDER = 'artifacts/research/eurusd-paper-research-100'
ZONE = ZoneInfo('America/Santo_Domingo')


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def sha(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def number(value):
    if isinstance(value, bool):
        raise ValueError('INVALID_NUMBER')
    n = Decimal(str(value))
    if not n.is_finite():
        raise ValueError('INVALID_NUMBER')
    return n


def instant(value):
    at = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if at.utcoffset() != timedelta(0):
        raise ValueError('UTC_REQUIRED')
    return at


def load_profile(root):
    p = json.loads((Path(root)/'config/eurusd-paper-research-100.json').read_bytes())
    required = dict(profile=PROFILE, environment='INTERNAL_SIMULATION',
                    instrument='EUR/USD CASH IDEALPRO', purpose='SPECULATIVE_RESEARCH_NOT_CURRENCY_CONVERSION',
                    capital_usd='100', risk_fraction='0.01', maximum_trade_risk_usd='1',
                    daily_loss_budget_usd='2', cumulative_loss_budget_usd='20', exposure_multiple='1',
                    timezone='America/Santo_Domingo', policy='WIN_TO_CONTINUE / FIRST_LOSS_STOPS_DAY',
                    baseline_strategy='trend', minimum_net_reward_risk='1', maximum_cost_target_fraction='0.5',
                    broker_orders_enabled=False, live_enabled=False, openai_calls_enabled=False)
    if p != required:
        raise ValueError('ISOLATED_PROFILE_REQUIRED')
    return p


def exit_decision(position, bar, previous_opened_at, exits, opening):
    """Exact research-d-exits-v1 precedence; independently parity-tested."""
    at = instant(bar['opened_at']); previous = instant(previous_opened_at)
    o, h, l, c = [number(bar[k]) for k in ('open', 'high', 'low', 'close')]
    if bar['minutes'] != 15 or min(o, l, c) <= 0 or h < max(o, c) or l > min(o, c) or previous > at or at < instant(position['entry_at']):
        raise ValueError('INVALID_EXIT_OBSERVATION')
    if opening:
        matched = any(e['strategy_id'] == position['strategy'] and e['side'] == position['side']
                      and previous < instant(e['at']) <= at for e in exits)
        return (str(o), 'RULE_EXIT_NEXT_OPEN', at.isoformat()) if matched else None
    buy = position['side'] == 'BUY'
    stop, target = number(position['stop']), number(position['target'])
    stopped = l <= stop if buy else h >= stop
    targeted = h >= target if buy else l <= target
    if stopped:
        price = min(o, stop) if buy else max(o, stop)
        return str(price), 'STOP_AMBIGUOUS' if targeted else 'STOP', (at+timedelta(minutes=15)).isoformat()
    if targeted:
        return str(target), 'TAKE_PROFIT', (at+timedelta(minutes=15)).isoformat()
    return None


class Simulator:
    def __init__(self, path, profile, costs, strategy, *, positive_expectancy_evidence=False):
        # Only deterministic fixtures can exercise inexpensive costs. Production
        # entrypoints obtain costs from hash-checked observed Paper evidence.
        for k in ('openingCommission', 'closingCommission', 'spread', 'slippage', 'adverseGap'):
            if number(costs[k]) < 0:
                raise ValueError('NEGATIVE_COST')
        if any(number(costs[k]) <= 0 for k in ('minimumQuantity', 'quantityStep')):
            raise ValueError('INVALID_QUANTITY_RULE')
        if not strategy.get('strategy_version') or strategy.get('version') != 1:
            raise ValueError('EXISTING_STRATEGY_VERSION_REQUIRED')
        self.profile, self.costs, self.strategy = profile, costs, strategy
        self.expectancy = positive_expectancy_evidence
        self.binding = sha(dict(profile=profile, costs=costs, strategy=strategy, expectancy=positive_expectancy_evidence))
        self.db = sqlite3.connect(path, timeout=15, isolation_level=None)
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('CREATE TABLE IF NOT EXISTS events (revision INTEGER PRIMARY KEY, payload TEXT NOT NULL, previous TEXT NOT NULL, hash TEXT NOT NULL)')
        for action in ('UPDATE', 'DELETE'):
            self.db.execute(f"CREATE TRIGGER IF NOT EXISTS immutable_{action} BEFORE {action} ON events BEGIN SELECT RAISE(ABORT,'IMMUTABLE_SIMULATION_JOURNAL'); END")
        self.db.execute('BEGIN IMMEDIATE')
        try:
            self.restore()
            if not self.revision:
                self.state = dict(binding=self.binding, equity='100', consumed_loss='0', daily_losses={},
                                  stopped_days={}, position=None, trades=[], seen=[], last_at=None, last_bar=None, peak='100', drawdown='0')
                self.append('PREREGISTERED', dict(profile=profile, costs=costs, strategy=strategy))
            elif self.state['binding'] != self.binding:
                raise ValueError('SIMULATION_PROTOCOL_CHANGED')
            self.db.commit()
        except Exception:
            self.db.rollback(); self.db.close(); raise

    def restore(self, full=False):
        count, maximum = self.db.execute('SELECT count(*),max(revision) FROM events').fetchone()
        if count > 100000 or count != (maximum or 0):
            raise ValueError('SIMULATION_JOURNAL_LIMIT')
        cached = getattr(self, 'revision', 0)
        checkpoint = self.db.execute('SELECT revision,payload,previous,hash FROM events WHERE revision=?', (cached,)).fetchone() if cached and not full else None
        if checkpoint:
            revision,payload,previous,digest = checkpoint; data = json.loads(payload)
            if digest != self.head or sha([revision,data,previous]) != digest:
                raise ValueError('SIMULATION_JOURNAL_INTEGRITY_FAILED')
            self.state = data['state']
        else:
            self.revision = 0; self.head = ''; self.state = None
        rows = self.db.execute('SELECT revision,payload,previous,hash FROM events WHERE revision>? ORDER BY revision', (self.revision,)).fetchall()
        for revision, payload, previous, digest in rows:
            data = json.loads(payload)
            if revision != self.revision+1 or previous != self.head or sha([revision, data, previous]) != digest:
                raise ValueError('SIMULATION_JOURNAL_INTEGRITY_FAILED')
            self.revision, self.head, self.state = revision, digest, data['state']

    def append(self, kind, details):
        data = dict(event=kind, classification='SIMULATED', state=self.state, details=details)
        revision = self.revision+1; digest = sha([revision, data, self.head])
        self.db.execute('INSERT INTO events VALUES (?,?,?,?)', (revision, encoded(data).decode(), self.head, digest))
        self.revision, self.head = revision, digest

    def atomic(self, callback):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            self.restore(); result = callback(); self.db.commit(); return result
        except Exception:
            self.db.rollback(); self.restore(full=True); raise

    def size(self, s, at):
        p, c, st = self.profile, self.costs, self.state
        day = instant(at).astimezone(ZONE).date().isoformat()
        equity = number(st['equity']); loss = number(st['daily_losses'].get(day, '0'))
        budget = max(Decimal(0), min(equity*number(p['risk_fraction']), number(p['maximum_trade_risk_usd']),
                     number(p['daily_loss_budget_usd'])-loss, number(p['cumulative_loss_budget_usd'])-number(st['consumed_loss'])))
        decision = dict(admitted=False, reason=None, budget=str(budget), quantity='0', risk='0',
                        commissions=str(number(c['openingCommission'])+number(c['closingCommission'])),
                        costs=None, gross_target=None, net_target=None, net_reward_risk=None,
                        fill_classification='SIMULATED', ibkr_executability='UNKNOWN', execution_authorized=False)
        def reject(reason):
            decision['reason'] = reason; return decision
        if st['position'] is not None:
            return reject('RESULT_RECONCILIATION_PENDING')
        if day in st['stopped_days']:
            return reject(st['stopped_days'][day])
        if budget <= 0:
            return reject('LOSS_BUDGET_EXHAUSTED')
        if s.get('reasons') or s.get('entry_at') is None:
            return reject('NO_TRADE')
        if instant(s['entry_at']) != instant(at) or instant(s['signal_at']) > instant(at):
            raise ValueError('LOOK_AHEAD_OR_LATE_ENTRY')
        for frame in s.get('context', {}).values():
            for t in (frame.get('as_of'), frame.get('indicators', {}).get('closed_at')):
                if t and instant(t) > instant(s['signal_at']):
                    raise ValueError('LOOK_AHEAD_CONTEXT')
        mid, stop, target = [number(s[k]) for k in ('entry_midpoint', 'stop_distance', 'take_profit_distance')]
        if min(mid, stop, target) <= 0 or stop >= mid or s['side'] not in ('BUY', 'SELL'):
            raise ValueError('INVALID_SIGNAL')
        fixed = number(decision['commissions'])
        if fixed >= budget:
            return reject('COMMISSION_EXCEEDS_RISK_BUDGET')
        spread, slip, gap = [number(c[k]) for k in ('spread', 'slippage', 'adverseGap')]
        variable = spread+slip; unit_risk = stop+variable+gap
        ask = mid+spread/2
        cap = min((budget-fixed)/unit_risk, (min(equity, Decimal(100))-fixed)/(ask+variable))
        minimum, step = number(c['minimumQuantity']), number(c['quantityStep'])
        qty = minimum+((cap-minimum)/step).to_integral_value(rounding=ROUND_FLOOR)*step
        if qty < minimum:
            return reject('MINIMUM_QUANTITY_EXCEEDS_BUDGET')
        costs = fixed+qty*variable; risk = fixed+qty*unit_risk; gross = qty*target; net = gross-costs-qty*gap
        decision.update(quantity=str(qty), notional=str(qty*ask), risk=str(risk), costs=str(costs),
                        gross_target=str(gross), net_target=str(net), net_reward_risk=str(net/risk),
                        spread=str(qty*spread), slippage=str(qty*slip), gap_reserve=str(qty*gap))
        if net <= 0:
            return reject('TARGET_DOES_NOT_COVER_COSTS')
        if costs/gross > number(p['maximum_cost_target_fraction']):
            return reject('DISPROPORTIONATE_COSTS')
        if net/risk < number(p['minimum_net_reward_risk']):
            return reject('INSUFFICIENT_NET_REWARD_RISK')
        if not self.expectancy:
            return reject('NET_EXPECTANCY_EVIDENCE_INSUFFICIENT')
        decision.update(admitted=True, reason='INTERNAL_SIMULATION_ONLY')
        return decision

    def enter(self, signal, *, forward=False, quote=None):
        def run():
            s = deepcopy(signal); identity = sha(s)
            if identity in self.state['seen']:
                return dict(admitted=False, reason='DUPLICATE_SIGNAL')
            at = s['entry_at'] or s['signal_at']; instant(at)
            if self.state['last_at'] and instant(at) < instant(self.state['last_at']):
                raise ValueError('NON_CHRONOLOGICAL_INPUT')
            if forward:
                if not quote or quote.get('type') != 'LIVE' or quote.get('market_status') != 'OPEN' or quote.get('available_for_execution') is not True:
                    decision = dict(admitted=False, reason='FORWARD_QUOTE_UNUSABLE')
                elif not 0 <= (instant(quote['at'])-instant(at)).total_seconds() <= 5:
                    decision = dict(admitted=False, reason='LATE_NEXT_OPEN_ENTRY')
                else:
                    bid, ask = number(quote['bid']), number(quote['ask'])
                    if not 0 < bid <= ask or ask-bid > number(self.costs['spread']):
                        decision = dict(admitted=False, reason='SPREAD_EXCEEDS_PREREGISTERED_COSTS')
                    else:
                        s['entry_midpoint'] = str((bid+ask)/2); decision = self.size(s, at)
            else:
                decision = self.size(s, at)
            self.state['last_at'] = at; self.state['seen'].append(identity)
            if decision['admitted']:
                mid = number(s['entry_midpoint']); direction = 1 if s['side'] == 'BUY' else -1
                friction = (number(self.costs['spread'])+number(self.costs['slippage']))/2
                self.state['position'] = dict(id=identity, strategy=s['strategy_id'], strategy_version=self.strategy['strategy_version'],
                    signal=s, decision=decision, side=s['side'], entry_at=at, entry_midpoint=str(mid),
                    entry_fill=str(mid+direction*friction), stop=str(mid-direction*number(s['stop_distance'])),
                    target=str(mid+direction*number(s['take_profit_distance'])), result_state='OPEN_SIMULATED')
            self.append('SIMULATED_ENTRY' if decision['admitted'] else 'ENTRY_REJECTED', dict(signal=s, decision=decision))
            return decision
        return self.atomic(run)

    def close(self, price, at, reason, *, commission_pending=False):
        def run():
            p = self.state['position']
            if p is None or instant(at) < instant(p['entry_at']) or (self.state['last_at'] and instant(at) < instant(self.state['last_at'])):
                raise ValueError('INVALID_SETTLEMENT')
            if number(price) <= 0:
                raise ValueError('INVALID_SETTLEMENT_PRICE')
            if commission_pending:
                p['result_state'] = 'PENDING_COMMISSION';p['pending_exit']=dict(at=at,price=str(price),reason=reason)
                self.state['last_at']=at;self.append('RESULT_PENDING', dict(at=at, price=str(price), reason=reason)); return
            exit_at=at
            if p.get('pending_exit'):
                original=p['pending_exit']
                if number(price)!=number(original['price']) or reason!=original['reason']:raise ValueError('PENDING_EXIT_CANNOT_BE_REWRITTEN')
                exit_at=original['at']
            qty = number(p['decision']['quantity']); direction = 1 if p['side'] == 'BUY' else -1
            gross = direction*qty*(number(price)-number(p['entry_midpoint']))
            spread = qty*number(self.costs['spread']); slip = qty*number(self.costs['slippage'])
            buy_fee, sell_fee = number(self.costs['openingCommission']), number(self.costs['closingCommission'])
            net = gross-spread-slip-buy_fee-sell_fee
            day = instant(exit_at).astimezone(ZONE).date().isoformat()
            equity = number(self.state['equity'])+net; loss = max(Decimal(0), -net)
            self.state['equity'] = str(equity)
            self.state['consumed_loss'] = str(number(self.state['consumed_loss'])+loss)
            self.state['daily_losses'][day] = str(number(self.state['daily_losses'].get(day, '0'))+loss)
            if net <= 0:
                self.state['stopped_days'][day] = 'DAILY_FIRST_LOSS_STOP' if net < 0 else 'DAILY_NON_POSITIVE_STOP'
            self.state['peak'] = str(max(number(self.state['peak']), equity))
            self.state['drawdown'] = str(max(number(self.state['drawdown']), number(self.state['peak'])-equity))
            friction = (number(self.costs['spread'])+number(self.costs['slippage']))/2
            trade = dict(**{k:v for k,v in p.items() if k != 'result_state'}, exit_at=exit_at, settled_at=at, exit_midpoint=str(price), exit_fill=str(number(price)-direction*friction),
                         close_reason=reason, gross_pnl=str(gross), executed_gross_pnl=str(gross-spread-slip), net_pnl=str(net),
                         opening_commission=str(buy_fee), closing_commission=str(sell_fee), commission_currency='USD',
                         spread_cost=str(spread), slippage_cost=str(slip), fill_classification='SIMULATED',
                         equity=str(equity), risk_budget_breached=loss > number(p['decision']['budget']),
                         remaining_daily_loss_budget=str(max(Decimal(0), number(self.profile['daily_loss_budget_usd'])-number(self.state['daily_losses'][day]))),
                         continue_day=net > 0, result_state='RECONCILED_ESTIMATED_COSTS')
            self.state['trades'].append(trade); self.state['position'] = None; self.state['last_at'] = at
            self.append('SIMULATED_EXIT_RECONCILED', trade)
            return trade
        return self.atomic(run)

    def mark(self, bar, exits):
        # No liquidation invented at a window boundary; keep inventory and value
        # using only its last observed closed bar, including estimated exit costs.
        at = instant(bar['opened_at']); end = (at+timedelta(minutes=15)).isoformat()
        if self.state['last_bar'] and at <= instant(self.state['last_bar']['opened_at']):
            return
        p = self.state['position']
        previous = self.state['last_bar']['opened_at'] if self.state['last_bar'] else bar['opened_at']
        if p and at >= instant(p['entry_at']) and p['result_state'] == 'OPEN_SIMULATED':
            decision = exit_decision(p, bar, previous, exits, True) or exit_decision(p, bar, previous, exits, False)
            if decision:
                self.close(decision[0], decision[2], decision[1])
        if self.state['position'] is None:
            return
        def run():
            self.state['last_bar'] = bar; self.state['last_at'] = end
            self.append('CLOSED_BAR_OBSERVED', dict(bar=bar, price_provenance='AUTHENTIC_IBKR_MIDPOINT_EXECUTION_ESTIMATED'))
        self.atomic(run)

    def metrics(self):
        self.restore(full=True) # Complete audit before a reported result.
        trades = self.state['trades']; pnl = [number(t['net_pnl']) for t in trades]
        gains = sum((x for x in pnl if x > 0), Decimal(0)); losses = -sum((x for x in pnl if x < 0), Decimal(0))
        streak=longest=0
        for value in pnl:
            streak=streak+1 if value<0 else 0;longest=max(longest,streak)
        average_win=gains/sum(x>0 for x in pnl) if gains else None
        average_loss=losses/sum(x<0 for x in pnl) if losses else None
        unrealized = None; p = self.state['position']; last = self.state['last_bar']
        if p and last and instant(last['opened_at']) >= instant(p['entry_at']):
            qty = number(p['decision']['quantity']); direction = 1 if p['side'] == 'BUY' else -1
            unrealized = direction*qty*(number(last['close'])-number(p['entry_midpoint']))-number(p['decision']['costs'])
        return dict(completed_trades=len(trades), wins=sum(x > 0 for x in pnl), win_rate=float(sum(x > 0 for x in pnl)/len(pnl)) if pnl else None,
            gross_pnl=str(sum((number(t['gross_pnl']) for t in trades), Decimal(0))), net_pnl=str(sum(pnl, Decimal(0))),
            commissions=str(sum((number(t['opening_commission'])+number(t['closing_commission']) for t in trades), Decimal(0))),
            spread_cost=str(sum((number(t['spread_cost']) for t in trades),Decimal(0))),
            slippage_cost=str(sum((number(t['slippage_cost']) for t in trades),Decimal(0))),
            net_expectancy=str(sum(pnl)/len(pnl)) if pnl else None, net_profit_factor=str(gains/losses) if losses else None,
            average_win=str(average_win) if average_win is not None else None,
            average_loss=str(average_loss) if average_loss is not None else None,
            realized_reward_risk=str(average_win/average_loss) if average_win is not None and average_loss is not None else None,
            average_realized_r_multiple=str(sum((number(t['net_pnl'])/number(t['decision']['risk']) for t in trades),Decimal(0))/len(trades)) if trades else None,
            longest_losing_streak=longest,current_losing_streak=streak,
            recovery_factor=str(sum(pnl)/number(self.state['drawdown'])) if number(self.state['drawdown']) else None,
            cost_to_gross_profit_ratio=str(sum((number(t['decision']['costs']) for t in trades), Decimal(0))/sum((max(Decimal(0),number(t['gross_pnl'])) for t in trades),Decimal(0))) if any(number(t['gross_pnl'])>0 for t in trades) else None,
            equity_curve=[dict(at=t['exit_at'],equity=t['equity']) for t in trades],
            risk_of_ruin=None, risk_of_ruin_status='INSUFFICIENT_FORWARD_SAMPLE_AND_DEPENDENCE_MODEL',
            maximum_closed_drawdown_usd=self.state['drawdown'], equity_realized=self.state['equity'],
            pending_position=p, pending_net_liquidation_pnl=str(unrealized) if unrealized is not None else None,
            inventory_mark_policy='LAST_OBSERVED_CLOSED_BAR_MINUS_ESTIMATED_BOTH_SIDE_COSTS_NO_FUTURE_NO_FORCED_CLOSE',
            daily_stops=self.state['stopped_days'], consumed_loss=self.state['consumed_loss'],
            ibkr_execution_differences=None, comparison_status='NO_MATCHED_STRATEGY_PAPER_EXECUTIONS',
            fill_classification='SIMULATED', execution_authorized=False, live_enabled=False)


def replay(sim, bars, signals, exits):
    by_open = {}
    for s in signals:
        by_open.setdefault(s['entry_at'] or s['signal_at'], []).append(s)
    rejections = {}; admitted = 0
    for bar in bars:
        at = instant(bar['opened_at'])
        if sim.state['last_bar'] and at <= instant(sim.state['last_bar']['opened_at']):
            continue
        # Rule exits happen at this opening before admission; intrabar protective
        # exits remain after entry, exactly as in the original research model.
        p = sim.state['position']
        if p and p['result_state'] == 'OPEN_SIMULATED' and sim.state['last_bar']:
            decision = exit_decision(p, bar, sim.state['last_bar']['opened_at'], exits, True)
            if decision:
                sim.close(decision[0], decision[2], decision[1])
        for s in by_open.get(bar['opened_at'], []):
            result = sim.enter(s); admitted += result['admitted']
            if not result['admitted']:
                rejections[result['reason']] = rejections.get(result['reason'], 0)+1
        sim.mark(bar, exits)
    return dict(admitted=admitted, rejected=sum(rejections.values()), rejections=rejections, metrics=sim.metrics())


def run_backtest(root):
    from .progressive_risk_research import authentic_inputs, cost_evidence, walk_forward
    root = Path(root).resolve(); profile = load_profile(root)
    analysis, ids, provenance = authentic_inputs(root); costs, evidence = cost_evidence(root, provenance)
    folder = root/FOLDER/('run-'+uuid4().hex); folder.mkdir(parents=True, exist_ok=False)
    split = analysis['extension']['split']
    windows = [dict(name='development', test_start=split['start'], test_end=split['validation_start']),
               dict(name='validation', test_start=split['validation_start'], test_end=split['end']), *walk_forward(split)]
    results = []
    for strategy in ids:
        exits = [e for e in analysis['exit_signals'] if e['strategy_id'] == strategy]
        for window in windows:
            start, end = instant(window['test_start']), instant(window['test_end'])
            bars = [b for b in analysis['normalized']['15'] if start <= instant(b['opened_at']) and instant(b['opened_at'])+timedelta(minutes=15) <= end]
            signals = [s for s in analysis['candidates'] if s['strategy_id'] == strategy and start <= instant(s['entry_at'] or s['signal_at']) < end]
            sim = Simulator(folder/(strategy+'-'+window['name']+'.sqlite3'), profile, costs, ids[strategy])
            try:
                result = replay(sim, bars, signals, exits)
                results.append(dict(strategy=strategy, strategy_version=ids[strategy]['strategy_version'], window=window, **result, journal_hash=sim.head))
            finally:
                sim.db.close()
    report = dict(profile=profile, classification='SIMULATED_RESEARCH', costs=costs, cost_evidence=evidence,
                  provenance=provenance, split=split, strategy_versions=ids, results=results,
                  baseline='trend_V1_UNPROMOTED_REFERENCE_ONLY', selection='NO_VIABLE_STRATEGY_FOUND',
                  final_holdout_opened=False, fresh_oos=False, parameters_changed=False, openai_calls=0, broker_orders=0,
                  limitations=['Previously examined validation is retrospective, not fresh confirmation.',
                               'No fills are manufactured when costs exceed the risk budget.',
                               'Gap reserve is a forecast buffer, never a guaranteed maximum loss.',
                               'Contract minimum metadata does not prove odd-lot eligibility or speculative Forex permission.'])
    with (folder/'report.json').open('xb') as f:
        f.write(encoded(report))
    from .ai_strategy_researcher.simulation_memory import save
    save(root, folder/'report.json')
    return dict(report=str((folder/'report.json').relative_to(root)), decision=report['selection'],
                scenarios=len(results), admitted=sum(r['admitted'] for r in results), broker_orders=0, openai_calls=0)


def collect(root):
    """One bounded observation; no authorization, mutations, or what-if orders."""
    from .paper_lab_diagnostics import InspectionAuthorization
    from .paper_execution_wire import execution_wire
    from .ibkr_session import session_guard, ExecutionMode
    from .research_analysis import analyze
    root = Path(root).resolve(); load_profile(root)
    auth = InspectionAuthorization(root); a = auth.read(management=True)
    def deny(*args, **kwargs):
        raise PermissionError('INTERNAL_SIMULATION_NO_BROKER_ORDERS')
    wire = execution_wire(auth, deny, read_only=True, session=session_guard(root, ExecutionMode.Research))
    folder = root/FOLDER/('observation-'+uuid4().hex); folder.mkdir(parents=True, exist_ok=False)
    try:
        if wire.connect(a) != [a['account']]:
            raise PermissionError('EXACT_PAPER_IDENTITY_REQUIRED')
        contract = wire.contract_details(); calendar = wire.calendar()
        originals = {str(m):wire.history(m) for m in (60, 240, 15)}
        quote = wire.observe_quote(); at = datetime.now(timezone.utc).isoformat()
        analysis = analyze(dict(instrument='EUR/USD', source='IBKR_TWS', what_to_show='MIDPOINT', as_of=at,
                                indicators=json.loads((root/'config/research-indicators.json').read_bytes()), calendar=calendar, originals=originals))
        observation = dict(profile=PROFILE, at=at, exact_paper_identity_verified=True, contract=contract,
                           calendar=calendar, quote=quote, originals=originals, analysis=analysis, broker_orders=0)
        with (folder/'market.json').open('xb') as f:
            f.write(encoded(observation))
        return dict(observation=str((folder/'market.json').relative_to(root)), quote=quote, broker_orders=0)
    finally:
        wire.disconnect()


def forward_step(root, observation):
    from .progressive_risk_research import authentic_inputs, cost_evidence
    root = Path(root).resolve(); path = (root/observation).resolve()
    if not path.is_relative_to(root/FOLDER) or path.name != 'market.json':
        raise ValueError('OBSERVATION_SOURCE_REQUIRED')
    data = json.loads(path.read_bytes()); now = datetime.now(timezone.utc)
    if data.get('profile') != PROFILE or data.get('exact_paper_identity_verified') is not True or data.get('broker_orders') != 0:
        raise ValueError('READ_ONLY_PAPER_OBSERVATION_REQUIRED')
    if not 0 <= (now-instant(data['at'])).total_seconds() <= 60:
        raise ValueError('STALE_FORWARD_OBSERVATION')
    profile = load_profile(root); _, ids, provenance = authentic_inputs(root); costs, _ = cost_evidence(root, provenance)
    target = root/FOLDER/'forward'; target.mkdir(parents=True, exist_ok=True)
    sim = Simulator(target/'journal.sqlite3', profile, costs, ids['trend'])
    try:
        analysis = data['analysis']; bars = analysis['normalized']['15']; exits = analysis['exit_signals']
        for bar in bars:
            sim.mark(bar, exits)
        decisions = []
        # Never backfill forward entries: only the just-closed bar's signal may
        # enter at its next opening. Late quotes are an explicit rejection.
        for original in analysis['candidates']:
            if original['strategy_id'] != 'trend' or (now-instant(original['signal_at'])).total_seconds() > 900:
                continue
            s = deepcopy(original)
            s['reasons'] = [r for r in s['reasons'] if r != 'NO_NEXT_CLOSED_BAR']
            s['entry_at'] = s['signal_at']
            decisions.append(sim.enter(s, forward=True, quote=data['quote']))
        def finish():
            if bars:
                sim.state['last_bar'] = bars[-1]
            sim.append('FORWARD_STEP_COMPLETED', dict(source_path=str(path.relative_to(root)), source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(), decisions=decisions))
        sim.atomic(finish)
        return dict(decisions=decisions, metrics=sim.metrics(), broker_orders=0, openai_calls=0)
    finally:
        sim.db.close()


def main():
    p = argparse.ArgumentParser(); p.add_argument('--root', default='.'); p.add_argument('--action', choices=['Backtest', 'Observe', 'ForwardStep'], default='Backtest'); p.add_argument('--observation')
    args = p.parse_args()
    if args.action == 'Backtest': result = run_backtest(args.root)
    elif args.action == 'Observe': result = collect(args.root)
    else: result = forward_step(args.root, args.observation or '')
    print(json.dumps(result, allow_nan=False))


if __name__ == '__main__':
    main()
