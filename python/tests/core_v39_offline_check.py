"""345 accepted regressions plus V3.9 under the unchanged historical guards."""
import sys
from core_v38_offline_check import guard, VIOLATIONS
from core_v34_offline_check import main

if __name__ == '__main__':
    sys.dont_write_bytecode = True
    sys.addaudithook(guard)
    if len(sys.argv) == 1:
        sys.argv.extend(['test_core_v3_*.py', 'test_forex_research_*.py', 'test_ai_strategy_contracts.py',
                         'test_core_v34_*.py', 'test_core_v35_*.py', 'test_core_v36_*.py',
                         'test_core_v37_*.py', 'test_core_v38_*.py', 'test_core_v39_*.py'])
    code = main()
    print('V39_OFFLINE_BARRIER_VIOLATIONS:', len(VIOLATIONS))
    sys.exit(code if not VIOLATIONS else 1)
