"""Local NDJSON feed consumed by the authenticated C# backend.

Only trusted environment configuration authorizes the account. Stdout contains
validated observations and an internal account ID; never a full IBKR identity.
"""
from datetime import datetime, timezone
import json
import logging
import signal
import threading
import time
from .broker import PaperDataBroker
from .tws import official_wire, options_from_environment


def safe_reason(exc):
    # Never serialize arbitrary SDK exceptions or account-bearing error text.
    value=str(exc)
    if value.startswith('IBKR_') and value[5:].isdigit():return value
    known={'UNAUTHORIZED_ACCOUNT','BROKER_DISCONNECTED','TWS_PROTOCOL_TIMEOUT','TWS_HANDSHAKE_TIMEOUT',
        'ACCOUNT_VERIFICATION_TIMEOUT','TWS_CONNECT_FAILED','IBKR_READ_TIMEOUT','INVALID_QUOTE',
        'INCOMPLETE_BALANCE','INCOMPLETE_BASE_BALANCE','MISSING_BASE_CURRENCY','INVALID_BALANCE',
        'INVALID_CONTRACT','INVALID_CANDLE','INVALID_POSITION','AMBIGUOUS_OR_MISSING_CONTRACT'}
    return value if value in known else type(exc).__name__.upper()


def main():
    import ibapi
    options=options_from_environment();options.validate()
    logging.getLogger('ibapi').setLevel(logging.CRITICAL)
    stop=threading.Event()
    def read_control():
        if __import__('sys').stdin.readline().strip()=='shutdown':stop.set()
    threading.Thread(target=read_control,daemon=True).start()
    for sig in (signal.SIGINT,signal.SIGTERM):signal.signal(sig,lambda *_:stop.set())
    broker=PaperDataBroker(options,official_wire,sleeper=lambda delay:stop.wait(delay))

    def emit(kind,data):
        print(json.dumps({'kind':kind,'account_id':options.internal_id,
            'received_at':datetime.now(timezone.utc).isoformat(),'data':data},allow_nan=False),flush=True)

    def status(state,reason=None):
        emit('status',{'state':state,'account_verified':broker.connected,'port':options.port,'client_id':options.client_id,
            'server_version':broker.wire.server_version if broker.connected else None,'sdk_version':ibapi.get_version_string(),
            'read_only':True,'live_enabled':False,'orders_supported':False,'reason':reason})

    next_history=0;next_account=0;failure_delay=1
    try:
        while not stop.is_set():
            try:
                if not broker.connected:
                    status('CONNECTING');broker.connect();status('CONNECTED')
                    failure_delay=1;next_account=0
                    emit('contract',broker.contract_details())
                if time.monotonic()>=next_account:
                    emit('account',broker.balance());emit('positions',broker.positions());next_account=time.monotonic()+60
                emit('quote',broker.quote())
                if time.monotonic()>=next_history:
                    # Set before requesting: an error must not create a fast pacing retry.
                    next_history=time.monotonic()+900
                    for minutes in (15,60,240):
                        if stop.is_set():break
                        try:
                            emit('candles',broker.history(minutes=minutes))
                            stats=getattr(broker.wire,'history_stats',None)
                            if stats:
                                emit('event',{'code':f"HISTORY_{minutes}_RECEIVED_{stats['received']}_RETAINED_{stats['retained']}_SHORT_INTERVAL_{stats['short_interval']}"})
                        except (ValueError,RuntimeError) as exc:emit('event',{'code':safe_reason(exc)})
                        status('CONNECTED')
                if broker.wire:
                    for event in broker.wire.events:
                        emit('event',{'code':'IBKR_'+str(event['code'])})
                    broker.wire.events.clear()
                status('CONNECTED')
                stop.wait(20)
            except PermissionError as exc:
                broker.disconnect();status('REJECTED',safe_reason(exc));return 2
            except (ConnectionError,TimeoutError,OSError) as exc:
                broker.disconnect();status('DISCONNECTED',safe_reason(exc))
                stop.wait(failure_delay);failure_delay=min(60,failure_delay*2)
            except (ValueError,RuntimeError) as exc:
                emit('event',{'code':safe_reason(exc)});status('DEGRADED',safe_reason(exc));stop.wait(60)
    finally:
        broker.disconnect();status('DISCONNECTED','SHUTDOWN')
    return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:
        # No traceback: configuration may contain a sensitive identifier.
        print(safe_reason(exc),file=__import__('sys').stderr)
        raise SystemExit(1)
