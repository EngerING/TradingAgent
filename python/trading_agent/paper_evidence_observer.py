"""Preregistered read-only Paper study; no AI provider, strategy or executor imports."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from statistics import median
import time
from zoneinfo import ZoneInfo
from .ai_strategy_researcher.contracts import encoded,digest,strict_json,at,utc
from .ai_strategy_researcher.data import safe_path

FOLDER='artifacts/research/paper-evidence-observer'
CONFIG='config/paper-evidence-observer.json'
REQUIRED=('stock_etf_permissions','effective_fee_plan','effective_per_order_fees','SettledCash_USD',
          'effective_intraday_restrictions','contract_specific_margin','effective_minimum_quantity','quantity_increment')


def folder(root,study):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,48}',study):raise ValueError('SAFE_STUDY_ID_REQUIRED')
    return safe_path(root,FOLDER+'/'+study)


def validate_config(c):
    expected={'schema_version','environment','symbol','sessions','capital_usd','exposure','poll_seconds',
        'calendar_refresh_seconds','capabilities_refresh_seconds','request_timeout_seconds','client_id',
        'max_quote_age_seconds','maximum_midpoint_jump_ratio','minimum_live_coverage','maximum_gap_seconds',
        'required_capabilities','corporate_action_coverage','max_future_research_cost_usd'}
    if set(c)!=expected or any(c[k]!=v or type(c[k])!=type(v) for k,v in dict(schema_version=1,
            environment='PAPER_TRADING',symbol='F',sessions=20,capital_usd=100,exposure=1).items()):
        raise ValueError('OBSERVER_FIXED_SCOPE_REQUIRED')
    for key,lo,hi in [('poll_seconds',30,300),('calendar_refresh_seconds',900,86400),
                     ('capabilities_refresh_seconds',3600,86400),('request_timeout_seconds',1,30),
                     ('client_id',1,999),('max_quote_age_seconds',1,120),('maximum_gap_seconds',60,1800)]:
        if type(c[key]) is not int or not lo<=c[key]<=hi:raise ValueError('OBSERVER_BOUNDS_REQUIRED')
    if not .9<=c['minimum_live_coverage']<=1 or not 0<c['maximum_midpoint_jump_ratio']<=.1 or c['required_capabilities']!=list(REQUIRED):
        raise ValueError('OBSERVER_QUALITY_GATE_REQUIRED')
    if c['corporate_action_coverage']!='UNKNOWN' or c['max_future_research_cost_usd']!='1.00':
        raise ValueError('OBSERVER_UNKNOWN_OR_BUDGET_REQUIRED')
    return c


def prepare(root,study):
    from .ai_strategy_researcher.data import load_dataset
    from .ai_strategy_researcher.memory import load_readonly
    c=validate_config(strict_json(safe_path(root,CONFIG).read_bytes()))
    package,_=load_dataset(root);memory=load_readonly(Path(root).resolve(),package)
    spec=dict(config=c,registered_at=utc(),protocol='F_20_AUTHENTIC_RTH_SESSIONS_V1',
        first_session_rule='FIRST_FULL_SESSION_AFTER_EXPLICIT_RUN_START',
        missed_sessions='COUNT_ALL_AUTHENTIC_SESSIONS_IN_ORDER_INCLUDING_MISSING',
        timestamp_policy='UTC_RECEIPT_IS_NOT_EXCHANGE_QUOTE_TIMESTAMP',
        calendar='IBKR_SCHEDULE_AND_CONTRACT_LIQUID_HOURS_ONLY_NO_TEMPLATE',
        final_holdout='SEALED_NOT_READ',baseline_history_sha256=memory['history_sha256'],
        baseline_event_chain_head=memory['event_chain_head'],
        baseline_deferred_ids=[d['evidence_id'] for d in memory.get('deferred_decisions',[])],
        baseline_memory_sha256=digest(memory),execution_authorized=False,openai_requests=0)
    binding=safe_path(root,'.local/ibkr-account-binding.dpapi')
    spec['account_binding_sha256']=hashlib.sha256(binding.read_bytes()).hexdigest() if binding.exists() else 'ABSENT'
    dest=folder(root,study);dest.mkdir(parents=True,exist_ok=True)
    with (dest/'spec.json').open('xb') as f:f.write(encoded(spec))
    with (dest/'spec.sha256').open('x',encoding='ascii') as f:f.write(digest(spec))
    return dict(study=study,state='PREREGISTERED_NOT_STARTED',spec_sha256=digest(spec),config=c)


def load_spec(root,study):
    dest=folder(root,study);raw=(dest/'spec.json').read_bytes()
    if len(raw)>50000 or hashlib.sha256(raw).hexdigest()!=(dest/'spec.sha256').read_text():
        raise ValueError('OBSERVER_SPEC_TAMPERED')
    spec=strict_json(raw);validate_config(spec['config']);return spec


@contextmanager
def locked(dest):
    import msvcrt
    with (dest/'observer.lock').open('a+b') as f:
        if f.seek(0,2)==0:f.write(b'0');f.flush()
        f.seek(0)
        try:msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:raise ValueError('OBSERVER_ALREADY_RUNNING') from None
        try:yield
        finally:f.seek(0);msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)


class Store:
    def __init__(self,path,spec,readonly=False):
        self.db=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True) if readonly else sqlite3.connect(path)
        if readonly:self.db.execute('BEGIN')
        if not readonly:
            self.db.execute('PRAGMA synchronous=FULL')
            self.db.execute('CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY,kind TEXT,payload TEXT,at TEXT,previous TEXT,hash TEXT)')
        try:
            self.verify()
            rows=self.rows()
            if rows and (rows[0]['kind']!='BOUND' or rows[0]['payload']!={'spec_sha256':digest(spec)}):raise ValueError('OBSERVER_SPEC_BINDING_CHANGED')
            if not rows and not readonly:self.append('BOUND',{'spec_sha256':digest(spec)})
        except BaseException:self.db.close();raise
    def close(self):self.db.close()
    def rows(self):
        return [dict(seq=r[0],kind=r[1],payload=strict_json(r[2]),at=r[3],previous=r[4],hash=r[5]) for r in self.db.execute('SELECT * FROM events ORDER BY seq')]
    def verify(self):
        previous='0'*64
        for r in self.rows():
            if r['previous']!=previous or digest({k:r[k] for k in ('kind','payload','at','previous')})!=r['hash']:
                raise ValueError('OBSERVER_JOURNAL_TAMPERED')
            previous=r['hash']
    def append(self,kind,payload,stamp=None):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            row=self.db.execute('SELECT hash FROM events ORDER BY seq DESC LIMIT 1').fetchone()
            value=dict(kind=kind,payload=payload,at=stamp or utc(),previous=row[0] if row else '0'*64)
            self.db.execute('INSERT INTO events(kind,payload,at,previous,hash) VALUES(?,?,?,?,?)',
                            (kind,encoded(payload).decode(),value['at'],value['previous'],digest(value)))
            self.db.commit()
        except BaseException:self.db.rollback();raise


def point(value,zone,fmt):
    wall=datetime.strptime(value,fmt);a=wall.replace(tzinfo=zone,fold=0);b=wall.replace(tzinfo=zone,fold=1)
    if a.utcoffset()!=b.utcoffset() or a.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None)!=wall:
        raise ValueError('OBSERVER_DST_UNCERTAIN')
    return a.astimezone(timezone.utc)


def sessions_from(contract,schedule,now):
    if not 0<=(now-at(contract['received_at'])).total_seconds()<=300:raise ValueError('OBSERVER_CALENDAR_STALE')
    sessions={}
    def add(day,start,end):
        if end<=start or start.astimezone(ZoneInfo('America/New_York')).strftime('%Y%m%d')!=day:raise ValueError('OBSERVER_SESSION_INVALID')
        value=dict(day=day,start=start.isoformat(),end=end.isoformat())
        if day in sessions and sessions[day]!=value:raise ValueError('OBSERVER_CALENDAR_CONFLICT')
        sessions[day]=value
    for row in schedule:
        zone=ZoneInfo(row['time_zone']);add(row['day'],point(row['start'],zone,'%Y%m%d-%H:%M:%S'),point(row['end'],zone,'%Y%m%d-%H:%M:%S'))
    zone=ZoneInfo(contract['time_zone'])
    for entry in contract['liquid_hours'].split(';'):
        if not entry:continue
        day,period=entry.split(':',1)
        if period=='CLOSED':continue
        if ',' in period:raise ValueError('OBSERVER_SPLIT_SESSION_UNSUPPORTED')
        start,end=period.split('-')
        add(day,point(start if ':' in start else day+':'+start,zone,'%Y%m%d:%H%M'),
            point(end if ':' in end else day+':'+end,zone,'%Y%m%d:%H%M'))
    if not sessions:raise ValueError('OBSERVER_CALENDAR_MISSING')
    return sorted(sessions.values(),key=lambda s:s['start'])


def classify(raw,now,c):
    from .tws import finite
    result=dict(raw);flags=[];kind='MISSING';bid=ask=None
    try:
        bid,ask=finite(raw['bid'],True),finite(raw['ask'],True)
        if ask<bid:flags.append('CROSSED_BOOK')
        ages=[(now-at(raw['field_received_at'][k])).total_seconds() for k in ('bid','ask')]
        if any(v<0 for v in ages):flags.append('FUTURE_RECEIPT_TIMESTAMP')
        if not flags:
            kind={1:'LIVE',2:'STALE',3:'DELAYED',4:'STALE'}.get(raw['market_data_type'],'MISSING')
            if any(v>c['max_quote_age_seconds'] for v in ages):kind='STALE'
    except (ValueError,ArithmeticError,KeyError,TypeError):flags.append('BID_ASK_OR_TIMESTAMP_UNAVAILABLE')
    result.update(status=kind,observed_at=now.isoformat(),spread=str(ask-bid) if bid and ask and ask>=bid else None,
        midpoint=str((ask+bid)/2) if bid and ask and ask>=bid else None,flags=flags,
        timestamp_status='RECEIPT_ONLY_QUOTE_EXCHANGE_TIME_UNKNOWN',slippage='UNKNOWN',executable=False)
    return result


def project(spec,rows,now):
    c=spec['config'];anchors=[r for r in rows if r['kind']=='STARTED'];known={};conflict=False
    for r in rows:
        if r['kind']=='CALENDAR':
            for s in r['payload']['sessions']:
                if s['day'] in known and known[s['day']]!=s:conflict=True
                known[s['day']]=s
    anchor=at(anchors[0]['at']) if anchors else None
    selected=sorted((s for s in known.values() if anchor and at(s['start'])>=anchor),key=lambda s:s['start'])[:20]
    reports=[]
    for s in selected:
        a,b=at(s['start']),at(s['end']);finished=b<=now
        samples=[r['payload'] for r in rows if r['kind']=='QUOTE' and a<=at(r['payload']['observed_at'])<b]
        expected=max(1,int((b-a).total_seconds()/c['poll_seconds']))
        # Unique preregistered slots prevent repeated samples inflating coverage.
        slots={int((at(q['observed_at'])-a).total_seconds()/c['poll_seconds']) for q in samples if q['status']=='LIVE' and not q['flags']}
        times=sorted({at(q['observed_at']) for q in samples})
        gaps=[(y-x).total_seconds() for x,y in zip([a]+times,times+[b if finished else min(b,now)])]
        reports.append(dict(**s,finished=finished,samples=len(samples),expected_slots=expected,
            live_slots=len(slots),live_coverage=min(1,len(slots)/expected),maximum_gap_seconds=max(gaps,default=(b-a).total_seconds()),
            statuses={k:sum(q['status']==k for q in samples) for k in ('LIVE','DELAYED','STALE','MISSING')},
            anomalies=sum(bool(q['flags']) for q in samples)))
    facts={};coverage=[];calendar_coverage_verified=False
    for r in rows:
        if r['kind']=='CAPABILITIES':facts={f['name']:f for f in r['payload']['facts']}
        if r['kind']=='CALENDAR':
            bounds=r['payload'].get('coverage')
            if bounds:
                z=ZoneInfo(bounds['time_zone']);coverage.append((point(bounds['start'],z,'%Y%m%d-%H:%M:%S'),point(bounds['end'],z,'%Y%m%d-%H:%M:%S')))
            # Each published contract day includes its CLOSED/open declaration;
            # this covers today's end even when historical SCHEDULE ends at now.
            contract=r['payload'].get('contract')
            if contract:
                z=ZoneInfo(contract['time_zone'])
                for entry in contract['liquid_hours'].split(';'):
                    if not entry:continue
                    day=entry.split(':',1)[0];a=point(day+':0000',z,'%Y%m%d:%H%M')
                    next_day=(datetime.strptime(day,'%Y%m%d')+timedelta(days=1)).strftime('%Y%m%d')
                    coverage.append((a,point(next_day+':0000',z,'%Y%m%d:%H%M')))
    for r in rows:
        if r['kind']=='DOCUMENTED_EVIDENCE':
            for f in r['payload']['facts']:
                if f['name']!='corporate_action_coverage' and (facts.get(f['name'],{}).get('status')!='VERIFIED' or at(f['observed_at'])>=at(facts[f['name']]['observed_at'])):facts[f['name']]=f
    corporate=[f for r in rows if r['kind']=='DOCUMENTED_EVIDENCE' for f in r['payload']['facts'] if f['name']=='corporate_action_coverage']
    if anchor and selected:
        cursor=anchor
        for a,b in sorted(coverage):
            if a<=cursor<=b:cursor=max(cursor,b)
        calendar_coverage_verified=cursor>=at(selected[-1]['end'])
    complete=sum(s['finished'] for s in reports)
    unknown=[k for k in REQUIRED if facts.get(k,{}).get('status')!='VERIFIED' or facts.get(k,{}).get('value') is None]
    settled=facts.get('SettledCash_USD',{})
    if 'SettledCash_USD' not in unknown:
        try:
            from .tws import finite
            if finite(settled['value'])<100 or not 0<=(now-at(settled['observed_at'])).total_seconds()<=86400:unknown.append('SettledCash_USD')
        except (ValueError,ArithmeticError,KeyError):unknown.append('SettledCash_USD')
    quality=conflict or not calendar_coverage_verified or any(s['finished'] and (s['live_coverage']<c['minimum_live_coverage'] or s['maximum_gap_seconds']>c['maximum_gap_seconds'] or s['anomalies']) for s in reports)
    reasons=[]
    if complete<20:decision='INSUFFICIENT_EVIDENCE';reasons.append('TWENTY_AUTHENTIC_COMPLETED_SESSIONS_REQUIRED')
    elif quality:decision='DATA_QUALITY_BLOCKED';reasons.append('LIVE_COVERAGE_GAPS_ANOMALIES_OR_CALENDAR_CONFLICT')
    elif unknown:decision='EXECUTION_CONSTRAINT_BLOCKED';reasons.append('REQUIRED_ACCOUNT_EVIDENCE_UNKNOWN')
    elif not corporate or corporate[-1]['value']!='COMPLETE' or at(corporate[-1]['coverage_start'])>at(selected[0]['start']) or at(corporate[-1]['coverage_end'])<at(selected[-1]['end']):
        decision='DATA_QUALITY_BLOCKED';reasons.append('CORPORATE_ACTION_COVERAGE_UNKNOWN')
    else:decision='EVIDENCE_READY_FOR_RESEARCH'
    if decision=='EVIDENCE_READY_FOR_RESEARCH':
        minimum=facts['effective_minimum_quantity']['value']
        asks=[float(r['payload']['ask']) for r in rows if r['kind']=='QUOTE' and r['payload']['status']=='LIVE']
        fees=facts['effective_per_order_fees']['value']['conservative_roundtrip_cost_usd_at_minimum']
        if not asks or minimum*max(asks)+fees>100:
            decision='EXECUTION_CONSTRAINT_BLOCKED';reasons.append('MINIMUM_SIZE_AND_COST_EXCEED_VIRTUAL_100_USD')
    # The current read-only API cannot verify all account conditions or corporate
    # action coverage. READY is deliberately unreachable by favorable defaults.
    material=complete==20 and decision=='EVIDENCE_READY_FOR_RESEARCH'
    live=[r['payload'] for r in rows if r['kind']=='QUOTE' and r['payload']['status']=='LIVE' and not r['payload']['flags']]
    research_summary=dict(symbol='F',completed_sessions=complete,live_samples=len(live),
        bid_ask_exchange_timestamp='UNKNOWN_RECEIPT_ONLY',slippage='UNKNOWN_NOT_MEASURED',
        median_spread_usd=median(float(q['spread']) for q in live) if live else None,
        maximum_ask_usd=max(float(q['ask']) for q in live) if live else None,
        volume_observations=sum('volume' in q.get('sizes',{}) for q in live),size_units='UNKNOWN',
        facts={k:dict(status=facts[k]['status'],value=facts[k]['value'],source=facts[k].get('source','IBKR_TWS'))
               for k in ('effective_fee_plan','effective_minimum_quantity','quantity_increment') if k in facts},
        conservative_roundtrip_cost_usd_at_minimum=facts.get('effective_per_order_fees',{}).get('value',{}).get('conservative_roundtrip_cost_usd_at_minimum')
            if type(facts.get('effective_per_order_fees',{}).get('value')) is dict else None,
        research_readiness_is_not_profitability_or_execution_approval=True)
    return dict(study_status='COMPLETED' if complete==20 else ('OBSERVING' if anchor else 'PREREGISTERED_NOT_STARTED'),
        decision=decision,reasons=reasons,completed_sessions=complete,sessions=reports,
        required_unknown=unknown,capability_facts=facts,material_new_evidence=material,
        consecutive_calendar_coverage_verified=calendar_coverage_verified,
        research_summary=research_summary,
        baseline_history_sha256=spec['baseline_history_sha256'],baseline_deferred_ids=spec['baseline_deferred_ids'],
        spec_sha256=digest(spec),chain_head=rows[-1]['hash'] if rows else '0'*64,
        observations=sum(r['kind']=='QUOTE' for r in rows),interruptions=sum(r['kind']=='DISCONNECTED' for r in rows),
        research_proposal=dict(problem='TEST_NET_COST_ECONOMICS_ON_PROSPECTIVE_DATA',max_cost_usd='1.00',
                               execution='REQUIRES_EXPLICIT_AUTHORIZATION') if material else None,
        orders_sent=0,openai_requests=0,execution_authorized=False)


def status(root,study,now=None):
    spec=load_spec(root,study);dest=folder(root,study);rows=[]
    if (dest/'journal.sqlite3').exists():
        store=Store(dest/'journal.sqlite3',spec,True)
        try:
            rows=store.rows()
            for row in rows:
                if row['kind']=='DOCUMENTED_EVIDENCE':validate_evidence(root,spec,row['payload'],now)
        finally:store.close()
    result=project(spec,rows,now or datetime.now(timezone.utc));result['study']=study
    result['stop_requested']=(dest/'stop.request').exists()
    if rows and rows[-1]['kind'] in ('STOPPED','SUSPENDED'):result['study_status']=rows[-1]['kind']
    return result


def connect(root,c):
    # Lazy import: research readiness and progress never decrypt binding/connect.
    from .broker import PaperOptions
    from .ibkr_session import AccountBinding,SessionConfiguration
    from .paper_lab import unseal
    from .paper_evidence_wire import observer_wire
    binding=AccountBinding(unseal(Path(root)/'.local/ibkr-account-binding.dpapi'))
    endpoint=SessionConfiguration.load(root)
    wire=observer_wire(PaperOptions(binding.account,host=endpoint.host,port=endpoint.port,
        verified_tws_port=endpoint.port,paper_mode_attested=True,configured_endpoint=True,
        client_id=c['client_id'],timeout=c['request_timeout_seconds'],read_only=True))
    try:binding.select(wire.connect())
    except BaseException:wire.disconnect();raise
    return wire


def validate_evidence(root,spec,manifest,now=None):
    if set(manifest)!={'environment','account_binding_sha256','facts'} or manifest['environment']!='PAPER_TRADING' or manifest['account_binding_sha256']!=spec['account_binding_sha256'] or manifest['account_binding_sha256']=='ABSENT':
        raise ValueError('OBSERVER_EVIDENCE_SCOPE_REQUIRED')
    if type(manifest['facts']) is not list or not 1<=len(manifest['facts'])<=9:raise ValueError('OBSERVER_EVIDENCE_FACTS_REQUIRED')
    names=[]
    for f in manifest['facts']:
        keys={'name','status','value','source','source_path','source_sha256','observed_at'}|({'coverage_start','coverage_end'} if f.get('name')=='corporate_action_coverage' else set())
        if keys!=set(f) or f['name'] not in REQUIRED+('corporate_action_coverage',) or f['status']!='VERIFIED' or f['source']!='OPERATOR_VERIFIED_PAPER_DOCUMENT':
            raise ValueError('OBSERVER_DOCUMENTED_FACT_REQUIRED')
        relative=f['source_path']
        if type(relative) is not str or not relative.startswith(FOLDER+'/evidence/') or '..' in relative or '\\' in relative:raise ValueError('OBSERVER_DOCUMENT_PATH_REQUIRED')
        p=safe_path(root,relative)
        if hashlib.sha256(p.read_bytes()).hexdigest()!=f['source_sha256']:raise ValueError('OBSERVER_DOCUMENT_TAMPERED')
        if not at(spec['registered_at'])<=at(f['observed_at'])<=(now or datetime.now(timezone.utc)):raise ValueError('OBSERVER_NEW_DOCUMENT_REQUIRED')
        value=f['value'];names.append(f['name'])
        if f['name']=='stock_etf_permissions' and value is not True:raise ValueError('OBSERVER_PERMISSION_NOT_CONFIRMED')
        if f['name']=='SettledCash_USD' and (type(value) not in (int,float) or not 100<=value<1e20):raise ValueError('OBSERVER_SETTLED_FUNDS_INSUFFICIENT')
        if f['name']=='effective_fee_plan' and value not in ('TIERED','FIXED'):raise ValueError('OBSERVER_FEE_PLAN_REQUIRED')
        if f['name'] in ('effective_per_order_fees','effective_intraday_restrictions','contract_specific_margin') and (type(value) is not dict or not value or value.get('reviewed_for_fully_funded_100_usd_long') is not True):raise ValueError('OBSERVER_RESTRICTIONS_REVIEW_REQUIRED')
        if f['name'] in ('effective_intraday_restrictions','contract_specific_margin') and value.get('compatible_with_study') is not True:raise ValueError('OBSERVER_EXECUTION_RESTRICTED')
        if f['name']=='effective_per_order_fees':
            fee=value.get('conservative_roundtrip_cost_usd_at_minimum')
            if type(fee) not in (int,float) or not 0<fee<=100:raise ValueError('OBSERVER_FULL_COST_EVIDENCE_REQUIRED')
        if f['name'] in ('effective_minimum_quantity','quantity_increment') and (type(value) is not int or not 1<=value<=100000):raise ValueError('OBSERVER_WHOLE_QUANTITY_REQUIRED')
        if type(value) is dict:
            from .ai_strategy_researcher.contracts import text
            if len(encoded(value))>2000:raise ValueError('OBSERVER_FACT_SIZE_REQUIRED')
            text(encoded(value).decode(),2000)
        if f['name']=='corporate_action_coverage':
            if value!='COMPLETE' or at(f['coverage_start'])>=at(f['coverage_end']):raise ValueError('OBSERVER_CORPORATE_COVERAGE_REQUIRED')
    if len(set(names))!=len(names):raise ValueError('OBSERVER_DUPLICATE_FACT')
    return manifest


def attach_evidence(root,study,manifest_path):
    spec=load_spec(root,study);manifest=validate_evidence(root,spec,strict_json(Path(manifest_path).read_bytes()))
    dest=folder(root,study)
    with locked(dest):
        store=Store(dest/'journal.sqlite3',spec)
        try:store.append('DOCUMENTED_EVIDENCE',manifest)
        finally:store.close()
    return status(root,study)


def run(root,study,connector=None,clock=None,sleeper=None,max_cycles=None):
    spec=load_spec(root,study);dest=folder(root,study);c=spec['config']
    now=clock or (lambda:datetime.now(timezone.utc));pause=sleeper or time.sleep;wire=None
    with locked(dest):
        store=Store(dest/'journal.sqlite3',spec)
        try:
            (dest/'stop.request').unlink(missing_ok=True)
            if not any(r['kind']=='STARTED' for r in store.rows()):store.append('STARTED',{},now().isoformat())
            store.append('RESUMED',{},now().isoformat());cycles=0;last_calendar=None;last_cap=None;contract=None
            while not (dest/'stop.request').exists():
                stamp=now();rows=store.rows();summary=project(spec,rows,stamp)
                if summary['completed_sessions']==20:store.append('COMPLETED',summary,stamp.isoformat());break
                try:
                    if not wire or not wire.connected:
                        binding=safe_path(root,'.local/ibkr-account-binding.dpapi')
                        current=hashlib.sha256(binding.read_bytes()).hexdigest() if binding.exists() else 'ABSENT'
                        if connector is None and (current=='ABSENT' or current!=spec['account_binding_sha256']):raise PermissionError('OBSERVER_ACCOUNT_BINDING_CHANGED')
                        wire=(connector or connect)(root,c);store.append('CONNECTED',dict(identity_verified=True,source='EXACT_PROTECTED_PAPER_BINDING'),stamp.isoformat())
                        last_calendar=last_cap=None
                    if last_calendar is None or (stamp-last_calendar).total_seconds()>=c['calendar_refresh_seconds']:
                        contract=wire.contract_details('F');schedule=wire.recent_schedule();stamp=now()
                        previous_contracts=[r['payload']['contract'] for r in store.rows() if r['kind']=='CALENDAR']
                        if previous_contracts and any(contract[k]!=previous_contracts[-1][k] for k in ('con_id','symbol','currency','security_type')):
                            raise PermissionError('OBSERVER_CONTRACT_IDENTITY_CHANGED')
                        sessions=sessions_from(contract,schedule['sessions'],stamp)
                        store.append('CALENDAR',dict(sessions=sessions,contract=contract,schedule=schedule,
                            coverage=schedule['coverage'],source='IBKR_HISTORICAL_SCHEDULE_AND_LIQUID_HOURS'),stamp.isoformat());last_calendar=stamp
                    if last_cap is None or (stamp-last_cap).total_seconds()>=c['capabilities_refresh_seconds']:
                        from .paper_account_capabilities import account_facts
                        observation=dict(identity_verified=True,environment='PAPER_TRADING',queries={},completed_at=stamp.isoformat())
                        for mode in ('summary','ledger','updates','multi'):
                            if (dest/'stop.request').exists():break
                            try:observation['queries'][mode]=dict(complete=True,rows=wire.values(mode),callback=mode)
                            except Exception as exc:observation['queries'][mode]=dict(complete=False,error=type(exc).__name__)
                            if not wire.connected:raise ConnectionError('OBSERVER_DISCONNECTED')
                        store.append('CAPABILITIES',dict(facts=account_facts(observation),queries=observation['queries'],
                            minimum_size_declared=contract.get('minimum_size'),size_increment_declared=contract.get('size_increment'),
                            effective_minimum='UNKNOWN',fractional_permission='UNKNOWN',margin='UNKNOWN'),now().isoformat());last_cap=stamp
                    active=[s for s in project(spec,store.rows(),now())['sessions'] if at(s['start'])<=now()<at(s['end'])]
                    if active and not (dest/'stop.request').exists():
                        q=classify(wire.sample(),now(),c)
                        previous=[r['payload'] for r in store.rows() if r['kind']=='QUOTE']
                        if q['midpoint'] and previous and previous[-1].get('midpoint') and previous[-1]['status']==q['status']:
                            if abs(float(q['midpoint'])/float(previous[-1]['midpoint'])-1)>c['maximum_midpoint_jump_ratio']:q['flags'].append('MIDPOINT_DISCONTINUITY_NOT_CAUSALLY_EXPLAINED')
                        store.append('QUOTE',q,now().isoformat())
                    if wire.events:
                        store.append('IBKR_CODES',dict(events=wire.events[:]),now().isoformat());wire.events.clear()
                except Exception as exc:
                    # No arbitrary exception text/account/credentials is recorded.
                    store.append('DISCONNECTED',dict(error_type=type(exc).__name__,quote_status='MISSING'),now().isoformat())
                    if wire and wire.events:store.append('IBKR_CODES',dict(events=wire.events[:]),now().isoformat())
                    if wire:wire.disconnect();wire=None
                    if isinstance(exc,PermissionError):store.append('SUSPENDED',dict(reason='IDENTITY_OR_PERMISSION_UNCERTAIN'),now().isoformat());break
                cycles+=1
                if max_cycles is not None and cycles>=max_cycles:break
                for _ in range(c['poll_seconds']):
                    if (dest/'stop.request').exists():break
                    pause(1)
            if (dest/'stop.request').exists():store.append('STOPPED',dict(reason='OPERATOR_STOP'),now().isoformat())
        except KeyboardInterrupt:store.append('STOPPED',dict(reason='KEYBOARD_INTERRUPT'),now().isoformat())
        finally:
            if wire:wire.disconnect()
            store.close()
    return status(root,study,now())


def research_preflight(root):
    """No billing/credentials/network. Never grants authorization or starts research."""
    from .ai_strategy_researcher.data import load_dataset
    from .ai_strategy_researcher.memory import load_readonly
    package,_=load_dataset(root);memory=load_readonly(Path(root).resolve(),package)
    deferred={d['evidence_id'] for d in memory.get('deferred_decisions',[])}
    candidates=[]
    base=safe_path(root,FOLDER)
    if base.exists():
        for child in base.iterdir():
            if not child.is_dir():continue
            result=status(root,child.name)
            if result['decision']=='EVIDENCE_READY_FOR_RESEARCH' and deferred<=set(result['baseline_deferred_ids']) and result['baseline_history_sha256']==memory['history_sha256']:candidates.append(result)
    return dict(decision='EVIDENCE_READY_FOR_RESEARCH' if candidates else 'INSUFFICIENT_EVIDENCE',
                deferred_decisions=len(deferred),ready_studies=candidates,openai_requests=0)


def main():
    p=argparse.ArgumentParser(description='Paper-only evidence observer. No orders and no OpenAI calls.')
    p.add_argument('action',choices=('prepare','run','status','stop','evaluate','preflight','attach-evidence'))
    p.add_argument('--root',default='.');p.add_argument('--study',default='ford-evidence-001')
    p.add_argument('--manifest')
    args=p.parse_args();root=Path(args.root).resolve()
    if args.action=='prepare':r=prepare(root,args.study)
    elif args.action=='run':r=run(root,args.study)
    elif args.action in ('status','evaluate'):r=status(root,args.study)
    elif args.action=='preflight':r=research_preflight(root)
    elif args.action=='attach-evidence':r=attach_evidence(root,args.study,args.manifest)
    else:
        load_spec(root,args.study);path=folder(root,args.study)/'stop.request'
        if not path.exists():
            with path.open('x',encoding='ascii') as f:f.write('OPERATOR_STOP')
        r=dict(study=args.study,stop_requested=True,orders_sent=0,openai_requests=0)
    print(encoded(r).decode())


if __name__=='__main__':
    try:main()
    except Exception as exc:
        code=str(exc) if re.fullmatch('[A-Z][A-Z0-9_]{1,100}',str(exc)) else 'OBSERVER_BLOCKED'
        print(json.dumps(dict(status='BLOCKED',reason=code,error_type=type(exc).__name__,orders_sent=0,openai_requests=0)))
        raise SystemExit(2)
