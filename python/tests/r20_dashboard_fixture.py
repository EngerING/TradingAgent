"""Synthetic browser integration evidence, restricted to postgres on test55432.

Never invokes Reader/run or contacts IBKR. Not an operational experiment.
"""
import json
import os
import sys
from pathlib import Path
from uuid import uuid4

from trading_agent.aggressive_growth import configuration
from trading_agent.aggressive_growth_runner import Experiment, Journal, engine_hashes


def main():
    connection = dict(part.split('=', 1) for part in os.environ['TRADING_LAB_DB'].split(';') if part)
    if any(connection.get(key) != value for key, value in
           {'Host': '127.0.0.1', 'Port': '55432', 'Username': 'trading_test', 'Database': 'postgres'}.items()):
        raise PermissionError('SYNTHETIC_FIXTURE_REQUIRES_TEST55432')
    root = Path(__file__).resolve().parents[2]
    action = sys.argv[1]
    identifier = sys.argv[2] if len(sys.argv) > 2 else 'aggressive-r20-' + uuid4().hex
    experiment = Experiment(Journal(root, identifier, configuration='R20'))
    if action == 'prepare':
        experiment.prepare(configuration(root), engine_hashes(root))
    elif action == 'stop':
        experiment.stop()
    else:
        raise ValueError('TEST_ACTION_REQUIRED')
    print(json.dumps(dict(source='SYNTHETIC_TEST_55432_ONLY', experiment=identifier,
                         revision=experiment.revision, hash=experiment.head,
                         status=experiment.state['status'],
                         equity=experiment.state['portfolios']['R20']['equity'])))


if __name__ == '__main__':
    main()
