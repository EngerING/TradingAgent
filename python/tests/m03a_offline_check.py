"""M03-A tests under unchanged V3.8/V3.4 guards, with an exact execution report."""
import json
from pathlib import Path
import sys
import unittest

from core_v38_offline_check import guard, VIOLATIONS
from core_v34_offline_check import main


class ReportingRunner(unittest.TextTestRunner):
    def run(self, test):
        def ids(suite):
            for value in suite:
                if isinstance(value,unittest.TestSuite): yield from ids(value)
                else: yield value.id()
        names = list(ids(test))
        result = super().run(test)
        report = {'schema':'trading.m03a.offline_tests','schema_version':1,
                  'total':result.testsRun,'passed':result.testsRun-len(result.failures)-len(result.errors)-len(result.skipped),
                  'failed':len(result.failures)+len(result.errors),'skipped':len(result.skipped),
                  'distinct':len(set(names)),'test_ids':names,'barrier_violations':len(VIOLATIONS)}
        directory = Path(__file__).resolve().parents[2]/'tmp/m03a'
        directory.mkdir(parents=True,exist_ok=True)
        (directory/'tests.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        if result.testsRun < 45 or result.skipped or len(set(names)) != result.testsRun:
            raise AssertionError('M03_TEST_DISCOVERY_OR_SKIPS')
        return result


if __name__ == '__main__':
    sys.dont_write_bytecode = True
    sys.addaudithook(guard)
    unittest.TextTestRunner = ReportingRunner
    sys.argv[1:] = ['test_m03a_*.py']
    code = main()
    print('M03A_OFFLINE_BARRIER_VIOLATIONS:',len(VIOLATIONS))
    raise SystemExit(code if not VIOLATIONS else 1)
