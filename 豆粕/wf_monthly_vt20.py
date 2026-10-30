#!/usr/bin/env python3
"""New baseline: monthly WF template selection + 20% volatility target.

- Every month's first trading day, choose one of 8 templates using only the
  prior 3 calendar years.
- ETF long-only: template signal > 0, scaled by min(1, 20% / 20d realized vol).
- 3bp one-way; decision at close, exposure from next session.
"""
from __future__ import annotations

import json
import pathlib

import numpy as np
import pandas as pd

from final_b2_etf import build_final, load_etf, load_main

ROOT = pathlib.Path(__file__).resolve().parent
DATA = ROOT / "data"


def load_roll():
    p = DATA / "M0_roll_adjusted_full.csv"
    return pd.read_csv(p, parse_dates=["date"]).set_index("date").sort_index().close.pct_change()


def perf(pnl):
    pnl = pnl.dropna(); nav = (1 + pnl).cumprod()
    yrs = (nav.index[-1] - nav.index[0]).days / 365.25
    cagr = nav.iloc[-1] ** (1 / yrs) - 1 if yrs > 0 else np.nan
    mdd = (nav / nav.cummax() - 1).min()
    sr = pnl.mean() / pnl.std() * np.sqrt(252) if pnl.std() > 0 else np.nan
    return {"n": int(len(pnl)), "cagr": float(cagr), "sharpe": float(sr),
            "mdd": float(mdd), "calmar": float(cagr / abs(mdd)) if mdd < 0 else np.nan,
            "final": float(nav.iloc[-1])}


def main():
    cal, final, c = build_final()
    vt, vv, g6, k2, basis = c["pv_vt"], c["pv_vol"], c["g6"], c["k2"], c["basis"]
    templates = {
        "PV_VT": vt, "PV_VOL": vv, "PV50_G50": 0.5 * vt + 0.5 * g6,
        "PV50_G30_K10_B10": 0.5 * vt + 0.3 * g6 + 0.1 * k2 + 0.1 * basis,
        "PV60_G20_K10_B10": 0.6 * vt + 0.2 * g6 + 0.1 * k2 + 0.1 * basis,
        "final_b2": final, "final_b2_L10": 0.1 + 0.9 * final,
        "PV50_G30_K10_B10_L10": 0.1 + 0.9 * (0.5 * vt + 0.3 * g6 + 0.1 * k2 + 0.1 * basis),
    }
    templates = {k: pd.Series(v, index=cal).clip(-1, 1).fillna(0) for k, v in templates.items()}

    # ETF proxy before listing, actual ETF after.
    roll = load_roll(); etf = load_etf(); er = (etf.open.shift(-1) / etf.open - 1).iloc[:-1]
    ov = roll.index.intersection(er.index); ov = ov[ov >= "2019-12-05"]
    carry = (er.loc[ov].mean() - roll.loc[ov].mean()) * 252 if len(ov) else 0.0
    synth = roll + carry / 252
    ret = pd.concat([synth[synth.index < "2019-12-05"], er[er.index >= "2019-12-05"]])
    ret = ret[~ret.index.duplicated(keep="last")].sort_index().reindex(cal).fillna(0.0)

    def cand_pnl(pos):
        p = (pos > 0).astype(float)
        return p.shift(1) * ret - 0.0003 * p.diff().abs().fillna(0)
    cand_pnl = {k: cand_pnl(v) for k, v in templates.items()}
    vol20 = ret.rolling(20).std() * np.sqrt(252)

    rdates = pd.Series(cal, index=cal).groupby([cal.year, cal.month]).first().tolist()
    wf = pd.Series(0.0, index=cal); picks = {}
    for i, d in enumerate(rdates):
        a, b = d - pd.DateOffset(years=3), d - pd.Timedelta(days=1)
        rows = []
        for name, pnl in cand_pnl.items():
            x = pnl.loc[a:b]
            if len(x) < 200:
                continue
            st = perf(x)
            if st["sharpe"] > 0:
                rows.append((name, st["sharpe"] + 0.25 * st["calmar"]))
        if not rows:
            picks[str(d.date())] = "CASH"; continue
        rows.sort(key=lambda z: z[1], reverse=True)
        chosen = rows[0][0]; picks[str(d.date())] = chosen
        pos = (templates[chosen] > 0).astype(float) * (0.20 / vol20).clip(upper=1.0).fillna(0)
        nxt = rdates[i + 1] if i + 1 < len(rdates) else cal[-1] + pd.Timedelta(days=1)
        idx = cal[(cal > d) & (cal < nxt)]
        wf.loc[idx] = pos.loc[idx]

    p = wf.reindex(ret.index).ffill().fillna(0).shift(1).fillna(0)
    pnl = p * ret - 0.0003 * p.diff().abs().fillna(0)
    starts = {"2010": "2010-01-01", "2016": "2016-01-01", "2026": "2026-01-01"}
    res = {"carry": float(carry), "picks": picks, "periods": {}}
    for name, s in starts.items():
        st = perf(pnl.loc[s:"2026-10-30"])
        st["exposure"] = float(p.reindex(pnl.loc[s:"2026-10-30"].index).mean())
        st["yearly"] = {str(k): float((1 + v).prod() - 1) for k, v in pnl.loc[s:"2026-10-30"].groupby(pnl.loc[s:].index.year)}
        res["periods"][name] = st
    res["etf_2019_2026"] = perf(pnl.loc["2019-12-05":"2026-10-30"])
    res["etf_2019_2026"]["exposure"] = float(p.reindex(pnl.loc["2019-12-05":"2026-10-30"].index).mean())

    out = ROOT / "output"; out.mkdir(exist_ok=True)
    (out / "wf_monthly_vt20_metrics.json").write_text(json.dumps(res, ensure_ascii=False, indent=2) + "\n")
    pd.DataFrame({"date": cal, "position": wf.values}).to_csv(out / "wf_monthly_vt20_positions.csv", index=False)

    nav = (1 + pnl).cumprod(); bh = (1 + ret).cumprod()
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.family"] = ["Hiragino Sans GB", "Arial Unicode MS", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True,
                                   gridspec_kw={"height_ratios": [2.1, 1.0], "hspace": 0.08})
    ax1.plot(nav.index, nav.values, color="#1F4E79", lw=2.2, label="WF 月/3y + VT20")
    ax1.plot(bh.index, bh.values, color="#222", lw=2.2, ls="--", label="买入持有（代理/ETF）")
    ax1.set_yscale("log"); ax1.set_ylabel("净值（对数轴）")
    ax1.set_title("豆粕 ETF 新基准：WF 月/3y + 20% 波动目标", loc="left", fontsize=14)
    ax1.grid(alpha=0.25, which="both"); ax1.legend(frameon=False, loc="upper left")
    for name, nv, color, ls in (("WF+VT20", nav, "#1F4E79", "-"), ("B&H", bh, "#222", "--")):
        dd = nv / nv.cummax() - 1
        ax2.plot(dd.index, dd.values * 100, color=color, lw=2.0, ls=ls)
    ax2.set_ylabel("回撤（%）"); ax2.grid(alpha=0.25); ax2.axhline(0, color="#888", lw=0.8)
    ax2.set_xlabel("日期")
    fig.tight_layout(); fig.savefig(out / "wf_monthly_vt20_nav.png", dpi=160, bbox_inches="tight")
    plt.close(fig)
    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
