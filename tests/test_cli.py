from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from typer.testing import CliRunner

from vnstratlab import __version__
from vnstratlab.cli import app
from vnstratlab.data.pipeline import load_execution_frame
from vnstratlab.data.store import MarketStore

runner = CliRunner()
ANSI = re.compile(r"\[[0-9;?]*[A-Za-z]")


def plain(result: Any) -> str:
    """Output without ANSI styling (Rich colours it when GITHUB_ACTIONS or FORCE_COLOR is set)."""
    return ANSI.sub("", result.output)


EXPECTED_COMMANDS = [
    "doctor",
    "demo",
    "init",
    "ingest",
    "data",
    "features",
    "backtest",
    "lab",
    "meta-backtest",
    "stress",
    "daily",
    "serve",
]


def test_help_lists_all_commands() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in EXPECTED_COMMANDS:
        assert command in result.output


def test_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


@pytest.mark.parametrize(
    ("args", "card"),
    [
        (["backtest", "--strategy", "S02_breakout20"], "P1-T20"),
        (["lab", "--horizon", "short"], "P1-T22"),
        (["meta-backtest", "--horizon", "long"], "P1-T23"),
        (["stress", "--horizon", "medium"], "P1-T33"),
        (["daily", "--dry-run"], "P1-T26"),
        (["serve"], "P1-T27"),
    ],
)
def test_stubs_fail_loudly_and_name_their_card(args: list[str], card: str) -> None:
    result = runner.invoke(app, args)
    assert result.exit_code == 1
    assert card in result.output


def test_ingest_rejects_bad_date() -> None:
    result = runner.invoke(app, ["ingest", "--from", "2020-13-45"])
    assert result.exit_code != 0


def test_lab_rejects_unknown_horizon() -> None:
    result = runner.invoke(app, ["lab", "--horizon", "weekly"])
    assert result.exit_code == 2


def test_doctor_never_prints_secret_values(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> None:
    secret = "synthetic-secret-value-123"  # noqa: S105 - synthetic test value
    monkeypatch.chdir(str(tmp_path))  # a developer's own .env in the repo must not matter
    monkeypatch.setenv("APP_HOME", str(tmp_path))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", secret)
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert secret not in result.output
    assert "telegram_bot_token" in result.output
    assert "vnstock" not in result.output.lower()
    assert "set" in result.output


@pytest.mark.parametrize("args", [["--help"], ["--version"], ["data", "--help"]])
def test_help_and_version_do_not_import_the_heavy_libraries(args: list[str]) -> None:
    import subprocess
    import sys

    code = (
        "import sys\n"
        "from vnstratlab.cli import app\n"
        "try:\n"
        f"    app({args!r})\n"
        "except SystemExit:\n"
        "    pass\n"
        "heavy = [m for m in ('pandas', 'numpy', 'duckdb', 'pyarrow') if m in sys.modules]\n"
        "print('HEAVY=' + ','.join(heavy))\n"
    )
    done = subprocess.run(  # noqa: S603
        [sys.executable, "-I", "-c", code], capture_output=True, text=True, check=False
    )
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip().endswith("HEAVY="), done.stdout


def test_data_rebuild_without_a_store_fails_and_names_the_fix(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("APP_HOME", str(tmp_path / "home"))
    result = runner.invoke(app, ["data", "rebuild", "--source", "synthetic"])
    assert result.exit_code == 1
    assert "ingest" in result.output


def test_data_rebuild_reports_counts_and_is_repeatable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("APP_HOME", str(home))
    args = ["ingest", "--source", "synthetic", "--from", "2026-03-02", "--to", "2026-03-13"]
    assert runner.invoke(app, args).exit_code == 0
    first = runner.invoke(app, ["data", "rebuild", "--source", "synthetic"])
    assert first.exit_code == 0, first.output
    # synthetic rows are raw-like: the execution series is the stored rows unchanged
    assert "rebuilt synthetic" in first.output
    assert "excluded tickers 0" in first.output
    assert "bad source rows omitted 0" in first.output
    assert "scale outlier rows omitted 0" in first.output
    assert "rows before a scale step excluded 0 (suspect events 0)" in first.output
    assert "non-HOSE history rows excluded 0" in first.output
    second = runner.invoke(app, ["data", "rebuild", "--source", "synthetic"])
    assert second.output == first.output
    with MarketStore(home / "data" / "market-synthetic.duckdb", "synthetic", read_only=True) as s:
        stored = s.row_count()
        assert len(s.read_adjusted("synthetic")) == stored
        frame = load_execution_frame(s, ["ACB"], date(2026, 3, 2), date(2026, 3, 13))
    assert stored > 0
    assert set(frame.prices["price_basis"]) == {"synthetic"}


def test_data_rebuild_of_a_source_without_a_store_exits_1(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("APP_HOME", str(home))
    args = ["ingest", "--source", "synthetic", "--from", "2026-03-02", "--to", "2026-03-04"]
    assert runner.invoke(app, args).exit_code == 0
    result = runner.invoke(app, ["data", "rebuild", "--source", "yahoo"])  # no real store
    assert result.exit_code == 1


def test_data_rebuild_dry_run_prints_the_report_and_writes_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("APP_HOME", str(home))
    args = ["ingest", "--source", "synthetic", "--from", "2026-03-02", "--to", "2026-03-06"]
    assert runner.invoke(app, args).exit_code == 0
    result = runner.invoke(app, ["data", "rebuild", "--source", "synthetic", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "would rebuild synthetic" in result.output
    assert "dry run: nothing was written" in result.output
    with MarketStore(home / "data" / "market-synthetic.duckdb", "synthetic", read_only=True) as s:
        assert s.derived_sources() == []


def test_data_rebuild_prints_counts_per_exclusion_kind(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("APP_HOME", str(home))
    days = [date(2026, 11, d) for d in (2, 3, 4, 5, 6, 9, 10, 11)]
    # AAA: the ex-date row D3 (Thu 11-05) is one out-of-scale session (57,500 vs 50,000);
    # BBB: 50,000 then a persistent step to 57,500 from D3 (4 rows through the ex-date excluded)
    closes = {
        "AAA": [50_000.0] * 3 + [57_500.0] + [50_000.0] * 4,
        "BBB": [50_000.0] * 3 + [57_500.0] * 5,
    }
    frames = []
    for ticker, values in closes.items():
        ref = [values[0], *values[:-1]]
        frames.append(
            pd.DataFrame(
                {
                    "ticker": ticker,
                    "date": days,
                    "open": values,
                    "high": values,
                    "low": values,
                    "close": values,
                    "volume": [1_000_000 + i for i in range(len(values))],  # not duplicates
                    "value": 0.0,
                    "ref_price": ref,
                    "ceiling": [r * 1.07 for r in ref],
                    "floor": [r * 0.93 for r in ref],
                    "source": "yahoo",
                    "price_basis": "split_adjusted",
                    "derived_limits": True,
                }
            )
        )
    acts = pd.DataFrame(
        [(t, days[3], "stock", 0.15, "yahoo") for t in closes],
        columns=["ticker", "ex_date", "type", "ratio_or_amount", "source"],
    )
    path = home / "data" / "market.duckdb"
    with MarketStore(path, "real") as store:
        store.upsert_prices(pd.concat(frames), "r1", datetime(2026, 11, 12, tzinfo=UTC))
        store.upsert_corporate_actions(acts, "r1")
    result = runner.invoke(app, ["data", "rebuild", "--source", "yahoo"])
    assert result.exit_code == 0, result.output
    assert "excluded tickers 0" in result.output
    assert "scale outlier rows omitted 1" in result.output
    assert "rows before a scale step excluded 4 (suspect events 1)" in result.output
    assert "non-HOSE history rows excluded 0" in result.output


# ------------------------------------------------------------------ features build (P1-T10)


def synthetic_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    home = tmp_path / "home"
    monkeypatch.setenv("APP_HOME", str(home))
    args = ["ingest", "--source", "synthetic", "--from", "2026-01-05", "--to", "2026-04-30"]
    assert runner.invoke(app, args).exit_code == 0
    return home


def synthetic_db(home: Path) -> Path:
    return home / "data" / "market-synthetic.duckdb"


def test_features_build_before_a_rebuild_stops_and_names_the_fix(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    synthetic_home(monkeypatch, tmp_path)
    for extra in ([], ["--dry-run"]):
        result = runner.invoke(app, ["features", "build", "--source", "synthetic", *extra])
        assert result.exit_code == 1
        assert "vnstratlab data rebuild" in result.output


def test_features_build_refuses_a_store_rebuilt_by_an_older_method(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import duckdb

    home = synthetic_home(monkeypatch, tmp_path)
    assert runner.invoke(app, ["data", "rebuild", "--source", "synthetic"]).exit_code == 0
    con = duckdb.connect(str(synthetic_db(home)))
    con.execute("UPDATE prices_adjusted SET adj_version = 'ratio-v1:old'")
    con.close()
    for extra in ([], ["--dry-run"]):
        result = runner.invoke(app, ["features", "build", "--source", "synthetic", *extra])
        assert result.exit_code == 1
        assert "vnstratlab data rebuild" in result.output


def test_features_build_without_a_store_exits_1(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("APP_HOME", str(tmp_path / "home"))
    result = runner.invoke(app, ["features", "build", "--source", "synthetic"])
    assert result.exit_code == 1
    assert "ingest" in result.output


def test_features_build_dry_run_writes_nothing_and_build_is_idempotent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home = synthetic_home(monkeypatch, tmp_path)
    assert runner.invoke(app, ["data", "rebuild", "--source", "synthetic"]).exit_code == 0
    dry = runner.invoke(app, ["features", "build", "--source", "synthetic", "--dry-run"])
    assert dry.exit_code == 0, dry.output
    assert "would build features for synthetic" in dry.output
    assert "rows per ticker:" in dry.output
    assert "NaN share per feature group:" in dry.output
    assert "sessions_in_window" in dry.output
    assert "dry run: nothing was written" in dry.output
    with MarketStore(synthetic_db(home), "synthetic", read_only=True) as store:
        assert not store.has_table("features_daily")  # nothing written

    first = runner.invoke(app, ["features", "build", "--source", "synthetic"])
    assert first.exit_code == 0, first.output
    assert "built features for synthetic" in first.output
    with MarketStore(synthetic_db(home), "synthetic", read_only=True) as store:
        a = store.read_features(date(2026, 1, 1), date(2026, 12, 31))
    second = runner.invoke(app, ["features", "build", "--source", "synthetic"])
    assert second.exit_code == 0
    with MarketStore(synthetic_db(home), "synthetic", read_only=True) as store:
        b = store.read_features(date(2026, 1, 1), date(2026, 12, 31))
    assert len(a) > 0
    pd.testing.assert_frame_equal(a, b)  # idempotent
    assert a["feature_version"].nunique() == 1
    # the dry run reports the same row count that the build wrote
    assert f"{len(a)} rows" in dry.output


# ------------------------------------------------------------------ lab trials / register (P1-T13)


@pytest.fixture
def local_strategies() -> Iterator[None]:
    from test_strategies_base import SyntheticEqualWeight, SyntheticOther
    from vnstratlab.strategies.registry import register_strategy, unregister_strategy

    for cls in (SyntheticEqualWeight, SyntheticOther):
        register_strategy(cls)
    yield
    for cls in (SyntheticEqualWeight, SyntheticOther):
        unregister_strategy(cls.id)


DISABLE_PACKAGED = """strategies:
  S00_composite: {enabled: false, reason: "test isolates the local strategies"}
  S17_equal_weight: {enabled: false, reason: "test isolates the local strategies"}
  S01_weekly_reversal: {enabled: false, reason: "test isolates the local strategies"}
  S02_breakout_volume: {enabled: false, reason: "test isolates the local strategies"}
  S03_oversold_uptrend: {enabled: false, reason: "test isolates the local strategies"}
  S04_bank_pairs: {enabled: false, reason: "test isolates the local strategies"}
  S05_residual_reversion: {enabled: false, reason: "test isolates the local strategies"}
  S08_momentum: {enabled: false, reason: "test isolates the local strategies"}
  S09_reversal: {enabled: false, reason: "test isolates the local strategies"}
  S14_low_volatility: {enabled: false, reason: "test isolates the local strategies"}
  S15_sector_trend: {enabled: false, reason: "test isolates the local strategies"}
  S18_hrp: {enabled: false, reason: "test isolates the local strategies"}
"""
STRATEGIES_YAML = """strategies:
  S00_composite: {enabled: false, reason: "test isolates the local strategies"}
  S17_equal_weight: {enabled: false, reason: "test isolates the local strategies"}
  S01_weekly_reversal: {enabled: false, reason: "test isolates the local strategies"}
  S02_breakout_volume: {enabled: false, reason: "test isolates the local strategies"}
  S03_oversold_uptrend: {enabled: false, reason: "test isolates the local strategies"}
  S04_bank_pairs: {enabled: false, reason: "test isolates the local strategies"}
  S05_residual_reversion: {enabled: false, reason: "test isolates the local strategies"}
  S08_momentum: {enabled: false, reason: "test isolates the local strategies"}
  S09_reversal: {enabled: false, reason: "test isolates the local strategies"}
  S14_low_volatility: {enabled: false, reason: "test isolates the local strategies"}
  S15_sector_trend: {enabled: false, reason: "test isolates the local strategies"}
  S18_hrp: {enabled: false, reason: "test isolates the local strategies"}
  T_equal: {horizons: [short, medium], params: [{top: 1}, {top: 2}]}
  T_other: {horizons: [long], params: [{top: 1}]}
  S06_foreign_flow: {enabled: false, reason: "pending P1-T04"}
"""


def lab_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, yaml_text: str) -> Path:
    """Synthetic store with features built, plus a user config with the given text."""
    home = synthetic_home(monkeypatch, tmp_path)
    assert runner.invoke(app, ["data", "rebuild", "--source", "synthetic"]).exit_code == 0
    assert runner.invoke(app, ["features", "build", "--source", "synthetic"]).exit_code == 0
    (home / "config.yaml").write_text(yaml_text, encoding="utf-8")
    return home


def lab_db(home: Path) -> Path:
    return home / "data" / "lab.duckdb"


def test_lab_selection_command_still_works_with_subcommands(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("APP_HOME", str(tmp_path / "home"))
    stub = runner.invoke(app, ["lab", "--horizon", "short", "--dry-run"])
    assert stub.exit_code == 1
    assert "P1-T22" in plain(stub)
    missing = runner.invoke(app, ["lab"])
    assert missing.exit_code == 2
    assert "--horizon" in plain(missing)
    helped = runner.invoke(app, ["lab", "--help"])
    assert "trials" in plain(helped)
    assert "register" in plain(helped)


def test_lab_trials_without_a_registry_is_read_only(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("APP_HOME", str(home))
    result = runner.invoke(app, ["lab", "trials"])
    assert result.exit_code == 0
    assert "trials: 0" in plain(result)
    assert not lab_db(home).exists()  # reading never creates the file


def test_lab_register_with_no_strategies_says_so_and_needs_no_store(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("APP_HOME", str(home))
    home.mkdir()
    (home / "config.yaml").write_text(DISABLE_PACKAGED, encoding="utf-8")
    result = runner.invoke(app, ["lab", "register"])
    assert result.exit_code == 0
    assert "nothing to register" in plain(result)
    assert not lab_db(home).exists()


def test_lab_register_dry_run_writes_nothing_then_register_and_trials(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, local_strategies: None
) -> None:
    home = lab_home(monkeypatch, tmp_path, STRATEGIES_YAML)
    dry = runner.invoke(app, ["lab", "register", "--source", "synthetic", "--dry-run"])
    assert dry.exit_code == 0, plain(dry)
    assert "would register 5 new trial(s) of 5" in plain(dry)  # (2 params x 2 horizons) + 1
    assert "nothing was written" in plain(dry)
    assert not lab_db(home).exists()  # not created

    real = runner.invoke(app, ["lab", "register", "--source", "synthetic"])
    assert real.exit_code == 0, plain(real)
    assert "registered 5 new trial(s) of 5" in plain(real)
    assert "trials now: 5" in plain(real)
    before = lab_db(home).read_bytes()

    again = runner.invoke(app, ["lab", "register", "--source", "synthetic"])
    assert again.exit_code == 0
    assert "registered 0 new trial(s) of 5" in plain(again)
    assert "already registered" in plain(again)
    dry_again = runner.invoke(app, ["lab", "register", "--source", "synthetic", "--dry-run"])
    assert "would register 0 new trial(s) of 5" in plain(dry_again)
    assert lab_db(home).read_bytes() == before  # a dry run and an idempotent run leave it alone

    listing = runner.invoke(app, ["lab", "trials"])
    assert listing.exit_code == 0
    assert "trials: 5" in plain(listing)
    assert "[config]" in plain(listing)
    assert "UTC" in plain(listing)
    assert '{"top":2}' in plain(listing)
    long_only = runner.invoke(app, ["lab", "trials", "--horizon", "long"])
    assert "trials: 1 (horizon long)" in plain(long_only)
    assert "T_equal" not in plain(long_only)
    assert lab_db(home).read_bytes() == before  # lab trials is read-only


def test_lab_register_new_param_set_adds_one_trial(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, local_strategies: None
) -> None:
    home = lab_home(monkeypatch, tmp_path, STRATEGIES_YAML)
    assert runner.invoke(app, ["lab", "register", "--source", "synthetic"]).exit_code == 0
    extended = STRATEGIES_YAML.replace("{top: 1}, {top: 2}", "{top: 1}, {top: 2}, {top: 3}")
    (home / "config.yaml").write_text(extended, encoding="utf-8")
    result = runner.invoke(app, ["lab", "register", "--source", "synthetic"])
    assert "registered 2 new trial(s) of 7" in plain(result)  # {top: 3} on two horizons
    assert "trials now: 7" in plain(result)


def test_lab_register_rejects_a_bad_strategies_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, local_strategies: None
) -> None:
    home = lab_home(
        monkeypatch, tmp_path, "strategies:\n  S99_nope: {horizons: [short], params: [{}]}\n"
    )
    result = runner.invoke(app, ["lab", "register", "--source", "synthetic"])
    assert result.exit_code == 1
    assert "strategies config: INVALID" in plain(result)
    assert "S99_nope" in plain(result)
    assert not lab_db(home).exists()


def test_lab_register_needs_a_store_with_features(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, local_strategies: None
) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("APP_HOME", str(home))
    home.mkdir()
    (home / "config.yaml").write_text(STRATEGIES_YAML, encoding="utf-8")
    no_store = runner.invoke(app, ["lab", "register", "--source", "synthetic"])
    assert no_store.exit_code == 1
    assert "ingest" in plain(no_store)

    args = ["ingest", "--source", "synthetic", "--from", "2026-01-05", "--to", "2026-02-27"]
    assert runner.invoke(app, args).exit_code == 0
    no_features = runner.invoke(app, ["lab", "register", "--source", "synthetic"])
    assert no_features.exit_code == 1
    assert "features build" in plain(no_features)
    assert not lab_db(home).exists()


def test_lab_commands_report_an_unusable_lab_db_cleanly(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, local_strategies: None
) -> None:
    home = lab_home(monkeypatch, tmp_path, STRATEGIES_YAML)
    lab_db(home).parent.mkdir(parents=True, exist_ok=True)
    lab_db(home).write_text("this is not a duckdb file", encoding="utf-8")
    for args in (["lab", "trials"], ["lab", "register", "--source", "synthetic"]):
        result = runner.invoke(app, args)
        assert result.exit_code == 1
        assert "cannot use" in plain(result)
        assert "Traceback" not in plain(result)


def test_lab_register_dry_run_lists_the_packaged_strategies(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # P1-T14..T19: S00 2 + S17 3 (1 param set x 3 horizons) + S01 2 + S02 1 + S03 2 + S04 1
    # + S05 1 + S08 2 + S09 1 + S14 1 + S15 2 + S18 1 = 19 trials
    home = lab_home(monkeypatch, tmp_path, "lab: {}\n")
    dry = runner.invoke(app, ["lab", "register", "--source", "synthetic", "--dry-run"])
    assert dry.exit_code == 0, plain(dry)
    text = plain(dry)
    assert "would register 19 new trial(s) of 19" in text
    assert text.count("S00_composite") == 2
    assert text.count("S17_equal_weight") == 3
    assert text.count("S01_weekly_reversal") == 2
    assert text.count("S02_breakout_volume") == 1
    assert text.count("S03_oversold_uptrend") == 2
    assert text.count("S04_bank_pairs") == 1
    assert text.count("S05_residual_reversion") == 1
    assert text.count("S08_momentum") == 2
    assert text.count("S09_reversal") == 1
    assert text.count("S14_low_volatility") == 1
    assert text.count("S15_sector_trend") == 2
    assert text.count("S18_hrp") == 1
    assert not lab_db(home).exists()
