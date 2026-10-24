"""Additional M03-A.2 cases under the unchanged historical no-network barriers."""
import json
from pathlib import Path
import sys
import unittest
from core_v38_offline_check import guard, VIOLATIONS
from core_v34_offline_check import main


class ReportingRunner(unittest.TextTestRunner):
    def run(self, tests):
        def ids(suite):
            for test in suite:
                if isinstance(test,unittest.TestSuite): yield from ids(test)
                else: yield test.id()
        names=list(ids(tests));result=super().run(tests)
        report={'total':result.testsRun,'passed':result.testsRun-len(result.failures)-len(result.errors)-len(result.skipped),
                'failed':len(result.failures)+len(result.errors),'skipped':len(result.skipped),'test_ids':names,
                'distinct':len(set(names)),'barrier_violations':len(VIOLATIONS)}
        root=Path(__file__).resolve().parents[2]/'tmp/m03a2';root.mkdir(parents=True,exist_ok=True)
        (root/'tests.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        assert result.testsRun>=42 and len(set(names))==result.testsRun and not result.skipped,'M032_DISCOVERY'
        return result


if __name__=='__main__':
    sys.dont_write_bytecode=True;sys.addaudithook(guard);unittest.TextTestRunner=ReportingRunner
    sys.argv[1:]=['test_m03a2_*.py'];code=main()
    print('M03A2_OFFLINE_BARRIER_VIOLATIONS:',len(VIOLATIONS))
    raise SystemExit(code if not VIOLATIONS else 1)
