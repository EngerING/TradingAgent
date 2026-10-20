"""Synthetic recipes only. No import path for external bars or provider claims."""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext

from .contracts import Instrument
from .serialization import Record, require

FIXTURE_VERSION = 'MARKET_ANALYST_SYNTHETIC_RECIPE_V1'
_CREATED_HERE = object()
_CONTEXT = Context(prec=34, rounding=ROUND_HALF_EVEN)


@dataclass(frozen=True, slots=True)
class FixtureRecipe(Record):
    start: datetime
    count: int = 80
    instrument: Instrument = field(default_factory=Instrument)
    minutes: int = 60
    pattern: str = 'RISING'
    base_price: Decimal = Decimal('1.1')
    step: Decimal = Decimal('0.0001')
    half_range: Decimal = Decimal('0.0001')
    availability_lag_seconds: int = 0
    generator_version: str = FIXTURE_VERSION

    def __post_init__(self):
        Record.__post_init__(self)
        require(self.generator_version == FIXTURE_VERSION, 'MA_FIXTURE_VERSION')
        require(0 <= self.count <= 4096 and self.minutes in (15, 60, 240), 'MA_FIXTURE_LIMIT')
        require(self.pattern in ('RISING', 'FALLING', 'FLAT', 'ALTERNATING'), 'MA_FIXTURE_PATTERN')
        require(Decimal('0.001') <= self.base_price <= 1000
                and Decimal('0') <= self.step <= 1
                and Decimal('0.00000001') <= self.half_range <= 1, 'MA_FIXTURE_PRICE')
        require(0 <= self.availability_lag_seconds <= 86400, 'MA_FIXTURE_AVAILABILITY')
        epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
        require(self.start.microsecond == 0
                and (self.start - epoch).total_seconds() % (self.minutes * 60) == 0,
                'MA_FIXTURE_ALIGNMENT')
        require(2000 <= self.start.year <= 2090, 'MA_FIXTURE_DATE')
        with localcontext(_CONTEXT):
            lowest = (self.base_price - self.step * max(0, self.count - 1)
                      if self.pattern == 'FALLING' else self.base_price)
            require(lowest > self.half_range, 'MA_FIXTURE_PRICE')


@dataclass(frozen=True, slots=True)
class FixtureBar(Record):
    instrument: Instrument
    opened_at: datetime
    minutes: int
    available_at: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal

    @property
    def closed_at(self):
        return self.opened_at + timedelta(minutes=self.minutes)


@dataclass(frozen=True, slots=True)
class SyntheticFixture:
    """In-process handle, deliberately not a deserializable market dataset."""
    recipe: FixtureRecipe
    bars: tuple[FixtureBar, ...]
    _seal: object = field(default=None, repr=False, compare=False)


def _generate(recipe):
    bars = []
    with localcontext(_CONTEXT):
        for i in range(recipe.count):
            offset = (recipe.step * i if recipe.pattern == 'RISING'
                      else -recipe.step * i if recipe.pattern == 'FALLING'
                      else recipe.step * (i % 2) if recipe.pattern == 'ALTERNATING'
                      else Decimal('0'))
            price = recipe.base_price + offset
            opened = recipe.start + timedelta(minutes=recipe.minutes * i)
            available = opened + timedelta(minutes=recipe.minutes,
                                            seconds=recipe.availability_lag_seconds)
            bars.append(FixtureBar(recipe.instrument, opened, recipe.minutes, available,
                                   price, price + recipe.half_range, price - recipe.half_range, price))
    return tuple(bars)


def make_fixture(recipe):
    require(type(recipe) is FixtureRecipe, 'MA_RECIPE_REQUIRED')
    recipe.__post_init__()
    return SyntheticFixture(recipe, _generate(recipe), _CREATED_HERE)


def is_local_fixture(value):
    return (type(value) is SyntheticFixture and value._seal is _CREATED_HERE
            and type(value.recipe) is FixtureRecipe)
