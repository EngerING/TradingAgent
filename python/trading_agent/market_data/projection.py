"""Incremental causal fold. One committed row is consumed once, without journal I/O."""
import base64
from dataclasses import replace
from datetime import datetime, timezone

from trading_agent.core_v3.contracts import require, utc
from trading_agent.core_v3.market_observation.contracts import Kind, DataType, Origin
from trading_agent.core_v3.market_observation.validation import State, step
from trading_agent.core_v3.market_observation.ibkr_protocol import fields
from .contracts import Observation
from .calendar import TradingCalendar
from .wire import historical, request_cutoff, TIMEFRAMES


class Projection:
    def __init__(self, config, origin, environment, metadata):
        self.config, self.origin, self.environment = config, origin, environment
        self.state, self.quote, self.calendar, self.contract = State(), None, None, None
        self.planned, self.seen, self.conflicts = {}, {}, set()
        self.bars, self.quality = {}, {}
        self.available = datetime.min.replace(tzinfo=timezone.utc)
        self.evidence, self.folded = metadata, 0

    def feed(self, row):
        raw = row.value.event
        self.available = max(self.available,raw.received_at,row.value.as_of)
        self.state, value = step(self.state,raw,self.config.capture,as_of=row.value.as_of)
        self.evidence, self.folded = row.sha256, self.folded+1
        if raw.kind is Kind.CONNECTED:
            self.quote, self.calendar, self.contract = None, None, None
            self.bars, self.quality, self.planned = {}, {}, {}
        if raw.kind is Kind.CONTRACT and value.accepted:
            self.contract = raw.contract
            if raw.raw_frame_b64:
                f = fields(base64.b64decode(raw.raw_frame_b64))
                self.calendar = TradingCalendar(f[27],f[28],raw.received_at)
        if raw.kind in (Kind.GAP,Kind.DISCONNECTED) or not value.accepted: self.quote = None
        if raw.kind in (Kind.BID,Kind.ASK): self.quote = value.quote
        if raw.diagnostic == 'HISTORY_REQUEST_PLANNED':
            require(self.contract is not None,'M03_HISTORY_NO_CONTRACT')
            cutoff = request_cutoff(base64.b64decode(raw.raw_frame_b64),raw.wire_request_id,self.contract.con_id)
            require(cutoff <= raw.received_at,'M03_HISTORY_REQUEST_FUTURE')
            self.planned[raw.wire_request_id] = cutoff
        if raw.diagnostic == 'HISTORY_BATCH':
            minutes = TIMEFRAMES.get(raw.wire_request_id)
            require(minutes and self.calendar is not None and self.contract is not None and
                    raw.wire_request_id in self.planned,'M03_HISTORY_NO_CONTRACT')
            all_bars, quality = historical(base64.b64decode(raw.raw_frame_b64),minutes,raw.received_at,
                self.calendar,request_end=self.planned[raw.wire_request_id])
            included, extra = [], []
            for bar in all_bars:
                if not bar.complete: continue
                key = (self.contract.con_id,minutes,bar.opened_at)
                prices = (bar.open,bar.high,bar.low,bar.close)
                if key in self.seen:
                    extra.append('HISTORY_DUPLICATE' if self.seen[key] == prices else 'HISTORY_CONFLICT')
                    if self.seen[key] != prices: self.conflicts.add(key)
                if key in self.conflicts:
                    extra.append('HISTORY_CONFLICT')
                    continue
                require(key in self.seen or len(self.seen) < 8192,'M03_PROJECTION_BUDGET')
                self.seen[key] = prices
                included.append(replace(bar,available_at=self.available))
            self.bars[minutes] = tuple(included)
            self.quality[minutes] = tuple(sorted(set(quality+tuple(extra)+tuple(c for b in all_bars for c in b.quality))))

    def observe(self, as_of, minutes=0, *, active=False):
        as_of = utc(as_of)
        require(minutes in (0,15,60,240),'M03_TIMEFRAME')
        require(as_of >= self.available,'M03_PREFIX_NOT_AVAILABLE')
        quote, bars = self.quote, self.bars.get(minutes,())
        reasons = list(self.quality.get(minutes,()))
        if not active or not self.state.connected:
            quote = None
            reasons.append('DISCONNECTED_OR_RESTARTED')
        if quote and max((as_of-t).total_seconds()*1000 for t in (quote.bid_received_at,quote.ask_received_at)) > self.config.capture.side_max_age_ms:
            quote = None
            reasons.append('SIDE_RECEIPT_STALE')
        if self.calendar is None or self.calendar.state(as_of) != 'OPEN':
            quote = None
            reasons.append('MARKET_CLOSED_OR_CALENDAR_UNKNOWN')
        if self.state.data_type is not DataType.LIVE: reasons.append('FEED_NOT_LIVE')
        if quote and quote.source_age_us is None: reasons.append('SOURCE_TIME_NOT_PROVIDED')
        if not quote and not minutes: reasons.append('QUOTE_UNAVAILABLE')
        if minutes and not bars: reasons.append('BARS_UNAVAILABLE')
        if minutes: reasons.append('HISTORICAL_FEED_TYPE_NOT_CONFIRMED')
        # A non-LIVE feed can retain its provenance, but is never a current quote.
        if self.state.data_type is not DataType.LIVE: quote = None
        available = bool(bars) if minutes else quote is not None
        freshness = 'STALE' if minutes and bars else 'FRESH' if available else 'UNAVAILABLE'
        return Observation('EUR/USD',self.contract,self.origin,self.environment,self.state.connection,as_of,minutes,
            None if minutes else quote,bars if minutes else (),DataType.UNKNOWN if minutes else self.state.data_type,
            freshness,tuple(sorted(set(reasons))),self.evidence,'IBKR_DATA_ONLY' if self.origin is Origin.SOCKET else 'OFFLINE')
