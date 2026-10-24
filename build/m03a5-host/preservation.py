"""M03-A.5 immutable develop baseline guard; financial code untouched."""
import json
from pathlib import Path
import subprocess

BASE='8e9a06b3c4f238e797ea6ace3bea651b13e9e628'
MAIN='f67fa92086d10b9562df214f4e869344bf0753d8'
ADDITIONS={
    'python/trading_agent/market_data/host_calendar.py',
    'python/trading_agent/market_data/research_seed.py',
    'python/tests/test_m03a5_session_scheduler.py',
    'build/m03a5-host/preservation.py',
    '.github/workflows/m03a5-market-session-ci.yml',
    'docs/architecture/m03a5-market-session-scheduler.md',
}
EDITS={
    'python/trading_agent/market_data/reader.py',
    'python/trading_agent/market_data/backfill/reader.py',
    'python/trading_agent/market_data/host_history.py',
    'python/trading_agent/market_data/host_service.py',
    'python/tests/test_m03a4_offhours_health.py',
    'build/m03a4-host/preservation.py',
}

def git(*args):return subprocess.check_output(['git',*args],text=True).strip()

subprocess.run(['git','merge-base','--is-ancestor',BASE,'HEAD'],check=True)
changes=[tuple(row.split('\t',1)) for row in
         git('diff','--no-renames','--name-status',BASE,'HEAD').splitlines()]
assert set(changes)=={('A',p) for p in ADDITIONS}|{('M',p) for p in EDITS},'M035_EXACT_DIFF'
before=dict(row.split('\t',1)[::-1] for row in git('ls-tree','-r',BASE).splitlines())
after=dict(row.split('\t',1)[::-1] for row in git('ls-tree','-r','HEAD').splitlines())
assert set(before).issubset(after),'M035_NO_DELETIONS'
for path,blob in before.items():
    if path not in EDITS:assert after[path]==blob,'M035_BASE_BLOB_CHANGED'
assert git('rev-parse','origin/main')==MAIN,'M035_MAIN_CHANGED'
protected={}
for path in ('python/trading_agent/core_v3','python/trading_agent/market_analyst',
             'python/trading_agent/market_data/authorization.py',
             'python/trading_agent/market_data/host_identity.py',
             'python/trading_agent/market_data/host_approval.py',
             'python/trading_agent/market_data/backfill/contracts.py',
             'python/trading_agent/market_data/backfill/store.py',
             'python/trading_agent/kronos','src/TradingAgent.Infrastructure',
             'src/TradingAgent.Core','src/TradingAgent.Api',
             'frontend','frontend-react','TradingAgent.sln','Directory.Build.props'):
    old,current=git('rev-parse',BASE+':'+path),git('rev-parse','HEAD:'+path)
    assert old==current,'M035_PROTECTED_COMPONENT_CHANGED'
    protected[path]=current
subprocess.run(['git','diff','--exit-code','HEAD','--',*sorted(ADDITIONS|EDITS)],check=True)
report={'baseline':BASE,'head':git('rev-parse','HEAD'),
        'tree':git('rev-parse','HEAD^{tree}'),'main':MAIN,
        'preserved_base_files':len(before)-len(EDITS),
        'additions':len(ADDITIONS),'modifications':len(EDITS),'deletions':0,
        'diff':changes,'protected_git_objects':protected,
        'decision':'NO_TRADE','executionAuthorized':False,
        'tws_tested':False,'live_activation':False,'mode':'OFFLINE'}
root=Path('tmp/m03a5');root.mkdir(parents=True,exist_ok=True)
(root/'preservation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report))
