"""Add V3.8 to the unchanged historical guard; resolve aliases to private paths."""
import os
from pathlib import Path
import sys

from core_v34_offline_check import main

VIOLATIONS = []

def private_path(value):
    if not isinstance(value, (str, bytes, os.PathLike)):
        return False
    path = Path(os.path.abspath(os.fsdecode(value)))
    if any(p.casefold().rstrip(' .') == '.local' for p in path.parts):
        return True
    return any(p.casefold().rstrip(' .') == '.local' for p in path.resolve().parts)


def guard(event, args):
    blocked = event.startswith('socket.') or event in ('subprocess.Popen', 'os.system', 'os.startfile')
    if event in ('open', 'os.listdir', 'os.scandir', 'os.chdir', 'os.remove', 'os.mkdir', 'os.rmdir') and args:
        blocked |= private_path(args[0])
    if event in ('os.rename', 'os.link', 'os.symlink'):
        blocked |= any(private_path(v) for v in args[:2])
    if blocked:
        VIOLATIONS.append(event)
        raise AssertionError('V38_OFFLINE_BARRIER')


if __name__ == '__main__':
    sys.dont_write_bytecode = True
    sys.addaudithook(guard)
    if len(sys.argv) == 1:
        sys.argv.extend(['test_core_v3_*.py', 'test_forex_research_*.py', 'test_ai_strategy_contracts.py',
                         'test_core_v34_*.py', 'test_core_v35_*.py', 'test_core_v36_*.py',
                         'test_core_v37_*.py', 'test_core_v38_*.py'])
    code = main()
    print('V38_OFFLINE_BARRIER_VIOLATIONS:', len(VIOLATIONS))
    sys.exit(code if not VIOLATIONS else 1)
