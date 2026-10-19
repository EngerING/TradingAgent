"""Observational causality, uncertainty and no synthetic-backtest promotion."""
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal as D
from pathlib import Path
import tempfile
import unittest

from trading_agent.core_v3.contracts import ContractError
from trading_agent.core_v3.market_observation.contracts import Origin, SessionKind, Kind, DataType
from trading_agent.core_v3.market_observation.journal import Journal
from trading_agent.core_v3.market_observation.shadow import ShadowSpec, observe
from test_core_v39_validation import prices, event, policy, AT


def spec(**changes):
    return replace(ShadowSpec('quote-hypothesis-1', 1, 'BID_GT', D('1.09'), 'LONG'), **changes)


class ShadowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.j = Journal(Path(self.tmp.name)/'observations.sqlite', policy(), 'session-1', Origin.FIXTURE, SessionKind.PAPER)
        for raw in prices():
            self.j.append(raw, as_of=raw.received_at)

    def tearDown(self):
        self.j.close()
        self.tmp.cleanup()

    def test_default_rejects_unknown_source_time_and_explicit_hypothesis_records_it(self):
        result = observe(self.j, spec(), cutoff=AT+timedelta(seconds=1))
        self.assertEqual('NO_TRADE', result.signals[-1].hypothetical_direction)
        self.assertIn('SOURCE_AGE_UNKNOWN', result.signals[-1].uncertainty)
        accepted = observe(self.j, spec(allow_unknown_source_time=True), cutoff=AT+timedelta(seconds=1))
        signal = accepted.signals[-1]
        self.assertEqual('LONG', signal.hypothetical_direction)
        self.assertEqual((4,5), signal.available_sequences)
        self.assertEqual(5, signal.causal_sequence)
        self.assertEqual('NO_TRADE', accepted.action)
        self.assertFalse(accepted.execution_authorized)
        self.assertFalse(accepted.statistically_validated)

    def test_later_conditions_are_separate_and_replay_is_deterministic(self):
        rules = spec(allow_unknown_source_time=True)
        first = observe(self.j, rules, cutoff=AT+timedelta(seconds=1))
        raw = event(6, Kind.BID, price_text='1.1001', tick_type=1)
        self.j.append(raw, as_of=raw.received_at)
        later = observe(self.j, rules, cutoff=AT+timedelta(seconds=1))
        self.assertEqual(first.signals[-1], later.signals[-2])
        self.assertTrue(all(item.observed_sequence > item.signal_sequence for item in later.subsequent))
        self.assertEqual(later.to_json(), observe(self.j, rules, cutoff=AT+timedelta(seconds=1)).to_json())
        self.assertNotIn('pnl', later.to_json().lower())
        self.assertNotIn('fill', later.to_json().lower())

    def test_future_receipts_do_not_leak_at_cutoff(self):
        value = observe(self.j, spec(allow_unknown_source_time=True), cutoff=AT+timedelta(milliseconds=450))
        self.assertFalse(any(signal.hypothetical_direction == 'LONG' for signal in value.signals))
        self.assertTrue(all(signal.generated_at <= AT+timedelta(milliseconds=450) for signal in value.signals))

    def test_delayed_frozen_gap_and_invalid_feed_never_yield_direction(self):
        for index, raw in enumerate((event(6,Kind.DATA_TYPE,data_type=DataType.FROZEN),
                event(7,Kind.BID,price_text='1.1',tick_type=1), event(8,Kind.ASK,price_text='1.1002',tick_type=2),
                event(9,Kind.GAP))):
            self.j.append(raw, as_of=raw.received_at)
        value = observe(self.j, spec(allow_unknown_source_time=True), cutoff=AT+timedelta(seconds=2))
        self.assertEqual('NO_TRADE', value.signals[-1].hypothetical_direction)
        self.assertEqual('NO_TRADE', value.signals[-2].hypothetical_direction)

    def test_only_exact_verified_journal_and_closed_hypothesis(self):
        with self.assertRaises(ContractError):
            observe({'allowed':True}, spec(), cutoff=AT)
        for changes in ({'operator':'eval'}, {'direction':'BUY'}, {'threshold':1.1}, {'version':0}):
            with self.assertRaises(ContractError):
                spec(**changes)

    def test_source_timestamp_stale_blocks_even_with_fresh_receipt(self):
        rules = spec(allow_unknown_source_time=True, max_source_age_ms=1000)
        # Same known, old source time on both sides; arrival time is fresh.
        for seq, kind, text, tick in ((6,Kind.BID,'1.1000',1),(7,Kind.ASK,'1.1002',2)):
            raw = event(seq,kind,price_text=text,tick_type=tick,source_at=AT-timedelta(minutes=1))
            self.j.append(raw, as_of=raw.received_at)
        value = observe(self.j,rules,cutoff=AT+timedelta(seconds=1))
        self.assertEqual('NO_TRADE',value.signals[-1].hypothetical_direction)
        self.assertIn('SOURCE_TOO_OLD',value.signals[-1].uncertainty)
