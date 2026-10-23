"""Fail closed on empty, skipped, failed or unexpectedly sized guarded regressions."""
import json
from pathlib import Path
import re
import ast
import subprocess

root = Path('tmp/m03a')
report = {}
for suite,expected in (('core_v39_offline_check',394),('market_analyst_offline_check',38),('m03a_offline_check',63)):
    payload = (root/(suite+'.log')).read_bytes()
    log = payload.decode('utf-16' if payload.startswith((b'\xff\xfe',b'\xfe\xff')) else 'utf-8-sig')
    counts = re.findall(r'Ran (\d+) tests? in ([0-9.]+)s',log)
    assert len(counts) == 1 and int(counts[0][0]) >= expected, 'M03_SUITE_TEST_COUNT'
    assert re.search(r'^OK\s*$',log,re.M) and not re.search(r'FAILED|skipped=|ERROR:|FAIL:',log), 'M03_SUITE_RESULT'
    counters = re.findall(r'BARRIER_VIOLATIONS:\s*(\d+)',log)
    assert counters and all(int(c) == 0 for c in counters), 'M03_OFFLINE_BARRIER'
    report[suite] = {'passed':int(counts[0][0]),'failed':0,'skipped':0,'seconds':float(counts[0][1])}
tests = json.loads((root/'tests.json').read_text())
assert tests['total'] == tests['passed'] == tests['distinct'] >= 63, 'M03_DISTINCT_TESTS'
assert tests['failed'] == tests['skipped'] == tests['barrier_violations'] == 0, 'M03_TEST_RESULTS'
original = set()
for module in ('contracts','wire','reader','archive','supervisor','adversarial','entrypoint'):
    name = 'test_m03a_'+module
    source = subprocess.check_output(['git','show','524c23f6629f46750a52c4b6da31c78252ffe5be:python/tests/'+name+'.py'],text=True)
    for node in ast.parse(source).body:
        if isinstance(node,ast.ClassDef):
            original.update(name+'.'+node.name+'.'+method.name for method in node.body
                            if isinstance(method,ast.FunctionDef) and method.name.startswith('test_'))
assert len(original) == 47 and original <= set(tests['test_ids']), 'M03_ORIGINAL_TESTS_REQUIRED'
concurrent = json.loads((root/'concurrency.json').read_text())
assert concurrent['platform'] == 'win32' and concurrent['total'] == concurrent['passed'] == len(set(concurrent['test_ids'])) == 3, 'M03A1_WINDOWS_PROCESS_TESTS'
assert concurrent['failed'] == concurrent['skipped'] == concurrent['barrier_violations'] == 0, 'M03A1_PROCESS_RESULTS'
assert concurrent['poll_samples'] >= 35, 'M03A1_PROCESS_POLL_EVIDENCE'
report['windows_processes'] = concurrent
report['consumer_performance'] = tests['consumer_performance']
report['distinct_total'] = sum(report[s]['passed'] for s in ('core_v39_offline_check','market_analyst_offline_check','m03a_offline_check'))+concurrent['passed']
(root/'results.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
