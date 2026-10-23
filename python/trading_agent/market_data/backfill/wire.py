"""Bounded V157 history-only grammar. No quote or order operation encoder."""
from datetime import timedelta, datetime, timezone
import hashlib

from trading_agent.core_v3.contracts import require, parse_decimal, ContractError
from ..wire import _frame
from ..contracts import Bar
from .contracts import Window


def plan(spec):
    windows=[]
    for minutes in spec.timeframes:
        start=spec.start
        while start<spec.end:
            end=min(spec.end,start+timedelta(days={15:1,60:4,240:7}[minutes]))
            windows.append(Window(3000+len(windows),minutes,start,end)); start=end
    require(len(windows)+5<=spec.collector.capture.max_requests,'M032_REQUEST_BUDGET')
    return tuple(windows)


def request(window, con_id):
    require(type(window) is Window and type(con_id) is int and 0<con_id<2**31,'M032_COMMAND')
    days=(window.end-window.start).days
    return _frame([20,window.request_id,con_id,'EUR','CASH','','0.0','','','IDEALPRO','',
        'USD','','',0,window.end.strftime('%Y%m%d-%H:%M:%S'),
        {15:'15 mins',60:'1 hour',240:'4 hours'}[window.minutes],str(days)+' D',0,'MIDPOINT',2,0,''])


def cancel(request_id):
    require(type(request_id) is int and 3000<=request_id<3032,'M032_COMMAND')
    return _frame([25,1,request_id])


def history_fields(payload):
    require(type(payload) is bytes and 0<len(payload)<=16384 and payload.endswith(b'\0'),'M032_FRAME')
    try:
        f=payload[:-1].decode('ascii').split('\0')
        require(len(f)>=5 and f[0]=='17' and 3000<=int(f[1])<3032 and
                0<=int(f[4])<=128 and len(f)==5+8*int(f[4]),'M032_LAYOUT')
        return f
    except (UnicodeError,ValueError,IndexError): raise ContractError('M032_LAYOUT') from None


def bars(payload, window, received_at, available_at, calendar, contract):
    f=history_fields(payload)
    require(int(f[1])==window.request_id,'M032_REQUEST_BINDING')
    result=[]; previous=None
    for i in range(int(f[4])):
        p=f[5+8*i:13+8*i]
        require(p[0].isascii() and p[0].isdigit() and len(p[0])<=11,'M032_TIMESTAMP')
        try: opened=datetime.fromtimestamp(int(p[0]),timezone.utc)
        except (ValueError,OverflowError,OSError): raise ContractError('M032_TIMESTAMP') from None
        require(window.start<=opened<window.end,'M032_BAR_RANGE')
        require(previous is None or opened>=previous,'M032_BAR_ORDER')
        previous=opened
        nominal=opened+timedelta(minutes=window.minutes)
        session=calendar.interval(opened) if calendar else None
        if session:
            require((opened-session[0]).total_seconds()%(window.minutes*60)==0,'M032_BAR_GRID')
        elif calendar and opened.astimezone(calendar.zone).date() in calendar.days:
            require(False,'M032_BAR_CLOSED_SESSION')
        close=min(nominal,session[1]) if session else nominal
        require(close<=min(window.end,received_at,available_at),'M032_FUTURE_BAR')
        prices=tuple(parse_decimal(v) for v in p[1:5])
        require(all(v%contract.min_tick==0 for v in prices),'M032_PRICE_TICK')
        quality=() if session else ('BAR_CALENDAR_UNKNOWN',)
        if close!=nominal: quality+=('BAR_SESSION_BOUNDARY',)
        result.append(Bar(p[0],opened,close,available_at,window.minutes,*prices,True,quality,
                          hashlib.sha256(payload).hexdigest()))
    return tuple(result)
