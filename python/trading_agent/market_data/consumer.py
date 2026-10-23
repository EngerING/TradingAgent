"""Read-only, latest-state consumer. No SQLite connection, recovery, capture or order API."""
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
import errno
import hashlib
import os
import re
import time

from trading_agent.core_v3.contracts import require, content_hash, strict_json, utc, ContractError
from trading_agent.core_v3.economic_contracts import _hash
from trading_agent.core_v3.historical_ingestion.contracts import Record
from trading_agent.core_v3.historical_ingestion.files import safe_path, read_local
from trading_agent.core_v3.market_observation.contracts import Origin, SessionKind, DataType
from .contracts import CollectorConfig, Observation


@dataclass(frozen=True, slots=True)
class Cursor(Record):
    SCHEMA = 'trading.m03a.consumer_cursor'
    metadata_sha256: str
    segment: int
    sequence: int
    sha256: str

    def __post_init__(self):
        self.check_types()
        _hash(self.metadata_sha256)
        _hash(self.sha256)
        require(0 <= self.segment <= 16 and 0 <= self.sequence <= 512 and
                (self.segment > 0 or self.sequence == 0),'M03_CURSOR')


@dataclass(frozen=True, slots=True)
class Segment(Record):
    SCHEMA = 'trading.m03a.published_segment'
    name: str
    file_sha256: str
    size: int
    prefix_sha256: str
    count: int
    head: str

    def __post_init__(self):
        self.check_types()
        require(re.fullmatch(r'[0-9]{4}-[0-9a-f]{64}\.sqlite',self.name) is not None and
                0 <= self.count <= 512 and 0 < self.size <= 67108864,'M03_PUBLICATION_SEGMENT')
        for value in (self.file_sha256,self.prefix_sha256,self.head): _hash(value)


@dataclass(frozen=True, slots=True)
class Publication(Record):
    SCHEMA = 'trading.m03a.committed_publication'
    cursor: Cursor
    epoch: str
    available_at: datetime
    valid_until: datetime
    monotonic_ns: int
    active: bool
    segments: tuple[Segment, ...]
    views: tuple[str, ...]

    def __post_init__(self):
        self.check_types()
        _hash(self.epoch)
        require(0 <= self.monotonic_ns and len(self.segments) <= 16 and len(self.views) == 4,
                'M03_PUBLICATION_LIMIT')
        require(self.cursor.segment == len(self.segments),'M03_PUBLICATION_CURSOR')
        for digest in self.views: _hash(digest)
        object.__setattr__(self,'available_at',utc(self.available_at))
        object.__setattr__(self,'valid_until',utc(self.valid_until))


@dataclass(frozen=True, slots=True)
class ReadResult:
    code: str
    cursor: Cursor | None
    observation: Observation | None


def fingerprint(path):
    safe_path(path)
    stat = path.stat()
    require(path.is_file() and stat.st_nlink == 1,'M03_CONSUMER_FILE')
    return (stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns)


def writer_present(path):
    """Read the mandatory-locked Windows byte; POSIX uses compatible shared probes."""
    fingerprint(path)
    with path.open('rb') as stream:
        try:
            if os.name == 'nt':
                # CRT LK_NBRLCK is exclusive too: do not let readers impersonate a
                # writer by blocking each other's probes. No reader lock on Windows.
                require(stream.read(1) == b'M','M03_ARCHIVE_LOCK')
            else:
                import fcntl
                fcntl.flock(stream.fileno(),fcntl.LOCK_SH | fcntl.LOCK_NB)
                fcntl.flock(stream.fileno(),fcntl.LOCK_UN)
            return False
        except OSError as exc:
            if exc.errno in (errno.EACCES,errno.EAGAIN,errno.EDEADLK): return True
            raise


class Consumer:
    """One latest observation per poll; cursor anchors a durable prefix, not every tick.

    Retain the returned cursor outside the capture directory to detect prefix rollback.
    Re-evaluate poll() for every decision: retained Observation objects are historical.
    """
    def __init__(self, directory, config, session_id, origin, environment, *, cursor=None):
        require(type(config) is CollectorConfig and type(origin) is Origin and
                type(environment) is SessionKind,'M03_CONSUMER_TYPE')
        self.root = safe_path(directory)
        require(self.root.is_dir(),'M03_ARCHIVE_DIRECTORY')
        self.identity = {'schema':'trading.m03a.archive','schema_version':1,'config':config.to_dict(),
                         'session_id':session_id,'origin':origin.value,'environment':environment.value}
        self.metadata = content_hash(self.identity)
        require(cursor is None or type(cursor) is Cursor and cursor.metadata_sha256 == self.metadata,'M03_CURSOR')
        self.config, self.origin, self.environment, self.cursor = config, origin, environment, cursor
        self._root_id = (self.root.stat().st_dev,self.root.stat().st_ino)
        self._files, self._last_publication = {}, None
        self.hashed_bytes = 0

    def _file_digest(self, name, maximum):
        path = self.root/name
        before = fingerprint(path)
        require(before[2] <= maximum,'M03_CONSUMER_BUDGET')
        if name not in self._files or self._files[name][0] != before:
            digest = hashlib.sha256()
            with path.open('rb') as stream:
                remaining = maximum+1
                while remaining:
                    chunk = stream.read(min(65536,remaining))
                    if not chunk: break
                    remaining -= len(chunk)
                    digest.update(chunk)
                    self.hashed_bytes += len(chunk)
            require(remaining > 0 and fingerprint(path) == before,'M03_CONSUMER_CHANGED')
            self._files[name] = (before,digest.hexdigest())
        return self._files[name][1]

    def poll(self, as_of, minutes=0):
        as_of = utc(as_of)
        require(minutes in (0,15,60,240),'M03_TIMEFRAME')
        try:
            return self._poll(as_of,minutes)
        except (ContractError,OSError,ValueError,TypeError,KeyError,IndexError):
            # No cached quote on any uncertain/in-progress/tampered publication.
            return ReadResult('UNAVAILABLE',self.cursor,None)

    def _poll(self, as_of, minutes):
        safe_path(self.root)
        require((self.root.stat().st_dev,self.root.stat().st_ino) == self._root_id,'M03_DIRECTORY_CHANGED')
        require(strict_json(read_local(self.root,'identity.json',max_bytes=4096)) == self.identity,'M03_ARCHIVE_IDENTITY')
        raw = read_local(self.root,'consumer.json',max_bytes=131072)
        pub = Publication.from_json(raw)
        require(pub.cursor.metadata_sha256 == self.metadata and pub.available_at <= as_of,'M03_PUBLICATION_IDENTITY')
        owner = read_local(self.root,'owner.json',max_bytes=131072)
        require(strict_json(owner) == {'epoch':pub.epoch,'metadata_sha256':self.metadata},'M03_OWNER')
        allowed = {'identity.json','writer.lock','owner.json','consumer.json',
                   'owner.tmp','consumer.tmp',*(f'view-{m}.json' for m in (0,15,60,240)),
                   *(f'view-{m}.tmp' for m in (0,15,60,240)),
                   *(f'prefix-{i:04}.json' for i in range(1,len(pub.segments)+1)),
                   *(f'prefix-{i:04}.tmp' for i in range(1,len(pub.segments)+2)),
                   *(s.name for s in pub.segments),*(s.name+'-journal' for s in pub.segments)}
        files = tuple(self.root.iterdir())
        # A concurrent rotation may briefly add a segment before its publication.
        require(len(pub.segments) <= self.config.max_segments and all(s.count <= self.config.capture.max_events
                for s in pub.segments),'M03_PUBLICATION_LIMIT')
        require(len(files) <= 96 and all(p.name in allowed for p in files) and
                not any(p.suffix == '.tmp' for p in files),'M03_PUBLICATION_FILES')
        require(sum(fingerprint(p)[2] for p in files) <= self.config.max_total_bytes,'M03_CONSUMER_BUDGET')
        previous = self.metadata
        for i,s in enumerate(pub.segments,1):
            require(s.name == f'{i:04}-{previous}.sqlite','M03_SEGMENT_CHAIN')
            require(self._file_digest(s.name,self.config.capture.max_disk_bytes) == s.file_sha256 and
                    (self.root/s.name).stat().st_size == s.size,'M03_SEGMENT_CONTENT')
            previous = s.head
        last = pub.segments[-1] if pub.segments else None
        require(pub.cursor.sha256 == (last.head if last else self.metadata) and
                pub.cursor.sequence == (last.count if last else 0),'M03_PUBLICATION_CURSOR')
        if self.cursor:
            anchor = self.cursor
            require(anchor.segment <= len(pub.segments),'M03_CURSOR_ROLLBACK')
            if anchor.segment:
                segment = pub.segments[anchor.segment-1]
                prefix = read_local(self.root,f'prefix-{anchor.segment:04}.json',max_bytes=131072)
                require(hashlib.sha256(prefix).hexdigest() == segment.prefix_sha256,'M03_CURSOR_PROOF')
                proof = strict_json(prefix)
                require(set(proof) == {'schema','schema_version','digests'} and
                        proof['schema'] == 'trading.m03a.segment_prefix' and type(proof['schema_version']) is int and
                        proof['schema_version'] == 1 and type(proof['digests']) is list and
                        len(proof['digests']) == segment.count+1 and anchor.sequence < len(proof['digests']) and
                        proof['digests'][anchor.sequence] == anchor.sha256,'M03_CURSOR_ROLLBACK')
            else: require(anchor.sha256 == self.metadata,'M03_CURSOR_ROLLBACK')
        index = (0,15,60,240).index(minutes)
        view_raw = read_local(self.root,f'view-{minutes}.json',max_bytes=131072)
        require(hashlib.sha256(view_raw).hexdigest() == pub.views[index],'M03_VIEW_CONTENT')
        view = Observation.from_json(view_raw)
        require(view.origin is self.origin and view.environment is self.environment and
                view.timeframe_minutes == minutes and view.as_of == pub.available_at and
                view.evidence_sha256 == pub.cursor.sha256,'M03_VIEW_IDENTITY')
        # Detect rotation/commit/publication changes across this read, not just at its start.
        require(read_local(self.root,'consumer.json',max_bytes=131072) == raw and
                read_local(self.root,'owner.json',max_bytes=131072) == owner,'M03_PUBLICATION_CHANGED')
        require(all(fingerprint(self.root/name) == pair[0] for name,pair in self._files.items()),'M03_CONSUMER_CHANGED')
        elapsed = time.monotonic_ns()-pub.monotonic_ns
        live = pub.active and writer_present(self.root/'writer.lock') and 0 <= elapsed
        live = live and as_of < pub.valid_until and elapsed < max(0,(pub.valid_until-pub.available_at).total_seconds()*10**9)
        if view.quote:
            require(pub.valid_until <= min(view.quote.bid_received_at,view.quote.ask_received_at)+
                    timedelta(milliseconds=self.config.capture.side_max_age_ms),
                    'M03_PUBLICATION_FRESHNESS')
        if not live or view.feed_type is not DataType.LIVE or minutes:
            view = replace(view,as_of=as_of,quote=None,freshness='STALE' if view.bars else 'UNAVAILABLE',
                           quality=tuple(sorted(set(view.quality+('CONSUMER_NOT_CURRENT',)))))
        else: view = replace(view,as_of=as_of)
        same = self.cursor == pub.cursor and self._last_publication in (None,raw)
        self.cursor, self._last_publication = pub.cursor, raw
        return ReadResult('UNCHANGED' if same else 'OK',self.cursor,view)
