"""Finite contractDetails.tradingHours, not an inferred Forex weekly template."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from trading_agent.core_v3.contracts import require, ContractError, utc


class TradingCalendar:
    def __init__(self, zone, hours, received_at):
        require(type(zone) is str and 0 < len(zone) <= 80 and type(hours) is str and
                0 < len(hours) <= 4096, 'M03_CALENDAR_MISSING')
        require(zone == 'UTC' or '/' in zone, 'M03_CALENDAR_ZONE_UNCERTAIN')
        self.received_at = utc(received_at)
        try:
            self.zone = ZoneInfo(zone)
            sessions, days = [], set()
            for item in hours.split(';'):
                day, intervals = item.split(':', 1)
                date = datetime.strptime(day, '%Y%m%d').date()
                require(date not in days, 'M03_CALENDAR_CONFLICT')
                days.add(date)
                if intervals == 'CLOSED':
                    continue
                for pair in intervals.split(','):
                    start, end = pair.split('-')
                    a, b = (self._point(p if ':' in p else day+':'+p) for p in (start, end))
                    require(a < b and (b-a) <= timedelta(days=2), 'M03_CALENDAR_INTERVAL')
                    sessions.append((a, b))
            self.sessions = tuple(sorted(sessions))
            self.days = frozenset(days)
            require(len(days) <= 16 and len(sessions) <= 64 and all(a[1] <= b[0]
                    for a, b in zip(self.sessions, self.sessions[1:])), 'M03_CALENDAR_CONFLICT')
        except (ValueError, ZoneInfoNotFoundError, OverflowError):
            raise ContractError('M03_CALENDAR_FORMAT') from None

    def _point(self, text):
        wall = datetime.strptime(text, '%Y%m%d:%H%M')
        a, b = (wall.replace(tzinfo=self.zone, fold=f) for f in (0, 1))
        require(a.utcoffset() == b.utcoffset() and
                a.astimezone(timezone.utc).astimezone(self.zone).replace(tzinfo=None) == wall,
                'M03_CALENDAR_DST_UNCERTAIN')
        return a.astimezone(timezone.utc)

    def state(self, at):
        at = utc(at)
        if not self.received_at <= at <= self.received_at+timedelta(hours=24):
            return 'UNKNOWN'
        if any(a <= at < b for a, b in self.sessions):
            return 'OPEN'
        return 'CLOSED' if at.astimezone(self.zone).date() in self.days else 'UNKNOWN'

    def next_open(self, at):
        return next((a for a, b in self.sessions if a > at), None)

    def interval(self, at):
        return next(((a, b) for a, b in self.sessions if a <= at < b), None)
