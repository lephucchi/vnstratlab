"""Risk layer: sizing, caps, vol scaling, circuit breaker, invariants (synthetic numbers)."""

from __future__ import annotations

import logging
import math

import numpy as np
import pandas as pd
import pytest

from vnstratlab.config.models import AppConfig, Risk
from vnstratlab.risk import RiskLayer

EQUITY = 100_000_000.0


def layer(cfg: AppConfig, **over: float | int | None) -> RiskLayer:
    return RiskLayer(cfg.risk.model_copy(update=over))


def w(**x: float) -> pd.Series:
    return pd.Series(x, dtype=float)


def apply(
    rl: RiskLayer,
    weights: pd.Series,
    *,
    atr: float = 100.0,
    price: float = 50_000.0,
    equity: float = EQUITY,
    peak: float = EQUITY,
    held: dict[str, float] | None = None,
    cooldown: tuple[str, ...] = (),
    returns: pd.Series | None = None,
):  # type: ignore[no-untyped-def]
    tickers = set(weights.index) | set(held or {})
    return rl.apply(
        weights,
        equity=equity,
        prices_close=dict.fromkeys(tickers, price),
        atr=dict.fromkeys(tickers, atr),
        held=held or {},
        peak_equity=peak,
        cooldown=cooldown,
        returns_history=returns,
    )


def test_config_default_cooldown_is_null(engine_cfg: AppConfig) -> None:
    assert engine_cfg.risk.stop_cooldown_sessions is None
    assert isinstance(engine_cfg.risk, Risk)


def test_sizing_caps_weight_at_one_percent_risk(engine_cfg: AppConfig) -> None:
    # Equity 100,000,000, risk 1 % = 1,000,000; stop distance 2 x 1,500 = 3,000 per share
    # -> 333.33 shares x 50,000 = 16,666,667 = weight 0.16667.
    out = apply(layer(engine_cfg), w(AAA=0.30), atr=1_500, price=50_000)
    # (the 0.35 max weight does not bind: 0.30 is cut by sizing)
    assert out.weights["AAA"] == pytest.approx(1 / 6)
    assert out.reasons["AAA"] == ["sizing"]
    # A smaller request is left alone.
    assert apply(layer(engine_cfg), w(AAA=0.10), atr=1_500).weights["AAA"] == pytest.approx(0.10)


def test_max_weight_per_ticker(engine_cfg: AppConfig) -> None:
    # ATR tiny so sizing does not bind (cap = 0.01 x 50,000 / (2 x 10) = 25 -> huge).
    out = apply(layer(engine_cfg), w(AAA=0.50, BBB=0.30), atr=10)
    assert out.weights["AAA"] == pytest.approx(0.35)  # capped at max_weight_per_ticker
    assert out.weights["BBB"] == pytest.approx(0.30)
    assert out.reasons == {"AAA": ["max_weight"]}


def test_max_positions_keeps_largest_and_breaks_ties_by_ticker(engine_cfg: AppConfig) -> None:
    rl = layer(engine_cfg)  # max_positions = 4
    req = w(A=0.05, B=0.20, C=0.10, D=0.15, E=0.10, F=0.10)
    out = apply(rl, req, atr=10).weights
    # Largest four: B 0.20, D 0.15, then C, E, F tie at 0.10 -> alphabetical: C and E kept.
    assert sorted(out[out > 0].index) == ["B", "C", "D", "E"]
    assert out.get("A", 0.0) == 0
    assert out.get("F", 0.0) == 0
    assert (out > 0).sum() == 4
    # Same input in another order gives the same result (deterministic).
    again = apply(rl, req.iloc[::-1], atr=10).weights
    assert again.sort_index().equals(out.sort_index())
    two = apply(layer(engine_cfg, max_positions=2), req, atr=10).weights
    assert sorted(two[two > 0].index) == ["B", "D"]


def test_cooldown_never_buys_but_keeps_holdings(engine_cfg: AppConfig) -> None:
    rl = layer(engine_cfg)
    # AAA in cooldown, not held -> dropped. BBB in cooldown, held 100 sh x 50,000 = 0.05
    # of equity, requested 0.20 -> stays at 0.05 (not increased). Requested 0.02 -> 0.02.
    held = {"BBB": 100.0, "CCC": 100.0}
    out = apply(rl, w(AAA=0.10, BBB=0.20, CCC=0.02), held=held, cooldown=("AAA", "BBB", "CCC"))
    assert out.weights["AAA"] == 0
    assert out.weights["BBB"] == pytest.approx(0.05)
    assert out.weights["CCC"] == pytest.approx(0.02)
    assert out.reasons["AAA"] == ["cooldown"]


def test_unknown_atr_blocks_new_entries_only(engine_cfg: AppConfig) -> None:
    rl = layer(engine_cfg)
    out = rl.apply(
        w(AAA=0.2, BBB=0.2),
        equity=EQUITY,
        prices_close={"AAA": 50_000.0, "BBB": 50_000.0},
        atr={"AAA": math.nan},
        held={"BBB": 100.0},
        peak_equity=EQUITY,
    )
    # AAA: new entry without ATR -> 0. BBB: no ATR entry at all -> held weight 0.05 kept.
    assert out.weights["AAA"] == 0
    assert out.weights["BBB"] == pytest.approx(0.05)
    assert out.reasons["AAA"] == ["no_atr"]


def test_vol_scaling_off_when_target_is_null(engine_cfg: AppConfig) -> None:
    returns = pd.Series([0.05, -0.05] * 10)  # very volatile
    out = apply(layer(engine_cfg), w(AAA=0.2), atr=10, returns=returns)
    assert engine_cfg.risk.vol_target_annual is None
    assert out.weights["AAA"] == pytest.approx(0.2)
    assert out.vol_scale == 1.0


def test_vol_scaling_scales_down_never_up(engine_cfg: AppConfig) -> None:
    rl = layer(engine_cfg, vol_target_annual=0.10)
    # 20 returns alternating +1 % / -1 %: mean 0, sample variance = 20 x 0.0001 / 19,
    # std = 0.0102598, x sqrt(252) = 0.162869 annual. Scale = 0.10 / 0.162869 = 0.613990.
    returns = pd.Series([0.01, -0.01] * 10)
    out = apply(rl, w(AAA=0.20, BBB=0.10), atr=10, returns=returns)
    assert out.vol_scale == pytest.approx(0.6139903)
    assert out.weights["AAA"] == pytest.approx(0.20 * 0.6139903)
    assert out.weights["BBB"] == pytest.approx(0.10 * 0.6139903)
    # Calm market: 0.1 % alternating -> realised 0.0160 < target -> scale would be > 1 -> 1.
    calm = pd.Series([0.001, -0.001] * 10)
    up = apply(rl, w(AAA=0.20), atr=10, returns=calm)
    assert up.vol_scale == 1.0
    assert up.weights["AAA"] == pytest.approx(0.20)
    # Fewer than 20 returns: no scaling; flat returns (zero vol): no scaling.
    assert apply(rl, w(AAA=0.2), atr=10, returns=returns.iloc[:19]).vol_scale == 1.0
    assert apply(rl, w(AAA=0.2), atr=10, returns=pd.Series([0.0] * 20)).vol_scale == 1.0


def test_circuit_breaker_blocks_buys_and_allows_sells(engine_cfg: AppConfig) -> None:
    rl = layer(engine_cfg)  # drawdown 10 % -> threshold 100M x 0.9 = 90,000,000
    # Equity 89.9M <= 90.0M -> breaker on. AAA held 100 sh x 50,000 = 5,000,000
    # / 89,900,000 = 0.05562. Requests: AAA 0.20 (increase), BBB 0.10 (new), CCC 0.01
    # (below its held weight 0.05562 -> a reduction passes unchanged).
    held = {"AAA": 100.0, "CCC": 100.0}
    out = apply(rl, w(AAA=0.20, BBB=0.10, CCC=0.01), atr=10, equity=89_900_000, held=held)
    held_w = 100 * 50_000 / 89_900_000
    assert out.alert is True
    assert out.weights["AAA"] == pytest.approx(held_w)  # not increased
    assert out.weights["BBB"] == 0  # no new buy
    assert out.weights["CCC"] == pytest.approx(0.01)  # a sell (reduction) is allowed
    assert "circuit_breaker" in out.reasons["BBB"]
    # Exit entirely is allowed.
    assert apply(rl, w(), atr=10, equity=89_900_000, held=held).weights.empty
    # Re-arm: equity back above the threshold (90,000,001 > 90,000,000) -> buys allowed again.
    back = apply(rl, w(AAA=0.20, BBB=0.10), atr=10, equity=90_000_001, held=held)
    assert back.alert is False
    assert back.weights["BBB"] == pytest.approx(0.10)
    assert back.weights["AAA"] == pytest.approx(0.20)
    # Exactly at the threshold counts as breached (<=).
    assert rl.breaker_active(90_000_000, 100_000_000)
    assert not rl.breaker_active(90_000_001, 100_000_000)


def test_stop_price_formula(engine_cfg: AppConfig) -> None:
    # entry 50,050, ATR 1,500, multiple 2 -> 50,050 - 3,000 = 47,050.
    assert layer(engine_cfg).stop_price(50_050, 1_500) == pytest.approx(47_050)


def test_rejects_bad_inputs(engine_cfg: AppConfig) -> None:
    rl = layer(engine_cfg)
    with pytest.raises(ValueError, match="long-only"):
        apply(rl, w(AAA=-0.1))
    with pytest.raises(ValueError, match="equity"):
        apply(rl, w(AAA=0.1), equity=0)
    # Ticker without a price cannot be sized -> dropped.
    out = rl.apply(w(AAA=0.1), equity=EQUITY, prices_close={}, atr={}, held={}, peak_equity=EQUITY)
    assert out.weights["AAA"] == 0
    assert out.reasons["AAA"] == ["no_price"]


def test_property_output_never_exceeds_request(engine_cfg: AppConfig) -> None:
    rng = np.random.default_rng(20261117)
    cases = 400
    for case in range(cases):
        n = int(rng.integers(1, 9))
        tickers = [f"T{i}" for i in range(n)]
        raw = rng.random(n) * (rng.random(n) < 0.7)
        total = raw.sum()
        req = pd.Series(raw / max(total, 1.0) * rng.random(), index=tickers)
        prices = {t: float(rng.integers(5, 200) * 1_000) for t in tickers}
        atrs = {t: float(rng.random() * 3_000) if rng.random() < 0.9 else math.nan for t in tickers}
        held = {t: float(rng.integers(0, 2_000)) for t in tickers if rng.random() < 0.5}
        equity = float(rng.integers(20, 150)) * 1_000_000
        cfg = engine_cfg.risk.model_copy(
            update={
                "vol_target_annual": [None, 0.05, 0.2][case % 3],
                "max_positions": int(rng.integers(1, 6)),
            }
        )
        returns = pd.Series(rng.normal(0, 0.02, 25))
        out = RiskLayer(cfg).apply(
            req,
            equity=equity,
            prices_close=prices,
            atr=atrs,
            held=held,
            peak_equity=100_000_000.0,
            cooldown=[t for t in tickers if rng.random() < 0.2],
            returns_history=returns,
        )
        for t, value in out.weights.items():
            assert -1e-12 <= value <= req[t] + 1e-12, (case, t)
        assert out.weights.sum() <= 1 + 1e-9
        assert (out.weights > 1e-12).sum() <= cfg.max_positions
        if out.alert:  # breaker: no weight above its held weight
            for t, value in out.weights.items():
                held_w = held.get(t, 0.0) * prices[t] / equity
                assert value <= held_w + 1e-9


def test_blocked_decisions_log_at_debug_not_warning(
    engine_cfg: AppConfig, caplog: pytest.LogCaptureFixture
) -> None:
    rl = layer(engine_cfg)
    caplog.set_level(logging.DEBUG, logger="vnstratlab.risk.layer")
    for _ in range(3):
        assert apply(rl, w(AAA=0.1), equity=89_900_000).alert is True
    assert [r.levelno for r in caplog.records] == [logging.DEBUG] * 3
