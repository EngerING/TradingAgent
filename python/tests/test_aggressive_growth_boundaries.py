"""Synthetic boundary/causality tests; never forward market evidence."""
from copy import deepcopy
from datetime import timedelta
import unittest
from unittest.mock import patch

from test_aggressive_growth import ROOT, AT, observation, quote
from trading_agent import aggressive_growth as domain
from trading_agent.aggressive_growth_projection import kronos_view
from trading_agent.aggressive_growth_runner import Experiment, engine_hashes, verify_protocol, read_kronos
from test_aggressive_growth_runner import MemoryJournal


class BoundaryTests(unittest.TestCase):
    def setUp(self):
        self.config = domain.configuration(ROOT)
        self.state = domain.initial_state(self.config, engine_hashes(ROOT), AT.isoformat())

    def test_short_target_zero_or_negative_rejected(self):
        for distance in ('1.107', '1.2'):
            with self.subTest(distance=distance):
                result = domain.assess(self.config, quote(), dict(side='SHORT', stop_distance='.6', target_distance=distance), '100')
                self.assertFalse(result['admitted'])
                self.assertEqual('INVALID_COST_SIZE_OR_GEOMETRY', result['reason'])

    def test_missing_or_invalid_quality_fails_closed(self):
        for quality in (None, {}, {'60': {}}, {'60': {'missing_expected_openings': None}},
                        {'60': {'missing_expected_openings': ['bad-date']}}):
            with self.subTest(quality=quality):
                state = deepcopy(self.state); obs = observation(); obs['analysis']['quality'] = quality
                domain.consume(state, obs, AT + timedelta(seconds=1))
                self.assertTrue(all(p['active'] is None for p in state['portfolios'].values()))
                self.assertEqual('BAR_QUALITY_UNAVAILABLE', state['last_no_trade']['reason'])

    def test_gap_anywhere_in_indicator_input_rejected_without_filling(self):
        obs = observation()
        for tf in ('60', '240'):
            missing = obs['analysis']['normalized'][tf].pop(5)['opened_at']
            obs['analysis']['quality'][tf]['missing_expected_openings'] = [missing]
        original = deepcopy(obs)
        domain.consume(self.state, obs, AT + timedelta(seconds=1))
        self.assertEqual(original, obs)
        self.assertEqual('MISSING_EXPECTED_BARS', self.state['last_no_trade']['reason'])
        self.assertIsNone(self.state['portfolios']['R20']['active'])

    def test_absent_or_invalid_bars_rejected_explicitly(self):
        for change in ('absent', 'timestamp', 'ohlc', 'timeframe'):
            with self.subTest(change=change):
                state = deepcopy(self.state); obs = observation()
                for tf, rows in obs['analysis']['normalized'].items():
                    if change == 'absent': rows.clear()
                    elif change == 'timestamp': rows[-1]['opened_at'] = 'invalid'
                    elif change == 'ohlc': rows[-1]['low'] = '3'
                    else: rows[-1]['minutes'] = 15
                domain.consume(state, obs, AT + timedelta(seconds=1))
                self.assertIsNone(state['portfolios']['R20']['active'])
                self.assertIn(state['last_no_trade']['reason'], ('INVALID_MARKET_DATA', 'INSUFFICIENT_CLOSED_BARS'))

    def test_stop_with_invalid_bars_uses_only_fresh_quote(self):
        domain.consume(self.state, observation(), AT + timedelta(seconds=1))
        obs = observation(at=AT + timedelta(seconds=2))
        for rows in obs['analysis']['normalized'].values(): rows[-1]['low'] = '3'
        events = domain.consume(self.state, obs, AT + timedelta(seconds=2), stop=True)
        self.assertTrue(any(e['kind'] == 'NO_TRADE' and e['detail']['reason'] == 'INVALID_EXIT_BARS' for e in events))
        self.assertEqual('STOPPED', self.state['status'])
        self.assertEqual('OPERATOR_STOP', self.state['portfolios']['R20']['trades'][0]['exit_reason'])

    def test_historical_requires_modeled_quote_and_cannot_run_forward(self):
        journal = MemoryJournal(); e = Experiment(journal, lambda: AT + timedelta(seconds=1))
        e.prepare(self.config, engine_hashes(ROOT), 'HISTORICAL')
        e.observe(observation())
        self.assertEqual('QUOTE_STALE_MISSING_OR_CLOSED', e.state['last_no_trade']['reason'])
        obs = observation(); obs['quote']['type'] = 'HISTORICAL_MODELED'; e.observe(obs)
        self.assertEqual('HISTORICAL', e.state['portfolios']['R20']['active']['run_kind'])
        with self.assertRaisesRegex(ValueError, 'HISTORICAL_CANNOT_RUN_FORWARD'): verify_protocol(e, ROOT)
        domain.consume(self.state, obs, AT + timedelta(seconds=1))
        self.assertIsNone(self.state['portfolios']['R20']['active'])

    def test_replay_clock_cannot_rewind_or_mutate_candidate(self):
        self.state['run_kind'] = 'HISTORICAL'; original = deepcopy(self.state)
        with self.assertRaisesRegex(ValueError, 'OBSERVATION_TIME_CANNOT_REWIND'):
            domain.consume(self.state, observation(), AT - timedelta(seconds=1))
        self.assertEqual(original, self.state)

    def test_warmup_history_cannot_open_before_preregistration_window(self):
        state = domain.initial_state(self.config, 'a'*64, (AT + timedelta(hours=1)).isoformat(), 'HISTORICAL')
        obs = observation(at=AT + timedelta(hours=1)); obs['quote']['type'] = 'HISTORICAL_MODELED'
        domain.consume(state, obs, AT + timedelta(hours=1))
        self.assertIsNone(state['portfolios']['R20']['active'])
        self.assertTrue(all(not d['admitted'] for s in state['signals'] for d in s['decisions'].values()))


def forecast():
    # Native predictor output shape, deliberately synthetic contents.
    return dict(status='RAW_ONLY', latest=dict(prediction_id='synthetic-kronos', timeframe='1H', pred_len=12,
        created_at=AT.isoformat(), candle_timestamp=AT.isoformat(), prediction_start=AT.isoformat(),
        prediction_end=(AT + timedelta(hours=12)).isoformat(), partition='FORWARD',
        consensus={'kronos_direction': 'LONG'}))


class KronosCausalityTests(unittest.TestCase):
    def state_with(self, k):
        s = domain.initial_state(domain.configuration(ROOT), 'a'*64, AT.isoformat())
        obs = observation(); obs['analysis']['normalized']['240'] = []
        domain.consume(s, obs, AT + timedelta(seconds=1), k)
        return s

    def test_native_timeframe_and_horizon_survive_domain_and_match_signal(self):
        s = self.state_with(forecast()); evidence = s['signals'][0]['kronos']
        self.assertEqual(60, evidence['timeframe'])
        self.assertEqual('1H', evidence['source_timeframe'])
        self.assertEqual(12, evidence['horizon_bars'])
        self.assertEqual('AGREE', kronos_view(s, AT + timedelta(seconds=2))['agreement'])
        self.assertEqual('RAW_ONLY', evidence['calibration_state'])
        self.assertIsNone(evidence['calibrated_probability'])

    def test_missing_incompatible_future_or_replay_metadata_never_agrees(self):
        cases = [dict(timeframe=None), dict(pred_len=None), dict(timeframe='4H'), dict(pred_len=0),
                 dict(pred_len=True), dict(pred_len=13), dict(partition='HISTORICAL'),
                 dict(created_at=(AT + timedelta(seconds=2)).isoformat())]
        for changes in cases:
            with self.subTest(changes=changes):
                k = forecast(); k['latest'].update(changes); s = self.state_with(k)
                view = kronos_view(s, AT + timedelta(seconds=3))
                self.assertIsNone(view['agreement']); self.assertIsNone(view['calibratedProbability'])
                self.assertEqual('RAW_ONLY', view['calibration'])

    def test_later_forecast_does_not_replace_frozen_signal_evidence(self):
        s = self.state_with({}); obs = observation(at=AT + timedelta(seconds=3))
        domain.consume(s, obs, AT + timedelta(seconds=3), forecast())
        self.assertIsNone(kronos_view(s, AT + timedelta(seconds=3))['agreement'])

    def test_journal_reader_selects_only_prediction_available_at_decision(self):
        available = forecast()['latest']; future = deepcopy(available)
        future.update(prediction_id='future', created_at=(AT + timedelta(seconds=2)).isoformat())
        with patch('trading_agent.kronos.persistence.PostgreSQLJournal') as journal:
            journal.return_value.read.return_value = dict(events=[dict(kind='PREDICTION', payload=p) for p in (future, available)])
            self.assertEqual(available, read_kronos(ROOT, AT + timedelta(seconds=1))['latest'])

    def test_wrapper_metadata_cannot_override_frozen_forecast(self):
        k = forecast(); k.update(created_at=(AT-timedelta(days=1)).isoformat(), timeframe='4H', direction='SHORT')
        result = domain.kronos_evidence(k, AT + timedelta(seconds=1))
        self.assertEqual(AT.isoformat(), result['created_at'])
        self.assertEqual(60, result['timeframe']); self.assertEqual('LONG', result['direction'])


if __name__ == '__main__': unittest.main()
