"""Static dependency evidence complements the runner's runtime audit hooks."""
import ast
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
import sys
import unittest

from trading_agent.market_analyst.contracts import Policy
from trading_agent.market_analyst.evaluator import evaluate
from test_market_analyst_evaluation import BASE, assessment, fixture

PACKAGE = Path(__file__).resolve().parents[1] / 'trading_agent' / 'market_analyst'


class IsolationTests(unittest.TestCase):
    def test_source_dependency_allowlist_has_no_operational_import_or_io(self):
        standard = {'dataclasses', 'datetime', 'decimal', 'hashlib', 'json', 'math',
                    're', 'types', 'typing', 'statistics'}
        local = {'serialization', 'contracts', 'fixtures', 'evaluator'}
        for path in sorted(PACKAGE.glob('*.py')):
            with self.subTest(file=path.name):
                tree = ast.parse(path.read_text(encoding='utf-8'))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        self.assertTrue(all(n.name in standard for n in node.names))
                    if isinstance(node, ast.ImportFrom):
                        allowed = standard if node.level == 0 else local if node.level == 1 else {
                            'market', 'research_indicators'} if node.level == 2 else set()
                        self.assertIn(node.module, allowed)
                    if isinstance(node, ast.Call):
                        name = (node.func.id if isinstance(node.func, ast.Name) else node.func.attr
                                if isinstance(node.func, ast.Attribute) else '')
                        self.assertNotIn(name, {'open', 'exec', 'eval', '__import__', 'connect',
                                                'send', 'placeOrder', 'request', 'now', 'today',
                                                'read_text', 'write_text', 'load', 'dump'})
        for relative in ('market.py', 'research_indicators.py'):
            tree = ast.parse((PACKAGE.parent / relative).read_text(encoding='utf-8'))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    self.assertTrue(all(n.name in standard for n in node.names))
                if isinstance(node, ast.ImportFrom):
                    self.assertIn(node.module, standard | {'market'})

    def test_all_statuses_have_no_operational_authority(self):
        data = fixture()
        results = [assessment(data), assessment(fixture(1), cutoff=BASE + timedelta(hours=1)),
                   assessment(data, policy=Policy(max_age_seconds=0),
                              cutoff=data.bars[-1].available_at.replace(microsecond=1)),
                   evaluate(None, cutoff=BASE), evaluate({}, cutoff=BASE),
                   assessment(replace(data, bars=data.bars[1:]))]
        self.assertEqual({r.status for r in results}, {
            'COMPLETE', 'INSUFFICIENT_DATA', 'STALE_DATA', 'SOURCE_UNAVAILABLE',
            'UNVERIFIED_PROVENANCE', 'VALIDATION_ERROR'})
        for result in results:
            self.assertEqual(result.authority.decision, 'NO_TRADE')
            self.assertFalse(any((result.authority.execution_authorized,
                                  result.authority.paper_eligible, result.authority.live_approved)))

    def test_new_package_does_not_load_core_brokers_or_model_providers(self):
        assessment()
        forbidden = ('trading_agent.core_v3', 'trading_agent.kronos',
                     'trading_agent.r20_market', 'trading_agent.tws', 'trading_agent.broker',
                     'openai', 'ibapi', 'torch', 'transformers', 'huggingface_hub')
        self.assertFalse([name for name in sys.modules if any(
            name == prefix or name.startswith(prefix + '.') for prefix in forbidden)])


if __name__ == '__main__':
    unittest.main()
