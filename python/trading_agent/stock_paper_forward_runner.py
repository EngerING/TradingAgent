"""Fixed H40 runner: read/reconcile before entry, resume management without re-entry."""
from datetime import timedelta
import hashlib
import queue
import time
from contextlib import contextmanager
from pathlib import Path
from .stock_paper_forward import (now, number, at, VERSION, CANDIDATE, Journal, Ledger,
    PaperExecutionGuard, configuration, FOLDER, inspect, readiness, estimate,
    risk_request, core_risk, h40_next_signal, sha)
from .ibkr_session import AccountBinding, SessionConfiguration
from .paper_lab import unseal
from .broker import PaperOptions

@contextmanager
def run_lock(path):
    import msvcrt
    with Path(path).open('a+b') as f:
        if f.seek(0,2)==0:f.write(b'0');f.flush()
        f.seek(0)
        try:msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:raise PermissionError('STOCK_FORWARD_ALREADY_RUNNING') from None
        try:yield
        finally:f.seek(0);msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)


def owned_snapshot(snapshot,ledger):
    value=dict(snapshot);i=ledger.state['intent']
    ref=i['intent'] if i else None
    for name in ('completed_orders','executions'):
        value[name]=[r for r in snapshot[name] if r.get('order_ref')==ref or r.get('order_ref','').startswith('H40-')]
    exec_ids={r['exec_id'] for r in value['executions']}
    value['commissions']=[r for r in snapshot['commissions'] if r['exec_id'] in exec_ids]
    return value

def drain(wire,ledger):
    while True:
        try:kind,row=wire.callback_events.get_nowait()
        except queue.Empty:return
        i=ledger.state['intent']
        if kind in ('order','fill') and not row.get('order_ref','').startswith('H40-'):continue
        if kind=='fee' and (not i or row['exec_id'] not in i['executions']):
            # snapshot fee cache retains a commission that precedes execDetails.
            continue
        if kind=='order':ledger.order(row)
        elif kind=='fill':ledger.fill(row)
        elif kind=='fee':ledger.fee(row)
        elif kind=='error':
            if i:i['uncertain']=True
            ledger.suspend('IBKR_ORDER_ERROR_RECONCILIATION_REQUIRED')
        elif kind=='status_without_contract' and i and row['order_id'] in i['order_ids']+([i['close_id']] if i.get('close_id') else []):
            i['uncertain']=True;ledger.write('STATUS_REQUIRES_CONTRACT_RECONCILIATION',row)

def plan_signal(root,c,ledger,snapshot,rows,wire):
    session=snapshot['active_session'];stamp=now()
    if not session or not at(session['start'])<=stamp<at(session['start'])+timedelta(seconds=c['entry_window_seconds']):return None
    completed=[b for b in rows if at(b['closed_at'])<=at(session['start'])]
    opening=next((b for b in rows if at(b['opened_at'])==at(session['start'])),None)
    if not opening or len(completed)<100:return None
    event=h40_next_signal(completed,opening,session,c)
    if not event:return None
    # Use the actual opening, then the live ASK limit; an adverse opening gap
    # invalidates original stop/target geometry rather than moving H40 levels.
    quote=snapshot['quote'];p=number(quote['ask'])
    if not number(event['stop'])<p<number(event['target']):return None
    size=estimate(p,event['stop'],event['target'],2,ledger.state['cash'],ledger.state['equity'],number(quote['ask'])-number(quote['bid']),losses=ledger.state['consumed_loss'])
    if not size['quantity']:return None
    signal_key=hashlib.sha256((VERSION+'|'+event['signal_at']).encode()).hexdigest()
    first=max(wire.next_order_id,ledger.state['next_order_id'])
    plan=dict(at=stamp.isoformat(),intent='H40-'+signal_key[:32],signal_key=signal_key,strategy_version=VERSION,side='BUY',
        signal=event,quantity=size['quantity'],entry=size['entry'],stop=str(event['stop']),target=str(event['target']),
        opening_fee=size['opening_fee'],closing_fee=size['closing_fee'],fees=size['fees'],risk=size['estimated_loss'],
        cash=ledger.state['cash'],slippage_per_unit=str(p*number('.0005')),gap_per_unit=str(p*number('.005')),
        con_id=snapshot['contract']['con_id'],order_ids=[first,first+1,first+2],entry_session=session['start'],
        friction={k:size[k] for k in ('spread','slippage','gap','target_net')},completed_bars=completed,opening_bar=opening)
    decision=core_risk(root,ledger.state,risk_request(plan,snapshot))
    ledger.write('RISK_AND_EXECUTION_FEASIBILITY',decision)
    if decision.get('allowed') is not True:return None
    return plan

def manage(wire,ledger,snapshot):
    i=ledger.state['intent']
    if not i:return
    open_orders=snapshot['open_orders'];q=number(i['position']);session=snapshot.get('active_session')
    parent=i['orders'].get(str(i['order_ids'][0]))
    if parent and parent['status'] not in ('Filled','Cancelled','ApiCancelled','Inactive'):
        # Do not leave a late DAY entry working after the next-open window.
        if i['first_fill_at'] or now()>at(i['entry_session'])+timedelta(seconds=60):wire.cancel_owned(i['order_ids'][0])
        return
    if q==0:
        for order in open_orders:wire.cancel_owned(order['order_id'])
        return
    children=[o for o in open_orders if o['order_id'] in i['order_ids'][1:]]
    if not i.get('hold_exit_due'):
        if len(children)!=2 or any(number(o['quantity'])!=q or o['status'] not in ('PreSubmitted','Submitted') for o in children):
            ledger.suspend('PROTECTION_NOT_CONFIRMED_FOR_REMAINING_POSITION');return
        # Original Hold40 exits at opening of observed daily bar index 39.
        rows=wire.daily_context()
        held=[b for b in rows if at(i['entry_session'])<=at(b['opened_at'])]
        if len(held)<40:return
        if not session or at(held[39]['opened_at'])!=at(session['start']):
            ledger.suspend('H40_RULE_NEXT_OPEN_MISSED_OPERATOR_REVIEW_REQUIRED');return
        i['hold_exit_due']=True;ledger.write('RULE_NEXT_OPEN_EXIT_DUE')
    # Cancelling OCA siblings is followed by another full broker snapshot.
    # Never submit an independent SELL while any child can still fill.
    if open_orders:
        for order in open_orders:wire.cancel_owned(order['order_id'])
        return
    quote=snapshot['quote'];stamp=now()
    if quote['market_data_type']!=1 or any(not 0<=(stamp-at(quote['field_received_at'][k])).total_seconds()<=15 for k in ('bid','ask')):
        ledger.suspend('OWNED_EXIT_LIVE_QUOTE_UNAVAILABLE');return
    if not session:ledger.suspend('OWNED_EXIT_AUTHENTIC_SESSION_CLOSED');return
    wire.close_owned(snapshot,quote['bid'],'RULE_NEXT_OPEN')

def run(root,c):
    """No connection or mutation unless the existing independent grant is valid.

    This revision is intentionally blocked by the unchanged 0.5% productive
    ceiling. Exposing transport must not manufacture a 2% policy approval.
    """
    root=Path(root);binding=AccountBinding(unseal(root/'.local/ibkr-account-binding.dpapi'))
    folder=root/FOLDER;folder.mkdir(parents=True,exist_ok=True)
    with run_lock(folder/'runner.lock'):
        journal=Journal(folder/'journal.sqlite3',binding.binding_id);ledger=Ledger(journal)
        guard=PaperExecutionGuard(root,c,ledger);wire=None
        try:
            # Management survives stop/expiry, but account/process/scope never do.
            grant=guard.grant(management=ledger.state['intent'] is not None)
            if not ledger.state['intent'] and CANDIDATE['risk_percent']>number('.5'):
                raise PermissionError('H40_RISK_2_PERCENT_EXCEEDS_PRODUCTIVE_0_5_PERCENT')
            from .stock_paper_forward_wire import stock_forward_wire
            endpoint=SessionConfiguration.load(root)
            wire=stock_forward_wire(PaperOptions(binding.account,host=endpoint.host,port=endpoint.port,
                verified_tws_port=endpoint.port,paper_mode_attested=True,configured_endpoint=True,
                read_only=False,client_id=c['client_id'],timeout=c['request_timeout_seconds']))
            binding.select(wire.connect());wire.bind_execution(guard,ledger)
            while True:
                guard.grant(management=ledger.state['intent'] is not None)
                snapshot=owned_snapshot(wire.snapshot(),ledger);drain(wire,ledger);ledger.reconcile(snapshot)
                if ledger.state['intent']:manage(wire,ledger,snapshot)
                else:
                    try:guard.grant()
                    except PermissionError:return dict(state='STOPPED',open_position=False,new_entries_stopped=True,live_enabled=False)
                    if not ledger.entry_block(now().isoformat()) and not readiness(snapshot,c):
                        rows=wire.daily_context()
                        snapshot=owned_snapshot(wire.snapshot(),ledger);drain(wire,ledger);ledger.reconcile(snapshot)
                        plan=plan_signal(root,c,ledger,snapshot,rows,wire)
                        if plan:wire.bracket(snapshot,plan)
                time.sleep(c['poll_seconds'])
        except BaseException:
            ledger.suspend('RUNNER_STOPPED_RECONCILIATION_REQUIRED');raise
        finally:
            if wire:wire.disconnect()
            journal.close()
