"""Typed, deeply immutable configuration models (pydantic v2).

Every model forbids unknown keys and is frozen; sequences are tuples and mappings are read-only
``MappingProxyType`` views. Percentages are fractions in [0, 1). Money, percentage and count
fields use strict types (no bool -> int, no str -> float coercion).
"""

from __future__ import annotations

import datetime as dt
import itertools
import re
from collections.abc import Mapping
from types import MappingProxyType
from typing import Annotated, Any, Literal, TypeVar

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    GetCoreSchemaHandler,
    PlainSerializer,
    field_validator,
    model_validator,
)
from pydantic_core import CoreSchema, core_schema

Horizon = Literal["short", "medium", "long"]
Status = Literal["VERIFY", "confirmed", "provisional"]
Coverage = Literal["complete", "partial"]

Pct = Annotated[float, Field(ge=0, lt=1, strict=True)]
PositiveFloat = Annotated[float, Field(gt=0, strict=True)]
PositiveInt = Annotated[int, Field(ge=1, strict=True)]
NonNegInt = Annotated[int, Field(ge=0, strict=True)]
StrictInt = Annotated[int, Field(strict=True)]
Flag = Annotated[bool, Field(strict=True)]
Name = Annotated[str, Field(pattern=r"^[a-z0-9_]+$")]
Span = Annotated[str, Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d-([01]\d|2[0-3]):[0-5]\d$")]

_CLOCK = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

K = TypeVar("K")
V = TypeVar("V")


def _freeze_map(value: Mapping[K, V]) -> Mapping[K, V]:
    return MappingProxyType(dict(value))


def _deep_freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({k: _deep_freeze(v) for k, v in value.items()})
    if isinstance(value, list | tuple):
        return tuple(_deep_freeze(v) for v in value)
    return value


def _thaw(value: Any) -> Any:
    """Inverse of :func:`_deep_freeze`, for serialization."""
    if isinstance(value, Mapping):
        return {k: _thaw(v) for k, v in value.items()}
    if isinstance(value, tuple):
        return [_thaw(v) for v in value]
    return value


class _FrozenMapMarker:
    """Annotated marker: validate as a mapping, expose it read-only, serialize as a dict."""

    def __get_pydantic_core_schema__(
        self, source: Any, handler: GetCoreSchemaHandler
    ) -> CoreSchema:
        inner = handler(source)
        return core_schema.no_info_after_validator_function(
            _freeze_map,
            inner,
            serialization=core_schema.wrap_serializer_function_ser_schema(
                lambda value, nxt: nxt(dict(value)), schema=inner
            ),
        )


FrozenMap = _FrozenMapMarker()


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


# ------------------------------------------------------------------ defaults.yaml


class Project(_Model):
    timezone: str
    backfill_start: dt.date
    market: Name
    universe: Name


class ShortBook(_Model):
    capital_vnd: Annotated[int, Field(gt=0, strict=True)]
    decision_day: Literal["last_trading_day_of_week"]


class MediumBook(_Model):
    capital_vnd: Annotated[int, Field(gt=0, strict=True)]
    decision_day: Literal["last_trading_day_of_month"]
    tranches: PositiveInt


class LongBook(_Model):
    capital_vnd: Annotated[int, Field(gt=0, strict=True)]
    decision_day: Literal["last_trading_day_of_month"]


class Books(_Model):
    short: ShortBook
    medium: MediumBook
    long: LongBook


class Slippage(_Model):
    round_lot: Pct
    odd_lot: Pct


class Costs(_Model):
    brokerage_fee_pct: Pct
    sales_tax_pct: Pct
    slippage_pct: Slippage


class Risk(_Model):
    risk_per_position_pct: Pct
    atr_stop_multiple: PositiveFloat
    max_positions: PositiveInt
    max_weight_per_ticker: Pct
    circuit_breaker_drawdown_pct: Pct
    rebalance_threshold_pct: Pct
    vol_target_annual: PositiveFloat | None


class Gate1(_Model):
    dsr_min: Annotated[float, Field(ge=0, le=1, strict=True)]
    pbo_max: Annotated[float, Field(ge=0, le=1, strict=True)]
    min_periods: Annotated[Mapping[Horizon, PositiveInt], FrozenMap]


class Gate2(_Model):
    spa_alpha: Annotated[float, Field(gt=0, lt=1, strict=True)]
    bootstrap_reps: PositiveInt
    block_size: Annotated[Mapping[Horizon, PositiveInt], FrozenMap]


class WeightSettings(_Model):
    window: PositiveInt | None
    lambda_: Annotated[float, Field(ge=0, le=1, strict=True, alias="lambda")]
    eta: Annotated[float, Field(ge=0, strict=True)] | None
    max_weight: Annotated[float, Field(gt=0, le=1, strict=True)]


class Decay(_Model):
    short_window: PositiveInt
    medium_window: PositiveInt


class Lab(_Model):
    seed: StrictInt
    gate1: Gate1
    gate2: Gate2
    mcs_alpha: Annotated[float, Field(gt=0, lt=1, strict=True)]
    weights: Annotated[Mapping[Horizon, WeightSettings], FrozenMap]
    decay: Decay
    challenger_min_periods: Annotated[Mapping[Horizon, PositiveInt], FrozenMap]


class RiskFree(_Model):
    source: str
    annual_rate: Pct | None


class Benchmarks(_Model):
    market_indices: tuple[str, ...]
    equal_weight_universe: Flag
    sector_index: Flag
    risk_free: RiskFree
    naive_selectors: tuple[str, ...]


class Regime(_Model):
    name: str
    start: dt.date
    end: dt.date

    @model_validator(mode="after")
    def _ordered(self) -> Regime:
        if self.end < self.start:
            raise ValueError("end must not be before start")
        return self


class Stress(_Model):
    cost_multipliers: tuple[Annotated[float, Field(ge=1, strict=True)], ...]
    fill_delay_sessions: tuple[NonNegInt, ...]
    max_participation_adv20: Annotated[float, Field(gt=0, le=1, strict=True)]
    param_perturbation_pct: Pct
    regimes: tuple[Regime, ...]


class News(_Model):
    collect_raw: Flag
    use_in_signals: Flag
    cutoff_time: str

    @field_validator("cutoff_time")
    @classmethod
    def _check_clock(cls, value: str) -> str:
        if not _CLOCK.match(value):
            raise ValueError("cutoff_time must look like HH:MM")
        return value


class Notify(_Model):
    console: Flag
    telegram: Flag


class SyntheticConfig(_Model):
    seed: StrictInt
    start: dt.date
    corporate_actions_per_ticker_per_year: Annotated[float, Field(ge=0, le=12, strict=True)]
    suspension_probability: Pct


class YahooConfig(_Model):
    symbol_suffix: Annotated[str, Field(pattern=r"^(\.[A-Z]{1,4})?$")]
    max_requests_per_minute: PositiveInt
    retries: NonNegInt
    backoff_seconds: PositiveFloat
    final_after: Annotated[str, Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")]  # Asia/Ho_Chi_Minh


class DataConfig(_Model):
    source: Name
    synthetic: SyntheticConfig
    yahoo: YahooConfig


# ------------------------------------------------------------------ markets/<name>.yaml


class _RuleMeta(_Model):
    status: Literal["VERIFY", "confirmed"]
    source: str | None = None
    note: str | None = None


class PctRule(_RuleMeta):
    value: Pct


class PositiveIntRule(_RuleMeta):
    value: PositiveInt


class NonNegIntRule(_RuleMeta):
    value: NonNegInt


class FlagRule(_RuleMeta):
    value: Flag


class OddLotValue(_Model):
    min: Annotated[int, Field(ge=1, le=99, strict=True)]
    max: Annotated[int, Field(ge=1, le=99, strict=True)]
    limit_orders_only: Flag

    @model_validator(mode="after")
    def _ordered(self) -> OddLotValue:
        if self.min > self.max:
            raise ValueError("min must not exceed max")
        return self


class OddLotRule(_RuleMeta):
    value: OddLotValue


TickBand = tuple[NonNegInt, PositiveInt]  # (price_from_vnd, tick_vnd)


class TickSizesRule(_RuleMeta):
    value: tuple[TickBand, ...]

    @field_validator("value")
    @classmethod
    def _check_bands(cls, value: tuple[TickBand, ...]) -> tuple[TickBand, ...]:
        if not value or value[0][0] != 0:
            raise ValueError("tick bands must start at price 0")
        prices = [price for price, _ in value]
        if any(b <= a for a, b in itertools.pairwise(prices)):
            raise ValueError("tick bands must have strictly ascending prices")
        return value


class SessionTimes(_Model):
    ato: Span
    continuous: tuple[Span, ...]
    atc: Span


class SessionsRule(_RuleMeta):
    value: SessionTimes


class HoseRules(_Model):
    earliest_sell_session_offset: NonNegIntRule
    price_limit_pct: PctRule
    round_lot: PositiveIntRule
    odd_lot: OddLotRule
    tick_sizes: TickSizesRule
    sessions: SessionsRule
    sales_tax_pct: PctRule
    short_selling: FlagRule
    intraday_t0: FlagRule


def holiday_date_problem(year: int, day: dt.date) -> str | None:
    """Why ``day`` is not a valid holiday of ``year`` (weekdays inside the year only)."""
    if day.year != year:
        return f"{day} is not inside year {year}"
    if day.weekday() >= 5:
        return f"{day} falls on a weekend"
    return None


class HolidayDay(_Model):
    date: dt.date
    name: Annotated[str, Field(min_length=1)]
    status: Status
    source: Annotated[str, Field(min_length=1)]


class HolidayYear(_Model):
    coverage: Coverage
    days: tuple[HolidayDay, ...]


class Market(_Model):
    market: Name
    currency: Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
    rules: HoseRules
    holidays: Annotated[Mapping[int, HolidayYear], FrozenMap]

    # Weekday / in-year checks need every day to have parsed. `load_config` also runs them on
    # the raw data so they are reported alongside field errors on other days.
    @field_validator("holidays")
    @classmethod
    def _check_holidays(cls, value: Mapping[int, HolidayYear]) -> Mapping[int, HolidayYear]:
        problems: list[str] = []
        for year, block in value.items():
            for index, day in enumerate(block.days):
                problem = holiday_date_problem(year, day.date)
                if problem:
                    problems.append(f"@{year}.days.{index}.date|{problem}")
        if problems:
            raise ValueError("\n".join(problems))
        return value


# ------------------------------------------------------------------ universes/<name>.yaml


class Membership(_Model):
    effective_from: dt.date
    effective_to: dt.date | None
    tickers: Annotated[tuple[str, ...], Field(min_length=1)]
    source_url: str | None


class KnownExit(_Model):
    ticker: str
    last_member_date: dt.date
    source_url: str | None


class Universe(_Model):
    universe: Name
    index: str
    sector: str
    review_months: tuple[Annotated[int, Field(ge=1, le=12, strict=True)], ...]
    membership: tuple[Membership, ...]
    known_exits: tuple[KnownExit, ...]


# ------------------------------------------------------------------ root


class AppConfig(_Model):
    project: Project
    books: Books
    costs: Costs
    risk: Risk
    lab: Lab
    benchmarks: Benchmarks
    stress: Stress
    strategies: Annotated[Mapping[str, Any], AfterValidator(_deep_freeze), PlainSerializer(_thaw)]
    news: News
    notify: Notify
    data: DataConfig
    market: Market
    universe: Universe

    @model_validator(mode="after")
    def _names_match_project(self) -> AppConfig:
        problems: list[str] = []
        if self.market.market != self.project.market:
            problems.append(
                f"@market.market|{self.market.market!r} does not match "
                f"project.market {self.project.market!r}"
            )
        if self.universe.universe != self.project.universe:
            problems.append(
                f"@universe.universe|{self.universe.universe!r} does not match "
                f"project.universe {self.project.universe!r}"
            )
        if problems:
            raise ValueError("\n".join(problems))
        return self
