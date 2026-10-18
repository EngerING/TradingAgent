"""V3.3 isolated SQLite event ledger. No mutable candidate or budget cache."""
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Context, Decimal, localcontext
import hashlib
from pathlib import Path
import sqlite3

from .contracts import ContractError, Money, canonical_bytes, content_hash, identifier, instant, require, strict_json, utc
from .economic_contracts import EconomicResult, EconomicStatus
from .economics import postflight, preflight
from .research_contracts import (
    BudgetPolicy, BudgetStatus, DesignReceipt, DesignRequest, InstrumentIdentity, ResearchCharge,
    ResearchInputs, ResearchRequest, ResearchResult, ResearchState, TERMINAL,
)
from .research_designer import proposal_for, receipt


MAX_REQUESTS, MAX_EVENTS = 256, 2049
ZERO_HASH = '0' * 64
S = ResearchState
ALLOWED = {
    S.RECEIVED: frozenset((S.VALIDATION_REJECTED, S.ECONOMIC_BLOCKED, S.BUDGET_BLOCKED, S.BUDGET_RESERVED, S.INTERRUPTED)),
    S.BUDGET_RESERVED: frozenset((S.DESIGNING, S.FAILED, S.INTERRUPTED)),
    S.DESIGNING: frozenset((S.DESIGN_RECEIVED, S.FAILED, S.INTERRUPTED)),
    S.DESIGN_RECEIVED: frozenset((S.POSTFLIGHT_PENDING, S.FAILED, S.INTERRUPTED)),
    S.POSTFLIGHT_PENDING: frozenset((S.CANDIDATE_RECORDED, S.FAILED, S.INTERRUPTED)),
}


@dataclass(slots=True)
class _View:
    request: ResearchRequest
    state: ResearchState
    at: object
    preflight: EconomicResult | None = None
    receipt: DesignReceipt | None = None
    inputs: ResearchInputs | None = None
    reserved: bool = False
    settled: bool = False
    result: ResearchResult | None = None


class ResearchJournal:
    """One connection per worker; all public operations verify a locked snapshot."""
    def __init__(self, root, policy: BudgetPolicy):
        require(type(policy) is BudgetPolicy, 'RESEARCH_BUDGET_REQUIRED')
        raw = Path(root).absolute()
        require('.local' not in (part.casefold() for part in raw.parts), 'PRIVATE_ROOT_FORBIDDEN')
        require(not any(p.is_symlink() or p.is_junction() for p in (raw, *raw.parents)), 'JOURNAL_PATH_REDIRECTED')
        resolved = raw.resolve()
        require('.local' not in (part.casefold() for part in resolved.parts), 'PRIVATE_ROOT_FORBIDDEN')
        self.path = resolved / 'artifacts/research/core-v3-3/journal.sqlite3'
        require(self.path.resolve() == self.path, 'JOURNAL_PATH_REDIRECTED')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        require(self.path.resolve() == self.path, 'JOURNAL_PATH_REDIRECTED')
        self.policy = policy
        self.db = sqlite3.connect(self.path, timeout=2, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        try:
            self.db.execute('PRAGMA synchronous=FULL')
            self.db.execute('PRAGMA trusted_schema=OFF')
            with self._transaction():
                tables = {r[0] for r in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if not tables:
                    self.db.execute('CREATE TABLE events(sequence INTEGER PRIMARY KEY, request_id TEXT NOT NULL, state TEXT NOT NULL, at TEXT NOT NULL, payload TEXT NOT NULL, previous_sha256 TEXT NOT NULL, event_sha256 TEXT NOT NULL, UNIQUE(request_id,state))')
                    self.db.execute('CREATE TABLE head(singleton INTEGER PRIMARY KEY CHECK(singleton=1), sequence INTEGER NOT NULL, event_sha256 TEXT NOT NULL)')
                    for action in ('UPDATE', 'DELETE'):
                        self.db.execute(f"CREATE TRIGGER immutable_events_{action.lower()} BEFORE {action} ON events BEGIN SELECT RAISE(ABORT,'IMMUTABLE_EVENTS'); END")
                    self.db.execute('INSERT INTO head VALUES(1,0,?)', (ZERO_HASH,))
                    self._append('', 'INITIALIZED', '2026-01-01T00:00:00+00:00', policy.to_dict())
                require(tables == set() or tables == {'events', 'head'}, 'FOREIGN_JOURNAL_FORBIDDEN')
                self._load()
        except BaseException:
            self.db.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.db.close()

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
                raise ContractError('RESEARCH_PERSISTENCE_FAILED') from None
            raise

    @staticmethod
    def _event_hash(sequence, request_id, state, at, payload, previous):
        return content_hash(dict(engine='CORE_V3_3_V1', sequence=sequence, request_id=request_id,
            state=state, at=at, payload_sha256=hashlib.sha256(payload.encode('utf-8')).hexdigest(), previous=previous))

    def _append(self, request_id, state, at, payload):
        head = self.db.execute('SELECT sequence,event_sha256 FROM head WHERE singleton=1').fetchone()
        require(head is not None and head[0] < MAX_EVENTS, 'RESEARCH_EVENT_LIMIT')
        encoded = canonical_bytes(payload).decode('utf-8')
        stamp = at if type(at) is str else utc(at).isoformat(timespec='microseconds')
        digest = self._event_hash(head[0] + 1, request_id, state, stamp, encoded, head[1])
        self.db.execute('INSERT INTO events VALUES(?,?,?,?,?,?,?)',
            (head[0] + 1, request_id, state, stamp, encoded, head[1], digest))
        self.db.execute('UPDATE head SET sequence=?,event_sha256=? WHERE singleton=1', (head[0] + 1, digest))

    def _budget(self, views):
        with localcontext(Context(prec=160)):
            reserved = [v.request.allowance for v in views.values() if v.reserved]
            count, used = len(reserved), sum(v.settled for v in views.values())
            tokens = sum(a.tokens for a in reserved)
            cost = sum((a.max_cost.amount for a in reserved), Decimal(0))
            require(count + used <= self.policy.max_requests and tokens <= self.policy.max_tokens
                    and cost <= self.policy.max_cost.amount, 'RESEARCH_BUDGET_INTEGRITY')
            return BudgetStatus(self.policy, count, used, self.policy.max_requests - count - used,
                tokens, 0, self.policy.max_tokens - tokens, Money(cost, 'USD'), Money(Decimal(0), 'USD'),
                Money(self.policy.max_cost.amount - cost, 'USD'))

    def _can_reserve(self, views, allowance):
        balance = self._budget(views)
        return (balance.remaining_requests >= 1 and balance.remaining_tokens >= allowance.tokens
                and balance.remaining_cost.amount >= allowance.max_cost.amount)

    @staticmethod
    def _charge(view, *, release=False):
        held = view.reserved and not release
        return ResearchCharge(int(held), int(view.settled), view.request.allowance.tokens if held else 0,
            view.request.allowance.max_cost if held else Money(Decimal(0), 'USD'))

    def _result(self, view, state=None, *, at=None, reason='PENDING', before=None, after=None):
        state = view.state if state is None else state
        release = state in (S.INTERRUPTED, S.FAILED) and view.state is S.BUDGET_RESERVED
        digest = content_hash(view.request)
        return ResearchResult(view.request.request_id, digest, 'op-' + digest, view.request.instrument,
            state, reason, view.at if at is None else at, self._charge(view, release=release),
            view.preflight if before is None else before, view.receipt, after)

    def _terminal(self, view, state, now, views, reason=None):
        req, before, after = view.request, view.preflight, None
        if state is S.VALIDATION_REJECTED:
            require(req.instrument != InstrumentIdentity.of(req.inputs.context.market.instrument), 'JOURNAL_INTEGRITY')
            reason = 'INSTRUMENT_IDENTITY_MISMATCH'
        elif state in (S.ECONOMIC_BLOCKED, S.BUDGET_BLOCKED):
            require(req.instrument == InstrumentIdentity.of(req.inputs.context.market.instrument), 'JOURNAL_INTEGRITY')
            before = preflight(req.inputs.context, req.inputs.policy, now=now)
            if state is S.ECONOMIC_BLOCKED:
                require(before.status is not EconomicStatus.FEASIBLE, 'JOURNAL_INTEGRITY')
                reason = 'PREFLIGHT_BLOCKED'
            else:
                require(before.status is EconomicStatus.FEASIBLE and not self._can_reserve(views, req.allowance),
                        'JOURNAL_INTEGRITY')
                reason = 'RESEARCH_BUDGET_EXHAUSTED'
        elif state is S.INTERRUPTED:
            reason = 'REVIEW_REQUIRED'
        elif state is S.FAILED and view.state is S.BUDGET_RESERVED:
            after = postflight(req.inputs.context, req.inputs.policy, before.witness, before, now=now)
            require(after.status is not EconomicStatus.FEASIBLE, 'JOURNAL_INTEGRITY')
            reason = 'PREDESIGN_EVIDENCE_BLOCKED'
        elif view.state is S.POSTFLIGHT_PENDING:
            require(view.receipt.proposal == proposal_for(DesignRequest(req, before)), 'JOURNAL_INTEGRITY')
            after = postflight(view.inputs.context, view.inputs.policy, view.receipt.proposal.scenario, before, now=now)
            require((state is S.CANDIDATE_RECORDED) == (after.status is EconomicStatus.FEASIBLE), 'JOURNAL_INTEGRITY')
            reason = 'RESEARCH_RECORDED' if state is S.CANDIDATE_RECORDED else 'POSTFLIGHT_BLOCKED'
        elif state is S.FAILED:
            require((view.state is S.DESIGNING and reason == 'DESIGNER_FAILED') or
                    (view.state is S.DESIGN_RECEIVED and reason == (
                        'PROPOSAL_INVALID' if view.receipt.proposal is None else 'INPUT_REFRESH_FAILED')),
                    'JOURNAL_INTEGRITY')
        else:
            raise ContractError('JOURNAL_INTEGRITY')
        return self._result(view, state, at=now, reason=reason, before=before, after=after)

    def _apply(self, views, row, payload):
        request_id, now = row['request_id'], instant(row['at'])
        state = S(row['state'])
        if state is S.RECEIVED:
            req = ResearchRequest.from_dict(payload)
            require(request_id == req.request_id and request_id not in views and len(views) < MAX_REQUESTS
                    and all(v.request.idempotency_key != req.idempotency_key for v in views.values()), 'JOURNAL_INTEGRITY')
            require(req.to_dict() == payload, 'JOURNAL_INTEGRITY')
            views[request_id] = _View(req, state, now)
            return
        require(request_id in views, 'JOURNAL_INTEGRITY')
        view = views[request_id]
        require(state in ALLOWED.get(view.state, ()) and now >= view.at, 'JOURNAL_INTEGRITY')
        if state is S.BUDGET_RESERVED:
            before = EconomicResult.from_dict(payload)
            require(view.request.instrument == InstrumentIdentity.of(view.request.inputs.context.market.instrument)
                    and before == preflight(view.request.inputs.context, view.request.inputs.policy, now=now)
                    and before.status is EconomicStatus.FEASIBLE
                    and self._can_reserve(views, view.request.allowance), 'JOURNAL_INTEGRITY')
            view.preflight, view.reserved = before, True
        elif state is S.DESIGNING:
            require(payload == {}, 'JOURNAL_INTEGRITY')
        elif state is S.DESIGN_RECEIVED:
            received = DesignReceipt.from_dict(payload)
            if received.proposal is not None:
                require(received.proposal == proposal_for(DesignRequest(view.request, view.preflight)), 'JOURNAL_INTEGRITY')
            view.receipt, view.reserved, view.settled = received, False, True
        elif state is S.POSTFLIGHT_PENDING:
            require(view.receipt.proposal is not None, 'JOURNAL_INTEGRITY')
            view.inputs = ResearchInputs.from_dict(payload)
        else:
            result = ResearchResult.from_dict(payload)
            require(result == self._terminal(view, state, now, views, result.reason), 'JOURNAL_INTEGRITY')
            if state in (S.INTERRUPTED, S.FAILED) and view.state is S.BUDGET_RESERVED:
                view.reserved = False
            view.result, view.preflight = result, result.preflight
        view.state, view.at = state, now

    def _load(self):
        try:
            triggers = {r[0] for r in self.db.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
            require({'immutable_events_update', 'immutable_events_delete'} <= triggers, 'JOURNAL_INTEGRITY')
            rows = self.db.execute('SELECT * FROM events ORDER BY sequence LIMIT ?', (MAX_EVENTS + 1,)).fetchall()
            heads = self.db.execute('SELECT * FROM head').fetchall()
            require(1 <= len(rows) <= MAX_EVENTS and len(heads) == 1, 'JOURNAL_INTEGRITY')
            previous, views = ZERO_HASH, {}
            for sequence, row in enumerate(rows, 1):
                payload = strict_json(row['payload'])
                require(row['sequence'] == sequence and row['previous_sha256'] == previous
                        and canonical_bytes(payload).decode() == row['payload']
                        and row['event_sha256'] == self._event_hash(sequence, row['request_id'], row['state'],
                            row['at'], row['payload'], previous), 'JOURNAL_INTEGRITY')
                if sequence == 1:
                    require(row['request_id'] == '' and row['state'] == 'INITIALIZED', 'JOURNAL_INTEGRITY')
                    require(BudgetPolicy.from_dict(payload) == self.policy, 'BUDGET_POLICY_CONFLICT')
                else:
                    self._apply(views, row, payload)
                previous = row['event_sha256']
            require(heads[0]['singleton'] == 1 and heads[0]['sequence'] == len(rows)
                    and heads[0]['event_sha256'] == previous, 'JOURNAL_INTEGRITY')
            self._budget(views)
            return views, rows
        except ContractError as exc:
            if str(exc) == 'BUDGET_POLICY_CONFLICT':
                raise
            raise ContractError('JOURNAL_INTEGRITY') from None
        except (ValueError, TypeError, KeyError, OverflowError):
            raise ContractError('JOURNAL_INTEGRITY') from None

    def _get(self, views, request_id):
        identifier(request_id)
        require(request_id in views, 'RESEARCH_REQUEST_UNKNOWN')
        return views[request_id]

    def _write(self, view, state, payload, now):
        require(state in ALLOWED.get(view.state, ()) and utc(now) >= view.at, 'RESEARCH_STATE_CONFLICT')
        self._append(view.request.request_id, state.value, now, payload)
        views, _ = self._load()
        return self._get(views, view.request.request_id)

    def _read_result(self, view):
        return view.result if view.result is not None else self._result(view)

    def history(self):
        with self._transaction():
            return tuple(dict(row) for row in self._load()[1])

    def budget_status(self):
        with self._transaction():
            return self._budget(self._load()[0])

    def read(self, request_id):
        with self._transaction():
            return self._read_result(self._get(self._load()[0], request_id))

    def receive(self, request: ResearchRequest, *, now):
        require(type(request) is ResearchRequest, 'RESEARCH_REQUEST_REQUIRED')
        with self._transaction():
            views, _ = self._load()
            prior = [v for v in views.values() if v.request.request_id == request.request_id
                     or v.request.idempotency_key == request.idempotency_key]
            if prior:
                require(len(prior) == 1 and prior[0].request == request, 'IDEMPOTENCY_CONFLICT')
                return self._read_result(prior[0]), False
            require(len(views) < MAX_REQUESTS, 'RESEARCH_REQUEST_LIMIT')
            self._append(request.request_id, S.RECEIVED.value, now, request.to_dict())
            view = self._get(self._load()[0], request.request_id)
            return self._result(view), True

    def admit(self, request_id, *, now):
        with self._transaction():
            views, _ = self._load()
            view = self._get(views, request_id)
            require(view.state is S.RECEIVED, 'RESEARCH_STATE_CONFLICT')
            req = view.request
            if req.instrument != InstrumentIdentity.of(req.inputs.context.market.instrument):
                state = S.VALIDATION_REJECTED
            else:
                before = preflight(req.inputs.context, req.inputs.policy, now=now)
                state = (S.ECONOMIC_BLOCKED if before.status is not EconomicStatus.FEASIBLE else
                         S.BUDGET_RESERVED if self._can_reserve(views, req.allowance) else S.BUDGET_BLOCKED)
            payload = before.to_dict() if state is S.BUDGET_RESERVED else self._terminal(view, state, utc(now), views).to_dict()
            return self._read_result(self._write(view, state, payload, now))

    def start(self, request_id, *, now):
        with self._transaction():
            views, _ = self._load()
            view = self._get(views, request_id)
            require(view.state is S.BUDGET_RESERVED, 'RESEARCH_STATE_CONFLICT')
            req = view.request
            checked = postflight(req.inputs.context, req.inputs.policy, view.preflight.witness, view.preflight, now=now)
            if checked.status is not EconomicStatus.FEASIBLE:
                result = self._terminal(view, S.FAILED, utc(now), views)
                return self._read_result(self._write(view, S.FAILED, result.to_dict(), now))
            return self._read_result(self._write(view, S.DESIGNING, {}, now))

    def record_reply(self, request_id, raw, *, now):
        with self._transaction():
            view = self._get(self._load()[0], request_id)
            require(view.state is S.DESIGNING, 'RESEARCH_STATE_CONFLICT')
            received = receipt(raw, DesignRequest(view.request, view.preflight))
            return self._read_result(self._write(view, S.DESIGN_RECEIVED, received.to_dict(), now))

    def begin_postflight(self, request_id, inputs: ResearchInputs, *, now):
        require(type(inputs) is ResearchInputs, 'OFFLINE_INPUTS_REQUIRED')
        with self._transaction():
            view = self._get(self._load()[0], request_id)
            require(view.state is S.DESIGN_RECEIVED, 'RESEARCH_STATE_CONFLICT')
            return self._read_result(self._write(view, S.POSTFLIGHT_PENDING, inputs.to_dict(), now))

    def finish(self, request_id, *, now):
        with self._transaction():
            views, _ = self._load()
            view = self._get(views, request_id)
            require(view.state is S.POSTFLIGHT_PENDING, 'RESEARCH_STATE_CONFLICT')
            checked = postflight(view.inputs.context, view.inputs.policy, view.receipt.proposal.scenario,
                                 view.preflight, now=now)
            state = S.CANDIDATE_RECORDED if checked.status is EconomicStatus.FEASIBLE else S.FAILED
            result = self._terminal(view, state, utc(now), views)
            return self._read_result(self._write(view, state, result.to_dict(), now))

    def fail(self, request_id, *, reason, now):
        with self._transaction():
            views, _ = self._load()
            view = self._get(views, request_id)
            result = self._terminal(view, S.FAILED, utc(now), views, reason)
            return self._read_result(self._write(view, S.FAILED, result.to_dict(), now))

    def recover(self, request_id, *, now):
        with self._transaction():
            views, _ = self._load()
            view = self._get(views, request_id)
            if view.state in TERMINAL:
                return view.result
            result = self._terminal(view, S.INTERRUPTED, utc(now), views)
            return self._read_result(self._write(view, S.INTERRUPTED, result.to_dict(), now))
