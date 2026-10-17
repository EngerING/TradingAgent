"""Autonomous controlled replay runner. No operational store or broker execution.

Authentic reading is a separate capability in r20_market; its records are never
relabelled as replay. A future operational deployment must implement its own
store/permission boundary, rather than bypassing TestStore.
"""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import time

from .aggressive_growth_runner import run_lock
from .r20_profiles import digest, encoded, strict_json
from .r20_persistence import sql_text
from .r20_admission import RoleStore


def source_manifest(root):
    root=Path(root)
    paths=sorted(set(root.glob('python/trading_agent/r20_*.py')) |
                 set(root.glob('python/trading_agent/r20_*schema.sql')) |
                 {root/'python/trading_agent/aggressive_growth.py',
                  root/'python/trading_agent/aggressive_growth_runner.py',
                  root/'config/aggressive-growth-r20.json'})
    sources={p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    return dict(sources=sources,engineHash=digest(sources),classification='SYNTHETIC_REPLAY_LAB',
                economicTimezone='America/Santo_Domingo',stopPolicy='NO_NEW_ENTRIES_MANAGE_TO_VALID_EXIT',
                exitPolicy='FRESH_QUOTE_SL_TP_DEFENSIVE_NO_INTRABAR_INVENTION',brokerOrders=False)


class RunnerControl:
    def __init__(self,store,scope):
        from .r20_economics import identity
        identity(scope);self.store,self.scope=store,scope

    @staticmethod
    def install(store):
        if isinstance(store,RoleStore):raise ValueError('OWNER_SETUP_ONLY')
        store.execute(Path(__file__).with_name('r20_runner_schema.sql').read_text(encoding='utf-8'))

    def preregister(self,manifest):
        if isinstance(self.store,RoleStore):raise ValueError('OWNER_SETUP_ONLY')
        if manifest.get('classification')!='SYNTHETIC_REPLAY_LAB':raise ValueError('REPLAY_ONLY')
        existing=self.state()['manifest']
        if existing is not None:
            if existing!=manifest:raise ValueError('IMMUTABLE_PREREGISTRATION')
            return
        body=encoded(manifest)
        self.store.execute('INSERT INTO r20_v2_runner.controls VALUES('+','.join((sql_text(self.scope),
            "'PREREGISTER'",sql_text(body),sql_text(digest(manifest))))+');')

    def state(self):
        raw=self.store.execute('SELECT json_build_object(\'kind\',kind,\'payload\',payload,\'hash\',hash)::text '
            'FROM r20_v2_runner.controls WHERE scope='+sql_text(self.scope)+' ORDER BY kind;')
        data={}
        for line in raw.splitlines():
            row=strict_json(line);value=strict_json(row['payload'])
            if digest(value)!=row['hash']:raise ValueError('RUNNER_CONTROL_INTEGRITY')
            data[row['kind']]=value
        return dict(manifest=data.get('PREREGISTER'),stopRequested='STOP' in data,stop=data.get('STOP'))

    def stop(self,actor):
        from .r20_economics import identity
        identity(actor)
        body=encoded(dict(actor=actor,at=datetime.now(timezone.utc),requested=True))
        self.store.execute('SELECT r20_v2_runner.control('+','.join((sql_text(self.scope),"'STOP'",sql_text(body)))+');')


class ReplayRunner:
    def __init__(self,cycle,control,root):
        if cycle.scope!=control.scope:raise ValueError('RUNNER_SCOPE_MISMATCH')
        self.cycle,self.control,self.root=cycle,control,Path(root)
        if control.state()['manifest']!=source_manifest(root):raise ValueError('PREREGISTERED_ENGINE_CHANGED')

    def status(self):
        state=self.control.state();view=self.cycle.view()
        pending=self.cycle.store.load(self.cycle.scope).snapshot.daily.pending_terms
        status=('STOPPING_MANAGING_SHADOW' if view['positions'] or pending else 'STOPPED') if state['stopRequested'] else 'PREPARED_REPLAY'
        return dict(view,runner=dict(state,status=status),status=status)

    def step(self,quote,key,bars=None,minutes=None):
        # Every step reloads ledger state, resolving lost acknowledgements.
        if self.control.state()['manifest']!=source_manifest(self.root):raise ValueError('PREREGISTERED_ENGINE_CHANGED')
        if self.control.state()['stopRequested']:
            from .r20_profiles import economic_day,utc
            head=self.cycle.store.load(self.cycle.scope)
            if economic_day(utc(self.cycle.clock()))[0]!=head.snapshot.daily.day_id:
                try:quote.validate(self.cycle.clock())
                except ValueError:return self.cycle.observe(quote,key)
                self.cycle.roll_management_day(quote,'stop-day-'+key)
            pending={p.position_id for p in self.cycle.store.load(self.cycle.scope).snapshot.daily.pending_terms}
            for receipt in self.cycle.admission.receipts():
                if receipt['signal']['signal_id'] in pending:
                    self.cycle.release(receipt['requestId'],'stop-release-'+receipt['requestId'])
            if not self.cycle.inventory():return self.status()
        result=self.cycle.observe(quote,key)
        # A reservation surviving interruption is not a fill. Release it only
        # after a valid observation rolls the economic day if necessary.
        if result.get('kind')=='DATA_UNAVAILABLE':return result
        pending={p.position_id for p in self.cycle.store.load(self.cycle.scope).snapshot.daily.pending_terms}
        for receipt in self.cycle.admission.receipts():
            if receipt['signal']['signal_id'] in pending:
                self.cycle.release(receipt['requestId'],'recovery-release-'+receipt['requestId'])
        if bars is not None and not self.control.state()['stopRequested']:
            try:
                receipt=self.cycle.reserve_engine(self.root,bars,minutes,quote,'signal-'+key,
                    quality='SYNTHETIC_CONTIGUOUS_COMPLETE')
                if 'requestId' in receipt:
                    return self.cycle.open(receipt['requestId'],quote,'entry-'+key)
            except ValueError as exc:
                return self.diagnostic('reject-'+key,'REJECTED:'+str(exc))
        return result

    def diagnostic(self,key,reason):
        request=dict(action='runner-diagnostic',reason=reason,decision=None,
                     intrabarProtection='UNVERIFIED_BETWEEN_QUOTES')
        replay=self.cycle._replay(key,request)
        if replay:return replay
        rows,head=self.cycle._state()
        return self.cycle._commit(key,request,'SIGNAL_DIAGNOSTIC',head.snapshot,
            rows[-1]['positions'] if rows else [],rows[-1]['trades'] if rows else [],reason=reason,expected_head=head)

    def run(self,source,poll_seconds=1):
        """Finite or streaming explicit replay; caller owns data and clock.

        Replayed records have stable keys. No automatic reservation/open command:
        admission remains an explicit independently permitted transaction.
        """
        if not 0<=poll_seconds<=60:raise ValueError('POLL_RANGE')
        path=self.root/'.local/r20-v2-replay'/self.cycle.store.database/'singleton.lock'
        with run_lock(path):
            for record in source:
                key,quote,*analysis=record
                self.step(quote,key,*analysis)
                if self.status()['status']=='STOPPED':break
                if poll_seconds:time.sleep(poll_seconds)


class ReadOnlyObserver:
    """Authentic diagnostics only: no store, profile, permission or virtual fill.

    Caller schedules polls explicitly. Each poll revalidates exact account binding
    through PaperReadSource, including after a disconnect. No synthetic conversion.
    """
    def __init__(self,root,*,source=None,client_id=196):
        from .r20_market import PaperReadSource
        self.source=source or PaperReadSource(root,client_id=client_id)

    def poll(self):
        try:
            raw,view=self.source.poll()
            return dict(status='READ_ONLY_DIAGNOSTIC',market= view,source=raw,
                entryEligible=False,cohortStarted=False,brokerOrders=0)
        except (ConnectionError,TimeoutError,OSError,ValueError) as exc:
            return dict(status='DATA_UNAVAILABLE',error=type(exc).__name__,market=None,
                entryEligible=False,cohortStarted=False,brokerOrders=0)


def main():
    """Explicit lab CLI only. Does not install, initialize or activate anything."""
    import argparse,os
    from .r20_shadow import ShadowCycle,Quote
    from .r20_profiles import decimal_text
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=('Status','Stop','Replay','ReadOnly'))
    parser.add_argument('--root',required=True);parser.add_argument('--replay')
    args=parser.parse_args()
    if args.action=='ReadOnly':
        print(encoded(ReadOnlyObserver(args.root).poll()));return
    store=RoleStore(os.environ['R20_V2_TEST_DATABASE'],os.environ['R20_V2_TEST_SYSTEM_ID'],
                    'reader' if args.action=='Status' else 'shadow')
    context=strict_json(Path(os.environ['R20_V2_CONTEXT']).read_text(encoding='utf-8'))
    cycle=ShadowCycle(store,context);control=RunnerControl(store,cycle.scope)
    runner=ReplayRunner(cycle,control,args.root)
    if args.action=='Stop':control.stop('explicit-lab-operator')
    elif args.action=='Replay':
        if args.replay is None:raise ValueError('EXPLICIT_REPLAY_REQUIRED')
        raw=strict_json(Path(args.replay).read_text(encoding='utf-8'))
        if raw.get('classification')!='SYNTHETIC_TEST_ONLY':raise ValueError('REPLAY_SOURCE_REQUIRED')
        lock=Path(args.root)/'.local/r20-v2-replay'/store.database/'singleton.lock'
        with run_lock(lock):
            for record in raw['records']:
                q=record['quote'];quote=Quote(**dict(q,bid=decimal_text(q['bid']),ask=decimal_text(q['ask']),at=datetime.fromisoformat(q['at'])))
                cycle.clock=lambda at=quote.at:at
                runner.step(quote,record['key'],record.get('bars'),record.get('minutes'))
                if runner.status()['status']=='STOPPED':break
    print(encoded(runner.status()))

if __name__=='__main__':main()
