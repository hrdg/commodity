"""Asphalt BU timing helpers."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

RUN = Path(__file__).resolve().parent
DATA = RUN / "data"
FEE = 0.0003


def load_main(sym: str) -> pd.DataFrame:
    d = pd.read_csv(DATA / f"{sym}.csv", parse_dates=["date"])
    return d.drop_duplicates("date").sort_values("date").set_index("date")


def load_series(name: str, col: str) -> pd.Series:
    d = pd.read_csv(DATA / f"{name}.csv", parse_dates=["date"])
    d = d.rename(columns={"observation_date": "date"})
    return d.set_index("date")[col].sort_index()


def adj_ret(px: pd.Series, cap: float = 0.035) -> pd.Series:
    """Clip main-continuous roll gaps; BU/FU exchange limit is +/-3%."""
    return px.pct_change().clip(-cap, cap).fillna(0.0)


def robust_z(x: pd.Series, window: int = 252, minp: int = 126) -> pd.Series:
    med = x.rolling(window, min_periods=minp).median()
    mad = (x - med).abs().rolling(window, min_periods=minp).median()
    return (x - med) / (1.4826 * mad).replace(0, np.nan)


def metrics(pnl: pd.Series, pos: pd.Series) -> dict:
    pnl = pnl.dropna()
    nav = (1 + pnl).cumprod()
    years = (pnl.index[-1] - pnl.index[0]).days / 365.25
    cagr = nav.iloc[-1] ** (1 / years) - 1 if years > 0 else np.nan
    vol = pnl.std() * np.sqrt(252)
    sharpe = pnl.mean() / pnl.std() * np.sqrt(252) if pnl.std() > 0 else np.nan
    dd = (nav / nav.cummax() - 1).min()
    return {"cagr": float(cagr), "vol": float(vol), "sharpe": float(sharpe),
            "mdd": float(dd), "calmar": float(cagr / abs(dd)) if dd < 0 else np.nan,
            "exposure": float(pos.reindex(pnl.index).mean()),
            "final": float(nav.iloc[-1]), "n": int(len(pnl))}


def run(px: pd.Series, signal: pd.Series, fee: float = FEE) -> tuple[pd.Series, pd.Series]:
    ret = adj_ret(px)
    pos = signal.reindex(px.index).fillna(0).shift(1).fillna(0)
    pnl = pos * ret - fee * pos.diff().abs().fillna(pos.abs())
    return pnl, pos


def window(pnl: pd.Series, pos: pd.Series, a: str, b: str) -> dict:
    return metrics(pnl.loc[a:b], pos.loc[a:b])
