"""160723 嘉实原油 LOF: 裂解价差 + 库欣库存 + 溢价分层。

只做多。基础信号为 3-2-1 裂解价差（252 日滚动中位数）与库欣库存
（52 周均值较 4 周前上升）取 OR；溢价 <=5% 满仓、5-10% 半仓、>10% 空仓。
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"


def load_value(name: str) -> pd.Series:
    d = pd.read_csv(DATA / f"{name}.csv", parse_dates=["date"])
    return d.set_index("date")["value"].sort_index()


def load_price() -> pd.Series:
    d = pd.read_csv(DATA / "160723.csv", parse_dates=["date"])
    return d.set_index("date")["close"].sort_index()


def load_nav() -> pd.Series:
    d = pd.read_csv(DATA / "nav_160723.csv", parse_dates=["date"])
    return d.set_index("date")["nav"].sort_index()


def metrics(pnl: pd.Series, pos: pd.Series) -> dict:
    pnl = pnl.dropna()
    nav = (1 + pnl).cumprod()
    years = (pnl.index[-1] - pnl.index[0]).days / 365.25
    cagr = nav.iloc[-1] ** (1 / years) - 1
    vol = pnl.std() * np.sqrt(252)
    sharpe = pnl.mean() / pnl.std() * np.sqrt(252) if pnl.std() > 0 else np.nan
    mdd = (nav / nav.cummax() - 1).min()
    changes = pos.reindex(pnl.index).diff().abs().sum()
    return {
        "start": str(pnl.index[0].date()), "end": str(pnl.index[-1].date()),
        "n": int(len(pnl)), "cagr": float(cagr), "vol": float(vol),
        "sharpe": float(sharpe), "mdd": float(mdd),
        "calmar": float(cagr / abs(mdd)) if mdd < 0 else np.nan,
        "final": float(nav.iloc[-1]), "exposure": float(pos.reindex(pnl.index).mean()),
        "round_trips_per_year": float(changes / 2 / years) if years > 0 else np.nan,
    }


def run(cfg: dict) -> tuple[pd.DataFrame, dict]:
    wti = load_value("wti")
    gas = load_value("gasoline")
    ho = load_value("heating_oil")
    cushing = load_value("cushing")
    px = load_price().loc[cfg["start"]:cfg["end"]]
    nav = load_nav()

    d = pd.concat([wti.rename("wti"), gas.rename("gas"), ho.rename("ho")],
                  axis=1, sort=False).dropna()
    crack = (2 * d.gas * 42 + d.ho * 42 - 3 * d.wti) / 3

    cw = cfg["crack"]
    thr = crack.rolling(cw["window"], min_periods=cw["min_periods"]).median()
    crack_sig = (crack > thr).astype(float).where(thr.notna())

    uw = cfg["cushing"]
    roll = cushing.rolling(uw["weeks"]).mean()
    cush_sig = (roll - roll.shift(uw["diff_weeks"]) > 0).astype(float).where(roll.notna())

    f = crack_sig.reindex(px.index).ffill().shift(cfg["execution"]["crack_lag"])
    c = cush_sig.reindex(px.index).ffill().shift(uw["lag"])
    base = pd.concat([f, c], axis=1).max(axis=1).fillna(0.0)

    pw = cfg["premium"]
    prem = px / nav.reindex(px.index).ffill().shift(pw["nav_lag"]) - 1
    weight = pd.Series(1.0, index=px.index)
    weight[prem > pw["low"]] = pw["mid_weight"]
    weight[prem > pw["high"]] = pw["high_weight"]

    raw_pos = (base * weight).fillna(0.0)
    pos = raw_pos.shift(1).fillna(0.0)
    ret = px.pct_change()
    pnl = pos * ret - cfg["execution"]["fee"] * pos.diff().abs().fillna(pos.abs())

    bh = ret - cfg["execution"]["fee"] * pd.Series(1.0, index=px.index).diff().abs().fillna(1.0)
    out = pd.DataFrame({
        "date": px.index, "close": px.values, "crack_signal": f.values,
        "cushing_signal": c.values, "base_position": base.values,
        "premium": prem.values, "premium_weight": weight.values,
        "target_position": raw_pos.values, "held_position": pos.values,
        "ret": ret.values, "pnl": pnl.values, "nav": (1 + pnl).cumprod().values,
    })
    report = {
        "instrument": "160723 嘉实原油 LOF",
        "strategy": metrics(pnl, pos),
        "buy_hold": metrics(bh, pd.Series(1.0, index=px.index)),
        "config": cfg,
        "data": {"start": str(px.index.min().date()), "end": str(px.index.max().date())},
        "note": "Long-only, 3bp per position change; premium uses lagged NAV.",
    }
    return out, report


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--output", default="output")
    args = p.parse_args()
    cfg = json.loads((ROOT / "config.json").read_text())
    out, report = run(cfg)
    outdir = ROOT / args.output
    outdir.mkdir(parents=True, exist_ok=True)
    out.to_csv(outdir / "positions.csv", index=False)
    (outdir / "metrics.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=float) + "\n")

    nav = (1 + out.pnl).cumprod()
    bh = (1 + out.ret.fillna(0)).cumprod()
    fig, ax = plt.subplots(2, 1, figsize=(10, 7), sharex=True,
                           gridspec_kw={"height_ratios": [3, 1]})
    ax[0].plot(out.date, nav, label="Strategy")
    ax[0].plot(out.date, bh, label="Buy & hold", alpha=0.7)
    ax[0].set_title("160723 — crack + Cushing + premium tier")
    ax[0].legend()
    ax[0].grid(alpha=0.25)
    dd = nav / nav.cummax() - 1
    ax[1].fill_between(out.date, dd, 0, alpha=0.35)
    ax[1].set_ylabel("Drawdown")
    ax[1].grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(outdir / "nav.png", dpi=150)
    plt.close(fig)
    print(json.dumps(report, ensure_ascii=False, indent=2, default=float))


if __name__ == "__main__":
    main()
