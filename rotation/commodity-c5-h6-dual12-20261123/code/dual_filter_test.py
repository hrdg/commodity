from __future__ import annotations

import numpy as np
import pandas as pd

import run


def test_momentum_window_is_compounded() -> None:
    dates = pd.date_range("2020-01-31", periods=12, freq="ME")
    panel = pd.DataFrame(
        {"date": list(dates) * 8,
         "product": np.repeat([f"P{i}" for i in range(8)], 12),
         "r_first": 0.01}
    ).sort_values(["product", "date"]).reset_index(drop=True)
    out = run.add_momentum(panel, 6)
    assert out.groupby("product")["mom6"].apply(lambda s: s.iloc[:5].isna().all()).all()
    assert np.allclose(out.groupby("product")["mom6"].last(), 1.01**6 - 1)


def test_dual_filter_requires_both_absolute_and_relative() -> None:
    date = pd.Timestamp("2022-01-31")
    products = [f"P{i}" for i in range(8)]
    frame = pd.DataFrame(
        {
            "date": [date] * 8,
            "product": products,
            "bm5": np.arange(8.0),
            "mom6": [-0.2, -0.1, 0.01, 0.02, 0.04, 0.05, 0.06, 0.07],
            "y_nearby": np.arange(8.0) / 100,
        }
    )
    weights, diag = run.portfolio_weights(frame, "bm5", "y_nearby", momentum="mom6", dual=True)
    eligible = set(diag.loc[diag["reason"].eq("OK"), "eligible_count"])
    assert eligible == {5}
    assert len(weights) == 1
    assert weights.iloc[0]["product"] == "P7"


def test_filtered_cash_when_fewer_than_three() -> None:
    date = pd.Timestamp("2022-01-31")
    frame = pd.DataFrame(
        {
            "date": [date] * 8,
            "product": [f"P{i}" for i in range(8)],
            "bm5": np.arange(8.0),
            "mom6": [-0.2, -0.1, -0.05, -0.01, 0.01, 0.02, -0.03, -0.04],
            "y_nearby": np.arange(8.0) / 100,
        }
    )
    weights, diag = run.portfolio_weights(frame, "bm5", "y_nearby", momentum="mom6", dual=True)
    assert weights.empty
    assert bool(diag.iloc[0]["cash"])
