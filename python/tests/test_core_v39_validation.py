"""Receipt clocks are not market clocks; no invalid or stale quote becomes LIVE."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D
import unittest

from trading_agent.core_v3.contracts import content_hash
from trading_agent.core_v3.market_observation.contracts import (
    CapturePolicy, ContractIdentity, DataType, Kind, Origin, RawEvent, SessionKind)
from trading_agent.core_v3.market_observation.validation import State, step

AT = datetime(2026, 10, 19, 12, tzinfo=timezone.utc)


def policy(**changes):
    return replace(CapturePolicy('capture-1'), **changes)


def contract():
    return ContractIdentity(12087792, 'EUR', 'CASH', 'USD', 'IDEALPRO', D('.00005'), '0'*64)


def event(seq, kind, *, connection='connection-1', **changes):
    return RawEvent('session-1', connection, 101, seq, kind,
        AT+timedelta(milliseconds=seq*100), seq*100_000_000,
        Origin.FIXTURE, SessionKind.PAPER, **changes)


def prefix():
    return (event(1, Kind.CONNECTED), event(2, Kind.CONTRACT, contract=contract()),
            event(3, Kind.DATA_TYPE, data_type=DataType.LIVE))


def fold(events, rules=None):
    state, values = State(), []
    for raw in events:
        state, value = step(state, raw, rules or policy(), as_of=raw.received_at)
        values.append(value)
    return state, tuple(values)


def prices():
    return prefix()+(event(4, Kind.BID, price_text='1.1000', tick_type=1),
                     event(5, Kind.ASK, price_text='1.1002', tick_type=2))


class QuoteValidationTests(unittest.TestCase):
    def test_valid_pair_preserves_decimal_and_unknown_source_latency(self):
        _, values = fold(prices())
        quote = values[-1].quote
        self.assertEqual(D('.0002'), quote.spread)
        self.assertIsNone(quote.bid_source_at)
        self.assertIsNone(quote.source_age_us)
        self.assertIn('SOURCE_TIME_NOT_PROVIDED', values[-1].reasons)
        self.assertEqual(DataType.LIVE, quote.data_type)

    def test_crossed_nonfinite_zero_and_offgrid_prices_are_retained_but_rejected(self):
        for text in ('1.2', 'NaN', 'Infinity', '-1', '0', '1.100001'):
            raws = prefix()+(event(4, Kind.ASK, price_text='1.1002', tick_type=2),
                              event(5, Kind.BID, price_text=text, tick_type=1))
            _, values = fold(raws)
            self.assertIsNone(values[-1].quote)
            self.assertEqual(text, values[-1].event.price_text)
            self.assertFalse(values[-1].accepted)

    def test_type_change_clears_old_sides_and_delayed_ticks_cannot_be_live(self):
        _, values = fold(prices()+(event(6, Kind.DATA_TYPE, data_type=DataType.DELAYED),
            event(7, Kind.BID, price_text='1.1000', tick_type=66),
            event(8, Kind.ASK, price_text='1.1002', tick_type=67)))
        self.assertIsNone(values[-2].quote)
        self.assertEqual(DataType.DELAYED, values[-1].quote.data_type)
        _, invalid = fold(prefix()+(event(4, Kind.BID, price_text='1.1', tick_type=66),))
        self.assertFalse(invalid[-1].accepted)

    def test_source_future_and_receipt_cutoff_future_fail_closed(self):
        raw = event(4, Kind.BID, price_text='1.1', tick_type=1, source_at=AT+timedelta(days=1))
        state, _ = fold(prefix())
        _, value = step(state, raw, policy(), as_of=raw.received_at)
        self.assertIn('SOURCE_TIME_FUTURE', value.reasons)
        _, value = step(state, raw, policy(), as_of=AT)
        self.assertIn('RECEIPT_FROM_FUTURE', value.reasons)

    def test_sequence_gap_disconnect_and_restart_clear_quotes(self):
        _, values = fold(prices()+(event(7, Kind.BID, price_text='1.1', tick_type=1),))
        self.assertIn('RECEIVE_SEQUENCE_GAP', values[-1].reasons)
        raws = prices()+(event(6, Kind.DISCONNECTED), event(1, Kind.CONNECTED, connection='connection-2'),
                         event(2, Kind.ASK, connection='connection-2', price_text='1.1', tick_type=2))
        _, values = fold(raws)
        self.assertIsNone(values[-1].quote)

    def test_side_age_and_clock_jump_are_not_market_latency(self):
        stale = replace(event(5, Kind.ASK, price_text='1.1002', tick_type=2),
                        received_at=AT+timedelta(seconds=10), monotonic_ns=10_000_000_000)
        _, values = fold(prices()[:-1]+(stale,))
        self.assertIsNone(values[-1].quote)
        self.assertIn('SIDE_RECEIPT_STALE', values[-1].reasons)
        jump = replace(event(5, Kind.ASK, price_text='1.1002', tick_type=2), received_at=AT+timedelta(seconds=10))
        _, values = fold(prices()[:-1]+(jump,))
        self.assertIn('RECEIPT_CLOCK_DISCONTINUITY', values[-1].reasons)
