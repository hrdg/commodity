"""Train-only candidate screen for the standalone 159981 strategy."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

import strategy

ROOT = Path(__file__).resolve().parent
TRAIN_END = "2021-12-31"


def main() -> None:
    px = strategy.load_prices().loc[:TRAIN_END]
    signals = {name: strategy.make_signal(px, name) for name in strategy.CANDIDATES}
    common_start = max(s.first_valid_index() for s in signals.values())
    # Allow two observations for the close -> next-open execution lag.
    common_start = px.index[px.index.get_loc(common_start) + 2]
    rows = []
    for name, sig in signals.items():
        pnl, pos = strategy.backtest(px, sig)
        m = strategy.metrics(pnl, pos, str(common_start.date()), TRAIN_END)
        rows.append({"candidate": name, **m})
    out = pd.DataFrame(rows).sort_values(["sharpe", "calmar"], ascending=False)
    outdir = ROOT / "output"
    outdir.mkdir(exist_ok=True)
    out.to_csv(outdir / "train_candidates.csv", index=False)
    (outdir / "train_selection.json").write_text(json.dumps({
        "train_start": str(common_start.date()), "train_end": TRAIN_END,
        "selection": "highest training Sharpe; min 6 round trips; tie-break Calmar",
        "candidates": out.to_dict("records"),
    }, ensure_ascii=False, indent=2, default=float) + "\n")
    print(out[["candidate", "start", "end", "total", "sharpe", "calmar", "mdd", "exposure", "round_trips"]].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
