"""Additions only against approved develop; all preexisting Git objects stay untouched."""
import json
from pathlib import Path
import subprocess

BASE = '363e40985fbd3533992c70dfbe2aa05f6774ba9f'
MAIN = 'f67fa92086d10b9562df214f4e869344bf0753d8'
CORRECTION_BASE = '524c23f6629f46750a52c4b6da31c78252ffe5be'
AUDIT_BASE = '8faa5869d50e0f8753d2745e7d4524fd06caa4cc'
AUDIT_ADDITIONS = {
    'python/tests/test_m03a_audit_fixes.py',
    'docs/architecture/m03a1-audit-fixes.md','docs/architecture/m03a1-audit-fixes-evidence.json',
}
AUDIT_EDITS = {
    'python/trading_agent/market_data/projection.py','python/trading_agent/market_data/archive.py',
    'python/trading_agent/market_data/supervisor.py','python/tests/m03a_offline_check.py',
    'build/market-data/preservation.py','build/market-data/verify-results.py',
}
CORRECTION_ADDITIONS = {
    'python/trading_agent/market_data/consumer.py','python/trading_agent/market_data/projection.py',
    'python/trading_agent/market_data/publication.py','python/tests/test_m03a_consumer.py',
    'python/tests/m03a_concurrency_worker.py','build/market-data/concurrency-check.py',
    'docs/architecture/m03a1-concurrent-reader.md','docs/architecture/m03a1-evidence.json',
}
CORRECTION_EDITS = {
    'python/trading_agent/market_data/archive.py','python/trading_agent/market_data/supervisor.py',
    'python/tests/m03a_offline_check.py','build/market-data/preservation.py',
    'build/market-data/verify-results.py','.github/workflows/m03a-market-data-ci.yml',
}
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
CORRECTION_ADDITIONS |= AUDIT_ADDITIONS
ALLOWED |= CORRECTION_ADDITIONS


def git(*args): return subprocess.check_output(['git',*args],text=True).strip()


subprocess.run(['git','merge-base','--is-ancestor',BASE,'HEAD'],check=True)
subprocess.run(['git','merge-base','--is-ancestor',CORRECTION_BASE,'HEAD'],check=True)
subprocess.run(['git','merge-base','--is-ancestor',AUDIT_BASE,'HEAD'],check=True)
audit = [row.split('\t') for row in git('diff','--name-status',AUDIT_BASE,'HEAD').splitlines()]
assert all((s == 'A' and p in AUDIT_ADDITIONS) or (s == 'M' and p in AUDIT_EDITS)
           for s,p in audit), 'M03A1_AUDIT_EXACT_ALLOWLIST'
correction = [row.split('\t') for row in git('diff','--name-status',CORRECTION_BASE,'HEAD').splitlines()]
assert all((s == 'A' and p in CORRECTION_ADDITIONS) or (s == 'M' and p in CORRECTION_EDITS)
           for s,p in correction), 'M03A1_EXACT_CORRECTION_ALLOWLIST'
changes = [row.split('\t') for row in git('diff','--name-status',BASE,'HEAD').splitlines()]
assert all((status == 'A' and name in ALLOWED) or (status == 'M' and name == DISPATCHER)
           for status,name in changes), 'M03_EXACT_ALLOWLIST'
subprocess.run(['git','diff','--exit-code','--',*sorted(ALLOWED),DISPATCHER],check=True)
assert git('rev-parse','origin/main') == MAIN, 'M03_MAIN_PRESERVED'
protected = {}
for path in ('python/trading_agent/core_v3','python/trading_agent/market_analyst','frontend',
             'src/TradingAgent.Infrastructure','src/TradingAgent.Core','src/TradingAgent.Api',
             'Directory.Build.props','TradingAgent.sln','frontend-react','src/TradingAgent.Web'):
    old,current = git('rev-parse',BASE+':'+path),git('rev-parse','HEAD:'+path)
    assert old == current, 'M03_PROTECTED_OBJECT'
    protected[path] = current
report = {'baseline':BASE,'head':git('rev-parse','HEAD'),'tree':git('rev-parse','HEAD^{tree}'),
          'main':MAIN,'protected_git_objects':protected,'additions':sum(s=='A' for s,p in changes),
          'modifications':sum(s=='M' for s,p in changes),'deletions':0,
          'correction_baseline':CORRECTION_BASE,'correction_diff':correction,
          'audit_baseline':AUDIT_BASE,'audit_diff':audit,
          'approved_infrastructure_edit':DISPATCHER}
root = Path('tmp/m03a')
root.mkdir(parents=True,exist_ok=True)
(root/'preservation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
