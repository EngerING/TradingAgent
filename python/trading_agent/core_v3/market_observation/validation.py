"""Causal quote fold. Invalid inputs clear eligible sides, never repair prices."""
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import localcontext

from ..contracts import ContractError, parse_decimal, require, utc
from .contracts import CapturePolicy, RawEvent, Quote, ValidatedEvent, Kind, DataType


@dataclass(frozen=True, slots=True)
class State:
    connection: str = ''
    session: str = ''
    origin: object = None
    session_kind: object = None
    request_id: int = 0
    sequence: int = 0
    previous: RawEvent | None = None
    connected: bool = False
    contract: object = None
    data_type: DataType = DataType.UNKNOWN
    bid: RawEvent | None = None
    ask: RawEvent | None = None
    last_mid: object = None


def step(state, event, policy, *, as_of):
    require(type(state) is State and type(event) is RawEvent and type(policy) is CapturePolicy, 'OBS_EXACT_TYPE')
    as_of = utc(as_of)
    with localcontext() as ctx:
        ctx.prec = 160
        return _step(state, event, policy, as_of)


def _step(state, event, policy, as_of):
    reasons = []
    if event.kind is Kind.CONNECTED:
        if event.sequence != 1 or event.connection_id == state.connection:
            reasons.append('CONNECTION_EPOCH_INVALID')
        state = State(connection=event.connection_id, session=event.session_id, origin=event.origin,
                      session_kind=event.session_kind, request_id=event.request_id, connected=True)
    elif not state.connected or (event.connection_id, event.session_id, event.origin,
            event.session_kind, event.request_id) != (state.connection, state.session, state.origin,
            state.session_kind, state.request_id):
        reasons.append('CONNECTION_IDENTITY_MISMATCH')
    if event.sequence != state.sequence+1:
        reasons.append('RECEIVE_SEQUENCE_GAP')
    if event.received_at > as_of:
        reasons.append('RECEIPT_FROM_FUTURE')
    if event.source_at is not None and event.source_at > event.received_at:
        reasons.append('SOURCE_TIME_FUTURE')
    if state.previous:
        delta = event.received_at-state.previous.received_at
        wall = (delta.days*86400+delta.seconds)*1000000000+delta.microseconds*1000
        mono = event.monotonic_ns-state.previous.monotonic_ns
        if mono < 0 or wall < 0 or abs(wall-mono) > policy.clock_tolerance_ms*1000000:
            reasons.append('RECEIPT_CLOCK_DISCONTINUITY')
    state = replace(state, sequence=event.sequence, previous=event)
    if event.kind in (Kind.DISCONNECTED, Kind.GAP):
        state = replace(state, connected=False, contract=None, data_type=DataType.UNKNOWN, bid=None, ask=None, last_mid=None)
    if reasons:
        state = replace(state, bid=None, ask=None)
        return state, ValidatedEvent(event, as_of, False, tuple(reasons), None)
    if event.kind is Kind.CONTRACT:
        if event.contract is None:
            reasons.append('CONTRACT_MISSING')
        state = replace(state, contract=event.contract, bid=None, ask=None, last_mid=None)
    elif event.kind is Kind.DATA_TYPE:
        state = replace(state, data_type=event.data_type or DataType.UNKNOWN, bid=None, ask=None, last_mid=None)
    quote = None
    if event.kind in (Kind.BID, Kind.ASK):
        if state.contract is None:
            reasons.append('CONTRACT_UNVERIFIED')
        expected = (66 if event.kind is Kind.BID else 67) if state.data_type in (DataType.DELAYED, DataType.DELAYED_FROZEN) else (1 if event.kind is Kind.BID else 2)
        if event.tick_type != expected or state.data_type is DataType.UNKNOWN:
            reasons.append('TICK_DATA_TYPE_MISMATCH')
        try:
            value = parse_decimal(event.price_text)
            require(value > 0 and (state.contract is None or value % state.contract.min_tick == 0), 'PRICE_INVALID')
        except (ContractError, TypeError, ValueError):
            reasons.append('PRICE_INVALID')
        if not reasons:
            state = replace(state, **{'bid' if event.kind is Kind.BID else 'ask': event})
            if state.bid and state.ask:
                bid, ask = parse_decimal(state.bid.price_text), parse_decimal(state.ask.price_text)
                ages = [int((as_of-side.received_at).total_seconds()*1000000) for side in (state.bid, state.ask)]
                if max(ages) > policy.side_max_age_ms*1000:
                    reasons.append('SIDE_RECEIPT_STALE')
                if bid > ask or ask-bid > policy.max_spread:
                    reasons.append('SPREAD_INVALID')
                mid = (bid+ask)/2
                if state.last_mid and abs(mid-state.last_mid)*10000 > state.last_mid*policy.max_jump_bps:
                    reasons.append('PRICE_JUMP')
                if not reasons:
                    sources = (state.bid.source_at, state.ask.source_at)
                    age = None if None in sources else max(int((as_of-t).total_seconds()*1000000) for t in sources)
                    quote = Quote(bid, ask, ask-bid, state.bid.sequence, state.ask.sequence,
                            state.bid.received_at, state.ask.received_at, *sources, age, state.data_type, state.contract)
                    state = replace(state, last_mid=mid)
        if reasons:
            state = replace(state, bid=None, ask=None)
    accepted = not reasons
    if quote and quote.source_age_us is None:
        reasons.append('SOURCE_TIME_NOT_PROVIDED')
    return state, ValidatedEvent(event, as_of, accepted, tuple(reasons), quote)
