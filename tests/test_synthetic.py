from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from vnstratlab.config.loader import load_config
from vnstratlab.config.models import AppConfig
from vnstratlab.data.protocol import TickTable, universe_tickers
from vnstratlab.data.sources.synthetic import SyntheticSource, ex_price

START = date(2020, 1, 1)
END = date(2022, 12, 31)


@pytest.fixture(scope="module")
def cfg(tmp_path_factory: pytest.TempPathFactory) -> AppConfig:
    base = load_config(tmp_path_factory.mktemp("home"))
    return _with(base, start=START)


def _with(
    cfg: AppConfig,
    *,
    seed: int | None = None,
    start: date | None = None,
    suspension: float | None = None,
) -> AppConfig:
    syn = cfg.data.synthetic
    update: dict[str, object] = {}
    if seed is not None:
        update["seed"] = seed
    if start is not None:
        update["start"] = start
    if suspension is not None:
        update["suspension_probability"] = suspension
    new_syn = syn.model_copy(update=update)
    return cfg.model_copy(update={"data": cfg.data.model_copy(update={"synthetic": new_syn})})


@pytest.fixture(scope="module")
def prices(cfg: AppConfig) -> pd.DataFrame:
    return SyntheticSource(cfg).fetch_daily(universe_tickers(cfg), START, END)


@pytest.fixture(scope="module")
def actions(cfg: AppConfig) -> pd.DataFrame:
    return SyntheticSource(cfg).fetch_corporate_actions(universe_tickers(cfg), START, END)


def _hash(frame: pd.DataFrame) -> int:
    return int(pd.util.hash_pandas_object(frame, index=False).sum())


def test_same_seed_same_frames(cfg: AppConfig, prices: pd.DataFrame) -> None:
    again = SyntheticSource(cfg).fetch_daily(universe_tickers(cfg), START, END)
    assert _hash(again) == _hash(prices)
    assert again.equals(prices)


def test_values_do_not_depend_on_later_end_date(cfg: AppConfig, prices: pd.DataFrame) -> None:
    longer = SyntheticSource(cfg).fetch_daily(universe_tickers(cfg), START, date(2023, 6, 30))
    assert longer[longer["date"] <= END].reset_index(drop=True).equals(prices)


def test_frame_shape_and_dtypes(prices: pd.DataFrame) -> None:
    assert list(prices.columns) == [
        "ticker",
        "date",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "ref_price",
        "ceiling",
        "floor",
    ]
    assert all(isinstance(d, date) for d in prices["date"].head(5))
    for col in ("open", "high", "low", "close", "ref_price", "ceiling", "floor"):
        assert prices[col].dtype == np.float64
    assert prices["volume"].dtype == np.int64
    assert (prices["volume"] > 0).all()
    assert not prices.isna().any().any()
    keys = prices[["ticker", "date"]]
    assert not keys.duplicated().any()
    assert prices.equals(prices.sort_values(["ticker", "date"]).reset_index(drop=True))


def test_tickers_include_known_exit(cfg: AppConfig, prices: pd.DataFrame) -> None:
    assert set(prices["ticker"]) == set(universe_tickers(cfg))
    assert "TPB" in set(prices["ticker"])


def test_sessions_follow_calendar(cfg: AppConfig, prices: pd.DataFrame) -> None:
    days = set(prices["date"])
    assert all(d.weekday() < 5 for d in days)
    assert date(2022, 12, 30) in days
    # configured Tet 2026 holidays are not sessions
    tet = SyntheticSource(_with(cfg, suspension=0.0)).fetch_daily(
        ["ACB"], date(2026, 2, 12), date(2026, 2, 24)
    )
    got = set(tet["date"])
    assert date(2026, 2, 13) in got
    assert not any(date(2026, 2, d) in got for d in range(16, 21))
    assert date(2026, 2, 23) in got


def test_prices_on_tick_grid_and_inside_limits(cfg: AppConfig, prices: pd.DataFrame) -> None:
    ticks = TickTable.from_config(cfg)
    for col in ("open", "high", "low", "close", "ceiling", "floor", "ref_price"):
        assert ticks.is_on_grid(prices[col].to_numpy()).all(), col
    assert (prices["close"] <= prices["ceiling"]).all()
    assert (prices["close"] >= prices["floor"]).all()
    for col in ("open", "high", "low"):
        assert (prices[col] <= prices["ceiling"]).all()
        assert (prices[col] >= prices["floor"]).all()
    assert (prices["high"] >= prices[["open", "close"]].max(axis=1)).all()
    assert (prices["low"] <= prices[["open", "close"]].min(axis=1)).all()
    ceiling, floor = ticks.limits(prices["ref_price"].to_numpy())
    assert np.array_equal(ceiling, prices["ceiling"].to_numpy())
    assert np.array_equal(floor, prices["floor"].to_numpy())


def test_ex_price_across_the_50000_boundary(cfg: AppConfig) -> None:
    ticks = TickTable.from_config(cfg)
    # 57,450 / 1.15 = 49,956.5 -> tick 50 below 50,000 -> 49,950
    assert ex_price("stock", 57_450.0, 0.15, ticks) == 49_950.0
    # 51,950 - 2,000 = 49,950
    assert ex_price("cash", 51_950.0, 2_000.0, ticks) == 49_950.0


def test_ex_price_rounds_down_not_to_nearest(cfg: AppConfig) -> None:
    ticks = TickTable.from_config(cfg)
    # 57,590 / 1.15 = 50,078.26; tick is 100 at >= 50,000, so down -> 50,000 (nearest: 50,100)
    assert ex_price("stock", 57_590.0, 0.15, ticks) == 50_000.0
    # 52,090 - 2,000 = 50,090 -> down 50,000 (nearest: 50,100)
    assert ex_price("cash", 52_090.0, 2_000.0, ticks) == 50_000.0


def test_ex_price_hand_computed(cfg: AppConfig) -> None:
    ticks = TickTable.from_config(cfg)
    assert ex_price("cash", 25_300.0, 1_000.0, ticks) == 24_300.0
    # 30,000 / 1.10 = 27,272.7 -> down to the 50-VND tick
    assert ex_price("stock", 30_000.0, 0.10, ticks) == 27_250.0


def test_corporate_actions_cover_both_types(actions: pd.DataFrame) -> None:
    assert list(actions.columns) == ["ticker", "ex_date", "type", "ratio_or_amount"]
    assert {"cash", "stock"} <= set(actions["type"])
    assert (actions["ratio_or_amount"] > 0).all()
    assert all(START <= d <= END for d in actions["ex_date"])


def test_ref_price_on_ex_dates_is_theoretical_ex_price(
    cfg: AppConfig, prices: pd.DataFrame, actions: pd.DataFrame
) -> None:
    ticks = TickTable.from_config(cfg)
    by_ticker = {t: g.reset_index(drop=True) for t, g in prices.groupby("ticker")}
    seen = {"cash": 0, "stock": 0}
    for ev in actions.itertuples():
        g = by_ticker[str(ev.ticker)]
        pos = int(g.index[g["date"] == ev.ex_date][0])
        prev_close = float(g.loc[pos - 1, "close"])
        expected = ex_price(str(ev.type), prev_close, float(ev.ratio_or_amount), ticks)
        assert g.loc[pos, "ref_price"] == expected
        seen[str(ev.type)] += 1
    assert seen["cash"] >= 1
    assert seen["stock"] >= 1
    # and by hand for one event of each type
    cash = actions[actions["type"] == "cash"].iloc[0]
    g = by_ticker[str(cash["ticker"])].reset_index(drop=True)
    pos = int(g.index[g["date"] == cash["ex_date"]][0])
    raw = g.loc[pos - 1, "close"] - cash["ratio_or_amount"]
    assert (
        g.loc[pos, "ref_price"]
        == np.floor(raw / ticks.tick(np.array([raw]))[0]) * (ticks.tick(np.array([raw]))[0])
    )


def test_ref_price_is_previous_close_off_ex_dates(
    prices: pd.DataFrame, actions: pd.DataFrame
) -> None:
    ex = {(str(r.ticker), r.ex_date) for r in actions.itertuples()}
    checked = 0
    for ticker, g in prices.groupby("ticker"):
        g = g.reset_index(drop=True)
        for pos in range(1, len(g)):
            if (str(ticker), g.loc[pos, "date"]) not in ex:
                assert g.loc[pos, "ref_price"] == g.loc[pos - 1, "close"]
                checked += 1
    assert checked > 1000


def test_suspensions_are_missing_rows(cfg: AppConfig) -> None:
    quiet = SyntheticSource(_with(cfg, suspension=0.0))
    busy = SyntheticSource(_with(cfg, suspension=0.3))
    tickers = universe_tickers(cfg)
    n_quiet = len(quiet.fetch_daily(tickers, START, date(2020, 12, 31)))
    n_busy = len(busy.fetch_daily(tickers, START, date(2020, 12, 31)))
    assert n_busy < n_quiet * 0.9


def test_symbols_identity(cfg: AppConfig) -> None:
    assert SyntheticSource(cfg).symbols(["ACB", "VCB"]) == {"ACB": "ACB", "VCB": "VCB"}


def test_unknown_ticker_filtered_out(cfg: AppConfig) -> None:
    frame = SyntheticSource(cfg).fetch_daily(["ACB"], START, date(2020, 3, 31))
    assert set(frame["ticker"]) == {"ACB"}


def test_empty_range_returns_empty_frame(cfg: AppConfig) -> None:
    frame = SyntheticSource(cfg).fetch_daily(["ACB"], date(2019, 1, 1), date(2019, 6, 30))
    assert frame.empty
    assert "close" in frame.columns
