"""PIT-safe NAV nowcast using lagged NAV + known USO returns."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

import strategy

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
FEE = 0.0003


def series(name: str, col: str) -> pd.Series:
    d = pd.read_csv(DATA / f"{name}.csv", parse_dates=["date"])
    return d.set_index("date")[col].sort_index()


def hyst(prem: pd.Series, block: float, reenter: float) -> pd.Series:
    state, out = 1.0, []
    for p in prem.fillna(0):
        if p > block:
            state = 0.0
        elif p < reenter:
            state = 1.0
        out.append(state)
    return pd.Series(out, index=prem.index)


def main() -> None:
    px = series("160723", "close").loc["2017-05-05":]
    nav = series("nav_160723", "nav")
    uso = series("uso", "close")
    u = uso.pct_change().reindex(px.index).ffill().shift(1)  # known at China close t
    nav_base = nav.reindex(px.index).ffill().shift(3)        # disclosed by t-1 at latest
    nav_proxy = nav_base * (1 + u.shift(1)) * (1 + u)
    prem = px / nav_proxy - 1

    wti = series("wti", "value")
    w = wti.pct_change().reindex(px.index).ffill().shift(1)
    w_proxy = nav_base * (1 + w.shift(1)) * (1 + w)
    w_prem = px / w_proxy - 1

    # Base signal from the frozen strategy inputs.
    out, _ = strategy.run(json.loads((ROOT / "config_oos_9_3.json").read_text()))
    base = out.set_index("date")["base_position"].reindex(px.index).fillna(0)

    def run(p: pd.Series, b: float, r: float) -> dict:
        pos = base * hyst(p, b, r)
        pnl = pos.shift(1).fillna(0) * px.pct_change() - FEE * pos.diff().abs().fillna(pos.abs())
        f = strategy.metrics(pnl, pos)
        o = strategy.metrics(pnl.loc["2022-01-01":"2026-10-27"], pos.loc["2022-01-01":"2026-10-27"])
        return {"full": {k: f[k] for k in ("cagr", "sharpe", "calmar", "mdd")},
                "oos": {k: o[k] for k in ("cagr", "sharpe", "calmar", "mdd")}}

    err = nav_proxy / nav.reindex(px.index).ffill().shift(1) - 1
    w_err = w_proxy / nav.reindex(px.index).ffill().shift(1) - 1
    res = {
        "nav_proxy_uso": {"10/5": run(prem, 0.10, 0.05), "9/3": run(prem, 0.09, 0.03)},
        "nav_proxy_wti": {"10/5": run(w_prem, 0.10, 0.05), "9/3": run(w_prem, 0.09, 0.03)},
        "proxy_error_vs_lag1": {"uso_mae": float(err.abs().mean()), "uso_corr": float(nav_proxy.pct_change().corr(nav.reindex(px.index).pct_change())),
                                "wti_mae": float(w_err.abs().mean()), "wti_corr": float(w_proxy.pct_change().corr(nav.reindex(px.index).pct_change()))},
        "last": {"date": str(px.index[-1].date()), "price": float(px.iloc[-1]),
                 "nav_proxy": float(nav_proxy.iloc[-1]), "premium_proxy": float(prem.iloc[-1])},
        "note": "USO return is shifted one session; NAV base is lag3; no future US close used.",
    }
    (ROOT / "output" / "nav_proxy.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=2, default=float) + "\n")
    print(json.dumps(res, ensure_ascii=False, indent=2, default=float))


if __name__ == "__main__":
    main()
