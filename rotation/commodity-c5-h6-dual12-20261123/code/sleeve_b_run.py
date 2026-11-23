"""Compare same-carrier and cross-carrier Sleeve B choices for H6."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


RUN = Path(__file__).resolve().parents[1]
PARENT = Path(
    "/Users/hsh/Documents/Quant/科技轮动/research/runs/"
    "aw7_commodity_h6_dual_fusion_20261123"
)
F1_DAILY = PARENT / "artifacts/returns_f1_daily.csv"
F2_MONTHLY = PARENT / "artifacts/returns_f2_monthly.csv"
ART = RUN / "artifacts"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def monthly_compound(series: pd.Series) -> pd.Series:
    values = (1.0 + series.fillna(0.0)).groupby(series.index.to_period("M")).prod() - 1.0
    values.index = values.index.to_timestamp(how="end").normalize()
    return values


def blend_two(first: pd.Series, second: pd.Series, cost: float) -> pd.Series:
    common = first.index.intersection(second.index)
    a, b = first.reindex(common), second.reindex(common)
    raw = 0.5 * a + 0.5 * b
    post_a = 0.5 * (1.0 + a) / (1.0 + raw)
    turnover = 2.0 * (post_a - 0.5).abs()
    return raw - cost * turnover


def metric(values: pd.Series) -> dict:
    values = values.dropna()
    nav = (1.0 + values).cumprod()
    years = len(values) / 12.0
    cagr = float(nav.iloc[-1] ** (1.0 / years) - 1.0)
    mdd = float((nav / nav.cummax() - 1.0).min())
    std = float(values.std(ddof=1))
    return {
        "start": str(values.index.min().date()),
        "end": str(values.index.max().date()),
        "months": int(len(values)),
        "cagr": cagr,
        "vol": float(std * math.sqrt(12.0)),
        "sharpe": float(values.mean() / std * math.sqrt(12.0)),
        "mdd": mdd,
        "calmar": cagr / abs(mdd) if mdd < 0 else np.nan,
    }


def block_sharpe_diff(
    candidate: pd.Series,
    control: pd.Series,
    *,
    block: int = 6,
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
    c = (
        sampled[:, :, 0].mean(axis=1)
        / sampled[:, :, 0].std(axis=1, ddof=1)
        * np.sqrt(12.0)
    )
    k = (
        sampled[:, :, 1].mean(axis=1)
        / sampled[:, :, 1].std(axis=1, ddof=1)
        * np.sqrt(12.0)
    )
    diff = c - k
    point = float(
        (
            frame["candidate"].mean() / frame["candidate"].std(ddof=1)
            - frame["control"].mean() / frame["control"].std(ddof=1)
        )
        * np.sqrt(12.0)
    )
    return {
        "sharpe_difference": point,
        "ci95": [
            float(np.quantile(diff, 0.025)),
            float(np.quantile(diff, 0.975)),
        ],
        "p_two_sided": float(
            2.0
            * min(float((diff <= 0).mean()), float((diff >= 0).mean()))
        ),
    }


def main() -> None:
    ART.mkdir(parents=True, exist_ok=True)
    daily = pd.read_csv(F1_DAILY, index_col=0, parse_dates=True)
    monthly_ref = pd.read_csv(F2_MONTHLY, index_col=0, parse_dates=True)
    metrics_rows, series_map, correlation_rows = [], {}, []
    for cost_bps in (5.0, 20.5):
        h6 = monthly_compound(daily[f"H6_{cost_bps:g}bp"])
        c5 = monthly_compound(daily[f"DUAL12_C5_{cost_bps:g}bp"])
        h6f = monthly_compound(daily[f"DUAL12_H6_{cost_bps:g}bp"])
        broad = monthly_ref[f"BM5_DUAL12_{cost_bps:g}bp"]
        common = h6.index.intersection(c5.index).intersection(h6f.index).intersection(broad.index)
        h6, c5, h6f, broad = (
            h6.reindex(common),
            c5.reindex(common),
            h6f.reindex(common),
            broad.reindex(common),
        )
        blends = {
            "H6": h6,
            "DUAL12_C5": c5,
            "DUAL12_H6": h6f,
            "H6_PLUS_DUAL12_C5": blend_two(h6, c5, cost_bps / 10000.0),
            "H6_PLUS_DUAL12_H6": blend_two(h6, h6f, cost_bps / 10000.0),
            "H6_PLUS_BM5_DUAL12": blend_two(h6, broad, cost_bps / 10000.0),
        }
        for label, values in blends.items():
            key = f"{label}_{cost_bps:g}bp"
            series_map[key] = values
            metrics_rows.append({"arm": label, "cost_bps": cost_bps, **metric(values)})
        for other in ("DUAL12_C5", "DUAL12_H6", "BM5_DUAL12"):
            other_values = {"DUAL12_C5": c5, "DUAL12_H6": h6f, "BM5_DUAL12": broad}[other]
            correlation_rows.append(
                {
                    "cost_bps": cost_bps,
                    "left": "H6",
                    "right": other,
                    "correlation": float(h6.corr(other_values)),
                }
            )
    pd.DataFrame(metrics_rows).to_csv(ART / "metrics.csv", index=False)
    pd.DataFrame(correlation_rows).to_csv(ART / "correlations.csv", index=False)
    pd.DataFrame(series_map).to_csv(ART / "returns_monthly.csv")

    comparisons = []
    for cost_bps in (5.0, 20.5):
        for candidate, control in (
            ("H6_PLUS_DUAL12_C5", "H6"),
            ("H6_PLUS_DUAL12_H6", "H6"),
            ("H6_PLUS_DUAL12_H6", "H6_PLUS_DUAL12_C5"),
            ("H6_PLUS_DUAL12_C5", "H6_PLUS_BM5_DUAL12"),
            ("H6_PLUS_DUAL12_H6", "H6_PLUS_BM5_DUAL12"),
        ):
            comparisons.append(
                {
                    "candidate": f"{candidate}_{cost_bps:g}bp",
                    "control": f"{control}_{cost_bps:g}bp",
                    "cost_bps": cost_bps,
                    **block_sharpe_diff(
                        series_map[f"{candidate}_{cost_bps:g}bp"],
                        series_map[f"{control}_{cost_bps:g}bp"],
                    ),
                }
            )
    comparison = pd.DataFrame(comparisons)
    for cost_bps in (5.0, 20.5):
        mask = comparison["cost_bps"].eq(cost_bps)
        p = comparison.loc[mask, "p_two_sided"].to_numpy(float)
        order = np.argsort(p)
        q = np.ones(len(p))
        running = 1.0
        for rank in range(len(p) - 1, -1, -1):
            pos = order[rank]
            running = min(running, p[pos] * len(p) / (rank + 1))
            q[pos] = running
        comparison.loc[mask, "bh_q"] = q
    comparison.to_csv(ART / "bootstrap.csv", index=False)

    nav = (1.0 + pd.DataFrame(series_map)).cumprod()
    fig, ax = plt.subplots(figsize=(12, 6))
    for column in (
        "H6_5bp",
        "DUAL12_C5_5bp",
        "DUAL12_H6_5bp",
        "H6_PLUS_DUAL12_C5_5bp",
        "H6_PLUS_DUAL12_H6_5bp",
        "H6_PLUS_BM5_DUAL12_5bp",
    ):
        ax.plot(nav.index, nav[column], label=column, linewidth=1.4)
    ax.set_yscale("log")
    ax.set_ylabel("NAV (monthly, log)")
    ax.legend(frameon=False, ncol=2)
    ax.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(ART / "nav_sleeveb.png", dpi=180)
    plt.close(fig)

    result = {
        "status": "VIEWED_HISTORY_EXPLORATORY_NOT_OOS",
        "metrics": metrics_rows,
        "correlations": correlation_rows,
        "bootstrap": comparison.to_dict(orient="records"),
        "limitations": [
            "All arms use viewed history.",
            "Same-carrier variants remain ETF proxies.",
            "Broad BM5+dual12 is a separate futures proxy.",
        ],
    }
    (ART / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
