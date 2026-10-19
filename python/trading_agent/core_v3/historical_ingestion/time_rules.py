"""Pinned TZif, offset roundtrips and explicit session grids; no ambient calendar."""
from datetime import datetime, timedelta
import io
import re
import struct
from zoneinfo import ZoneInfo

from ..contracts import ContractError, require, utc
from .contracts import MAX_BYTES, MAX_ROWS, SessionCalendar


class _BoundedTZif(io.BytesIO):
    def read(self, size=-1):
        raw = super().read(size)
        # ZoneInfo's footer loop does not itself stop at EOF. Never return a
        # short positive-size read to that parser, including a missing newline.
        if size > 0 and len(raw) != size:
            raise EOFError
        return raw


def load_zone(raw, name):
    require(type(raw) is bytes and 0 < len(raw) <= MAX_BYTES, 'H38_TZIF_SIZE')
    try:
        return ZoneInfo.from_file(_BoundedTZif(raw), key=name)
    except (ValueError, EOFError, OSError, OverflowError, struct.error, AssertionError):
        raise ContractError('H38_TZIF_INVALID') from None


def parse_timestamp(text, zone):
    require(type(text) is str and re.fullmatch(
        r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}'
        r'(?:\.[0-9]{1,6})?(?:Z|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])', text) is not None,
        'H38_TIMESTAMP_FORMAT')
    require(not text.endswith('-00:00'), 'H38_UNKNOWN_OFFSET')
    try:
        value = datetime.fromisoformat(text.replace('Z', '+00:00'))
        normalized = utc(value)
        local = normalized.astimezone(zone)
        require(local.replace(tzinfo=None) == value.replace(tzinfo=None)
                and local.utcoffset() == value.utcoffset(), 'H38_TIMEZONE_OFFSET')
        return normalized
    except (ValueError, OverflowError) as error:
        if type(error) is ContractError:
            raise
        raise ContractError('H38_TIMESTAMP_INVALID') from None


def session_windows(calendar, start, end):
    require(type(calendar) is SessionCalendar, 'H38_CALENDAR_REQUIRED')
    start, end = utc(start), utc(end)
    require(calendar.coverage_start <= start < end <= calendar.coverage_end, 'H38_WINDOW_COVERAGE')
    return tuple((max(start, s.opened_at), min(end, s.closed_at), s.opened_at)
                 for s in calendar.sessions if s.opened_at < end and s.closed_at > start)


def expected_intervals(calendar, start, end, seconds):
    require(type(seconds) is int and 1 <= seconds <= 86400, 'H38_INTERVAL')
    step = timedelta(seconds=seconds)
    result = []
    for begin, finish, origin in session_windows(calendar, start, end):
        require((begin-origin) % step == timedelta(0) and (finish-origin) % step == timedelta(0),
                'H38_PARTIAL_INTERVAL')
        count = (finish-begin)//step
        require(len(result)+count <= MAX_ROWS, 'H38_GRID_LIMIT')
        result.extend((begin+i*step, begin+(i+1)*step) for i in range(count))
    return tuple(result)
