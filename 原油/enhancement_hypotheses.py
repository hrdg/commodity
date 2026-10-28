"""Enhanced hypotheses: premium dynamics, Brent carriers, 159981 fallback, DXY."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

import strategy

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
CFG = json.loads((ROOT / "config.json").read_text())


def series(name: str, col: str = "value") -> pd.Series:
    d = pd.read_csv(DATA / f"{name}.csv", parse_dates=["date"])
    return d.set_index("date")[col].sort_index()


def signals():
    wti, gas, ho = series("wti"), series("gasoline"), series("heating_oil")
    cushing = series("cushing")
    d = pd.concat([wti.rename("wti"), gas.rename("gas"), ho.rename("ho")], axis=1, sort=False).dropna()
    crack = (2 * d.gas * 42 + d.ho * 42 - 3 * d.wti) / 3
    thr = crack.rolling(252, min_periods=126).median()
    fs = (crack > thr).astype(float).where(thr.notna())
    roll = cushing.rolling(52).mean()
    cs = (roll - roll.shift(4) > 0).astype(float).where(roll.notna())
    return fs, cs


def carrier(code: str, start: str, fs, cs, lag: int = 6):
    px = series(code, "close").loc[start:]
    nav = series(f"nav_{code}", "nav")
    f = fs.reindex(px.index).ffill().shift(1)
    c = cs.reindex(px.index).ffill().shift(lag)
    base = pd.concat([f, c], axis=1).max(axis=1).fillna(0)
    prem = px / nav.reindex(px.index).ffill().shift(1) - 1
    gap = pd.Series(1.0, index=px.index)
    gap[prem > 0.05] = 0.5
    gap[prem > 0.10] = 0.0
    return px, base, prem, gap


def run(px, pos, fee=0.0003):
    pos = pos.reindex(px.index).fillna(0)
    pnl = pos.shift(1).fillna(0) * px.pct_change() - fee * pos.diff().abs().fillna(pos.abs())
    return strategy.metrics(pnl, pos)


def main() -> None:
    fs, cs = signals()
    start = "2017-05-05"
    out = {"carriers": {}}
    for code in ("160723", "501018", "161129", "160216"):
        px, base, prem, gap = carrier(code, start, fs, cs)
        out["carriers"][code] = {"base": run(px, base), "premium": run(px, base * gap)}

    # Premium dynamics / hysteresis on 160723.
    px, base, prem, gap = carrier("160723", start, fs, cs)
    # Hysteresis: block >10%, re-enter only <5%; otherwise previous state.
    state, arr = 1.0, []
    for p in prem.fillna(0):
        if p > 0.10:
            state = 0.0
        elif p < 0.05:
            state = 1.0
        arr.append(state)
    hyst = pd.Series(arr, index=px.index)
    prema = prem.rolling(5).mean()
    trend_block = (prem > 0.10) & (prema > prema.shift(1))
    dyn = gap.copy()
    dyn[trend_block] = 0.0
    out["premium_dynamics"] = {"static": run(px, base * gap),
                               "hysteresis": run(px, base * hyst),
                               "premium_trend": run(px, base * dyn)}

    # DXY 20-day trend: strong dollar -> half.
    dxy = series("dxy")
    dchg = dxy.pct_change(20).reindex(px.index).ffill().shift(1)
    dxy_cut = pd.Series(np.where(dchg > 0, 0.5, 1.0), index=px.index)
    out["dxy"] = {"premium": run(px, base * gap),
                  "premium_dxy": run(px, base * gap * dxy_cut)}

    # 2026/2020 premium blocks -> 159981 fallback when its trend is positive.
    px3 = series("159981", "close")
    ma20, ma60 = px3.rolling(20).mean(), px3.rolling(60).mean()
    trend = ((ma20 > ma60) & (px3.pct_change(20) > 0)).astype(float).shift(1).fillna(0)
    idx = px.index.intersection(px3.index)
    p160 = (base * gap).reindex(idx)
    p159 = ((gap.reindex(idx) == 0) & (trend.reindex(idx) > 0)).astype(float)
    ret160 = px.pct_change().reindex(idx).fillna(0)
    ret159 = px3.pct_change().reindex(idx).fillna(0)
    pnl = p160.shift(1).fillna(0) * ret160 + p159.shift(1).fillna(0) * ret159
    turn = p160.diff().abs().fillna(p160.abs()) + p159.diff().abs().fillna(p159.abs())
    pnl = pnl - 0.0003 * turn
    out["fallback_159981"] = {"premium": strategy.metrics(
        (p160.shift(1).fillna(0) * ret160 - 0.0003 * p160.diff().abs().fillna(p160.abs())), p160),
        "premium_159981": strategy.metrics(pnl, p160 + p159)}

    # Season overlay on premium.
    season = pd.Series(px.index.month.isin([4, 5, 6]).astype(float), index=px.index)
    out["season"] = {"premium": run(px, base * gap),
                     "premium_season": run(px, base * np.maximum(gap, season))}

    (ROOT / "output" / "enhancement_hypotheses.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2, default=float) + "\n")
    print(json.dumps(out, ensure_ascii=False, indent=1, default=float))


if __name__ == "__main__":
    main()
