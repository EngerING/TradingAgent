"""Run the unchanged 187 regressions and V3.5 under the established offline barriers."""
import sys
from core_v34_offline_check import main


if __name__ == '__main__':
    if len(sys.argv) == 1:
        sys.argv.extend(['test_core_v3_*.py', 'test_forex_research_*.py', 'test_ai_strategy_contracts.py',
                         'test_core_v34_*.py', 'test_core_v35_*.py'])
    sys.exit(main())
