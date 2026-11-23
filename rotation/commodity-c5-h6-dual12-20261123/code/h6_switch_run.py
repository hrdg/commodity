"""Test BM5 as a commodity switch-event confirmation or near-tie signal."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


RUN = Path(__file__).resolve().parents[1]
R1 = Path(
    "/Users/hsh/Documents/Quant/科技轮动/research/runs/"
    "aw7_commodity_basis_momentum_20261123"
)
R1_RUN = R1 / "reproduction/run.py"
R1_PANEL = R1 / "artifacts/monthly_basis_signals.csv"
R1_RETURNS = R1 / "artifacts/daily_returns.csv"
PARENT = Path(
    "/Users/hsh/Documents/Quant/大类择时/research/runs/"
    "c5_six_commodity_proxy2015_20261109"
)
PARENT_RUN = PARENT / "run.py"
PARENT_AUDIT = PARENT / "event_audit.py"
ART = RUN / "artifacts"
NEAR_TIE_GAP = 0.25
BM_TOL = 1e-12


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


R1M = load_module("r1_basis_run", R1_RUN)
CURRENT = load_module("current_c5", PARENT_RUN)
AUDIT = load_module("current_dd_audit", PARENT_AUDIT)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def json_safe(value):
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if isinstance(value, (np.floating, float)):
        return None if not np.isfinite(value) else float(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, pd.Timestamp):
        return str(value.date())
    return value


def load_inputs():
    opens, closes, _, splices = CURRENT.build_asset_panel()
    opens = opens.loc[:"2026-11-06"]
    closes = closes.loc[:"2026-11-06"]
    panel = pd.read_csv(R1_PANEL, index_col=0, parse_dates=True)
    bm5 = R1M.node_matrix(panel, "bm5").reindex(columns=R1M.basis.NODE_GROUPS)
    c5_daily = CURRENT.B.momentum_scores(closes, 25, 250)
    return opens, closes, splices, bm5, c5_daily


def apply_h6_near_tie(
    score: pd.Series,
    z_score: pd.Series,
    bm5_day: pd.Series,
) -> tuple[pd.Series, dict | None]:
    """Swap only the C5 top-two order when their z gap is near and BM5 disagrees."""
    ranked = score.dropna().sort_values(ascending=False, kind="stable")
    if len(ranked) < 2:
        return score, None
    first, second = ranked.index[:2]
    z_gap = z_score.get(first, np.nan) - z_score.get(second, np.nan)
    bm_first = bm5_day.get(first, np.nan)
    bm_second = bm5_day.get(second, np.nan)
    if not (
        np.isfinite(z_gap)
        and z_gap <= NEAR_TIE_GAP
        and np.isfinite(bm_first)
        and np.isfinite(bm_second)
        and bm_second - bm_first > BM_TOL
    ):
        return score, None
    adjusted = score.copy()
    adjusted.loc[first], adjusted.loc[second] = score.loc[second], score.loc[first]
    return adjusted, {
        "c5_first": first,
        "c5_second": second,
        "c5_z_gap": float(z_gap),
        "bm5_first": float(bm_first),
        "bm5_second": float(bm_second),
    }


def h5_blocks_switch(
    target: str | None,
    hold: str | None,
    take_profit: bool,
    score: pd.Series,
    bm5_day: pd.Series,
) -> tuple[bool, float | None, float | None]:
    """Relative BM5 gate for discretionary C5 switches."""
    if target is None or hold is None or target == hold or take_profit:
        return False, None, None
    if target not in score.index or hold not in score.index:
        return False, None, None
    bm_target = bm5_day.get(target, np.nan)
    bm_hold = bm5_day.get(hold, np.nan)
    if not np.isfinite(bm_target) or not np.isfinite(bm_hold):
        return False, None, None
    return bool(bm_target < bm_hold), float(bm_target), float(bm_hold)


def simulate(
    mode: str,
    cost: float,
    first_execution: int,
    closes: pd.DataFrame,
    opens: pd.DataFrame,
    scores: pd.DataFrame,
    c5_daily: pd.DataFrame,
    bm5: pd.DataFrame,
    splices: pd.DataFrame,
    freeze_dates: set[pd.Timestamp] | None = None,
    exclude_h6_decisions: set[pd.Timestamp] | None = None,
    bm5_permute_seed: int | None = None,
) -> pd.DataFrame:
    z_r2 = CURRENT.B.zscore(c5_daily)
    eff = CURRENT.B.efficiency(closes)
    beta = CURRENT.B.beta252(closes)
    trail = closes.pct_change(10, fill_method=None)
    hold = None
    unlock: dict[str, int] = {}
    splice_dates = set(pd.to_datetime(splices["actual_start"])) if len(splices) else set()
    rows = []
    for i in range(first_execution, len(closes) - 1):
        d = i - 1
        decision = closes.index[d]
        rebalance = i == first_execution or (
            closes.index[i].month != closes.index[i - 1].month
        )
        original_target = hold
        target = hold
        take_profit = False
        veto = False
        blocked = False
        swapped = None
        bm_target = None
        bm_hold = None
        gross_planned = 0.0
        if rebalance:
            if decision not in scores.index:
                target = None
            else:
                raw_score = scores.loc[decision].dropna()
                chosen_score = raw_score
                bm5_day = bm5.loc[decision] if decision in bm5.index else pd.Series(dtype=float)
                if mode == "h6" and bm5_permute_seed is not None and len(bm5_day):
                    rng = np.random.default_rng(
                        bm5_permute_seed + int(decision.strftime("%Y%m%d"))
                    )
                    bm5_day = pd.Series(
                        rng.permutation(bm5_day.to_numpy(float)),
                        index=bm5_day.index,
                    )
                if (
                    mode == "h6"
                    and decision in bm5.index
                    and decision not in (exclude_h6_decisions or set())
                ):
                    chosen_score, swapped = apply_h6_near_tie(
                        raw_score, z_r2.loc[decision], bm5_day
                    )
                if len(chosen_score) < 2:
                    target = None
                else:
                    original_target, unlock, take_profit, veto = CURRENT.B.choose(
                        chosen_score,
                        z_r2.iloc[d],
                        eff.iloc[d],
                        beta.iloc[d],
                        hold,
                        trail.iloc[d],
                        i,
                        unlock,
                        rank2=True,
                        hold_k=2,
                    )
                    target = original_target
                    if original_target is not None:
                        gross_planned = float(
                            opens.iloc[i + 1][original_target]
                            / opens.iloc[i][original_target]
                            - 1.0
                        )
                    if swapped is not None:
                        bm_target = (
                            float(bm5_day.get(original_target))
                            if original_target is not None
                            else None
                        )
                        bm_hold = (
                            float(bm5_day.get(hold))
                            if hold is not None
                            else None
                        )
                    if mode == "h5" and decision in bm5.index:
                        blocked, bm_target, bm_hold = h5_blocks_switch(
                            original_target,
                            hold,
                            take_profit,
                            raw_score,
                            bm5_day,
                        )
                    elif (
                        mode == "h5_placebo"
                        and freeze_dates is not None
                        and hold is not None
                        and original_target is not None
                        and original_target != hold
                        and not take_profit
                        and decision in freeze_dates
                    ):
                        blocked = True
                    if blocked:
                        target = hold
        if target == hold:
            turnover = 0.0
        elif target is None or hold is None:
            turnover = 1.0
        else:
            turnover = 2.0
        gross = 0.0 if target is None else float(
            opens.iloc[i + 1][target] / opens.iloc[i][target] - 1.0
        )
        splice_fee = (
            2.0 * cost
            if target is not None and target == hold and closes.index[i] in splice_dates
            else 0.0
        )
        net = gross - cost * turnover - splice_fee
        rows.append(
            {
                "date": closes.index[i],
                "decision": decision,
                "rebalance": rebalance,
                "planned_target": original_target,
                "hold": target,
                "gross": gross,
                "planned_gross": gross_planned,
                "missed_gross": (gross_planned - gross) if blocked else 0.0,
                "ret": net,
                "turnover": turnover,
                "splice_fee": splice_fee,
                "take_profit": take_profit,
                "veto": veto,
                "h5_blocked": blocked,
                "bm5_target": bm_target,
                "bm5_hold": bm_hold,
                "h6_swapped": swapped is not None,
                "h6_c5_first": None if swapped is None else swapped["c5_first"],
                "h6_c5_second": None if swapped is None else swapped["c5_second"],
                "h6_z_gap": None if swapped is None else swapped["c5_z_gap"],
            }
        )
        hold = target
    return pd.DataFrame(rows).set_index("date")


def compound(values: pd.Series) -> float:
    values = values.dropna()
    return float((1.0 + values).prod() - 1.0)


def main() -> None:
    ART.mkdir(parents=True, exist_ok=True)
    opens, closes, splices, bm5, c5_daily = load_inputs()
    month_dates = bm5.dropna().index.intersection(c5_daily.index)
    if len(month_dates) <= 12:
        raise RuntimeError("insufficient common BM5/C5 dates")
    c5_signal = c5_daily.reindex(month_dates).reindex(columns=R1M.basis.NODE_GROUPS)
    first_signal = month_dates.min()
    first_execution = int(
        np.searchsorted(closes.index.values, first_signal.to_datetime64(), side="right")
    )

    ledgers: dict[str, dict[float, pd.DataFrame]] = {
        mode: {} for mode in ("b0", "h5", "h6")
    }
    for mode in ledgers:
        for cost_bps in (5.0, 20.5):
            ledger = simulate(
                mode,
                cost_bps / 10000.0,
                first_execution,
                closes,
                opens,
                c5_signal,
                c5_daily,
                bm5,
                splices,
            )
            ledgers[mode][cost_bps] = ledger
            ledger.to_csv(ART / f"ledger_{mode.upper()}_{cost_bps:g}bp.csv")

    r1_returns = pd.read_csv(R1_RETURNS, index_col=0, parse_dates=True)
    baseline_pair = pd.concat(
        [
            ledgers["b0"][5.0]["ret"].rename("local"),
            r1_returns["B0_C5_NODD_5bp"].rename("r1"),
        ],
        axis=1,
    ).dropna()
    baseline_engine_error = float(
        (baseline_pair["local"] - baseline_pair["r1"]).abs().max()
    )
    if baseline_engine_error > 1e-12:
        raise RuntimeError(f"baseline replay failed: {baseline_engine_error}")

    returns: dict[str, pd.Series] = {}
    exposures: dict[str, pd.Series] = {}
    ledgers_by_arm: dict[str, pd.DataFrame] = {}
    rows = []
    for mode, label in (("b0", "B0_C5"), ("h5", "H5_SWITCH_CONFIRM"), ("h6", "H6_NEAR_TIE")):
        for cost_bps in (5.0, 20.5):
            ledger = ledgers[mode][cost_bps]
            raw_name = f"{label}_NODD_{cost_bps:g}bp"
            risk_name = f"{label}_TIPDD_{cost_bps:g}bp"
            risk_ret, risk_exp = AUDIT.apply_tip_dd_lagged(
                ledger["ret"], cost_bps / 10000.0, tip_name="S"
            )
            returns[raw_name] = ledger["ret"]
            returns[risk_name] = risk_ret
            exposures[raw_name] = ledger["hold"].notna().astype(float)
            exposures[risk_name] = risk_exp
            ledgers_by_arm[raw_name] = ledger
            rows.append(
                {
                    "arm": raw_name,
                    "mode": mode,
                    "cost_bps": cost_bps,
                    **R1M.perf(ledger["ret"], exposures[raw_name]),
                }
            )
            rows.append(
                {
                    "arm": risk_name,
                    "mode": mode,
                    "cost_bps": cost_bps,
                    **R1M.perf(risk_ret, risk_exp),
                }
            )
    all_returns = pd.DataFrame(returns)
    common_start = all_returns.apply(lambda x: x.first_valid_index()).max()
    common_end = min(
        all_returns.apply(lambda x: x.last_valid_index()).min(),
        pd.Timestamp("2026-09-30"),
    )
    all_returns = all_returns.loc[common_start:common_end]
    all_returns.to_csv(ART / "daily_returns.csv")

    metric_rows = []
    for arm in all_returns:
        metric_rows.append(
            {
                "arm": arm,
                "mode": arm.split("_")[0].lower(),
                "cost_bps": 20.5 if "20.5bp" in arm else 5.0,
                **R1M.perf(all_returns[arm], exposures[arm].reindex(all_returns.index)),
            }
        )
    metrics = pd.DataFrame(metric_rows)
    metrics.to_csv(ART / "metrics_common_window.csv", index=False)

    bootstrap_rows = []
    for cost_bps in (5.0, 20.5):
        control = all_returns[f"B0_C5_TIPDD_{cost_bps:g}bp"]
        for mode in ("H5_SWITCH_CONFIRM", "H6_NEAR_TIE"):
            candidate = all_returns[f"{mode}_TIPDD_{cost_bps:g}bp"]
            test = R1M.circular_block_bootstrap(candidate, control)
            bootstrap_rows.append(
                {
                    "candidate": f"{mode}_TIPDD_{cost_bps:g}bp",
                    "control": f"B0_C5_TIPDD_{cost_bps:g}bp",
                    "cost_bps": cost_bps,
                    **test,
                }
            )
    bootstrap = pd.DataFrame(bootstrap_rows)
    for cost_bps in (5.0, 20.5):
        mask = bootstrap["cost_bps"].eq(cost_bps)
        p = bootstrap.loc[mask, "p_two_sided"].to_numpy(float)
        order = np.argsort(p)
        adjusted = np.empty(len(p))
        running = 1.0
        for rank in range(len(p) - 1, -1, -1):
            pos = order[rank]
            running = min(running, p[pos] * len(p) / (rank + 1))
            adjusted[pos] = running
        bootstrap.loc[mask, "bh_q"] = np.clip(adjusted, 0.0, 1.0)
    bootstrap.to_csv(ART / "bootstrap.csv", index=False)

    segment_rows = []
    for label in ("B0_C5", "H5_SWITCH_CONFIRM", "H6_NEAR_TIE"):
        arm = f"{label}_TIPDD_5bp"
        for segment, start, end in (
            ("2021-02:2022-12", "2021-02-01", "2022-12-31"),
            ("2023-01:2024-12", "2023-01-01", "2024-12-31"),
            ("2025-01:2026-09", "2025-01-01", "2026-09-30"),
            ("full", common_start, common_end),
        ):
            ret = all_returns[arm].loc[start:end]
            segment_rows.append(
                {
                    "arm": arm,
                    "segment": segment,
                    **R1M.perf(ret, exposures[arm].reindex(ret.index)),
                }
            )
    segments = pd.DataFrame(segment_rows)
    segments.to_csv(ART / "segments.csv", index=False)

    event_rows = []
    for mode, label in (("b0", "B0_C5"), ("h5", "H5_SWITCH_CONFIRM"), ("h6", "H6_NEAR_TIE")):
        ledger = ledgers[mode][5.0].loc[common_start:common_end]
        rebalances = ledger[ledger["rebalance"]]
        event_rows.append(
            {
                "arm": label,
                "rebalances": int(len(rebalances)),
                "switches": int(rebalances["turnover"].gt(0).sum()),
                "h5_blocked": int(rebalances["h5_blocked"].sum()),
                "h6_swapped": int(rebalances["h6_swapped"].sum()),
                "missed_gross_compound": compound(rebalances["missed_gross"]),
                "turnover_sum": float(rebalances["turnover"].sum()),
            }
        )
    events = pd.DataFrame(event_rows)
    events.to_csv(ART / "event_summary.csv", index=False)
    ledgers["h5"][5.0].to_csv(ART / "ledger_H5_events.csv")
    ledgers["h6"][5.0].to_csv(ART / "ledger_H6_events.csv")

    rebalance_dates = list(
        ledgers["h5"][5.0].loc[common_start:common_end]
        .query("rebalance")
        .index
    )
    decision_by_execution = (
        ledgers["h5"][5.0].loc[common_start:common_end, "decision"].to_dict()
    )
    frozen_decisions = [
        pd.Timestamp(decision_by_execution[date])
        for date in ledgers["h5"][5.0].loc[common_start:common_end]
        .query("rebalance and h5_blocked")
        .index
    ]
    decision_dates = [pd.Timestamp(decision_by_execution[date]) for date in rebalance_dates]
    decision_positions = {date: idx for idx, date in enumerate(decision_dates)}
    actual_h5 = all_returns["H5_SWITCH_CONFIRM_TIPDD_5bp"]
    actual_h5_sharpe = float(R1M.perf(actual_h5, exposures["H5_SWITCH_CONFIRM_TIPDD_5bp"])["sharpe"])
    placebo_rows = []
    for shift in range(200):
        shifted = {
            decision_dates[
                (decision_positions[pd.Timestamp(date)] + shift) % len(decision_dates)
            ]
            for date in frozen_decisions
        }
        ledger = simulate(
            "h5_placebo",
            0.0005,
            first_execution,
            closes,
            opens,
            c5_signal,
            c5_daily,
            bm5,
            splices,
            shifted,
        )
        risk_ret, risk_exp = AUDIT.apply_tip_dd_lagged(
            ledger["ret"], 0.0005, tip_name="S"
        )
        risk_ret = risk_ret.loc[common_start:common_end]
        risk_exp = risk_exp.reindex(risk_ret.index)
        placebo_rows.append(
            {
                "shift": shift,
                "realized_blocks": int(
                    ledger.loc[common_start:common_end, "h5_blocked"].sum()
                ),
                **R1M.perf(risk_ret, risk_exp),
            }
        )
    placebo = pd.DataFrame(placebo_rows)
    placebo.to_csv(ART / "h5_placebo.csv", index=False)
    placebo_percentile = float(placebo["sharpe"].le(actual_h5_sharpe).mean())

    h6_swapped_decisions = sorted(
        {
            pd.Timestamp(value)
            for value in ledgers["h6"][5.0]
            .loc[common_start:common_end]
            .query("h6_swapped")["decision"]
        }
    )
    h6_leave_one_out = []
    for excluded in h6_swapped_decisions:
        ledger = simulate(
            "h6",
            0.0005,
            first_execution,
            closes,
            opens,
            c5_signal,
            c5_daily,
            bm5,
            splices,
            exclude_h6_decisions={excluded},
        )
        risk_ret, risk_exp = AUDIT.apply_tip_dd_lagged(
            ledger["ret"], 0.0005, tip_name="S"
        )
        risk_ret = risk_ret.loc[common_start:common_end]
        risk_exp = risk_exp.reindex(risk_ret.index)
        h6_leave_one_out.append(
            {
                "excluded_decision": excluded,
                **R1M.perf(risk_ret, risk_exp),
            }
        )
    h6_leave_one_out_frame = pd.DataFrame(h6_leave_one_out)
    h6_leave_one_out_frame.to_csv(ART / "h6_leave_one_out.csv", index=False)

    actual_h6 = all_returns["H6_NEAR_TIE_TIPDD_5bp"]
    actual_h6_sharpe = float(
        R1M.perf(actual_h6, exposures["H6_NEAR_TIE_TIPDD_5bp"])["sharpe"]
    )
    h6_placebo_rows = []
    for seed in range(200):
        ledger = simulate(
            "h6",
            0.0005,
            first_execution,
            closes,
            opens,
            c5_signal,
            c5_daily,
            bm5,
            splices,
            bm5_permute_seed=seed,
        )
        risk_ret, risk_exp = AUDIT.apply_tip_dd_lagged(
            ledger["ret"], 0.0005, tip_name="S"
        )
        risk_ret = risk_ret.loc[common_start:common_end]
        risk_exp = risk_exp.reindex(risk_ret.index)
        h6_placebo_rows.append(
            {
                "seed": seed,
                "h6_swapped": int(
                    ledger.loc[common_start:common_end, "h6_swapped"].sum()
                ),
                **R1M.perf(risk_ret, risk_exp),
            }
        )
    h6_placebo = pd.DataFrame(h6_placebo_rows)
    h6_placebo.to_csv(ART / "h6_bm_permutation.csv", index=False)
    h6_placebo_percentile = float(h6_placebo["sharpe"].le(actual_h6_sharpe).mean())

    contribution_rows = []
    view_returns = pd.DataFrame(
        {
            "B0": all_returns["B0_C5_TIPDD_5bp"],
            "H5": all_returns["H5_SWITCH_CONFIRM_TIPDD_5bp"],
            "H6": all_returns["H6_NEAR_TIE_TIPDD_5bp"],
        }
    )
    b0_holds = ledgers["b0"][5.0]["hold"].reindex(view_returns.index)
    for asset in sorted(b0_holds.dropna().unique()):
        mask = b0_holds.eq(asset)
        contribution_rows.append(
            {
                "held_asset": asset,
                "days": int(mask.sum()),
                **{column: compound(view_returns.loc[mask, column]) for column in view_returns},
            }
        )
    contributions = pd.DataFrame(contribution_rows)
    contributions.to_csv(ART / "asset_contribution.csv", index=False)

    yearly = view_returns.groupby(view_returns.index.year).apply(
        lambda frame: pd.Series({column: compound(frame[column]) for column in frame})
    )
    yearly.to_csv(ART / "yearly_returns.csv")

    figure, axes = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    nav = (1.0 + view_returns).cumprod()
    nav.to_csv(ART / "nav_comparison.csv")
    for column in nav:
        axes[0].plot(nav.index, nav[column], label=column, linewidth=1.5)
        axes[1].plot(
            nav.index,
            nav[column] / nav[column].cummax() - 1.0,
            linewidth=1.0,
        )
    axes[0].set_yscale("log")
    axes[0].set_ylabel("NAV (log)")
    axes[0].legend(frameon=False)
    axes[0].grid(alpha=0.2)
    axes[1].set_ylabel("Drawdown")
    axes[1].grid(alpha=0.2)
    figure.tight_layout()
    figure.savefig(ART / "nav_switch_candidates.png", dpi=180)
    plt.close(figure)

    result = {
        "status": "VIEWED_HISTORY_EXPLORATORY_NOT_OOS",
        "parent_run": str(R1),
        "common_window": [str(common_start.date()), str(common_end.date())],
        "baseline_engine_replay": {
            "days": int(len(baseline_pair)),
            "max_abs_difference": baseline_engine_error,
            "r1_daily_returns_sha256": sha256(R1_RETURNS),
        },
        "metrics": metric_rows,
        "bootstrap": bootstrap.to_dict(orient="records"),
        "segments": segment_rows,
        "event_summary": event_rows,
        "h5_placebo": {
            "draws": int(len(placebo)),
            "actual_frozen_decisions": len(frozen_decisions),
            "actual_sharpe": actual_h5_sharpe,
            "placebo_sharpe_mean": float(placebo["sharpe"].mean()),
            "placebo_sharpe_p05": float(placebo["sharpe"].quantile(0.05)),
            "placebo_sharpe_p95": float(placebo["sharpe"].quantile(0.95)),
            "actual_percentile": placebo_percentile,
            "realized_blocks_range": [
                int(placebo["realized_blocks"].min()),
                int(placebo["realized_blocks"].max()),
            ],
        },
        "h6_audit": {
            "swapped_decisions": [str(value.date()) for value in h6_swapped_decisions],
            "leave_one_out": h6_leave_one_out,
            "bm_permutation": {
                "draws": int(len(h6_placebo)),
                "actual_sharpe": actual_h6_sharpe,
                "placebo_sharpe_mean": float(h6_placebo["sharpe"].mean()),
                "placebo_sharpe_p05": float(h6_placebo["sharpe"].quantile(0.05)),
                "placebo_sharpe_p95": float(h6_placebo["sharpe"].quantile(0.95)),
                "actual_percentile": h6_placebo_percentile,
                "swapped_range": [
                    int(h6_placebo["h6_swapped"].min()),
                    int(h6_placebo["h6_swapped"].max()),
                ],
            },
        },
        "asset_contribution": contribution_rows,
        "yearly_returns": {
            str(year): row.to_dict() for year, row in yearly.iterrows()
        },
        "limitations": [
            "All history was viewed in R1; this is exploratory, not independent OOS.",
            "Six-node futures-to-ETF mapping is a research proxy.",
            "Current-revision public snapshots have no certified historical release vintage.",
            "No candidate is promoted without all preregistered guards.",
        ],
    }
    (ART / "result.json").write_text(
        json.dumps(json_safe(result), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(metrics.to_string(index=False))
    print("\nEVENTS\n", events.to_string(index=False))
    print("\nBOOTSTRAP\n", bootstrap.to_string(index=False))
    print("\nPLACEBO\n", json.dumps(json_safe(result["h5_placebo"]), indent=2))
    print("\nH6 AUDIT\n", json.dumps(json_safe(result["h6_audit"]), indent=2))
    print("\nSEGMENTS\n", segments.to_string(index=False))


if __name__ == "__main__":
    main()
