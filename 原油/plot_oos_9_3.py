"""Plot 9/3 OOS strategy NAV vs buy-and-hold for 160723."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

import strategy

ROOT = Path(__file__).resolve().parent


def main() -> None:
    cfg = json.loads((ROOT / "config_oos_9_3.json").read_text())
    cfg["end"] = "2026-10-29"
    out, _ = strategy.run(cfg)
    out = out.set_index("date")
    nav = (1 + out.pnl).cumprod()
    bh = (1 + out.ret.fillna(0)).cumprod()

    def m(series: pd.Series, pos: pd.Series) -> dict:
        return strategy.metrics(series, pos)

    full = m(out.pnl, out.held_position)
    oos = m(out.pnl.loc["2022-01-01":], out.held_position.loc["2022-01-01":])
    bh_oos = m(out.ret.loc["2022-01-01":"2026-10-29"],
               pd.Series(1.0, index=out.ret.loc["2022-01-01":"2026-10-29"].index))

    fig, ax = plt.subplots(2, 1, figsize=(11, 8), sharex=True,
                           gridspec_kw={"height_ratios": [3, 1.2]})
    ax[0].plot(nav.index, nav, label="160723 strategy (9/3 hysteresis)", lw=1.6)
    ax[0].plot(bh.index, bh, label="Buy & hold 160723", lw=1.3, alpha=0.75)
    ax[0].axvline(pd.Timestamp("2022-01-01"), color="gray", ls="--", lw=1)
    ax[0].axvspan(pd.Timestamp("2022-01-01"), nav.index[-1], color="orange", alpha=0.06)
    ax[0].set_yscale("log")
    ax[0].set_title("160723 Jia Shi Crude Oil LOF — 9/3 OOS strategy vs buy & hold")
    ax[0].set_ylabel("NAV (log)")
    ax[0].legend(loc="upper left")
    ax[0].grid(alpha=0.25)
    ax[0].text(0.98, 0.96,
               f"Full: {full['cagr']*100:.1f}% CAGR / SR {full['sharpe']:.2f} / MDD {full['mdd']*100:.1f}%\n"
               f"OOS 2022-26: {oos['cagr']*100:.1f}% / SR {oos['sharpe']:.2f} / MDD {oos['mdd']*100:.1f}%\n"
               f"B&H OOS: {bh_oos['cagr']*100:.1f}% / SR {bh_oos['sharpe']:.2f} / MDD {bh_oos['mdd']*100:.1f}%",
               transform=ax[0].transAxes, va="top", ha="right", fontsize=8,
               bbox=dict(boxstyle="round,pad=0.3", fc="white", alpha=0.8, ec="0.8"))

    dds = nav / nav.cummax() - 1
    ddb = bh / bh.cummax() - 1
    ax[1].plot(dds.index, dds, label="Strategy", lw=1.2)
    ax[1].plot(ddb.index, ddb, label="Buy & hold", lw=1.0, alpha=0.7)
    ax[1].axvline(pd.Timestamp("2022-01-01"), color="gray", ls="--", lw=1)
    ax[1].fill_between(dds.index, dds, 0, alpha=0.2)
    ax[1].set_ylabel("Drawdown")
    ax[1].set_xlabel("Date")
    ax[1].legend(loc="lower left", fontsize=8)
    ax[1].grid(alpha=0.25)
    fig.tight_layout()
    outpath = ROOT / "output_oos_9_3" / "nav_vs_buy_hold.png"
    fig.savefig(outpath, dpi=180)
    plt.close(fig)
    print(outpath)


if __name__ == "__main__":
    main()
