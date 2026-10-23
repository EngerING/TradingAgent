"""Additions only against approved develop; all preexisting Git objects stay untouched."""
import json
from pathlib import Path
import subprocess

BASE = '363e40985fbd3533992c70dfbe2aa05f6774ba9f'
MAIN = 'f67fa92086d10b9562df214f4e869344bf0753d8'
ALLOWED = {
    '.github/workflows/m03a-market-data-ci.yml',
    'build/market-data/preservation.py', 'build/market-data/verify-results.py',
    'build/market-data/requirements-ci.txt', 'build/market-data/sdk-oracle.py',
    'build/market-data/run-approved.ps1',
    'docs/architecture/m03a-market-data-collector.md', 'docs/architecture/m03a-review.md',
    'docs/architecture/m03a-evidence.json', 'python/tests/m03a_offline_check.py',
    *('python/tests/test_m03a_'+n+'.py' for n in ('contracts','wire','reader','archive','supervisor','adversarial','entrypoint')),
    *('python/trading_agent/market_data/'+n+'.py' for n in ('__init__','__main__','contracts','authorization',
        'calendar','wire','reader','archive','supervisor')),
}
DISPATCHER = 'build/react-bff/preservation.mjs'


def git(*args): return subprocess.check_output(['git',*args],text=True).strip()


subprocess.run(['git','merge-base','--is-ancestor',BASE,'HEAD'],check=True)
changes = [row.split('\t') for row in git('diff','--name-status',BASE,'HEAD').splitlines()]
assert all((status == 'A' and name in ALLOWED) or (status == 'M' and name == DISPATCHER)
           for status,name in changes), 'M03_EXACT_ALLOWLIST'
subprocess.run(['git','diff','--exit-code','--',*sorted(ALLOWED),DISPATCHER],check=True)
assert git('rev-parse','origin/main') == MAIN, 'M03_MAIN_PRESERVED'
protected = {}
for path in ('python/trading_agent/core_v3','python/trading_agent/market_analyst','frontend',
             'src/TradingAgent.Infrastructure','src/TradingAgent.Core','src/TradingAgent.Api',
             'Directory.Build.props','TradingAgent.sln'):
    old,current = git('rev-parse',BASE+':'+path),git('rev-parse','HEAD:'+path)
    assert old == current, 'M03_PROTECTED_OBJECT'
    protected[path] = current
report = {'baseline':BASE,'head':git('rev-parse','HEAD'),'tree':git('rev-parse','HEAD^{tree}'),
          'main':MAIN,'protected_git_objects':protected,'additions':sum(s=='A' for s,p in changes),
          'modifications':sum(s=='M' for s,p in changes),'deletions':0,
          'approved_infrastructure_edit':DISPATCHER}
root = Path('tmp/m03a')
root.mkdir(parents=True,exist_ok=True)
(root/'preservation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
