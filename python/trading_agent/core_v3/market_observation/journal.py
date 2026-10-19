"""Own bounded SQLite ledger; validate and commit original before publication."""
from dataclasses import dataclass
from pathlib import Path
import sqlite3

from ..contracts import require, identifier, content_hash, ContractError
from ..historical_ingestion.files import safe_path
from .contracts import CapturePolicy, RawEvent, ValidatedEvent, Origin, SessionKind
from .validation import State, step


@dataclass(frozen=True, slots=True)
class Entry:
    sequence: int
    previous_sha256: str
    sha256: str
    value: ValidatedEvent


@dataclass(frozen=True, slots=True)
class Checkpoint:
    metadata_sha256: str
    sequence: int
    sha256: str


_TRIGGERS = {
    'events_update': "CREATE TRIGGER events_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT,'immutable'); END",
    'events_delete': "CREATE TRIGGER events_delete BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT,'immutable'); END",
    'meta_update': "CREATE TRIGGER meta_update BEFORE UPDATE ON meta BEGIN SELECT RAISE(ABORT,'immutable'); END",
    'meta_delete': "CREATE TRIGGER meta_delete BEFORE DELETE ON meta BEGIN SELECT RAISE(ABORT,'immutable'); END",
}


class Journal:
    def __init__(self, path, policy, session_id, origin, session_kind, *, checkpoint=None):
        require(type(policy) is CapturePolicy and type(origin) is Origin and type(session_kind) is SessionKind, 'OBS_JOURNAL_TYPE')
        identifier(session_id)
        self.path = Path(safe_path(path))
        self.policy, self.session_id, self.origin, self.session_kind = policy, session_id, origin, session_kind
        self.metadata = content_hash({'policy': policy.to_dict(), 'session_id': session_id,
                                      'origin': origin.value, 'session_kind': session_kind.value})
        self.anchor = checkpoint
        self.db = None
        self._parent = self._identity(self.path.parent)
        self._storage()
        existed = self.path.exists()
        try:
            self.db = sqlite3.connect(self.path, timeout=2, isolation_level=None)
            self.db.execute('PRAGMA journal_mode=DELETE')
            self.db.execute('PRAGMA synchronous=FULL')
            self.db.execute('PRAGMA temp_store=MEMORY')
            self.db.execute('PRAGMA trusted_schema=OFF')
            self.db.execute('PRAGMA page_size=4096')
            self.db.execute('PRAGMA max_page_count='+str((policy.max_disk_bytes-65536)//(3*4096)))
            self.db.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 131072)
            if not existed:
                self.db.execute('BEGIN IMMEDIATE')
                self.db.execute('CREATE TABLE meta(digest TEXT NOT NULL)')
                self.db.execute('INSERT INTO meta VALUES(?)', (self.metadata,))
                self.db.execute('CREATE TABLE events(seq INTEGER PRIMARY KEY, connection TEXT NOT NULL, received_seq INTEGER NOT NULL, previous TEXT NOT NULL, digest TEXT NOT NULL, document TEXT NOT NULL, UNIQUE(connection,received_seq))')
                self.db.execute('CREATE TABLE head(seq INTEGER NOT NULL,digest TEXT NOT NULL)')
                self.db.execute('INSERT INTO head VALUES(0,?)', (self.metadata,))
                for sql in _TRIGGERS.values():
                    self.db.execute(sql)
                self.db.execute('COMMIT')
            self.history()
        except BaseException:
            self.close()
            raise

    @staticmethod
    def _identity(path):
        stat = path.stat()
        return stat.st_dev, stat.st_ino

    def _storage(self):
        require(self._identity(self.path.parent) == self._parent, 'OBS_DIRECTORY_CHANGED')
        total = 0
        for suffix in ('', '-journal', '-wal', '-shm'):
            path = Path(str(self.path)+suffix)
            safe_path(path)
            if path.exists():
                stat = path.stat()
                require(path.is_file() and stat.st_nlink == 1, 'OBS_STORAGE_FILE')
                require(suffix not in ('-wal', '-shm'), 'OBS_UNEXPECTED_SIDECAR')
                total += stat.st_size
                if suffix == '-journal':
                    require(stat.st_size <= self.policy.max_disk_bytes//3, 'OBS_SIDECAR_BUDGET')
        require(total <= self.policy.max_disk_bytes, 'OBS_DISK_BUDGET')

    def _verified(self):
        self._storage()
        require(self.db is not None, 'OBS_JOURNAL_CLOSED')
        require(self.db.execute('SELECT digest FROM meta').fetchall() == [(self.metadata,)], 'OBS_METADATA')
        triggers = dict(self.db.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger'"))
        require(triggers == _TRIGGERS, 'OBS_SCHEMA_CHANGED')
        require(self.db.execute('PRAGMA quick_check').fetchall() == [('ok',)], 'OBS_SQLITE_CORRUPTION')
        state, result, previous = State(), [], self.metadata
        for seq, connection, recv_seq, prev, digest, document in self.db.execute('SELECT * FROM events ORDER BY seq'):
            require(len(result) < self.policy.max_events and len(document.encode('utf-8')) <= 131072, 'OBS_EVENT_BUDGET')
            value = ValidatedEvent.from_json(document)
            require(seq == len(result)+1 and prev == previous and
                    (connection, recv_seq) == (value.event.connection_id, value.event.sequence), 'OBS_CHAIN_ORDER')
            raw = value.event
            require((raw.session_id, raw.origin, raw.session_kind) == (self.session_id, self.origin, self.session_kind), 'OBS_JOURNAL_ORIGIN')
            state, recalculated = step(state, raw, self.policy, as_of=value.as_of)
            require(recalculated == value and content_hash({'seq': seq, 'previous': prev, 'value': value.to_dict()}) == digest, 'OBS_CHAIN_CONTENT')
            result.append(Entry(seq, prev, digest, value))
            previous = digest
        require(self.db.execute('SELECT seq,digest FROM head').fetchall() == [(len(result), previous)], 'OBS_HEAD')
        if self.anchor is not None:
            a = self.anchor
            require(type(a) is Checkpoint and a.metadata_sha256 == self.metadata and 0 <= a.sequence <= len(result), 'OBS_CHECKPOINT')
            require((result[a.sequence-1].sha256 if a.sequence else self.metadata) == a.sha256, 'OBS_CHECKPOINT')
        return state, tuple(result)

    def history(self):
        try:
            return self._verified()[1]
        except sqlite3.Error:
            raise ContractError('OBS_STORAGE_FAILURE') from None

    def checkpoint(self):
        rows = self.history()
        return Checkpoint(self.metadata, len(rows), rows[-1].sha256 if rows else self.metadata)

    def export(self):
        return tuple(row.value.to_json() for row in self.history())

    def _before_commit(self):
        """Fault boundary exercised offline; no network call or external callback."""

    def append(self, raw, *, as_of):
        require(type(raw) is RawEvent, 'OBS_RAW_REQUIRED')
        require((raw.session_id, raw.origin, raw.session_kind) == (self.session_id, self.origin, self.session_kind), 'OBS_JOURNAL_ORIGIN')
        self._storage()
        try:
            self.db.execute('BEGIN IMMEDIATE')
            state, rows = self._verified()
            for row in rows:
                if (raw.connection_id, raw.sequence) == (row.value.event.connection_id, row.value.event.sequence):
                    require(raw == row.value.event, 'OBS_DUPLICATE_CONFLICT')
                    self.db.execute('ROLLBACK')
                    return row
            require(len(rows) < self.policy.max_events, 'OBS_EVENT_BUDGET')
            state, value = step(state, raw, self.policy, as_of=as_of)
            prev, seq = (rows[-1].sha256 if rows else self.metadata), len(rows)+1
            digest = content_hash({'seq': seq, 'previous': prev, 'value': value.to_dict()})
            self.db.execute('INSERT INTO events VALUES(?,?,?,?,?,?)', (seq, raw.connection_id, raw.sequence, prev, digest, value.to_json()))
            self.db.execute('UPDATE head SET seq=?,digest=?', (seq, digest))
            self._before_commit()
            self.db.execute('COMMIT')
            self._storage()
            return Entry(seq, prev, digest, value)
        except BaseException as exc:
            if self.db.in_transaction:
                self.db.execute('ROLLBACK')
            if isinstance(exc, sqlite3.Error):
                raise ContractError('OBS_STORAGE_FAILURE') from None
            raise

    def close(self):
        if self.db is not None:
            self.db.close()
            self.db = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
