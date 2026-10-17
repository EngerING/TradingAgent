import argparse
from datetime import datetime, timedelta, timezone
import json
from .market import Candle, analyze_timeframes
from .backtest import Config, run

parser=argparse.ArgumentParser()
parser.add_argument("command",choices=["demo","analyze","backtest"])
parser.add_argument("--input")
args=parser.parse_args()
if args.command=="demo":
    base=datetime(2026,1,5,tzinfo=timezone.utc)
    def series(minutes):
        return [Candle(base+timedelta(minutes=i*minutes),minutes,1.1+i*.0001,1.102+i*.0001,1.098+i*.0001,1.1005+i*.0001) for i in range(80)]
    print(json.dumps({"analysis":analyze_timeframes({m:series(m) for m in (15,60,240)},base+timedelta(days=14)),
                      "backtest":run(series(15),Config(signal="always_long"))},allow_nan=False))
else:
    if not args.input: parser.error("--input required")
    with open(args.input,encoding="utf-8") as f: payload=json.load(f)
    bars=[Candle(**{**b,"opened_at":datetime.fromisoformat(b["opened_at"])}) for b in payload["candles"]]
    if args.command=="analyze":
        from .market import analyze
        result=analyze(bars,datetime.fromisoformat(payload["as_of"]))
    else:
        result=run(bars,Config(**payload.get("config",{})),dataset_role=payload.get("dataset_role","development"))
    print(json.dumps(result,allow_nan=False))
