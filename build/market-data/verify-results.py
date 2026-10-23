"""Fail closed on empty, skipped, failed or unexpectedly sized guarded regressions."""
import json
from pathlib import Path
import re

root = Path('tmp/m03a')
report = {}
for suite,expected in (('core_v39_offline_check',394),('market_analyst_offline_check',38),('m03a_offline_check',43)):
    payload = (root/(suite+'.log')).read_bytes()
    log = payload.decode('utf-16' if payload.startswith((b'\xff\xfe',b'\xfe\xff')) else 'utf-8-sig')
    counts = re.findall(r'Ran (\d+) tests? in ([0-9.]+)s',log)
    assert len(counts) == 1 and int(counts[0][0]) >= expected, 'M03_SUITE_TEST_COUNT'
    assert re.search(r'^OK\s*$',log,re.M) and not re.search(r'FAILED|skipped=|ERROR:|FAIL:',log), 'M03_SUITE_RESULT'
    counters = re.findall(r'BARRIER_VIOLATIONS:\s*(\d+)',log)
    assert counters and all(int(c) == 0 for c in counters), 'M03_OFFLINE_BARRIER'
    report[suite] = {'passed':int(counts[0][0]),'failed':0,'skipped':0,'seconds':float(counts[0][1])}
tests = json.loads((root/'tests.json').read_text())
assert tests['total'] == tests['passed'] == tests['distinct'] >= 43, 'M03_DISTINCT_TESTS'
assert tests['failed'] == tests['skipped'] == tests['barrier_violations'] == 0, 'M03_TEST_RESULTS'
(root/'results.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
