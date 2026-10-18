"""One durable simulated research cycle. Real providers are deliberately absent."""
from typing import Callable
from datetime import datetime

from .contracts import require
from .research_contracts import DesignRequest, ResearchRequest, ResearchResult, ResearchState
from .research_designer import OfflineInputSource, SimulatedDesigner
from .research_journal import ResearchJournal


def run(journal: ResearchJournal, request: ResearchRequest, designer: SimulatedDesigner, *,
        clock: Callable[[], datetime], source: OfflineInputSource | None = None) -> ResearchResult:
    require(type(journal) is ResearchJournal and type(request) is ResearchRequest, 'RESEARCH_CONTRACT_REQUIRED')
    require(type(designer) is SimulatedDesigner, 'OFFLINE_DESIGNER_REQUIRED')
    require(source is None or type(source) is OfflineInputSource, 'OFFLINE_INPUT_SOURCE_REQUIRED')
    result, owned = journal.receive(request, now=clock())
    if not owned:
        return result
    result = journal.admit(request.request_id, now=clock())
    if result.state is not ResearchState.BUDGET_RESERVED:
        return result
    result = journal.start(request.request_id, now=clock())
    if result.state is not ResearchState.DESIGNING:
        return result
    try:
        raw = designer.propose(DesignRequest(request, result.preflight))
    except Exception:
        # A missing response is not evidence that an invocation consumed nothing.
        return journal.fail(request.request_id, reason='DESIGNER_FAILED', now=clock())
    result = journal.record_reply(request.request_id, raw, now=clock())
    if result.receipt.proposal is None:
        return journal.fail(request.request_id, reason='PROPOSAL_INVALID', now=clock())
    try:
        refreshed = (OfflineInputSource(request.inputs) if source is None else source).capture()
    except Exception:
        return journal.fail(request.request_id, reason='INPUT_REFRESH_FAILED', now=clock())
    journal.begin_postflight(request.request_id, refreshed, now=clock())
    return journal.finish(request.request_id, now=clock())
