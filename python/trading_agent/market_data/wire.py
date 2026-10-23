"""Only two added read opcodes for legacy 157; no arbitrary command encoder."""
from datetime import datetime, timedelta, timezone
import hashlib
import struct

from trading_agent.core_v3.contracts import require, ContractError, parse_decimal, utc
from trading_agent.core_v3.market_observation.ibkr_protocol import fields
from .contracts import Bar

TIMEFRAMES = {201:15, 202:60, 203:240}


def _frame(values):
    payload = ('\0'.join(map(str, values))+'\0').encode('ascii')
    return struct.pack('!I', len(payload))+payload


def history_request(request_id, con_id, minutes, end):
    require(type(request_id) is int and TIMEFRAMES.get(request_id) == minutes and
            type(con_id) is int and 0 < con_id < 2**31 and type(minutes) is int, 'M03_HISTORY_COMMAND')
    return _frame([20, request_id, con_id, 'EUR', 'CASH', '', '0.0', '', '', 'IDEALPRO', '',
        'USD', '', '', 0, utc(end).strftime('%Y%m%d-%H:%M:%S'),
        {15:'15 mins',60:'1 hour',240:'4 hours'}[minutes], '1 D', 0, 'MIDPOINT', 2, 0, ''])


def cancel_history(request_id):
    require(type(request_id) is int and request_id in TIMEFRAMES, 'M03_HISTORY_COMMAND')
    return _frame([25, 1, request_id])


def request_cutoff(payload, request_id, con_id):
    """Use the actual serialized endpoint cutoff, never the intention's receipt clock."""
    f = fields(payload)
    try:
        cutoff = datetime.strptime(f[15], '%Y%m%d-%H:%M:%S').replace(tzinfo=timezone.utc)
        require(history_request(request_id,con_id,TIMEFRAMES[request_id],cutoff)[4:] == payload,
                'M03_HISTORY_REQUEST_FRAME')
        return cutoff
    except (ValueError,IndexError,KeyError):
        raise ContractError('M03_HISTORY_REQUEST_FRAME') from None


def history_fields(payload):
    require(type(payload) is bytes and 0 < len(payload) <= 16384 and payload.endswith(b'\0'), 'M03_HISTORY_FRAME')
    try:
        f = payload[:-1].decode('ascii').split('\0')
        require(f[0] == '17' and len(f) >= 5 and int(f[1]) in TIMEFRAMES and
                0 <= int(f[4]) <= 128 and len(f) == 5+8*int(f[4]), 'M03_HISTORY_LAYOUT')
        return f
    except (UnicodeError, ValueError, IndexError):
        raise ContractError('M03_HISTORY_LAYOUT') from None


def historical(payload, minutes, received_at, calendar, *, request_end=None):
    f = history_fields(payload)
    require(TIMEFRAMES[int(f[1])] == minutes, 'M03_HISTORY_REQUEST')
    received_at = utc(received_at)
    bars, reasons, previous = [], [], None
    for i in range(int(f[4])):
        p = f[5+i*8:13+i*8]
        require(p[0].isascii() and p[0].isdigit() and len(p[0]) <= 11, 'M03_HISTORY_TIMESTAMP')
        try:
            opened = datetime.fromtimestamp(int(p[0]), timezone.utc)
        except (ValueError, OverflowError, OSError):
            raise ContractError('M03_HISTORY_TIMESTAMP') from None
        require(previous is None or opened > previous, 'M03_HISTORY_DUPLICATE_OR_ORDER')
        if previous is not None and opened != previous+timedelta(minutes=minutes):
            reasons.append('HISTORY_DISCONTINUITY')
        previous = opened
        if request_end is not None:
            require(request_end-timedelta(days=1) <= opened < request_end, 'M03_HISTORY_RANGE')
        nominal = opened+timedelta(minutes=minutes)
        interval = calendar.interval(opened)
        effective = min(nominal, interval[1]) if interval else nominal
        quality = []
        if nominal > received_at: quality.append('BAR_INCOMPLETE')
        if request_end is not None and nominal > request_end: quality.append('BAR_INCOMPLETE_AT_REQUEST')
        if interval is None: quality.append('BAR_CALENDAR_UNAVAILABLE')
        if effective != nominal: quality.append('BAR_SESSION_BOUNDARY')
        prices = tuple(parse_decimal(v) for v in p[1:5])
        bars.append(Bar(p[0], opened, effective, received_at, minutes, *prices, not quality,
                        tuple(quality), hashlib.sha256(payload).hexdigest()))
    return tuple(bars), tuple(sorted(set(reasons)))
