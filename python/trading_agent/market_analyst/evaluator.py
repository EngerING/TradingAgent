"""Pure assessment of validated local synthetic recipes; no implicit clock or I/O."""
from datetime import datetime, timezone
from decimal import Decimal
from math import isfinite

from ..market import Candle
from ..research_indicators import calculate, settings
from .contracts import (INDICATOR_NAMES, Indicator, Instrument, MarketAssessment,
                        Policy, Provenance, Quality, indicator_unit, indicator_warmups)
from .fixtures import FixtureBar, _generate, is_local_fixture
from .serialization import AnalystError, digest, require, utc


def _indicators(policy, instrument, count, point=None, *, unavailable=False):
    warmups, result = indicator_warmups(policy), []
    for name in INDICATOR_NAMES:
        value = None if point is None else point[name]
        if value is not None:
            require(type(value) in (float, int) and isfinite(value), 'MA_CALCULATION_NONFINITE')
            value = Decimal(str(value))
        unit = indicator_unit(name, instrument)
        status = 'UNAVAILABLE' if unavailable else 'READY' if value is not None else 'WARMUP'
        result.append(Indicator(name, value, unit, warmups[name], count, status))
    return tuple(result)


def _seconds(delta):
    # Integers -> decimal text, independent of the caller's decimal precision.
    micros = (delta.days * 86400 + delta.seconds) * 1000000 + delta.microseconds
    return Decimal(f'{micros // 1000000}.{micros % 1000000:06d}')


def _inspect(bars, instrument, minutes):
    reasons, seen, previous = [], set(), None
    duplicates = discontinuities = 0
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    for bar in bars:
        if bar.instrument != instrument:
            reasons.append('MA_INSTRUMENT_MISMATCH')
        if bar.minutes != minutes:
            reasons.append('MA_TIMEFRAME_MISMATCH')
        if (bar.opened_at - epoch).total_seconds() % (minutes * 60) != 0:
            reasons.append('MA_BAR_ALIGNMENT')
        prices = (bar.open, bar.high, bar.low, bar.close)
        if any(not Decimal('0.00000001') <= p <= Decimal('1e8') for p in prices):
            reasons.append('MA_PRICE_RANGE')
        if bar.high < max(bar.open, bar.close, bar.low) or bar.low > min(bar.open, bar.close, bar.high):
            reasons.append('MA_OHLC')
        if bar.available_at < bar.closed_at:
            reasons.append('MA_AVAILABILITY_BEFORE_CLOSE')
        if bar.opened_at in seen:
            duplicates += 1
            reasons.append('MA_DUPLICATE_BAR')
        seen.add(bar.opened_at)
        if previous is not None:
            gap = (bar.opened_at - previous.closed_at).total_seconds()
            if gap < 0:
                reasons.append('MA_BAR_ORDER')
                discontinuities += 1
            elif gap > 0:
                discontinuities += 1
                reasons.append('MA_MISSING_BARS')
            if bar.available_at < previous.available_at:
                reasons.append('MA_AVAILABILITY_ORDER')
        previous = bar
    return tuple(dict.fromkeys(reasons)), duplicates, discontinuities


def evaluate(source, *, cutoff, policy=None, instrument=None, minutes=60):
    """Return an observation, never a signal. JSON/real data are not accepted sources.

    Future/unavailable bars do not contribute to any output field, including hashes.
    Invalid context (policy, cutoff, expected identity) raises a fixed-code error;
    unavailable, untrusted and invalid sources produce structured assessments.
    """
    cutoff = utc(cutoff)
    policy = Policy() if policy is None else policy
    instrument = Instrument() if instrument is None else instrument
    require(type(policy) is Policy and type(instrument) is Instrument, 'MA_CONTEXT_TYPE')
    policy.__post_init__()
    instrument.__post_init__()
    require(type(minutes) is int and minutes in (15, 60, 240), 'MA_TIMEFRAME')

    def output(status, quality, *, bars=(), provenance=None, point=None):
        valid = status in ('COMPLETE', 'INSUFFICIENT_DATA', 'STALE_DATA')
        known_period = bool(bars) and valid
        return MarketAssessment(
            instrument, minutes, cutoff,
            bars[0].opened_at if known_period else None,
            bars[-1].closed_at if known_period else None,
            bars[-1].closed_at if known_period else None,
            max(b.available_at for b in bars) if known_period else None,
            Provenance() if provenance is None else provenance,
            _indicators(policy, instrument, quality.evaluated_bars or 0, point, unavailable=not valid),
            point['trend'] if status == 'COMPLETE' else 'UNKNOWN',
            point['volatility'] if status == 'COMPLETE' else 'UNKNOWN',
            quality, policy, policy.sha256(), status)

    if source is None:
        return output('SOURCE_UNAVAILABLE', Quality(reasons=('MA_SOURCE_UNAVAILABLE',)))
    if not is_local_fixture(source):
        return output('UNVERIFIED_PROVENANCE', Quality(reasons=('MA_LOCAL_FIXTURE_REQUIRED',)))
    try:
        source.recipe.__post_init__()
        require(type(source.bars) is tuple and len(source.bars) <= policy.max_bars, 'MA_BAR_LIMIT')
        for bar in source.bars:
            require(type(bar) is FixtureBar, 'MA_BAR_TYPE')
            bar.__post_init__()
            require(type(bar.minutes) is int and bar.minutes in (15, 60, 240), 'MA_TIMEFRAME')
            require(2000 <= bar.opened_at.year <= 2100, 'MA_BAR_TIME_RANGE')
        bars = tuple(b for b in source.bars if b.closed_at <= cutoff and b.available_at <= cutoff)
        expected = tuple(b for b in _generate(source.recipe)
                         if b.closed_at <= cutoff and b.available_at <= cutoff)
    except AnalystError as exc:
        return output('VALIDATION_ERROR', Quality(reasons=(str(exc),)))

    reasons, duplicates, discontinuities = _inspect(bars, instrument, minutes)
    issues = list(reasons)
    missing = len({b.opened_at for b in expected} - {b.opened_at for b in bars})
    if missing:
        issues.append('MA_MISSING_BARS')
    if source.recipe.instrument != instrument:
        issues.append('MA_INSTRUMENT_MISMATCH')
    if source.recipe.minutes != minutes:
        issues.append('MA_TIMEFRAME_MISMATCH')
    if bars != expected:
        issues.append('MA_FIXTURE_CONTENT_MISMATCH')
    if issues:
        return output('VALIDATION_ERROR', Quality(len(bars), missing, duplicates, discontinuities,
                                                 None, tuple(dict.fromkeys(issues))))

    recipe_evidence = source.recipe.to_dict()
    del recipe_evidence['count']
    provenance = Provenance('SYNTHETIC_TEST_FIXTURE', 'fixture-v1:' + digest(recipe_evidence),
                            digest([b.to_dict() for b in bars]), 'NOT_APPLICABLE_SYNTHETIC')
    if not bars:
        return output('INSUFFICIENT_DATA', Quality(0, 0, 0, 0, None, ('MA_NO_AVAILABLE_BARS',)),
                      provenance=provenance)

    config = settings({name: (float(getattr(policy, name)) if type(getattr(policy, name)) is Decimal
                              else getattr(policy, name)) for name in (
        'ema_fast', 'ema_slow', 'rsi', 'macd_fast', 'macd_slow', 'macd_signal', 'atr',
        'volatility', 'slope', 'trend_gap_atr', 'trend_slope_atr',
        'high_volatility_atr_ratio', 'low_volatility_atr_ratio')})
    candles = [Candle(b.opened_at, b.minutes, float(b.open), float(b.high), float(b.low), float(b.close))
               for b in bars]
    try:
        point = calculate(candles, config)[-1]
        _indicators(policy, instrument, len(bars), point)
    except (ArithmeticError, ValueError):
        return output('VALIDATION_ERROR', Quality(len(bars), 0, 0, 0, None,
                      ('MA_CALCULATION_INVALID',)), provenance=provenance)
    age = _seconds(cutoff - bars[-1].closed_at)
    status, reasons = ('COMPLETE', ()) if point['status'] == 'READY' else (
        'INSUFFICIENT_DATA', ('MA_INDICATOR_WARMUP',))
    if age > policy.max_age_seconds:
        status, reasons = 'STALE_DATA', (*reasons, 'MA_STALE_BAR')
    return output(status, Quality(len(bars), 0, 0, 0, age, reasons), bars=bars,
                  provenance=provenance, point=point)
