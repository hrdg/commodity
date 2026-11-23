from __future__ import annotations

import numpy as np
import pandas as pd

import run


def test_h5_blocks_lower_bm5_candidate() -> None:
    score = pd.Series({"A": 1.0, "B": 0.8, "C": 0.2})
    bm5 = pd.Series({"A": 0.01, "B": 0.03, "C": -0.1})
    blocked, bm_target, bm_hold = run.h5_blocks_switch(
        "A", "B", False, score, bm5
    )
    assert blocked is True
    assert bm_target == 0.01
    assert bm_hold == 0.03


def test_h5_preserves_take_profit_and_missing_bm_fallback() -> None:
    score = pd.Series({"A": 1.0, "B": 0.8})
    bm5 = pd.Series({"A": 0.01, "B": 0.03})
    assert run.h5_blocks_switch("A", "B", True, score, bm5)[0] is False
    assert run.h5_blocks_switch("A", "B", False, score, pd.Series(dtype=float))[0] is False


def test_h6_swaps_only_near_tie_when_bm5_disagrees() -> None:
    score = pd.Series({"A": 1.00, "B": 0.80, "C": 0.10})
    z_score = pd.Series({"A": 1.00, "B": 0.80, "C": -1.00})
    bm5 = pd.Series({"A": 0.01, "B": 0.03, "C": -0.10})
    adjusted, detail = run.apply_h6_near_tie(score, z_score, bm5)
    ranked = adjusted.sort_values(ascending=False, kind="stable")
    assert list(ranked.index[:2]) == ["B", "A"]
    assert detail is not None
    assert np.isclose(detail["c5_z_gap"], 0.2)


def test_h6_does_not_swap_outside_fixed_gap() -> None:
    score = pd.Series({"A": 1.00, "B": 0.60})
    z_score = pd.Series({"A": 1.00, "B": 0.60})
    bm5 = pd.Series({"A": 0.01, "B": 0.03})
    adjusted, detail = run.apply_h6_near_tie(score, z_score, bm5)
    assert adjusted.equals(score)
    assert detail is None


def test_h6_does_not_trade_on_floating_zero() -> None:
    score = pd.Series({"A": 1.00, "B": 0.99})
    z_score = pd.Series({"A": 1.00, "B": 0.99})
    bm5 = pd.Series({"A": 0.0, "B": 3.7e-17})
    adjusted, detail = run.apply_h6_near_tie(score, z_score, bm5)
    assert adjusted.equals(score)
    assert detail is None


def test_baseline_replay_matches_r1() -> None:
    opens, closes, splices, bm5, c5_daily = run.load_inputs()
    month_dates = bm5.dropna().index.intersection(c5_daily.index)
    c5_signal = c5_daily.reindex(month_dates).reindex(columns=run.R1M.basis.NODE_GROUPS)
    first_execution = int(
        np.searchsorted(
            closes.index.values, month_dates.min().to_datetime64(), side="right"
        )
    )
    ledger = run.simulate(
        "b0",
        0.0005,
        first_execution,
        closes,
        opens,
        c5_signal,
        c5_daily,
        bm5,
        splices,
    )
    r1_returns = pd.read_csv(run.R1_RETURNS, index_col=0, parse_dates=True)
    pair = pd.concat(
        [
            ledger["ret"].rename("local"),
            r1_returns["B0_C5_NODD_5bp"].rename("r1"),
        ],
        axis=1,
    ).dropna()
    assert (pair["local"] - pair["r1"]).abs().max() < 1e-12
