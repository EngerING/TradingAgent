"""Writer-only post-COMMIT publication. Readers never open or recover SQLite."""
from dataclasses import replace
from datetime import timedelta
import hashlib
import os
import time

from trading_agent.core_v3.contracts import canonical_bytes, require
from .consumer import Cursor, Segment, Publication, fingerprint


PUBLIC_FILES = {'owner.json','consumer.json','owner.tmp','consumer.tmp',
                *(f'view-{m}.{ext}' for m in (0,15,60,240) for ext in ('json','tmp')),
                *(f'prefix-{i:04}.{ext}' for i in range(1,17) for ext in ('json','tmp'))}


class Publisher:
    def __init__(self, archive):
        self.archive, self.segments, self._fingerprints = archive, [], {}
        self.epoch = os.urandom(32).hex()
        # Only the exclusive writer may discard an interrupted, unpublished staging file.
        for name in sorted(PUBLIC_FILES):
            path = archive.root/name
            if name.endswith('.tmp') and path.exists():
                fingerprint(path)
                require(path.stat().st_size <= 131072,'M03_PUBLICATION_BUDGET')
                path.unlink()
        self._write('owner.json',canonical_bytes({'epoch':self.epoch,'metadata_sha256':archive.metadata}))

    def _write(self, name, data):
        archive = self.archive
        require(name in PUBLIC_FILES and name.endswith('.json') and len(data) <= 131072,'M03_PUBLICATION_FILE')
        archive._storage()
        total = sum(p.stat().st_size for p in archive.root.iterdir())
        require(total+len(data) <= archive.config.max_total_bytes-65536,'M03_ARCHIVE_DISK_BUDGET')
        temporary, destination = archive.root/name.replace('.json','.tmp'), archive.root/name
        with temporary.open('xb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        # Windows readers close handles before parsing. Sharing violations are bounded,
        # never interpreted as permission to publish partial bytes or skip durability.
        for attempt in range(5):
            try:
                os.replace(temporary,destination)
                return
            except PermissionError:
                if attempt == 4: raise
                time.sleep(.002)

    def publish(self, at):
        a = self.archive
        require(a.current is None or not a.current.db.in_transaction,'M03_PUBLICATION_BEFORE_COMMIT')
        for index,name in enumerate(a.segments):
            if index < len(self.segments) and index < len(a.segments)-1:
                require(fingerprint(a.root/name) == self._fingerprints[name],'M03_SEALED_SEGMENT_CHANGED')
                continue
            if a.current is not None and name == a.segments[-1]:
                journal, owned = a.current, False
            else: journal, owned = a._journal(name), True
            try:
                rows = journal.history()
                proof = canonical_bytes({'schema':'trading.m03a.segment_prefix','schema_version':1,
                    'digests':[journal.metadata]+[r.sha256 for r in rows]})
                digest = hashlib.sha256()
                before = fingerprint(a.root/name)
                with (a.root/name).open('rb') as stream:
                    while chunk := stream.read(65536): digest.update(chunk)
                require(fingerprint(a.root/name) == before,'M03_PUBLICATION_CHANGED')
                self._fingerprints[name] = before
                segment = Segment(name,digest.hexdigest(),before[2],hashlib.sha256(proof).hexdigest(),len(rows),
                                  rows[-1].sha256 if rows else journal.metadata)
                self._write(f'prefix-{index+1:04}.json',proof)
                if index < len(self.segments): self.segments[index] = segment
                else: self.segments.append(segment)
            finally:
                if owned: journal.close()
        last = self.segments[-1] if self.segments else None
        cursor = Cursor(a.metadata,len(self.segments),last.count if last else 0,last.head if last else a.metadata)
        at = max(at,a._projection.available)
        views = [replace(a._projection.observe(at,m,active=a._active),evidence_sha256=cursor.sha256)
                 for m in (0,15,60,240)]
        encoded = [v.to_json().encode('utf-8') for v in views]
        valid_until = at
        quote = views[0].quote
        if quote is not None:
            cal = a._projection.calendar
            interval = cal.interval(at) if cal else None
            if interval:
                valid_until = min(quote.bid_received_at+timedelta(milliseconds=a.config.capture.side_max_age_ms),
                                  quote.ask_received_at+timedelta(milliseconds=a.config.capture.side_max_age_ms),
                                  cal.received_at+timedelta(hours=24),interval[1])
        publication = Publication(cursor,self.epoch,at,valid_until,time.monotonic_ns(),a._active,
                                  tuple(self.segments),tuple(hashlib.sha256(v).hexdigest() for v in encoded))
        manifest = publication.to_json().encode('utf-8')
        for minutes,data in zip((0,15,60,240),encoded): self._write(f'view-{minutes}.json',data)
        self._write('consumer.json',manifest)

    def verify_files(self):
        require(all(fingerprint(self.archive.root/name) == stamp for name,stamp in self._fingerprints.items()),
                'M03_PUBLISHED_SEGMENT_CHANGED')
