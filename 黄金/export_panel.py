#!/usr/bin/env python3
"""Regenerate the frozen daily panel from the audited research run.

This helper is only needed on the research workstation where the source run and
raw macro data exist. Normal users can run strategy.py against the committed
gold_daily_panel.csv.gz without either dependency.
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

import pandas as pd

DEFAULT_RUN = Path(
    "/Users/hsh/Documents/Quant/科技轮动/"
    "research/runs/gold_monthly_confirm3_20261123"
)
DEFAULT_OUTPUT = Path(__file__).resolve().parent / "data/gold_daily_panel.csv.gz"


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    run = load_module(args.run_dir / "run.py", "gold_confirm3_export")
    loaded = run.load_inputs()
    price, dxy, tips, spdr, cpi_std, cpi_release, ism, cftc = loaded
    daily = run.build_daily_votes(
        price, dxy, tips, spdr, cpi_std, cpi_release, ism, cftc
    )
    source_signals = pd.read_csv(run.PIT_RUN / "signals.csv")
    monthly_target, _ = run.target_from_source_signals(
        price, source_signals, "monthly"
    )
    vol15 = run.realized_vol_scale(price)

    panel = daily.join(
        pd.DataFrame(
            {
                "close": price,
                "monthly_m1_target": monthly_target,
                "vol15_scale": vol15,
            }
        ),
        how="left",
    )
    panel = panel.reset_index().rename(columns={"decision_date": "date"})
    panel["date"] = pd.to_datetime(panel["date"]).dt.strftime("%Y-%m-%d")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    panel.to_csv(
        args.output,
        index=False,
        compression={"method": "gzip", "mtime": 0},
    )
    print(
        f"wrote {args.output}: {len(panel)} rows, "
        f"{panel['date'].iloc[0]}..{panel['date'].iloc[-1]}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
