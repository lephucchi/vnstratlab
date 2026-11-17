from __future__ import annotations

import json
import shutil
import warnings
from datetime import date
from pathlib import Path

import pytest
from typer.testing import CliRunner

from vnstratlab.cli import app
from vnstratlab.config.loader import ConfigError, load_config

FIXTURES = Path(__file__).parent / "fixtures"
runner = CliRunner()


def _home_with(tmp_path: Path, fixture: str) -> Path:
    shutil.copy(FIXTURES / fixture, tmp_path / "config.yaml")
    return tmp_path


def test_packaged_config_loads_and_round_trips(tmp_path: Path) -> None:
    cfg = load_config(tmp_path)
    assert cfg.costs.sales_tax_pct == 0.001
    assert len(cfg.universe.membership[0].tickers) == 13
    assert cfg.market.market == "hose"
    assert cfg.market.rules.round_lot.value == 100
    assert cfg.books.long.decision_day == "last_trading_day_of_month"
    assert cfg.lab.weights["short"].lambda_ == 0.5
    assert cfg.risk.vol_target_annual is None


def test_config_is_frozen(tmp_path: Path) -> None:
    cfg = load_config(tmp_path)
    with pytest.raises(ValueError, match="frozen"):
        cfg.costs.sales_tax_pct = 0.5  # type: ignore[misc]


def test_deep_merge_keeps_siblings_and_lists_replace(tmp_path: Path) -> None:
    cfg = load_config(_home_with(tmp_path, "synthetic_override_ok.yaml"))
    assert cfg.costs.slippage_pct.round_lot == 0.002
    assert cfg.costs.slippage_pct.odd_lot == 0.003  # sibling intact
    assert cfg.costs.brokerage_fee_pct == 0.0015
    assert cfg.risk.max_positions == 6
    assert cfg.risk.atr_stop_multiple == 2.0
    assert cfg.benchmarks.market_indices == ("VN30",)  # list replaced


def test_user_can_add_holidays_for_a_year(tmp_path: Path) -> None:
    cfg = load_config(_home_with(tmp_path, "synthetic_holidays_ok.yaml"))
    assert cfg.market.holidays[2030].days[0].date == date(2030, 3, 4)
    assert 2026 in cfg.market.holidays  # packaged years remain


@pytest.mark.parametrize(
    ("fixture", "path"),
    [
        ("synthetic_bad_unknown_key.yaml", "costs.brokerage_fee"),
        ("synthetic_bad_negative_cost.yaml", "costs.sales_tax_pct"),
        ("synthetic_bad_horizon.yaml", "lab.gate1.min_periods.weekly"),
        ("synthetic_bad_holiday_saturday.yaml", "market.holidays.2026.days.0.date"),
        ("synthetic_bad_holiday_year.yaml", "market.holidays.2026.days.0.date"),
    ],
)
def test_invalid_fixtures_raise_config_error_with_dotted_path(
    tmp_path: Path, fixture: str, path: str
) -> None:
    with pytest.raises(ConfigError) as info:
        load_config(_home_with(tmp_path, fixture))
    assert f"{path}:" in str(info.value)


def test_negative_cost_message_text(tmp_path: Path) -> None:
    with pytest.raises(ConfigError) as info:
        load_config(_home_with(tmp_path, "synthetic_bad_negative_cost.yaml"))
    assert "costs.sales_tax_pct: Input should be greater than or equal to 0" in str(info.value)


def test_all_problems_are_listed(tmp_path: Path) -> None:
    (tmp_path / "config.yaml").write_text(
        "costs: {sales_tax_pct: -1, brokerage_fee_pct: 2}\nrisk: {max_positions: 0}\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError) as info:
        load_config(tmp_path)
    assert len(info.value.problems) == 3


def test_malformed_yaml_and_non_mapping(tmp_path: Path) -> None:
    (tmp_path / "config.yaml").write_text("costs: [unclosed", encoding="utf-8")
    with pytest.raises(ConfigError, match=r"config\.yaml"):
        load_config(tmp_path)
    (tmp_path / "config.yaml").write_text("- a\n- b\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="mapping"):
        load_config(tmp_path)


def test_empty_user_file_is_fine(tmp_path: Path) -> None:
    (tmp_path / "config.yaml").write_text("", encoding="utf-8")
    assert load_config(tmp_path).project.market == "hose"


@pytest.mark.parametrize("name", ["../evil", "nope"])
def test_unknown_or_unsafe_market_name(tmp_path: Path, name: str) -> None:
    (tmp_path / "config.yaml").write_text(f"project: {{market: '{name}'}}\n", encoding="utf-8")
    with pytest.raises(ConfigError, match=r"project\.market"):
        load_config(tmp_path)


def test_unknown_universe(tmp_path: Path) -> None:
    (tmp_path / "config.yaml").write_text("project: {universe: nope}\n", encoding="utf-8")
    with pytest.raises(ConfigError, match=r"project\.universe"):
        load_config(tmp_path)


def test_bad_long_decision_day_and_bad_regime(tmp_path: Path) -> None:
    (tmp_path / "config.yaml").write_text(
        "books: {long: {decision_day: after_report_season}}\n"
        "stress: {regimes: [{name: x, start: 2020-02-01, end: 2020-01-01}]}\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError) as info:
        load_config(tmp_path)
    assert "books.long.decision_day" in str(info.value)
    assert "stress.regimes.0" in str(info.value)


def test_packaged_holidays_cover_current_year_with_sources(tmp_path: Path) -> None:
    cfg = load_config(tmp_path)  # no user file in tmp_path
    year = date.today().year
    assert year in cfg.market.holidays, f"no holiday data for {year}: add it to hose.yaml"
    assert cfg.market.holidays[year].days, f"empty holiday list for {year}"
    for y, block in cfg.market.holidays.items():
        for day in block.days:
            assert day.date.year == y
            assert day.date.weekday() < 5
            assert day.source


def test_doctor_ok_without_user_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VNSTRATLAB_HOME", str(tmp_path))
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "config: OK" in result.output
    assert str(date.today().year) in result.output
    assert "holidays" in result.output


def test_doctor_invalid_config_exits_1(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _home_with(tmp_path, "synthetic_bad_negative_cost.yaml")
    monkeypatch.setenv("VNSTRATLAB_HOME", str(tmp_path))
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 1
    assert "config: INVALID" in result.output
    assert "costs.sales_tax_pct" in result.output
    assert "Traceback" not in result.output


# ---------------------------------------------------------------- G2 review fixes


def _write(tmp_path: Path, text: str) -> Path:
    (tmp_path / "config.yaml").write_text(text, encoding="utf-8")
    return tmp_path


def _problems(tmp_path: Path) -> str:
    with pytest.raises(ConfigError) as info:
        load_config(tmp_path)
    return str(info.value)


def test_rules_are_typed(tmp_path: Path) -> None:
    rules = load_config(tmp_path).market.rules
    assert rules.price_limit_pct.value == 0.07
    assert rules.odd_lot.value.max == 99
    assert rules.tick_sizes.value[1] == (10000, 50)
    assert rules.sessions.value.continuous == ("09:15-11:30", "13:00-14:30")
    assert rules.short_selling.value is False


@pytest.mark.parametrize(
    ("override", "path"),
    [
        ("market: {rules: {round_lott: {value: 100, status: VERIFY}}}", "market.rules.round_lott"),
        ("market: {rules: {round_lot: {value: 0}}}", "market.rules.round_lot.value"),
        ("market: {rules: {price_limit_pct: {value: 1.5}}}", "market.rules.price_limit_pct.value"),
        (
            "market: {rules: {price_limit_pct: {value: '0.07'}}}",
            "market.rules.price_limit_pct.value",
        ),
        ("market: {rules: {odd_lot: {value: {min: 50, max: 10}}}}", "market.rules.odd_lot.value"),
        ("market: {rules: {odd_lot: {value: {max: 100}}}}", "market.rules.odd_lot.value.max"),
        ("market: {rules: {tick_sizes: {value: [[5, 10]]}}}", "market.rules.tick_sizes.value"),
        (
            "market: {rules: {tick_sizes: {value: [[0, 10], [0, 50]]}}}",
            "market.rules.tick_sizes.value",
        ),
        ("market: {rules: {tick_sizes: {value: [[0, 0]]}}}", "market.rules.tick_sizes.value"),
        ("market: {rules: {sessions: {value: {ato: '9am'}}}}", "market.rules.sessions.value.ato"),
        ("market: {rules: {short_selling: {value: 'yes'}}}", "market.rules.short_selling.value"),
        (
            "market: {rules: {earliest_sell_session_offset: {value: -1}}}",
            "market.rules.earliest_sell_session_offset.value",
        ),
        ("costs: {sales_tax_pct: true}", "costs.sales_tax_pct"),
        ("costs: {sales_tax_pct: '0.001'}", "costs.sales_tax_pct"),
        ("risk: {max_positions: true}", "risk.max_positions"),
        ("risk: {atr_stop_multiple: true}", "risk.atr_stop_multiple"),
        ("risk: {max_positions: 2.5}", "risk.max_positions"),
        ("books: {short: {capital_vnd: 1000.5}}", "books.short.capital_vnd"),
    ],
)
def test_rules_and_strict_types_reject_bad_values(tmp_path: Path, override: str, path: str) -> None:
    assert f"{path}" in _problems(_write(tmp_path, override + "\n"))


def test_valid_rule_override_is_accepted(tmp_path: Path) -> None:
    cfg = load_config(
        _write(tmp_path, "market: {rules: {round_lot: {value: 10, status: confirmed}}}\n")
    )
    assert cfg.market.rules.round_lot.value == 10
    assert cfg.market.rules.round_lot.status == "confirmed"


def test_unreadable_user_config_is_config_error(tmp_path: Path) -> None:
    (tmp_path / "config.yaml").write_bytes(b"\xff\xfe\x00bad")
    with pytest.raises(ConfigError, match=r"config\.yaml: cannot read"):
        load_config(tmp_path)


def test_doctor_unreadable_config_exits_1_without_traceback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "config.yaml").write_bytes(b"\xff\xfe\x00bad")
    monkeypatch.setenv("VNSTRATLAB_HOME", str(tmp_path))
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 1
    assert "config: INVALID" in result.output
    assert "cannot read" in result.output
    assert isinstance(result.exception, SystemExit)


def test_config_is_deeply_immutable(tmp_path: Path) -> None:
    cfg = load_config(tmp_path)
    assert not hasattr(cfg.universe.membership, "append")
    assert not hasattr(cfg.universe.membership[0].tickers, "append")
    assert not hasattr(cfg.market.holidays[2026].days, "append")
    with pytest.raises(TypeError):
        cfg.market.holidays[2099] = cfg.market.holidays[2026]  # type: ignore[index]
    with pytest.raises(TypeError):
        cfg.lab.weights["short"] = cfg.lab.weights["medium"]  # type: ignore[index]
    with pytest.raises(TypeError):
        cfg.lab.gate1.min_periods["short"] = 1  # type: ignore[index]


def test_market_errors_reported_together(tmp_path: Path) -> None:
    text = _problems(
        _write(
            tmp_path,
            "market:\n  currency: vnd\n  holidays:\n    2026:\n      coverage: partial\n"
            "      days:\n        - {date: 2026-03-07, name: x, status: VERIFY, source: s}\n",
        )
    )
    assert "market.currency:" in text
    assert "market.holidays.2026.days.0.date:" in text


def test_market_and_universe_names_must_match_project(tmp_path: Path) -> None:
    assert "market.market:" in _problems(_write(tmp_path, "market: {market: hnx}\n"))
    assert "universe.universe:" in _problems(_write(tmp_path, "universe: {universe: other}\n"))


def test_doctor_reports_user_holiday_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "config.yaml").write_text(
        "market:\n  holidays:\n    2026:\n      coverage: complete\n      days:\n"
        "        - {date: 2026-03-09, name: synthetic, status: provisional, source: s}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("VNSTRATLAB_HOME", str(tmp_path))
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "holidays 2026: user override" in result.output


# ---------------------------------------------------------------- G2 round 2


def test_doctor_reports_empty_days_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "config.yaml").write_text(
        "market: {holidays: {2026: {coverage: partial, days: []}}}\n", encoding="utf-8"
    )
    monkeypatch.setenv("VNSTRATLAB_HOME", str(tmp_path))
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "holidays 2026: user override" in result.output


def test_quoted_year_key_merges_into_int_year(tmp_path: Path) -> None:
    cfg = load_config(
        _write(
            tmp_path,
            "market:\n  holidays:\n    '2026':\n      coverage: partial\n      days:\n"
            "        - {date: 2026-03-09, name: synthetic, status: provisional, source: s}\n",
        )
    )
    assert [d.date for d in cfg.market.holidays[2026].days] == [date(2026, 3, 9)]
    assert set(cfg.market.holidays) == {2026, 2027}


def test_non_integer_and_duplicate_year_keys_are_errors(tmp_path: Path) -> None:
    text = _problems(_write(tmp_path, "market: {holidays: {abc: {coverage: partial, days: []}}}\n"))
    assert "market.holidays.abc:" in text
    text = _problems(
        _write(
            tmp_path,
            "market:\n  holidays:\n    '2026': {coverage: partial, days: []}\n"
            "    2026: {coverage: partial, days: []}\n",
        )
    )
    assert "market.holidays.2026:" in text


def test_model_dump_and_json_round_trip_without_warnings(tmp_path: Path) -> None:
    cfg = load_config(_write(tmp_path, "strategies: {s1: {params: {a: [1, 2]}}}\n"))
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        data = json.loads(cfg.model_dump_json())
        py = cfg.model_dump()
    assert data["costs"]["sales_tax_pct"] == 0.001
    assert data["market"]["holidays"]["2026"]["coverage"] == "complete"
    assert data["lab"]["weights"]["short"]["lambda_"] == 0.5
    assert data["strategies"] == {"s1": {"params": {"a": [1, 2]}}}
    assert py["market"]["holidays"][2026]["coverage"] == "complete"
    assert isinstance(py["strategies"], dict)


def test_config_path_that_is_not_a_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / "config.yaml").mkdir()
    with pytest.raises(ConfigError, match="not a file"):
        load_config(tmp_path)
    monkeypatch.setenv("VNSTRATLAB_HOME", str(tmp_path))
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 1
    assert "config: INVALID" in result.output


def test_long_book_rejects_weekly_decision_day(tmp_path: Path) -> None:
    text = _problems(_write(tmp_path, "books: {long: {decision_day: last_trading_day_of_week}}\n"))
    assert "books.long.decision_day:" in text


def test_holiday_checks_run_even_when_another_day_has_a_field_error(tmp_path: Path) -> None:
    text = _problems(
        _write(
            tmp_path,
            "market:\n  holidays:\n    2026:\n      coverage: partial\n      days:\n"
            "        - {date: 2026-03-09, name: x, status: maybe, source: s}\n"
            "        - {date: 2026-08-22, name: y, status: VERIFY, source: s}\n",
        )
    )
    assert "market.holidays.2026.days.0.status:" in text
    assert "market.holidays.2026.days.1.date:" in text


@pytest.mark.parametrize("field", ["name", "source"])
def test_holiday_name_and_source_must_not_be_empty(tmp_path: Path, field: str) -> None:
    fields = {"name": "x", "source": "s"} | {field: '""'}
    day = (
        f"{{date: 2026-03-09, name: {fields['name']}, status: VERIFY, source: {fields['source']}}}"
    )
    text = _problems(
        _write(
            tmp_path,
            "market:\n  holidays:\n    2026:\n      coverage: partial\n      days:\n"
            f"        - {day}\n",
        )
    )
    assert f"market.holidays.2026.days.0.{field}:" in text
