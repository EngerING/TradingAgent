"""Append-only local research ledger, independent of all existing stores."""
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3

from ..ai_strategy_researcher.strategy_bundle_v2 import validate_bundle
from .economics import assess, canonical, digest, identifier, instant, require

FOLDER = 'artifacts/research/forex-economic-phase1'
REJECTIONS = frozenset(('PREFLIGHT_BLOCKED', 'POSTFLIGHT_BLOCKED',
                        'PROPOSAL_INVALID', 'SIMULATED_PROVIDER_FAILED'))
AUTHORITY = dict(execution_authority=False, paper_execution_eligible=False,
                 live_enabled=False, trading_decision='NO_TRADE')


class Journal:
    def __init__(self, root):
        root = Path(root).resolve()
        self.path = root / FOLDER / 'journal.sqlite3'
        require(self.path.resolve() == self.path, 'JOURNAL_PATH_REDIRECTED')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        try:
            self.db.executescript('''
                CREATE TABLE IF NOT EXISTS events(
                    sequence INTEGER PRIMARY KEY,
                    request_id TEXT NOT NULL,
                    phase TEXT NOT NULL CHECK(phase IN ('RESERVED','FINISHED')),
                    input_sha256 TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    previous_sha256 TEXT NOT NULL,
                    event_sha256 TEXT NOT NULL,
                    UNIQUE(request_id,phase));
                CREATE TRIGGER IF NOT EXISTS immutable_events_update
                    BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT,'IMMUTABLE_EVENTS'); END;
                CREATE TRIGGER IF NOT EXISTS immutable_events_delete
                    BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT,'IMMUTABLE_EVENTS'); END;
            ''')
            self.history()
        except BaseException:
            self.db.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.db.close()

    @contextmanager
    def _transaction(self):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            yield
            self.db.execute('COMMIT')
        except BaseException:
            self.db.execute('ROLLBACK')
            raise

    def history(self):
        rows = self.db.execute('SELECT * FROM events ORDER BY sequence LIMIT 10001').fetchall()
        require(len(rows) <= 10000, 'JOURNAL_RECORD_LIMIT')
        previous, result, pending = '', [], {}
        for row in rows:
            material = {key: row[key] for key in ('sequence', 'request_id', 'phase',
                                                  'input_sha256', 'payload', 'previous_sha256')}
            require(row['sequence'] == len(result) + 1 and row['previous_sha256'] == previous
                    and row['event_sha256'] == digest(material), 'JOURNAL_INTEGRITY')
            try:
                payload = json.loads(row['payload'])
                require(canonical(payload).decode() == row['payload'], 'JOURNAL_INTEGRITY')
            except (ValueError, TypeError):
                raise ValueError('JOURNAL_INTEGRITY') from None
            request = row['request_id']
            if row['phase'] == 'RESERVED':
                require(request not in pending, 'JOURNAL_INTEGRITY')
                pending[request] = row['input_sha256']
            else:
                require(pending.get(request) == row['input_sha256'], 'JOURNAL_INTEGRITY')
                pending[request] = None
            result.append(dict(row, value=payload))
            previous = row['event_sha256']
        return result

    def _append(self, request_id, phase, input_hash, value, history):
        payload = canonical(value).decode()
        require(len(payload) <= 100000, 'JOURNAL_PAYLOAD_LIMIT')
        require(len(history) < 10000, 'JOURNAL_RECORD_LIMIT')
        material = dict(sequence=len(history) + 1, request_id=request_id, phase=phase,
                        input_sha256=input_hash, payload=payload,
                        previous_sha256=history[-1]['event_sha256'] if history else '')
        self.db.execute('INSERT INTO events VALUES(?,?,?,?,?,?,?)',
                        (*material.values(), digest(material)))

    def reserve(self, request_id, inputs):
        identifier(request_id)
        encoded = canonical(inputs)
        require(len(encoded) <= 30000, 'RESEARCH_INPUT_LIMIT')
        input_hash = digest(inputs)
        with self._transaction():
            rows = self.history()
            prior = [row for row in rows if row['request_id'] == request_id]
            if prior:
                require(prior[0]['input_sha256'] == input_hash, 'IDEMPOTENCY_CONFLICT')
                require(prior[-1]['phase'] == 'FINISHED', 'REQUEST_PENDING_REVIEW')
                return prior[-1]['value']
            # Reserve only hashes: invalid input or raw model output is never archived.
            self._append(request_id, 'RESERVED', input_hash,
                         dict(provider='SIMULATED_NO_MODEL', api_cost_usd='0'), rows)
        return None

    def finish(self, request_id, inputs, *, reason=None, bundle=None, now=None):
        identifier(request_id)
        require((reason in REJECTIONS and bundle is None) or (reason is None and bundle is not None),
                'TERMINAL_STATE_INVALID')
        assessment = (assess(inputs['context'], inputs['plan'], now=now)
                      if 'context' in inputs and 'plan' in inputs else None)
        candidate = None
        if bundle is not None:
            # A caller cannot bypass the gate by calling this persistence boundary directly.
            require(assessment is not None and assessment['admitted'], 'ECONOMIC_GATE_REQUIRED')
            bundle = validate_bundle(bundle)
            require(bundle['candidate']['direction'] == inputs['plan']['direction']
                    and bundle['candidate']['risk_profile'] == inputs['risk_profile'], 'DESIGN_BINDING_MISMATCH')
            candidate = dict(schema='FOREX_ECONOMIC_CANDIDATE_V1', bundle=bundle,
                             economic_context=inputs['context'], economic_plan=inputs['plan'],
                             assessment=assessment, assessed_at_utc=instant(now).isoformat(),
                             scope='ECONOMIC_SCENARIO_ONLY',
                             exit_model='UNIMPLEMENTED_RESEARCH_BRACKET_SCENARIO',
                             statistically_validated=False, **AUTHORITY)
            candidate['record_sha256'] = digest(candidate)
        result = dict(request_id=request_id, state='ACCEPTED_FOR_RESEARCH' if candidate else 'REJECTED',
                      reason=reason, assessment=assessment, candidate=candidate,
                      provider='SIMULATED_NO_MODEL', input_tokens=0, output_tokens=0,
                      api_cost_usd='0', **AUTHORITY)
        with self._transaction():
            rows = self.history()
            prior = [row for row in rows if row['request_id'] == request_id]
            require(len(prior) == 1 and prior[0]['phase'] == 'RESERVED', 'REQUEST_NOT_PENDING')
            require(prior[0]['input_sha256'] == digest(inputs), 'IDEMPOTENCY_CONFLICT')
            self._append(request_id, 'FINISHED', digest(inputs), result, rows)
        return json.loads(canonical(result))
