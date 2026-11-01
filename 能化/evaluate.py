"""Frozen train/OOS evaluation and chart for the standalone 159981 strategy."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import strategy

ROOT = Path(__file__).resolve().parent


def block_bootstrap_mean_diff(pnl: pd.Series, bh_pnl: pd.Series, start: str, end: str,
                              block: int = 20, draws: int = 5000) -> dict:
    d = (pnl - bh_pnl).loc[start:end].dropna().to_numpy()
    rng = np.random.default_rng(20261030)
    n = len(d)
    means = []
    for _ in range(draws):
        sample = []
        while len(sample) < n:
            i = int(rng.integers(0, n))
            sample.extend(d[(np.arange(i, i + block) % n)])
        means.append(float(np.mean(sample[:n])))
    means = np.asarray(means)
    return {
        "annualized_mean_difference": float(d.mean() * 252),
        "ci95_annualized": [float(x * 252) for x in np.quantile(means, [0.025, 0.975])],
        "prob_mean_le_zero": float((means <= 0).mean()),
        "block_days": block, "draws": draws, "seed": 20261030,
    }


def main() -> None:
    cfg = strategy.load_config()
    px = strategy.load_prices().loc[:cfg["oos_end"]]
    sig = strategy.make_signal(px, cfg["signal"])
    pnl, pos = strategy.backtest(px, sig, cfg["fee"])
    bh_pnl, bh_pos = strategy.backtest(px, pd.Series(1.0, index=px.index), cfg["fee"])

    train = strategy.metrics(pnl, pos, cfg["train_start"], cfg["train_end"])
    oos = strategy.metrics(pnl, pos, cfg["oos_start"], cfg["oos_end"])
    full = strategy.metrics(pnl, pos, cfg["train_start"], cfg["oos_end"])
    bh_oos = strategy.metrics(bh_pnl, bh_pos, cfg["oos_start"], cfg["oos_end"])
    result = {
        "config": cfg, "train": train, "oos": oos, "full": full,
        "buy_hold_oos": bh_oos,
        "yearly_oos": strategy.yearly_returns(pnl, cfg["oos_start"], cfg["oos_end"]),
        "buy_hold_yearly_oos": strategy.yearly_returns(bh_pnl, cfg["oos_start"], cfg["oos_end"]),
        "bootstrap_difference": block_bootstrap_mean_diff(pnl, bh_pnl, cfg["oos_start"], cfg["oos_end"]),
        "note": "mom20 selected only on 2020-11-19..2021-12-31 with >=6 round trips; OOS evaluated once after freezing.",
    }
    outdir = ROOT / "output"
    outdir.mkdir(exist_ok=True)
    diag = []
    for name in strategy.CANDIDATES:
        s = strategy.make_signal(px, name)
        p, q = strategy.backtest(px, s, cfg["fee"])
        m = strategy.metrics(p, q, cfg["oos_start"], cfg["oos_end"])
        diag.append({"candidate": name, "selected": name == cfg["signal"],
                     "total": m["total"], "cagr": m["cagr"], "sharpe": m["sharpe"],
                     "calmar": m["calmar"], "mdd": m["mdd"], "exposure": m["exposure"],
                     "round_trips": m["round_trips"]})
    pd.DataFrame(diag).sort_values("sharpe", ascending=False).to_csv(
        outdir / "oos_candidates_diagnostic.csv", index=False)
    (outdir / "metrics.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, default=float) + "\n")
    frame = pd.DataFrame({"close": px.close, "signal": sig, "target": sig.fillna(0),
                          "held_position": pos, "pnl": pnl,
                          "nav": (1 + pnl).cumprod()}).reset_index()
    frame.to_csv(outdir / "positions.csv", index=False)

    o = pnl.loc[cfg["oos_start"]:cfg["oos_end"]]
    nav = (1 + o).cumprod()
    nav = pd.concat([pd.Series([1.0], index=[nav.index[0] - pd.Timedelta(days=1)]), nav])
    b = bh_pnl.loc[cfg["oos_start"]:cfg["oos_end"]]
    bnav = (1 + b).cumprod()
    bnav = pd.concat([pd.Series([1.0], index=[bnav.index[0] - pd.Timedelta(days=1)]), bnav])
    p = pos.loc[cfg["oos_start"]:cfg["oos_end"]]

    fig, ax = plt.subplots(3, 1, figsize=(11, 8.5), sharex=True,
                           gridspec_kw={"height_ratios": [3.1, 1.2, 0.7]})
    ax[0].plot(nav.index, nav, color="#176b5b", lw=1.7,
               label=f"159981 mom20  {oos['total'] * 100:+.1f}%")
    ax[0].plot(bnav.index, bnav, color="#b5651d", lw=1.2, alpha=0.8,
               label=f"Buy & hold  {bh_oos['total'] * 100:+.1f}%")
    ax[0].set_title("159981 energy-chemical ETF | frozen OOS 2022-2026")
    ax[0].set_ylabel("NAV")
    ax[0].legend(loc="upper left")
    ax[0].grid(alpha=0.22)
    ax[0].text(0.985, 0.96,
               f"OOS {cfg['oos_start']} to {cfg['oos_end']}\n"
               f"CAGR {oos['cagr'] * 100:.1f}% | Sharpe {oos['sharpe']:.2f} | Calmar {oos['calmar']:.2f}\n"
               f"MDD {oos['mdd'] * 100:.1f}% | Exposure {oos['exposure'] * 100:.0f}%",
               transform=ax[0].transAxes, va="top", ha="right", fontsize=9,
               bbox=dict(boxstyle="round,pad=0.4", fc="white", alpha=0.88, ec="0.8"))
    dd = nav / nav.cummax() - 1
    bdd = bnav / bnav.cummax() - 1
    ax[1].fill_between(dd.index, dd, 0, color="#b23a48", alpha=0.3)
    ax[1].plot(bdd.index, bdd, color="#b5651d", alpha=0.6, lw=1, label="Buy & hold")
    ax[1].set_ylabel("Drawdown")
    ax[1].yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    ax[1].legend(loc="lower left", fontsize=8)
    ax[1].grid(alpha=0.22)
    ax[2].step(p.index, p, where="post", color="#176b5b", lw=1.1)
    ax[2].fill_between(p.index, p, 0, step="post", color="#176b5b", alpha=0.25)
    ax[2].set_ylim(-0.05, 1.08)
    ax[2].set_yticks([0, 1])
    ax[2].set_yticklabels(["Cash", "Long"])
    ax[2].set_ylabel("Position")
    ax[2].set_xlabel("Date")
    ax[2].grid(alpha=0.22)
    fig.tight_layout()
    outpath = outdir / "oos_nav.png"
    fig.savefig(outpath, dpi=180)
    plt.close(fig)
    print(json.dumps({k: result[k] for k in ["train", "oos", "buy_hold_oos", "yearly_oos"]},
                     ensure_ascii=False, indent=2, default=float))
    print(outpath)


if __name__ == "__main__":
    main()
