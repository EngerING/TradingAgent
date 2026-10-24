"""Independent, bounded IBKR calendar preflight for the Paper host scheduler.

No quote subscription, historical request, order API or system-clock market guess.
This in-memory probe never certifies a fixture as authentic broker evidence.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
import threading

from trading_agent.core_v3.contracts import require
from trading_agent.core_v3.market_observation.contracts import Kind, Origin
from .authorization import DataApproval
from .contracts import CollectorConfig
from .reader import MarketReader, TranscriptReader


@dataclass(frozen=True, slots=True)
class CalendarProbe:
    state: str
    origin: str
    next_open: datetime | None = None

    @property
    def broker_closed(self):
        return self.state == 'CLOSED' and self.origin == Origin.SOCKET.value


def probe_broker_calendar(config, approval, stop, *, reader_factory=MarketReader, now=None):
    """Return UNKNOWN unless account, contract and finite tradingHours all validate."""
    require(type(config) is CollectorConfig and type(approval) is DataApproval and
            type(stop) is threading.Event and not stop.is_set(), 'M035_PROBE_AUTH')
    require(reader_factory in (MarketReader, TranscriptReader), 'M035_PROBE_READER')
    approval.verify(config, now() if now is not None else datetime.now(timezone.utc))
    clock = {'now':now} if now is not None else {}
    reader = reader_factory(config, approval, stop=stop.is_set, calendar_only=True, **clock)
    state, next_open = 'UNKNOWN', None
    try:
        for event in reader.events():
            if stop.is_set():
                break
            if event.kind is Kind.GAP and event.diagnostic in ('MARKET_OPEN', 'MARKET_CLOSED'):
                if reader.calendar is not None and reader.calendar.state(reader.now()) == event.diagnostic[7:]:
                    state, next_open = event.diagnostic[7:], reader.next_open
                break
            if event.kind is Kind.GAP:
                break
    finally:
        reader.close()
    return CalendarProbe(state, reader.origin.value, next_open)
