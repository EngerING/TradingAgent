"""Explicit initial Paper diagnostic exception. An absent ledger row never becomes zero."""
import re
from datetime import timedelta
from .paper_lab import date,num,utc


def initial_absence_evidence(snapshot,additional,state,now,*,strategy=False):
    cash=snapshot.get('cash_reconciliation',{});reasons=[]
    if cash.get('state')!='UNKNOWN' or cash.get('value') is not None or cash.get('row_status')!='EUR_ROW_ABSENT' or cash.get('reason')!='CURRENCY_NOT_REPORTED':
        reasons.append('INITIAL_ABSENCE_NOT_OBSERVED')
    sources=set(cash.get('completed_sources',[]));expected=set(cash.get('expected_sources',[]))
    if cash.get('query_status')!='COMPLETE' or sources!=expected or len([s for s in sources if s.startswith('SUMMARY_')])!=2 or not {'ACCOUNT_UPDATES','ACCOUNT_UPDATES_MULTI'}<=sources or cash.get('errors'):
        reasons.append('ACCOUNT_QUERY_INCOMPLETE')
    if cash.get('base_currency')!='USD' or cash.get('account_ready') is not True:reasons.append('ACCOUNT_STATE_UNVERIFIED')
    rows=[r for r in cash.get('observations',[]) if r.get('source') in sources]
    usd={num(r['value']) for r in rows if r.get('tag') in ('CashBalance','TotalCashBalance') and r.get('currency') in ('USD','BASE')}
    if len(usd)!=1 or any(v<0 for v in usd):reasons.append('USD_CASH_MISSING_OR_CONFLICTING')
    for tag in ('InitMarginReq','MaintMarginReq'):
        values={num(r['value']) for r in rows if r.get('tag')==tag and r.get('currency')=='USD'}
        if values!={num(0)}:reasons.append('INITIAL_MARGIN_MISSING_OR_NONZERO')
    if snapshot.get('exposure_reads_complete') is not True or additional.get('status')!='COMPLETE' or additional.get('errors'):
        reasons.append('EXPOSURE_QUERY_INCOMPLETE')
    try:
        if not all(0<=(now-date(t)).total_seconds()<=30 for t in (snapshot['received_at'],additional['received_at'])):
            reasons.append('BASELINE_EVIDENCE_STALE')
    except (KeyError,ValueError,TypeError):reasons.append('BASELINE_EVIDENCE_STALE')
    for field in ('positions','portfolio','orders'):
        if field not in snapshot or (any(num(p.get('quantity',1))!=0 for p in snapshot[field]) if strategy and field!='orders' else snapshot[field]):reasons.append('INITIAL_'+field.upper()+'_NOT_EMPTY')
    if 'positions' not in additional or (any(num(p.get('quantity',1))!=0 for p in additional['positions']) if strategy else additional['positions']):reasons.append('INITIAL_SPECIFIC_POSITIONS_NOT_EMPTY')
    if snapshot.get('foreign_positions') or snapshot.get('foreign_currency_balances'):reasons.append('FOREIGN_EXPOSURE_PRESENT')
    if any(field not in snapshot for field in ('foreign_positions','foreign_currency_balances','events')):reasons.append('EXPOSURE_QUERY_INCOMPLETE')
    if any(e.get('kind') in ('fill','commission','commission_unavailable','disconnect','readonly','reject') for e in snapshot.get('events',[])):
        reasons.append('UNRESOLVED_BROKER_EVENT')
    if state.get('orders') or state.get('experiences') or state.get('pending_commissions') or state.get('unavailable_commissions') or state.get('eur_absence_consumed'):
        reasons.append('INITIAL_JOURNAL_NOT_EMPTY')
    if strategy:
        a=state.get('strategy_account');capital=(a or {}).get('capital',state.get('strategy_capital',{}))
        if num(capital.get('reservedLoss',0))!=0 or num(capital.get('consumedLoss',capital.get('consumed_loss',0)))!=0 or num(capital.get('equity',0))!=100 or state.get('unavailable_commissions') or a and (a.get('reservationId') or a.get('openPositions') or a.get('pendingOrders') or a.get('paperContinuation',{}).get('results')):
            reasons.append('INITIAL_STRATEGY_JOURNAL_NOT_RECONCILED')
    if any(s.get('count',0)!=0 or num(s.get('reserved',0))!=0 or num(s.get('consumed_loss',0))!=0 for s in state.get('sessions',{}).values()):
        reasons.append('INITIAL_DIAGNOSTIC_ALREADY_USED')
    return {'eligible':not reasons,'reasons':reasons,'eur_state':'EUR_ROW_ABSENT','eur_balance':None,
            'absence_of_exposure_proven':False,'manual_uncertainty_acceptance_required':True}


def owned_prefill_absence_evidence(snapshot,additional,order,now):
    """Observe only the already-bound bracket before any real fill; never authorize another entry."""
    cash=snapshot.get('cash_reconciliation',{});reasons=[]
    if order['fills']:reasons.append('STRICT_RECONCILIATION_REQUIRED_AFTER_FIRST_FILL')
    if cash.get('state')!='UNKNOWN' or cash.get('value') is not None or cash.get('row_status')!='EUR_ROW_ABSENT' or cash.get('reason')!='CURRENCY_NOT_REPORTED':reasons.append('INITIAL_ABSENCE_NOT_OBSERVED')
    sources=set(cash.get('completed_sources',[]));expected=set(cash.get('expected_sources',[]))
    if cash.get('query_status')!='COMPLETE' or sources!=expected or len([v for v in sources if v.startswith('SUMMARY_')])!=2 or not {'ACCOUNT_UPDATES','ACCOUNT_UPDATES_MULTI'}<=sources or cash.get('errors') or cash.get('account_ready') is not True or cash.get('base_currency')!='USD':reasons.append('ACCOUNT_QUERY_INCOMPLETE')
    if snapshot.get('exposure_reads_complete') is not True or additional.get('status')!='COMPLETE' or additional.get('errors'):reasons.append('EXPOSURE_QUERY_INCOMPLETE')
    for rows in (snapshot.get('positions'),snapshot.get('portfolio'),additional.get('positions')):
        if rows is None or any(num(p.get('quantity',1))!=0 for p in rows):reasons.append('PREFILL_POSITION_NOT_ZERO')
    if snapshot.get('foreign_positions') or snapshot.get('foreign_currency_balances'):reasons.append('FOREIGN_EXPOSURE_PRESENT')
    ids=order['order_ids']
    for r in snapshot.get('orders',[]):
        if r.get('order_id') not in ids:reasons.append('FOREIGN_ORDER');continue
        index=ids.index(r['order_id'])
        if (r.get('client_id')!=82 or r.get('contract_id')!=12087792 or r.get('reference')!=order['intent'] or
            r.get('side')!=('BUY' if index==0 else 'SELL') or r.get('order_type')!=('STP' if index==2 else 'LMT') or
            (index and r.get('parent_id')!=ids[0]) or num(r.get('quantity',0))!=num(order['quantity'])):reasons.append('OWNED_ORDER_LINK_UNVERIFIED')
        if index and (r.get('oca_type')!=2 or r.get('oca_group') not in (order['intent'],str(order['perm_ids'].get(str(ids[0]),'')))):reasons.append('OWNED_PROTECTION_LINK_UNVERIFIED')
    try:
        if not all(0<=(now-date(t)).total_seconds()<=30 for t in (snapshot['received_at'],additional['received_at'])):reasons.append('BASELINE_EVIDENCE_STALE')
    except (KeyError,ValueError,TypeError):reasons.append('BASELINE_EVIDENCE_STALE')
    return {'eligible':not reasons,'reasons':reasons,'eur_balance':None,'eur_state':'EUR_ROW_ABSENT','new_entry_allowed':False}


class AbsentEurAuthorization:
    def __init__(self,loader,clock=utc):self.loader,self.clock=loader,clock
    def read(self,a,*,for_review=False):
        e=self.loader();now=self.clock()
        strategy=e.get('scope')=='INITIAL_STRATEGY_PAPER_EUR_ABSENCE'
        if e.get('schema_version')!=1 or e.get('environment')!='PAPER_TRADING' or e.get('live_enabled') is not False or a.get('environment')!='PAPER_TRADING' or a.get('live_enabled') is not False or e.get('scope') not in ('INITIAL_DIAGNOSTIC_EUR_ABSENCE','INITIAL_STRATEGY_PAPER_EUR_ABSENCE'):
            raise PermissionError('EUR_EXCEPTION_SCOPE_INVALID')
        if (not strategy and (a.get('mode')!='ExecutionDiagnostics' or e.get('mode')!='ExecutionDiagnostics')) or e.get('account')!=a.get('account') or e.get('contract_id')!=12087792:
            raise PermissionError('EUR_EXCEPTION_ACCOUNT_OR_MODE_MISMATCH')
        if strategy:
            from .research_analysis import digest
            if e.get('mode')!='StrategyPaper' or e.get('risk_profile')!='PAPER_EXPERIMENTAL_10_PERCENT' or e.get('maximum_exposure')!=1 or e.get('risk_ceiling')!=10 or e.get('loss_allowance')!=20:
                raise PermissionError('EUR_EXCEPTION_STRATEGY_SCOPE_INVALID')
            if not re.fullmatch(r'[a-f0-9]{64}',e.get('strategy_version','')) or not re.fullmatch(r'[a-f0-9]{64}',e.get('plan_hash','')) or not re.fullmatch(r'[a-f0-9]{32}',e.get('execution_session_id','')):
                raise PermissionError('EUR_EXCEPTION_STRATEGY_BINDING_REQUIRED')
            if for_review:
                if a.get('session_id')!=e.get('review_session_id'):raise PermissionError('EUR_EXCEPTION_REVIEW_SESSION_MISMATCH')
            elif a.get('mode')!='StrategyPaper' or a.get('risk_profile')!=e['risk_profile'] or a.get('session_id')!=e['execution_session_id'] or a.get('strategy_versions')!=[e['strategy_version']] or digest(a.get('strategy_plan'))!=e['plan_hash']:
                raise PermissionError('EUR_EXCEPTION_STRATEGY_SESSION_MISMATCH')
        if e.get('tws_pid')!=a.get('tws_pid') or e.get('tws_start_filetime')!=a.get('tws_start_filetime'):
            raise PermissionError('EUR_EXCEPTION_TWS_SESSION_CHANGED')
        if not re.fullmatch(r'[a-f0-9]{32}',e.get('record_id','')) or e.get('manual_uncertainty_accepted') is not True or e.get('paper_checked') is not True or e.get('identity_manual_match') is not True or e.get('observed_state')!='EUR_ROW_ABSENT':
            raise PermissionError('EUR_EXCEPTION_OWNER_ACKNOWLEDGEMENT_REQUIRED')
        start,end=date(e['confirmed_at']),date(e['expires_at'])
        if not start<=now<end<=start+timedelta(minutes=30):raise PermissionError('EUR_EXCEPTION_EXPIRED')
        if not strategy and (e.get('max_experiments'),e.get('max_quantity'),e.get('max_notional_usd'),e.get('diagnostic_loss_budget'),e.get('max_hold_seconds'))!=(1,100,150,10,60):
            raise PermissionError('EUR_EXCEPTION_LIMITS_INVALID')
        if not for_review:
            if a.get('eur_absence_exception_id')!=e['record_id']:raise PermissionError('EUR_EXCEPTION_NOT_BOUND_TO_EXECUTION_SESSION')
            if not strategy and (a.get('max_experiments')!=1 or not 0<num(a.get('max_quantity',0))<=100 or not 0<num(a.get('max_notional_usd',0))<=150 or num(a.get('diagnostic_loss_budget',0))!=10 or not 0<a.get('max_hold_seconds',0)<=60):
                raise PermissionError('EUR_EXCEPTION_EXECUTION_LIMITS_EXCEEDED')
        return e


def validate_review_permit(p,a,now,*,exception_id=None):
    if p.get('schema_version')!=1 or p.get('scope')!='OWNER_REVIEW_CLEAR_EMERGENCY' or p.get('environment')!='PAPER_TRADING' or p.get('live_enabled') is not False:
        raise PermissionError('PROTECTED_OWNER_REVIEW_REQUIRED')
    if p.get('account')!=a.get('account') or p.get('session_id')!=a.get('session_id') or p.get('tws_pid')!=a.get('tws_pid') or p.get('tws_start_filetime')!=a.get('tws_start_filetime') or p.get('exception_id')!=exception_id:
        raise PermissionError('OWNER_REVIEW_SCOPE_MISMATCH')
    start,end=date(p['confirmed_at']),date(p['expires_at'])
    if not start<=now<end<=start+timedelta(minutes=2) or not re.fullmatch(r'[a-f0-9]{32}',p.get('record_id','')):
        raise PermissionError('OWNER_REVIEW_EXPIRED')
    return p['record_id']
