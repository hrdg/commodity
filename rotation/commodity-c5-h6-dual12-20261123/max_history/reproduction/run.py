"""Extend H6 to the longest history with non-interpolated BM5 availability."""
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
R2 = Path(
    "/Users/hsh/Documents/Quant/科技轮动/research/runs/"
    "aw7_commodity_switch_confirm_20261123"
)
R2_RUNNER = R2 / "reproduction/run.py"
PRODUCT_BM = R1 / "artifacts/product_basis_momentum.csv"
ART = RUN / "artifacts"
NODES = (
    "160723.XSHE",
    "159985.XSHE",
    "159980.XSHE",
    "159981.XSHE",
    "518880.XSHG",
    "161226.XSHE",
)
NODE_GROUPS = {
    "160723.XSHE": ("WTI",),
    "159985.XSHE": ("M",),
    "159980.XSHE": ("CU", "AL", "ZN"),
    "159981.XSHE": ("TA", "MA", "FG"),
    "518880.XSHG": ("AU",),
    "161226.XSHE": ("AG",),
}


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


R2M = load_module("r2_engine", R2_RUNNER)


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


def node_panel_partial(product_bm: pd.DataFrame) -> pd.DataFrame:
    rows = {}
    for node, products in NODE_GROUPS.items():
        pivot = product_bm[product_bm["product"].isin(products)].pivot(
            index="date", columns="product", values="bm5"
        )
        pivot = pivot.reindex(columns=products)
        if len(products) == 1:
            rows[node] = pivot.iloc[:, 0]
        else:
            z = pivot.sub(pivot.mean(axis=1), axis=0).div(
                pivot.std(axis=1, ddof=0).replace(0, np.nan), axis=0
            )
            rows[node] = z.mean(axis=1, skipna=False)
    return pd.DataFrame(rows).reindex(columns=NODES).sort_index()


def perf_daily(ret: pd.Series, exposure: pd.Series) -> dict:
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


def event_count(ledger: pd.DataFrame) -> dict:
    months = ledger.index.month
    reb = ledger[months != pd.Series(months, index=ledger.index).shift(1)]
    return {
        "rebalances": int(len(reb)),
        "swaps": int(reb["turnover"].gt(0).sum()),
        "h6_order_changes": int(reb["h6_swapped"].fillna(False).sum()),
    }


def main() -> None:
    ART.mkdir(parents=True, exist_ok=True)
    parent = R2M.CURRENT
    audit = R2M.AUDIT
    opens, closes, _, splices = parent.build_asset_panel()
    opens, closes = opens.loc[:"2026-11-06"], closes.loc[:"2026-11-06"]
    product_bm = pd.read_csv(PRODUCT_BM, parse_dates=["date"])
    bm5 = node_panel_partial(product_bm)
    bm5.to_csv(ART / "node_bm5_partial.csv")
    c5_daily = parent.B.momentum_scores(closes, 25, 250)
    month_dates = bm5.index.intersection(c5_daily.index)
    month_dates = month_dates[month_dates <= pd.Timestamp("2026-09-30")]
    first_exec = int(
        np.searchsorted(closes.index.values, month_dates.min().to_datetime64(), side="right")
    )
    c5_signal = c5_daily.reindex(month_dates).reindex(columns=NODES)

    full_six_dates = bm5.dropna().index.intersection(c5_daily.index)
    strict_first = int(
        np.searchsorted(
            closes.index.values, full_six_dates.min().to_datetime64(), side="right"
        )
    )

    returns, exposures, ledgers, metrics = {}, {}, {}, []
    for label, mode, start, bm_column in (
        ("B0_MAX", "b0", first_exec, bm5),
        ("H6_MAX", "h6", first_exec, bm5),
        ("B0_STRICT2021", "b0", strict_first, bm5),
        ("H6_STRICT2021", "h6", strict_first, bm5),
    ):
        for cost_bps in (5.0, 20.5):
            ledger = R2M.simulate(
                mode,
                cost_bps / 10000.0,
                start,
                closes,
                opens,
                c5_signal,
                c5_daily,
                bm_column,
                splices,
            )
            risk, exposure = audit.apply_tip_dd_lagged(
                ledger["ret"], cost_bps / 10000.0, tip_name="S"
            )
            risk = risk.loc[:"2026-09-30"]
            exposure = exposure.reindex(risk.index)
            raw_key = f"{label}_NODD_{cost_bps:g}bp"
            risk_key = f"{label}_TIPDD_{cost_bps:g}bp"
            returns[raw_key] = ledger["ret"].loc[: risk.index.max()]
            returns[risk_key] = risk
            exposures[raw_key] = ledger["hold"].notna().astype(float).reindex(
                returns[raw_key].index
            )
            exposures[risk_key] = exposure
            ledgers[raw_key] = ledger
            metrics.append(
                {"arm": raw_key, "cost_bps": cost_bps, **perf_daily(returns[raw_key], exposures[raw_key])}
            )
            metrics.append(
                {"arm": risk_key, "cost_bps": cost_bps, **perf_daily(risk, exposure)}
            )

    r2_returns = pd.read_csv(R2 / "artifacts/daily_returns.csv", index_col=0, parse_dates=True)
    strict_h6 = pd.concat(
        [
            returns["H6_STRICT2021_NODD_5bp"].rename("new"),
            r2_returns["H6_NEAR_TIE_NODD_5bp"].rename("r2"),
        ],
        axis=1,
    ).dropna()
    strict_error = float((strict_h6["new"] - strict_h6["r2"]).abs().max())
    if strict_error > 1e-12:
        raise RuntimeError(f"strict-six H6 replay mismatch: {strict_error}")

    # Month-level difference attribution versus the same-start C5.
    b0 = returns["B0_MAX_TIPDD_5bp"]
    h6 = returns["H6_MAX_TIPDD_5bp"]
    yearly = {}
    for year, block in pd.DataFrame({"B0": b0, "H6": h6}).groupby(
        lambda idx: idx.year
    ):
        yearly[str(year)] = {
            "B0": float((1.0 + block["B0"]).prod() - 1.0),
            "H6": float((1.0 + block["H6"]).prod() - 1.0),
            "delta": float((1.0 + block["H6"]).prod() - (1.0 + block["B0"]).prod()),
        }

    # Permute only available BM5 labels within each month.
    rng_seed = 20261123
    permutations = []
    for draw in range(200):
        changed = bm5.copy()
        rng = np.random.default_rng(rng_seed + draw)
        for date, row in changed.iterrows():
            available = row.dropna()
            if len(available) > 1:
                changed.loc[date, available.index] = rng.permutation(available.to_numpy())
        ledger = R2M.simulate(
            "h6",
            0.0005,
            first_exec,
            closes,
            opens,
            c5_signal,
            c5_daily,
            changed,
            splices,
        )
        risk, exposure = audit.apply_tip_dd_lagged(ledger["ret"], 0.0005, tip_name="S")
        risk = risk.loc[:"2026-09-30"]
        exposure = exposure.reindex(risk.index)
        permutations.append({"draw": draw, **perf_daily(risk, exposure)})
    perm = pd.DataFrame(permutations)
    perm.to_csv(ART / "h6_bm_permutation.csv", index=False)
    actual_h6 = float(
        pd.DataFrame(metrics).set_index("arm").loc["H6_MAX_TIPDD_5bp", "sharpe"]
    )
    permutation_percentile = float(perm["sharpe"].le(actual_h6).mean())

    metrics_frame = pd.DataFrame(metrics)
    metrics_frame.to_csv(ART / "metrics.csv", index=False)
    pd.DataFrame(returns).to_csv(ART / "daily_returns.csv")
    pd.DataFrame(yearly).T.to_csv(ART / "yearly.csv")
    for arm in ("B0_MAX_NODD_5bp", "H6_MAX_NODD_5bp"):
        ledgers[arm].to_csv(ART / f"ledger_{arm}.csv")
    event_rows = ledgers["H6_MAX_NODD_5bp"].loc[
        ledgers["H6_MAX_NODD_5bp"]["h6_swapped"].fillna(False)
    ]
    event_rows.to_csv(ART / "h6_events.csv")

    figure, axes = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    nav = (1.0 + pd.DataFrame({"B0": b0, "H6": h6})).cumprod()
    axes[0].plot(nav.index, nav["B0"], label="B0 C5", linewidth=1.4)
    axes[0].plot(nav.index, nav["H6"], label="H6 max", linewidth=1.4)
    axes[0].set_yscale("log")
    axes[0].legend(frameon=False)
    axes[0].grid(alpha=0.2)
    axes[1].plot(nav.index, nav["B0"] / nav["B0"].cummax() - 1, label="B0", linewidth=1.2)
    axes[1].plot(nav.index, nav["H6"] / nav["H6"].cummax() - 1, label="H6", linewidth=1.2)
    axes[1].legend(frameon=False)
    axes[1].grid(alpha=0.2)
    figure.tight_layout()
    figure.savefig(ART / "nav_maxhistory.png", dpi=180)
    plt.close(figure)

    result = {
        "status": "MAXHISTORY_VIEWED_HISTORY_NOT_OOS",
        "window": {
            "start": str(month_dates.min().date()),
            "end": str(month_dates.max().date()),
            "complete_six_start": str(full_six_dates.min().date()),
        },
        "strict_six_replay_max_abs_error": strict_error,
        "events_max": event_count(ledgers["H6_MAX_NODD_5bp"]),
        "event_rows": [
            {
                "execution": str(index.date()),
                "target": row["hold"],
                "turnover": float(row["turnover"]),
                "gross": float(row["gross"]),
            }
            for index, row in event_rows.iterrows()
        ],
        "metrics": metrics,
        "yearly_returns": yearly,
        "permutation": {
            "draws": int(len(perm)),
            "actual_sharpe": actual_h6,
            "mean": float(perm["sharpe"].mean()),
            "p05": float(perm["sharpe"].quantile(0.05)),
            "p95": float(perm["sharpe"].quantile(0.95)),
            "percentile": permutation_percentile,
        },
        "limitations": [
            "Pre-listing ETF return history is proxy-inclusive.",
            "BM5 nodes enter only when their mapped contract groups are available.",
            "All history is viewed; this is not independent OOS.",
            "The long-history extension still has no certified vendor vintage.",
        ],
    }
    (ART / "result.json").write_text(
        json.dumps(json_safe(result), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(json_safe(result), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
