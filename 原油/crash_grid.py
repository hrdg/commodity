"""Grid of post-shock cooldowns: threshold x flat days (1-10).

A usable rule should show a plateau, not a single lucky cell.  Positions are
decided at the China open; the overnight gap is always borne by the prior
position, only open-to-close exposure can be cut.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import strategy

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
FEE = 0.0003
THRESHOLDS = [-0.04, -0.05, -0.06, -0.07, -0.08]
DAYS = list(range(1, 11))


def main() -> None:
    px = pd.read_csv(DATA / "160723.csv", parse_dates=["date"]).set_index("date")
    px = px.sort_index().loc["2017-05-05":]
    uso = pd.read_csv(DATA / "uso.csv", parse_dates=["date"]).set_index("date")["close"].sort_index()
    idx = px.index

    pos = np.searchsorted(uso.index.values, idx.values - np.timedelta64(1, "D"), side="right") - 1
    pre = np.searchsorted(uso.index.values, idx.values[:-1] - np.timedelta64(1, "D"), side="right") - 1
    ov = pd.Series(uso.values[pos] / np.r_[np.nan, uso.values[pre]] - 1, index=idx)

    out, _ = strategy.run(json.loads((ROOT / "config.json").read_text()))
    out = out.set_index("date")
    base = out.target_position.shift(1).fillna(0.0)
    gap = px.open / px.close.shift(1) - 1
    intra = px.close / px.open - 1

    def run(p: pd.Series) -> dict:
        p = p.clip(0, 1).fillna(0.0)
        pnl = (p.shift(1).fillna(0.0) * gap + p * intra
               - FEE * (p - p.shift(1)).abs().fillna(p.abs()))
        keep = ("cagr", "sharpe", "calmar", "mdd")
        full = strategy.metrics(pnl, p)
        train = strategy.metrics(pnl.loc[:"2021-12-31"], p.loc[:"2021-12-31"])
        oos = strategy.metrics(pnl.loc["2022-01-01":], p.loc["2022-01-01":])
        return {f: {k: float(x[k]) for k in keep} for f, x in (("full", full), ("train", train), ("oos", oos))}

    rows = [{"threshold": 0.0, "days": 0, **run(base)}]
    for th in THRESHOLDS:
        flag = (ov <= th).astype(float)
        for n in DAYS:
            block = flag.rolling(n, min_periods=1).max().fillna(0.0)
            rows.append({"threshold": th, "days": n, **run(base.where(block < 0.5, 0.0))})

    recs = []
    for r in rows:
        recs.append({"threshold": r["threshold"], "days": r["days"],
                     **{f"{f}_{k}": r[f][k] for f in ("full", "train", "oos") for k in ("cagr", "sharpe", "calmar", "mdd")}})
    df = pd.DataFrame(recs)
    df.to_csv(ROOT / "output_overnight" / "crash_grid.csv", index=False)

    def heat(field: str, ax, title: str) -> None:
        m = np.full((len(THRESHOLDS), len(DAYS)), np.nan)
        for i, th in enumerate(THRESHOLDS):
            for j, n in enumerate(DAYS):
                v = df[(df.threshold == th) & (df.days == n)][field]
                if len(v):
                    m[i, j] = v.iloc[0]
        im = ax.imshow(m, cmap="RdYlGn", aspect="auto")
        ax.set_xticks(range(len(DAYS)), DAYS)
        ax.set_yticks(range(len(THRESHOLDS)), [f"{t:.0%}" for t in THRESHOLDS])
        ax.set_xlabel("flat days (including shock day)")
        ax.set_ylabel("overnight USO threshold")
        ax.set_title(title, fontsize=10)
        for i in range(len(THRESHOLDS)):
            for j in range(len(DAYS)):
                if np.isfinite(m[i, j]):
                    ax.text(j, i, f"{m[i, j]:.2f}", ha="center", va="center", fontsize=7)
        plt.colorbar(im, ax=ax, fraction=0.046)

    fig, ax = plt.subplots(1, 3, figsize=(14, 4.4))
    heat("full_calmar", ax[0], "Full 2017-2026 Calmar")
    heat("oos_calmar", ax[1], "OOS 2022-2026 Calmar")
    heat("full_cagr", ax[2], "Full 2017-2026 CAGR")
    fig.tight_layout()
    fig.savefig(ROOT / "output_overnight" / "crash_grid.png", dpi=150)
    plt.close(fig)

    print(df[df.threshold == 0].to_string(index=False))
    print(df[df.threshold == -0.07][["days", "full_cagr", "full_sharpe", "full_calmar", "oos_cagr", "oos_calmar"]].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
