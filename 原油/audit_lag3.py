"""Re-run all enhancement hypotheses with PIT-safe NAV lag3."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

import strategy

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
FEE = 0.0003
START, END = "2017-05-05", "2026-10-27"
OOS = ("2022-01-01", END)


def s(name: str, col: str = "value") -> pd.Series:
    d = pd.read_csv(DATA / f"{name}.csv", parse_dates=["date"])
    return d.set_index("date")[col].sort_index()


def signals():
    w, g, h = s("wti"), s("gasoline"), s("heating_oil")
    c = s("cushing")
    d = pd.concat([w.rename("w"), g.rename("g"), h.rename("h")], axis=1, sort=False).dropna()
    crack = (2 * d.g * 42 + d.h * 42 - 3 * d.w) / 3
    thr = crack.rolling(252, min_periods=126).median()
    fs = (crack > thr).astype(float).where(thr.notna())
    roll = c.rolling(52).mean()
    cs = (roll - roll.shift(4) > 0).astype(float).where(roll.notna())
    return fs, cs


def hyst(prem: pd.Series, block=0.10, reenter=0.05, gate: pd.Series | None = None) -> pd.Series:
    state, out = 1.0, []
    for i, p in enumerate(prem.fillna(0)):
        if p > block:
            state = 0.0
        elif p < reenter and (gate is None or not bool(gate.iloc[i])):
            state = 1.0
        out.append(state)
    return pd.Series(out, index=prem.index)


def carrier(code: str, start=START, lag=6, nav_lag=3):
    px = s(code, "close").loc[start:]
    nav = s(f"nav_{code}", "nav")
    fs, cs = signals()
    f = fs.reindex(px.index).ffill().shift(1)
    c = cs.reindex(px.index).ffill().shift(lag)
    base = pd.concat([f, c], axis=1).max(axis=1).fillna(0)
    prem = px / nav.reindex(px.index).ffill().shift(nav_lag) - 1
    return px, base, prem


def close_pnl(px, pos):
    return pos.shift(1).fillna(0) * px.pct_change() - FEE * pos.diff().abs().fillna(pos.abs())


def open_pnl(px, pos, op):
    held = pos.shift(1).fillna(0)
    return held * (op.shift(-1) / op - 1) - FEE * held.diff().abs().fillna(held.abs())


def perf(pnl, pos, a=None, b=None):
    if a:
        pnl, pos = pnl.loc[a:b], pos.loc[a:b]
    return strategy.metrics(pnl, pos)


def main() -> None:
    fs, cs = signals()
    rows = []

    def add(name, px, pos):
        pnl = close_pnl(px, pos)
        f = perf(pnl, pos, START, END)
        o = perf(pnl, pos, *OOS)
        rows.append({"name": name,
                     "full_cagr": f["cagr"], "full_sharpe": f["sharpe"], "full_calmar": f["calmar"], "full_mdd": f["mdd"],
                     "oos_cagr": o["cagr"], "oos_sharpe": o["sharpe"], "oos_calmar": o["calmar"], "oos_mdd": o["mdd"]})

    px, base, prem = carrier("160723")
    add("160723 10/5 close", px, base * hyst(prem, 0.10, 0.05))
    add("160723 9/3 close", px, base * hyst(prem, 0.09, 0.03))

    # Open execution
    op = s("160723", "open").reindex(px.index)
    for label, b, r in (("10/5", 0.10, 0.05), ("9/3", 0.09, 0.03)):
        pos = base * hyst(prem, b, r)
        pnl = open_pnl(px, pos, op)
        f = perf(pnl, pos, START, END); o = perf(pnl, pos, *OOS)
        rows.append({"name": f"160723 {label} open",
                     "full_cagr": f["cagr"], "full_sharpe": f["sharpe"], "full_calmar": f["calmar"], "full_mdd": f["mdd"],
                     "oos_cagr": o["cagr"], "oos_sharpe": o["sharpe"], "oos_calmar": o["calmar"], "oos_mdd": o["mdd"]})

    # Volatility target on 10/5
    pos = base * hyst(prem, 0.10, 0.05)
    base_pnl = close_pnl(px, pos)
    for target in (0.15, 0.25):
        rv = base_pnl.rolling(20, min_periods=10).std() * np.sqrt(252)
        w = (target / rv).replace([np.inf, -np.inf], np.nan).clip(0, 1).fillna(0)
        e = pos * w
        add(f"160723 10/5 + vol{int(target*100)}", px, e)

    # TIPS spike brake
    dfii = pd.read_csv(DATA / "dfii10.csv", parse_dates=["date"]).set_index("date")["dfii10"].sort_index()
    dy = dfii.reindex(px.index).ffill().diff(20)
    trig = (dy >= 0.30).fillna(False).to_numpy()
    st, arr = 1.0, []
    cool = 0
    for t in trig:
        if t:
            cool = 20
        if cool > 0:
            arr.append(0.5); cool -= 1
        else:
            arr.append(1.0)
    tips = pd.Series(arr, index=px.index).shift(1).fillna(1.0)
    add("160723 10/5 + TIPS", px, pos * tips)

    # Carrier comparison
    for code in ("501018", "161129", "160216"):
        p, b, pr = carrier(code)
        add(f"{code} 10/5 close", p, b * hyst(pr, 0.10, 0.05))

    # Premium percentile
    pct = prem.rolling(252, min_periods=126).apply(lambda x: float((x < x.iloc[-1]).mean()), raw=False)
    state, arr = 1.0, []
    for q in pct.fillna(0.5):
        if q > 0.90:
            state = 0.0
        elif q < 0.50:
            state = 1.0
        arr.append(state)
    add("160723 premium percentile", px, base * pd.Series(arr, index=px.index))

    # DXY filter
    dxy = s("dxy")
    dchg = dxy.pct_change(20).reindex(px.index).ffill().shift(1)
    dcut = pd.Series(np.where(dchg > 0, 0.5, 1.0), index=px.index)
    add("160723 10/5 + DXY", px, pos * dcut)

    # Season forced overlay
    season = pd.Series(px.index.month.isin([4, 5, 6]).astype(float), index=px.index)
    add("160723 10/5 + season", px, base * np.maximum(hyst(prem, 0.10, 0.05), season))

    # SGZT strict / suspend half
    sg = pd.read_csv(DATA / "sgzt_160723.csv", parse_dates=["date"]).set_index("date")["SGZT"].reindex(px.index).ffill()
    susp = sg.str.contains("暂停", na=False)
    add("160723 10/5 + SGZT strict", px, base * hyst(prem, 0.10, 0.05, gate=susp))
    add("160723 10/5 + suspend half", px, pos * np.where(susp & (prem > 0.05), 0.5, 1.0))

    # 159981 fallback when premium blocked
    p3 = s("159981", "close")
    ma20, ma60 = p3.rolling(20).mean(), p3.rolling(60).mean()
    trend = ((ma20 > ma60) & (p3.pct_change(20) > 0)).astype(float).shift(1).fillna(0)
    idx = px.index.intersection(p3.index)
    gap = hyst(prem, 0.10, 0.05)
    p160 = (pos * gap).reindex(idx)
    p159 = ((gap.reindex(idx) == 0) & (trend.reindex(idx) > 0)).astype(float)
    pnl = p160.shift(1).fillna(0) * px.pct_change().reindex(idx).fillna(0) + p159.shift(1).fillna(0) * p3.pct_change().reindex(idx).fillna(0)
    pnl -= FEE * (p160.diff().abs().fillna(p160.abs()) + p159.diff().abs().fillna(p159.abs()))
    f = perf(pnl, p160 + p159, "2020-01-17", END); o = perf(pnl, p160 + p159, "2022-01-01", END)
    rows.append({"name": "160723 10/5 + 159981 fallback (2020+)",
                 "full_cagr": f["cagr"], "full_sharpe": f["sharpe"], "full_calmar": f["calmar"], "full_mdd": f["mdd"],
                 "oos_cagr": o["cagr"], "oos_sharpe": o["sharpe"], "oos_calmar": o["calmar"], "oos_mdd": o["mdd"]})

    out = pd.DataFrame(rows)
    out.to_csv(ROOT / "output" / "audit_lag3.csv", index=False)
    print(out.round(3).to_string(index=False))
    (ROOT / "output" / "audit_lag3.json").write_text(
        json.dumps(out.to_dict("records"), ensure_ascii=False, indent=2, default=float) + "\n")


if __name__ == "__main__":
    main()
