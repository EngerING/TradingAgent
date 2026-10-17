"""Separate real CPU fallback smoke test; no writes to prediction history."""
import json
from pathlib import Path
import sys
from .config import load
from .persistence import PostgreSQLJournal,source_request
from .adapter import LocalKronosAdapter
from .predictor import KronosPredictionService

def run(root):
    root=Path(root);c=load(root);c.update(device='cpu',sample_count=2,pred_len=2,lookback=16)
    source=PostgreSQLJournal(root).read()['source'];r=source_request(root,source,c)
    s=KronosPredictionService(root,c,LocalKronosAdapter(root,c))
    try:p=s.submit(r).result(timeout=600)
    finally:s.close()
    out=dict(status=p['status'],telemetry=p['telemetry'],lookback=16,pred_len=2,sample_count=2,execution_authority=False,broker_orders=0)
    (root/'artifacts/research/kronos/verification/cpu-fallback.json').write_text(json.dumps(out,indent=2),encoding='utf-8');print(json.dumps(out))

if __name__=='__main__':run(Path(sys.argv[1]) if len(sys.argv)>1 else Path('.'))
