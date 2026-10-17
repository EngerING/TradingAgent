"""Independent R20 journal/observer. No Paper execution, authorization or model calls."""
import argparse
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
from uuid import uuid4

from .aggressive_growth import PROFILE, CLASSIFICATION, configuration, initial_state, consume, paper_plan, encoded, sha, instant

FOLDER='artifacts/research/aggressive-growth-r20'
ENGINE=('python/trading_agent/aggressive_growth.py','python/trading_agent/aggressive_growth_runner.py')


def now(): return datetime.now(timezone.utc)


def engine_hashes(root):
    return sha({p:hashlib.sha256((Path(root)/p).read_bytes()).hexdigest() for p in ENGINE})


def safe_reason(exc):
    value=str(exc)
    return value if re.fullmatch('[A-Z0-9_]{1,100}',value) else type(exc).__name__


class Journal:
    def __init__(self,root,experiment,configuration='Debug'):
        if not re.fullmatch('aggressive-r20-[a-f0-9]{32}',experiment):raise ValueError('R20_EXPERIMENT_ID_REQUIRED')
        if configuration not in ('Debug','R20'):raise ValueError('R20_BUILD_CONFIGURATION_REQUIRED')
        self.root,self.experiment=Path(root).resolve(),experiment
        self.configuration=configuration

    def call(self,event=None):
        if os.environ.get('LIVE_TRADING','false').lower()!='false':raise PermissionError('LIVE_DISABLED')
        allowed={'PATH','SYSTEMROOT','TEMP','TMP','TRADING_LAB_DB'}
        env={k:v for k,v in os.environ.items() if k.upper() in allowed}
        result=subprocess.run(['dotnet',str(self.root/f'src/TradingAgent.Api/bin/{self.configuration}/net9.0/TradingAgent.Api.dll'),'--aggressive-growth-journal'],
                              input=encoded(dict(experiment=self.experiment,event=event)).decode(),text=True,capture_output=True,env=env,timeout=20,cwd=self.root)
        try:value=json.loads(result.stdout)
        except (ValueError,TypeError):raise RuntimeError('R20_POSTGRES_UNAVAILABLE') from None
        if result.returncode or value.get('error'):raise RuntimeError('R20_POSTGRES_UNAVAILABLE_OR_CONFLICT')
        return value

    def load(self):return self.call()

    def commit(self,revision,previous,payload):
        return self.call(dict(revision=revision,previous=previous,payload=encoded(payload).decode(),hash=sha([revision,payload,previous]),material=encoded([revision,payload,previous]).decode()))


class Experiment:
    def __init__(self,journal,clock=now):
        self.journal,self.clock=journal,clock
        h=journal.load();self.revision,self.head=h['revision'],h['hash'];self.state=json.loads(h['payload'])['state'] if h.get('payload') else None

    def commit(self,state,kind,details=None,events=None):
        at=self.clock().isoformat();candidate=deepcopy(state);candidate['updated_at']=at
        if instant(at)<instant(state['updated_at']):raise ValueError('OBSERVATION_TIME_CANNOT_REWIND')
        records=events or [dict(kind=kind,at=at,detail=details or {},classification=CLASSIFICATION)]
        for i,e in enumerate(records):e=dict(e,id=f'{self.journal.experiment}:{self.revision+1}:{i}');candidate['events'].append(e)
        candidate['events']=candidate['events'][-200:]
        payload=dict(experiment=self.journal.experiment,scope=PROFILE,classification=CLASSIFICATION,broker_orders=0,live_enabled=False,event=kind,at=at,state=candidate)
        try:h=self.journal.commit(self.revision+1,self.head,payload)
        except Exception:
            # An ACK can be lost after INSERT. Invalidate all mutable local state;
            # only a new instance loaded from PostgreSQL may make another decision.
            self.state=None
            raise
        self.revision,self.head,self.state=h['revision'],h['hash'],candidate

    def prepare(self,c,engine_hash,run_kind='FORWARD'):
        if self.state is not None:raise ValueError('IMMUTABLE_EXPERIMENT_EXISTS')
        self.commit(initial_state(c,engine_hash,self.clock().isoformat(),run_kind),'EXPERIMENT_PREREGISTERED')

    def observe(self,observation,kronos=None,stop=False):
        if self.state is None:raise ValueError('R20_STATE_RELOAD_REQUIRED')
        if self.state['status']=='STOPPED':return
        candidate=deepcopy(self.state);events=consume(candidate,observation,self.clock(),kronos,stop)
        self.commit(candidate,'OBSERVATION_EVALUATED',events=events)

    def stop(self):
        if self.state is None:raise ValueError('PREREGISTERED_EXPERIMENT_REQUIRED')
        if self.state['status']=='STOPPED':return
        s=deepcopy(self.state);s['stop_requested']=True
        s['status']='STOPPING_MANAGING_SHADOW' if any(p['active'] for p in s['portfolios'].values()) else 'STOPPED'
        self.commit(s,'OPERATOR_STOP_REQUESTED',dict(virtual_inventory_retained=any(p['active'] for p in s['portfolios'].values()),broker_untouched=True))


class Reader:
    def __init__(self,root):
        from .eurusd_exploratory_runner import ExploratoryReadIdentity
        from .eurusd_shadow_research import MarketReader
        from .paper_execution_wire import execution_wire
        from .ibkr_session import session_guard,ExecutionMode
        self.reader=MarketReader.__new__(MarketReader);r=self.reader
        r.root=Path(root);r.auth=ExploratoryReadIdentity(root,92);r.cached={};r.updated={};r.initialized=False
        def deny(*a,**kw):raise PermissionError('R20_READ_ONLY_NO_BROKER_ORDERS')
        r.wire=execution_wire(r.auth,deny,read_only=True,session=session_guard(root,ExecutionMode.Research));a=r.auth.read(management=True)
        try:
            if r.wire.connect(a)!=[a['account']]:raise PermissionError('EXACT_PAPER_IDENTITY_REQUIRED')
            r.contract=r.wire.contract_details();r.calendar=r.wire.calendar();r.snapshot=r.wire.snapshot(diagnostic=True)
            # Read-only evidence is deliberately sparse; broker balances never reach sizing.
            r.capabilities=dict(identity=dict(status='VERIFIED',source='AccountBinding + exact managedAccounts'),
                                reconciliation=dict(status='VERIFIED' if not r.snapshot['orders'] and not r.snapshot['positions'] and r.snapshot['exposure_reads_complete'] else 'UNKNOWN'),
                                minimum=dict(status='DECLARED_NOT_EFFECTIVE_PERMISSION',quantity=r.contract['minimum_size_metadata'],increment=r.contract['size_increment_metadata']),
                                permissions='UNKNOWN_EFFECTIVE_FOREX_PERMISSION',margin='UNKNOWN_INCREMENTAL',fees='ESTIMATED_NOT_VERIFIED_FOR_THIS_SIZE',protection='UNKNOWN_EFFECTIVE_ACCEPTANCE')
        except Exception:r.wire.disconnect();raise

    def observe(self):return self.reader.observe()
    def close(self):self.reader.close()


def read_kronos(root,at):
    from .kronos.persistence import PostgreSQLJournal
    try:
        events=PostgreSQLJournal(root).read().get('events',[])
        predictions=[e['payload'] for e in events if e['kind']=='PREDICTION' and instant(e['payload']['created_at'])<=instant(at)]
        if not predictions:return dict(status='KRONOS_UNAVAILABLE',reason='NO_PREDICTION_AVAILABLE_AS_OF')
        p=max(predictions,key=lambda x:instant(x['created_at']))
        return dict(status=p.get('status','RAW_ONLY'),latest=p)
    except Exception as exc:return dict(status='KRONOS_UNAVAILABLE',reason=safe_reason(exc))


@contextmanager
def run_lock(path):
    import msvcrt
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a+b') as f:
        # Windows permits locking a byte beyond EOF. Do not write before owning the lock.
        f.seek(0)
        try:msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:raise RuntimeError('R20_OBSERVER_ALREADY_RUNNING') from None
        try:yield
        finally:f.seek(0);msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)


def verify_protocol(e,root):
    if e.state is None:raise ValueError('PREREGISTERED_EXPERIMENT_REQUIRED')
    if e.state['protocol']!=configuration(root) or e.state['engine_hash']!=engine_hashes(root):raise PermissionError('PREREGISTERED_R20_ENGINE_CHANGED')
    if e.state['run_kind']!='FORWARD':raise ValueError('HISTORICAL_CANNOT_RUN_FORWARD')


def wait_for_poll(seconds,stop,stop_requested):
    deadline=time.monotonic()+seconds
    # A new Stop wakes the runner; an acknowledged Stop must not busy-poll unavailable quotes.
    while time.monotonic()<deadline and (stop_requested or not stop.exists()):
        time.sleep(min(1,max(0,deadline-time.monotonic())))


def run(root,identifier,once=False):
    root=Path(root);folder=root/FOLDER/identifier;folder.mkdir(parents=True,exist_ok=True);stop=folder/'stop.request'
    with run_lock(root/FOLDER/'singleton.lock'),run_lock(folder/'run.lock'):
        reader=None
        try:
            while True:
                # Reload also observes Stop from another terminal and resolves any uncertain write.
                e=Experiment(Journal(root,identifier));verify_protocol(e,root)
                if e.state['status']=='STOPPED':return e
                if stop.exists() and not any(p['active'] for p in e.state['portfolios'].values()):e.stop();return e
                try:
                    if reader is None:reader=Reader(root)
                    observation=reader.observe();kronos=read_kronos(root,observation['at'])
                    e.observe(observation,kronos,stop.exists())
                    print(json.dumps(dict(experiment=identifier,revision=e.revision,status=e.state['status'],opportunities=e.state['opportunities'],broker_orders=0)),flush=True)
                    if once or e.state['status']=='STOPPED':return e
                except Exception as exc:
                    if reader:
                        try:reader.close()
                        except Exception:pass
                    reader=None
                    # Do not assume a failed append did not commit. Stop deciding until PostgreSQL reload works.
                    e=Experiment(Journal(root,identifier));verify_protocol(e,root)
                    if e.state['status']=='STOPPED':return e
                    s=deepcopy(e.state);s['status']='STOPPING_MANAGING_SHADOW' if s.get('stop_requested') else 'DATA_UNAVAILABLE'
                    e.commit(s,'OBSERVATION_INTERRUPTED',dict(reason=safe_reason(exc),inventory_retained=any(p['active'] for p in s['portfolios'].values())))
                    if once:raise
                wait=min(e.state['protocol']['poll_seconds'],3600-time.time()%3600)
                wait_for_poll(wait,stop,e.state.get('stop_requested',False))
        finally:
            if reader:reader.close()


def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['Prepare','Status','Run','Once','Stop','PaperPlan']);p.add_argument('--root',required=True);p.add_argument('--experiment');a=p.parse_args();root=Path(a.root).resolve()
    if os.environ.get('LIVE_TRADING','false').lower()!='false':raise PermissionError('LIVE_DISABLED')
    identifier=a.experiment or ('aggressive-r20-'+uuid4().hex if a.action=='Prepare' else '')
    e=Experiment(Journal(root,identifier))
    if a.action=='Prepare':e.prepare(configuration(root),engine_hashes(root))
    elif a.action=='Stop':
        folder=root/FOLDER/identifier;folder.mkdir(parents=True,exist_ok=True);(folder/'stop.request').write_text(now().isoformat(),encoding='utf-8')
        # File latch is first and irreversible. CAS conflict from a concurrent tick is safe to reload once.
        try:e.stop()
        except Exception:e=Experiment(Journal(root,identifier));e.stop()
    elif a.action in ('Run','Once'):e=run(root,identifier,a.action=='Once')
    if a.action=='PaperPlan':result=dict(experiment=identifier,paper=e.state['paper'],broker_orders=0,live_enabled=False)
    else:result=dict(experiment=identifier,revision=e.revision,state=e.state,broker_orders=0,live_enabled=False)
    print(json.dumps(result,allow_nan=False),flush=True)


if __name__=='__main__':
    try:main()
    except Exception as exc:
        print(json.dumps(dict(status='BLOCKED',reason=safe_reason(exc),broker_orders=0,live_enabled=False)),flush=True)
        raise SystemExit(1)
