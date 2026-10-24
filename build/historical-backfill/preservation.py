"""Exact M03-A.2 additions; every integrated baseline blob remains protected."""
import json
from pathlib import Path
import subprocess

BASE='b7129313f216b24184c54f519fbc761c151bc101'
MAIN='f67fa92086d10b9562df214f4e869344bf0753d8'
DISPATCH='build/market-data/preservation.py'
ADDITIONS={
    *('python/trading_agent/market_data/backfill/'+p+'.py' for p in ('__init__','__main__','contracts','wire','store','reader','host_provisioner')),
    *('python/tests/test_m03a2_'+p+'.py' for p in ('backfill','protocol','recovery','review')),
    'python/tests/test_m03a2_host_provisioner.py',
    'python/tests/m03a2_offline_check.py','python/tests/m03a2_concurrency_worker.py',
    *('build/historical-backfill/'+p for p in ('preservation.py','verify-results.py','run-approved.ps1','prepare-paper-history.ps1','concurrency-check.py')),
    '.github/workflows/m03a2-historical-backfill-ci.yml',
    'docs/architecture/m03a2-historical-backfill.md','docs/architecture/m03a2-evidence.json',
}


def git(*args): return subprocess.check_output(['git',*args],text=True).strip()


subprocess.run(['git','merge-base','--is-ancestor',BASE,'HEAD'],check=True)
changes=[r.split('\t') for r in git('diff','--no-renames','--name-status',BASE,'HEAD').splitlines()]
assert all((s=='A' and p in ADDITIONS) or (s=='M' and p==DISPATCH) for s,p in changes),'M032_EXACT_ALLOWLIST'
protected={}
def objects(ref):
    return {row.split('\t',1)[1]:row.split('\t',1)[0] for row in git('ls-tree','-r',ref).splitlines()}
before,after=objects(BASE),objects('HEAD')
for p,value in before.items():
    if p!=DISPATCH: assert after.get(p)==value,'M032_BASELINE_BLOB_CHANGED'
for p in ('python/trading_agent/core_v3','python/trading_agent/market_analyst','python/trading_agent/market_data/contracts.py',
          'python/trading_agent/market_data/projection.py','src/TradingAgent.Infrastructure','src/TradingAgent.Core',
          'src/TradingAgent.Api','frontend','frontend-react','src/TradingAgent.Web','src/TradingAgent.Web.Auth',
          'Directory.Build.props','TradingAgent.sln'):
    protected[p]=git('rev-parse','HEAD:'+p)
assert git('rev-parse','origin/main')==MAIN,'M032_MAIN_CHANGED'
subprocess.run(['git','diff','--exit-code','HEAD','--',*sorted(ADDITIONS),DISPATCH],check=True)
report={'baseline':BASE,'head':git('rev-parse','HEAD'),'tree':git('rev-parse','HEAD^{tree}'),
        'main':MAIN,'protected_git_objects':protected,'preserved_base_files':len(before)-1,
        'additions':sum(s=='A' for s,p in changes),'modifications':sum(s=='M' for s,p in changes),
        'deletions':0,'diff':changes,'mode':'OFFLINE','decision':'NO_TRADE'}
root=Path('tmp/m03a2');root.mkdir(parents=True,exist_ok=True)
(root/'preservation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
