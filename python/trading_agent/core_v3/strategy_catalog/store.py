"""Private catalog persistence. Every mutation folds a verified bounded event log."""
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
from pathlib import Path
import sqlite3

from ..contracts import ContractError, canonical_bytes, content_hash, instant, require, shape, strict_json, utc
from .contracts import Action, CatalogCheck, CatalogOutcome, CatalogRef, CatalogRequest, CatalogVersion, SourceProof, State, TERMINAL, semantic_hash
from .research_link import check_binding


MAX_OPERATIONS, MAX_EVENTS = 128, 2049
GENESIS_AT, ZERO = '1970-01-01T00:00:00.000000+00:00', '0' * 64


@dataclass(slots=True)
class _View:
    command: CatalogRequest
    sequence: int
    at: object
    state: State = State.REQUESTED
    phase: State = State.REQUESTED
    proof: SourceProof | None = None
    check: CatalogCheck | None = None
    target: CatalogRef | None = None
    reason: str = 'REQUEST_RECEIVED'


def _family(strategy):
    return strategy.instrument, strategy.timeframe, strategy.scenario.direction


def _check(command, proof, inputs, now, versions):
    checked = check_binding(command, proof, inputs, now=now)
    existing = versions.get((command.catalog_id, command.version))
    if existing is not None and utc(now) < existing.recorded_at:
        return CatalogCheck(inputs, utc(now), False, 'CATALOG_VERSION_FROM_FUTURE', None)
    return checked


def _choice(command, proof, versions, at):
    key = command.catalog_id, command.version
    existing = versions.get(key)
    if existing is not None:
        old = existing.registration
        if command.strategy != old.strategy or command.parent_sha256 != old.parent_sha256:
            return State.REJECTED, None, 'VERSION_CONTENT_CONFLICT'
        if command.action is Action.REVALIDATE:
            if command.source_id != old.source_id or command.research_request_id != old.research_request_id or proof != existing.source:
                return State.REJECTED, None, 'REVALIDATION_SOURCE_MISMATCH'
            return State.RECORDED, existing, 'REVALIDATION_PENDING'
        return State.DUPLICATE, existing, 'EXACT_VERSION_DUPLICATE'
    if command.action is Action.REVALIDATE:
        return State.REJECTED, None, 'VERSION_NOT_FOUND'
    lineage = [v for (catalog_id, number), v in versions.items() if catalog_id == command.catalog_id]
    if lineage:
        latest = max(lineage, key=lambda v: v.registration.version)
        if at < latest.recorded_at:
            return State.REJECTED, None, 'CATALOG_PARENT_FROM_FUTURE'
        if command.version != latest.registration.version + 1 or command.parent_sha256 != latest.record_sha256:
            return State.REJECTED, None, 'PARENT_VERSION_CONFLICT'
        if _family(command.strategy) != _family(latest.registration.strategy):
            return State.REJECTED, None, 'CATALOG_FAMILY_MISMATCH'
        if semantic_hash(command.strategy) == latest.semantic_sha256 and proof.result == latest.source.result:
            return State.DUPLICATE, latest, 'UNCHANGED_REVISION_DUPLICATE'
    elif command.version != 1 or command.parent_sha256 is not None:
        return State.REJECTED, None, 'PARENT_VERSION_CONFLICT'
    fingerprint = semantic_hash(command.strategy)
    duplicates = [v for v in versions.values() if v.semantic_sha256 == fingerprint
                  and v.registration.catalog_id != command.catalog_id]
    if duplicates:
        return State.DUPLICATE, duplicates[0], 'SEMANTIC_DUPLICATE'
    return State.RECORDED, None, 'AWAITING_RECONCILIATION'


class _Store:
    def __init__(self, root):
        raw = Path(root).absolute()
        require('.local' not in (v.casefold() for v in raw.parts), 'PRIVATE_ROOT_FORBIDDEN')
        require(not any(p.is_symlink() or p.is_junction() for p in (raw, *raw.parents)), 'CATALOG_PATH_REDIRECTED')
        root = raw.resolve()
        require('.local' not in (v.casefold() for v in root.parts), 'PRIVATE_ROOT_FORBIDDEN')
        self.path = root / 'artifacts/research/core-v3-5/strategy-catalog.sqlite3'
        require(self.path.resolve() == self.path, 'CATALOG_PATH_REDIRECTED')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        require(self.path.resolve() == self.path, 'CATALOG_PATH_REDIRECTED')
        self.db = sqlite3.connect(self.path, timeout=2, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        try:
            self.db.execute('PRAGMA synchronous=FULL')
            self.db.execute('PRAGMA trusted_schema=OFF')
            with self._transaction():
                tables = {r[0] for r in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if not tables:
                    self.db.execute('CREATE TABLE events(sequence INTEGER PRIMARY KEY, operation_id TEXT NOT NULL, state TEXT NOT NULL, at TEXT NOT NULL, payload TEXT NOT NULL, previous_sha256 TEXT NOT NULL, event_sha256 TEXT NOT NULL)')
                    self.db.execute('CREATE TABLE head(singleton INTEGER PRIMARY KEY CHECK(singleton=1), sequence INTEGER NOT NULL, event_sha256 TEXT NOT NULL)')
                    for action in ('UPDATE', 'DELETE'):
                        self.db.execute(f"CREATE TRIGGER immutable_events_{action.lower()} BEFORE {action} ON events BEGIN SELECT RAISE(ABORT,'IMMUTABLE_EVENTS'); END")
                    self.db.execute('INSERT INTO head VALUES(1,0,?)', (ZERO,))
                    self._insert('', 'INITIALIZED', GENESIS_AT, {'engine': 'CORE_V35_CATALOG_V1'})
                require(not tables or tables == {'events', 'head'}, 'FOREIGN_CATALOG_FORBIDDEN')
                self._load()
        except BaseException:
            self.db.close()
            raise

    @contextmanager
    def _transaction(self):
        try:
            self.db.execute('BEGIN IMMEDIATE')
            yield
            self.db.execute('COMMIT')
        except BaseException as exc:
            if self.db.in_transaction:
                self.db.execute('ROLLBACK')
            if isinstance(exc, sqlite3.Error):
                raise ContractError('CATALOG_PERSISTENCE_FAILED') from None
            raise

    @staticmethod
    def _hash(sequence, operation, state, at, payload, previous):
        return content_hash(dict(engine='CORE_V35_CATALOG_V1', sequence=sequence, operation=operation,
            state=state, at=at, payload_sha256=hashlib.sha256(payload.encode('utf-8')).hexdigest(), previous=previous))

    def _insert(self, operation, state, now, payload):
        head = self.db.execute('SELECT sequence,event_sha256 FROM head WHERE singleton=1').fetchone()
        require(head is not None and head[0] < MAX_EVENTS, 'CATALOG_EVENT_LIMIT')
        at = now if type(now) is str else utc(now).isoformat(timespec='microseconds')
        raw = canonical_bytes(payload).decode()
        digest = self._hash(head[0] + 1, operation, state, at, raw, head[1])
        self.db.execute('INSERT INTO events VALUES(?,?,?,?,?,?,?)', (head[0] + 1, operation, state, at, raw, head[1], digest))
        self.db.execute('UPDATE head SET sequence=?,event_sha256=? WHERE singleton=1', (head[0] + 1, digest))

    @staticmethod
    def _outcome(view):
        return CatalogOutcome(view.command.operation_id, content_hash(view.command), view.state,
                              view.reason, view.at, view.target, view.check)

    def _apply(self, views, versions, row, payload):
        state, at, operation = State(row['state']), instant(row['at']), row['operation_id']
        if state is State.REQUESTED:
            cmd = CatalogRequest.from_dict(payload)
            require(cmd.to_dict() == payload and cmd.operation_id == operation and operation not in views
                    and len(views) < MAX_OPERATIONS
                    and all(v.command.idempotency_key != cmd.idempotency_key for v in views.values()), 'CATALOG_INTEGRITY')
            views[operation] = _View(cmd, row['sequence'], at)
            return
        require(operation in views, 'CATALOG_INTEGRITY')
        view = views[operation]
        require(view.state not in TERMINAL and at >= view.at, 'CATALOG_INTEGRITY')
        cmd = view.command
        if state in (State.PREPARED, State.INVALIDATED):
            if state is State.INVALIDATED and set(payload) == {'reason'}:
                require(view.proof is not None and payload['reason'] == 'RESEARCH_PREFIX_CHANGED', 'CATALOG_INTEGRITY')
                view.check, view.reason = None, payload['reason']
                view.state, view.sequence, view.at = state, row['sequence'], at
                return
            shape(payload, ('proof', 'check'))
            proof, checked = SourceProof.from_dict(payload['proof']), CatalogCheck.from_dict(payload['check'])
            require(view.proof is None or view.proof == proof, 'CATALOG_INTEGRITY')
            require(checked == _check(cmd, proof, checked.inputs, at, versions), 'CATALOG_INTEGRITY')
            require((state is State.PREPARED) == checked.valid, 'CATALOG_INTEGRITY')
            require(state is State.INVALIDATED or view.phase in (State.REQUESTED, State.PREPARED), 'CATALOG_INTEGRITY')
            view.proof, view.check, view.reason = proof, checked, checked.reason
            if state is State.INVALIDATED and cmd.action is Action.REVALIDATE:
                existing = versions.get((cmd.catalog_id, cmd.version))
                if existing is not None:
                    view.target = CatalogRef.of(existing)
            if state is State.PREPARED:
                view.phase = State.PREPARED
        elif state is State.RECORDED:
            require(view.phase is State.PREPARED and view.check.valid, 'CATALOG_INTEGRITY')
            checked = _check(cmd, view.proof, view.check.inputs, at, versions)
            require(checked.valid, 'CATALOG_INTEGRITY')
            expected_state, existing, reason = _choice(cmd, view.proof, versions, at)
            require(expected_state is State.RECORDED, 'CATALOG_INTEGRITY')
            version = CatalogVersion.from_dict(payload)
            if cmd.action is Action.REVALIDATE:
                require(existing == version, 'CATALOG_INTEGRITY')
            else:
                require(version == CatalogVersion(cmd, view.proof, semantic_hash(cmd.strategy), at), 'CATALOG_INTEGRITY')
                versions[(cmd.catalog_id, cmd.version)] = version
            view.target, view.check, view.phase, view.reason = CatalogRef.of(version), checked, State.RECORDED, reason
        elif state is State.VALIDATED:
            require(view.phase is State.RECORDED and view.target is not None, 'CATALOG_INTEGRITY')
            checked = CatalogCheck.from_dict(payload)
            require(checked.valid and checked == _check(cmd, view.proof, checked.inputs, at, versions), 'CATALOG_INTEGRITY')
            view.check, view.reason = checked, 'VALIDATED_FOR_BOUND_CONTEXT'
        elif state is State.DUPLICATE:
            require(view.phase is State.PREPARED, 'CATALOG_INTEGRITY')
            decision, existing, reason = _choice(cmd, view.proof, versions, at)
            require(decision is State.DUPLICATE and CatalogRef.from_dict(payload) == CatalogRef.of(existing), 'CATALOG_INTEGRITY')
            view.target, view.reason = CatalogRef.of(existing), reason
        elif state in (State.REJECTED, State.RECOVERY_REQUIRED):
            shape(payload, ('reason',))
            require(payload['reason'] in {
                'RESEARCH_NOT_RECORDED', 'RESEARCH_SOURCE_REJECTED', 'RESEARCH_SOURCE_UNAVAILABLE',
                'RESEARCH_PENDING', 'RESEARCH_NOT_FOUND', 'RESEARCH_PREFIX_CHANGED',
                'VERSION_CONTENT_CONFLICT', 'PARENT_VERSION_CONFLICT', 'CATALOG_FAMILY_MISMATCH',
                'VERSION_NOT_FOUND', 'REVALIDATION_SOURCE_MISMATCH', 'CATALOG_PARENT_FROM_FUTURE'}, 'CATALOG_INTEGRITY')
            if state is State.REJECTED and view.phase is State.PREPARED:
                decision, unused, reason = _choice(cmd, view.proof, versions, at)
                require(decision is State.REJECTED and reason == payload['reason'], 'CATALOG_INTEGRITY')
            require(state is State.RECOVERY_REQUIRED or view.phase is not State.RECORDED, 'CATALOG_INTEGRITY')
            view.reason = payload['reason']
        else:
            raise ContractError('CATALOG_INTEGRITY')
        view.state, view.sequence, view.at = state, row['sequence'], at
        self._outcome(view)

    def _load(self):
        try:
            triggers = {r[0] for r in self.db.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
            require({'immutable_events_update', 'immutable_events_delete'} <= triggers, 'CATALOG_INTEGRITY')
            rows = self.db.execute('SELECT * FROM events ORDER BY sequence LIMIT ?', (MAX_EVENTS + 1,)).fetchall()
            heads = self.db.execute('SELECT * FROM head').fetchall()
            require(1 <= len(rows) <= MAX_EVENTS and len(heads) == 1, 'CATALOG_INTEGRITY')
            previous, views, versions = ZERO, {}, {}
            for sequence, row in enumerate(rows, 1):
                payload = strict_json(row['payload'])
                require(row['sequence'] == sequence and row['previous_sha256'] == previous
                        and canonical_bytes(payload).decode() == row['payload']
                        and row['event_sha256'] == self._hash(sequence, row['operation_id'], row['state'],
                            row['at'], row['payload'], previous), 'CATALOG_INTEGRITY')
                if sequence == 1:
                    require(row['operation_id'] == '' and row['state'] == 'INITIALIZED' and row['at'] == GENESIS_AT
                            and payload == {'engine': 'CORE_V35_CATALOG_V1'}, 'CATALOG_INTEGRITY')
                else:
                    self._apply(views, versions, row, payload)
                previous = row['event_sha256']
            require(heads[0]['singleton'] == 1 and heads[0]['sequence'] == len(rows)
                    and heads[0]['event_sha256'] == previous, 'CATALOG_INTEGRITY')
            return views, versions, rows
        except (ContractError, ValueError, TypeError, KeyError, OverflowError):
            raise ContractError('CATALOG_INTEGRITY') from None

    def snapshot(self):
        with self._transaction():
            return self._load()

    def check(self, view, proof, inputs, *, now):
        with self._transaction():
            versions = self._load()[1]
            return _check(view.command, proof, inputs, now, versions)

    def claim(self, command, *, now):
        require(type(command) is CatalogRequest, 'CATALOG_REQUEST_REQUIRED')
        with self._transaction():
            views, versions, rows = self._load()
            prior = [v for v in views.values() if v.command.operation_id == command.operation_id
                     or v.command.idempotency_key == command.idempotency_key]
            if prior:
                require(len(prior) == 1 and prior[0].command == command, 'CATALOG_IDEMPOTENCY_CONFLICT')
                return prior[0], False
            require(len(views) < MAX_OPERATIONS, 'CATALOG_OPERATION_LIMIT')
            self._insert(command.operation_id, State.REQUESTED.value, now, command.to_dict())
            return self._load()[0][command.operation_id], True

    def event(self, view, state, payload, *, now):
        with self._transaction():
            views, versions, rows = self._load()
            current = views[view.command.operation_id]
            require(current.sequence == view.sequence, 'CATALOG_CONCURRENT_CHANGE')
            require(current.state not in TERMINAL and utc(now) >= current.at, 'CATALOG_STATE_CONFLICT')
            self._insert(current.command.operation_id, state.value, now, payload)
            return self._load()[0][current.command.operation_id]

    def record(self, view, *, now):
        with self._transaction():
            views, versions, rows = self._load()
            current = views[view.command.operation_id]
            require(current.sequence == view.sequence and current.phase is State.PREPARED
                    and current.state not in TERMINAL, 'CATALOG_CONCURRENT_CHANGE')
            checked = _check(current.command, current.proof, current.check.inputs, now, versions)
            if not checked.valid:
                state, payload = State.INVALIDATED, dict(proof=current.proof.to_dict(), check=checked.to_dict())
            else:
                state, existing, reason = _choice(current.command, current.proof, versions, utc(now))
                if state is State.REJECTED:
                    payload = {'reason': reason}
                elif state is State.DUPLICATE:
                    payload = CatalogRef.of(existing).to_dict()
                else:
                    version = (existing if current.command.action is Action.REVALIDATE else
                               CatalogVersion(current.command, current.proof, semantic_hash(current.command.strategy), utc(now)))
                    payload = version.to_dict()
            self._insert(current.command.operation_id, state.value, now, payload)
            return self._load()[0][current.command.operation_id]
