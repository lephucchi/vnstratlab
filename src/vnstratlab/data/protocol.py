"""The ``DataSource`` protocol, source metadata, the registry and HOSE tick/limit helpers.

Adapters return a *source frame* and never write files or the store. The registry imports
adapters lazily so the core install works without any source library.
"""

from __future__ import annotations

import importlib
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Literal, Protocol

import numpy as np
import numpy.typing as npt
import pandas as pd

if TYPE_CHECKING:
    from vnstratlab.config.models import AppConfig

PriceBasis = Literal["raw", "split_adjusted", "synthetic"]
FloatArray = npt.NDArray[np.float64]

REQUIRED_COLUMNS = ("ticker", "date", "open", "high", "low", "close", "volume")
OPTIONAL_COLUMNS = ("ref_price", "ceiling", "floor")


class SourceError(RuntimeError):
    """A data source or the market store refused an operation."""


@dataclass(frozen=True)
class SourceInfo:
    name: str
    price_basis: PriceBasis
    interim: bool
    terms_url: str | None
    requires_extra: str | None


class DataSource(Protocol):
    """A market-data adapter. Returns frames; never writes files or the store."""

    info: SourceInfo

    def symbols(self, universe: Sequence[str]) -> dict[str, str]:
        """Map each universe ticker to the source's own symbol."""
        ...

    def fetch_daily(self, tickers: Sequence[str], start: date, end: date) -> pd.DataFrame:
        """Source frame: ticker, date, open, high, low, close, volume (+ optional limits)."""
        ...

    def fetch_corporate_actions(
        self, tickers: Sequence[str], start: date, end: date
    ) -> pd.DataFrame:
        """Frame: ticker, ex_date, type, ratio_or_amount."""
        ...


# name -> "module:factory"; adapters are imported only when requested.
_REGISTRY: dict[str, str] = {
    "synthetic": "vnstratlab.data.sources.synthetic:build",
    "yahoo": "vnstratlab.data.sources.yahoo:build",
}


def source_names() -> list[str]:
    return sorted(_REGISTRY)


def get_source(name: str, cfg: AppConfig) -> DataSource:
    """Build the named adapter, importing it lazily. Unknown names raise ``SourceError``."""
    target = _REGISTRY.get(name)
    if target is None:
        raise SourceError(f"unknown source {name!r}; available: {', '.join(source_names())}")
    module_name, factory_name = target.split(":")
    module = importlib.import_module(module_name)
    source: DataSource = getattr(module, factory_name)(cfg)
    return source


def universe_tickers(cfg: AppConfig) -> list[str]:
    """Membership tickers plus known exits (avoids survivorship bias), sorted."""
    found = {t for m in cfg.universe.membership for t in m.tickers}
    found.update(e.ticker for e in cfg.universe.known_exits)
    return sorted(found)


class TickTable:
    """HOSE tick bands and daily price limits (vectorised, float VND)."""

    def __init__(self, bands: Sequence[tuple[int, int]], limit_pct: float) -> None:
        self._from = np.array([b[0] for b in bands], dtype=np.float64)
        self._tick = np.array([b[1] for b in bands], dtype=np.float64)
        self.limit_pct = limit_pct

    @classmethod
    def from_config(cls, cfg: AppConfig) -> TickTable:
        rules = cfg.market.rules
        return cls(rules.tick_sizes.value, rules.price_limit_pct.value)

    def tick(self, price: FloatArray) -> FloatArray:
        index = np.searchsorted(self._from, price, side="right") - 1
        return self._tick[np.clip(index, 0, len(self._tick) - 1)]

    def nearest(self, value: FloatArray) -> FloatArray:
        tick = self.tick(value)
        return np.round(value / tick) * tick

    def round_down(self, value: FloatArray) -> FloatArray:
        tick = self.tick(value)
        return np.floor(np.round(value / tick, 6)) * tick

    def round_up(self, value: FloatArray) -> FloatArray:
        tick = self.tick(value)
        return np.ceil(np.round(value / tick, 6)) * tick

    def is_on_grid(self, price: FloatArray) -> npt.NDArray[np.bool_]:
        tick = self.tick(price)
        return np.isclose(np.round(price / tick) * tick, price, rtol=0, atol=1e-6)

    def limits(self, ref: FloatArray) -> tuple[FloatArray, FloatArray]:
        """``(ceiling, floor)`` from a reference price: ceiling down, floor up to the tick."""
        ceiling = self.round_down(np.round(ref * (1 + self.limit_pct), 6))
        floor = self.round_up(np.round(ref * (1 - self.limit_pct), 6))
        return ceiling, floor
