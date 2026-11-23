"""Test absolute+relative dual-momentum filters on the R3 commodity panel."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


RUN = Path(__file__).resolve().parents[1]
R3 = Path(
    "/Users/hsh/Documents/Quant/科技轮动/research/runs/"
    "aw7_commodity_contract_xsection_20261123"
)
PANEL = R3 / "artifacts/panel.csv"
ART = RUN / "artifacts"
MIN_BASE = 8
MIN_FILTERED = 3
REL_CUT = 0.50


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


R3M = load_module("r3_runner", R3 / "reproduction/run.py")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def json_safe(value):
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if isinstance(value, (np.floating, float)):
        return None if not np.isfinite(value) else float(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, pd.Timestamp):
        return str(value.date())
    return value


def add_momentum(panel: pd.DataFrame, window: int) -> pd.DataFrame:
    frame = panel.sort_values(["product", "date"]).copy()
    values = np.full(len(frame), np.nan)
    for _, indexes in frame.groupby("product").groups.items():
        block = frame.loc[indexes].sort_values("date")
        periods = block["date"].dt.to_period("M").astype("int64").to_numpy()
        returns = block["r_first"].to_numpy(float)
        for index in range(window - 1, len(block)):
            win_periods = periods[index - window + 1 : index + 1]
            if np.array_equal(win_periods - win_periods[0], np.arange(window)):
                values[block.index[index]] = (
                    np.prod(1.0 + returns[index - window + 1 : index + 1]) - 1.0
                )
    frame[f"mom{window}"] = values
    return frame


def portfolio_weights(
    frame: pd.DataFrame,
    factor: str,
    label: str,
    *,
    momentum: str | None = None,
    dual: bool = False,
    equal_weight: bool = False,
):
    rows, diagnostics = [], []
    for date, block in frame.groupby("date"):
        columns = ["product", label]
        if factor is not None:
            columns.append(factor)
        if momentum is not None:
            columns.append(momentum)
        columns = list(dict.fromkeys(columns))
        base = block[columns].dropna()
        if len(base) < MIN_BASE:
            diagnostics.append(
                {
                    "date": date,
                    "base_count": len(base),
                    "eligible_count": 0,
                    "cash": True,
                    "reason": "BASE_BELOW_8",
                }
            )
            continue
        eligible = base.copy()
        if dual:
            eligible["rel"] = eligible[momentum].rank(pct=True, method="average")
            eligible = eligible[
                eligible[momentum].gt(0) & eligible["rel"].ge(REL_CUT)
            ]
        if len(eligible) < MIN_FILTERED:
            diagnostics.append(
                {
                    "date": date,
                    "base_count": len(base),
                    "eligible_count": len(eligible),
                    "cash": True,
                    "reason": "FILTERED_BELOW_3",
                }
            )
            continue
        if equal_weight:
            chosen = eligible
            n = len(chosen)
            weights = pd.Series(1.0 / n, index=chosen["product"])
        else:
            ranked = eligible.sort_values(factor, ascending=False, kind="stable")
            n = max(1, len(ranked) // 3)
            weights = pd.Series(
                1.0 / n, index=ranked["product"].iloc[:n]
            )
        diagnostics.append(
            {
                "date": date,
                "base_count": len(base),
                "eligible_count": len(eligible),
                "cash": False,
                "reason": "OK",
            }
        )
        for product, weight in weights.items():
            rows.append({"date": date, "product": product, "weight": weight})
    return pd.DataFrame(rows), pd.DataFrame(diagnostics)


def returns_for_arm(
    frame: pd.DataFrame,
    weights: pd.DataFrame,
    label: str,
    dates: pd.Index,
    cost: float,
):
    values = frame[["date", "product", label]].dropna()
    merged = weights.merge(values, on=["date", "product"], how="left")
    wide = merged.pivot(index="date", columns="product", values="weight").fillna(0.0)
    labels = merged.pivot(index="date", columns="product", values=label).fillna(0.0)
    wide = wide.reindex(dates, fill_value=0.0)
    labels = labels.reindex(index=dates, columns=wide.columns, fill_value=0.0)
    gross = (wide * labels).sum(axis=1)
    turnover = wide.diff().abs().sum(axis=1)
    turnover.iloc[0] = wide.iloc[0].abs().sum()
    net = gross - cost * turnover
    return net.rename("ret"), gross.rename("gross"), turnover.rename("turnover"), wide


def metric(ret: pd.Series) -> dict:
    values = ret.dropna()
    nav = (1.0 + values).cumprod()
    years = len(values) / 12.0
    cagr = float(nav.iloc[-1] ** (1.0 / years) - 1.0)
    mdd = float((nav / nav.cummax() - 1.0).min())
    return {
        "start": str(values.index.min().date()),
        "end": str(values.index.max().date()),
        "months": int(len(values)),
        "cagr": cagr,
        "vol": float(values.std(ddof=1) * math.sqrt(12.0)),
        "sharpe": float(values.mean() / values.std(ddof=1) * math.sqrt(12.0)),
        "mdd": mdd,
        "calmar": cagr / abs(mdd) if mdd < 0 else np.nan,
    }


def main() -> None:
    ART.mkdir(parents=True, exist_ok=True)
    panel = pd.read_csv(PANEL, parse_dates=["date"])
    panel = add_momentum(panel, 6)
    label_dates = panel.loc[panel["y_nearby"].notna(), "date"].drop_duplicates().sort_values()
    lag_dates = panel.loc[panel["y_nearby_lag1"].notna(), "date"].drop_duplicates().sort_values()

    arm_specs = {}
    arm_specs["UNIVERSE_EW"] = dict(factor=None, momentum=None, dual=False, equal_weight=True)
    arm_specs["BM5_LONG"] = dict(factor="bm5", momentum=None, dual=False, equal_weight=False)
    arm_specs["CARRY_LONG"] = dict(factor="carry", momentum=None, dual=False, equal_weight=False)
    arm_specs["MOM6_LONG"] = dict(factor="mom6", momentum=None, dual=False, equal_weight=False)
    arm_specs["MOM12_LONG"] = dict(factor="mom12", momentum=None, dual=False, equal_weight=False)
    for h in (6, 12):
        arm_specs[f"EW_DUAL{h}"] = dict(
            factor=None, momentum=f"mom{h}", dual=True, equal_weight=True
        )
        arm_specs[f"BM5_DUAL{h}"] = dict(
            factor="bm5", momentum=f"mom{h}", dual=True, equal_weight=False
        )
        arm_specs[f"CARRY_DUAL{h}"] = dict(
            factor="carry", momentum=f"mom{h}", dual=True, equal_weight=False
        )
        arm_specs[f"MOM{h}_DUAL{h}"] = dict(
            factor=f"mom{h}", momentum=f"mom{h}", dual=True, equal_weight=False
        )

    weight_map, diagnostics = {}, {}
    for arm, spec in arm_specs.items():
        if spec["factor"] is None and not spec["dual"]:
            # Universe EW needs an arbitrary non-null frame; product+label is enough.
            factor = "r_first"
        else:
            factor = spec["factor"]
        weights, diag = portfolio_weights(
            panel,
            factor,
            "y_nearby",
            momentum=spec["momentum"],
            dual=spec["dual"],
            equal_weight=spec["equal_weight"],
        )
        weight_map[arm] = weights
        diagnostics[arm] = diag

    metric_rows = []
    net_returns = {}
    for arm in arm_specs:
        for execution, label, dates in (
            ("paper_like", "y_nearby", label_dates),
            ("lag1", "y_nearby_lag1", lag_dates),
        ):
            for cost_bps in (5.0, 20.5):
                net, gross, turnover, wide = returns_for_arm(
                    panel, weight_map[arm], label, dates, cost_bps / 10000.0
                )
                key = f"{arm}_{execution}_{cost_bps:g}bp"
                net_returns[key] = net
                metric_rows.append(
                    {
                        "arm": arm,
                        "execution": execution,
                        "cost_bps": cost_bps,
                        "turnover": float(turnover.mean()),
                        "average_exposure": float(wide.sum(axis=1).mean()),
                        "cash_months": int(wide.sum(axis=1).le(1e-12).sum()),
                        **metric(net),
                    }
                )
                pd.DataFrame({"net": net, "gross": gross, "turnover": turnover}).to_csv(
                    ART / f"returns_{key}.csv"
                )
    metrics = pd.DataFrame(metric_rows)
    metrics.to_csv(ART / "metrics.csv", index=False)
    pd.DataFrame(net_returns).to_csv(ART / "returns.csv")

    for arm, diag in diagnostics.items():
        diag.to_csv(ART / f"eligibility_{arm}.csv", index=False)

    comparisons = []
    pairs = {
        "EW_DUAL6": "UNIVERSE_EW",
        "BM5_DUAL6": "BM5_LONG",
        "CARRY_DUAL6": "CARRY_LONG",
        "MOM6_DUAL6": "MOM6_LONG",
        "EW_DUAL12": "UNIVERSE_EW",
        "BM5_DUAL12": "BM5_LONG",
        "CARRY_DUAL12": "CARRY_LONG",
        "MOM12_DUAL12": "MOM12_LONG",
    }
    for execution in ("paper_like", "lag1"):
        for cost_bps in (5.0, 20.5):
            for candidate, control in pairs.items():
                test = R3M.circular_block_sharpe_diff(
                    net_returns[f"{candidate}_{execution}_{cost_bps:g}bp"],
                    net_returns[f"{control}_{execution}_{cost_bps:g}bp"],
                )
                comparisons.append(
                    {
                        "candidate": candidate,
                        "control": control,
                        "execution": execution,
                        "cost_bps": cost_bps,
                        **test,
                    }
                )
    comparison = pd.DataFrame(comparisons)
    for execution in ("paper_like", "lag1"):
        for cost_bps in (5.0, 20.5):
            mask = comparison["execution"].eq(execution) & comparison["cost_bps"].eq(cost_bps)
            p = comparison.loc[mask, "p_two_sided"].to_numpy(float)
            order = np.argsort(p)
            q = np.ones(len(p))
            running = 1.0
            for rank in range(len(p) - 1, -1, -1):
                pos = order[rank]
                running = min(running, p[pos] * len(p) / (rank + 1))
                q[pos] = running
            comparison.loc[mask, "bh_q"] = q
    comparison.to_csv(ART / "bootstrap.csv", index=False)

    nav = (1.0 + pd.DataFrame(net_returns)).cumprod()
    figure, axis = plt.subplots(figsize=(12, 6))
    for column in (
        "UNIVERSE_EW_paper_like_5bp",
        "BM5_LONG_paper_like_5bp",
        "BM5_DUAL6_paper_like_5bp",
        "BM5_DUAL12_paper_like_5bp",
    ):
        axis.plot(nav.index, nav[column], label=column, linewidth=1.5)
    axis.set_yscale("log")
    axis.set_ylabel("NAV (monthly, log)")
    axis.legend(frameon=False)
    axis.grid(alpha=0.2)
    figure.tight_layout()
    figure.savefig(ART / "nav_dual_filter.png", dpi=180)
    plt.close(figure)

    summary = {
        "status": "DUAL_FILTER_VIEWED_HISTORY_NOT_OOS",
        "controls": ["UNIVERSE_EW", "BM5_LONG", "CARRY_LONG", "MOM6_LONG", "MOM12_LONG"],
        "filtered": list(pairs),
        "metrics": metric_rows,
        "bootstrap": comparison.to_dict(orient="records"),
    }
    (ART / "result.json").write_text(
        json.dumps(json_safe(summary), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(json_safe(summary), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
