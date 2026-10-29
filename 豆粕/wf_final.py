#!/usr/bin/env python3
"""Yearly walk-forward of final_b2 templates, futures and long-only ETF."""
from __future__ import annotations

import json
import pathlib

import numpy as np
import pandas as pd

from final_b2_etf import build_final, load_etf

ROOT = pathlib.Path(__file__).resolve().parent


def perf(pnl):
    pnl = pnl.dropna()
    nav = (1 + pnl).cumprod()
    yrs = (nav.index[-1] - nav.index[0]).days / 365.25
    cagr = nav.iloc[-1] ** (1 / yrs) - 1 if yrs > 0 else np.nan
    mdd = (nav / nav.cummax() - 1).min()
    sr = pnl.mean() / pnl.std() * np.sqrt(252) if pnl.std() > 0 else np.nan
    return {"n": int(len(pnl)), "cagr": float(cagr), "sharpe": float(sr),
            "mdd": float(mdd), "calmar": float(cagr / abs(mdd)) if mdd < 0 else np.nan,
            "final": float(nav.iloc[-1])}


def main():
    cal, final, c = build_final()
    pv_vt, pv_vol, g6, k2, basis = c["pv_vt"], c["pv_vol"], c["g6"], c["k2"], c["basis"]
    ret = final.index.to_series().index  # placeholder to keep index
    Mret = pd.Series(np.nan, index=cal)
    # Rebuild M0 returns from the same loader used by final_b2_etf.
    from final_b2_etf import load_main
    Mret = load_main("M0").close.pct_change().reindex(cal)

    templates = {
        "PV_VT": pv_vt,
        "PV_VOL": pv_vol,
        "PV50_G50": 0.5 * pv_vt + 0.5 * g6,
        "PV50_G30_K10_B10": 0.5 * pv_vt + 0.3 * g6 + 0.1 * k2 + 0.1 * basis,
        "PV60_G20_K10_B10": 0.6 * pv_vt + 0.2 * g6 + 0.1 * k2 + 0.1 * basis,
        "final_b2": final,
        "final_b2_L10": 0.1 + 0.9 * final,
        "PV50_G30_K10_B10_L10": 0.1 + 0.9 * (0.5 * pv_vt + 0.3 * g6 + 0.1 * k2 + 0.1 * basis),
    }
    templates = {k: v.clip(-1, 1) for k, v in templates.items()}

    def pnl_of(p, a, b):
        x = p.loc[a:b]
        r = Mret.loc[a:b]
        pnl = x.shift(1) * r - 0.0003 * x.diff().abs().fillna(0)
        return pnl.dropna()

    picks = {}
    wf = pd.Series(0.0, index=cal)
    for year in range(2019, 2027):
        train_start = f"{year-3}-01-01"; train_end = f"{year-1}-12-31"
        rows = []
        for name, p in templates.items():
            pnl = pnl_of(p, train_start, train_end)
            if len(pnl) < 100:
                continue
            st = perf(pnl)
            yearly_sr = [g.mean() / g.std() * np.sqrt(252) if g.std() > 0 else np.nan
                         for _, g in pnl.groupby(pnl.index.year)]
            rows.append((name, st["sharpe"], st["calmar"], st["mdd"], min(yearly_sr)))
        rows = [r for r in rows if np.isfinite(r[1]) and r[1] > 0]
        if not rows:
            picks[str(year)] = {"choice": "CASH"}
            continue
        rows.sort(key=lambda r: (r[1] + 0.25 * r[2], r[4]), reverse=True)
        name, sr, calmar, mdd, worst = rows[0]
        picks[str(year)] = {"choice": name, "train_sharpe": sr, "train_calmar": calmar,
                            "train_mdd": mdd, "worst_year_sharpe": worst}
        idx = cal[cal.year == year]
        wf.loc[idx] = templates[name].loc[idx]

    pnl = pnl_of(wf, "2019-01-01", "2026-10-20")
    res = {"picks": picks, "walkforward": perf(pnl),
           "yearly": {str(k): float((1 + v).prod() - 1) for k, v in pnl.groupby(pnl.index.year)},
           "fixed": {k: perf(pnl_of(p, "2019-01-01", "2026-10-20")) for k, p in templates.items()}}

    # ETF long-only mapping.
    etf = load_etf(); w = etf.loc["2019-12-05":etf.index.max()]
    er = (w.open.shift(-1) / w.open - 1).iloc[:-1]
    def etf_run(sig):
        p = sig.reindex(er.index).ffill().fillna(0.0).shift(1).fillna(0.0)
        turn = p.diff().abs().fillna(p.abs())
        return p * er - 0.0003 * turn, p
    etf_nav = {}
    res["etf"] = {}
    for name, sig in (("full", (wf > 0).astype(float)), ("fractional", wf.clip(lower=0))):
        pnl_e, p = etf_run(sig)
        etf_nav[name] = (1 + pnl_e).cumprod()
        st = perf(pnl_e)
        st["exposure"] = float(p.reindex(pnl_e.index).mean())
        st["yearly"] = {str(k): float((1 + v).prod() - 1) for k, v in pnl_e.groupby(pnl_e.index.year)}
        res["etf"][name] = st
    bh = (1 + er).cumprod(); res["etf"]["buy_hold"] = perf(er)

    out = ROOT / "output"; out.mkdir(exist_ok=True)
    (out / "wf_final_metrics.json").write_text(json.dumps(res, ensure_ascii=False, indent=2) + "\n")
    pd.DataFrame({"date": cal, "position": wf.values}).to_csv(out / "wf_final_futures_positions.csv", index=False)
    pd.DataFrame({"date": er.index,
                  "position_full": (wf > 0).astype(float).reindex(er.index).ffill().fillna(0).values,
                  "position_fractional": wf.clip(lower=0).reindex(er.index).ffill().fillna(0).values}).to_csv(
        out / "wf_final_etf_positions.csv", index=False)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.family"] = ["Hiragino Sans GB", "Arial Unicode MS", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True,
                                   gridspec_kw={"height_ratios": [2.1, 1.0], "hspace": 0.08})
    ax1.plot(etf_nav["full"].index, etf_nav["full"].values, color="#1F4E79", lw=2.2, label="WF 满仓/现金")
    ax1.plot(etf_nav["fractional"].index, etf_nav["fractional"].values, color="#2E8B57", lw=2.0, label="WF 分数仓位")
    ax1.plot(bh.index, bh.values, color="#222", lw=2.2, ls="--", label="买入持有 159985")
    ax1.set_yscale("log"); ax1.set_ylabel("净值（对数轴）")
    ax1.set_title("逐年 walk-forward 信号用于豆粕 ETF（只做多）：2019-12–2026-10", loc="left", fontsize=14)
    ax1.grid(alpha=0.25, which="both"); ax1.legend(frameon=False, loc="upper left")
    for k, c in (("full", "#1F4E79"), ("fractional", "#2E8B57"), ("bh", "#222")):
        nv = bh if k == "bh" else etf_nav[k]
        dd = nv / nv.cummax() - 1
        ax2.plot(dd.index, dd.values * 100, color=c, lw=1.8, ls="--" if k == "bh" else "-")
    ax2.set_ylabel("回撤（%）"); ax2.grid(alpha=0.25); ax2.axhline(0, color="#888", lw=0.8)
    ax2.set_xlabel("日期")
    fig.tight_layout(); fig.savefig(out / "wf_final_etf_nav.png", dpi=160, bbox_inches="tight")
    plt.close(fig)
    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
