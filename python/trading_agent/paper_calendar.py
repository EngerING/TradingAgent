"""Finite IBKR sessions only. No weekly templates or inferred holidays."""
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
from .paper_lab import date,stamp
from .research_calendar import ForexCalendar


def broker_calendar(schedules,contract,now):
    if not 0<=(now-date(contract['received_at'])).total_seconds()<=300:
        raise PermissionError('IBKR_CALENDAR_STALE')
    intervals={}
    def point(text,zone,fmt):
        wall=datetime.strptime(text,fmt);a=wall.replace(tzinfo=zone,fold=0);b=wall.replace(tzinfo=zone,fold=1)
        if a.utcoffset()!=b.utcoffset() or a.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None)!=wall:
            raise PermissionError('IBKR_CALENDAR_DST_UNCERTAIN')
        return a.astimezone(timezone.utc)
    for s in schedules:
        zone=ZoneInfo(s['time_zone'])
        for row in s['sessions']:
            a,b=(point(row[k],zone,'%Y%m%d-%H:%M:%S') for k in ('start','end'))
            if b<=a:raise PermissionError('IBKR_CALENDAR_INVALID')
            if a in intervals and intervals[a]!=b:raise PermissionError('IBKR_CALENDAR_CONFLICT')
            intervals[a]=b
    zone=ZoneInfo(contract['timezone'])
    for item in contract['hours'].split(';'):
        if not item:continue
        day,periods=item.split(':',1)
        if periods=='CLOSED':continue
        for interval in periods.split(','):
            values=interval.split('-');parsed=[]
            for value in values:
                full=value if ':' in value else day+':'+value
                parsed.append(point(full,zone,'%Y%m%d:%H%M'))
            if len(parsed)!=2 or parsed[1]<=parsed[0]:raise PermissionError('IBKR_CALENDAR_INVALID')
            a,b=parsed
            if a in intervals and intervals[a]!=b:raise PermissionError('IBKR_CALENDAR_CONFLICT')
            intervals[a]=b
    if not intervals:raise PermissionError('IBKR_CALENDAR_UNAVAILABLE')
    result={'version':'ibkr-paper-sessions-v1','timezone':'UTC','grid_timezone':'UTC',
        'coverage_start':min(intervals).date().isoformat(),'coverage_end':max(intervals.values()).date().isoformat(),
        'sessions':[{'start':stamp(a),'end':stamp(b)} for a,b in sorted(intervals.items())],
        'status':'IBKR_AUTHENTIC_SESSIONS','source':'IBKR historicalSchedule + contractDetails.tradingHours',
        'received_at':contract['received_at']}
    ForexCalendar(result) # Reject overlapping/conflicting broker intervals.
    return result
