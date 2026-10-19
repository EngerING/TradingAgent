"""Decimal descriptive arithmetic and conditional whole-window bootstrap."""
from decimal import Context, Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_EVEN, localcontext
from hashlib import sha256

from ..contracts import Money, require
from .contracts import Dependence, StatisticalMetrics, UncertaintyEstimate

ZERO = Decimal(0)
QUANTUM = Decimal('0.000000000001')


def analytical(value, rounding=ROUND_HALF_EVEN):
    return value.quantize(QUANTUM, rounding=rounding)


def ratio(numerator, denominator):
    with localcontext(Context(prec=160)):
        return None if denominator == 0 else analytical(numerator / denominator)


def describe(net, gross, currency):
    """Inputs are net and gross closed-trade amounts, never signal counts."""
    require(type(net) is tuple and type(gross) is tuple and len(net) == len(gross) <= 256
            and all(type(v) is Decimal and v.is_finite() for v in net+gross), 'STATISTICAL_SAMPLE_INVALID')
    with localcontext(Context(prec=160)):
        require(all(g >= n for g, n in zip(gross, net)), 'NEGATIVE_COST_FORBIDDEN')
        count = len(net)
        wins, losses = tuple(v for v in net if v > 0), tuple(v for v in net if v < 0)
        total, total_gross = sum(net, ZERO), sum(gross, ZERO)
        mean_win = ratio(sum(wins, ZERO), len(wins))
        mean_loss = ratio(sum(losses, ZERO), len(losses))
        stddev = None
        if count >= 2:
            mean = total/count
            stddev = analytical((sum(((v-mean)**2 for v in net), ZERO)/(count-1)).sqrt())
        sensitive = None
        if count >= 2:
            index = max(range(count), key=lambda i: abs(net[i]))  # earliest tie, fixed before results.
            sensitive = ratio(total-net[index], count-1)
        return StatisticalMetrics(count, len(wins), len(losses), count-len(wins)-len(losses),
            Money(total_gross, currency), Money(total_gross-total, currency), Money(total, currency),
            mean_win, mean_loss, ratio(Decimal(len(wins)), count),
            ratio(sum(wins, ZERO), -sum(losses, ZERO)), ratio(total, count),
            None if mean_win is None or mean_loss is None else ratio(mean_win, -mean_loss), stddev, sensitive)


class _CounterRandom:
    """Versioned SHA-256 rejection sampler, independent of Python/global RNG state."""
    def __init__(self, seed):
        self.seed, self.counter = seed.to_bytes(8, 'big'), 0

    def index(self, size):
        limit = 2**256 - (2**256 % size)
        for _ in range(64):
            value = int.from_bytes(sha256(self.seed+self.counter.to_bytes(8, 'big')).digest(), 'big')
            self.counter += 1
            if value < limit:
                return value % size
        require(False, 'BOOTSTRAP_RANDOM_LIMIT')


def bootstrap(values, *, dependence, seed, replicas, confidence_bps, family_size):
    require(type(values) is tuple and len(values) <= 12 and all(type(v) is Decimal and v.is_finite() for v in values)
            and type(dependence) is Dependence and type(seed) is int and 0 <= seed < 2**63
            and type(replicas) is int and 32 <= replicas <= 512
            and type(confidence_bps) is int and 5000 <= confidence_bps <= 9900
            and type(family_size) is int and 1 <= family_size <= 256, 'BOOTSTRAP_INPUT_INVALID')
    def empty(reason):
        return UncertaintyEstimate(None, None, None, len(values), dependence, replicas, seed,
                                   confidence_bps, family_size, reason)
    if dependence is not Dependence.IID_WINDOW_BLOCKS_ASSUMED:
        return empty('INDEPENDENT_UNITS_NOT_ESTABLISHED')
    if len(values) < 2:
        return empty('INSUFFICIENT_SAMPLE')
    # Bonferroni is conditional on the declared family being complete.
    numerator, denominator = 10000-confidence_bps, 20000*family_size
    if replicas*numerator < denominator:
        return empty('BOOTSTRAP_RESOLUTION_INSUFFICIENT')
    rng, size = _CounterRandom(seed), len(values)
    with localcontext(Context(prec=160)):
        draws = sorted(sum((values[rng.index(size)] for _ in values), ZERO)/size for _ in range(replicas))
        low = (replicas*numerator+denominator-1)//denominator-1
        high = (replicas*(denominator-numerator)+denominator-1)//denominator-1
        return UncertaintyEstimate(analytical(draws[low], ROUND_FLOOR), analytical(draws[high], ROUND_CEILING),
            size, size, dependence, replicas, seed, confidence_bps, family_size,
            'CONDITIONAL_IID_BLOCK_PERCENTILE_INTERVAL')
