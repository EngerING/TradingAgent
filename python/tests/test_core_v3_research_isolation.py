"""Runtime isolation and simultaneous complete cycles."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import os
import sys
import tempfile
from threading import Barrier
import unittest
from unittest.mock import patch

from test_core_v3_research_contracts import AT, budget, request
from trading_agent.core_v3.contracts import ContractError
from trading_agent.core_v3.research_contracts import ResearchResult, ResearchState
from trading_agent.core_v3.research_designer import SimulatedDesigner
from trading_agent.core_v3.research_journal import ResearchJournal
from trading_agent.core_v3.research_runner import run


class ResearchIsolationTests(unittest.TestCase):
    def test_complete_cycles_are_offline_and_only_connect_to_their_temporary_sqlite(self):
        enabled = [True]
        private = os.path.normcase(os.path.abspath('.local'))
        with tempfile.TemporaryDirectory() as root:
            allowed = os.path.normcase(str(Path(root).resolve())) + os.sep
            def guard(event, args):
                if not enabled[0]:
                    return
                if event in ('socket.connect', 'socket.bind', 'socket.getaddrinfo', 'subprocess.Popen'):
                    raise AssertionError('OFFLINE_RUNTIME_VIOLATION')
                if event == 'sqlite3.connect':
                    path = os.path.normcase(os.path.abspath(args[0]))
                    if not path.startswith(allowed):
                        raise AssertionError('SQLITE_OUTSIDE_TEST_ROOT')
                if event in ('open', 'os.listdir', 'os.scandir') and args and isinstance(args[0], (str, bytes, os.PathLike)):
                    path = os.path.normcase(os.path.abspath(os.fsdecode(args[0])))
                    if path == private or path.startswith(private + os.sep):
                        raise AssertionError('PRIVATE_DATA_ACCESS')
            sys.addaudithook(guard)
            try:
                with ResearchJournal(root, budget()) as journal:
                    result = run(journal, request(), SimulatedDesigner(), clock=lambda: AT)
                    self.assertEqual(ResearchState.CANDIDATE_RECORDED, result.state)
                    self.assertEqual(result, ResearchResult.from_json(result.to_json()))
                    for field in ('execution_authority', 'paper_execution_eligible', 'live_enabled', 'statistically_validated'):
                        data = result.to_dict()
                        data[field] = True
                        with self.subTest(field=field), self.assertRaises(ContractError):
                            ResearchResult.from_dict(data)
            finally:
                enabled[0] = False

    def test_simultaneous_complete_runs_consume_once_for_duplicate_or_competing_ids(self):
        for duplicate in (False, True):
            with self.subTest(duplicate=duplicate), tempfile.TemporaryDirectory() as root:
                with ResearchJournal(root, budget(requests=1)):
                    pass
                ready, invocations = Barrier(2), []
                original = SimulatedDesigner.propose
                def propose(designer, design):
                    invocations.append(design.request.request_id)
                    return original(designer, design)
                def worker(index):
                    with ResearchJournal(root, budget(requests=1)) as journal:
                        ready.wait(timeout=5)
                        return run(journal, request(name='same' if duplicate else 'id-' + str(index)),
                                   SimulatedDesigner(), clock=lambda: AT)
                with patch.object(SimulatedDesigner, 'propose', autospec=True, side_effect=propose):
                    with ThreadPoolExecutor(max_workers=2) as pool:
                        results = list(pool.map(worker, range(2)))
                self.assertEqual(1, len(invocations))
                self.assertTrue(any(r.state is ResearchState.CANDIDATE_RECORDED for r in results))
                with ResearchJournal(root, budget(requests=1)) as journal:
                    self.assertEqual(1, journal.budget_status().consumed_requests)
                    self.assertEqual(1, sum(e['state'] == 'CANDIDATE_RECORDED' for e in journal.history()))

    def test_subclasses_and_callables_cannot_be_used_as_designer_plugins(self):
        class Extended(SimulatedDesigner):
            pass
        with tempfile.TemporaryDirectory() as root, ResearchJournal(root, budget()) as journal:
            for designer in (Extended(), lambda req: 'data'):
                with self.assertRaisesRegex(ContractError, 'OFFLINE_DESIGNER_REQUIRED'):
                    run(journal, request(), designer, clock=lambda: AT)
            self.assertEqual(1, len(journal.history()))
