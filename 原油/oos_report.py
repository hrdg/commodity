"""Train/OOS report for a fixed config."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

import strategy

ROOT = Path(__file__).resolve().parent


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--config", default="config_oos_9_3.json")
    p.add_argument("--output", default="output_oos_9_3")
    args = p.parse_args()
    cfg = json.loads((ROOT / args.config).read_text())
    out, _ = strategy.run(cfg)
    out = out.set_index("date")

    train = ("2017-05-05", "2021-12-31")
    oos = ("2022-01-01", "2026-10-30")

    def m(a: str, b: str) -> dict:
        return strategy.metrics(out.pnl.loc[a:b], out.held_position.loc[a:b])

    yearly = {str(y): float((1 + out.pnl.loc[f"{y}-01-01":f"{y}-12-31"]).prod() - 1)
              for y in range(2022, 2027)}
    threshold = "9/3" if cfg["premium"].get("reenter") == 0.03 else "10/5"
    proxy = cfg["premium"].get("nav_source") == "proxy_uso"
    note = (f"{threshold} threshold selected on 2017-2021 only; "
            "OOS 2022-2026 is not used for threshold selection. "
            + ("USO proxy NAV is an estimate; OOS is exploratory, not clean actual-NAV OOS."
               if proxy else "Actual NAV lag3; parameters frozen before the 2022-2026 holdout."))
    res = {
        "config": args.config,
        "train": m(*train),
        "oos": m(*oos),
        "full": m(cfg["start"], cfg["end"]),
        "buy_hold_oos": strategy.metrics(out.ret.loc[oos[0]:oos[1]],
                                         pd.Series(1.0, index=out.ret.loc[oos[0]:oos[1]].index)),
        "yearly_oos": yearly,
        "note": note,
    }
    outdir = ROOT / args.output
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "oos_metrics.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=2, default=float) + "\n")
    print(json.dumps(res, ensure_ascii=False, indent=2, default=float))


if __name__ == "__main__":
    main()
