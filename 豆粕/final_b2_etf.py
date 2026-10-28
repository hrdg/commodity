#!/usr/bin/env python3
"""Final PV+fundamental signal from the research run, applied to 159985.

Futures signal (M0):
  20% PV+VT15 + 20% PV+vol40 + 40% G6 + 10% K2 + 10% basis

ETF long-only mapping:
  full:      signal > 0 -> 100% ETF, else cash
  fractional: max(signal, 0)

This is a research reconstruction, not a live mandate.
"""
from __future__ import annotations

import json
import pathlib

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent
DATA = ROOT / "data"


def load_main(name):
    a = pd.read_csv(DATA / f"{name}_main_sina.csv", parse_dates=["日期"])
    b = pd.read_csv(DATA / f"{name}_main_2025_2026.csv", parse_dates=["日期"])
    d = pd.concat([a, b]).rename(columns={"日期": "date", "开盘价": "open", "收盘价": "close",
                                          "最高价": "high", "最低价": "low", "成交量": "volume"})
    d = d.drop_duplicates("date", keep="last").set_index("date").sort_index()
    for c in ["open", "high", "low", "close", "volume"]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d.dropna(subset=["close"])
    if pd.Timestamp("2014-10-08") in d.index:
        d.loc["2014-10-08", ["open", "high", "low", "close"]] = [2780, 2795, 2760, 2790]
    r = d.close.pct_change().clip(-0.06, 0.06)
    sc = (1 + r.fillna(0)).cumprod() / d.close
    out = d.copy()
    for c in ["open", "high", "low", "close"]:
        out[c] = d[c] * sc
    return out


def load_etf():
    d = pd.read_csv(DATA / "159985_soybean_meal_etf.csv", parse_dates=["date"])
    d = d.drop_duplicates("date", keep="last").set_index("date").sort_index()
    for c in ["open", "high", "low", "close"]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    return d.dropna(subset=["open", "close"])


def decision(obs, cal):
    obs = obs.dropna().sort_index(); obs = obs[~obs.index.duplicated(keep="last")]
    rows = {}
    for ts, v in obs.items():
        p = cal.searchsorted(pd.Timestamp(ts).normalize(), side="left")
        if p < len(cal):
            rows[cal[p]] = v
    return pd.Series(rows).sort_index().reindex(cal).ffill()


def zsig(v, w, d=1):
    m = v.rolling(w, min_periods=max(6, int(w * .6))).mean()
    s = v.rolling(w, min_periods=max(6, int(w * .6))).std()
    return np.sign((v - m) / s) * d


def yoy(v, lag, d=-1):
    return np.sign(v.pct_change(lag, fill_method=None)) * d


def state(long_entry, short_entry, idx):
    out, cur = [], 0
    for l, s in zip(long_entry.values, short_entry.values):
        if l: cur = 1
        elif s: cur = -1
        out.append(cur)
    return pd.Series(out, index=idx)


def main():
    M = load_main("M0"); RM = load_main("RM0"); A0 = load_main("A0"); Y0 = load_main("Y0")
    cal = M.index
    ret = M.close.pct_change()

    # PV factors
    ex = M.close.ewm(span=6, adjust=False).mean()
    ex = ex.ewm(span=6, adjust=False).mean().ewm(span=6, adjust=False).mean()
    trix = ex / ex.shift(1) - 1
    tsp = trix.rolling(10).mean() - trix.rolling(30).mean()
    trix_sig = pd.Series(np.where(tsp.abs() > 0.0005, np.sign(tsp), 0.0), index=cal)
    tp = (M.high + M.low + M.close) / 3
    ma = tp.rolling(20).mean(); md = (tp - ma).abs().rolling(20).mean()
    cci = (tp - ma) / (0.015 * md)
    cci_sig = state(cci < -150, cci > 150, cal)
    bm = M.close.rolling(20).mean(); bs = M.close.rolling(20).std()
    boll_sig = state(M.close > bm + 2.5 * bs, M.close < bm - 2.5 * bs, cal)
    med = (M.high + M.low) / 2
    med_sig = pd.Series(np.sign((med.rolling(3).mean() - med.rolling(15).mean()) / med), index=cal)
    v40 = ret.rolling(40).std()
    vol40_sig = pd.Series(np.sign(v40 - v40.rolling(30).mean()), index=cal)
    base4 = np.sign(pd.DataFrame({"trix": trix_sig, "cci": cci_sig, "boll": boll_sig,
                                  "medma": med_sig}).fillna(0).mean(axis=1))
    vol20 = ret.rolling(20).std() * np.sqrt(252)
    vt15 = base4 * (0.15 / vol20).clip(upper=1.0).fillna(0.0)
    pv_vol = np.sign(pd.DataFrame({"t": trix_sig, "c": cci_sig, "b": boll_sig,
                                   "m": med_sig, "v": vol40_sig}).fillna(0).mean(axis=1))

    # Fundamentals G6
    soy = pd.read_csv(DATA / "factor_soy_inventory_combined.csv", parse_dates=["pub"])
    soy = soy.set_index("pub")["value"].dropna().sort_index()
    port = pd.read_csv(DATA / "soy_port_inventory_weekly.csv", parse_dates=["publish"])
    port = port.set_index("publish")["value"].dropna().sort_index()
    basis = pd.concat([pd.read_csv(DATA / "m_basis_2016_2024.csv", parse_dates=["date"]),
                       pd.read_csv(DATA / "m_basis_2025_2026.csv", parse_dates=["date"])]) \
        .sort_values("date").set_index("date")["dom_basis_rate"].dropna()
    wh = pd.read_csv(DATA / "warehouse_receipts_2016_2024.csv", parse_dates=["date"])
    wh = wh.set_index("date")["receipts"].dropna()
    latest = pd.read_csv(DATA / "m_warehouse_receipt_latest.csv", parse_dates=["date"])
    wh = pd.concat([wh, latest.set_index("date")["stock"].loc["2025-01-01":]]).sort_index()
    ec = pd.read_csv(DATA / "meal_inventory_east_china_candidates.csv",
                     parse_dates=["obs_date", "published_at"])
    ec = ec[ec.is_latest_revision].set_index("published_at")["value_wan_t"].dropna().sort_index()

    raw = {"soy_yoy": yoy(soy, 52, -1), "port_yoy": yoy(port, 52, -1),
           "basis_z": zsig(basis, 252, +1), "spread_diff_neg": zsig(M.close - RM.close, 252, -1),
           "ware_diff5": zsig(wh.diff(5), 252, -1), "ec_z": zsig(ec, 52, -1)}
    F = pd.DataFrame({k: decision(v, cal) for k, v in raw.items()})
    av = F.notna(); n = av.sum(axis=1)
    score = F.fillna(0).sum(axis=1) / n.replace(0, np.nan)
    g6 = np.sign(score).where(n >= 3, 0.0).fillna(0.0)

    # K2: crush margin + meal inventory
    common = M.index.intersection(A0.index).intersection(Y0.index)
    margin = ((M.loc[common, "close"] * 0.79 + Y0.loc[common, "close"] * 0.19
               - A0.loc[common, "close"]) / A0.loc[common, "close"])
    crush = (margin < 0).astype(float).reindex(cal).ffill().fillna(0.0)
    meal = pd.read_csv(DATA / "soy_crush_weekly.csv", parse_dates=["publish"])
    meal = meal.set_index("publish")["meal"].sort_index()
    mma = meal.rolling(52, min_periods=26).mean()
    meal_sig = decision((mma - mma.shift(4) < 0).astype(float), cal).fillna(0.0)
    pma = port.rolling(52, min_periods=26).mean()
    port_sig = decision((pma - pma.shift(4) < 0).astype(float), cal).fillna(0.0)
    inv = port_sig.copy(); inv.loc[meal.index.min():] = meal_sig.loc[meal.index.min():]
    k2 = (crush + inv - 1).clip(-1, 1)
    basis_ls = np.sign(decision(raw["basis_z"], cal).fillna(0.0))

    final = (0.8 * (0.25 * vt15 + 0.25 * pv_vol + 0.5 * g6) + 0.1 * k2 + 0.1 * basis_ls).clip(-1, 1)
    pd.DataFrame({"date": cal, "final": final.values}).to_csv(
        ROOT / "output" / "final_b2_signal.csv", index=False)

    etf = load_etf(); w = etf.loc["2019-12-05":"2026-10-21"]
    r = (w.open.shift(-1) / w.open - 1).iloc[:-1]

    def run(sig_map):
        p = sig_map.reindex(r.index).ffill().fillna(0.0).shift(1).fillna(0.0)
        turn = p.diff().abs().fillna(p.abs())
        return p * r - 0.0003 * turn, p

    res = {}
    nav = {}
    for name, sig_map in (("full", (final > 0).astype(float)),
                          ("fractional", final.clip(lower=0))):
        pnl, p = run(sig_map)
        nav[name] = (1 + pnl).cumprod()
        res[name] = {"cagr": float(nav[name].iloc[-1] ** (365.25 / (pnl.index[-1] - pnl.index[0]).days) - 1),
                     "sharpe": float(pnl.mean() / pnl.std() * np.sqrt(252)),
                     "mdd": float((nav[name] / nav[name].cummax() - 1).min()),
                     "exposure": float(p.reindex(pnl.index).mean()),
                     "yearly": {str(k): float((1 + v).prod() - 1) for k, v in pnl.groupby(pnl.index.year)}}
        res[name]["calmar"] = float(res[name]["cagr"] / abs(res[name]["mdd"]))
    bh = (1 + r).cumprod(); res["buy_hold"] = {"cagr": float(bh.iloc[-1] ** (365.25 / (r.index[-1] - r.index[0]).days) - 1),
                                               "sharpe": float(r.mean() / r.std() * np.sqrt(252)),
                                               "mdd": float((bh / bh.cummax() - 1).min())}
    res["buy_hold"]["calmar"] = res["buy_hold"]["cagr"] / abs(res["buy_hold"]["mdd"])

    out = ROOT / "output"; out.mkdir(exist_ok=True)
    (out / "final_b2_etf_metrics.json").write_text(json.dumps(res, ensure_ascii=False, indent=2) + "\n")
    pd.DataFrame({"date": r.index, "position_full": (final > 0).astype(float).reindex(r.index).ffill().fillna(0).values,
                  "position_fractional": final.clip(lower=0).reindex(r.index).ffill().fillna(0).values}).to_csv(
        out / "final_b2_etf_positions.csv", index=False)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.family"] = ["Hiragino Sans GB", "Arial Unicode MS", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True,
                                   gridspec_kw={"height_ratios": [2.1, 1.0], "hspace": 0.08})
    ax1.plot(nav["full"].index, nav["full"].values, color="#1F4E79", lw=2.2, label="final_b2 满仓/现金")
    ax1.plot(nav["fractional"].index, nav["fractional"].values, color="#2E8B57", lw=2.0, label="final_b2 分数仓位")
    ax1.plot(bh.index, bh.values, color="#222", lw=2.2, ls="--", label="买入持有 159985")
    ax1.set_yscale("log"); ax1.set_ylabel("净值（对数轴）")
    ax1.set_title("final_b2 信号用于豆粕 ETF（只做多）：2019-12–2026-10", loc="left", fontsize=14)
    ax1.grid(alpha=0.25, which="both"); ax1.legend(frameon=False, loc="upper left")
    for k, c in (("full", "#1F4E79"), ("fractional", "#2E8B57"), ("bh", "#222")):
        nv = bh if k == "bh" else nav[k]
        dd = nv / nv.cummax() - 1
        ax2.plot(dd.index, dd.values * 100, color=c, lw=1.8, ls="--" if k == "bh" else "-")
    ax2.set_ylabel("回撤（%）"); ax2.grid(alpha=0.25); ax2.axhline(0, color="#888", lw=0.8)
    ax2.set_xlabel("日期")
    fig.tight_layout(); fig.savefig(out / "final_b2_etf_nav.png", dpi=160, bbox_inches="tight")
    plt.close(fig)
    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
