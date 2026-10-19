"""Bounded, synchronous commit-before-publication collection; no background worker."""
from dataclasses import dataclass
from datetime import datetime, timezone

from ..contracts import require
from .contracts import RawEvent, Origin, Kind
from .ibkr_adapter import IBKRReader, TranscriptAdapter
from .journal import Journal, Checkpoint


class FixtureAdapter:
    def __init__(self, events):
        require(type(events) is tuple and len(events) <= 4096 and all(type(e) is RawEvent and e.origin is Origin.FIXTURE for e in events), 'OBS_FIXTURE_ONLY')
        self._events, self.closed = events, False

    def events(self):
        yield from self._events

    def close(self):
        self.closed = True


@dataclass(frozen=True, slots=True)
class CollectionReceipt:
    committed: int
    checkpoint: Checkpoint
    action: str = 'NO_TRADE'
    execution_authorized: bool = False


def collect(adapter, journal, *, now=lambda: datetime.now(timezone.utc)):
    require(type(adapter) in (FixtureAdapter, TranscriptAdapter, IBKRReader) and type(journal) is Journal, 'OBS_COLLECTOR_TYPE')
    expected = Origin.SOCKET if type(adapter) is IBKRReader else Origin.FIXTURE
    require(journal.origin is expected, 'OBS_COLLECTOR_ORIGIN')
    before = len(journal.history())
    iterator = adapter.events()
    try:
        first = True
        for event in iterator:
            if first:
                # A resumed producer must establish a new epoch; old quotes cannot survive restart.
                require(event.kind is Kind.CONNECTED, 'OBS_NEW_EPOCH_REQUIRED')
                if before:
                    last = journal.history()[-1].value.event
                    require(event.connection_id != last.connection_id, 'OBS_NEW_EPOCH_REQUIRED')
                    from dataclasses import replace
                    gap = replace(last, sequence=last.sequence+1, kind=Kind.GAP, received_at=event.received_at,
                                  monotonic_ns=event.monotonic_ns, contract=None, data_type=None,
                                  price_text=None, tick_type=None, source_at=None, raw_frame_b64='',
                                  raw_frame_sha256=None, raw_frame_size=0, wire_request_id=None,
                                  diagnostic='COLLECTOR_RESTART_GAP')
                    journal.append(gap, as_of=now())
                first = False
            journal.append(event, as_of=now())
        rows = journal.history()
        return CollectionReceipt(len(rows)-before, journal.checkpoint())
    finally:
        iterator.close()
        adapter.close()
