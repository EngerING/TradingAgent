"""Read-check-record-reconcile protocol; never calls a research provider or budget mutation."""
from ..contracts import ContractError, identifier, require, utc
from ..research_contracts import ResearchInputs
from ..research_journal import ResearchJournal
from ..strategy_v34.signals import CandleSeries, evaluate
from .contracts import Action, CatalogRequest, State, TERMINAL
from .research_link import SourceChanged, SourcePending, SourceUnavailable, capture, verify
from .store import _Store


class Catalog:
    def __init__(self, root):
        self._store = _Store(root)

    @property
    def path(self):
        return self._store.path

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._store.db.close()

    def history(self):
        return tuple(dict(row) for row in self._store.snapshot()[2])

    def versions(self):
        values = self._store.snapshot()[1]
        return tuple(values[key] for key in sorted(values))

    def version(self, catalog_id, number):
        identifier(catalog_id)
        require(type(number) is int and 1 <= number <= 1024, 'CATALOG_VERSION_INVALID')
        versions = self._store.snapshot()[1]
        require((catalog_id, number) in versions, 'VERSION_NOT_FOUND')
        return versions[catalog_id, number]

    def outcome(self, operation_id):
        identifier(operation_id)
        views = self._store.snapshot()[0]
        require(operation_id in views, 'CATALOG_OPERATION_UNKNOWN')
        return self._store._outcome(views[operation_id])

    def _mark(self, view, state, reason, now):
        if view.state is state and view.reason == reason:
            return self._store._outcome(view)
        updated = self._store.event(view, state, {'reason': reason}, now=now)
        return self._store._outcome(updated)

    def _advance(self, view, journal, inputs, now):
        try:
            if view.proof is None:
                if view.command.action is Action.REVALIDATE:
                    versions = self._store.snapshot()[1]
                    version = versions.get((view.command.catalog_id, view.command.version))
                    if version is None:
                        return self._mark(view, State.REJECTED, 'VERSION_NOT_FOUND', now)
                    proof = version.source
                else:
                    proof = capture(journal, view.command)
            else:
                proof = view.proof
            verify(journal, proof)
            checked = self._store.check(view, proof, inputs, now=now)
            if not checked.valid:
                view = self._store.event(view, State.INVALIDATED,
                    dict(proof=proof.to_dict(), check=checked.to_dict()), now=now)
                return self._store._outcome(view)
            if view.phase is not State.RECORDED:
                view = self._store.event(view, State.PREPARED,
                    dict(proof=proof.to_dict(), check=checked.to_dict()), now=now)
                view = self._store.record(view, now=now)
                if view.state in TERMINAL:
                    return self._store._outcome(view)
            # This read is after the independent catalog commit, with neither file locked together.
            verify(journal, proof)
            checked = self._store.check(view, proof, inputs, now=now)
            if checked.valid:
                view = self._store.event(view, State.VALIDATED, checked.to_dict(), now=now)
            else:
                view = self._store.event(view, State.INVALIDATED,
                    dict(proof=proof.to_dict(), check=checked.to_dict()), now=now)
            return self._store._outcome(view)
        except SourcePending as exc:
            reason = 'RESEARCH_NOT_FOUND' if str(exc) == 'RESEARCH_NOT_FOUND' else 'RESEARCH_PENDING'
            return self._mark(view, State.RECOVERY_REQUIRED, reason, now)
        except SourceUnavailable:
            return self._mark(view, State.RECOVERY_REQUIRED, 'RESEARCH_SOURCE_UNAVAILABLE', now)
        except SourceChanged:
            state = State.INVALIDATED if view.proof is not None else State.RECOVERY_REQUIRED
            return self._mark(view, state, 'RESEARCH_PREFIX_CHANGED', now)
        except ContractError as exc:
            if str(exc) == 'CATALOG_CONCURRENT_CHANGE':
                return self.outcome(view.command.operation_id)
            if str(exc) == 'RESEARCH_NOT_RECORDED':
                return self._mark(view, State.REJECTED, 'RESEARCH_NOT_RECORDED', now)
            raise

    def register(self, command: CatalogRequest, journal: ResearchJournal, inputs: ResearchInputs, *, now):
        require(type(command) is CatalogRequest and type(inputs) is ResearchInputs, 'CATALOG_TYPES_REQUIRED')
        require(type(journal) is ResearchJournal, 'VERIFIED_RESEARCH_JOURNAL_REQUIRED')
        now = utc(now)
        view, owned = self._store.claim(command, now=now)
        if owned:
            return self._advance(view, journal, inputs, now)
        if view.proof is not None:
            verify(journal, view.proof)
        return self._store._outcome(view)

    def reconcile(self, operation_id, journal: ResearchJournal, inputs: ResearchInputs, *, now):
        identifier(operation_id)
        require(type(journal) is ResearchJournal and type(inputs) is ResearchInputs, 'CATALOG_TYPES_REQUIRED')
        views = self._store.snapshot()[0]
        require(operation_id in views, 'CATALOG_OPERATION_UNKNOWN')
        view = views[operation_id]
        if view.state in TERMINAL:
            if view.proof is not None:
                verify(journal, view.proof)
            return self._store._outcome(view)
        return self._advance(view, journal, inputs, utc(now))

    def diagnose(self, command: CatalogRequest, journal: ResearchJournal, inputs: ResearchInputs,
                 candles: CandleSeries, *, now):
        require(type(command) is CatalogRequest and command.action is Action.REVALIDATE, 'REVALIDATION_REQUIRED')
        result = self.register(command, journal, inputs, now=now)
        require(result.state is State.VALIDATED and result.at == utc(now), 'CURRENT_CATALOG_VALIDATION_REQUIRED')
        version = self.version(result.target.catalog_id, result.target.version)
        verify(journal, version.source)
        return evaluate(version.registration.strategy, version.source.request, candles, as_of=now)
