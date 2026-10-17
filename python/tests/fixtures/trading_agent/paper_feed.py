"""TEST DOUBLE: no SDK import, socket or broker connection."""
from datetime import datetime,timezone,timedelta
import hashlib
import json
import os
import sys
import threading

account='PAPER-'+hashlib.sha256(os.environ['IBKR_PAPER_ACCOUNT'].encode()).hexdigest()[:16]
stop=threading.Event()
threading.Thread(target=lambda:(sys.stdin.readline(),stop.set()),daemon=True).start()
def emit(kind,data):
    print(json.dumps(dict(kind=kind,account_id=account,received_at=datetime.now(timezone.utc).isoformat(),data=data)),flush=True)
def status(state):
    emit('status',dict(state=state,account_verified=state=='CONNECTED',port=7497,client_id=73,server_version=226,
                      sdk_version='TEST_DOUBLE',read_only=True,live_enabled=False,orders_supported=False,reason=None))
status('CONNECTED')
now=datetime.now(timezone.utc).isoformat()
emit('account',dict(base_currency='USD',received_at=now,values=[dict(tag=t,value=v,currency='USD') for t,v in
    [('Currency','USD'),('NetLiquidation','1000000'),('TotalCashValue','1000000'),('AvailableFunds','1000000')]]))
emit('positions',[])
emit('contract',dict(con_id=12087792,symbol='EUR',currency='USD',security_type='CASH',exchange='IDEALPRO',valid_exchanges='IDEALPRO',
    min_tick='.00005',market_rule_ids='1',trading_hours='',liquid_hours='',time_zone='US/Eastern',order_types='MKT,LMT',
    minimum_size='20000',size_increment='1',restrictions_verified=False,received_at=now))
emit('quote',dict(instrument='EUR/USD',bid='1.1',ask='1.1002',last=None,spread='.0002',received_at=now,
    bid_received_at=now,ask_received_at=now,source='IBKR_TWS',data_type='FROZEN',market_data_type=2,
    source_timestamp=None,executable=False,reason=None))
for minutes in (15,60,240):
    row=dict(opened_at=datetime(2026,1,5,tzinfo=timezone.utc).isoformat(),minutes=minutes,
             open='1.1',high='1.2',low='1',close='1.15',volume=None,spread=None)
    emit('candles',[row]);emit('candles',[row])
while not stop.wait(.2):status('CONNECTED')
status('DISCONNECTED')
