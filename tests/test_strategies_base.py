"""Strategy base, guards, registry, config loading and trial identity (P1-T13). Synthetic only."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from vnstratlab.config.models import AppConfig
from vnstratlab.engine import ENGINE_VERSION
from vnstratlab.strategies import registry
from vnstratlab.strategies.base import (
    BaseStrategy,
    LookaheadError,
    Strategy,
    WeightError,
    asof_guard,
    validate_weights,
)
from vnstratlab.strategies.registry import (
    StrategyConfigError,
    canonical_params_json,
    compute_trial_id,
    load_strategies,
    make_trial_spec,
    register_strategy,
    strategy_code_hash,
    unregister_strategy,
)

ASOF = pd.Timestamp("2026-03-10")


class SyntheticEqualWeight(BaseStrategy):
    """Equal weight over the first ``top`` tickers (test-local, never in the packaged registry)."""

    id = "T_equal"

    @classmethod
    def validate_params(cls, params: Any) -> None:
        top = params.get("top")
        if not isinstance(top, int) or isinstance(top, bool) or top < 1:
            raise ValueError("top must be a positive integer")

    def compute_weights(self, features: pd.DataFrame, asof: pd.Timestamp) -> pd.Series:
        tickers = sorted(features["ticker"].unique())[: self.params["top"]]
        if not tickers:
            return pd.Series(dtype=float)
        return pd.Series(1.0 / len(tickers), index=tickers)


class SyntheticOther(SyntheticEqualWeight):
    id = "T_other"


FUTURE_ONLY = pd.DataFrame({"ticker": ["FUT"], "date": [date(2026, 3, 11)]})


class SyntheticPeek(BaseStrategy):
    """Cheats: weights a ticker it can only know from a row dated after asof."""

    id = "T_peek"

    def compute_weights(self, features: pd.DataFrame, asof: pd.Timestamp) -> pd.Series:
        return pd.Series({"FUT": 0.5, "AAA": 0.5})


def synthetic_features(last: date = date(2026, 3, 10)) -> pd.DataFrame:
    days = pd.bdate_range(end=pd.Timestamp(last), periods=3)
    rows = [(t, d.date()) for t in ("AAA", "BBB", "CCC") for d in days]
    return pd.DataFrame(rows, columns=["ticker", "date"]).assign(ret_5=0.01)


@pytest.fixture
def local_strategies() -> Iterator[None]:
    for cls in (SyntheticEqualWeight, SyntheticOther, SyntheticPeek):
        register_strategy(cls)
    yield
    for cls in (SyntheticEqualWeight, SyntheticOther, SyntheticPeek):
        unregister_strategy(cls.id)


def cfg_with(base: AppConfig, strategies: dict[str, Any]) -> AppConfig:
    return base.model_copy(update={"strategies": strategies})


# ------------------------------------------------------------------ validate_weights / asof_guard


def test_validate_weights_accepts_long_only_sum_to_one() -> None:
    w = validate_weights(pd.Series({"AAA": 0.5, "BBB": 0.5}))
    assert w.dtype == float
    validate_weights(pd.Series(dtype=float))  # all cash is valid
    validate_weights(pd.Series({"AAA": 0.6, "BBB": 0.4 + 5e-10}))  # inside the tolerance


@pytest.mark.parametrize(
    "weights",
    [
        pd.Series({"AAA": -0.1, "BBB": 0.5}),
        pd.Series({"AAA": np.nan, "BBB": 0.5}),
        pd.Series({"AAA": np.inf}),
        pd.Series({"AAA": 0.6, "BBB": 0.5}),
        pd.Series([0.5, 0.5], index=["AAA", "AAA"]),
        pd.Series([0.5, 0.5], index=[1, 2]),
    ],
)
def test_validate_weights_rejects_bad_weights(weights: pd.Series) -> None:
    with pytest.raises(WeightError):
        validate_weights(weights)


def test_validate_weights_rejects_non_series_and_unknown_tickers() -> None:
    with pytest.raises(WeightError, match="Series"):
        validate_weights([0.5, 0.5])  # type: ignore[arg-type]
    with pytest.raises(WeightError, match="universe"):
        validate_weights(pd.Series({"ZZZ": 0.5}), universe=["AAA"])


def test_asof_guard_passes_clamped_and_raises_on_later_rows() -> None:
    clean = synthetic_features(date(2026, 3, 10))
    assert asof_guard(clean, ASOF) is clean
    assert asof_guard(clean, date(2026, 3, 10)) is clean  # a plain date works too
    late = pd.concat([clean, FUTURE_ONLY.assign(ret_5=0.0)], ignore_index=True)
    with pytest.raises(LookaheadError, match="after asof"):
        asof_guard(late, ASOF)
    with pytest.raises(LookaheadError, match="date"):
        asof_guard(clean.drop(columns=["date"]), ASOF)


def test_base_strategy_refuses_future_rows_and_peeking_is_caught() -> None:
    equal = SyntheticEqualWeight({"top": 2}, ("short",))
    clean = synthetic_features()
    weights = equal.target_weights(clean, ASOF)
    assert weights.to_dict() == {"AAA": 0.5, "BBB": 0.5}

    late = pd.concat([clean, FUTURE_ONLY.assign(ret_5=0.0)], ignore_index=True)
    with pytest.raises(LookaheadError):
        equal.target_weights(late, ASOF)  # a future row never reaches compute_weights

    peek = SyntheticPeek({}, ("short",))
    with pytest.raises(WeightError, match="universe"):
        peek.target_weights(clean, ASOF)  # weights built on knowledge from beyond asof


def test_strategy_instances_satisfy_the_protocol() -> None:
    s = SyntheticEqualWeight({"top": 1}, ("short", "medium"))
    assert isinstance(s, Strategy)
    assert s.horizons == ("short", "medium")
    assert s.params == {"top": 1}


# ------------------------------------------------------------------ load_strategies


def test_empty_config_loads_nothing(engine_cfg: AppConfig) -> None:
    assert load_strategies(cfg_with(engine_cfg, {})) == []


def test_packaged_config_lists_the_builtin_strategies(engine_cfg: AppConfig) -> None:
    assert set(engine_cfg.strategies) == {"S00_composite", "S17_equal_weight"}
    assert {s.id for s in load_strategies(engine_cfg)} == set(engine_cfg.strategies)


def test_load_strategies_one_instance_per_param_set(
    engine_cfg: AppConfig, local_strategies: None
) -> None:
    cfg = cfg_with(
        engine_cfg,
        {
            "T_equal": {"horizons": ["short", "medium"], "params": [{"top": 1}, {"top": 2}]},
            "T_other": {"horizons": ["long"], "params": [{"top": 3}]},
        },
    )
    got = load_strategies(cfg)
    assert [(s.id, s.params["top"], s.horizons) for s in got] == [
        ("T_equal", 1, ("short", "medium")),
        ("T_equal", 2, ("short", "medium")),
        ("T_other", 3, ("long",)),
    ]


def test_disabled_entries_are_skipped_with_their_reason_logged(
    engine_cfg: AppConfig, local_strategies: None, caplog: pytest.LogCaptureFixture
) -> None:
    cfg = cfg_with(
        engine_cfg,
        {
            "T_equal": {"enabled": False, "reason": "pending P1-T04"},
            "S06_not_written_yet": {"enabled": False, "reason": "no data"},  # unknown but disabled
            "T_other": {"horizons": ["long"], "params": [{"top": 1}]},
        },
    )
    with caplog.at_level(logging.INFO, logger="vnstratlab.strategies.registry"):
        got = load_strategies(cfg)
    assert [s.id for s in got] == ["T_other"]
    assert "pending P1-T04" in caplog.text
    assert "no data" in caplog.text


def test_unknown_id_and_bad_params_raise_a_clear_config_error(
    engine_cfg: AppConfig, local_strategies: None
) -> None:
    cfg = cfg_with(
        engine_cfg,
        {
            "S99_missing": {"horizons": ["short"], "params": [{}]},
            "T_equal": {"horizons": ["short"], "params": [{"top": 2}, {"top": 0}]},
            "T_other": {"horizons": ["weekly"], "params": [{"top": 1}, {"top": 1}]},
        },
    )
    with pytest.raises(StrategyConfigError) as err:
        load_strategies(cfg)
    text = str(err.value)
    assert "strategies.S99_missing: unknown strategy id 'S99_missing'" in text
    assert "strategies.T_equal.params[1]: top must be a positive integer" in text
    assert "strategies.T_other.horizons: 'weekly'" in text
    assert len(err.value.problems) == 4  # every problem is reported at once


@pytest.mark.parametrize(
    ("entry", "needle"),
    [
        ("not a mapping", "must be a mapping"),
        ({"horizons": ["short"]}, ".params: must be a non-empty list"),
        ({"params": [{"top": 1}]}, ".horizons: must be a non-empty list"),
        ({"horizons": ["short"], "params": [{"top": 1}], "extra": 1}, "unknown key"),
        ({"horizons": ["short"], "params": ["x"]}, "must be a mapping with string keys"),
        ({"horizons": ["short"], "params": [{"top": 1}, {"top": 1}]}, "duplicate of an earlier"),
        ({"horizons": ["short", "short"], "params": [{"top": 1}]}, "duplicate 'short'"),
        ({"horizons": ["short"], "params": [{"top": float("nan")}]}, r"params\[0\]"),
        ({"enabled": "no", "horizons": ["short"], "params": [{"top": 1}]}, "true or false"),
    ],
)
def test_malformed_entries_are_rejected(
    engine_cfg: AppConfig, local_strategies: None, entry: object, needle: str
) -> None:
    with pytest.raises(StrategyConfigError, match=needle):
        load_strategies(cfg_with(engine_cfg, {"T_equal": entry}))


def test_register_strategy_rules(local_strategies: None) -> None:
    class NoId(BaseStrategy):
        def compute_weights(self, features: pd.DataFrame, asof: pd.Timestamp) -> pd.Series:
            return pd.Series(dtype=float)

    with pytest.raises(TypeError, match="'id'"):
        register_strategy(NoId)

    class Clash(NoId):
        id = "T_equal"

    with pytest.raises(ValueError, match="already registered"):
        register_strategy(Clash)
    assert register_strategy(SyntheticEqualWeight) is SyntheticEqualWeight  # idempotent
    assert {"T_equal", "T_other", "T_peek"} <= set(registry.registered_ids())
    with pytest.raises(KeyError, match="unknown strategy id"):
        registry.get_strategy_class("nope")


def test_packaged_registry_has_no_test_strategy() -> None:
    code = (
        "from vnstratlab.strategies.registry import registered_ids\n"
        "ids = registered_ids()\n"
        "assert ids == ['S00_composite', 'S17_equal_weight'], ids\n"
    )
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONPATH": str(Path(registry.__file__).parents[2])},
    )
    assert result.returncode == 0, result.stderr


# ------------------------------------------------------------------ trial identity


def test_canonical_params_json_ignores_key_order_and_frozen_views(engine_cfg: AppConfig) -> None:
    a = canonical_params_json({"vol_mult": 1.5, "lookback": 20})
    b = canonical_params_json({"lookback": 20, "vol_mult": 1.5})
    assert a == b == '{"lookback":20,"vol_mult":1.5}'
    assert canonical_params_json({"x": {"b": 1, "a": [1, 2]}}) == '{"x":{"a":[1,2],"b":1}}'
    from types import MappingProxyType

    assert canonical_params_json(MappingProxyType({"k": MappingProxyType({"z": 1})})) == (
        '{"k":{"z":1}}'
    )
    with pytest.raises(ValueError, match="Out of range"):
        canonical_params_json({"x": float("nan")})
    with pytest.raises(TypeError):
        canonical_params_json({"x": object()})


def test_trial_id_hand_checked_literal() -> None:
    """Pinned: any accidental change to the identity formula breaks this test."""
    got = compute_trial_id(
        "S_test", {"vol_mult": 1.5, "lookback": 20}, "short", "codehash-1", "fv-1", "engine-v1"
    )
    assert got == "cb5057434665065d"


def test_trial_id_changes_with_every_identity_part() -> None:
    base: dict[str, Any] = {
        "strategy_id": "S_test",
        "params": {"lookback": 20},
        "horizon": "short",
        "code_hash": "c1",
        "feature_version": "f1",
        "engine_version": "e1",
    }
    ids = {compute_trial_id(**base)}
    for key, value in [
        ("strategy_id", "S_other"),
        ("params", {"lookback": 21}),
        ("horizon", "medium"),
        ("code_hash", "c2"),
        ("feature_version", "f2"),
        ("engine_version", "e2"),
    ]:
        ids.add(compute_trial_id(**{**base, key: value}))
    assert len(ids) == 7


def test_trial_id_is_deterministic_across_processes_and_key_order() -> None:
    expected = compute_trial_id(
        "S_test", {"vol_mult": 1.5, "lookback": 20}, "short", "codehash-1", "fv-1", "engine-v1"
    )
    code = (
        "from vnstratlab.strategies.registry import compute_trial_id\n"
        "print(compute_trial_id('S_test', {'lookback': 20, 'vol_mult': 1.5}, 'short',"
        " 'codehash-1', 'fv-1', 'engine-v1'))\n"
    )
    src = str(Path(registry.__file__).parents[2])
    for seed in ("0", "1", "random"):
        result = subprocess.run(  # noqa: S603
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            check=True,
            env={**os.environ, "PYTHONPATH": src, "PYTHONHASHSEED": seed},
        )
        assert result.stdout.strip() == expected


def test_strategy_code_hash_follows_the_source_not_the_line_endings(tmp_path: Path) -> None:
    import importlib.util

    def load(name: str, text: str, newline: str) -> type:
        path = tmp_path / f"{name}.py"
        path.write_bytes(text.replace("\n", newline).encode())
        spec = importlib.util.spec_from_file_location(name, path)
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module.Klass  # type: ignore[no-any-return]

    src = "class Klass:\n    value = 1\n"
    try:
        lf = strategy_code_hash(load("synthetic_mod_a", src, "\n"))
        crlf = strategy_code_hash(load("synthetic_mod_b", src, "\r\n"))
        edited = strategy_code_hash(load("synthetic_mod_c", src.replace("1", "2"), "\n"))
    finally:
        for name in ("synthetic_mod_a", "synthetic_mod_b", "synthetic_mod_c"):
            sys.modules.pop(name, None)
    assert lf == crlf  # line endings are normalised
    assert edited != lf  # a code edit changes the hash
    assert len(lf) == 64
    assert strategy_code_hash(SyntheticEqualWeight) == strategy_code_hash(SyntheticOther)  # module


def test_strategy_code_hash_needs_importable_source() -> None:
    class Orphan:
        pass

    Orphan.__module__ = "synthetic_not_imported"
    with pytest.raises(ValueError, match="not imported"):
        strategy_code_hash(Orphan)
    Orphan.__module__ = "builtins"  # a module without Python source
    with pytest.raises(ValueError, match="no source"):
        strategy_code_hash(Orphan)


def test_make_trial_spec_uses_code_hash_and_checks_horizon() -> None:
    s = SyntheticEqualWeight({"top": 2}, ("short",))
    spec = make_trial_spec(s, "short", "fv", ENGINE_VERSION)
    assert spec.strategy_code_hash == strategy_code_hash(SyntheticEqualWeight)
    assert spec.params_json == '{"top":2}'
    other = make_trial_spec(s, "short", "fv", ENGINE_VERSION, code_hash="edited")
    assert other.trial_id != spec.trial_id  # a code change is a new trial
    with pytest.raises(ValueError, match="does not run on horizon"):
        make_trial_spec(s, "long", "fv", ENGINE_VERSION)


def test_register_strategy_refuses_a_class_outside_base_strategy() -> None:
    class Rogue:
        id = "T_rogue"

        def __init__(self, params: Any, horizons: Any) -> None:
            self.params, self.horizons = params, horizons

        def target_weights(self, features: pd.DataFrame, asof: pd.Timestamp) -> pd.Series:
            return pd.Series({"ZZZ": 5.0})

    with pytest.raises(TypeError, match="BaseStrategy"):
        register_strategy(Rogue)  # type: ignore[type-var]
    assert "T_rogue" not in registry.registered_ids()


def test_asof_guard_names_a_timezone_mismatch() -> None:
    naive = synthetic_features()
    with pytest.raises(LookaheadError, match="timezone mismatch"):
        asof_guard(naive, pd.Timestamp("2026-03-10", tz="Asia/Ho_Chi_Minh"))
    aware = naive.assign(date=pd.to_datetime(naive["date"]).dt.tz_localize("UTC"))
    with pytest.raises(LookaheadError, match="timezone mismatch"):
        asof_guard(aware, ASOF)
    assert asof_guard(aware, pd.Timestamp("2026-03-10", tz="UTC")) is aware
