"""Overnight US crude shocks and 160723 open-to-close risk.

The LOF trades in China while WTI/USO move overnight.  A shock that is only
observed at the China open cannot be avoided by selling at that open, so this
script separates the gap (unavoidable) from the intraday move (avoidable) and
tests whether a crash filter or a pre-emptive trend/vol rule adds value.
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


def load() -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    px = pd.read_csv(DATA / "160723.csv", parse_dates=["date"]).set_index("date")
    px = px.sort_index().loc["2017-05-05":]
    uso = pd.read_csv(DATA / "uso.csv", parse_dates=["date"]).set_index("date")["close"].sort_index()
    nav = pd.read_csv(DATA / "nav_160723.csv", parse_dates=["date"]).set_index("date")["nav"].sort_index()
    return px, uso, nav


def overnight(uso: pd.Series, idx: pd.DatetimeIndex) -> pd.Series:
    """USO return of the sessions between the previous and current China close."""
    us_now = np.searchsorted(uso.index.values, idx.values - np.timedelta64(1, "D"), side="right") - 1
    prev = idx.values[:-1]
    us_prev_pos = np.searchsorted(uso.index.values, prev - np.timedelta64(1, "D"), side="right") - 1
    us_prev = np.r_[np.nan, uso.values[us_prev_pos]]
    return pd.Series(uso.values[us_now] / us_prev - 1, index=idx, name="us_ov")


def main() -> None:
    px, uso, nav = load()
    idx = px.index
    out, _ = strategy.run(json.loads((ROOT / "config.json").read_text()))
    out = out.set_index("date")
    base = out.target_position.shift(1).fillna(0.0)

    asof = idx - pd.Timedelta(days=1)
    uso_kn = uso.reindex(asof, method="ffill")
    uso_kn.index = idx
    ov = overnight(uso, idx)
    gap = px.open / px.close.shift(1) - 1
    intra = px.close / px.open - 1
    day = px.close / px.close.shift(1) - 1
    fwd5 = px.close.shift(-5) / px.close - 1

    d0 = pd.Series(nav.index, index=nav.index).reindex(idx, method="ffill").shift(3)
    nav0 = nav.reindex(idx, method="ffill").shift(3)
    us0 = uso.reindex(pd.DatetimeIndex(d0), method="ffill")
    us0.index = idx
    prem_open = px.close / (nav0 * uso_kn / us0) - 1

    buckets = [(-1.0, -0.07), (-0.07, -0.05), (-0.05, -0.03),
               (-0.03, 0.0), (0.0, 0.03), (0.03, 1.0)]
    rows = []
    for lo, hi in buckets:
        sel = (ov > lo) & (ov <= hi)
        rows.append({
            "bucket": f"{lo:.0%}..{hi:.0%}",
            "n": int(sel.sum()),
            "gap": float(gap[sel].mean()),
            "intraday": float(intra[sel].mean()),
            "day": float(day[sel].mean()),
            "fwd5": float(fwd5[sel].mean()),
            "intra_neg_share": float((intra[sel] < 0).mean()),
        })

    def bt(pos: pd.Series) -> dict:
        pos = pos.clip(0, 1).fillna(0.0)
        pnl = (pos.shift(1).fillna(0.0) * gap + pos * intra
               - FEE * (pos - pos.shift(1)).abs().fillna(pos.abs()))
        f = strategy.metrics(pnl, pos)
        o = strategy.metrics(pnl.loc["2022-01-01":], pos.loc["2022-01-01":])
        keep = ("cagr", "sharpe", "calmar", "mdd")
        return {"full": {k: float(f[k]) for k in keep},
                "oos": {k: float(o[k]) for k in keep},
                "exposure": float(pos.mean()),
                "worst5_sum": float(pnl.nsmallest(5).sum())}

    mom20 = uso_kn / uso_kn.shift(20) - 1
    vol20 = uso_kn.pct_change().rolling(20).std()
    vol_cap = vol20.expanding(min_periods=250).quantile(0.8)

    tests = {"base": bt(base)}
    for th in (-0.04, -0.05, -0.06):
        tests[f"crash_exit_{int(-th*100)}pct"] = bt(base.where(ov > th, 0.0))
    tests["trend20_half"] = bt(base.where(~(mom20 <= 0), base * 0.5))
    tests["trend20_flat"] = bt(base.where(~(mom20 <= 0), 0.0))
    tests["vol80_half"] = bt(base.where(~(vol20 >= vol_cap), base * 0.5))

    crash = ov <= -0.05
    intra_crash = intra[crash & prem_open.notna()]
    stats = {
        "n_days": int(len(idx)),
        "n_crash5": int(crash.sum()),
        "n_crash7": int((ov <= -0.07).sum()),
        "crash5_intraday_mean": float(intra_crash.mean()),
        "crash5_intraday_t": float(intra_crash.mean() / (intra_crash.std() / np.sqrt(len(intra_crash)))),
        "crash5_share_base_long": float((base[crash] > 0).mean()),
        "next_open_ov": float(uso.iloc[-1] / uso.iloc[-2] - 1),
        "prem_open_last": float(prem_open.iloc[-1]),
    }

    ev = pd.DataFrame({"ov": ov, "gap": gap, "intraday": intra, "day": day, "fwd5": fwd5,
                       "prem_open": prem_open, "base": base})
    ev.to_csv(ROOT / "output_overnight" / "events.csv")

    labels = [r["bucket"] for r in rows]
    x = np.arange(len(rows))
    fig, ax = plt.subplots(figsize=(9, 4.2))
    ax.bar(x - 0.26, [r["gap"] for r in rows], 0.26, label="overnight gap (unavoidable)")
    ax.bar(x, [r["intraday"] for r in rows], 0.26, label="open-to-close (tradable)")
    ax.bar(x + 0.26, [r["day"] for r in rows], 0.26, label="close-to-close")
    ax.set_xticks(x, [f"{l}\nn={r['n']}" for l, r in zip(labels, rows)], fontsize=8)
    ax.axhline(0, color="black", lw=0.8)
    ax.set_ylabel("mean return")
    ax.set_title("160723 after overnight USO shocks: gap does the damage")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.25, axis="y")
    fig.tight_layout()
    fig.savefig(ROOT / "output_overnight" / "buckets.png", dpi=150)
    plt.close(fig)
    res = {"buckets": rows, "tests": tests, "stats": stats}
    (ROOT / "output_overnight" / "overnight_risk.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    (ROOT / "output_overnight").mkdir(exist_ok=True)
    main()
