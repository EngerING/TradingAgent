"""Bounded linked V3.9 journals. No migration or writes to protected financial stores."""
from dataclasses import dataclass
from datetime import timedelta
import os
import re

from trading_agent.core_v3.contracts import require, content_hash, canonical_bytes, utc, ContractError
from trading_agent.core_v3.historical_ingestion.files import safe_path, read_local
from trading_agent.core_v3.market_observation.contracts import RawEvent, Kind
from trading_agent.core_v3.market_observation.journal import Journal
from .projection import Projection
from .publication import Publisher, PUBLIC_FILES


@dataclass(frozen=True, slots=True)
class ArchiveCheckpoint:
    metadata_sha256: str
    segments: int
    sequence: int
    sha256: str


class Archive:
    def __init__(self, directory, config, session_id, origin, environment, *, create=False, checkpoint=None):
        self.root = safe_path(directory)
        require(self.root.is_dir(), 'M03_ARCHIVE_DIRECTORY')
        self.config, self.session_id, self.origin, self.environment = config, session_id, origin, environment
        self._lock, self.current, self.segments, self._active = None, None, [], False
        self._publisher = None
        self._root_identity = Journal._identity(self.root)
        identity = {'schema':'trading.m03a.archive', 'schema_version':1, 'config':config.to_dict(),
                    'session_id':session_id, 'origin':origin.value, 'environment':environment.value}
        self.metadata = content_hash(identity)
        try:
            if create:
                require(not tuple(self.root.iterdir()), 'M03_ARCHIVE_NOT_EMPTY')
                with (self.root/'identity.json').open('xb') as stream:
                    stream.write(canonical_bytes(identity))
                    stream.flush()
                    os.fsync(stream.fileno())
                with (self.root/'writer.lock').open('xb') as stream: stream.write(b'M03A')
            require(read_local(self.root,'identity.json',max_bytes=4096) == canonical_bytes(identity), 'M03_ARCHIVE_IDENTITY')
            require(read_local(self.root,'writer.lock',max_bytes=4) == b'M03A', 'M03_ARCHIVE_LOCK')
            self._lock = (self.root/'writer.lock').open('r+b')
            self._lock.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self._lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            # Invalidate the previous process epoch before potentially slow verification.
            self._publisher = Publisher(self)
            self._scan()
            rows = self.history()
            self._projection = Projection(config,origin,environment,self.metadata)
            for row in rows: self._projection.feed(row)
            if checkpoint is not None:
                require(type(checkpoint) is ArchiveCheckpoint and checkpoint.metadata_sha256 == self.metadata and
                        0 <= checkpoint.segments <= len(self.segments), 'M03_CHECKPOINT')
                digest = self.metadata
                if checkpoint.segments:
                    with self._journal(self.segments[checkpoint.segments-1]) as journal:
                        rows = journal.history()
                        require(type(checkpoint.sequence) is int and 0 <= checkpoint.sequence <= len(rows), 'M03_CHECKPOINT')
                        digest = rows[checkpoint.sequence-1].sha256 if checkpoint.sequence else journal.metadata
                else: require(checkpoint.sequence == 0, 'M03_CHECKPOINT')
                require(digest == checkpoint.sha256, 'M03_CHECKPOINT')
            self._publisher.publish(self._projection.available)
        except BaseException as exc:
            self.close()
            if isinstance(exc, OSError): raise ContractError('M03_ARCHIVE_LOCK_OR_IO') from None
            raise

    def _storage(self):
        safe_path(self.root)
        require(Journal._identity(self.root) == self._root_identity, 'M03_DIRECTORY_CHANGED')
        total = 0
        for p in self.root.iterdir():
            safe_path(p)
            require(p.is_file() and p.stat().st_nlink == 1, 'M03_ARCHIVE_FILE')
            total += p.stat().st_size
        require(total <= self.config.max_total_bytes-65536, 'M03_ARCHIVE_DISK_BUDGET')

    def _scan(self):
        self._storage()
        files = [p.name for p in self.root.iterdir() if p.name not in {'identity.json','writer.lock'} | PUBLIC_FILES]
        names = sorted(n for n in files if not n.endswith('-journal'))
        require(all(n in names or n.removesuffix('-journal') in names for n in files), 'M03_ARCHIVE_FILES')
        require(len(names) <= self.config.max_segments and all(
            re.fullmatch(r'[0-9]{4}-[0-9a-f]{64}\.sqlite', n) for n in names), 'M03_ARCHIVE_FILES')
        previous = self.metadata
        for i, name in enumerate(names, 1):
            require(name == f'{i:04}-{previous}.sqlite', 'M03_SEGMENT_CHAIN')
            previous = self._head(name)
        self.segments = names

    def _journal(self, name, *, create=False):
        require(create or (self.root/name).is_file(), 'M03_SEGMENT_MISSING')
        return Journal(self.root/name, self.config.capture, self.session_id, self.origin, self.environment)

    def _head(self, name):
        with self._journal(name) as journal: return journal.checkpoint().sha256

    def history(self):
        self._storage()
        rows = []
        for name in self.segments:
            if self.current is not None and name == self.segments[-1]:
                rows.extend(self.current.history())
            else:
                with self._journal(name) as journal: rows.extend(journal.history())
        require(len(rows) <= 8192, 'M03_ARCHIVE_EVENT_BUDGET')
        return tuple(rows)

    def checkpoint(self):
        self.history()
        if not self.segments: return ArchiveCheckpoint(self.metadata,0,0,self.metadata)
        if self.current is not None: head = self.current.checkpoint()
        else:
            with self._journal(self.segments[-1]) as journal: head = journal.checkpoint()
        return ArchiveCheckpoint(self.metadata,len(self.segments),head.sequence,head.sha256)

    def rotate(self, now):
        require(self._lock is not None,'M03_WRITER_CLOSED')
        self._storage()
        require(len(self.segments) < self.config.max_segments, 'M03_SEGMENT_BUDGET')
        if self.current is None and self.segments:
            self.current = self._journal(self.segments[-1])
        if self.current is not None:
            rows = self.current.history()
            if rows and rows[-1].value.event.kind is not Kind.DISCONNECTED:
                last = rows[-1].value.event
                seq = max(r.value.event.sequence for r in rows if r.value.event.connection_id == last.connection_id)+1
                gap = RawEvent(self.session_id, last.connection_id, last.request_id, seq, Kind.GAP,
                    utc(now), last.monotonic_ns, self.origin, self.environment,
                    diagnostic='COLLECTOR_RESTART_GAP', host_attestation_sha256=last.host_attestation_sha256,
                    capture_grant_sha256=last.capture_grant_sha256)
                row = self.current.append(gap, as_of=now)
                self._projection.feed(row)
                if self._publisher: self._publisher.segments = self._publisher.segments[:-1]
            previous = self.current.checkpoint().sha256
            self.current.close()
            self.current = None
        else: previous = self.metadata
        name = f'{len(self.segments)+1:04}-{previous}.sqlite'
        self.current = self._journal(name, create=True)
        self.segments.append(name)
        self._active = False
        self._storage()
        self._publisher.publish(max(utc(now),self._projection.available))

    def append(self, event, *, as_of):
        require(self._lock is not None,'M03_WRITER_CLOSED')
        require(type(event) is RawEvent, 'M03_EVENT_TYPE')
        if self.current is None: self.rotate(as_of)
        rows = self.current.history()
        if not rows:
            require(event.kind is Kind.CONNECTED and not any(r.value.event.connection_id == event.connection_id
                    for r in self.history()), 'M03_NEW_EPOCH_REQUIRED')
        require(len(rows) < self.config.capture.max_events-1, 'M03_SEGMENT_EVENTS')
        # Reserve worst-case main/rollback growth before accepting another record.
        self._storage()
        total = sum(p.stat().st_size for p in self.root.iterdir())
        require(total+3*131072 <= self.config.max_total_bytes, 'M03_ARCHIVE_DISK_BUDGET')
        before = len(rows)
        row = self.current.append(event, as_of=as_of)
        self._storage()
        if row.sequence > before:
            self._projection.feed(row)
            if event.kind is Kind.CONNECTED: self._active = True
            if event.kind in (Kind.GAP, Kind.DISCONNECTED): self._active = False
            self._publisher.publish(max(utc(as_of),self._projection.available))
        return row

    def history_not_before(self):
        planned = [r.value.event.received_at for r in self.history()
                   if r.value.event.diagnostic == 'HISTORY_REQUEST_PLANNED']
        return max(planned)+timedelta(seconds=600) if planned else None

    def observe(self, as_of, minutes=0):
        as_of = utc(as_of)
        require(minutes in (0,15,60,240), 'M03_TIMEFRAME')
        projection = self._projection
        if as_of < projection.available:
            # Historical cutoffs are explicit replay, never the live polling path.
            projection = Projection(self.config,self.origin,self.environment,self.metadata)
            for row in self.history():
                if max(row.value.event.received_at,row.value.as_of) > as_of: break
                projection.feed(row)
        self._storage()
        self._publisher.verify_files()
        return projection.observe(as_of,minutes,active=self._active)

    def invalidate(self, as_of):
        self._active = False
        self._publisher.publish(max(utc(as_of),self._projection.available))

    def close(self):
        journal, self.current = self.current, None
        try:
            if journal is not None: journal.close()
        finally:
            self._active = False
            lock, self._lock = self._lock, None
            if lock is not None: lock.close()

    def __enter__(self): return self
    def __exit__(self, *args): self.close()
