"""Read-only catalog boundary. Hash pins identify content; they do not authenticate a host."""
from ..contracts import content_hash, require, utc
from ..research_journal import ResearchJournal
from ..strategy_catalog.contracts import CatalogRef, CatalogRequest, State
from ..strategy_catalog.research_link import check_binding, verify
from ..strategy_catalog.service import Catalog
from .contracts import BacktestEvidence, BacktestPolicy, BacktestRequest, SyntheticDataset


def _read(catalog, journal, catalog_id, number, operation_id, cutoff):
    require(type(catalog) is Catalog and type(journal) is ResearchJournal, 'BACKTEST_VERIFIED_READERS_REQUIRED')
    rows = catalog.history()  # V3.5 verifies the entire bounded log on every read.
    version = catalog.version(catalog_id, number)
    reference = CatalogRef.of(version)
    outcome = catalog.outcome(operation_id)
    require(outcome.state is State.VALIDATED and outcome.target == reference and outcome.at == cutoff,
            'BACKTEST_VALIDATED_CATALOG_REQUIRED')
    commands, latest = {}, {}
    for row in rows[1:]:
        operation = row['operation_id']
        if row['state'] == State.REQUESTED.value:
            cmd = CatalogRequest.from_json(row['payload'])
            if (cmd.catalog_id, cmd.version) == (catalog_id, number):
                commands[operation] = cmd
        if operation in commands:
            latest[operation] = row
    relevant = [r for r in latest.values() if r['state'] not in (State.REJECTED.value, State.DUPLICATE.value)]
    require(relevant and max(relevant, key=lambda r: r['sequence'])['state'] == State.VALIDATED.value,
            'BACKTEST_CATALOG_INVALIDATED_OR_PENDING')
    require(version.recorded_at <= cutoff, 'BACKTEST_VERSION_FROM_FUTURE')
    verify(journal, version.source)
    checked = check_binding(version.registration, version.source, version.source.request.inputs, now=cutoff)
    require(checked.valid and outcome.check == checked, 'BACKTEST_ECONOMIC_EVIDENCE_MISMATCH')
    return version, checked, rows


def prepare(request_id, catalog, journal, catalog_id, number, validation_operation_id,
            dataset: SyntheticDataset, policy: BacktestPolicy, *, research_cutoff) -> BacktestRequest:
    """Create a request from actual verified records, never from a supplied approval dictionary."""
    require(type(dataset) is SyntheticDataset and type(policy) is BacktestPolicy, 'BACKTEST_TYPES_REQUIRED')
    cutoff = utc(research_cutoff)
    version, checked, rows = _read(catalog, journal, catalog_id, number, validation_operation_id, cutoff)
    result = BacktestRequest(request_id, CatalogRef.of(version), validation_operation_id, cutoff,
        rows[-1]['sequence'], rows[-1]['event_sha256'], content_hash(version.source.request),
        content_hash(version.registration.strategy.scenario), content_hash(checked.postflight),
        content_hash(dataset), content_hash(policy))
    load(result, catalog, journal, dataset, policy)
    return result


def load(request: BacktestRequest, catalog, journal, dataset: SyntheticDataset, policy: BacktestPolicy):
    require(type(request) is BacktestRequest and type(dataset) is SyntheticDataset
            and type(policy) is BacktestPolicy, 'BACKTEST_TYPES_REQUIRED')
    ref = request.catalog_ref
    version, checked, rows = _read(catalog, journal, ref.catalog_id, ref.version,
                                  request.validation_operation_id, request.research_cutoff)
    require(len(rows) >= request.catalog_sequence
            and rows[request.catalog_sequence-1]['event_sha256'] == request.catalog_sha256,
            'BACKTEST_CATALOG_PREFIX_CHANGED')
    strategy = version.registration.strategy
    require(CatalogRef.of(version) == ref and content_hash(version.source.request) == request.research_request_sha256
            and content_hash(strategy.scenario) == request.scenario_sha256
            and content_hash(checked.postflight) == request.economic_sha256, 'BACKTEST_SOURCE_HASH_MISMATCH')
    require(content_hash(dataset) == request.dataset_sha256 and content_hash(policy) == request.policy_sha256,
            'BACKTEST_INPUT_HASH_MISMATCH')
    require(dataset.instrument == strategy.instrument and dataset.timeframe is strategy.timeframe,
            'BACKTEST_DATASET_BINDING_MISMATCH')
    instrument = version.source.request.inputs.context.market.instrument
    for bar in dataset.bars:
        for price in (bar.open, bar.high, bar.low, bar.close):
            instrument.check_terms(strategy.scenario.quantity, price)
    evidence = BacktestEvidence(request, content_hash(strategy), strategy.instrument, strategy.timeframe,
                                version.source.prefix_sequence, version.source.prefix_sha256)
    return version, evidence
