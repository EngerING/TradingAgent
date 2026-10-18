"""Read-only V3.3 evidence bridge and pure V3.4/V3.2 checks."""
from ..contracts import ContractError, content_hash, require, utc
from ..research_contracts import BudgetPolicy, InstrumentIdentity, ResearchInputs, ResearchRequest, ResearchResult, TERMINAL
from ..research_journal import ResearchJournal
from ..strategy_v34.validation import validate
from .contracts import CatalogCheck, CatalogRequest, SourceProof


class SourcePending(ContractError):
    pass


class SourceUnavailable(ContractError):
    pass


class SourceChanged(ContractError):
    pass


def _history(journal):
    require(type(journal) is ResearchJournal, 'VERIFIED_RESEARCH_JOURNAL_REQUIRED')
    try:
        return journal.history()
    except ContractError:
        raise SourceUnavailable('RESEARCH_SOURCE_UNAVAILABLE') from None


def capture(journal: ResearchJournal, command: CatalogRequest) -> SourceProof:
    rows = _history(journal)
    selected = [row for row in rows if row['request_id'] == command.research_request_id]
    if not selected:
        raise SourcePending('RESEARCH_NOT_FOUND')
    last = selected[-1]
    if last['state'] != 'CANDIDATE_RECORDED':
        if last['state'] in {state.value for state in TERMINAL}:
            raise ContractError('RESEARCH_NOT_RECORDED')
        raise SourcePending('RESEARCH_PENDING')
    first, head = selected[0], rows[-1]
    return SourceProof(command.source_id, ResearchRequest.from_json(first['payload']),
        ResearchResult.from_json(last['payload']), BudgetPolicy.from_json(rows[0]['payload']),
        first['sequence'], first['event_sha256'], last['sequence'], last['event_sha256'],
        head['sequence'], head['event_sha256'])


def verify(journal: ResearchJournal, proof: SourceProof):
    rows = _history(journal)
    if len(rows) < proof.prefix_sequence:
        raise SourceChanged('RESEARCH_PREFIX_CHANGED')
    received, terminal = rows[proof.received_sequence - 1], rows[proof.terminal_sequence - 1]
    matches = (rows[proof.prefix_sequence - 1]['event_sha256'] == proof.prefix_sha256
        and received['event_sha256'] == proof.received_sha256 and terminal['event_sha256'] == proof.terminal_sha256
        and ResearchRequest.from_json(received['payload']) == proof.request
        and ResearchResult.from_json(terminal['payload']) == proof.result
        and BudgetPolicy.from_json(rows[0]['payload']) == proof.budget)
    if not matches:
        raise SourceChanged('RESEARCH_PREFIX_CHANGED')


def check_binding(command: CatalogRequest, proof: SourceProof, inputs: ResearchInputs, *, now) -> CatalogCheck:
    require(type(command) is CatalogRequest and type(proof) is SourceProof and type(inputs) is ResearchInputs,
            'CATALOG_CHECK_TYPES_REQUIRED')
    now, strategy = utc(now), command.strategy
    def invalid(reason):
        return CatalogCheck(inputs, now, False, reason, None)
    if command.source_id != proof.source_id or command.research_request_id != proof.request.request_id:
        return invalid('RESEARCH_IDENTITY_MISMATCH')
    if strategy.request_sha256 != content_hash(proof.request):
        return invalid('RESEARCH_REQUEST_MISMATCH')
    if strategy.instrument != proof.request.instrument:
        return invalid('STRATEGY_INSTRUMENT_MISMATCH')
    if strategy.timeframe is not command.timeframe:
        return invalid('STRATEGY_TIMEFRAME_MISMATCH')
    if InstrumentIdentity.of(inputs.context.market.instrument) != strategy.instrument:
        return invalid('INSTRUMENT_SPECIFICATION_CHANGED')
    if inputs.context != proof.request.inputs.context:
        return invalid('ECONOMIC_CONTEXT_CHANGED')
    if inputs.policy != proof.request.inputs.policy:
        return invalid('ECONOMIC_POLICY_CHANGED')
    if now < proof.result.at:
        return invalid('RESEARCH_RESULT_FROM_FUTURE')
    if strategy.scenario != proof.result.preflight.witness or strategy.scenario != proof.result.postflight.witness:
        return invalid('RESEARCH_GEOMETRY_MISMATCH')
    try:
        after = validate(strategy, proof.request, command.timeframe, now=now)
    except ContractError:
        return invalid('ECONOMIC_EVIDENCE_REJECTED')
    return CatalogCheck(inputs, now, True, 'BOUND_ECONOMIC_RESEARCH', after)
