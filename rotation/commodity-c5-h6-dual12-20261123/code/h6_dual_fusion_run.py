"""Fuse H6 near-tie ranking with dual-momentum filtering in two layers."""
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
H6RUN = Path(
    "/Users/hsh/Documents/Quant/科技轮动/research/runs/"
    "aw7_commodity_switch_confirm_20261123"
)
DUALRUN = Path(
    "/Users/hsh/Documents/Quant/科技轮动/research/runs/"
    "aw7_commodity_dual_filter_20261123"
)
H6_RUNNER = H6RUN / "reproduction/run.py"
H6_DAILY = H6RUN / "artifacts/daily_returns.csv"
DUAL_RETURNS = DUALRUN / "artifacts/returns.csv"
ART = RUN / "artifacts"
NODES = (
    "160723.XSHE",
    "159985.XSHE",
    "159980.XSHE",
    "159981.XSHE",
    "518880.XSHG",
    "161226.XSHE",
)
REL_CUT = 0.50


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


M = load_module("h6_runner", H6_RUNNER)


def hash_file(path: Path) -> str:
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


def monthly_eligibility(
    closes: pd.DataFrame,
    month_dates: pd.DatetimeIndex,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    monthly = closes.reindex(month_dates).reindex(columns=NODES)
    mom12 = monthly.pct_change(12, fill_method=None)
    rank = mom12.rank(axis=1, pct=True, method="average")
    absolute = mom12.gt(0)
    dual = absolute & rank.ge(REL_CUT)
    return absolute, dual


def simulate_filtered(
    mode: str,
    eligible: pd.DataFrame,
    cost: float,
    first_execution: int,
    closes: pd.DataFrame,
    opens: pd.DataFrame,
    c5_signal: pd.DataFrame,
    c5_daily: pd.DataFrame,
    bm5: pd.DataFrame,
    splices: pd.DataFrame,
):
    """Run the R2 state machine after filtering the eligible C5 ensemble."""
    z_r2 = M.CURRENT.B.zscore(c5_daily)
    eff = M.CURRENT.B.efficiency(closes)
    beta = M.CURRENT.B.beta252(closes)
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
        target = hold
        take_profit = False
        veto = False
        swapped = False
        if rebalance:
            if decision not in c5_signal.index or decision not in eligible.index:
                target = None
            else:
                raw_score = c5_signal.loc[decision].dropna()
                allowed = eligible.loc[decision].reindex(raw_score.index).fillna(False)
                score = raw_score[allowed]
                if len(score) < 2:
                    target = None
                else:
                    if mode == "h6" and decision in bm5.index:
                        score, detail = M.apply_h6_near_tie(
                            score, z_r2.loc[decision], bm5.loc[decision]
                        )
                        swapped = detail is not None
                    target, unlock, take_profit, veto = M.CURRENT.B.choose(
                        score,
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
        turnover = 0.0 if target == hold else (1.0 if target is None or hold is None else 2.0)
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
                "ret": net,
                "gross": gross,
                "turnover": turnover,
                "splice_fee": splice_fee,
                "hold": target,
                "take_profit": take_profit,
                "veto": veto,
                "h6_swapped": swapped,
            }
        )
        hold = target
    return pd.DataFrame(rows).set_index("date")


def monthly_return(series: pd.Series) -> pd.Series:
    return (1.0 + series.fillna(0.0)).groupby(series.index.to_period("M")).prod() - 1.0


def daily_metrics(ret: pd.Series, exposure: pd.Series) -> dict:
    values = ret.dropna()
    nav = (1.0 + values).cumprod()
    years = len(values) / 252.0
    cagr = float(nav.iloc[-1] ** (1.0 / years) - 1.0)
    mdd = float((nav / nav.cummax() - 1.0).min())
    std = float(values.std(ddof=1))
    return {
        "start": str(values.index.min().date()),
        "end": str(values.index.max().date()),
        "days": int(len(values)),
        "cagr": cagr,
        "vol": float(std * math.sqrt(252.0)),
        "sharpe": float(values.mean() / std * math.sqrt(252.0)) if std > 0 else np.nan,
        "mdd": mdd,
        "calmar": cagr / abs(mdd) if mdd < 0 else np.nan,
        "average_exposure": float(exposure.reindex(values.index).mean()),
    }


def monthly_metrics(ret: pd.Series) -> dict:
    values = ret.dropna()
    nav = (1.0 + values).cumprod()
    years = len(values) / 12.0
    cagr = float(nav.iloc[-1] ** (1.0 / years) - 1.0)
    mdd = float((nav / nav.cummax() - 1.0).min())
    return {
        "start": str(values.index.min()),
        "end": str(values.index.max()),
        "months": int(len(values)),
        "cagr": cagr,
        "vol": float(values.std(ddof=1) * math.sqrt(12.0)),
        "sharpe": float(values.mean() / values.std(ddof=1) * math.sqrt(12.0)),
        "mdd": mdd,
        "calmar": cagr / abs(mdd) if mdd < 0 else np.nan,
    }


def block_sharpe_diff(
    candidate: pd.Series,
    control: pd.Series,
    *,
    block: int,
    annualization: float,
    draws: int = 10000,
    seed: int = 20261123,
) -> dict:
    frame = pd.concat(
        [candidate.rename("candidate"), control.rename("control")], axis=1
    ).dropna()
    values = frame.to_numpy(float)
    n = len(values)
    rng = np.random.default_rng(seed)
    starts = rng.integers(0, n, size=(draws, int(np.ceil(n / block))))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]) % n
    sampled = values[idx.reshape(draws, -1)[:, :n]]
    cand_sr = (
        sampled[:, :, 0].mean(axis=1)
        / sampled[:, :, 0].std(axis=1, ddof=1)
        * np.sqrt(annualization)
    )
    ctrl_sr = (
        sampled[:, :, 1].mean(axis=1)
        / sampled[:, :, 1].std(axis=1, ddof=1)
        * np.sqrt(annualization)
    )
    difference = cand_sr - ctrl_sr
    point = float(
        (
            frame["candidate"].mean() / frame["candidate"].std(ddof=1)
            - frame["control"].mean() / frame["control"].std(ddof=1)
        )
        * np.sqrt(annualization)
    )
    return {
        "sharpe_difference": point,
        "ci95": [
            float(np.quantile(difference, 0.025)),
            float(np.quantile(difference, 0.975)),
        ],
        "p_two_sided": float(
            2.0
            * min(
                float((difference <= 0).mean()),
                float((difference >= 0).mean()),
            )
        ),
    }


def main() -> None:
    ART.mkdir(parents=True, exist_ok=True)
    opens, closes, splices, bm5, c5_daily = M.load_inputs()
    month_dates = bm5.dropna().index.intersection(c5_daily.index)
    c5_signal = c5_daily.reindex(month_dates).reindex(columns=NODES)
    first_execution = int(
        np.searchsorted(closes.index.values, month_dates.min().to_datetime64(), side="right")
    )
    absolute, dual = monthly_eligibility(closes, month_dates)

    f1_returns, f1_exposure, f1_ledgers, f1_rows = {}, {}, {}, []
    for cost_bps in (5.0, 20.5):
        for label, mode, eligibility in (
            ("B0_C5", "b0", None),
            ("H6", "h6", None),
            ("ABS12_C5", "c5", absolute),
            ("ABS12_H6", "h6", absolute),
            ("DUAL12_C5", "c5", dual),
            ("DUAL12_H6", "h6", dual),
        ):
            if eligibility is None:
                ledger = M.simulate(
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
            else:
                ledger = simulate_filtered(
                    mode,
                    eligibility,
                    cost_bps / 10000.0,
                    first_execution,
                    closes,
                    opens,
                    c5_signal,
                    c5_daily,
                    bm5,
                    splices,
                )
            risk, exposure = M.AUDIT.apply_tip_dd_lagged(
                ledger["ret"], cost_bps / 10000.0, tip_name="S"
            )
            risk = risk.loc[:"2026-09-30"]
            exposure = exposure.reindex(risk.index)
            key = f"{label}_{cost_bps:g}bp"
            f1_returns[key] = risk
            f1_exposure[key] = exposure
            f1_ledgers[key] = ledger
            f1_rows.append(
                {
                    "arm": label,
                    "cost_bps": cost_bps,
                    "average_exposure": float(exposure.mean()),
                    "zero_risk_months": int(
                        exposure.loc[
                            (exposure.index.month != exposure.index.to_series().shift(1).dt.month)
                        ].le(1e-12).sum()
                    ),
                    **daily_metrics(risk, exposure),
                }
            )
    f1 = pd.DataFrame(f1_rows)
    f1.to_csv(ART / "metrics_f1.csv", index=False)
    pd.DataFrame(f1_returns).to_csv(ART / "returns_f1_daily.csv")

    eligible_events = []
    for date in month_dates:
        eligible_events.append(
            {
                "date": date,
                "abs12_count": int(absolute.loc[date].sum()),
                "dual12_count": int(dual.loc[date].sum()),
            }
        )
    eligible_frame = pd.DataFrame(eligible_events)
    eligible_frame.to_csv(ART / "eligibility.csv", index=False)

    f1_bootstrap = []
    for cost_bps in (5.0, 20.5):
        for candidate, control in (
            ("DUAL12_H6", "H6"),
            ("DUAL12_H6", "DUAL12_C5"),
            ("DUAL12_C5", "B0_C5"),
        ):
            f1_bootstrap.append(
                {
                    "candidate": f"{candidate}_{cost_bps:g}bp",
                    "control": f"{control}_{cost_bps:g}bp",
                    "cost_bps": cost_bps,
                    **block_sharpe_diff(
                        f1_returns[f"{candidate}_{cost_bps:g}bp"],
                        f1_returns[f"{control}_{cost_bps:g}bp"],
                        block=21,
                        annualization=252.0,
                    ),
                }
            )
    f1_bootstrap_frame = pd.DataFrame(f1_bootstrap)
    f1_bootstrap_frame.to_csv(ART / "bootstrap_f1.csv", index=False)

    h6_daily = pd.read_csv(H6_DAILY, index_col=0, parse_dates=True)
    dual_raw = pd.read_csv(DUAL_RETURNS, index_col=0, parse_dates=True)
    f2_rows = []
    f2_returns = {}
    f2_details = {}
    for cost_bps in (5.0, 20.5):
        h6_month = monthly_return(h6_daily[f"H6_NEAR_TIE_TIPDD_{cost_bps:g}bp"])
        dual_signal = dual_raw[f"BM5_DUAL12_lag1_{cost_bps:g}bp"].dropna()
        dual_month = pd.Series(
            dual_signal.values,
            index=(dual_signal.index.to_period("M") + 1).to_timestamp(how="end").normalize(),
        )
        h6_month.index = h6_month.index.to_timestamp(how="end").normalize()
        common = h6_month.index.intersection(dual_month.index)
        h6_common = h6_month.reindex(common)
        dual_common = dual_month.reindex(common)
        raw_blend = 0.5 * h6_common + 0.5 * dual_common
        h6_end_weight = 0.5 * (1.0 + h6_common) / (1.0 + raw_blend)
        blend_turnover = 2.0 * (h6_end_weight - 0.5).abs()
        blend = raw_blend - cost_bps / 10000.0 * blend_turnover
        f2_returns[f"H6_{cost_bps:g}bp"] = h6_common
        f2_returns[f"BM5_DUAL12_{cost_bps:g}bp"] = dual_common
        f2_returns[f"FUSION50_{cost_bps:g}bp"] = blend
        corr = float(h6_common.corr(dual_common))
        f2_details[str(cost_bps)] = {
            "correlation": corr,
            "common_start": str(common.min().date()),
            "common_end": str(common.max().date()),
            "common_months": int(len(common)),
        }
        for label, values in (
            ("H6", h6_common),
            ("BM5_DUAL12", dual_common),
            ("FUSION50", blend),
        ):
            f2_rows.append(
                {
                    "arm": label,
                    "cost_bps": cost_bps,
                    "correlation_H6_BM5DUAL": corr,
                    **monthly_metrics(values),
                }
            )
    f2 = pd.DataFrame(f2_rows)
    f2.to_csv(ART / "metrics_f2.csv", index=False)
    pd.DataFrame(f2_returns).to_csv(ART / "returns_f2_monthly.csv")

    f2_bootstrap = []
    for cost_bps in (5.0, 20.5):
        for control in ("H6", "BM5_DUAL12"):
            f2_bootstrap.append(
                {
                    "candidate": f"FUSION50_{cost_bps:g}bp",
                    "control": f"{control}_{cost_bps:g}bp",
                    "cost_bps": cost_bps,
                    **block_sharpe_diff(
                        f2_returns[f"FUSION50_{cost_bps:g}bp"],
                        f2_returns[f"{control}_{cost_bps:g}bp"],
                        block=6,
                        annualization=12.0,
                    ),
                }
            )
    f2_bootstrap_frame = pd.DataFrame(f2_bootstrap)
    for cost_bps in (5.0, 20.5):
        mask = f2_bootstrap_frame["cost_bps"].eq(cost_bps)
        p = f2_bootstrap_frame.loc[mask, "p_two_sided"].to_numpy(float)
        order = np.argsort(p)
        q = np.ones(len(p))
        running = 1.0
        for rank in range(len(p) - 1, -1, -1):
            pos = order[rank]
            running = min(running, p[pos] * len(p) / (rank + 1))
            q[pos] = running
        f2_bootstrap_frame.loc[mask, "bh_q"] = q
    f2_bootstrap_frame.to_csv(ART / "bootstrap_f2.csv", index=False)

    figure, axes = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    nav1 = (1.0 + pd.DataFrame(
        {
            "B0": f1_returns["B0_C5_5bp"],
            "H6": f1_returns["H6_5bp"],
            "DUAL12 C5": f1_returns["DUAL12_C5_5bp"],
            "DUAL12 H6": f1_returns["DUAL12_H6_5bp"],
        }
    )).cumprod()
    for column in nav1:
        axes[0].plot(nav1.index, nav1[column], label=column, linewidth=1.4)
    axes[0].set_yscale("log")
    axes[0].legend(frameon=False)
    axes[0].grid(alpha=0.2)
    axes[0].set_ylabel("F1 NAV (log)")
    nav2 = (1.0 + pd.DataFrame(
        {
            "H6": f2_returns["H6_5bp"],
            "BM5 dual12": f2_returns["BM5_DUAL12_5bp"],
            "50/50": f2_returns["FUSION50_5bp"],
        }
    )).cumprod()
    for column in nav2:
        axes[1].plot(nav2.index, nav2[column], label=column, linewidth=1.4)
    axes[1].set_yscale("log")
    axes[1].legend(frameon=False)
    axes[1].grid(alpha=0.2)
    axes[1].set_ylabel("F2 NAV (log)")
    figure.tight_layout()
    figure.savefig(ART / "nav_fusion.png", dpi=180)
    plt.close(figure)

    result = {
        "status": "VIEWED_HISTORY_EXPLORATORY_NOT_OOS",
        "F1": {
            "metrics": f1_rows,
            "bootstrap": f1_bootstrap_frame.to_dict(orient="records"),
            "eligible_summary": {
                "months": int(len(eligible_frame)),
                "dual_median": float(eligible_frame["dual12_count"].median()),
                "dual_min": int(eligible_frame["dual12_count"].min()),
                "dual_max": int(eligible_frame["dual12_count"].max()),
            },
        },
        "F2": {
            "metrics": f2_rows,
            "bootstrap": f2_bootstrap_frame.to_dict(orient="records"),
            "details": f2_details,
        },
        "limitations": [
            "F1 is a six-ETF proxy strategy with next-open execution.",
            "F2 mixes an ETF sleeve and a contract-level futures proxy and is not a single live carrier.",
            "All historical observations were previously viewed; no independent OOS.",
        ],
    }
    (ART / "result.json").write_text(
        json.dumps(json_safe(result), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(json_safe(result), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
