"""Run the 150 accepted regressions plus V3.4 under explicit offline barriers.

From the repository root: .venv/Scripts/python.exe -B python/tests/core_v34_offline_check.py
Optional arguments replace the default unittest filename patterns.
"""
from pathlib import Path
import os
import sys
import tempfile
import unittest


def main():
    repo = Path(__file__).resolve().parents[2]
    sys.dont_write_bytecode = True
    sys.path[:0] = [str(repo / 'python'), str(repo / 'python/tests')]
    private = os.path.normcase(str(repo / '.local'))
    temp = os.path.normcase(str(Path(tempfile.gettempdir()).resolve())) + os.sep
    violations = []

    def guard(event, args):
        blocked = event.startswith('socket.') or event in ('subprocess.Popen', 'os.system', 'os.startfile')
        if event in ('open', 'os.listdir', 'os.scandir') and args and isinstance(args[0], (str, bytes, os.PathLike)):
            path = os.path.normcase(os.path.abspath(os.fsdecode(args[0])))
            blocked |= path == private or path.startswith(private + os.sep)
        if event == 'sqlite3.connect':
            path = os.path.normcase(str(Path(args[0]).resolve()))
            blocked |= not path.startswith(temp)
        if blocked:
            violations.append(event)
            raise AssertionError('OFFLINE_VERIFICATION_BARRIER')

    sys.addaudithook(guard)
    suite = unittest.TestSuite()
    patterns = sys.argv[1:] or ['test_core_v3_*.py', 'test_forex_research_*.py',
                               'test_ai_strategy_contracts.py', 'test_core_v34_*.py']
    for pattern in patterns:
        suite.addTests(unittest.TestLoader().discover(str(repo / 'python/tests'), pattern=pattern))
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    print('OFFLINE_BARRIER_VIOLATIONS:', len(violations))
    return 0 if result.wasSuccessful() and not violations else 1


if __name__ == '__main__':
    sys.exit(main())
