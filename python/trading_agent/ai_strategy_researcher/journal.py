"""Persistent research budgets, immutable experiments and an auditable event chain."""
from contextlib import contextmanager
from datetime import datetime,timezone
import json
import os
import re
import sqlite3
from .contracts import digest,encoded,strict_json,utc,at,number,candidate_version
from .configuration import estimated_cost
from .data import safe_path,FOLDER


def verify_event_chain(db):
    previous='0'*64
    for e in db.execute('SELECT * FROM events ORDER BY sequence'):
        value=dict(session=e['session'],kind=e['kind'],payload=strict_json(e['payload']),at=e['at'],previous_hash=e['previous_hash'])
        if e['previous_hash']!=previous or digest(value)!=e['hash']:raise ValueError('RESEARCH_JOURNAL_TAMPERED')
        previous=e['hash']
    return previous


def memory_rows(db):
    # Fail explicitly rather than silently forgetting old failures at scale.
    rows=db.execute('SELECT e.*,s.binding FROM experiments e JOIN sessions s ON s.id=e.session ORDER BY e.created_at,e.id LIMIT 1001').fetchall()
    if len(rows)>1000:raise ValueError('RESEARCH_MEMORY_RECORD_LIMIT')
    completed={}
    for event in db.execute("SELECT payload FROM events WHERE kind='EXPERIMENT_COMPLETED'"):
        payload=strict_json(event['payload']);completed[payload['experiment_id']]=payload['result_hash']
    for r in rows:
        if r['state']=='COMPLETED' and (not r['result'] or digest(strict_json(r['result']))!=completed.get(r['id'])):
            raise ValueError('RESEARCH_MEMORY_RESULT_HASH_MISMATCH')
        if r['state']=='COMPLETED':
            proposal,result=strict_json(r['proposal']),strict_json(r['result'])
            if proposal['candidate']!=result['candidate'] or candidate_version(proposal['candidate'])!=r['version'] or result['version']!=r['version']:
                raise ValueError('RESEARCH_MEMORY_SPECIFICATION_MISMATCH')
    return [{**dict(r),'proposal':strict_json(r['proposal']),
             'result':strict_json(r['result']) if r['result'] else None,
             'provider':strict_json(r['binding'])['provider']} for r in rows]


def memory_rejections(db):
    rows=db.execute("SELECT session,payload FROM events WHERE kind='PROPOSAL_REJECTED' ORDER BY sequence LIMIT 1001").fetchall()
    if len(rows)>1000:raise ValueError('RESEARCH_MEMORY_RECORD_LIMIT')
    out=[]
    for row in rows:
        p=strict_json(row['payload']);code=p.get('validation_code');field=p.get('field');category=p.get('category')
        known=(type(code) is str and re.fullmatch('[A-Z][A-Z0-9_]{1,100}',code) and
               type(field) is str and re.fullmatch(r'\$[.A-Za-z0-9_]{0,100}',field) and category in ('FORMAT','PARAMETER','EVIDENCE'))
        out.append(dict(session=row['session'],code=code if known else 'UNKNOWN_LEGACY_GENERIC_REJECTION',
                        field=field if known else None,category=category if known else 'UNKNOWN',raw_body_available=False))
    return out


def memory_decisions(db):
    """Hash-verified decisions and bounded safe provenance, including zero-candidate sessions."""
    verify_event_chain(db)
    deferred=[]
    rows=db.execute("SELECT * FROM events WHERE kind='RESEARCH_DEFERRED' ORDER BY sequence LIMIT 1001").fetchall()
    if len(rows)>1000:raise ValueError('RESEARCH_MEMORY_RECORD_LIMIT')
    for row in rows:
        p=strict_json(row['payload'])
        call=db.execute('SELECT session,state FROM calls WHERE id=?',(p['call_id'],)).fetchone()
        consulted=db.execute("SELECT payload FROM events WHERE session=? AND kind='RESEARCH_MEMORY_CONSULTED' AND sequence<? ORDER BY sequence DESC",
                             (row['session'],row['sequence'])).fetchall()
        linked=[strict_json(r['payload']) for r in consulted if strict_json(r['payload']).get('call_id')==p['call_id']]
        if not call or call['session']!=row['session'] or call['state']!='COMPLETED' or len(linked)!=1 or linked[0]['snapshot_sha256']!=p['memory_sha256']:
            raise ValueError('RESEARCH_DEFER_BINDING_FAILED')
        deferred.append(dict(evidence_id='memory_defer_'+row['hash'][:20],session=row['session'],at=row['at'],
            event_hash=row['hash'],research_plan=p['research_plan'],memory_sha256=p['memory_sha256'],
            proposal_sha256=p['proposal_sha256'],call_id=p['call_id']))
    sessions=db.execute('SELECT id,state,reason,binding FROM sessions ORDER BY started_at LIMIT 1001').fetchall()
    calls=db.execute('SELECT session,state,input_tokens,output_tokens,cost,usage_status,error FROM calls ORDER BY id LIMIT 1001').fetchall()
    if max(len(sessions),len(calls))>1000:raise ValueError('RESEARCH_MEMORY_RECORD_LIMIT')
    safe=lambda s:s if type(s) is str and re.fullmatch('[A-Z][A-Z0-9_]{1,100}',s) else None
    return dict(deferred=deferred,sessions=[dict(session=r['id'],state=r['state'],reason=safe(r['reason']),
        binding_sha256=digest(strict_json(r['binding']))) for r in sessions],
        calls=[dict(session=r['session'],state=r['state'],input_tokens=r['input_tokens'],output_tokens=r['output_tokens'],
                    estimated_or_reserved_cost=r['cost'],usage_status=safe(r['usage_status']),error=safe(r['error'])) for r in calls])


def session_name(name):
    if type(name) is not str or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,48}',name):
        raise ValueError('SAFE_SESSION_ID_REQUIRED')
    return name


@contextmanager
def exclusive(root):
    path=safe_path(root,FOLDER+'/research.lock');path.parent.mkdir(parents=True,exist_ok=True)
    handle=open(path,'a+b');handle.seek(0)
    if path.stat().st_size==0:handle.write(b'0');handle.flush()
    handle.seek(0);locked=False
    try:
        if os.name=='nt':
            import msvcrt
            msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        locked=True;yield
    except OSError as exc:raise RuntimeError('RESEARCH_ALREADY_RUNNING') from None
    finally:
        if locked:
            handle.seek(0)
            if os.name=='nt':msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(handle,fcntl.LOCK_UN)
        handle.close()


class Journal:
    def __init__(self,root):
        path=safe_path(root,FOLDER+'/journal.sqlite3');path.parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(path,timeout=3,isolation_level=None);self.db.row_factory=sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON');self.db.execute('PRAGMA synchronous=FULL')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY,binding TEXT NOT NULL,
                started_at TEXT NOT NULL,state TEXT NOT NULL,reason TEXT);
            CREATE TABLE IF NOT EXISTS calls(id INTEGER PRIMARY KEY,session TEXT NOT NULL REFERENCES sessions(id),
                provider TEXT NOT NULL,model TEXT NOT NULL,request_hash TEXT NOT NULL,state TEXT NOT NULL,
                input_tokens INTEGER NOT NULL,output_tokens INTEGER NOT NULL,cost TEXT NOT NULL,
                reservation TEXT NOT NULL,latency REAL,usage_status TEXT NOT NULL,error TEXT);
            CREATE TABLE IF NOT EXISTS experiments(id TEXT PRIMARY KEY,session TEXT NOT NULL REFERENCES sessions(id),
                version TEXT NOT NULL,proposal TEXT NOT NULL,state TEXT NOT NULL,result TEXT,
                backtests INTEGER NOT NULL,created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events(sequence INTEGER PRIMARY KEY,session TEXT NOT NULL,
                kind TEXT NOT NULL,payload TEXT NOT NULL,at TEXT NOT NULL,previous_hash TEXT NOT NULL,hash TEXT NOT NULL);
        ''')
        try:self.verify_chain()
        except BaseException:
            self.db.close();raise

    def close(self):self.db.close()

    @contextmanager
    def transaction(self):
        self.db.execute('BEGIN IMMEDIATE')
        try:yield;self.db.execute('COMMIT')
        except BaseException:self.db.execute('ROLLBACK');raise

    def event(self,session,kind,payload):
        last=self.db.execute('SELECT hash FROM events ORDER BY sequence DESC LIMIT 1').fetchone()
        previous=last['hash'] if last else '0'*64;stamp=utc();value=dict(session=session,kind=kind,payload=payload,at=stamp,previous_hash=previous)
        self.db.execute('INSERT INTO events(session,kind,payload,at,previous_hash,hash) VALUES(?,?,?,?,?,?)',
            (session,kind,encoded(payload).decode(),stamp,previous,digest(value)))

    def verify_chain(self):
        return verify_event_chain(self.db)

    def memory_records(self):return memory_rows(self.db)
    def memory_rejections(self):return memory_rejections(self.db)
    def memory_decisions(self):return memory_decisions(self.db)

    def bind(self,session,binding):
        session_name(session);raw=encoded(binding).decode()
        with self.transaction():
            row=self.db.execute('SELECT * FROM sessions WHERE id=?',(session,)).fetchone()
            if row:
                if row['binding']!=raw:raise ValueError('SESSION_CONFIGURATION_OR_DATA_CHANGED')
                if self.db.execute("SELECT 1 FROM calls WHERE session=? AND state='RESERVED'",(session,)).fetchone() or self.db.execute("SELECT 1 FROM experiments WHERE session=? AND state='PENDING'",(session,)).fetchone():
                    self.db.execute("UPDATE calls SET state='RECOVERED_UNKNOWN_USAGE',usage_status='UNKNOWN_CHARGED_FULL_RESERVE' WHERE session=? AND state='RESERVED'",(session,))
                    self.db.execute("UPDATE sessions SET state='SUSPENDED',reason='UNRESOLVED_RESEARCH_REQUEST' WHERE id=?",(session,))
                    self.event(session,'RECOVERY_SUSPENDED',{'reason':'UNRESOLVED_RESEARCH_REQUEST'})
            else:
                self.db.execute('INSERT INTO sessions VALUES(?,?,?,?,?)',(session,raw,utc(),'ACTIVE',None))
                self.event(session,'SESSION_CREATED',binding)
        return self.status(session)

    def status(self,session):
        row=self.db.execute('SELECT * FROM sessions WHERE id=?',(session_name(session),)).fetchone()
        if not row:raise ValueError('SESSION_NOT_FOUND')
        calls=[dict(x) for x in self.db.execute('SELECT * FROM calls WHERE session=? ORDER BY id',(session,))]
        experiments=[dict(x) for x in self.db.execute('SELECT * FROM experiments WHERE session=? ORDER BY created_at,id',(session,))]
        return dict(session=session,state=row['state'],reason=row['reason'],started_at=row['started_at'],
            config=strict_json(row['binding'])['config'],provider_calls=len(calls),
            input_tokens=sum(c['input_tokens'] for c in calls),output_tokens=sum(c['output_tokens'] for c in calls),
            estimated_or_reserved_cost_usd=str(sum((number(c['cost']) for c in calls),number(0))),
            backtests_reserved=sum(e['backtests'] for e in experiments),candidates=len(experiments),
            calls=calls,experiments=[{**e,'proposal':strict_json(e['proposal']),
                'result':strict_json(e['result']) if e['result'] else None} for e in experiments],
            orders_sent=0,execution_authorized=False,live_approved=False)

    def remaining_seconds(self,session):
        s=self.status(session);elapsed=(datetime.now(timezone.utc)-at(s['started_at'])).total_seconds()
        if elapsed<0:raise ValueError('RESEARCH_CLOCK_MOVED_BACKWARDS')
        return max(0,s['config']['max_seconds']-elapsed)

    def failure_state(self,session):
        """Resume a failure streak from events; restarting cannot reset the circuit."""
        count=0;feedback=None;reason=None
        for row in self.db.execute('SELECT kind,payload FROM events WHERE session=? ORDER BY sequence',(session,)):
            payload=strict_json(row['payload']);kind=row['kind']
            if kind=='PROVIDER_FINALIZED' and payload.get('error'):
                count+=1;feedback=None;reason='PROVIDER_CIRCUIT_OPEN'
            elif kind=='PROPOSAL_REJECTED':
                count+=1;reason='INVALID_PROPOSAL_CIRCUIT_OPEN'
                keys=('validation_code','field','category')
                feedback={k:payload[k] for k in keys} if all(k in payload for k in keys) else None
            elif kind in ('PROPOSAL_ACCEPTED','EXPERIMENT_RESERVED','DUPLICATE_HYPOTHESIS'):
                count=0;feedback=None;reason=None
        return dict(count=count,feedback=feedback,reason=reason)

    def reserve_call(self,session,provider,request_hash,input_bound,output_bound):
        with self.transaction():
            s=self.status(session);c=s['config'];cost=estimated_cost(c,input_bound,output_bound)
            if s['state']!='ACTIVE' or self.remaining_seconds(session)<=0:raise ValueError('RESEARCH_SESSION_STOPPED_OR_EXPIRED')
            if s['provider_calls']>=c['max_provider_calls']:raise ValueError('PROVIDER_CALL_BUDGET_EXHAUSTED')
            if s['input_tokens']+s['output_tokens']+input_bound+output_bound>c['max_total_tokens']:raise ValueError('TOKEN_BUDGET_EXHAUSTED')
            if number(s['estimated_or_reserved_cost_usd'])+cost>number(c['max_cost_usd']):raise ValueError('COST_BUDGET_EXHAUSTED')
            reservation=dict(input_bound=input_bound,output_bound=output_bound,estimated_cost=str(cost))
            cur=self.db.execute('INSERT INTO calls(session,provider,model,request_hash,state,input_tokens,output_tokens,cost,reservation,usage_status) VALUES(?,?,?,?,?,?,?,?,?,?)',
                (session,provider,c['model'] if provider=='openai' else 'SIMULATED_NO_MODEL',request_hash,'RESERVED',input_bound,output_bound,str(cost),encoded(reservation).decode(),'RESERVED_WORST_CASE'))
            self.event(session,'PROVIDER_RESERVED',dict(call_id=cur.lastrowid,**reservation))
            return cur.lastrowid

    def finish_call(self,call_id,usage,latency,error=None):
        with self.transaction():
            call=self.db.execute('SELECT * FROM calls WHERE id=?',(call_id,)).fetchone()
            if not call or call['state']!='RESERVED':raise ValueError('CALL_ALREADY_FINALIZED')
            c=self.status(call['session'])['config'];r=strict_json(call['reservation']);exceeded=False
            if usage is not None:
                i,o=usage['input_tokens'],usage['output_tokens']
                if type(i) is not int or type(o) is not int or min(i,o)<0:raise ValueError('USAGE_INVALID')
                cost=estimated_cost(c,i,o);status='API_USAGE_CONFIGURED_PRICE_CEILINGS'
                exceeded=i>r['input_bound'] or o>r['output_bound']
            else:i,o,cost,status=call['input_tokens'],call['output_tokens'],number(call['cost']),'UNKNOWN_CHARGED_FULL_RESERVE'
            self.db.execute('UPDATE calls SET state=?,input_tokens=?,output_tokens=?,cost=?,latency=?,usage_status=?,error=? WHERE id=?',
                ('FAILED' if error else 'COMPLETED',i,o,str(cost),latency,status,error,call_id))
            self.event(call['session'],'PROVIDER_FINALIZED',dict(call_id=call_id,input_tokens=i,output_tokens=o,cost=str(cost),usage_status=status,error=error))
            if exceeded:
                self.db.execute("UPDATE sessions SET state='SUSPENDED',reason='PROVIDER_USAGE_EXCEEDED_RESERVATION' WHERE id=?",(call['session'],))
            return exceeded

    def lookup(self,key):
        r=self.db.execute('SELECT * FROM experiments WHERE id=?',(key,)).fetchone()
        return dict(r) if r else None

    def reserve_experiment(self,session,key,version,proposal):
        with self.transaction():
            s=self.status(session);c=s['config']
            if s['state']!='ACTIVE' or self.remaining_seconds(session)<=0:raise ValueError('RESEARCH_SESSION_STOPPED_OR_EXPIRED')
            if self.lookup(key):raise ValueError('EXPERIMENT_ALREADY_EXISTS')
            if s['candidates']>=c['max_candidates'] or s['backtests_reserved']+15>c['max_backtests']:
                raise ValueError('EXPERIMENT_BUDGET_EXHAUSTED')
            self.db.execute('INSERT INTO experiments VALUES(?,?,?,?,?,?,?,?)',
                (key,session,version,encoded(proposal).decode(),'PENDING',None,15,utc()))
            self.event(session,'EXPERIMENT_RESERVED',dict(experiment_id=key,version=version,backtests=15))

    def finish_experiment(self,key,result):
        with self.transaction():
            e=self.lookup(key)
            if not e or e['state']!='PENDING':raise ValueError('EXPERIMENT_ALREADY_FINALIZED')
            self.db.execute('UPDATE experiments SET state=?,result=? WHERE id=?',('COMPLETED',encoded(result).decode(),key))
            self.event(e['session'],'EXPERIMENT_COMPLETED',dict(experiment_id=key,result_hash=digest(result)))

    def stop(self,session,state,reason):
        if state not in ('COMPLETED','BUDGET_STOP','SUSPENDED'):raise ValueError('RESEARCH_STOP_STATE_REQUIRED')
        with self.transaction():
            self.db.execute('UPDATE sessions SET state=?,reason=? WHERE id=?',(state,reason,session))
            self.event(session,'SESSION_STOPPED',dict(state=state,reason=reason))

    def history(self):
        out=[]
        for r in self.db.execute("SELECT version,proposal,result FROM experiments WHERE state='COMPLETED' ORDER BY created_at DESC LIMIT 5"):
            p,result=strict_json(r['proposal']),strict_json(r['result'])
            out.append(dict(version=r['version'],candidate=p['candidate'],status=result['status'],
                metrics=result['results']['TIERED_BASE']['validation']['metrics'],reasons=result['rejection_reasons']))
        return list(reversed(out))

    def family_size(self,session=None):
        # Includes previous 192 comparisons and every reserved hypothesis, across sessions/restarts.
        count=self.db.execute('SELECT COUNT(*) FROM experiments').fetchone()[0]
        remaining=1
        if session:
            s=self.status(session);remaining=max(0,s['config']['max_candidates']-s['candidates'])
        return 192+3*(count+remaining)
