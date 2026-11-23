from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("gold_strategy", HERE / "strategy.py")
strategy = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(strategy)


def test_strategy_targets() -> None:
    index = pd.date_range("2026-01-01", periods=4, freq="B")
    panel = pd.DataFrame(
        {
            "close": [1.0, 1.1, 1.2, 1.3],
            "monthly_m1_target": [1.0, 1.0, 0.0, 1.0],
            "vol15_scale": [0.8, 0.5, 1.0, 1.0],
        },
        index=index,
    )
    target = strategy.strategy_targets(panel)
    assert target["M1"].tolist() == [1.0, 1.0, 0.0, 1.0]
    assert np.allclose(target["M1_VOL15"], [0.8, 0.5, 0.0, 1.0])


def test_simulation_is_self_financing() -> None:
    index = pd.date_range("2026-01-01", periods=4, freq="B")
    price = pd.Series([1.0, 1.1, 1.05, 1.2], index=index)
    target = pd.Series([1.0, 1.0, 0.5, 0.0], index=index)
    ledger = strategy.simulate(price, target, fee_bp=10)
    residual = (
        ledger["nav"] - ledger["cash"] - ledger["units"] * ledger["close"]
    ).abs()
    assert residual.max() < 1e-10
    assert ledger["exposure"].between(0.0, 1.0 + 1e-10).all()
    assert ledger["trade_notional"].ge(0.0).all()


def test_full_sample_metrics_are_frozen() -> None:
    panel = strategy.load_panel()
    _, metrics = strategy.run_all(panel)
    rows = metrics.set_index(["strategy", "fee_bp", "window"])
    m1 = rows.loc[("M1", 10, "full_2017")]
    vol = rows.loc[("M1_VOL15", 10, "full_2017")]
    assert abs(m1["cagr"] - 0.148965) < 5e-6
    assert abs(m1["sharpe"] - 1.224996) < 5e-6
    assert abs(m1["max_drawdown"] + 0.171373) < 5e-6
    assert abs(vol["cagr"] - 0.133334) < 5e-6
    assert abs(vol["sharpe"] - 1.269511) < 5e-6
    assert abs(vol["max_drawdown"] + 0.130929) < 5e-6


def test_current_target_is_flat() -> None:
    panel = strategy.load_panel()
    target = strategy.strategy_targets(panel).iloc[-1]
    assert target["M1"] == 0.0
    assert target["M1_VOL15"] == 0.0
