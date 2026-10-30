"""Refresh the four EIA series used by the crude-oil strategy."""
from __future__ import annotations

import hashlib
import io
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
SERIES = {
    "wti": "RWTCd",
    "gasoline": "EER_EPMRU_PF4_RGC_DPGd",
    "heating_oil": "EER_EPD2F_PF4_Y35NY_DPGd",
    "cushing": "W_EPC0_SAX_YCUOK_MBBLw",
}


def fetch(series: str) -> pd.Series:
    url = f"https://www.eia.gov/dnav/pet/hist_xls/{series}.xls"
    raw = requests.get(url, timeout=40).content
    frame = pd.read_excel(io.BytesIO(raw), sheet_name="Data 1", header=None)
    frame = frame.iloc[:, :2]
    frame.columns = ["date", "value"]
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce", format="mixed")
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    frame = frame.dropna().drop_duplicates("date").sort_values("date")
    if frame.empty or not frame["date"].is_monotonic_increasing:
        raise ValueError(f"invalid EIA response for {series}")
    return frame.set_index("date")["value"]


def main() -> None:
    for name, series in SERIES.items():
        path = DATA / f"{name}.csv"
        old = pd.read_csv(path, parse_dates=["date"]).set_index("date")["value"]
        new = fetch(series)
        common = old.index.intersection(new.index)
        if common.empty or new.index.max() < old.index.max():
            raise ValueError(f"refresh would shrink {name}")
        changed = int(((new.reindex(common) - old.reindex(common)).abs() > 1e-9).sum())
        if name == "cushing" and (new.dropna() % 1 == 0).all():
            new = new.astype("int64")
        new.rename("value").rename_axis("date").to_csv(path)
        print(f"{name}: {new.index.min().date()} -> {new.index.max().date()}, rows={len(new)}, revised_overlap={changed}")

    manifest = DATA / "SHA256SUMS"
    lines = []
    for line in manifest.read_text().splitlines():
        expected, name = line.split(maxsplit=1)
        name = name.strip()
        digest = hashlib.sha256((DATA / name).read_bytes()).hexdigest()
        lines.append(f"{digest}  {name}")
    manifest.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
