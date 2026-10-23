"""Require the 507 preserved cases and all additional distinct Windows fixtures."""
import ast
import json
from pathlib import Path
import re
import runpy

runpy.run_path('build/market-data/verify-results.py',run_name='__main__')
old=json.loads(Path('tmp/m03a/results.json').read_text())
assert old['distinct_total']==507,'M032_PRESERVED_507'
root=Path('tmp/m03a2');tests=json.loads((root/'tests.json').read_text())
assert tests['total']==tests['passed']==tests['distinct']==42,'M032_TEST_COUNT'
assert tests['failed']==tests['skipped']==tests['barrier_violations']==0,'M032_TEST_RESULT'
expected=set()
for p in Path('python/tests').glob('test_m03a2_*.py'):
    for cls in ast.parse(p.read_text()).body:
        if isinstance(cls,ast.ClassDef):
            expected.update(p.stem+'.'+cls.name+'.'+m.name for m in cls.body if isinstance(m,ast.FunctionDef) and m.name.startswith('test_'))
assert set(tests['test_ids'])==expected and len(expected)==42,'M032_REQUIRED_IDS'
concurrency=json.loads((root/'concurrency.json').read_text())
assert concurrency['platform']=='win32' and concurrency['total']==concurrency['passed']==2,'M032_WINDOWS_PROCESSES'
assert concurrency['failed']==concurrency['skipped']==concurrency['barrier_violations']==concurrency['child_barrier_violations']==0,'M032_PROCESS_FAILURE'
for name,count in (('units',42),('concurrency',2)):
    payload=(root/(name+'.log')).read_bytes()
    log=payload.decode('utf-16' if payload.startswith((b'\xff\xfe',b'\xfe\xff')) else 'utf-8-sig')
    assert re.search(r'Ran '+str(count)+r' tests in ',log) and re.search(r'^OK\s*$',log,re.M),'M032_LOG_RESULT'
report={'preserved':old,'new_units':tests,'new_windows_processes':concurrency,
        'distinct_total':507+tests['passed']+concurrency['passed'],'failed':0,'skipped':0}
(root/'results.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
