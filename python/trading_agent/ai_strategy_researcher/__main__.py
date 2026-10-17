import argparse
import json
import re
from pathlib import Path
from .contracts import encoded
from .data import prepare,FOLDER,load_dataset
from .memory import load_readonly,persist,compact
from .journal import Journal,exclusive,session_name
from .runner import run


def main():
    p=argparse.ArgumentParser(description='AI_Strategy_Researcher: offline research only, no orders.')
    p.add_argument('action',choices=('prepare','run','status','memory'))
    p.add_argument('--root',default='.');p.add_argument('--session',default='research-001')
    p.add_argument('--provider',choices=('simulated','openai'),default='simulated')
    a=p.parse_args();root=Path(a.root).resolve()
    if a.action=='prepare':
        with exclusive(root):d=prepare(root)
        print(json.dumps(dict(mode=d['mode'],final_holdout_sealed=True,
            bars={s:{tf:len(r) for tf,r in t.items()} for s,t in d['series'].items()},orders_sent=0)))
    elif a.action=='run':
        r=run(root,a.session,a.provider)
        print(json.dumps({k:r[k] for k in ('session','decision','session_state','stop_reason','consumption','orders_sent')}))
    elif a.action=='memory':
        package,_=load_dataset(root)
        with exclusive(root):
            snapshot=load_readonly(root,package);sha=persist(root,snapshot)
        print(encoded(dict(snapshot_sha256=sha,research_memory=compact(snapshot),orders_sent=0,openai_requests=0)).decode())
    else:
        session_name(a.session)
        with exclusive(root):
            j=Journal(root)
            try:r=j.status(a.session)
            finally:j.close()
        print(encoded({k:v for k,v in r.items() if k not in ('experiments','config')}).decode())


if __name__=='__main__':
    try:main()
    except Exception as exc:
        # Error codes/type only; API keys and broker-related content never printed.
        reason=str(exc) if re.fullmatch(r'[A-Z][A-Z0-9_]{1,100}',str(exc)) else 'CONTROLLED_RESEARCH_FAILURE'
        print(json.dumps(dict(status='RESEARCH_BLOCKED',reason=reason,error_type=type(exc).__name__,orders_sent=0)))
        raise SystemExit(2)
