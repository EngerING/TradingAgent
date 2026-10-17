"""Resumable read-only IBKR history archive. Reuses the guarded transport; no orders."""
from datetime import datetime,timezone,timedelta
from decimal import Decimal
import hashlib,json,logging,os,time
from pathlib import Path
from types import MethodType
from .tws import official_wire,options_from_environment,finite
from .broker import PaperDataBroker

UTC=timezone.utc
SIZES={15:'15 mins',60:'1 hour',240:'4 hours'}

def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def stamp(value):
    result=datetime.fromisoformat(value)
    if result.tzinfo is None:raise ValueError('TIMEZONE_REQUIRED')
    return result.astimezone(UTC)
def pages(start,end,minutes):
    if minutes not in SIZES or end<=start or end-start>timedelta(days=370):raise ValueError('INVALID_ARCHIVE_RANGE')
    days=7 if minutes==15 else 28
    while end>start:
        yield {'start':max(start,end-timedelta(days=days)).isoformat(),'end':end.isoformat(),'days':days,'minutes':minutes}
        end-=timedelta(days=days)

def research_wire(options,sdk_types=None):
    w=official_wire(options,sdk_types)
    def historical(self,req,bar):
        if req!=self.request_id or self.active!='research_history':return
        try:
            at=datetime.fromtimestamp(int(bar.date),UTC)
            prices=[str(finite(getattr(bar,k),True)) for k in ('open','high','low','close')]
            o,h,l,c=map(Decimal,prices)
            if h<max(o,l,c) or l>min(o,h,c):raise ValueError('INVALID_OHLC')
            self.data.append(dict(opened_at=at.isoformat(),minutes=self.bar_minutes,
                open=prices[0],high=prices[1],low=prices[2],close=prices[3],volume=None,spread=None))
        except (ValueError,ArithmeticError,OverflowError):self._invalid('INVALID_ARCHIVE_BAR')
    def complete(self,req,*args):
        if req==self.request_id and self.active=='research_history':self.done.set()
    def schedule(self,req,start,end,zone,sessions):
        if req==self.request_id and self.active=='research_schedule':
            self.data=[{'start':start,'end':end,'time_zone':zone,'sessions':[
                {'start':s.startDateTime,'end':s.endDateTime,'reference_date':s.refDate} for s in sessions]}];self.done.set()
    def ticks(self,req,rows,done):
        if req!=self.request_id or self.active!='research_ticks':return
        try:
            for r in rows:
                bid,ask=finite(r.priceBid,True),finite(r.priceAsk,True)
                if ask<bid:raise ValueError('CROSSED_BID_ASK')
                self.data.append({'timestamp':datetime.fromtimestamp(r.time,UTC).isoformat(),'bid':str(bid),'ask':str(ask),
                    'spread':str(ask-bid),'bid_past_low':bool(r.tickAttribBidAsk.bidPastLow),'ask_past_high':bool(r.tickAttribBidAsk.askPastHigh)})
            if done:self.done.set()
        except (ValueError,ArithmeticError,OverflowError):self._invalid('INVALID_ARCHIVE_TICK')
    w.historicalData=MethodType(historical,w);w.historicalDataEnd=MethodType(complete,w)
    w.historicalSchedule=MethodType(schedule,w);w.historicalTicksBidAsk=MethodType(ticks,w)
    return w

class Archive:
    def __init__(self,wire,root,account,cutoff,clock=time.monotonic,sleep=time.sleep):
        self.wire=wire;self.root=Path(root);self.account=account;self.cutoff=cutoff;self.clock=clock;self.sleep=sleep;self.last=None
        self.root.mkdir(parents=True,exist_ok=True)
    def request(self,spec):
        key=digest({'account':self.account,'contract':'EURUSD:CASH:IDEALPRO','spec':spec})
        path=self.root/(key+'.json')
        if path.exists():
            result=json.loads(path.read_text(encoding='utf-8'))
            if result.get('request')!=spec or result.get('account_id')!=self.account or result.get('content_hash')!=digest(result['rows']):
                raise ValueError('ARCHIVE_INTEGRITY_FAILED')
            return result
        # Sequential, <=50 request weight / 10min; BID_ASK gets double spacing.
        weight=2 if spec['kind']=='BID_ASK' else 1
        pacing=self.root/'pacing.json'
        if pacing.exists():
            previous=stamp(json.loads(pacing.read_text(encoding='utf-8'))['sent_at'])
            elapsed=(datetime.now(UTC)-previous).total_seconds()
            if elapsed<12*weight:self.sleep(12*weight-elapsed)
        if self.last is not None:
            delay=12*weight-(self.clock()-self.last)
            if delay>0:self.sleep(delay)
        self.last=self.clock()
        expiry=os.environ.get('PAPER_MANUAL_EXPIRES_AT')
        if not expiry or datetime.now(UTC)>=stamp(expiry):raise PermissionError('PAPER_MANUAL_VERIFICATION_EXPIRED')
        pacing.write_text(json.dumps({'sent_at':datetime.now(UTC).isoformat(),'request_key':key}),encoding='utf-8')
        rows=[];status='AVAILABLE';error=None;w=self.wire
        with w.lock:
            kind=spec['kind'];active='research_schedule' if kind=='SCHEDULE' else 'research_ticks' if kind=='TICKS' else 'research_history'
            req=w._begin(active);w.bar_minutes=spec.get('minutes',15)
            try:
                if kind=='TICKS':
                    w._client.reqHistoricalTicks(req,w.contract('EUR/USD'),stamp(spec['start']).strftime('%Y%m%d-%H:%M:%S'),'',1000,'BID_ASK',0,True,[])
                else:
                    w._client.reqHistoricalData(req,w.contract('EUR/USD'),stamp(spec['end']).strftime('%Y%m%d-%H:%M:%S'),
                        str(spec['days'])+' D','1 day' if kind=='SCHEDULE' else SIZES[spec['minutes']],kind,0,2,False,[])
                rows=w._wait()
                if kind not in ('SCHEDULE','TICKS'):
                    start,end=stamp(spec['start']),stamp(spec['end'])
                    rows=[r for r in rows if start<=stamp(r['opened_at'])<end]
                    unique={}
                    for r in rows:
                        if r['opened_at'] in unique and unique[r['opened_at']]!=r:raise ValueError('CONFLICTING_ARCHIVE_BAR')
                        unique[r['opened_at']]=r
                    rows=[unique[k] for k in sorted(unique)]
                if not rows:status='EMPTY'
            except PermissionError:raise
            except RuntimeError as exc:
                code=str(exc)
                if code not in ('IBKR_162','IBKR_165','IBKR_366','IBKR_321'):raise
                status='UNAVAILABLE';error=code
            except TimeoutError:status='UNAVAILABLE';error='READ_TIMEOUT'
            finally:
                w.active=None
                if kind!='TICKS':w._client.cancelHistoricalData(req)
        result={'schema_version':1,'source':'IBKR_TWS','instrument':'EUR/USD','account_id':self.account,'request':spec,
            'received_at':datetime.now(UTC).isoformat(),'availability':status,'error':error,'request_weight':weight,
            'rows':rows,'content_hash':digest(rows),'live_enabled':False,'orders_supported':False}
        # Exclusive immutable page; a completed identical request is never sent again.
        with path.open('x',encoding='utf-8') as f:json.dump(result,f,allow_nan=False)
        return result

def collect(root,start,end,broker):
    archive=Archive(broker.wire,root,broker.options.internal_id,end);results=[]
    schedules=list(pages(start,end,60))
    requests=[{**p,'kind':'SCHEDULE'} for p in schedules]
    requests+=[{'kind':'TICKS','start':(end-timedelta(hours=3,minutes=15)).isoformat()}]
    for minutes,kind in ((15,'MIDPOINT'),(60,'MIDPOINT'),(240,'MIDPOINT'),(15,'BID_ASK')):
        requests.extend({**p,'kind':kind} for p in pages(start,end,minutes))
    disabled=set()
    for n,spec in enumerate(requests):
        type_key=spec['kind']+':'+str(spec.get('minutes',0))
        if type_key in disabled:continue
        result=archive.request(spec);results.append(result)
        if result['availability']=='UNAVAILABLE':disabled.add(type_key)
        print(json.dumps({'completed':n+1,'planned':len(requests),'kind':spec['kind'],'minutes':spec.get('minutes'),
                          'rows':len(result['rows']),'availability':result['availability'],'error':result['error']}),flush=True)
        manifest={'schema_version':1,'source':'IBKR_TWS','account_id':broker.options.internal_id,'instrument':'EUR/USD',
            'requested_start':start.isoformat(),'requested_end':end.isoformat(),'receipts':results,
            'unavailable_types':sorted(disabled),'orders_supported':False,'live_enabled':False}
        temp=archive.root/'manifest.tmp';temp.write_text(json.dumps(manifest,allow_nan=False),encoding='utf-8');temp.replace(archive.root/'manifest.json')
    return manifest

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--start',required=True);p.add_argument('--end',required=True);args=p.parse_args()
    options=options_from_environment();broker=PaperDataBroker(options,research_wire);root=Path(args.root)
    root.mkdir(parents=True,exist_ok=True);lock=root/'collector.lock'
    logging.getLogger('ibapi').setLevel(logging.CRITICAL)
    try:
        with lock.open('x') as f:f.write('exclusive collector')
    except FileExistsError:raise SystemExit('ARCHIVE_COLLECTOR_ALREADY_RUNNING')
    try:
        broker.connect();collect(root,stamp(args.start),stamp(args.end),broker)
    except Exception as exc:
        print(json.dumps({'status':'BLOCKED','reason':str(exc) if str(exc).startswith(('IBKR_','PAPER_','BROKER_','ARCHIVE_')) else type(exc).__name__}),flush=True);raise SystemExit(1)
    finally:broker.disconnect();lock.unlink(missing_ok=True)
