#!/usr/bin/env python3
"""GTJA series-26 G6-diff5 soybean-meal ETF strategy (long-only).

Frozen signal set:
  soy_yoy, port_yoy, basis_z, spread_diff_neg, ware_diff5, ec_z.
Equal-weight available factors; long when the average sign is positive and at
least 3 factors are available.  Decision at close, exposure from next open.
One-way cost 3bp.  ETF: 159985.SZ.

This is a research reconstruction.  The original report does not disclose the
0/1/-1 thresholds, so the transforms here are transparent adapters.
"""
from __future__ import annotations

import argparse
import json
import pathlib

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent
DATA = ROOT / "data"
ETF_FILE = DATA / "159985_soybean_meal_etf.csv"


def load_main(name: str) -> pd.DataFrame:
    a = pd.read_csv(DATA / f"{name}_main_sina.csv", parse_dates=["日期"])
    b = pd.read_csv(DATA / f"{name}_main_2025_2026.csv", parse_dates=["日期"])
    d = pd.concat([a, b]).rename(columns={
        "日期": "date", "开盘价": "open", "收盘价": "close",
        "最高价": "high", "最低价": "low", "成交量": "volume"})
    d = d.drop_duplicates("date", keep="last").set_index("date").sort_index()
    for c in ["open", "close", "high", "low", "volume"]:
        if c in d:
            d[c] = pd.to_numeric(d[c], errors="coerce")
    return d.dropna(subset=["close"])


def load_etf() -> pd.DataFrame:
    d = pd.read_csv(ETF_FILE, parse_dates=["date"])
    d = d.drop_duplicates("date", keep="last").set_index("date").sort_index()
    for c in ["open", "high", "low", "close"]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    return d.dropna(subset=["open", "close"])


def to_decision(obs: pd.Series, cal: pd.DatetimeIndex) -> pd.Series:
    """Map timestamped observations to the first trading close on/after date."""
    obs = obs.dropna().sort_index()
    obs = obs[~obs.index.duplicated(keep="last")]
    rows = {}
    for ts, value in obs.items():
        pos = cal.searchsorted(pd.Timestamp(ts).normalize(), side="left")
        if pos < len(cal):
            rows[cal[pos]] = value
    if not rows:
        return pd.Series(dtype=float, index=cal)
    return pd.Series(rows).sort_index().reindex(cal).ffill()


def zsig(v: pd.Series, window: int, direction: int = 1) -> pd.Series:
    minp = max(6, int(window * 0.6))
    m = v.rolling(window, min_periods=minp).mean()
    s = v.rolling(window, min_periods=minp).std()
    return np.sign((v - m) / s) * direction


def yoy_sig(v: pd.Series, lag: int, direction: int = -1) -> pd.Series:
    return np.sign(v.pct_change(lag, fill_method=None)) * direction


def build_signals(cal: pd.DatetimeIndex) -> pd.DataFrame:
    soy = pd.read_csv(DATA / "factor_soy_inventory_combined.csv", parse_dates=["pub"])
    soy = soy.set_index("pub")["value"].dropna().sort_index()
    port = pd.read_csv(DATA / "soy_port_inventory_weekly.csv", parse_dates=["publish"])
    port = port.set_index("publish")["value"].dropna().sort_index()
    basis = pd.concat([
        pd.read_csv(DATA / "m_basis_2016_2024.csv", parse_dates=["date"]),
        pd.read_csv(DATA / "m_basis_2025_2026.csv", parse_dates=["date"]),
    ]).sort_values("date").set_index("date")["dom_basis_rate"].dropna()

    m = load_main("M0")
    rm = load_main("RM0")
    common = m.index.intersection(rm.index)
    spread = m.loc[common, "close"] - rm.loc[common, "close"]

    wh = pd.read_csv(DATA / "warehouse_receipts_2016_2024.csv", parse_dates=["date"])
    wh = wh.set_index("date")["receipts"].dropna()
    latest = pd.read_csv(DATA / "m_warehouse_receipt_latest.csv", parse_dates=["date"])
    latest = latest.set_index("date")["stock"].loc["2025-01-01":]
    wh = pd.concat([wh, latest]).sort_index()

    ec = pd.read_csv(DATA / "meal_inventory_east_china_candidates.csv",
                     parse_dates=["obs_date", "published_at"])
    ec = ec[ec.is_latest_revision]
    ec = ec.set_index("published_at")["value_wan_t"].dropna().sort_index()

    raw = {
        "soy_yoy": yoy_sig(soy, 52, -1),
        "port_yoy": yoy_sig(port, 52, -1),
        "basis_z": zsig(basis, 252, +1),
        "spread_diff_neg": zsig(spread, 252, -1),
        "ware_diff5": zsig(wh.diff(5), 252, -1),
        "ec_z": zsig(ec, 52, -1),
    }
    out = {}
    for name, s in raw.items():
        out[name] = to_decision(s, cal)
    return pd.DataFrame(out)


def positions(sig: pd.DataFrame) -> pd.Series:
    av = sig.notna()
    n = av.sum(axis=1)
    score = sig.fillna(0.0).sum(axis=1) / n.replace(0, np.nan)
    pos = (score > 0).astype(float)
    return pos.where(n >= 3, 0.0).fillna(0.0)


def perf(pnl: pd.Series) -> dict:
    pnl = pnl.dropna()
    nav = (1 + pnl).cumprod()
    years = (nav.index[-1] - nav.index[0]).days / 365.25
    cagr = nav.iloc[-1] ** (1 / years) - 1 if years > 0 else np.nan
    vol = pnl.std() * np.sqrt(252)
    sharpe = pnl.mean() / pnl.std() * np.sqrt(252) if pnl.std() > 0 else np.nan
    mdd = (nav / nav.cummax() - 1).min()
    return {"n": int(len(pnl)), "cagr": float(cagr), "vol": float(vol),
            "sharpe": float(sharpe), "mdd": float(mdd),
            "calmar": float(cagr / abs(mdd)) if mdd < 0 else np.nan,
            "win": float((pnl > 0).mean()), "final": float(nav.iloc[-1])}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default=str(ROOT / "output"))
    args = ap.parse_args()
    outdir = pathlib.Path(args.output)
    outdir.mkdir(parents=True, exist_ok=True)

    etf = load_etf()
    window = etf.loc["2019-12-05":"2026-10-21"]
    # Build signals on the futures calendar, then map to ETF sessions.  This
    # avoids losing signals on days when the ETF and futures calendars differ.
    futures_cal = load_main("M0").index
    sig = build_signals(futures_cal)
    pos = positions(sig).reindex(window.index).ffill().fillna(0.0)

    r = (window.open.shift(-1) / window.open - 1).iloc[:-1]
    p = pos.reindex(r.index).ffill().fillna(0.0).shift(1).fillna(0.0)
    turn = p.diff().abs().fillna(p.abs())
    pnl = p * r - 0.0003 * turn
    bh = r.copy()

    res = {"strategy": perf(pnl), "buy_hold": perf(bh),
           "exposure": float(p.mean()), "turnover": float(turn.sum() / ((pnl.index[-1] - pnl.index[0]).days / 365.25)),
           "period": [str(pnl.index[0].date()), str(pnl.index[-1].date())],
           "signals": sig, "positions": pos}
    yearly = {str(k): float((1 + v).prod() - 1) for k, v in pnl.groupby(pnl.index.year)}
    res["yearly"] = yearly

    pd.DataFrame({"date": window.index, "position": pos.reindex(window.index).fillna(0.0).values}).to_csv(
        outdir / "g6_diff5_positions.csv", index=False)
    (outdir / "g6_diff5_metrics.json").write_text(
        json.dumps({k: v for k, v in res.items() if k not in ("signals", "positions")},
                   ensure_ascii=False, indent=2, default=float) + "\n")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.family"] = ["Hiragino Sans GB", "Arial Unicode MS", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    nav = (1 + pnl).cumprod(); nav_bh = (1 + bh).cumprod()
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True,
                                   gridspec_kw={"height_ratios": [2.1, 1.0], "hspace": 0.08})
    ax1.plot(nav.index, nav.values, color="#1F4E79", lw=2.2, label="G6-diff5")
    ax1.plot(nav_bh.index, nav_bh.values, color="#222222", lw=2.2, ls="--", label="买入持有 159985")
    ax1.set_yscale("log"); ax1.set_ylabel("净值（对数轴）")
    ax1.set_title("豆粕 ETF G6-diff5 与买入持有：2019-12–2026-10", loc="left", fontsize=14)
    ax1.grid(alpha=0.25, which="both"); ax1.legend(frameon=False, loc="upper left")
    dd = nav / nav.cummax() - 1; ddb = nav_bh / nav_bh.cummax() - 1
    ax2.plot(dd.index, dd.values * 100, color="#1F4E79", lw=1.8, label="G6-diff5")
    ax2.plot(ddb.index, ddb.values * 100, color="#222222", lw=1.8, ls="--", label="买入持有")
    ax2.set_ylabel("回撤（%）"); ax2.grid(alpha=0.25); ax2.axhline(0, color="#888", lw=0.8)
    ax2.set_xlabel("日期"); ax2.legend(frameon=False, loc="lower left")
    fig.tight_layout()
    fig.savefig(outdir / "g6_diff5_nav.png", dpi=160, bbox_inches="tight")
    plt.close(fig)

    print(json.dumps({k: v for k, v in res.items() if k not in ("signals", "positions")},
                     ensure_ascii=False, indent=2, default=float))


if __name__ == "__main__":
    main()
