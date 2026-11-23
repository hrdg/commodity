from __future__ import annotations

import numpy as np
import pandas as pd

import run


def test_blend_cost_is_symmetric() -> None:
    idx = pd.date_range("2021-01-31", periods=2, freq="ME")
    a = pd.Series([0.10, 0.0], index=idx)
    b = pd.Series([0.0, 0.10], index=idx)
    raw = 0.5 * a + 0.5 * b
    blended = run.blend_two(a, b, 0.0005)
    assert np.allclose(blended, raw - 0.0005 * 2 * abs(0.5 * 1.1 / 1.05 - 0.5))


def test_common_month_alignment() -> None:
    a = pd.Series([0.01], index=[pd.Timestamp("2021-01-31")])
    b = pd.Series([0.02], index=[pd.Timestamp("2021-02-28")])
    assert run.blend_two(a, b, 0.0).empty
