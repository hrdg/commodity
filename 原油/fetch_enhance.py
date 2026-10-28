"""Fetch additional QDII carriers and DXY for enhancement tests."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import requests
import akshare as ak

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"


def nav(code: str) -> pd.DataFrame:
    url = "https://stock.finance.sina.com.cn/fundInfo/api/openapi.php/CaihuiFundInfoService.getNav"
    params = {"symbol": code, "datefrom": "2015-01-01", "dateto": "2026-10-28", "page": 1, "num": 10000}
    r = requests.get(url, params=params, timeout=40)
    rows = r.json()["result"]["data"]["data"]
    d = pd.DataFrame(rows)
    d["date"] = pd.to_datetime(d["fbrq"])
    d["nav"] = pd.to_numeric(d["jjjz"], errors="coerce")
    d = d[["date", "nav"]].dropna().drop_duplicates("date").sort_values("date")
    d.to_csv(DATA / f"nav_{code}.csv", index=False)
    return d


def main() -> None:
    meta = {}
    for code, sym in (("501018", "sh501018"), ("161129", "sz161129"), ("160216", "sz160216")):
        d = ak.fund_etf_hist_sina(symbol=sym)
        d["date"] = pd.to_datetime(d["date"])
        d = d.dropna(subset=["close"]).sort_values("date")
        d.to_csv(DATA / f"{code}.csv", index=False)
        n = nav(code)
        meta[code] = {"price_rows": len(d), "nav_rows": len(n),
                      "price_start": str(d.date.min().date()), "price_end": str(d.date.max().date())}
    r = requests.get("https://fred.stlouisfed.org/graph/fredgraph.csv?id=DTWEXBGS", timeout=40)
    dxy = pd.read_csv(pd.io.common.StringIO(r.text))
    dxy.columns = ["date", "value"]
    dxy["date"] = pd.to_datetime(dxy["date"])
    dxy["value"] = pd.to_numeric(dxy["value"], errors="coerce")
    dxy = dxy.dropna().sort_values("date")
    dxy.to_csv(DATA / "dxy.csv", index=False)
    meta["dxy"] = {"rows": len(dxy), "start": str(dxy.date.min().date()), "end": str(dxy.date.max().date())}
    (DATA / "enhance_manifest.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(meta, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
