"""Isolated price-risk Shadow experiment. This module cannot transmit broker orders."""
import argparse
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from decimal import Decimal,ROUND_FLOOR
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
from uuid import uuid4
from .eurusd_paper_research import number as N,instant,encoded,sha,ZONE
from .eurusd_exploratory_evidence import observer_context

PROFILE='R10_PRICE_RISK_EXPERIMENTAL'
CONFIG='config/r10-price-risk-experimental.json'
FOLDER='artifacts/research/r10-price-risk'
VERSION='9860cd16f4f43d38ca7c29f161aea82e17dea100da48bb78259457cc31133211'

def now():return datetime.now(timezone.utc)
def day(at):return instant(at).astimezone(ZONE).date().isoformat()
def configuration(root):
    c=json.loads((Path(root)/CONFIG).read_bytes())
    if c['profile']!=PROFILE or c['broker_orders_enabled'] or c['live_enabled'] or N(c['openai_budget_usd'])!=0:raise PermissionError('SHADOW_ONLY_LIVE_BLOCKED')
    if any(N(c[k])!=N(v) for k,v in dict(initial_capital_usd=100,price_risk_budget_usd=10,all_in_loss_cap_usd=15,cost_cap_usd=5,exposure_and_cost_reserve_cap_usd=100,cumulative_loss_cap_usd=20).items()):raise PermissionError('EXPERIMENT_SCOPE_CHANGED')
    if c['stop_policy']!='ORIGINAL_TECHNICAL_STOP' or c['max_positions']!=1 or c['signal_strategy']!='trend':raise PermissionError('PREREGISTERED_RULES_REQUIRED')
    if N(c['daily_loss_cap_usd'])!=15 or c['max_hold_hours']!=24 or not 1<=c['poll_seconds']<=60:raise PermissionError('EXPERIMENT_SCOPE_CHANGED')
    return c

def assess(c,quote,signal,equity='100'):
    """MIDPOINT price risk; costs charged separately once, with no leverage."""
    d=dict(profile=PROFILE,price_risk_budget='10',price_risk=None,estimated_fees=None,estimated_all_in_loss=None,
           realized_all_in_pnl=None,quantity='0',admitted=False,reason=None,execution_mode='SIMULATED_SHADOW',fees_status=c['fee_status'])
    try:
        bid,ask=N(quote['bid']),N(quote['ask']);mid=(bid+ask)/2
        stop_distance,target_distance=N(signal['stop_distance']),N(signal['take_profit_distance'])
        fee=N(c['opening_fee_usd'])+N(c['closing_fee_usd']);financing=N(c['financing_reserve_usd'])
        spread=max(ask-bid,N(c['spread_usd_per_eur']));slippage=2*N(c['slippage_per_side_usd_per_eur']);gap=N(c['gap_usd_per_eur'])
        step,minimum=N(c['quantity_increment']),N(c['minimum_quantity'])
        if min(bid,mid,stop_distance,target_distance,step,minimum)<=0 or ask<bid or stop_distance>=mid or min(fee,financing,spread,slippage,gap)<0:raise ValueError()
        price_budget=min(N(10),N(equity)*N('.1'));cost_unit=spread+slippage+gap;fixed=fee+financing
        capacity=min(N(100),N(equity))
        q=min((capacity-fixed)/(mid+cost_unit),price_budget/stop_distance,(N(c['all_in_loss_cap_usd'])-fixed)/(stop_distance+cost_unit),(N(c['cost_cap_usd'])-fixed)/cost_unit if cost_unit else N(100)/mid)
        q=max(N(0),(q/step).to_integral_value(rounding=ROUND_FLOOR)*step)
        price=q*stop_distance;costs=fixed+q*cost_unit;notional=q*mid
        d.update(quantity=str(q),price_risk_budget=str(price_budget),price_risk=str(price),estimated_fees=str(fee),opening_fee=str(N(c['opening_fee_usd'])),closing_fee=str(N(c['closing_fee_usd'])),spread_cost=str(q*spread),slippage_cost=str(q*slippage),gap_reserve=str(q*gap),financing_reserve=str(financing),estimated_costs=str(costs),estimated_all_in_loss=str(price+costs),notional=str(notional),capital_reserved=str(notional+costs),entry=str(mid),stop=str(mid-stop_distance),target=str(mid+target_distance),gross_target=str(q*target_distance),net_target=str(q*target_distance-costs),required_stop_distance_for_10=str(N(10)/q) if q else None,required_quantity_for_10=str(N(10)/stop_distance),price_risk_attained=price>=price_budget-N('.01'),increment_status=c['quantity_status'],stop_policy=c['stop_policy'])
        if q<minimum:d['reason']='CAPITAL_OR_MINIMUM_QUANTITY'
        elif signal.get('side')!='BUY':d['reason']='LONG_ONLY'
        elif q*target_distance<=costs:d['reason']='TARGET_DOES_NOT_COVER_COSTS'
        else:d['admitted']=True
    except (KeyError,ValueError,TypeError,ArithmeticError):d['reason']='COST_OR_GEOMETRY_UNKNOWN'
    return d

def paper_plan(assessment):
    return dict(profile=PROFILE,purpose='PAPER_EXECUTION_DIAGNOSTIC',state='BLOCKED',new_authorization_required=True,single_use=True,max_openings=1,max_minutes=30,emergency_review_required=True,broker_orders_enabled=False,live_enabled=False,
        assessment=assessment,conditions=['EXACT_PAPER_BINDING','FRESH_FLAT_RECONCILIATION','EFFECTIVE_FOREX_PERMISSION','SETTLED_CASH','MINIMUM_AND_INCREMENT','INCREMENTAL_MARGIN','BOUNDED_FEES_AND_FINANCING','LIVE_QUOTE_AND_CALENDAR','SUPERVISED_PROTECTION_ACK_AND_RECOVERY'],
        blockers=['R10_PRICE_RISK_PAPER_ADAPTER_NOT_RELEASED','NEW_PROFILE_SPECIFIC_AUTHORIZATION_REQUIRED','EFFECTIVE_BROKER_CONDITIONS_UNKNOWN'],
        diagnostic_is_predictive_evidence=False)

class Journal:
    def __init__(self,root,experiment):
        self.root=Path(root)
        if not re.fullmatch(r'r10-price-[a-f0-9]{32}',experiment):raise ValueError('EXPERIMENT_ID_REQUIRED')
        self.experiment=experiment
    def call(self,event=None):
        result=subprocess.run(['dotnet',str(self.root/'src/TradingAgent.Api/bin/Debug/net9.0/TradingAgent.Api.dll'),'--r10-price-journal'],input=encoded(dict(experiment=self.experiment,event=event)).decode(),text=True,capture_output=True,timeout=15,cwd=self.root)
        value=json.loads(result.stdout)
        if result.returncode or value.get('error'):raise RuntimeError('PRICE_RISK_JOURNAL_UNAVAILABLE')
        return value
    def load(self):return self.call()
    def commit(self,revision,previous,payload):return self.call(dict(revision=revision,previous=previous,payload=encoded(payload).decode(),hash=sha([revision,payload,previous]),material=encoded([revision,payload,previous]).decode()))

class Experiment:
    def __init__(self,journal,clock=now):
        self.journal,self.clock=journal,clock;h=journal.load();self.revision,self.head=h['revision'],h['hash'];self.state=json.loads(h['payload'])['state'] if h.get('payload') else None
    def append(self,kind,detail=None):
        at=self.clock().isoformat();event=dict(id=f'{self.journal.experiment}:{self.revision+1}',kind=kind,at=at,detail=detail or {},classification='SIMULATED_SHADOW')
        self.state['events']=[*self.state['events'],event][-200:];self.state['updated_at']=at
        payload=dict(experiment=self.journal.experiment,scope=PROFILE,classification='SIMULATED_SHADOW',live_enabled=False,broker_orders=0,event=kind,at=at,state=self.state)
        h=self.journal.commit(self.revision+1,self.head,payload);self.revision,self.head=h['revision'],h['hash']
    def prepare(self,c,root):
        if self.state is not None:raise ValueError('IMMUTABLE_EXPERIMENT_EXISTS')
        self.state=dict(protocol=c,engine_hash=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),strategy_version=VERSION,status='PREPARED_SHADOW',equity='100',consumed_loss='0',reserved='0',active=None,trades=[],seen=[],events=[],daily_stops={},last_quote=None,last_assessment=None,paper=paper_plan(None))
        self.append('EXPERIMENT_PREREGISTERED')
    def consume(self,observation,kronos=None,stop=False):
        s=self.state;c=s['protocol'];q=observation['quote'];at=observation['at'];analysis=observation['analysis'];s['last_quote']=q;s['status']='STOPPING_MANAGING_SHADOW' if stop and s['active'] else 'STOPPED' if stop else 'SHADOW_RUNNING'
        valid=q.get('type')=='LIVE' and q.get('market_status')=='OPEN' and q.get('available_for_execution') is True and q.get('at') and 0<=(self.clock()-instant(q['at'])).total_seconds()<=5 and N(q['ask'])>=N(q['bid'])>0
        if not valid:self.append('NO_TRADE',dict(reason='QUOTE_STALE_MISSING_OR_CLOSED',position_retained=bool(s['active'])));return
        if s['active']:
            t=s['active'];mid=(N(q['bid'])+N(q['ask']))/2;exit_price=None;reason=None
            # Completed bars strictly after entry; both-hit selects stop. No future bars.
            for b in analysis['normalized']['15']:
                if instant(b['opened_at'])<instant(t['at']) or instant(b['opened_at'])+timedelta(minutes=15)>instant(at):continue
                if N(b['low'])<=N(t['assessment']['stop']):exit_price=min(N(b['open']),N(t['assessment']['stop']));reason='STOP_OR_GAP';break
                if N(b['high'])>=N(t['assessment']['target']):exit_price=N(t['assessment']['target']);reason='TARGET';break
            if exit_price is None:
                if mid<=N(t['assessment']['stop']):exit_price=mid;reason='OBSERVED_STOP_OR_GAP'
                elif mid>=N(t['assessment']['target']):exit_price=N(t['assessment']['target']);reason='OBSERVED_TARGET'
                elif stop or instant(at)-instant(t['at'])>=timedelta(hours=c['max_hold_hours']):exit_price=mid;reason='OPERATOR_STOP' if stop else 'EXPERIMENT_HOLD_CAP'
                elif any(e['strategy_id']=='trend' and e['side']=='BUY' and instant(t['at'])<instant(e['at'])<=instant(at) for e in analysis.get('exit_signals',[])):exit_price=mid;reason='ORIGINAL_CONTEXT_EXIT_NEXT_OBSERVED_PRICE'
            if exit_price is not None:self.close(exit_price,q,at,reason)
            else:
                t['unrealized_price_pnl']=str((mid-N(t['assessment']['entry']))*N(t['assessment']['quantity']));self.append('SHADOW_POSITION_UPDATED')
            return
        if stop:self.append('SHADOW_STOPPED');return
        if N(s['consumed_loss'])>=N(c['cumulative_loss_cap_usd']):self.append('NO_TRADE',dict(reason='CUMULATIVE_ALL_IN_LOSS_STOP'));return
        if day(at) in s['daily_stops']:self.append('NO_TRADE',dict(reason=s['daily_stops'][day(at)]));return
        signal=next((deepcopy(x) for x in reversed(analysis['candidates']) if x['strategy_id']=='trend' and 0<=(instant(at)-instant(x['signal_at'])).total_seconds()<=5),None)
        if not signal:self.append('NO_TRADE',dict(reason='NO_CURRENT_AUTHENTIC_SIGNAL'));return
        signal['reasons']=[v for v in signal['reasons'] if v!='NO_NEXT_CLOSED_BAR'];identity=sha([VERSION,signal['signal_at'],signal['side']])
        if identity in s['seen']:return
        s['seen'].append(identity);d=assess(c,q,signal,s['equity']);s['last_assessment']=d;s['paper']=paper_plan(d)
        detail=dict(signal=signal,assessment=d,kronos=kronos,regime=observation.get('features',{}).get('regime','UNKNOWN'),history_source=observation.get('history_source'))
        self.append('SIGNAL_OBSERVED',detail)
        reason='INVALID_TECHNICAL_SIGNAL' if signal['reasons'] else d['reason']
        if N(d['estimated_all_in_loss'] or 0)>N(c['cumulative_loss_cap_usd'])-N(s['consumed_loss']):reason='CUMULATIVE_BUDGET_INSUFFICIENT'
        if reason:self.append('NO_TRADE',dict(reason=reason,signal_id=identity));return
        s['active']=dict(id=identity,at=at,signal=signal,assessment=d,kronos=kronos,regime=detail['regime'],quote=q,classification='SIMULATED_SHADOW',protection='SIMULATED_ONLY',reconciliation='VIRTUAL_JOURNAL_ONLY')
        s['reserved']=d['capital_reserved'];self.append('SIMULATED_SHADOW_FILL',s['active'])
    def close(self,price,quote,at,reason):
        s=self.state;t=s['active'];d=t['assessment'];qty=N(d['quantity']);gross=qty*(price-N(d['entry']))
        # Price fills are reference midpoint. Spread/slippage charged once separately;
        # actual gaps are already reflected in price, not charged again as reserve.
        spread=qty*max(N(s['protocol']['spread_usd_per_eur']),(N(t['quote']['ask'])-N(t['quote']['bid'])+N(quote['ask'])-N(quote['bid']))/2)
        net=gross-N(d['estimated_fees'])-spread-N(d['slippage_cost'])-N(d['financing_reserve'])
        t.update(exit=str(price),closed_at=at,reason=reason,gross_pnl=str(gross),realized_all_in_pnl=str(net),realized_spread_model=str(spread),cost_status='SIMULATED_ESTIMATES_NOT_BROKER_COMMISSIONS')
        s['equity']=str(N(s['equity'])+net);s['consumed_loss']=str(N(s['consumed_loss'])+max(N(0),-net))
        if net<=0:s['daily_stops'][day(at)]='DAILY_FIRST_LOSS_STOP' if net<0 else 'DAILY_BREAK_EVEN_STOP'
        s['trades'].append(t);s['active']=None;s['reserved']='0';self.append('SHADOW_CLOSE_RECONCILED',t)

class Reader:
    def __init__(self,root):
        from .eurusd_exploratory_runner import ExploratoryReadIdentity
        from .eurusd_shadow_research import MarketReader
        from .paper_execution_wire import execution_wire
        from .ibkr_session import session_guard,ExecutionMode
        self.reader=MarketReader.__new__(MarketReader);r=self.reader;r.root=Path(root);r.auth=ExploratoryReadIdentity(root,91);r.cached={};r.updated={};r.initialized=False
        def deny(*a,**kw):raise PermissionError('PRICE_RISK_SHADOW_NO_ORDERS')
        r.wire=execution_wire(r.auth,deny,read_only=True,session=session_guard(root,ExecutionMode.Research));a=r.auth.read(management=True)
        try:
            if r.wire.connect(a)!=[a['account']]:raise PermissionError('EXACT_PAPER_IDENTITY_REQUIRED')
            r.contract=r.wire.contract_details();r.calendar=r.wire.calendar();r.snapshot=r.wire.snapshot(diagnostic=True)
            r.capabilities=dict(identity=dict(status='VERIFIED',source='AccountBinding + exact managedAccounts'),
                reconciliation=dict(status='VERIFIED' if not r.snapshot['orders'] and not r.snapshot['positions'] and r.snapshot['exposure_reads_complete'] else 'UNKNOWN',orders=r.snapshot['orders'],positions=r.snapshot['positions'],reads_complete=r.snapshot['exposure_reads_complete']),
                permissions='UNKNOWN_EFFECTIVE_FOREX_PERMISSION',margin=dict(status='UNKNOWN_INCREMENTAL',account_total=r.snapshot['initial_margin']),
                minimum=dict(status='DECLARED_NOT_EFFECTIVE',quantity=r.contract['minimum_size_metadata'],increment=r.contract['size_increment_metadata']),
                settled_cash=dict(status='VERIFIED' if any(x['tag']=='SettledCash' for x in r.wire.account_rows) else 'UNKNOWN',observations=[x for x in r.wire.account_rows if x['tag']=='SettledCash']),
                fees='ESTIMATED_NOT_VERIFIED_FOR_THIS_SIZE',protection='UNKNOWN_EFFECTIVE_ACCEPTANCE')
        except Exception:
            r.wire.disconnect();raise
    def observe(self):return self.reader.observe()
    def close(self):self.reader.close()

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['Prepare','Assess','Status','Run','Once','Stop','PaperPlan']);p.add_argument('--root',required=True);p.add_argument('--experiment');a=p.parse_args();root=Path(a.root)
    if os.environ.get('LIVE_TRADING','false').lower()!='false':raise PermissionError('LIVE_DISABLED')
    identifier=a.experiment or ('r10-price-'+uuid4().hex if a.action=='Prepare' else '')
    e=Experiment(Journal(root,identifier));folder=root/FOLDER/identifier;folder.mkdir(parents=True,exist_ok=True);stop=folder/'stop.request'
    if a.action=='Prepare':e.prepare(configuration(root),root)
    elif a.action=='Stop':stop.write_text(now().isoformat())
    elif a.action in ('Run','Once','Assess'):
        if e.state['engine_hash']!=hashlib.sha256(Path(__file__).read_bytes()).hexdigest() or e.state['protocol']!=configuration(root):raise PermissionError('PREREGISTERED_ENGINE_CHANGED')
        import msvcrt
        with (folder/'run.lock').open('a+b') as lock:
            lock.write(b'0');lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
            reader=None
            try:
                while True:
                    if stop.exists() and not e.state['active']:e.state['status']='STOPPED';e.append('SHADOW_STOPPED');break
                    try:
                        if reader is None:reader=Reader(root)
                        o=reader.observe()
                        if a.action=='Assess':
                            from .progressive_risk_research import authentic_inputs
                            analysis,_,_=authentic_inputs(root);s=next(x for x in reversed(analysis['candidates']) if x['strategy_id']=='trend' and x['side']=='BUY' and not x['reasons'])
                            d=assess(e.state['protocol'],o['quote'],s,e.state['equity']);e.state.update(last_assessment=d,last_quote=o['quote'],paper=paper_plan(d));e.append('ASSESS_ONLY_NOT_CURRENT_SIGNAL',dict(source=s['signal_at'],capabilities=o['capabilities']));break
                        from .eurusd_shadow_research import feature_engine
                        o['features']=feature_engine(o['analysis'],o['quote'],o['at']);e.consume(o,observer_context(root,o['at']),stop.exists())
                        if a.action=='Once':break
                    except Exception as exc:
                        if reader:
                            try:reader.close()
                            except Exception:pass
                        from .paper_lab_diagnostics import safe_reason
                        reader=None;e=Experiment(Journal(root,identifier));e.state['status']='DATA_UNAVAILABLE';e.append('OBSERVATION_INTERRUPTED',dict(reason=safe_reason(exc),inventory_retained=bool(e.state['active'])))
                        if a.action!='Run':raise
                    time.sleep(e.state['protocol']['poll_seconds'])
            finally:
                if reader:reader.close()
    result=dict(experiment=identifier,revision=e.revision,state=e.state,broker_orders=0,live_enabled=False)
    print(json.dumps(result,allow_nan=False))

if __name__=='__main__':main()
