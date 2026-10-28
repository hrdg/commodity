"""Fetch Brent spot for Brent-WTI carrier tests."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"


def main() -> None:
    r = requests.get("https://fred.stlouisfed.org/graph/fredgraph.csv?id=DCOILBRENTEU", timeout=40)
    r.raise_for_status()
    d = pd.read_csv(pd.io.common.StringIO(r.text))
    d.columns = ["date", "value"]
    d["date"] = pd.to_datetime(d["date"])
    d["value"] = pd.to_numeric(d["value"], errors="coerce")
    d = d.dropna().sort_values("date")
    d.to_csv(DATA / "brent.csv", index=False)
    print({"rows": len(d), "start": str(d.date.min().date()), "end": str(d.date.max().date())})


if __name__ == "__main__":
    main()
