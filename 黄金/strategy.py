#!/usr/bin/env python3
"""Reproduce the frozen gold monthly six-vote M1 and M1+VOL15 strategies.

The committed daily panel contains the executable monthly target and the
next-session 63-day volatility scale. Targets are interpreted as executable at
the SGE close on the row date. Daily overlay signals were shifted before export;
the monthly target already uses its frozen parent execution date.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
DEFAULT_PANEL = HERE / "data/gold_daily_panel.csv.gz"
DEFAULT_OUTPUT = HERE / "output"
STRATEGIES = ("M1", "M1_VOL15")
COSTS_BP = (10, 20)
WINDOWS = {
    "full_2017": ("2017-01-03", "2026-11-20"),
    "2018_2025": ("2018-01-01", "2025-12-31"),
    "recent_2021": ("2021-01-01", "2026-11-20"),
    "recent_2024": ("2024-01-01", "2026-11-20"),
    "2026": ("2026-01-05", "2026-11-20"),
}


def load_panel(path: Path = DEFAULT_PANEL) -> pd.DataFrame:
    frame = pd.read_csv(path, parse_dates=["date"])
    required = {
        "date",
        "close",
        "monthly_m1_target",
        "vol15_scale",
    }
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"panel missing columns: {sorted(missing)}")
    frame = frame.sort_values("date").drop_duplicates("date", keep="last")
    if frame["date"].duplicated().any():
        raise ValueError("panel contains duplicate dates")
    if (~np.isfinite(frame["close"])).any() or (frame["close"] <= 0).any():
        raise ValueError("close must be finite and positive")
    for column in ("monthly_m1_target", "vol15_scale"):
        if frame[column].isna().any():
            raise ValueError(f"{column} contains missing values")
        if ((frame[column] < 0) | (frame[column] > 1)).any():
            raise ValueError(f"{column} must be within [0, 1]")
    return frame.set_index("date")


def strategy_targets(panel: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "M1": panel["monthly_m1_target"].clip(0.0, 1.0),
            "M1_VOL15": (
                panel["monthly_m1_target"] * panel["vol15_scale"]
            ).clip(0.0, 1.0),
        },
        index=panel.index,
    )


def simulate(
    price: pd.Series,
    target: pd.Series,
    fee_bp: int = 10,
) -> pd.DataFrame:
    """Simulate a self-financing long-only target at each close."""
    target = target.reindex(price.index).clip(0.0, 1.0)
    if target.isna().any():
        raise ValueError("target contains missing values")
    fee_rate = fee_bp / 10000.0
    nav = cash = 1.0
    units = 0.0
    prior_target: float | None = None
    rows = []
    for date, price_t in price.items():
        old_nav = nav
        nav = cash + units * float(price_t)
        desired = float(target.loc[date])
        fee = trade = 0.0
        if prior_target is None or abs(desired - prior_target) > 1e-12:
            current = units * float(price_t)
            fee = (
                fee_rate
                * abs(desired * nav - current)
                / (
                    1 + fee_rate * desired
                    if desired * nav >= current
                    else 1 - fee_rate * desired
                )
            )
            nav -= fee
            trade = abs(desired * nav - current)
            units = desired * nav / float(price_t)
            cash = nav - units * float(price_t)
            prior_target = desired
        if min(nav, cash, units) < -1e-8:
            raise AssertionError(f"accounting bound failed at {date}")
        exposure = units * float(price_t) / nav if nav else 0.0
        if exposure > 1 + 1e-8:
            raise AssertionError(f"exposure bound failed at {date}")
        rows.append(
            {
                "date": date,
                "close": float(price_t),
                "target": desired,
                "units": units,
                "cash": cash,
                "nav": nav,
                "ret": nav / old_nav - 1.0,
                "trade_notional": trade,
                "turnover_fraction": trade / (nav + fee),
                "fee": fee,
                "exposure": exposure,
            }
        )
    return pd.DataFrame(rows).set_index("date")


def performance(
    ledger: pd.DataFrame,
    start: str,
    end: str,
) -> dict:
    frame = ledger.loc[start:end].copy()
    if frame.empty:
        raise ValueError(f"empty performance window {start}..{end}")
    nav = frame["nav"] / float(frame["nav"].iloc[0])
    ret = nav.pct_change().fillna(0.0)
    years = len(frame) / 252.0
    cagr = float(nav.iloc[-1] ** (1.0 / years) - 1.0)
    drawdown = nav / np.maximum.accumulate(
        np.r_[1.0, nav.to_numpy(dtype=float)]
    )[1:] - 1.0
    downside = ret.where(ret < 0.0, 0.0).std(ddof=1) * np.sqrt(252.0)
    return {
        "start": str(frame.index[0].date()),
        "end": str(frame.index[-1].date()),
        "days": int(len(frame)),
        "cagr": cagr,
        "sharpe": float(
            ret.mean() / ret.std(ddof=1) * np.sqrt(252.0)
        ),
        "sortino": float(ret.mean() * 252.0 / downside),
        "max_drawdown": float(drawdown.min()),
        "calmar": cagr / abs(float(drawdown.min())),
        "annual_turnover": float(
            frame["turnover_fraction"].sum() / years
        ),
        "mean_exposure": float(frame["exposure"].mean()),
        "target_changes": int(frame["target"].diff().abs().gt(1e-12).sum()),
    }


def run_all(
    panel: pd.DataFrame,
) -> tuple[dict[tuple[str, int], pd.DataFrame], pd.DataFrame]:
    targets = strategy_targets(panel)
    ledgers = {}
    rows = []
    for name in STRATEGIES:
        for fee_bp in COSTS_BP:
            ledger = simulate(panel["close"], targets[name], fee_bp)
            ledgers[(name, fee_bp)] = ledger
            for window, (start, end) in WINDOWS.items():
                rows.append(
                    {
                        "strategy": name,
                        "fee_bp": fee_bp,
                        "window": window,
                        **performance(ledger, start, end),
                    }
                )
    return ledgers, pd.DataFrame(rows)


def write_outputs(
    panel: pd.DataFrame,
    ledgers: dict[tuple[str, int], pd.DataFrame],
    metrics: pd.DataFrame,
    output: Path,
) -> None:
    output.mkdir(parents=True, exist_ok=True)
    metrics.to_csv(output / "metrics.csv", index=False)

    nav = pd.DataFrame(
        {
            name: ledgers[(name, 10)]["nav"]
            for name in STRATEGIES
        }
    ).loc["2017-01-03":]
    nav = nav / nav.iloc[0]
    nav.to_csv(output / "nav.csv")

    positions = pd.concat(
        [
            ledgers[(name, 10)]
            .loc["2017-01-03":, ["target", "exposure", "nav"]]
            .assign(strategy=name)
            for name in STRATEGIES
        ]
    ).reset_index()
    positions.to_csv(output / "positions.csv", index=False)

    summary = {
        "asof": str(panel.index.max().date()),
        "strategies": {
            name: {
                "target": float(strategy_targets(panel)[name].iloc[-1]),
                "monthly_m1_target": float(
                    panel["monthly_m1_target"].iloc[-1]
                ),
                "vol15_scale": float(panel["vol15_scale"].iloc[-1]),
            }
            for name in STRATEGIES
        },
        "primary_cost_bp": 10,
        "future_profitability": "NOT_ASSESSED",
    }
    (output / "current_signal.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output / "metrics.json").write_text(
        json.dumps(
            metrics.to_dict(orient="records"),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    drawdown = nav / nav.cummax() - 1.0
    fig, axes = plt.subplots(
        2,
        1,
        figsize=(14, 8),
        gridspec_kw={"height_ratios": [2.0, 1.0]},
        constrained_layout=True,
    )
    for name in STRATEGIES:
        axes[0].plot(nav.index, nav[name], label=name, linewidth=1.5)
        axes[1].plot(drawdown.index, drawdown[name], label=name, linewidth=1.2)
    axes[0].set_title("Gold M1 vs M1 + 15% volatility target (10 bp)")
    axes[0].set_ylabel("Normalized NAV")
    axes[1].set_ylabel("Drawdown")
    axes[0].legend(loc="upper left")
    for axis in axes:
        axis.grid(alpha=0.22)
    fig.savefig(output / "gold_m1_vol15.png", dpi=180)
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", type=Path, default=DEFAULT_PANEL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    panel = load_panel(args.panel)
    ledgers, metrics = run_all(panel)
    write_outputs(panel, ledgers, metrics, args.output)
    print(
        metrics.loc[
            metrics["window"].eq("full_2017")
            & metrics["fee_bp"].eq(10)
        ].to_string(index=False)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
