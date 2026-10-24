"""M03-A.3 exact diff and protected Git-object guard against integrated develop."""
import json
from pathlib import Path
import subprocess

# M03-A.4 has a new integrated develop baseline and an independent exact-diff
# guard. Keep this dispatcher after merge so all earlier CI workflows still run.
if Path('build/m03a4-host/preservation.py').is_file():
    import runpy
    runpy.run_path('build/m03a4-host/preservation.py',run_name='__main__')
    raise SystemExit(0)

BASE = '3230379de06107b3667eefc24081e9b8ab3ec401'
MAIN = 'f67fa92086d10b9562df214f4e869344bf0753d8'
ADDITIONS = {
    'python/trading_agent/market_data/host_identity.py',
    'python/trading_agent/market_data/host_approval.py',
    'python/trading_agent/market_data/host_service.py',
    'python/tests/test_m03a3_host_identity.py',
    'build/m03a3-host/run-host.ps1',
    'build/m03a3-host/preservation.py',
    '.github/workflows/m03a3-host-identity-ci.yml',
    'docs/architecture/m03a3-persistent-market-identity.md',
}
EDITS = {
    'python/trading_agent/market_data/authorization.py',
    'build/historical-backfill/preservation.py',
}


def git(*args):
    return subprocess.check_output(['git', *args], text=True).strip()


subprocess.run(['git','merge-base','--is-ancestor',BASE,'HEAD'],check=True)
changes = [row.split('\t', 1) for row in
           git('diff','--no-renames','--name-status',BASE,'HEAD').splitlines()]
assert all((status == 'A' and path in ADDITIONS) or
           (status == 'M' and path in EDITS) for status,path in changes),'M033_EXACT_ALLOWLIST'
assert set(path for _,path in changes) == ADDITIONS | EDITS,'M033_REQUIRED_DELIVERY_FILES'
before = dict(row.split('\t',1)[::-1] for row in git('ls-tree','-r',BASE).splitlines())
after = dict(row.split('\t',1)[::-1] for row in git('ls-tree','-r','HEAD').splitlines())
assert set(before) - set(after) == set(),'M033_NO_DELETIONS'
for path, blob in before.items():
    if path not in EDITS:
        assert after.get(path) == blob,'M033_PROTECTED_GIT_OBJECT'
assert git('rev-parse','origin/main') == MAIN,'M033_MAIN_PRESERVED'
protected={}
for path in ('python/trading_agent/core_v3','python/trading_agent/market_analyst',
             'python/trading_agent/market_data/backfill','python/trading_agent/market_data/reader.py',
             'python/trading_agent/market_data/supervisor.py','python/trading_agent/market_data/wire.py',
             'src/TradingAgent.Core','src/TradingAgent.Api','src/TradingAgent.Infrastructure',
             'frontend','frontend-react','TradingAgent.sln','Directory.Build.props'):
    old,current=git('rev-parse',BASE+':'+path),git('rev-parse','HEAD:'+path)
    assert old==current,'M033_SAFETY_COMPONENT_CHANGED'
    protected[path]=current
subprocess.run(['git','diff','--exit-code','HEAD','--',*sorted(ADDITIONS|EDITS)],check=True)
report={'baseline':BASE,'head':git('rev-parse','HEAD'),
        'tree':git('rev-parse','HEAD^{tree}'),'main':MAIN,
        'protected_git_objects':protected,'preserved_base_files':len(before)-len(EDITS),
        'additions':len(ADDITIONS),'modifications':len(EDITS),'deletions':0,
        'diff':changes,'mode':'OFFLINE','decision':'NO_TRADE',
        'executionAuthorized':False,'real_tws_tested':False}
root=Path('tmp/m03a2')
root.mkdir(parents=True,exist_ok=True)
(root/'preservation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report))
