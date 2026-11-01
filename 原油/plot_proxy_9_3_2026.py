"""Plot 2026 performance and holdings for the USO NAV-proxy 9/3 config."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

import strategy

ROOT = Path(__file__).resolve().parent


def main() -> None:
    cfg = json.loads((ROOT / "config_proxy_9_3.json").read_text())
    cfg["end"] = date.today().isoformat()
    out, _ = strategy.run(cfg)
    out = out.set_index("date").loc["2026-01-01":]
    if out.empty:
        raise RuntimeError("no 2026 observations")

    nav = (1 + out.pnl).cumprod()
    bh = (1 + out.ret.fillna(0)).cumprod()
    dd = nav / nav.cummax() - 1
    bdd = bh / bh.cummax() - 1
    total = float(nav.iloc[-1] - 1)
    bh_total = float(bh.iloc[-1] - 1)
    sharpe = strategy.metrics(out.pnl, out.held_position)["sharpe"]
    mdd = float(dd.min())
    signal = float(out.target_position.iloc[-1])
    premium = float(out.premium.iloc[-1])

    fig, ax = plt.subplots(3, 1, figsize=(11, 8.5), sharex=True,
                           gridspec_kw={"height_ratios": [3.2, 1.3, 0.8]})
    ax[0].plot(nav.index, nav, color="#176b5b", lw=1.8,
               label=f"USO proxy 9/3  {total * 100:+.1f}%")
    ax[0].plot(bh.index, bh, color="#b5651d", lw=1.3, alpha=0.8,
               label=f"Buy & hold 160723  {bh_total * 100:+.1f}%")
    ax[0].axvline(out.index[-1], color="0.45", ls="--", lw=1)
    ax[0].set_title("160723 crude-oil strategy | 2026 YTD")
    ax[0].set_ylabel("NAV (start = 1)")
    ax[0].legend(loc="upper left")
    ax[0].grid(alpha=0.22)
    ax[0].text(
        0.985, 0.96,
        f"as of {out.index[-1].date()}\n"
        f"YTD {total * 100:+.2f}% | Sharpe {sharpe:.2f} | MDD {mdd * 100:.2f}%\n"
        f"Next-session target: {signal * 100:.0f}%\n"
        f"Proxy premium: {premium * 100:+.2f}%",
        transform=ax[0].transAxes, va="top", ha="right", fontsize=9,
        bbox=dict(boxstyle="round,pad=0.4", fc="white", alpha=0.88, ec="0.8"),
    )

    ax[1].fill_between(dd.index, dd, 0, color="#b23a48", alpha=0.32)
    ax[1].plot(bdd.index, bdd, color="#b5651d", lw=1.0, alpha=0.65,
               label="Buy & hold")
    ax[1].set_ylabel("Drawdown")
    ax[1].yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    ax[1].legend(loc="lower left", fontsize=8)
    ax[1].grid(alpha=0.22)

    ax[2].fill_between(out.index, out.held_position, 0, step="post",
                       color="#176b5b", alpha=0.3)
    ax[2].step(out.index, out.held_position, where="post", color="#176b5b", lw=1.2)
    ax[2].set_ylim(-0.05, 1.08)
    ax[2].set_yticks([0, 1])
    ax[2].set_yticklabels(["Cash", "Long"])
    ax[2].set_ylabel("Position")
    ax[2].set_xlabel("Date")
    ax[2].grid(alpha=0.22)

    fig.tight_layout()
    path = ROOT / "output_proxy_9_3" / "ytd_2026.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=180)
    plt.close(fig)
    print(json.dumps({
        "path": str(path), "as_of": str(out.index[-1].date()),
        "ytd_return": total, "buy_hold_ytd": bh_total,
        "sharpe": sharpe, "mdd": mdd, "target_position": signal,
        "premium": premium,
    }, indent=2))


if __name__ == "__main__":
    main()
