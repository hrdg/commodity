"""Single-factor and composite checks for the frozen BU dual-cheap strategy."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

import lab

RUN = Path(__file__).resolve().parent


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--output", default="output")
    args = p.parse_args()
    cfg = json.loads((RUN / "config.json").read_text())

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
    valid = cz.notna() & sz.notna()
    crack_low = (cz < cfg["threshold"]).astype(float).where(valid, 0.0)
    spread_low = (sz < cfg["threshold"]).astype(float).where(valid, 0.0)
    ma20, ma60 = bx.close.rolling(20).mean(), bx.close.rolling(60).mean()
    bu_ma = ((ma20 > ma60) & (bx.close.pct_change(20) > 0)).astype(float)
    tsmom = pd.Series(
        np.mean([np.sign(bx.close / bx.close.shift(w) - 1) for w in (21, 63, 126, 252)], axis=0),
        index=idx,
    ).clip(lower=0).fillna(0)
    season = pd.Series(bx.index.month.isin([3, 4, 5, 9, 10]).astype(float), index=idx)

    signals = {
        "buy_hold": pd.Series(1.0, index=idx),
        "bu_ma20_60": bu_ma,
        "bu_tsmom_long": tsmom,
        "season": season,
        "crack_low": crack_low,
        "bu_fu_spread_low": spread_low,
        "crack_and_spread": crack_low * spread_low,
        "crack_spread_score": (crack_low + spread_low) / 2,
    }
    rows = []
    for name, sig in signals.items():
        pnl, pos = lab.run(bx.close, sig, cfg["fee"])
        full = lab.metrics(pnl, pos)
        train = lab.window(pnl, pos, cfg["start"], "2021-12-31")
        oos = lab.window(pnl, pos, "2022-01-01", cfg["end"])
        rows.append({
            "name": name,
            "full_cagr": full["cagr"], "full_sharpe": full["sharpe"],
            "full_calmar": full["calmar"], "full_mdd": full["mdd"], "full_expo": full["exposure"],
            "train_cagr": train["cagr"], "train_sharpe": train["sharpe"], "train_calmar": train["calmar"],
            "oos_cagr": oos["cagr"], "oos_sharpe": oos["sharpe"],
            "oos_calmar": oos["calmar"], "oos_mdd": oos["mdd"], "oos_expo": oos["exposure"],
        })

    table = pd.DataFrame(rows)
    out = RUN / args.output
    out.mkdir(exist_ok=True)
    table.to_csv(out / "factor_results.csv", index=False)
    (out / "factor_results.json").write_text(
        json.dumps(table.to_dict("records"), ensure_ascii=False, indent=2, default=float) + "\n"
    )
    print(table.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
