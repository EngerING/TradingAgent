"""Explicit, versioned session model. Originals are never rewritten or filled."""
from datetime import datetime, date, time, timedelta, timezone
from math import isfinite, ceil
from zoneinfo import ZoneInfo
from .market import Candle

UTC=timezone.utc


def stamp(value):
    at=datetime.fromisoformat(value) if isinstance(value,str) else value
    if at.tzinfo is None:raise ValueError('TIMEZONE_REQUIRED')
    return at.astimezone(UTC)


class ForexCalendar:
    def __init__(self, config):
        self.config=config
        self.zone=ZoneInfo(config['timezone'])
        self.start=date.fromisoformat(config['coverage_start']);self.end=date.fromisoformat(config['coverage_end'])
        if self.end<self.start or (self.end-self.start).days>3660 or config.get('grid_timezone')!='UTC':
            raise ValueError('INVALID_CALENDAR_COVERAGE_OR_GRID')
        self.sessions=[]
        if 'sessions' in config:
            self.sessions=[(stamp(s['start']),stamp(s['end'])) for s in config['sessions']]
            if any(b<=a for a,b in self.sessions) or any(a[1]>b[0] for a,b in zip(self.sessions,self.sessions[1:])):
                raise ValueError('INVALID_EXPLICIT_SESSIONS')
            return
        day=self.start
        while day<=self.end:
            override=config.get('overrides',{}).get(day.isoformat(),'REGULAR')
            if override is not None and (override!='REGULAR' or day.weekday() in config['opening_weekdays']):
                opening=config['opens'] if override=='REGULAR' else override['opens']
                closing=config['closes'] if override=='REGULAR' else override['closes']
                a=datetime.combine(day,time.fromisoformat(opening),self.zone)
                b=datetime.combine(day+timedelta(days=1),time.fromisoformat(closing),self.zone)
                if b<=a:raise ValueError('INVALID_SESSION')
                self.sessions.append((a.astimezone(UTC),b.astimezone(UTC)))
            day+=timedelta(days=1)
    def session(self, at):
        return next(((a,b) for a,b in self.sessions if a<=at<b),None)
    def expected(self, minutes, start, end):
        step=minutes*60
        for a,b in self.sessions:
            opened=datetime.fromtimestamp(ceil(a.timestamp()/step)*step,UTC)
            while opened+timedelta(minutes=minutes)<=b:
                if start<=opened<=end:yield opened
                opened+=timedelta(minutes=minutes)


def normalize(rows, minutes, as_of, calendar):
    """Include only complete native bars on the declared UTC grid inside a session."""
    as_of=stamp(as_of);originals=[];seen=set();previous=None
    for row in rows:
        at=stamp(row['opened_at'])
        if at in seen:raise ValueError('DUPLICATE_CANDLE')
        seen.add(at)
        if previous is not None and at<=previous:raise ValueError('UNSORTED_CANDLES')
        previous=at
        if row['minutes']!=minutes or minutes not in (15,60,240):raise ValueError('TIMEFRAME_MISMATCH')
        prices=[float(row[k]) for k in ('open','high','low','close')]
        o,h,l,c=prices
        if any(not isfinite(x) or x<=0 for x in prices) or h<max(o,l,c) or l>min(o,h,c):raise ValueError('INVALID_OHLC')
        if row.get('volume') is not None or row.get('spread') is not None:raise ValueError('MIDPOINT_HAS_NO_VOLUME_OR_SPREAD')
        originals.append((row,at))
    included=[];audit=[];excluded={}
    for i,(row,at) in enumerate(originals):
        nominal=at+timedelta(minutes=minutes);session=calendar.session(at)
        reason=None;effective=nominal
        if nominal>as_of:reason='NOT_CLOSED_AT_CUTOFF'
        elif session is None:reason='OUTSIDE_CALENDAR_OR_SESSION'
        else:
            effective=min(nominal,session[1])
            if at==session[0] and at.timestamp()%(minutes*60):
                effective=min(effective,datetime.fromtimestamp(ceil(at.timestamp()/(minutes*60))*(minutes*60),UTC))
            if i+1<len(originals) and originals[i+1][1]<nominal:effective=min(effective,originals[i+1][1])
            if effective<nominal:reason='SESSION_BOUNDARY_SHORT_BAR'
            elif at.timestamp()%(minutes*60):reason='OFF_DECLARED_GRID'
        audit.append({'opened_at':at.isoformat(),'nominal_closed_at':nominal.isoformat(),
                      'effective_closed_at':effective.isoformat(),'status':reason or 'INCLUDED_NATIVE',
                      'session_boundary':bool(session and (at==session[0] or effective==session[1]))})
        if reason:excluded[reason]=excluded.get(reason,0)+1
        else:included.append(Candle(at,minutes,*(float(row[k]) for k in ('open','high','low','close'))))
    expected=list(calendar.expected(minutes,included[0].opened_at,included[-1].opened_at)) if included else []
    present={c.opened_at for c in included}
    gaps=[t.isoformat() for t in expected if t not in present and t+timedelta(minutes=minutes)<=as_of]
    return included,{'original_count':len(rows),'included_count':len(included),'excluded':excluded,
                     'missing_expected_openings':gaps,'bars':audit,'calendar_status':calendar.config['status'],
                     'method':'NATIVE_FULL_SESSION_BARS_NO_FILL_NO_RESAMPLING'}


def aggregate_15m(candles, minutes, calendar):
    """Optional derived OHLC, requiring every original 15m constituent. Never used as native IBKR data."""
    if minutes not in (60,240):raise ValueError('INVALID_AGGREGATION')
    groups={}
    for c in candles:
        if c.minutes!=15:raise ValueError('AGGREGATION_REQUIRES_15M')
        at=datetime.fromtimestamp(int(c.opened_at.timestamp()//(minutes*60))*(minutes*60),UTC)
        groups.setdefault(at,[]).append(c)
    out=[]
    for at,group in sorted(groups.items()):
        expected=[at+timedelta(minutes=15*i) for i in range(minutes//15)]
        session=calendar.session(at)
        if [b.opened_at for b in group]!=expected or not session or at+timedelta(minutes=minutes)>session[1]:continue
        out.append(Candle(at,minutes,group[0].open,max(c.high for c in group),min(c.low for c in group),group[-1].close))
    return out
