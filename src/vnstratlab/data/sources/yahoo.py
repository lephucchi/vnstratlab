"""Yahoo Finance daily prices through the optional ``yfinance`` library (ADR-007, interim).

Prices are split-adjusted (``price_basis = split_adjusted``). The adapter returns frames only;
it never writes files or the store. ``yfinance`` is imported only inside the default fetch
function, so the core install and the tests work without it.

Corporate actions: ``Dividends`` become ``cash`` events (VND per share). ``Stock Splits`` is
Yahoo's factor (1.1 for a 10% bonus issue); it is stored as the bonus fraction
``ratio_or_amount = factor - 1`` (0.10), the one convention of ``corporate_actions`` for all
sources. Factors of 1 or less (reverse splits) are not stored; they are logged and listed in
``warnings``. The fetch function and the sleep
function are injectable, so tests never touch the network or wait.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from datetime import time as dtime
from typing import TYPE_CHECKING

import pandas as pd

from vnstratlab.data.protocol import SourceError, SourceInfo

if TYPE_CHECKING:
    from vnstratlab.config.models import AppConfig

log = logging.getLogger(__name__)

TERMS_URL = "https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html"
INSTALL_HINT = 'Yahoo adapter needs: pip install "vnstratlab[yahoo]"'
# Vietnam has no daylight saving time; a fixed offset avoids a tz-database dependency.
VN_TZ = timezone(timedelta(hours=7), "Asia/Ho_Chi_Minh")

FetchFn = Callable[[str, date, date], pd.DataFrame]
SleepFn = Callable[[float], None]

_PRICE_MAP = {"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"}
_DAILY_COLUMNS = ("ticker", "date", "open", "high", "low", "close", "volume")
_ACTION_COLUMNS = ("ticker", "ex_date", "type", "ratio_or_amount")


class MissingExtraError(SourceError):
    """``yfinance`` is not installed."""


def yfinance_fetch(symbol: str, start: date, end: date) -> pd.DataFrame:
    """Default fetch: one symbol, daily history with dividend and split columns."""
    try:
        import yfinance
    except ImportError as exc:
        raise MissingExtraError(INSTALL_HINT) from exc
    frame: pd.DataFrame = yfinance.Ticker(symbol).history(
        start=start.isoformat(),
        end=(end + timedelta(days=1)).isoformat(),
        auto_adjust=False,
        actions=True,
    )
    return frame


def parse_clock(value: str) -> dtime:
    hour, minute = value.split(":")
    return dtime(int(hour), int(minute))


def vn_now(moment: datetime) -> datetime:
    return moment.astimezone(VN_TZ)


@dataclass
class _Fetched:
    daily: pd.DataFrame
    actions: pd.DataFrame


class YahooSource:
    """``DataSource`` for Yahoo Finance daily bars (interim, split-adjusted, no limits)."""

    # Hooks read by the pipeline (source-agnostic duck typing).
    drop_filler_rows = True

    def __init__(
        self,
        cfg: AppConfig,
        fetch: FetchFn | None = None,
        sleep: SleepFn = time.sleep,
    ) -> None:
        self.info = SourceInfo(
            name="yahoo",
            price_basis="split_adjusted",
            interim=True,
            terms_url=TERMS_URL,
            requires_extra="yahoo",
        )
        opts = cfg.data.yahoo
        self._suffix = opts.symbol_suffix
        self._interval = 60.0 / opts.max_requests_per_minute
        self._retries = opts.retries
        self._backoff = opts.backoff_seconds
        self.final_after = parse_clock(opts.final_after)
        self._fetch = fetch or yfinance_fetch
        # Module the pipeline must find before asking for terms (None when a fetch is injected).
        self.required_module: str | None = "yfinance" if fetch is None else None
        self._sleep = sleep
        self._cache: dict[tuple[tuple[str, ...], date, date], _Fetched] = {}
        self.failures: dict[str, str] = {}
        self.warnings: list[str] = []

    def symbols(self, universe: Sequence[str]) -> dict[str, str]:
        return {t: f"{t}{self._suffix}" for t in universe}

    def fetch_daily(self, tickers: Sequence[str], start: date, end: date) -> pd.DataFrame:
        return self._load(tickers, start, end).daily.copy()

    def fetch_corporate_actions(
        self, tickers: Sequence[str], start: date, end: date
    ) -> pd.DataFrame:
        return self._load(tickers, start, end).actions.copy()

    # ------------------------------------------------------------------ internals

    def _load(self, tickers: Sequence[str], start: date, end: date) -> _Fetched:
        """Fetch every ticker once; daily bars and actions come from the same response."""
        key = (tuple(tickers), start, end)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        self.failures = {}
        self.warnings = []
        daily: list[pd.DataFrame] = []
        actions: list[pd.DataFrame] = []
        for position, (ticker, symbol) in enumerate(self.symbols(tickers).items()):
            if position:
                self._sleep(self._interval)
            try:
                history = self._fetch_with_retries(symbol, start, end)
                prices, events, warns = _convert(ticker, history, start, end)
            except MissingExtraError:
                raise
            except Exception as exc:  # one bad ticker must not stop the others
                self.failures[ticker] = f"{type(exc).__name__}: {exc}"
                log.warning("yahoo: %s failed: %s", ticker, self.failures[ticker])
                continue
            daily.append(prices)
            actions.append(events)
            self.warnings.extend(warns)
        result = _Fetched(_concat(daily, _DAILY_COLUMNS), _concat(actions, _ACTION_COLUMNS))
        self._cache[key] = result
        return result

    def _fetch_with_retries(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        attempt = 0
        while True:
            try:
                return self._fetch(symbol, start, end)
            except MissingExtraError:
                raise
            except Exception:
                if attempt >= self._retries:
                    raise
                self._sleep(self._backoff * 2**attempt)
                attempt += 1


def _concat(frames: list[pd.DataFrame], columns: Sequence[str]) -> pd.DataFrame:
    if not frames:
        return pd.DataFrame({c: [] for c in columns})
    return pd.concat(frames, ignore_index=True)


def _to_dates(index: pd.Index) -> list[date]:
    out: list[date] = []
    for stamp in pd.DatetimeIndex(index):
        moment = pd.Timestamp(stamp)
        if moment.tzinfo is not None:
            moment = moment.tz_convert(VN_TZ)
        out.append(moment.date())
    return out


def _convert(
    ticker: str, history: pd.DataFrame, start: date, end: date
) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    """Yahoo history -> (source frame, action frame, warnings). ``Adj Close`` is ignored."""
    if history.empty:
        return _concat([], _DAILY_COLUMNS), _concat([], _ACTION_COLUMNS), []
    missing = [c for c in _PRICE_MAP if c not in history.columns]
    if missing:
        raise SourceError(f"yahoo frame for {ticker} is missing columns: {', '.join(missing)}")
    dates = _to_dates(history.index)
    frame = history.reset_index(drop=True)
    frame["date"] = dates
    frame = frame[[start <= d <= end for d in dates]].reset_index(drop=True)
    prices = frame[["date", *_PRICE_MAP]].rename(columns=_PRICE_MAP)
    prices.insert(0, "ticker", ticker)
    rows: list[tuple[str, date, str, float]] = []
    warns: list[str] = []
    for column, kind in (("Dividends", "cash"), ("Stock Splits", "stock")):
        if column not in frame.columns:
            continue
        values = pd.to_numeric(frame[column]).fillna(0.0)
        for day, value in zip(frame["date"], values, strict=True):
            if value <= 0:
                continue
            if kind == "stock":
                if value <= 1.0:  # reverse split: not a stock dividend, do not store it
                    message = f"{ticker} {day}: ignored split factor {value} (reverse split)"
                    log.warning("yahoo: %s", message)
                    warns.append(message)
                    continue
                value = value - 1.0  # factor 1.1 -> bonus fraction 0.10
            rows.append((ticker, day, kind, round(float(value), 10)))
    events = pd.DataFrame(rows, columns=list(_ACTION_COLUMNS))
    return prices[list(_DAILY_COLUMNS)], events, warns


def build(cfg: AppConfig) -> YahooSource:
    return YahooSource(cfg)
