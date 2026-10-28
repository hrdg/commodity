"""Fetch subscription/redemption status history for 160723."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
URL = "https://api.fund.eastmoney.com/f10/lsjz"


def fetch_year(code: str, year: int) -> list[dict]:
    rows, page = [], 1
    while True:
        params = {"fundCode": code, "pageIndex": page, "pageSize": 20,
                  "startDate": f"{year}-01-01", "endDate": f"{year}-12-31"}
        r = requests.get(URL, params=params, timeout=30,
                         headers={"User-Agent": "Mozilla/5.0",
                                  "Referer": "https://fundf10.eastmoney.com/"})
        r.raise_for_status()
        batch = (r.json().get("Data") or {}).get("LSJZList", [])
        if not batch:
            break
        rows.extend(batch)
        if len(batch) < 20:
            break
        page += 1
        time.sleep(0.05)
    return rows


def main() -> None:
    rows = []
    for y in range(2017, 2027):
        rows.extend(fetch_year("160723", y))
    d = pd.DataFrame(rows)
    d["date"] = pd.to_datetime(d["FSRQ"])
    d = d[["date", "SGZT", "SHZT"]].drop_duplicates("date").sort_values("date")
    d.to_csv(DATA / "sgzt_160723.csv", index=False)
    print(json.dumps({"rows": len(d), "start": str(d.date.min().date()),
                      "end": str(d.date.max().date()),
                      "sgzt": d.SGZT.value_counts().to_dict()}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
