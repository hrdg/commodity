"""Print the latest target position for a config."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import strategy

ROOT = Path(__file__).resolve().parent


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--config", required=True)
    p.add_argument("--asof", default="2026-10-29")
    p.add_argument("--output", default=None)
    args = p.parse_args()
    cfg = json.loads((ROOT / args.config).read_text())
    cfg["end"] = args.asof
    out, _ = strategy.run(cfg)
    last = out.iloc[-1]
    res = {
        "config": args.config,
        "asof": args.asof,
        "date": str(last.date.date()),
        "close": float(last.close),
        "crack_signal": float(last.crack_signal),
        "cushing_signal": float(last.cushing_signal),
        "base_position": float(last.base_position),
        "premium": float(last.premium),
        "premium_weight": float(last.premium_weight),
        "target_position": float(last.target_position),
        "held_position": float(last.held_position),
    }
    if args.output:
        pth = ROOT / args.output
        pth.parent.mkdir(parents=True, exist_ok=True)
        pth.write_text(json.dumps(res, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
