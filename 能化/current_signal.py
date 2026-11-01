"""Print the latest standalone 159981 signal."""
from __future__ import annotations

import json

import strategy


def main() -> None:
    cfg = strategy.load_config()
    px = strategy.load_prices()
    sig = strategy.make_signal(px, cfg["signal"])
    last = px.index[-1]
    print(json.dumps({
        "instrument": cfg["instrument"], "date": str(last.date()),
        "close": float(px.close.iloc[-1]),
        "close_20d_ago": float(px.close.shift(20).iloc[-1]),
        "signal": float(sig.iloc[-1]), "target_position": float(sig.fillna(0).iloc[-1]),
        "execution": cfg["execution"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
