"""Standalone long/cash research on the 159981 energy-chemical ETF."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
FEE = 0.0003

# Pre-registered candidate set.  All are price-only, causal trend rules.
CANDIDATES = {
    "sma20": ("sma", 20),
    "sma60": ("sma", 60),
    "sma120": ("sma", 120),
    "sma200": ("sma", 200),
    "mom20": ("mom", 20),
    "mom60": ("mom", 60),
    "mom120": ("mom", 120),
    "breakout20": ("breakout", 20),
    "breakout60": ("breakout", 60),
    "breakout120": ("breakout", 120),
    "cross20_60": ("cross", 20, 60),
    "cross50_200": ("cross", 50, 200),
}


def load_prices() -> pd.DataFrame:
    d = pd.read_csv(DATA / "159981.csv", parse_dates=["date"])
    d = d.set_index("date").sort_index()
    cols = ["open", "high", "low", "close", "volume", "amount"]
    d = d[cols].apply(pd.to_numeric, errors="coerce")
    d = d.dropna(subset=["open", "high", "low", "close"])
    if d.index.has_duplicates:
        raise ValueError("duplicate ETF dates")
    return d


def make_signal(px: pd.DataFrame, name: str) -> pd.Series:
    spec = CANDIDATES[name]
    close = px["close"]
    if spec[0] == "sma":
        n = spec[1]
        out = (close > close.rolling(n).mean()).astype(float)
        return out.where(close.rolling(n).mean().notna())
    if spec[0] == "mom":
        n = spec[1]
        return (close > close.shift(n)).astype(float).where(close.shift(n).notna())
    if spec[0] == "breakout":
        n = spec[1]
        prior_high = px["high"].rolling(n).max().shift(1)
        return (close > prior_high).astype(float).where(prior_high.notna())
    if spec[0] == "cross":
        fast, slow = spec[1], spec[2]
        fs, ss = close.rolling(fast).mean(), close.rolling(slow).mean()
        return (fs > ss).astype(float).where(ss.notna())
    raise KeyError(name)


def backtest(px: pd.DataFrame, target: pd.Series, fee: float = FEE) -> tuple[pd.Series, pd.Series]:
    """Close signal t, trade at open t+1; costs charged on the open turnover."""
    target = target.reindex(px.index).fillna(0.0).clip(0.0, 1.0)
    new_pos = target.shift(1).fillna(0.0)  # held after today's open
    old_pos = target.shift(2).fillna(0.0)  # held before today's open
    overnight = (px["open"] / px["close"].shift(1) - 1).fillna(0.0)
    intraday = px["close"] / px["open"] - 1
    gross = (1 + old_pos * overnight) * (1 + new_pos * intraday) - 1
    pnl = gross - fee * (new_pos - old_pos).abs()
    return pnl, new_pos


def _window(x: pd.Series, start: str | None, end: str | None) -> pd.Series:
    return x.loc[start:end] if start or end else x


def metrics(pnl: pd.Series, pos: pd.Series, start: str | None = None,
            end: str | None = None) -> dict:
    pnl = _window(pnl, start, end).dropna()
    pos = _window(pos, start, end).reindex(pnl.index)
    if pnl.empty:
        return {}
    nav = (1 + pnl).cumprod()
    nav = pd.concat([pd.Series([1.0], index=[nav.index[0] - pd.Timedelta(days=1)]), nav])
    years = (pnl.index[-1] - pnl.index[0]).days / 365.25
    cagr = float(nav.iloc[-1] ** (1 / years) - 1) if years > 0 else np.nan
    vol = float(pnl.std(ddof=1) * np.sqrt(252))
    sharpe = float(pnl.mean() / pnl.std(ddof=1) * np.sqrt(252)) if pnl.std(ddof=1) > 0 else np.nan
    mdd = float((nav / nav.cummax() - 1).min())
    turns = float(pos.diff().abs().sum())
    return {
        "start": str(pnl.index[0].date()), "end": str(pnl.index[-1].date()),
        "n": int(len(pnl)), "total": float(nav.iloc[-1] - 1), "cagr": cagr,
        "vol": vol, "sharpe": sharpe, "mdd": mdd,
        "calmar": float(cagr / abs(mdd)) if mdd < 0 else np.nan,
        "exposure": float(pos.mean()), "turnover": turns,
        "round_trips": turns / 2,
    }


def yearly_returns(pnl: pd.Series, start: str, end: str) -> dict[str, float]:
    s = pnl.loc[start:end]
    out = {}
    for year, g in s.groupby(s.index.year):
        out[str(year)] = float((1 + g).prod() - 1)
    return out


def load_config() -> dict:
    return json.loads((ROOT / "config.json").read_text())
