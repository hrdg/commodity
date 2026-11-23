from __future__ import annotations

import numpy as np
import pandas as pd

import run


def test_monthly_eligibility_combines_absolute_and_relative() -> None:
    dates = pd.date_range("2020-01-31", periods=14, freq="ME")
    columns = list(run.NODES)
    closes = pd.DataFrame(
        np.array(
            [
                [1.0 + 0.01 * step + 0.001 * node for node in range(6)]
                for step in range(14)
            ]
        ),
        index=dates,
        columns=columns,
    )
    absolute, dual = run.monthly_eligibility(closes, pd.DatetimeIndex(dates))
    assert absolute.loc[dates[-1]].all()
    assert int(dual.loc[dates[-1]].sum()) == 4


def test_fixed_monthly_blend() -> None:
    idx = pd.PeriodIndex(["2021-01", "2021-02"], freq="M")
    first = pd.Series([0.1, 0.0], index=idx)
    second = pd.Series([0.0, 0.2], index=idx)
    blended = 0.5 * first + 0.5 * second
    assert np.allclose(blended.to_numpy(), [0.05, 0.10])


def test_h6_rule_uses_only_eligible_top_two() -> None:
    score = pd.Series({"A": 1.0, "B": 0.99, "C": 0.95, "D": 0.1, "E": 0.0, "F": -0.1})
    z_score = pd.Series({"A": 1.0, "B": 0.99, "C": 0.95, "D": 0.1, "E": 0.0, "F": -0.1})
    bm5 = pd.Series({"A": -0.01, "B": 0.02, "C": 0.03, "D": 0.0, "E": 0.0, "F": 0.0})
    adjusted, detail = run.M.apply_h6_near_tie(score, z_score, bm5)
    ranked = adjusted.sort_values(ascending=False)
    assert list(ranked.index[:2]) == ["B", "A"]
    assert detail is not None
