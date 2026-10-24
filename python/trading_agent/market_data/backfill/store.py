"""Own Archive replay and immutable post-COMMIT pages; no protected journal changes."""
import base64
from dataclasses import dataclass
from datetime import timedelta, datetime, timezone
import hashlib
import os
from pathlib import Path
import time

from trading_agent.core_v3.contracts import require, content_hash, canonical_bytes, strict_json, utc, ContractError
from trading_agent.core_v3.historical_ingestion.files import safe_path, read_local
from trading_agent.core_v3.market_observation.contracts import Kind
from trading_agent.core_v3.market_observation.ibkr_protocol import fields
from ..archive import Archive
from ..calendar import TradingCalendar
from ..consumer import fingerprint
from .contracts import BackfillSpec, Window, HistoricalBar, Page, PageRef, Dataset, PageCursor
from .wire import plan, request, bars


def _sha(blob): return hashlib.sha256(blob).hexdigest()


def _window(payload, con_id):
    f=fields(payload)
    try:
        minutes={'15 mins':15,'1 hour':60,'4 hours':240}[f[16]]
        end=datetime.strptime(f[15],'%Y%m%d-%H:%M:%S').replace(tzinfo=timezone.utc)
        days=int(f[17].removesuffix(' D'))
        earliest=end-timedelta(days=days)
        start=earliest.replace(hour=0,minute=0,second=0,microsecond=0)
        if start<earliest: start+=timedelta(days=1)
        w=Window(int(f[1]),minutes,start,end)
        require(request(w,con_id)[4:]==payload,'M032_PLAN_BYTES')
        return w
    except (ValueError,IndexError,KeyError): raise ContractError('M032_PLAN_BYTES') from None


def expected(calendar, window):
    """Only declared sessions establish coverage. No inferred Forex template."""
    day=window.start.astimezone(calendar.zone).date()
    last=(window.end-timedelta(microseconds=1)).astimezone(calendar.zone).date()
    while day<=last:
        if day not in calendar.days: return None
        day+=timedelta(days=1)
    slots=set()
    for a,b in calendar.sessions:
        at=a
        while at<b:
            if window.start<=at<window.end and min(at+timedelta(minutes=window.minutes),b)<=window.end:
                slots.add(at)
            at+=timedelta(minutes=window.minutes)
    return slots


def cutoff_has_incomplete_bar(calendar, spec):
    """An intraday cutoff cannot certify a still-open higher-timeframe bar."""
    if calendar is None: return False
    session=calendar.interval(spec.end-timedelta(microseconds=1))
    if session is None or session[1]<=spec.end: return False
    elapsed=(spec.end-session[0]).total_seconds()
    return any(elapsed%(minutes*60)!=0 for minutes in spec.timeframes)


class HistoricalStore:
    def __init__(self, directory, spec, session_id, origin, environment, *, create=False):
        require(type(spec) is BackfillSpec,'M032_SPEC')
        plan(spec)
        self.root=Path(safe_path(directory));self.spec=spec
        self.origin,self.environment,self.session_id=origin,environment,session_id
        self.archive=None
        self.identity=content_hash({'schema':'trading.m03a2.store','collector':spec.collector.to_dict(),
            'session':session_id,'origin':origin.value,'environment':environment.value})
        marker=canonical_bytes({'schema':'trading.m03a2.store','schema_version':1,'sha256':self.identity})
        try:
            if create:
                require(not tuple(self.root.iterdir()),'M032_NOT_EMPTY')
                with (self.root/'identity.json').open('xb') as f: f.write(marker); f.flush();os.fsync(f.fileno())
                for name in ('capture','pages','manifests'): (self.root/name).mkdir()
            require(read_local(self.root,'identity.json',max_bytes=4096)==marker,'M032_STORE_IDENTITY')
            self._check()
            self.archive=Archive(self.root/'capture',spec.collector,session_id,origin,environment,create=create)
            self.rebuild()
        except BaseException:
            self.close();raise

    def _check(self):
        safe_path(self.root)
        total=0
        for p in self.root.iterdir():
            safe_path(p)
            if p.is_dir():
                require(p.name in ('capture','pages','manifests'),'M032_DIRECTORY')
                for f in p.iterdir(): fingerprint(f);total+=f.stat().st_size
            else:
                require(p.name in ('identity.json','dataset.json','dataset.tmp'),'M032_FILE')
                fingerprint(p);total+=p.stat().st_size
        require(total<=self.spec.max_bytes,'M032_DISK_BUDGET')

    def rebuild(self, incremental=False):
        previous=len(self.rows) if incremental else 0
        if not incremental:
            self.samples={};self.conflicts=set();self.quality=set();self.plans={};self.proofs=[]
            self.contract=None;self.calendar=None;self.at=None;self.last_planned=None;self.attempts={}
            self.used_grants={};self.contexts={}
        self.rows=self.archive.history()
        for row in self.rows[previous:]:
            v=row.value;r=v.event
            self.at=max(self.at or r.received_at,r.received_at,v.as_of)
            if r.kind is Kind.CONNECTED:
                self.calendar=None
                # Four preflight requests plus cancellation reserve survive crashes.
                self.used_grants[r.capture_grant_sha256]=self.used_grants.get(r.capture_grant_sha256,0)+5
            if r.diagnostic.startswith('IBKR_ERROR_'):
                self.quality.add('PROVIDER_PERMISSION_DENIED' if r.diagnostic in (
                    'IBKR_ERROR_354','IBKR_ERROR_10167','IBKR_ERROR_10168','IBKR_ERROR_10186') else 'PROVIDER_UNAVAILABLE')
            if r.kind is Kind.GAP:
                self.plans={k:v for k,v in self.plans.items() if k[0]!=r.connection_id}
                if r.diagnostic.startswith('BACKFILL_'): self.quality.add(r.diagnostic)
                elif not r.diagnostic.startswith('IBKR_ERROR_'): self.quality.add('PREFLIGHT_OR_IDENTITY_REJECTED')
            if not v.accepted:
                if r.kind is Kind.NOTICE and r.diagnostic.startswith('BACKFILL_'): self.quality.add('HISTORY_EVENT_REJECTED')
                continue
            if r.kind is Kind.CONTRACT:
                if self.contract and (r.contract.con_id,r.contract.min_tick)!=(self.contract.con_id,self.contract.min_tick):
                    self.quality.add('CONTRACT_CHANGED'); continue
                self.contract=r.contract
                f=fields(base64.b64decode(r.raw_frame_b64));self.calendar=TradingCalendar(f[27],f[28],r.received_at)
            if r.diagnostic=='BACKFILL_AUTH_CONTEXT':
                context=strict_json(base64.b64decode(r.raw_frame_b64).decode())
                require(set(context)=={'spec','permit_sha256'},'M032_CONTEXT')
                context_spec=BackfillSpec.from_dict(context['spec'])
                from trading_agent.core_v3.economic_contracts import _hash
                _hash(context['permit_sha256'])
                require(context_spec.enabled and context_spec.collector==self.spec.collector,'M032_CONTEXT')
                self.contexts[r.connection_id]=(context_spec,r.capture_grant_sha256)
            if r.diagnostic=='BACKFILL_PLANNED':
                require(self.contract is not None,'M032_NO_CONTRACT')
                w=_window(base64.b64decode(r.raw_frame_b64),self.contract.con_id)
                require(r.connection_id in self.contexts,'M032_CONTEXT_MISSING')
                scope,grant=self.contexts[r.connection_id]
                require(scope.start<=w.start<w.end<=scope.end<=r.received_at and w.minutes in scope.timeframes and
                        r.capture_grant_sha256==grant,'M032_CONTEXT_BINDING')
                key=(w.minutes,w.start,w.end)
                self.attempts[key]=self.attempts.get(key,0)+1
                require(sum(self.attempts.values())<=30,'M032_ATTEMPT_BUDGET')
                self.used_grants[r.capture_grant_sha256]=self.used_grants.get(r.capture_grant_sha256,0)+1
                self.last_planned=r.received_at
                self.plans[(r.connection_id,r.wire_request_id)]=(w,row,self.calendar,self.contract)
            if r.diagnostic=='BACKFILL_BATCH':
                entry=self.plans.pop((r.connection_id,r.wire_request_id),None)
                if entry is None: self.quality.add('HISTORY_EVENT_REJECTED');continue
                w,planned,cal,contract=entry
                try:
                    require(r.capture_grant_sha256==planned.value.event.capture_grant_sha256 and
                            r.received_at>=planned.value.event.received_at,'M032_BATCH_BINDING')
                    values=bars(base64.b64decode(r.raw_frame_b64),w,r.received_at,self.at,cal,contract)
                    for b in values:
                        k=(b.minutes,b.opened_at)
                        existing=self.samples.get(k)
                        if existing:
                            if (b.open,b.high,b.low,b.close)!=(existing.bar.open,existing.bar.high,existing.bar.low,existing.bar.close):
                                self.conflicts.add(k); self.quality.add('HISTORY_CONFLICT')
                            else: self.quality.add('HISTORY_DUPLICATE')
                        else:
                            require(len(self.samples)<2048,'M032_ROW_BUDGET')
                            self.samples[k]=HistoricalBar(b,contract,r.origin,r.session_kind,r.received_at,w,r.connection_id,row.sha256)
                    self.proofs.append((w,cal))
                except ContractError:
                    self.quality.add('HISTORY_REJECTED')
        for k in self.conflicts: self.samples.pop(k,None)
        self.covered=set()
        for w,cal in self.proofs:
            if not cal: continue
            day=w.start
            while day<w.end:
                daily=Window(w.request_id,w.minutes,day,min(day+timedelta(days=1),w.end))
                slots=expected(cal,daily)
                if slots is not None and all((w.minutes,t) in self.samples for t in slots): self.covered.add((w.minutes,day))
                day+=timedelta(days=1)

    def pending(self):
        windows=[]
        for minutes in self.spec.timeframes:
            day=self.spec.start
            while day<self.spec.end:
                if (minutes,day) in self.covered: day+=timedelta(days=1);continue
                start=day;day+=timedelta(days=1)
                while day<self.spec.end and (minutes,day) not in self.covered and (day-start).days<{15:1,60:4,240:7}[minutes]: day+=timedelta(days=1)
                w=Window(3000+len(windows),minutes,start,min(day,self.spec.end))
                if self.attempts.get((minutes,start,day),0)<self.spec.max_attempts: windows.append(w)
        return tuple(windows)

    def append(self, event, *, as_of):
        row=self.archive.append(event,as_of=as_of)
        self.rebuild(incremental=True)
        if event.diagnostic=='BACKFILL_BATCH' or event.kind is Kind.GAP or not row.value.accepted:
            self.publish(as_of)
        return row

    def _immutable(self, directory, data):
        digest=_sha(data);p=self.root/directory/(digest+'.json')
        require(len(data)<=131072,'M032_DOCUMENT_BUDGET');self._check()
        if p.exists(): require(read_local(p.parent,p.name,max_bytes=131072)==data,'M032_IMMUTABLE_CONFLICT')
        else:
            require(sum(f.stat().st_size for d in ('capture','pages','manifests') for f in (self.root/d).iterdir())+len(data)+131072<=self.spec.max_bytes,'M032_DISK_BUDGET')
            temporary=p.with_suffix('.tmp')
            if temporary.exists(): fingerprint(temporary);temporary.unlink()
            with temporary.open('xb') as stream: stream.write(data);stream.flush();os.fsync(stream.fileno())
            os.replace(temporary,p)
        return digest

    def publish(self, at):
        cp=self.archive.checkpoint()  # Reverify durable journal before exposing any page.
        at=max(utc(at),self.at or utc(at));pages=[]
        for minutes in self.spec.timeframes:
            values=[v for (m,t),v in sorted(self.samples.items()) if m==minutes and self.spec.start<=t<self.spec.end]
            for i in range(0,len(values),64):
                p=Page(self.identity,minutes,tuple(values[i:i+64]));digest=self._immutable('pages',p.to_json().encode())
                pages.append(PageRef(digest,minutes,len(p.bars)))
        quality=set(self.quality)
        required={(m,day) for m in self.spec.timeframes
                  for day in (self.spec.start+timedelta(days=i) for i in range((self.spec.end.date()-self.spec.start.date()).days+
                     (1 if self.spec.end.time()!=datetime.min.time() else 0)))}
        trailing=cutoff_has_incomplete_bar(self.calendar,self.spec)
        complete=required<=self.covered and not trailing
        if trailing: quality.add('HISTORY_TRAILING_INCOMPLETE_BAR')
        if not complete: quality.add('HISTORY_GAP')
        if not complete and (not self.calendar or any(expected(self.calendar,w) is None for w in plan(self.spec))):
            quality.add('CALENDAR_UNKNOWN')
        rejected=bool(quality & {'HISTORY_REJECTED','HISTORY_CONFLICT','HISTORY_EVENT_REJECTED','CONTRACT_CHANGED'})
        status='HISTORICAL_REJECTED' if rejected else 'HISTORICAL_COMPLETE' if complete and pages else 'HISTORICAL_PARTIAL' if pages else 'HISTORICAL_UNAVAILABLE'
        state=self.calendar.state(at) if self.calendar else 'UNKNOWN'
        result=Dataset(self.identity,self.spec,self.origin,self.environment,at,status,'MARKET_'+state,
            tuple(sorted(quality)),tuple(pages),cp.sha256,len(self.rows))
        data=result.to_json().encode();self._immutable('manifests',data)
        temporary=self.root/'dataset.tmp'
        if temporary.exists(): fingerprint(temporary);temporary.unlink()
        with temporary.open('xb') as stream: stream.write(data);stream.flush();os.fsync(stream.fileno())
        for attempt in range(5):
            try: os.replace(temporary,self.root/'dataset.json');break
            except PermissionError:
                if attempt==4: raise
                time.sleep(.002)
        self._check()
        return result

    def close(self):
        if self.archive is not None: self.archive.close()
    def __enter__(self): return self
    def __exit__(self,*args): self.close()


@dataclass(frozen=True, slots=True)
class HistoricalSlice:
    dataset: Dataset
    bars: tuple[HistoricalBar, ...]
    next_cursor: PageCursor | None
    available_count: int
    sufficient: bool


class HistoricalConsumer:
    """Read-only JSON boundary; historical snapshots remain valid without a writer."""
    def __init__(self, directory, spec, session_id, origin, environment):
        self.root=Path(safe_path(directory));self.spec=spec;self.origin=origin;self.environment=environment
        self.identity=content_hash({'schema':'trading.m03a2.store','collector':spec.collector.to_dict(),
            'session':session_id,'origin':origin.value,'environment':environment.value})

    def read(self, minutes, start, end, *, as_of, minimum_bars=1, cursor=None, snapshot=None):
        start,end,as_of=utc(start),utc(end),utc(as_of)
        require(type(minutes) is int and minutes in self.spec.timeframes and
                self.spec.start<=start<end<=self.spec.end and type(minimum_bars) is int and
                0<=minimum_bars<=2048,'M032_QUERY')
        if snapshot is not None:
            from trading_agent.core_v3.economic_contracts import _hash
            _hash(snapshot)
            raw=read_local(self.root/'manifests',snapshot+'.json',max_bytes=131072)
            require(_sha(raw)==snapshot,'M032_MANIFEST_HASH')
        else: raw=read_local(self.root,'dataset.json',max_bytes=131072)
        digest=_sha(raw);manifest=Dataset.from_json(raw.decode())
        require(read_local(self.root/'manifests',digest+'.json',max_bytes=131072)==raw,'M032_IMMUTABLE_MANIFEST')
        query=content_hash({'minutes':minutes,'start':start.isoformat(),'end':end.isoformat(),
                            'as_of':as_of.isoformat(),'minimum_bars':minimum_bars})
        require(manifest.identity_sha256==self.identity and manifest.spec==self.spec and
                manifest.origin is self.origin and manifest.environment is self.environment and
                manifest.available_at<=as_of,'M032_DATASET_BINDING_OR_CUTOFF')
        offset=0
        if cursor is not None:
            require(type(cursor) is PageCursor and cursor.dataset_sha256==digest and cursor.query_sha256==query,'M032_CURSOR_SNAPSHOT')
            offset=cursor.index
        total=0;selected=();next_cursor=None
        for index,ref in enumerate(manifest.pages):
            if ref.minutes!=minutes: continue
            data=read_local(self.root/'pages',ref.sha256+'.json',max_bytes=131072)
            require(_sha(data)==ref.sha256,'M032_PAGE_HASH')
            page=Page.from_json(data.decode())
            require(page.identity_sha256==self.identity and page.minutes==minutes and len(page.bars)==ref.count,
                    'M032_PAGE_BINDING')
            values=tuple(b for b in page.bars if start<=b.bar.opened_at<end)
            require(all(b.origin is self.origin and b.environment is self.environment and
                        b.bar.available_at<=manifest.available_at for b in page.bars),'M032_PAGE_CAUSALITY')
            total+=len(values)
            if index>=offset and values:
                if not selected: selected=values;next_cursor=PageCursor(digest,query,index+1)
        if next_cursor and not any(p.minutes==minutes for p in manifest.pages[next_cursor.index:]): next_cursor=None
        if snapshot is None: require(read_local(self.root,'dataset.json',max_bytes=131072)==raw,'M032_PUBLICATION_CHANGED')
        return HistoricalSlice(manifest,selected,next_cursor,total,
                               total>=minimum_bars and manifest.status=='HISTORICAL_COMPLETE')
