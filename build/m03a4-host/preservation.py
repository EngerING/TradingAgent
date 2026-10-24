"""M03-A.4: exact preservation guard against the merged develop baseline."""
import json
from pathlib import Path
import subprocess

BASE='18f5b9ce22587365950137a58ad6eb0b59559f84'
MAIN='f67fa92086d10b9562df214f4e869344bf0753d8'
ADDITIONS={
    'python/trading_agent/market_data/host_history.py',
    'python/tests/test_m03a4_offhours_health.py',
    'build/m03a4-host/preservation.py',
    '.github/workflows/m03a4-offhours-history-ci.yml',
    'docs/architecture/m03a4-offhours-history-health.md',
}
EDITS={
    'python/trading_agent/market_data/host_service.py',
    'python/trading_agent/market_data/backfill/contracts.py',
    'build/m03a3-host/preservation.py',
}

def git(*args):
    return subprocess.check_output(['git',*args],text=True).strip()

subprocess.run(['git','merge-base','--is-ancestor',BASE,'HEAD'],check=True)
changes=[tuple(row.split('\t',1)) for row in
         git('diff','--no-renames','--name-status',BASE,'HEAD').splitlines()]
assert set(changes)=={('A',p) for p in ADDITIONS}|{('M',p) for p in EDITS},'M034_EXACT_DIFF'
assert not any(s=='D' for s,_ in changes),'M034_NO_DELETION'
before=dict(row.split('\t',1)[::-1] for row in git('ls-tree','-r',BASE).splitlines())
after=dict(row.split('\t',1)[::-1] for row in git('ls-tree','-r','HEAD').splitlines())
assert set(before).issubset(after),'M034_BASE_FILES_PRESERVED'
for path,blob in before.items():
    if path not in EDITS:
        assert after[path]==blob,'M034_PROTECTED_BLOB_CHANGED'
assert git('rev-parse','origin/main')==MAIN,'M034_MAIN_CHANGED'
protected={}
for path in ('python/trading_agent/core_v3','python/trading_agent/market_analyst',
             'python/trading_agent/market_data/reader.py',
             'python/trading_agent/market_data/supervisor.py',
             'python/trading_agent/market_data/backfill/reader.py',
             'python/trading_agent/market_data/backfill/store.py',
             'src/TradingAgent.Infrastructure','src/TradingAgent.Core',
             'src/TradingAgent.Api','frontend','frontend-react','TradingAgent.sln'):
    old,current=git('rev-parse',BASE+':'+path),git('rev-parse','HEAD:'+path)
    assert old==current,'M034_SAFETY_COMPONENT_CHANGED'
    protected[path]=current
subprocess.run(['git','diff','--exit-code','HEAD','--',*sorted(ADDITIONS|EDITS)],check=True)
report={'baseline':BASE,'head':git('rev-parse','HEAD'),
        'tree':git('rev-parse','HEAD^{tree}'),'main':MAIN,
        'preserved_base_files':len(before)-len(EDITS),
        'additions':len(ADDITIONS),'modifications':len(EDITS),'deletions':0,
        'diff':changes,'protected_git_objects':protected,
        'mode':'OFFLINE','decision':'NO_TRADE','executionAuthorized':False,
        'tws_tested':False}
root=Path('tmp/m03a4');root.mkdir(parents=True,exist_ok=True)
(root/'preservation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report))
