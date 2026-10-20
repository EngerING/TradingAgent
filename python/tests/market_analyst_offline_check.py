"""New tests with unchanged historical guards plus no writes, DBs or providers.

Run from root: .venv/Scripts/python.exe -B python/tests/market_analyst_offline_check.py
This is test-process evidence, not a production Python sandbox.
"""
import os
import sys
import tempfile

from core_v38_offline_check import VIOLATIONS as HISTORICAL_VIOLATIONS, guard as historical_guard
from core_v34_offline_check import main

VIOLATIONS = []
ALLOWED_PRODUCT_MODULES = ('trading_agent', 'trading_agent.market',
                           'trading_agent.research_indicators', 'trading_agent.market_analyst')


def analyst_guard(event, args):
    blocked = event.startswith(('socket.', 'sqlite3.')) or event in (
        'subprocess.Popen', 'os.system', 'os.startfile', 'os.mkdir', 'os.remove',
        'os.rmdir', 'os.rename', 'os.link', 'os.symlink')
    if event == 'open':
        path, mode, flags = args
        blocked |= (isinstance(mode, str) and any(c in mode for c in 'wax+'))
        blocked |= bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
        if isinstance(path, (str, bytes, os.PathLike)):
            name = os.fsdecode(path).lower()
            blocked |= name.endswith(('.sqlite', '.sqlite3', '.db', '.db3'))
    if event == 'import' and args:
        name = args[0]
        if name.startswith('trading_agent'):
            blocked |= not (name in ALLOWED_PRODUCT_MODULES
                            or name.startswith('trading_agent.market_analyst.'))
        blocked |= name.split('.')[0] in ('openai', 'ibapi', 'torch', 'transformers',
                                          'huggingface_hub', 'psycopg', 'psycopg2')
    if blocked:
        VIOLATIONS.append(event)
        raise AssertionError('MARKET_ANALYST_OFFLINE_BARRIER')


if __name__ == '__main__':
    sys.dont_write_bytecode = True
    sys.addaudithook(historical_guard)
    # unittest's historical runner resolves the OS temp directory. Python probes
    # it once with a temporary file; finish harness setup before the no-write gate.
    tempfile.gettempdir()
    sys.addaudithook(analyst_guard)
    if len(sys.argv) == 1:
        sys.argv.append('test_market_analyst_*.py')
    code = main()
    print('MARKET_ANALYST_BARRIER_VIOLATIONS:', len(VIOLATIONS))
    print('HISTORICAL_BARRIER_VIOLATIONS:', len(HISTORICAL_VIOLATIONS))
    sys.exit(code if not VIOLATIONS and not HISTORICAL_VIOLATIONS else 1)
