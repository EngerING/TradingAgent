"""Read-only sidecar for incumbent Shadow observations; never connects to IBKR.

    Backtest catalogue -> preregistered candidate arms -> independent forward
evidence. Does not select/replace the incumbent strategy or call OpenAI.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import sqlite3
import time
from uuid import uuid4
from .eurusd_paper_research import encoded, sha, instant, number
from .eurusd_shadow_research import postgres
from .eurusd_cost_aware_search import (FOLDER, SCOPE, ENGINE_FILES, ResearchSimulator, profile,
                                      signals, calibrated, path_exit, configuration)


def identifier(value, kind):
    if not re.fullmatch(kind+r'-[a-f0-9]{32}', value or ''): raise ValueError('INVALID_RESEARCH_IDENTIFIER')
    return value


def read_source(root, study, after, previous, mirror=postgres):
    identifier(study,'eurusd-shadow')
    path=Path(root)/'artifacts/research/eurusd-shadow'/study/'journal.sqlite3'
    if not path.is_file(): raise ValueError('SHADOW_SOURCE_UNAVAILABLE')
    db=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)
    try:
        db.execute('BEGIN')
        latest=db.execute('SELECT revision,hash FROM events ORDER BY revision DESC LIMIT 1').fetchone()
        rows=db.execute('SELECT revision,payload,previous,hash FROM events WHERE revision>? ORDER BY revision LIMIT 100',(after,)).fetchall()
        revision=after;head=previous;events=[]
        for r,p,prev,h in rows:
            body=json.loads(p)
            if r!=revision+1 or prev!=head or sha([r,body,prev])!=h: raise ValueError('SOURCE_HASH_CHAIN_CONFLICT')
            if body['study_id']!=study: raise ValueError('SOURCE_STUDY_CONFLICT')
            revision,head=r,h;events.append((r,h,body))
        checkpoint=db.execute('SELECT hash FROM events WHERE revision=?',(after,)).fetchone() if after else None
        if after and (not checkpoint or checkpoint[0]!=previous): raise ValueError('SOURCE_CHECKPOINT_CONFLICT')
        remote=mirror(root,study,[])
        # A source writer may append after our SQLite snapshot. Do not accept a
        # different head, nor mark a racing snapshot as irreparable corruption.
        if remote['revision']>(latest[0] if latest else 0): return []
        remote_row=db.execute('SELECT hash FROM events WHERE revision=?',(remote['revision'],)).fetchone() if remote['revision'] else None
        if remote['revision']<after or remote['hash']!=(remote_row[0] if remote_row else ''): raise ValueError('SOURCE_POSTGRES_NOT_RECONCILED')
        if latest and remote['revision']<latest[0]:return []
        return events
    finally:db.close()


def archived_analysis(root, details, at):
    from .research_analysis import analyze
    source=details.get('history_source') or {};relative=source.get('path','')
    base=(Path(root)/'artifacts/research/eurusd-shadow/market-data').resolve()
    path=(Path(root)/relative).resolve()
    if path.parent!=base or not re.fullmatch(r'[a-f0-9]{64}\.json',path.name): raise ValueError('AUTHENTIC_ARCHIVE_PATH_REQUIRED')
    raw=json.loads(path.read_bytes())
    if sha(raw)!=source.get('sha256') or path.stem!=sha(raw) or raw.get('source')!='AUTHENTIC_IBKR_PAPER_READ_ONLY': raise ValueError('AUTHENTIC_ARCHIVE_HASH_CONFLICT')
    return analyze(dict(instrument='EUR/USD',source='IBKR_TWS',what_to_show='MIDPOINT',as_of=at,
        indicators=json.loads((Path(root)/'config/research-indicators.json').read_bytes()),calendar=raw['calendar'],originals=raw['originals']))


class Campaign:
    def __init__(self,root,campaign):
        self.root=Path(root).resolve();identifier(campaign,'forward');self.campaign=campaign
        self.folder=self.root/FOLDER/campaign
        if not self.folder.is_dir(): raise ValueError('PREREGISTERED_CAMPAIGN_REQUIRED')
        self.db=sqlite3.connect(self.folder/'journal.sqlite3',isolation_level=None,timeout=15)
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('CREATE TABLE IF NOT EXISTS events(revision INTEGER PRIMARY KEY,payload TEXT NOT NULL,previous TEXT NOT NULL,hash TEXT NOT NULL)')
        for action in ('UPDATE','DELETE'):
            self.db.execute(f"CREATE TRIGGER IF NOT EXISTS immutable_{action} BEFORE {action} ON events BEGIN SELECT RAISE(ABORT,'IMMUTABLE_COST_AWARE_FORWARD'); END")
        self.revision=0;self.head='';self.state=None
        try:
            for r,p,prev,h in self.db.execute('SELECT * FROM events ORDER BY revision'):
                body=json.loads(p)
                if r!=self.revision+1 or prev!=self.head or sha([r,body,prev])!=h: raise ValueError('FORWARD_JOURNAL_INTEGRITY')
                self.revision,self.head,self.state=r,h,body['state']
        except Exception:self.db.close();raise

    def append(self,event,details):
        body=dict(event=event,scope=SCOPE,classification='SIMULATED_SHADOW_CANDIDATE_ARM',broker_orders=0,
            openai_calls=0,execution_authorized=False,live_enabled=False,state=self.state,details=details)
        r=self.revision+1;digest=sha([r,body,self.head])
        self.db.execute('INSERT INTO events VALUES(?,?,?,?)',(r,encoded(body).decode(),self.head,digest))
        self.revision,self.head=r,digest


def prepare(root,search,source_study):
    root=Path(root).resolve();identifier(search,'search');identifier(source_study,'eurusd-shadow')
    folder=root/FOLDER/search;protocol=json.loads((folder/'protocol.json').read_bytes());report=json.loads((folder/'report.json').read_bytes())
    if protocol['scope']!=SCOPE or sha(protocol)!=report['protocol_hash'] or protocol['openai_budget_usd']!='0' or protocol['broker_orders']!=0: raise ValueError('SEARCH_PROTOCOL_CONFLICT')
    current={p:sha((root/p).read_text(encoding='utf-8')) for p in ENGINE_FILES}
    if protocol['engine_hashes']!=current: raise ValueError('SEARCH_ENGINE_CHANGED_REPEAT_OFFLINE_RESEARCH')
    # Confirm source existence and mirrored integrity without creating it.
    read_source(root,source_study,0,'')
    labels=json.loads((folder/'labels.json').read_bytes())
    campaign='forward-'+uuid4().hex;destination=root/FOLDER/campaign;destination.mkdir(exist_ok=False)
    c=Campaign(root,campaign)
    try:
        (destination/'labels.json').write_bytes(encoded(labels))
        c.state=dict(protocol=protocol,search=search,source_study=source_study,labels_sha=sha(labels),
            started_at=datetime.now(timezone.utc).isoformat(),source_revision=0,source_hash='',
            portfolio_heads={},portfolio_metrics={},seen=[],pending_paths={},forward_labels=[],
            status='PREPARED_NOT_RUNNING',openai_budget_usd='0')
        for candidate in protocol['candidates']:
            for name in protocol['profiles']:
                sim=ResearchSimulator(destination/(candidate['id']+'-'+name+'.sqlite3'),profile(root,name),protocol['costs'],candidate)
                c.state['portfolio_heads'][candidate['id']+'-'+name]=sim.head;sim.db.close()
        c.append('IMMUTABLE_FORWARD_PREREGISTRATION',dict(automatic_adoption=False,candidate_arms=len(protocol['candidates']),capital_per_profile_per_arm='100',combined_arms_not_one_portfolio=True))
        return dict(campaign=campaign,status=c.state['status'],source_study=source_study,broker_orders=0,openai_calls=0)
    finally:c.db.close()


def process_event(c,revision,digest,event,labels,analysis_loader=archived_analysis,clock=lambda:datetime.now(timezone.utc)):
    at=event['state'].get('last_observation')
    if event['event']!='COMMON_MARKET_OPPORTUNITY_EVALUATED' or not at or instant(at)<instant(c.state['started_at']):
        c.state.update(source_revision=revision,source_hash=digest)
        c.append('SOURCE_EVENT_CHECKPOINT_NO_BACKFILLED_ENTRIES',dict(source_event=event['event'],revision=revision));return
    details=event['details'];quote=details['quote'];analysis=analysis_loader(c.root,details,at)
    bars=[b for b in analysis['normalized']['15'] if instant(b['opened_at'])+timedelta(minutes=15)<=instant(at)]
    decisions=[];state=c.state
    for candidate in state['protocol']['candidates']:
        key=candidate['id']
        for path_id,pending in list(state['pending_paths'].items()):
            if pending['strategy']!=key:continue
            for b in bars:
                if instant(b['opened_at'])<instant(pending['entry_at']) or pending.get('last_bar') and instant(b['opened_at'])<=instant(pending['last_bar']):continue
                d=path_exit(pending,b,candidate);pending['last_bar']=b['opened_at']
                if d:
                    state['forward_labels'].append(dict(strategy=key,side=pending['side'],regime=pending['regime'],signal_at=pending['entry_at'],resolved_at=d[2],outcome='TP' if d[1]=='TAKE_PROFIT' else 'SL' if d[1].startswith('STOP') else 'COMPETING_EXIT',source='FORWARD_COUNTERFACTUAL_NOT_PORTFOLIO_TRADE',opportunity_id=pending['id'],calibration_eligible=pending['calibration_eligible']))
                    del state['pending_paths'][path_id];break
        rows=signals(analysis,candidate)
        s=deepcopy(rows[-1]) if rows else None
        if s and 'NO_AUTHENTIC_NEXT_OPEN' in s['reasons']:
            s['reasons'].remove('NO_AUTHENTIC_NEXT_OPEN')
            if quote.get('bid') and quote.get('ask'):s['entry_midpoint']=str((number(quote['bid'])+number(quote['ask']))/2)
        timely=bool(s and quote.get('at') and 0<=(instant(quote['at'])-instant(s['signal_at'])).total_seconds()<=5 and instant(quote['at'])<=instant(at) and 0<=(instant(at)-instant(quote['at'])).total_seconds()<=5)
        if s and not timely:s['reasons'].append('LATE_OR_STALE_NEXT_OPEN')
        if s and not s['entry_midpoint']:s['reasons'].append('QUOTE_MISSING')
        duplicate=bool(s and s['opportunity_id'] in state['seen'])
        if s:
            s['calibration']=calibrated(labels[key]+[x for x in state['forward_labels'] if x['strategy']==key],configuration(c.root)['probability'],state['protocol'].get('folds',[]),s,s['signal_at']) if not s['reasons'] else dict(status='INSUFFICIENT_EVIDENCE',probability=None)
            if not s['reasons'] and timely and quote.get('type')=='LIVE' and quote.get('market_status')=='OPEN' and quote.get('available_for_execution') is True and not duplicate:
                if len(state['pending_paths'])>=1024:raise ValueError('COUNTERFACTUAL_CAPTURE_LIMIT_REQUIRES_REVIEW')
                mid=number(s['entry_midpoint']);direction=1 if s['side']=='BUY' else -1
                eligible=not any(p['strategy']==key and p['calibration_eligible'] for p in state['pending_paths'].values())
                state['pending_paths'][s['opportunity_id']]=dict(id=s['opportunity_id'],strategy=key,side=s['side'],regime=s['regime'],entry_at=s['entry_at'],stop=str(mid-direction*number(s['stop_distance'])),target=str(mid+direction*number(s['take_profit_distance'])),calibration_eligible=eligible)
        per_profile={}
        for name in state['protocol']['profiles']:
            arm=key+'-'+name;sim=ResearchSimulator(c.folder/(arm+'.sqlite3'),profile(c.root,name),state['protocol']['costs'],candidate)
            try:
                if sim.head!=state['portfolio_heads'][arm]:raise ValueError('FORWARD_PORTFOLIO_RECONCILIATION_REQUIRED')
                for b in bars:sim.advance(b)
                decision=dict(admitted=False,reason='NO_VALID_SIGNAL' if not s else 'OPPORTUNITY_ALREADY_EVALUATED')
                if s and not duplicate:
                    if not 0<=(clock()-instant(s['entry_at'])).total_seconds()<=5:
                        decision=dict(admitted=False,reason='SIDECAR_LATE_NO_BACKFILLED_ENTRY')
                    else:decision=sim.enter(s,forward=True,quote=quote)
                per_profile[name]=decision;state['portfolio_heads'][arm]=sim.head;state['portfolio_metrics'][arm]=sim.metrics()
            finally:sim.db.close()
        if s and not duplicate:state['seen'].append(s['opportunity_id'])
        decisions.append(dict(candidate=key,signal=s,profiles=per_profile))
    state.update(source_revision=revision,source_hash=digest,status='COST_AWARE_SHADOW_RUNNING')
    c.append('COMMON_QUOTES_FEATURES_SIGNALS_REJECTIONS_AND_OUTCOMES',dict(source_revision=revision,source_hash=digest,quote=quote,history_source=details.get('history_source'),source_features=details.get('features'),decisions=decisions,model_state='NOT_RUNNING_BUDGET_ZERO'))


def run(root,campaign,once=False):
    from .stock_paper_forward_runner import run_lock
    c=Campaign(root,campaign)
    try:
        if c.state is None:raise ValueError('PREREGISTRATION_REQUIRED')
        if c.state['protocol']['engine_hashes']!={p:sha((c.root/p).read_text(encoding='utf-8')) for p in ENGINE_FILES}:raise ValueError('IMMUTABLE_FORWARD_ENGINE_CHANGED')
        if c.state['status'].startswith('SUSPENDED'):raise ValueError('MANUAL_RECONCILIATION_REQUIRED_NO_BLIND_RETRY')
        labels=json.loads((c.folder/'labels.json').read_bytes())
        if sha(labels)!=c.state['labels_sha']:raise ValueError('FORWARD_CALIBRATION_LABELS_CHANGED')
        with run_lock(c.folder/'runner.lock'):
            while not (c.folder/'stop.request').exists():
                events=read_source(c.root,c.state['source_study'],c.state['source_revision'],c.state['source_hash'])
                for revision,digest,event in events:process_event(c,revision,digest,event,labels)
                print(json.dumps(dict(campaign=campaign,status=c.state['status'],source_revision=c.state['source_revision'],events=len(events),broker_orders=0,openai_calls=0)),flush=True)
                if once:break
                for _ in range(5):
                    if (c.folder/'stop.request').exists():break
                    time.sleep(1)
            if (c.folder/'stop.request').exists():
                c.state['status']='STOPPED_CANDIDATE_SIDECAR_ONLY_PENDING_INVENTORY_PRESERVED'
                c.append('OPERATOR_STOP_INCUMBENT_UNTOUCHED',dict(pending_inventory_preserved=True))
    except Exception as error:
        if c.state:
            c.state['status']='SUSPENDED_RECONCILIATION_REQUIRED'
            c.append('FAIL_CLOSED_NO_BROKER_OR_MODEL_RETRY',dict(reason=str(error) if re.fullmatch('[A-Z0-9_]{1,100}',str(error)) else type(error).__name__))
        raise
    finally:c.db.close()


def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['Prepare','Run','Once','Status','Stop']);p.add_argument('--root',default='.');p.add_argument('--search');p.add_argument('--study');p.add_argument('--campaign');args=p.parse_args()
    if args.action=='Prepare':result=prepare(args.root,args.search,args.study)
    elif args.action in ('Run','Once'):run(args.root,args.campaign,args.action=='Once');return
    else:
        c=Campaign(args.root,args.campaign)
        try:
            if args.action=='Stop':(c.folder/'stop.request').write_text('OPERATOR_STOP_CANDIDATE_SIDECAR_ONLY\n');result=dict(campaign=args.campaign,stop_requested=True,incumbent_runner_untouched=True)
            else:result=dict(campaign=args.campaign,status=c.state['status'],source_revision=c.state['source_revision'],metrics=c.state['portfolio_metrics'],broker_orders=0,openai_calls=0)
        finally:c.db.close()
    print(json.dumps(result,allow_nan=False))

if __name__=='__main__':main()
