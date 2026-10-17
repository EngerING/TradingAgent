"""Fail-closed binding of the local equivalence report to the implementation it tested."""
import hashlib
import json
from pathlib import Path

FILES=('src/TradingAgent.Core/ResearchExitSemantics.cs','src/TradingAgent.Core/ResearchSimulation.cs',
       'python/trading_agent/paper_strategy.py','python/trading_agent/paper_lab.py',
       'python/trading_agent/paper_lab_runner.py','tests/TradingAgent.Tests/ResearchExitEquivalenceTests.cs',
       'python/tests/test_paper_exact_exits.py')

def hashes(root):
    return {name:hashlib.sha256((Path(root)/name).read_bytes()).hexdigest() for name in FILES}

def verified_equivalence(root=None):
    root=Path(root) if root else Path(__file__).resolve().parents[2]
    try:
        evidence=json.loads((root/'artifacts/test-results/research-exit-equivalence.json').read_text(encoding='utf-8-sig'))
        return evidence.get('status')=='PASSED' and evidence.get('execution_equivalence_verified') is True and evidence.get('semantics')=='research-d-exits-v1' and evidence.get('hashes')==hashes(root)
    except (OSError,ValueError,TypeError):return False
