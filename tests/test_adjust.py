"""Adjusted and reconstructed execution prices (P1-T06). Synthetic fixtures only.

HOSE ticks: 10 below 10,000, 50 from 10,000, 100 from 50,000; daily limit +/- 7 %.
Sessions: D[0] Fri 2026-10-30, D[1] Mon 11-02, D[2] Tue 11-03, D[3] Wed 11-04, D[4] Thu 11-05.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import pytest

from engine_helpers import make_days
from vnstratlab.calendar import TradingCalendar
from vnstratlab.config.loader import load_config
from vnstratlab.config.models import AppConfig
from vnstratlab.data.adjust import (
    build_series,
    execution_actions,
    precondition_tolerance,
)
from vnstratlab.data.pipeline import load_execution_frame, rebuild
from vnstratlab.data.protocol import SourceError, TickTable, universe_tickers
from vnstratlab.data.sources.synthetic import SyntheticSource
from vnstratlab.data.store import MarketStore, RunRecord
from vnstratlab.engine import make_params, run_simulation

TICKS = TickTable([(0, 10), (10_000, 50), (50_000, 100)], 0.07)
D = make_days(5)
NOW = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)


def bars(
    ticker: str,
    closes: list[float],
    basis: str,
    days: list[date] | None = None,
    volume: int = 1_000_000,
    source: str = "yahoo",
) -> pd.DataFrame:
    """open = high = low = close; ref = previous close (the first row keeps its own close)."""
    days = days or D[: len(closes)]
    ref = [closes[0], *closes[:-1]]
    ceiling, floor = TICKS.limits(np.array(ref, dtype=float))
    return pd.DataFrame(
        {
            "ticker": ticker,
            "date": days,
            "open": closes,
            "high": closes,
            "low": closes,
            "close": closes,
            "volume": volume,
            "value": 0.0,
            "ref_price": ref,
            "ceiling": ceiling,
            "floor": floor,
            "source": source,
            "price_basis": basis,
            "derived_limits": basis == "split_adjusted",
        }
    )


def events(*rows: tuple[str, date, str, float], source: str = "yahoo") -> pd.DataFrame:
    return pd.DataFrame(
        [(t, d, k, a, source) for t, d, k, a in rows],
        columns=["ticker", "ex_date", "type", "ratio_or_amount", "source"],
    )


# Hand case used by criteria 3 and 6: raw closes 55,000 / 54,300 / 55,000 before a 10 % stock
# dividend on D[3], then 50,000 (open and close of the ex-date row, ex-price 55,000 / 1.1) and
# 50,400. Yahoo-style stored history divides the first three by 1.1.
RAW = [55_000.0, 54_300.0, 55_000.0, 50_000.0, 50_400.0]


def split_adjusted_case() -> pd.DataFrame:
    stored = [c / 1.1 for c in RAW[:3]] + RAW[3:]
    return bars("AAA", stored, "split_adjusted", volume=1_100_000)


STOCK = events(("AAA", D[3], "stock", 0.10))


# ------------------------------------------------------------------ criterion 1


def test_stock_dividend_leaves_no_artificial_gap_and_raw_is_untouched() -> None:
    raw = bars("AAA", RAW, "raw")
    before = raw.copy()
    out = build_series(raw, STOCK, TICKS).adjusted
    # raw gap D[2] -> D[3]: 50,000 / 55,000 - 1 = -9.09 %
    # adjusted: rows before the ex-date are x 1 / 1.1: 55,000 -> 50,000, 54,300 -> 49,363.64
    close = out["adj_close"].to_numpy()
    assert close[2] == pytest.approx(50_000.0)
    assert close[1] == pytest.approx(54_300.0 / 1.1)
    assert close[3] / close[2] - 1.0 == pytest.approx(0.0, abs=1e-12)  # no -9 % gap
    assert out["adj_factor"].tolist() == pytest.approx([1 / 1.1] * 3 + [1.0, 1.0])
    pd.testing.assert_frame_equal(raw, before)  # input not modified


def test_split_adjusted_rows_are_not_scaled_by_the_split_again() -> None:
    out = build_series(split_adjusted_case(), STOCK, TICKS).adjusted
    # stored closes are already continuous: 55,000 / 1.1 = 50,000 then 50,000 -> factor 1
    assert out["adj_factor"].tolist() == [1.0] * 5
    assert out["adj_close"].tolist() == split_adjusted_case()["close"].tolist()


# ------------------------------------------------------------------ criterion 2


def test_cash_dividend_scales_earlier_closes() -> None:
    # closes 50,000; dividend 2,000 on D[3]: factor (50,000 - 2,000) / 50,000 = 0.96
    prices = bars("AAA", [50_000.0] * 5, "raw")
    out = build_series(prices, events(("AAA", D[3], "cash", 2_000.0)), TICKS).adjusted
    assert out["adj_close"].tolist() == pytest.approx([48_000.0] * 3 + [50_000.0] * 2)
    assert out["adj_factor"].tolist() == pytest.approx([0.96] * 3 + [1.0] * 2)


def test_cash_dividend_on_split_adjusted_rows_uses_the_raw_basis() -> None:
    # stored 50,000 before a later 10 % event on D[4]: raw close was 55,000.
    # dividend 2,200 on D[3] (raw basis, flag off): 2,200 / 55,000 = 0.04 -> 0.96 -> 48,000
    prices = bars("AAA", [50_000.0] * 5, "split_adjusted")
    acts = events(("AAA", D[3], "cash", 2_200.0), ("AAA", D[4], "stock", 0.10))
    out = build_series(prices, acts, TICKS, dividends_split_adjusted=False).adjusted
    assert out["adj_close"].tolist()[:3] == pytest.approx([48_000.0] * 3)
    # amounts as stored (the flag off): 2,200 / 55,000 = 0.04
    stored = build_series(prices, acts, TICKS, dividends_split_adjusted=False).adjusted
    assert stored["adj_close"].tolist()[:3] == pytest.approx([48_000.0] * 3)
    # Yahoo's amounts are split-adjusted (the default): 2,200 x F(D[3]) = 2,200 x 1.1 = 2,420
    # -> 2,420 / 55,000 = 0.044 -> factor 0.956 -> 47,800
    flagged = build_series(prices, acts, TICKS).adjusted
    assert flagged["adj_close"].tolist()[:3] == pytest.approx([50_000 * 0.956] * 3)


def test_adjusted_version_is_stable_and_follows_the_events() -> None:
    prices = bars("AAA", RAW, "raw")
    one = build_series(prices, STOCK, TICKS).adjusted["adj_version"].unique()
    two = build_series(prices, STOCK, TICKS).adjusted["adj_version"].unique()
    other = build_series(prices, events(("AAA", D[3], "stock", 0.05)), TICKS).adjusted
    assert list(one) == list(two)
    assert len(one) == 1
    assert one[0].startswith("ratio-v1:")
    assert other["adj_version"].iloc[0] != one[0]


# ------------------------------------------------------------------ criterion 3


def test_execution_series_of_a_split_adjusted_fixture() -> None:
    result = build_series(split_adjusted_case(), STOCK, TICKS)
    out = result.execution
    assert set(out["price_basis"]) == {"exec_reconstructed"}
    # exec = stored x F, F = 1.1 before D[3] and 1 from D[3]; nearest tick (100 above 50,000):
    #   50,000 x 1.1 = 55,000 ; 49,363.64 x 1.1 = 54,300 ; 55,000 ; then 50,000 and 50,400
    assert out["close"].tolist() == [55_000.0, 54_300.0, 55_000.0, 50_000.0, 50_400.0]
    assert out["open"].tolist() == out["close"].tolist()
    assert out["stock_factor"].tolist() == pytest.approx([1.1, 1.1, 1.1, 1.0, 1.0])
    # volume / F: 1,100,000 / 1.1 = 1,000,000 before the event, unchanged after
    assert out["volume"].tolist() == [1_000_000] * 3 + [1_100_000] * 2
    # ref = round_down(previous stored close x F(t)): the first row uses its stored ref
    #   D0 50,000 x 1.1 = 55,000 ; D1 50,000 x 1.1 = 55,000 ; D2 49,363.64 x 1.1 = 54,300
    #   D3 (ex-date) 50,000 x 1 = 50,000 = 55,000 / 1.1 ; D4 previous close 50,000
    assert out["ref_price"].tolist() == [55_000.0, 55_000.0, 54_300.0, 50_000.0, 50_000.0]
    # HOSE limits: ref 55,000 -> ceiling 58,850 down to 58,800, floor 51,150 up to 51,200
    #   ref 54,300 -> 58,101 -> 58,100 ; 50,499 -> 50,500 ; ref 50,000 -> 53,500 / 46,500
    #   D4 ref 50,000 -> 53,500 / 46,500 again
    assert out["ceiling"].tolist() == [58_800.0, 58_800.0, 58_100.0, 53_500.0, 53_500.0]
    assert out["floor"].tolist() == [51_200.0, 51_200.0, 50_500.0, 46_500.0, 46_500.0]
    assert result.report.excluded_tickers == ()


def test_execution_prices_are_clipped_to_the_limits() -> None:
    # D[2] stored 59,000 / 1.1 -> exec 59,000, but ref (D[1]) = 55,000 -> ceiling 58,800
    stored = [50_000.0, 50_000.0, 59_000.0 / 1.1, 50_000.0, 50_000.0]
    out = build_series(bars("AAA", stored, "split_adjusted"), STOCK, TICKS).execution
    assert out["close"].iloc[2] == 58_800.0


def test_raw_and_synthetic_rows_are_copied_unchanged() -> None:
    raw = bars("AAA", RAW, "raw")
    out = build_series(raw, STOCK, TICKS).execution
    for column in ("open", "high", "low", "close", "volume", "ref_price", "ceiling", "floor"):
        assert out[column].tolist() == raw[column].tolist()
    assert set(out["price_basis"]) == {"raw"}


def test_cash_ex_date_keeps_ref_at_the_previous_close() -> None:
    # cash 2,000 on D[3]: Yahoo's close is not cash-adjusted, ref stays 50,000 (GAP-02 residual)
    prices = bars("AAA", [50_000.0] * 5, "split_adjusted")
    out = build_series(prices, events(("AAA", D[3], "cash", 2_000.0)), TICKS).execution
    assert out["ref_price"].tolist() == [50_000.0] * 5


def test_nearest_tick_rounds_to_the_closest_grid_price() -> None:
    # stored 4,547 x 1.1 = 5,001.7 -> tick 10 -> 5,000 ; the ex-date rows are 4,547 -> 4,550
    # (tie-free: 454.7 ticks rounds to 455)
    prices = bars("AAA", [4_547.0] * 5, "split_adjusted")
    out = build_series(prices, STOCK, TICKS).execution
    assert out["close"].tolist() == [5_000.0] * 3 + [4_550.0] * 2


# ------------------------------------------------------------------ criterion 4


def test_scale_discontinuity_excludes_the_ticker() -> None:
    # AAA: stored event 10 % but the history is not in one scale at it (a 25 % jump):
    # closes 50,000 then the ex-date open 40,000 = 50,000 / 1.25.
    # expected open = close[p] x F[j] = 50,000 x 1 = 50,000 (the stored ratio cancels)
    # observed 40,000 -> deviation 20 % > tolerance 7 % + 1 % = 8 %
    bad = bars("AAA", [50_000.0] * 3 + [40_000.0] * 2, "split_adjusted")
    good = split_adjusted_case().assign(ticker="BBB")
    acts = events(("AAA", D[3], "stock", 0.10), ("BBB", D[3], "stock", 0.10))
    result = build_series(pd.concat([bad, good]), acts, TICKS)
    assert precondition_tolerance(TICKS) == pytest.approx(0.08)
    report = result.report
    assert report.excluded_tickers == ("AAA",)
    assert report.excluded_ticker_rows == 5
    assert set(result.execution["ticker"]) == {"BBB"}
    (item,) = [e for e in report.exclusions if e.kind == "scale_discontinuity"]
    assert (item.ticker, item.date) == ("AAA", D[3])
    assert "20.0%" in item.detail
    assert len(result.adjusted[result.adjusted["ticker"] == "AAA"]) == 5  # signals unaffected


def test_unrescaled_history_with_the_right_ratio_is_flagged_too() -> None:
    # stored 50,000 then an ex-date open of 45,500: 45,500 / 50,000 - 1 = -9 % > 8 %
    prices = bars("AAA", [50_000.0] * 3 + [45_500.0] * 2, "split_adjusted")
    assert build_series(prices, STOCK, TICKS).report.excluded_tickers == ("AAA",)


def test_ex_date_row_that_is_bad_is_compared_with_the_next_good_session() -> None:
    # stored 50,000 throughout, ex-date D[3] row is bad; D[4] (next good) opens 50,000: fine
    prices = bars("AAA", [50_000.0] * 5, "split_adjusted")
    ok = build_series(prices, STOCK, TICKS, bad_rows={("AAA", D[3])})
    assert ok.report.excluded_tickers == ()
    # same, but D[4] opens at 40,000: 20 % off the previous good close -> discontinuity
    jump = bars("AAA", [50_000.0] * 4 + [40_000.0], "split_adjusted")
    out = build_series(jump, STOCK, TICKS, bad_rows={("AAA", D[3])})
    assert out.report.excluded_tickers == ("AAA",)
    kinds = [e.kind for e in out.report.exclusions]
    assert "scale_discontinuity" in kinds
    assert str(D[4]) in out.report.exclusions[-1].detail


def test_event_with_only_bad_sessions_after_it_is_unverifiable() -> None:
    prices = bars("AAA", [50_000.0] * 5, "split_adjusted")
    bad = {("AAA", D[3]), ("AAA", D[4])}
    result = build_series(prices, STOCK, TICKS, bad_rows=bad)
    assert result.report.excluded_tickers == ("AAA",)
    kinds = sorted(e.kind for e in result.report.exclusions)
    assert kinds == ["dq_error", "dq_error", "precondition_unverifiable"]
    # rows dropped only because of the ticker: D0..D2 (bad rows are counted once, as dq_error)
    assert result.report.excluded_ticker_rows == 3
    assert result.report.bad_rows_omitted == 2


def test_two_events_inside_one_suspension_are_not_a_false_exclusion() -> None:
    # sessions D0, D1 then a suspension over D2 and D3 (10 % events on both), resume D4.
    # stored closes 46,000; resume open 45,500 = -1.1 % (inside 8 %).
    # old formula: expected = 46,000 x 1.21 / 1.1 = 50,600 -> 10.1 % off (false exclusion);
    # now expected = close[p] x F[j] = 46,000 -> deviation 1.1 %
    days = [D[0], D[1], D[4]]
    prices = bars("AAA", [46_000.0, 46_000.0, 45_500.0], "split_adjusted", days=days)
    acts = events(("AAA", D[2], "stock", 0.10), ("AAA", D[3], "stock", 0.10))
    result = build_series(prices, acts, TICKS)
    assert result.report.excluded_tickers == ()
    assert result.execution["stock_factor"].tolist() == pytest.approx([1.21, 1.21, 1.0])
    # exec before = 46,000 x 1.21 = 55,660 -> nearest 100 = 55,700
    assert result.execution["close"].tolist()[:2] == [55_700.0, 55_700.0]


# ------------------------------------------------------------------ criterion 5


def test_bad_row_is_omitted_counted_and_never_repaired() -> None:
    raw = bars("AAA", [50_000.0] * 5, "synthetic", source="synthetic")
    raw.loc[2, ["open", "high"]] = [50_100.0, 49_900.0]  # high < open: ohlc_inconsistent
    result = build_series(raw, events(), TICKS, bad_rows={("AAA", D[2])})
    assert D[2] not in set(result.execution["date"])
    assert len(result.execution) == 4
    assert result.report.bad_rows_omitted == 1
    assert [(e.kind, e.date) for e in result.report.exclusions] == [("dq_error", D[2])]
    # signals keep the row, flagged
    assert result.adjusted["dq_error"].tolist() == [False, False, True, False, False]


def test_bad_split_adjusted_row_is_omitted_and_neighbours_keep_their_values() -> None:
    result = build_series(split_adjusted_case(), STOCK, TICKS, bad_rows={("AAA", D[1])})
    assert result.execution["date"].tolist() == [D[0], D[2], D[3], D[4]]
    assert result.execution["close"].tolist() == [55_000.0, 55_000.0, 50_000.0, 50_400.0]


def test_row_without_a_reference_price_is_omitted() -> None:
    prices = split_adjusted_case()
    prices.loc[0, "ref_price"] = np.nan  # first session, no previous close
    result = build_series(prices, STOCK, TICKS)
    assert result.execution["date"].tolist() == D[1:]
    assert result.report.no_reference_omitted == 1


def test_one_source_per_call_and_required_columns() -> None:
    mixed = pd.concat([bars("AAA", RAW, "raw"), bars("BBB", RAW, "raw", source="other")])
    with pytest.raises(ValueError, match="one source"):
        build_series(mixed, events(), TICKS)
    with pytest.raises(ValueError, match="missing columns"):
        build_series(bars("AAA", RAW, "raw").drop(columns=["ref_price"]), events(), TICKS)


def test_empty_input_gives_empty_outputs() -> None:
    result = build_series(bars("AAA", RAW, "raw").iloc[0:0], events(), TICKS)
    assert result.adjusted.empty
    assert result.execution.empty
    assert result.report.price_rows == 0


def test_rights_and_invalid_amounts_are_ignored() -> None:
    acts = events(("AAA", D[3], "rights", 0.2), ("AAA", D[2], "cash", 0.0))
    out = build_series(bars("AAA", RAW, "raw"), acts, TICKS).adjusted
    assert out["adj_factor"].tolist() == [1.0] * 5


def test_oversized_cash_dividend_is_ignored_with_a_warning() -> None:
    prices = bars("AAA", [50_000.0] * 5, "raw")
    result = build_series(prices, events(("AAA", D[3], "cash", 60_000.0)), TICKS)
    assert result.adjusted["adj_factor"].tolist() == [1.0] * 5
    assert len(result.report.warnings) == 1


def test_bonus_counts_as_stock_and_two_events_on_one_date_combine() -> None:
    # 10 % stock + 10 % bonus on D[3]: F = 1.1 x 1.1 = 1.21 before; expected open =
    # 50,000 x 1.21 / 1.21 = 50,000 -> passes; exec before = 50,000 x 1.21 = 60,500
    prices = bars("AAA", [50_000.0] * 5, "split_adjusted")
    acts = events(("AAA", D[3], "stock", 0.10), ("AAA", D[3], "bonus", 0.10))
    result = build_series(prices, acts, TICKS)
    assert result.report.excluded_tickers == ()
    assert result.execution["stock_factor"].tolist() == pytest.approx([1.21] * 3 + [1.0] * 2)
    assert result.execution["close"].tolist() == [60_500.0] * 3 + [50_000.0] * 2


def test_execution_actions_scales_dividends_by_default_and_not_when_off() -> None:
    acts = events(("AAA", D[2], "cash", 1_000.0), ("AAA", D[3], "stock", 0.10))
    assert execution_actions(acts, {"AAA"}, dividends_split_adjusted=False).equals(acts)
    scaled = execution_actions(acts, {"AAA"})  # the default: Yahoo amounts are split-adjusted
    # F(D[2]) = 1.1 (the event on D[3] is later): 1,000 x 1.1
    assert scaled["ratio_or_amount"].tolist() == pytest.approx([1_100.0, 0.10])
    assert execution_actions(acts.iloc[0:0], {"AAA"}, True).empty


# ------------------------------------------------------------------ store and rebuild


def _store(tmp_path: Path, kind: str = "real") -> MarketStore:
    return MarketStore(tmp_path / "market.duckdb", "synthetic" if kind == "synthetic" else "real")


def _fill(store: MarketStore, prices: pd.DataFrame, acts: pd.DataFrame) -> None:
    store.upsert_prices(prices, "r1", NOW)
    store.upsert_corporate_actions(acts, "r1")


def _table_rows(store: MarketStore, table: str) -> list[tuple[object, ...]]:
    return store.connection.execute(f"SELECT * FROM {table} ORDER BY ALL").fetchall()  # noqa: S608


def test_rebuild_is_idempotent_and_leaves_source_tables_alone(tmp_path: Path) -> None:
    with _store(tmp_path) as store:
        _fill(store, pd.concat([split_adjusted_case(), bars("BBB", RAW, "split_adjusted")]), STOCK)
        daily, acts = _table_rows(store, "prices_daily"), _table_rows(store, "corporate_actions")
        first = rebuild(store, "yahoo", TICKS)
        derived = {t: _table_rows(store, t) for t in ("prices_adjusted", "prices_exec")}
        second = rebuild(store, "yahoo", TICKS)
        assert first == second
        assert derived == {t: _table_rows(store, t) for t in derived}
        assert len(derived["prices_exec"]) == 10
        assert daily == _table_rows(store, "prices_daily")
        assert acts == _table_rows(store, "corporate_actions")


def _bad_raw() -> pd.DataFrame:
    raw = bars("AAA", [50_000.0] * 5, "raw")
    raw.loc[1, ["open", "high"]] = [50_100.0, 49_900.0]  # high < open: error-level
    return raw


def _run(store: MarketStore, run_id: str, source: str, minute: int) -> None:
    stamp = datetime(2026, 11, 6, 12, minute, tzinfo=UTC)
    store.record_run(
        RunRecord(run_id, source, stamp, stamp, D[0], D[4], "AAA", 5, 5, 0, 0, "ok", None)
    )


def test_old_bad_row_stays_excluded_after_later_clean_and_foreign_runs(tmp_path: Path) -> None:
    with _store(tmp_path) as store:
        _fill(store, _bad_raw(), events())
        _run(store, "r1", "yahoo", 1)
        _run(store, "clean-incremental", "yahoo", 2)  # a later run that found nothing
        _run(store, "foreign", "other", 3)  # another source's newest run
        report = rebuild(store, "yahoo", TICKS)
        assert report.bad_rows_omitted == 1
        loaded = load_execution_frame(store, ["AAA"], D[0], D[4])
        assert D[1] not in set(loaded.prices["date"])
        assert len(loaded.prices) == 4
        assert loaded.exclusions[["ticker", "kind"]].values.tolist() == [["AAA", "dq_error"]]
        assert not loaded.stale


def test_corrected_row_is_no_longer_excluded(tmp_path: Path) -> None:
    with _store(tmp_path) as store:
        _fill(store, _bad_raw(), events())
        assert rebuild(store, "yahoo", TICKS).bad_rows_omitted == 1
        fixed = _bad_raw()
        fixed.loc[1, ["open", "high"]] = [50_000.0, 50_000.0]  # new revision of the same key
        assert store.upsert_prices(fixed, "r2", NOW).changed == 1
        report = rebuild(store, "yahoo", TICKS)
        assert report.bad_rows_omitted == 0
        assert len(store.read_execution("yahoo", ["AAA"], D[0], D[4])) == 5


def test_stale_flag_and_warning_when_a_newer_run_exists(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with _store(tmp_path) as store:
        _fill(store, split_adjusted_case(), STOCK)
        _run(store, "r1", "yahoo", 1)
        rebuild(store, "yahoo", TICKS)
        assert store.rebuilt_through_run("yahoo") == "r1"
        assert not load_execution_frame(store, ["AAA"], D[0], D[4]).stale
        _run(store, "r2", "yahoo", 2)
        with caplog.at_level("WARNING"):
            loaded = load_execution_frame(store, ["AAA"], D[0], D[4])
        assert loaded.stale
        assert "data rebuild" in caplog.text
        rebuild(store, "yahoo", TICKS)
        assert not load_execution_frame(store, ["AAA"], D[0], D[4]).stale


def test_dry_run_writes_nothing_and_empty_source_is_an_error(tmp_path: Path) -> None:
    with _store(tmp_path) as store:
        with pytest.raises(SourceError, match="no rows for source 'yahoo'"):
            rebuild(store, "yahoo", TICKS)
        _fill(store, split_adjusted_case(), STOCK)
        report = rebuild(store, "yahoo", TICKS, dry_run=True)
        assert report.exec_rows == 5
        assert _table_rows(store, "prices_exec") == []
        assert store.rebuilt_through_run("yahoo") is None
        rebuild(store, "yahoo", TICKS)
        before = _table_rows(store, "prices_exec")
        with pytest.raises(SourceError, match="no rows for source 'gone'"):
            rebuild(store, "gone", TICKS)
        assert before == _table_rows(store, "prices_exec")  # nothing deleted


def test_derived_rows_of_the_wrong_kind_are_refused(tmp_path: Path) -> None:
    with _store(tmp_path) as store, pytest.raises(SourceError, match="synthetic"):
        store.replace_derived("synthetic", pd.DataFrame(), pd.DataFrame(), pd.DataFrame())


def test_load_execution_frame_errors(tmp_path: Path) -> None:
    with _store(tmp_path) as store:
        _fill(store, split_adjusted_case(), STOCK)
        with pytest.raises(SourceError, match="rebuild"):
            load_execution_frame(store, ["AAA"], D[0], D[4])
        rebuild(store, "yahoo", TICKS)
        with pytest.raises(SourceError, match="no execution series"):
            load_execution_frame(store, ["AAA"], D[0], D[4], source="other")
    path = tmp_path / "old.duckdb"
    con = duckdb.connect(str(path))
    con.execute("CREATE TABLE store_meta (key VARCHAR, value VARCHAR)")
    con.execute("INSERT INTO store_meta VALUES ('kind', 'real')")
    con.close()
    with MarketStore(path, "real", read_only=True) as old, pytest.raises(SourceError, match="no"):
        load_execution_frame(old, ["AAA"], D[0], D[4])


def test_excluded_ticker_is_reported_by_the_loader(tmp_path: Path) -> None:
    bad = bars("AAA", [50_000.0] * 3 + [40_000.0] * 2, "split_adjusted")
    both = pd.concat([bad, split_adjusted_case().assign(ticker="BBB")])
    acts = events(("AAA", D[3], "stock", 0.10), ("BBB", D[3], "stock", 0.10))
    with _store(tmp_path) as store:
        _fill(store, both, acts)
        report = rebuild(store, "yahoo", TICKS)
        loaded = load_execution_frame(store, ["AAA", "BBB"], D[0], D[4])
    assert report.excluded_tickers == ("AAA",)
    assert set(loaded.prices["ticker"]) == {"BBB"}
    assert loaded.exclusions[["ticker", "kind"]].values.tolist() == [["AAA", "scale_discontinuity"]]
    assert loaded.exclusions["date"].tolist() == [D[3]]


def test_corporate_action_dates_migrate_and_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "old.duckdb"
    con = duckdb.connect(str(path))
    con.execute(
        "CREATE TABLE corporate_actions (ticker VARCHAR NOT NULL, ex_date DATE NOT NULL, "
        "type VARCHAR NOT NULL, ratio_or_amount DOUBLE, source VARCHAR NOT NULL, "
        "run_id VARCHAR NOT NULL, PRIMARY KEY (ticker, ex_date, type, source))"
    )
    con.execute("CREATE TABLE store_meta (key VARCHAR PRIMARY KEY, value VARCHAR)")
    con.execute("INSERT INTO store_meta VALUES ('kind', 'real')")
    con.close()
    with MarketStore(path, "real") as store:
        cols = {r[0] for r in store.connection.execute("DESCRIBE corporate_actions").fetchall()}
        assert {"pay_date", "listing_date"} <= cols
        acts = events(("AAA", D[3], "cash", 500.0)).assign(pay_date=D[4], listing_date=pd.NaT)
        assert store.upsert_corporate_actions(acts, "r1").inserted == 1
        stored = store.read_corporate_actions(["AAA"])
        assert stored["pay_date"].iloc[0].date() == D[4]
        assert pd.isna(stored["listing_date"].iloc[0])
        # the same row again changes nothing; a new pay date is a change
        assert store.upsert_corporate_actions(acts, "r2").written == 0
        moved = acts.assign(pay_date=D[3])
        assert store.upsert_corporate_actions(moved, "r3").changed == 1


# ------------------------------------------------------------------ criterion 6 end to end


@pytest.fixture(scope="module")
def cfg(tmp_path_factory: pytest.TempPathFactory) -> AppConfig:
    base = load_config(tmp_path_factory.mktemp("adjust_home"))
    syn = base.data.synthetic.model_copy(update={"start": date(2020, 1, 1)})
    return base.model_copy(update={"data": base.data.model_copy(update={"synthetic": syn})})


def yahoo_style(raw: pd.DataFrame, acts: pd.DataFrame) -> pd.DataFrame:
    """Re-express synthetic raw bars the way Yahoo does: earlier prices / (1 + ratio)."""
    out = raw.sort_values(["ticker", "date"]).reset_index(drop=True)
    for r in acts[acts["type"] == "stock"].itertuples():
        mask = (out["ticker"] == r.ticker) & (out["date"] < r.ex_date)
        for col in ("open", "high", "low", "close"):
            out.loc[mask, col] = out.loc[mask, col] / (1.0 + r.ratio_or_amount)
    prev = out.groupby("ticker")["close"].shift(1)  # derived at ingest from the previous close
    ceiling, floor = TICKS.limits(prev.fillna(1.0).to_numpy())
    out["ref_price"], out["ceiling"], out["floor"] = prev, ceiling, floor
    out["value"] = out["close"] * out["volume"]
    out["source"], out["price_basis"], out["derived_limits"] = "yahoo", "split_adjusted", True
    return out


def test_engine_runs_on_the_rebuilt_series_and_is_deterministic(
    cfg: AppConfig, tmp_path: Path
) -> None:
    start, end = date(2020, 1, 1), date(2021, 6, 30)
    source = SyntheticSource(cfg)
    tickers = universe_tickers(cfg)
    raw = source.fetch_daily(tickers, start, end)
    acts = source.fetch_corporate_actions(tickers, start, end)
    assert (acts["type"] == "stock").any()
    stored = yahoo_style(raw, acts)
    with _store(tmp_path) as store:
        store.upsert_prices(stored, "r1", NOW)
        store.upsert_corporate_actions(acts.assign(source="yahoo"), "r1")
        report = rebuild(store, "yahoo", TickTable.from_config(cfg))
        loaded = load_execution_frame(store, tickers, start, end)
    assert report.excluded_tickers == ()
    assert set(loaded.prices["price_basis"]) == {"exec_reconstructed"}
    # reconstruction recovers the synthetic raw bars on every session that is not a cash
    # ex-date (cash ex-dates keep ref at the previous close: GAP-02 residual); first rows have
    # no reference and are omitted
    cash_days = {(r.ticker, r.ex_date) for r in acts[acts["type"] == "cash"].itertuples()}
    merged = loaded.prices.merge(raw, on=["ticker", "date"], suffixes=("", "_raw"))
    keep = [(t, d) not in cash_days for t, d in zip(merged["ticker"], merged["date"], strict=True)]
    same = merged[keep]
    assert len(same) > 1_000
    for col in ("open", "high", "low", "close", "ref_price", "ceiling", "floor"):
        assert same[col].tolist() == pytest.approx(same[f"{col}_raw"].tolist()), col

    params = make_params(cfg, "ideal")
    calendar = TradingCalendar.from_config(cfg)
    days = sorted(set(loaded.prices["date"]))
    targets = {
        days[30]: pd.Series({tickers[0]: 0.4, tickers[1]: 0.4}),
        days[200]: pd.Series(dtype=float),
    }
    one = run_simulation(loaded.prices, loaded.actions, targets, calendar, params)
    two = run_simulation(loaded.prices, loaded.actions, targets, calendar, params)
    assert one.digest() == two.digest()
    assert len(one.trades) > 0

    with pytest.raises(ValueError, match="split_adjusted"):
        run_simulation(stored, loaded.actions, targets, calendar, params)


# ------------------------------------------------------------------ P1-T06b: event-scale repair

D8 = make_days(8)
EVENT15 = events(("AAA", D8[3], "stock", 0.15))


def test_isolated_outlier_row_is_omitted_and_the_ticker_stays() -> None:
    # stored 50,000 on D0..D2, the ex-date row D3 sits at old scale 57,500 (= 50,000 x 1.15),
    # D4..D7 are back at 50,000. Event 15 % on D3.
    # expected open = close[p] x F[j] = 50,000 ; observed 57,500 -> 15 % > 8 % (fails).
    # next good session D4: 50,000 -> 0 % <= 8 %: one outlier row (D3).
    prices = bars("AAA", [50_000.0] * 3 + [57_500.0] + [50_000.0] * 4, "split_adjusted", days=D8)
    result = build_series(prices, EVENT15, TICKS)
    report = result.report
    assert report.excluded_tickers == ()
    assert report.outlier_rows_omitted == 1
    assert [(e.kind, e.date) for e in report.exclusions] == [("scale_outlier_row", D8[3])]
    out = result.execution
    assert out["date"].tolist() == [*D8[:3], *D8[4:]]
    # F = 1.15 before D3: 50,000 x 1.15 = 57,500 on D0..D2; D4..D7 stored x 1 = 50,000
    assert out["close"].tolist() == [57_500.0] * 3 + [50_000.0] * 4
    # D4 reference = last non-omitted close 50,000 x F[D4] (1) = 50,000, never the outlier 57,500;
    # ceiling 53,500 / floor 46,500
    assert out["ref_price"].tolist()[3:] == [50_000.0] * 4
    assert out["ceiling"].tolist()[3] == 53_500.0
    assert out["floor"].tolist()[3] == 46_500.0
    assert len(result.adjusted) == 8  # signals untouched


def test_two_session_outlier_is_omitted_three_falls_back_to_discontinuity() -> None:
    # D3 and D4 at 57,500, D5 back at 50,000. m = 1: D4 57,500 is 15 % off (> 8 %); m = 2: D5
    # 50,000 is 0 % off -> both rows omitted.
    two = bars("AAA", [50_000.0] * 3 + [57_500.0] * 2 + [50_000.0] * 3, "split_adjusted", days=D8)
    result = build_series(two, EVENT15, TICKS)
    assert result.report.excluded_tickers == ()
    assert result.report.outlier_rows_omitted == 2
    assert [e.date for e in result.report.exclusions] == [D8[3], D8[4]]
    assert result.execution["date"].tolist() == [*D8[:3], *D8[5:]]
    assert result.execution["ref_price"].tolist()[3] == 50_000.0  # chained from D2, not D4
    # three sessions D3..D5 at 57,500, D6 back at 50,000: m = 1, 2 fail (D4, D5 are 15 % off);
    # D6 is the third following session -> not an outlier; it also returns to the old level,
    # so it is not a persistent step either -> whole ticker excluded
    three = bars("AAA", [50_000.0] * 3 + [57_500.0] * 3 + [50_000.0] * 2, "split_adjusted", days=D8)
    out = build_series(three, EVENT15, TICKS)
    assert out.report.excluded_tickers == ("AAA",)
    assert out.report.outlier_rows_omitted == 0
    assert [e.kind for e in out.report.exclusions] == ["scale_discontinuity"]
    assert out.execution.empty


def test_persistent_step_excludes_rows_through_the_ex_date_and_marks_the_event() -> None:
    # stored 50,000 on D0..D2 then 57,500 (= 50,000 x 1.15) on D3..D7; event 15 % on D3.
    # observed / (close[p] x G) = 57,500 / (50,000 x 1.15) = 1 -> a step by the ratio; D4, D5, D6
    # stay 15 % away from 50,000 and D4 continues from D3 (0 %) -> suspect event.
    prices = bars("AAA", [50_000.0] * 3 + [57_500.0] * 5, "split_adjusted", days=D8)
    result = build_series(prices, EVENT15, TICKS)
    report = result.report
    assert report.excluded_tickers == ()
    assert report.suspect_events == 1
    assert report.step_rows_excluded == 4  # D0..D3
    (item,) = report.exclusions
    assert (item.kind, item.date, item.rows) == ("scale_step_before", D8[3], 4)
    assert "4 execution rows" in item.detail
    out = result.execution
    assert out["date"].tolist() == D8[4:]
    # later rows: F = 1 (the suspect event only concerns rows through D3, which are gone)
    assert out["close"].tolist() == [57_500.0] * 4
    assert out["ref_price"].tolist() == [57_500.0] * 4  # D4 ref = close(D3) = 57,500


def test_suspect_event_is_not_returned_by_the_loader_and_the_engine_runs(
    tmp_path: Path, cfg: AppConfig
) -> None:
    prices = bars("AAA", [50_000.0] * 3 + [57_500.0] * 5, "split_adjusted", days=D8)
    acts = pd.concat([EVENT15, events(("AAA", D8[6], "cash", 500.0))])
    with _store(tmp_path) as store:
        _fill(store, prices, acts)
        report = rebuild(store, "yahoo", TICKS)
        loaded = load_execution_frame(store, ["AAA"], D8[0], D8[7])
    assert report.suspect_events == 1
    assert loaded.prices["date"].tolist() == D8[4:]
    # the 15 % event is gone, the cash dividend stays (F = 1 after the suspect event: 500 x 1)
    assert loaded.actions[["type", "ratio_or_amount"]].values.tolist() == [["cash", 500.0]]
    assert loaded.exclusions[["kind", "date"]].values.tolist() == [["scale_step_before", D8[3]]]
    params = make_params(cfg, "ideal")
    targets = {D8[4]: pd.Series({"AAA": 0.5}), D8[6]: pd.Series(dtype=float)}
    result = run_simulation(
        loaded.prices, loaded.actions, targets, TradingCalendar.from_config(cfg), params
    )
    assert len(result.trades) > 0


def test_genuine_correctly_scaled_event_passes_untouched() -> None:
    # Yahoo-style history continuous at 50,000 across the 15 % event: deviation 0 %, nothing
    # omitted; F = 1.15 before D3 -> 50,000 x 1.15 = 57,500 (the raw price before the event)
    prices = bars("AAA", [50_000.0] * 8, "split_adjusted", days=D8)
    result = build_series(prices, EVENT15, TICKS)
    assert result.report.exclusions == ()
    assert len(result.execution) == 8
    assert result.execution["close"].tolist() == [57_500.0] * 3 + [50_000.0] * 5


def test_pre_hose_history_is_excluded_after_the_last_out_of_band_session() -> None:
    days = make_days(180)
    # rows 0..99 alternate 50,000 / 54,750: moves +9.5 % and -8.68 % (both > 8 %) -> rows 1..99
    # are out of band; rows 100..179 alternate 54,750 / 56,000 (+2.3 % / -2.2 %, row 100 is 0 %
    # from row 99) -> 80 clean sessions >= 60 -> the first run starts at row 100, so the
    # last out-of-band session is row 99: rows 0..99 (100 sessions) are excluded
    closes = [50_000.0 if i % 2 == 0 else 54_750.0 for i in range(100)]
    closes += [54_750.0 if i % 2 == 0 else 56_000.0 for i in range(80)]
    result = build_series(bars("AAA", closes, "split_adjusted", days=days), events(), TICKS)
    report = result.report
    assert report.non_hose_rows_excluded == 100
    (item,) = report.exclusions
    assert (item.kind, item.date, item.rows) == ("non_hose_history", days[99], 100)
    assert result.execution["date"].tolist() == days[100:]
    assert report.excluded_tickers == ()


def test_a_single_in_band_day_does_not_trigger_the_pre_hose_rule() -> None:
    days = make_days(180)
    closes = [50_000.0] * 180
    closes[90] = 53_450.0  # +6.9 % (<= 8 %) then -6.5 %: both inside the band
    result = build_series(bars("AAA", closes, "split_adjusted", days=days), events(), TICKS)
    assert result.report.exclusions == ()
    assert len(result.execution) == 180


def test_pre_hose_rule_needs_a_clean_run_and_ignores_raw_sources() -> None:
    days = make_days(100)
    wild = [50_000.0 if i % 2 == 0 else 54_750.0 for i in range(100)]
    # never 60 clean sessions in a row: nothing is excluded
    never = build_series(bars("AAA", wild, "split_adjusted", days=days), events(), TICKS)
    assert never.report.exclusions == ()
    # raw rows are not touched even with a clean run after wild ones
    mixed = wild[:30] + [50_000.0] * 70
    assert (
        build_series(bars("AAA", mixed, "raw", days=days), events(), TICKS).report.exclusions == ()
    )


def test_rows_are_counted_once_across_kinds() -> None:
    days = make_days(180)
    closes = [50_000.0 if i % 2 == 0 else 54_750.0 for i in range(100)] + [54_750.0] * 80
    bad = {("AAA", days[5]), ("AAA", days[150])}
    result = build_series(
        bars("AAA", closes, "split_adjusted", days=days), events(), TICKS, bad_rows=bad
    )
    report = result.report
    # row 5 is both bad and in the pre-HOSE window: counted as dq_error only; 99 other window rows
    assert report.bad_rows_omitted == 2
    assert report.non_hose_rows_excluded == 99
    assert len(result.execution) == 180 - 2 - 99
    assert report.exec_rows == len(result.execution)


def test_split_adjusted_dividend_is_booked_in_the_split_adjusted_basis() -> None:
    # cash 500 on D2, stock 10 % on D3: F(D2) = 1.1 -> 500 x 1.1 = 550
    acts = events(("AAA", D[2], "cash", 500.0), ("AAA", D[3], "stock", 0.10))
    prices = bars("AAA", [50_000.0] * 5, "split_adjusted")
    adjusted = build_series(prices, acts, TICKS).adjusted
    # previous close D1 in raw basis = 50,000 x F(D1) = 55,000 -> 550 / 55,000 = 0.01 -> 0.99
    # (as stored, 500 / 55,000 = 0.00909 -> 0.990909)
    assert adjusted["adj_factor"].tolist() == pytest.approx([0.99, 0.99, 1.0, 1.0, 1.0])
    scaled = execution_actions(acts, {"AAA"})
    assert scaled["ratio_or_amount"].tolist() == pytest.approx([550.0, 0.10])
    # raw sources are unchanged: the amount stays 500 for a ticker not reconstructed
    assert execution_actions(acts, set()).equals(acts)
    raw = bars("AAA", [55_000.0] * 5, "raw")
    one = build_series(raw, acts, TICKS).adjusted
    # raw: 500 / 55,000 = 0.0090909 -> 0.9909091 for rows before D2, then / 1.1 before D3
    assert one["adj_factor"].tolist() == pytest.approx(
        [0.9909091 / 1.1, 0.9909091 / 1.1, 1 / 1.1, 1.0, 1.0]
    )


def test_rebuild_report_counts_each_kind_once_and_is_idempotent(tmp_path: Path) -> None:
    out = bars("AAA", [50_000.0] * 3 + [57_500.0] + [50_000.0] * 4, "split_adjusted", days=D8)
    step = bars("BBB", [50_000.0] * 3 + [57_500.0] * 5, "split_adjusted", days=D8)
    acts = pd.concat([EVENT15, EVENT15.assign(ticker="BBB")])
    with _store(tmp_path) as store:
        _fill(store, pd.concat([out, step]), acts)
        daily = _table_rows(store, "prices_daily")
        stored_acts = _table_rows(store, "corporate_actions")
        first = rebuild(store, "yahoo", TICKS)
        derived = {t: _table_rows(store, t) for t in ("prices_adjusted", "prices_exec")}
        exclusions = _table_rows(store, "exec_exclusions")
        second = rebuild(store, "yahoo", TICKS)
        assert first == second
        assert derived == {t: _table_rows(store, t) for t in derived}
        assert exclusions == _table_rows(store, "exec_exclusions")
        assert daily == _table_rows(store, "prices_daily")
        assert stored_acts == _table_rows(store, "corporate_actions")
    assert (first.outlier_rows_omitted, first.step_rows_excluded, first.suspect_events) == (1, 4, 1)
    assert first.exec_rows == 7 + 4  # AAA 8 - 1, BBB 8 - 4
    assert [e.kind for e in first.exclusions] == ["scale_outlier_row", "scale_step_before"]


# ------------------------------------------------------------------ P1-T06c: review fixes

D10 = make_days(10)
EVENT10 = events(("AAA", D10[3], "stock", 0.10))


def test_probe_a_persistent_step_followed_by_a_normal_move_is_not_an_outlier(
    tmp_path: Path,
) -> None:
    # closes 50,000 x3, 55,000 on the ex-date (10 % event), then 53,900 x6.
    # expected open = 50,000; D3 55,000 is 10 % off (> 8 %). D4 53,900 is 7.8 % off the old level
    # (inside 8 %) but nearer the stepped level 55,000 (1,100) than 50,000 (3,900) and continues
    # D3 (-2 %): not back in scale -> persistent step, the event is suspect.
    prices = bars("AAA", [50_000.0] * 3 + [55_000.0] + [53_900.0] * 6, "split_adjusted", days=D10)
    result = build_series(prices, EVENT10, TICKS)
    report = result.report
    assert report.outlier_rows_omitted == 0
    assert report.excluded_tickers == ()
    assert report.suspect_events == 1
    assert [(e.kind, e.date, e.rows) for e in report.exclusions] == [
        ("scale_step_before", D10[3], 4)
    ]
    out = result.execution
    assert out["date"].tolist() == D10[4:]
    assert out["close"].tolist() == [53_900.0] * 6  # no clipped close
    assert out["ref_price"].tolist()[0] == 55_000.0  # close of the ex-date session
    # signals ignore the suspect event: no 1 / 1.1 scaling of the earlier rows
    assert result.adjusted["adj_factor"].tolist() == [1.0] * 10
    with _store(tmp_path) as store:
        _fill(store, prices, EVENT10)
        rebuild(store, "yahoo", TICKS)
        loaded = load_execution_frame(store, ["AAA"], D10[0], D10[9])
    assert loaded.actions.empty  # the suspect event is not applied to holdings


def test_outlier_return_must_break_continuity_and_be_nearer_the_old_level() -> None:
    # genuine one-row outlier with a 10 % event: 55,000 then back at 50,000 (-9.1 %: breaks
    # continuity with the outlier close, nearer the old level) -> still an outlier row
    prices = bars("AAA", [50_000.0] * 3 + [55_000.0] + [50_000.0] * 6, "split_adjusted", days=D10)
    result = build_series(prices, EVENT10, TICKS)
    assert [e.kind for e in result.report.exclusions] == ["scale_outlier_row"]
    assert result.report.excluded_tickers == ()


def _alternating(count: int) -> list[float]:
    """50,000 / 54,750 alternating: +9.5 % and -8.68 % moves, both outside the 8 % tolerance."""
    return [50_000.0 if i % 2 == 0 else 54_750.0 for i in range(count)]


def test_probe_e_cut_is_the_last_out_of_band_session_followed_by_60_calm() -> None:
    # 100 wild (row 0 has no previous close, rows 1..99 are out of band), 60 calm, 50 wild
    # (row 160 jumps 54,750 -> 50,000; rows 160..209 are out of band), 80 calm. The last
    # out-of-band row is 209, followed by 80 in-band sessions -> rows 0..209 = 210 excluded
    # (the old rule cut at row 99: 100).
    days = make_days(290)
    closes = _alternating(100) + [54_750.0] * 60 + _alternating(50) + [54_750.0] * 80
    assert len(closes) == 290
    result = build_series(bars("AAA", closes, "split_adjusted", days=days), events(), TICKS)
    report = result.report
    assert report.non_hose_rows_excluded == 210
    (item,) = report.exclusions
    assert (item.kind, item.date, item.rows) == ("non_hose_history", days[209], 210)
    assert result.execution["date"].tolist() == days[210:]
    # signals mark exactly those rows unusable
    assert result.adjusted["signal_ok"].tolist() == [False] * 210 + [True] * 80


def test_probe_f_cash_ex_date_is_exempt_from_the_band_test() -> None:
    days = make_days(120)
    closes = [30_000.0] * 5 + [27_000.0] * 115  # -10 % at row 5, the 3,000 dividend ex-date
    prices = bars("AAA", closes, "split_adjusted", days=days)
    with_cash = build_series(prices, events(("AAA", days[5], "cash", 3_000.0)), TICKS)
    assert with_cash.report.exclusions == ()
    assert len(with_cash.execution) == 120
    assert with_cash.adjusted["signal_ok"].all()
    # without the dividend the same step is out of band: rows 0..5 are excluded
    without = build_series(prices, events(), TICKS)
    assert without.report.non_hose_rows_excluded == 6


def test_cash_dividend_is_split_adjusted_end_to_end_through_the_loader(tmp_path: Path) -> None:
    acts = events(("AAA", D[2], "cash", 500.0), ("AAA", D[3], "stock", 0.10))
    prices = bars("AAA", [50_000.0] * 5, "split_adjusted")
    with _store(tmp_path) as store:
        _fill(store, prices, acts)
        report = rebuild(store, "yahoo", TICKS)
        loaded = load_execution_frame(store, ["AAA"], D[0], D[4])
    assert report.suspect_events == 0
    by_type = dict(zip(loaded.actions["type"], loaded.actions["ratio_or_amount"], strict=True))
    assert by_type["cash"] == pytest.approx(550.0)  # 500 x F(D2) = 500 x 1.1
    assert by_type["stock"] == pytest.approx(0.10)


def test_exclusion_rows_and_signal_ok_are_stored_and_old_stores_migrate(tmp_path: Path) -> None:
    prices = bars("AAA", [50_000.0] * 3 + [57_500.0] * 5, "split_adjusted", days=D8)
    with _store(tmp_path) as store:
        _fill(store, prices, EVENT15)
        rebuild(store, "yahoo", TICKS)
        exclusions = store.read_exclusions("yahoo")
        adjusted = store.read_adjusted("yahoo")
    assert exclusions[["kind", "rows"]].values.tolist() == [["scale_step_before", 4]]
    assert adjusted["signal_ok"].tolist() == [False] * 4 + [True] * 4
    # a store created before P1-T06c has neither column; opening it adds them, rebuild fills them
    path = tmp_path / "old.duckdb"
    con = duckdb.connect(str(path))
    con.execute("CREATE TABLE store_meta (key VARCHAR PRIMARY KEY, value VARCHAR)")
    con.execute("INSERT INTO store_meta VALUES ('kind', 'real')")
    con.execute(
        "CREATE TABLE prices_adjusted (ticker VARCHAR NOT NULL, date DATE NOT NULL, "
        "source VARCHAR NOT NULL, price_basis VARCHAR NOT NULL, adj_open DOUBLE, adj_high DOUBLE, "
        "adj_low DOUBLE, adj_close DOUBLE, adj_factor DOUBLE, adj_version VARCHAR NOT NULL, "
        "dq_error BOOLEAN NOT NULL, PRIMARY KEY (ticker, date, source))"
    )
    con.execute(
        "CREATE TABLE exec_exclusions (source VARCHAR NOT NULL, ticker VARCHAR NOT NULL, "
        "kind VARCHAR NOT NULL, date DATE, detail VARCHAR NOT NULL)"
    )
    con.close()
    with MarketStore(path, "real") as store:
        for table, column in (("prices_adjusted", "signal_ok"), ("exec_exclusions", "rows")):
            cols = {r[0] for r in store.connection.execute(f"DESCRIBE {table}").fetchall()}
            assert column in cols
        _fill(store, prices, EVENT15)
        rebuild(store, "yahoo", TICKS)
        assert store.read_adjusted("yahoo")["signal_ok"].tolist() == [False] * 4 + [True] * 4
        assert store.read_exclusions("yahoo")["rows"].tolist() == [4]


def test_signal_ok_is_false_for_outlier_dq_and_step_rows_and_true_otherwise() -> None:
    outlier = bars("AAA", [50_000.0] * 3 + [57_500.0] + [50_000.0] * 4, "split_adjusted", days=D8)
    result = build_series(outlier, EVENT15, TICKS, bad_rows={("AAA", D8[6])})
    expected = [True] * 3 + [False] + [True] * 2 + [False, True]
    assert result.adjusted["signal_ok"].tolist() == expected
    assert result.adjusted["dq_error"].tolist() == [False] * 6 + [True, False]
    fine = build_series(bars("AAA", [50_000.0] * 8, "raw", days=D8), events(), TICKS)
    assert fine.adjusted["signal_ok"].all()
    assert fine.adjusted["signal_ok"].dtype == bool


def test_flagged_bad_row_does_not_cut_hose_history() -> None:
    days = make_days(300)
    closes = [50_000.0] * 300
    closes[200] = 60_000.0
    r = build_series(
        bars("AAA", closes, "split_adjusted", days=days),
        events(),
        TICKS,
        bad_rows={("AAA", days[200])},
    )
    assert [e.kind for e in r.report.exclusions] == ["dq_error"]
    assert len(r.execution) == 299
