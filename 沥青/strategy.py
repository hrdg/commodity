"""BU asphalt: long only when crack and BU-FU spread are both cheap."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import lab

RUN = Path(__file__).resolve().parent


def build(cfg: dict):
    bu = lab.load_main("BU0")
    fu = lab.load_main("FU0")
    brent = lab.load_series("brent", "value")
    fx = lab.load_series("usdcny", "usdcny")
    idx = bu.loc[cfg["start"]:cfg["end"]].index
    bx = bu.loc[idx]
    fu_i = fu.close.reindex(idx).ffill()
    brent_k = brent.reindex(idx).ffill().shift(1)
    fx_k = fx.reindex(idx).ffill()

    bu_adj = bx.close.iloc[0] * (1 + lab.adj_ret(bx.close, cfg["roll_cap"])).cumprod()
    fu_adj = fu_i.iloc[0] * (1 + lab.adj_ret(fu_i, cfg["roll_cap"])).cumprod()
    crack = bu_adj - brent_k * fx_k * 7.35
    spread = bu_adj - fu_adj
    cz = lab.robust_z(crack, cfg["window"])
    sz = lab.robust_z(spread, cfg["window"])
    signal = ((cz < cfg["threshold"]) & (sz < cfg["threshold"])).astype(float).where(cz.notna() & sz.notna(), 0.0)
    pnl, pos = lab.run(bx.close, signal, cfg["fee"])
    return bx, cz, sz, signal, pnl, pos


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--output", default="artifacts")
    args = p.parse_args()
    cfg = json.loads((RUN / "config.json").read_text())
    bx, cz, sz, signal, pnl, pos = build(cfg)
    full = lab.metrics(pnl, pos)
    train = lab.window(pnl, pos, cfg["start"], "2021-12-31")
    oos = lab.window(pnl, pos, "2022-01-01", cfg["end"])
    bh = lab.adj_ret(bx.close).loc[cfg["start"]:] - cfg["fee"] * pd.Series(1.0, index=bx.index).diff().abs().fillna(1.0)
    bh_full = lab.metrics(bh, pd.Series(1.0, index=bx.index))
    bh_oos = lab.window(bh, pd.Series(1.0, index=bx.index), "2022-01-01", cfg["end"])

    outdir = RUN / args.output
    outdir.mkdir(exist_ok=True)
    frame = pd.DataFrame({"date": bx.index, "bu_close": bx.close.values, "crack_z": cz.values,
                          "spread_z": sz.values, "signal": signal.values, "held_position": pos.values,
                          "ret": lab.adj_ret(bx.close, cfg["roll_cap"]).values, "pnl": pnl.values,
                          "nav": (1 + pnl).cumprod().values})
    frame.to_csv(outdir / "positions.csv", index=False)
    res = {"config": cfg, "full": full, "train": train, "oos": oos,
           "buy_hold_full": bh_full, "buy_hold_oos": bh_oos,
           "last": {"date": str(bx.index[-1].date()), "bu_close": float(bx.close.iloc[-1]),
                    "crack_z": float(cz.iloc[-1]), "spread_z": float(sz.iloc[-1]),
                    "signal_for_next_session": float(signal.iloc[-1])}}
    (outdir / "metrics.json").write_text(json.dumps(res, ensure_ascii=False, indent=2, default=float) + "\n")

    nav = (1 + pnl).cumprod(); bhnav = (1 + bh).cumprod()
    fig, ax = plt.subplots(2, 1, figsize=(10, 7), sharex=True, gridspec_kw={"height_ratios": [3, 1]})
    ax[0].plot(bx.index, nav, label="BU dual-cheap")
    ax[0].plot(bx.index, bhnav, label="Buy & hold", alpha=0.75)
    ax[0].set_title("BU asphalt — crack + BU-FU dual-cheap")
    ax[0].legend(); ax[0].grid(alpha=0.25)
    dd = nav / nav.cummax() - 1; ax[1].fill_between(bx.index, dd, 0, alpha=0.3)
    ax[1].set_ylabel("Drawdown"); ax[1].grid(alpha=0.25)
    fig.tight_layout(); fig.savefig(outdir / "nav.png", dpi=150); plt.close(fig)
    print(json.dumps(res, ensure_ascii=False, indent=2, default=float))


if __name__ == "__main__":
    main()
