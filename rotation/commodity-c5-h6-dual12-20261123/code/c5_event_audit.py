"""Audit the 2025-12 to 2026-02 silver-LOF return spike."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

RUN = Path(__file__).resolve().parent
ART = RUN / "artifacts"
_spec = importlib.util.spec_from_file_location("proxy2015_run", RUN / "run.py")
R = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(R)

RAW_SILVER = Path("/Users/hsh/Documents/Quant/行业轮动/data/raw/local_cache/etf/161226.XSHE.csv")
QFQ_SILVER = Path("/Users/hsh/Documents/Quant/行业轮动/data/raw/local_cache/etf_qfq/161226.XSHE.csv")
INDEPENDENT_SILVER = Path(
    "/Users/hsh/Documents/Quant/CTA策略/01_代码/strategies/22_xb_industry_cta/data/etf/161226.XSHE.csv"
)
SILVER_NAV = Path(
    "/Users/hsh/Documents/Quant/大类择时/research/runs/"
    "gtja_commodity_rotation_20261015/extensions/etf_proxy_benchmark_v1/data/nav_161226.csv"
)
AG0 = Path("/Users/hsh/Documents/Quant/CTA策略/02_数据/futures_raw/AG0.csv")


def apply_tip_dd_lagged(base: pd.Series, cost: float, *, tip_name: str = "S"):
    """Apply a T-1-close drawdown state to the next open-to-open return."""
    tip = R.tip_scores(base.index)
    tip_on = tip[tip_name].gt(0).astype(float).fillna(0.0)
    tip_off = 1.0 - tip_on
    bond = R.B.load_bond(base.index).fillna(0.0)
    tip_to = tip_on.diff().abs().fillna(tip_on.iloc[0]) + tip_off.diff().abs().fillna(
        tip_off.iloc[0]
    )
    pre = tip_on * base + tip_off * bond - cost * tip_to
    nav = (1.0 + pre).cumprod()
    drawdown = (nav / nav.cummax() - 1.0).shift(1)
    state = 1.0
    gates = []
    for value in drawdown:
        if np.isfinite(value):
            if state == 1.0 and value <= -R.B.DD_TRIGGER:
                state = R.B.DD_CUT
            elif state < 1.0 and value >= -R.B.DD_RELEASE:
                state = 1.0
        gates.append(state)
    gate = pd.Series(gates, index=base.index)
    w_risk = tip_on * gate
    w_bond = tip_off + tip_on * (1.0 - gate)
    turnover = (
        w_risk.diff().abs().fillna(w_risk.iloc[0])
        + w_bond.diff().abs().fillna(w_bond.iloc[0])
    )
    net = w_risk * base + w_bond * bond - cost * turnover
    return net.rename("ret"), w_risk.rename("risk_exposure")


def main() -> None:
    opens, closes, _, splices = R.build_asset_panel()
    sim = R.simulate_monthly(closes, opens, 0.0005, rank_k=2, splices=splices)
    strat, exposure = R.apply_tip_dd(
        sim["ret"], 0.0005, tip_name="S", dd=True
    )
    corrected_strat, corrected_exposure = apply_tip_dd_lagged(
        sim["ret"], 0.0005, tip_name="S"
    )

    raw = pd.read_csv(RAW_SILVER, parse_dates=["date"]).set_index("date")
    qfq = pd.read_csv(QFQ_SILVER, parse_dates=["date"]).set_index("date")
    independent = pd.read_csv(INDEPENDENT_SILVER, parse_dates=["date"]).set_index("date")
    nav = pd.read_csv(SILVER_NAV, parse_dates=["date"]).set_index("date")["nav"]
    ag0 = pd.read_csv(AG0, parse_dates=["date"]).set_index("date")["close"]

    # Price at an execution open versus the latest completed NAV known then.
    start_price = float(raw.at[pd.Timestamp("2025-12-01"), "open"])
    end_price = float(raw.at[pd.Timestamp("2026-02-02"), "open"])
    start_nav = float(nav.at[pd.Timestamp("2025-11-28")])
    jan_nav = float(nav.at[pd.Timestamp("2025-12-31")])
    end_nav = float(nav.at[pd.Timestamp("2026-01-30")])
    dec_nav_ret = jan_nav / start_nav - 1.0
    jan_nav_ret = end_nav / jan_nav - 1.0
    dec_price_ret = (
        float(raw.at[pd.Timestamp("2026-01-05"), "open"]) / start_price - 1.0
    )
    jan_price_ret = end_price / float(raw.at[pd.Timestamp("2026-01-05"), "open"]) - 1.0
    start_premium = start_price / start_nav - 1.0
    mid_premium = float(raw.at[pd.Timestamp("2026-01-05"), "open"]) / jan_nav - 1.0
    end_premium = end_price / end_nav - 1.0

    monthly = (1.0 + strat).groupby(strat.index.to_period("M")).prod() - 1.0
    exposure_monthly = exposure.groupby(exposure.index.to_period("M")).mean()
    corrected_monthly = (
        (1.0 + corrected_strat).groupby(corrected_strat.index.to_period("M")).prod()
        - 1.0
    )
    corrected_exposure_monthly = corrected_exposure.groupby(
        corrected_exposure.index.to_period("M")
    ).mean()

    timing_rows = []
    for cost_bps in (5.0, 20.5):
        cost = cost_bps / 10000.0
        for tip_name in ("U13612", "U136", "W", "S"):
            same_ret, same_exp = R.apply_tip_dd(
                sim["ret"], cost, tip_name=tip_name, dd=True
            )
            lag_ret, lag_exp = apply_tip_dd_lagged(
                sim["ret"], cost, tip_name=tip_name
            )
            timing_rows.append(
                {
                    "tip": tip_name,
                    "cost_bps": cost_bps,
                    "implementation": "same_day",
                    **R.B.metrics(
                        same_ret,
                        same_exp,
                        int((same_exp.diff().abs() > 1e-12).sum()),
                    ),
                }
            )
            timing_rows.append(
                {
                    "tip": tip_name,
                    "cost_bps": cost_bps,
                    "implementation": "next_session",
                    **R.B.metrics(
                        lag_ret,
                        lag_exp,
                        int((lag_exp.diff().abs() > 1e-12).sum()),
                    ),
                }
            )
    timing_frame = pd.DataFrame(timing_rows)
    timing_frame.to_csv(ART / "dd_timing_metrics.csv", index=False)

    # If the planned 2026-02-02 open sale cannot fill at a one-price limit-down,
    # compare the equity available for purchasing gold on each later open.
    silver0 = float(opens.at[pd.Timestamp("2026-02-02"), "161226.XSHE"])
    gold0 = float(opens.at[pd.Timestamp("2026-02-02"), "518880.XSHG"])
    delay_rows = []
    for day in pd.to_datetime(
        ["2026-02-02", "2026-02-03", "2026-02-04", "2026-02-05", "2026-02-06", "2026-02-09"]
    ):
        silver = float(opens.at[day, "161226.XSHE"])
        gold = float(opens.at[day, "518880.XSHG"])
        delay_rows.append(
            {
                "sell_date": str(day.date()),
                "silver_open": silver,
                "gold_open": gold,
                "relative_switch_capital_vs_2026_02_02": (silver / silver0)
                * (gold0 / gold)
                - 1.0,
            }
        )

    return_silver = opens["161226.XSHE"].shift(-1) / opens["161226.XSHE"] - 1.0
    return_gold = opens["518880.XSHG"].shift(-1) / opens["518880.XSHG"] - 1.0
    mar2 = pd.Timestamp("2026-03-02")
    delay_strategy_rows = []
    for row in delay_rows:
        sell = pd.Timestamp(row["sell_date"])
        adjusted = sim["ret"].copy()
        for day in adjusted.loc[pd.Timestamp("2026-02-02"):mar2].index:
            if day < sell:
                adjusted.loc[day] = return_silver.loc[day]
            elif day == sell:
                adjusted.loc[day] = return_gold.loc[day] - 2.0 * 0.0005
            else:
                adjusted.loc[day] = return_gold.loc[day]
        delayed_strategy, delayed_exposure = apply_tip_dd_lagged(
            adjusted, 0.0005, tip_name="S"
        )
        delay_strategy_rows.append(
            {
                **row,
                "dec_feb_strategy_return": float(
                    (
                        1.0
                        + delayed_strategy.loc["2025-12-01":"2026-02-27"]
                    ).prod()
                    - 1.0
                ),
                "feb_strategy_return": float(
                    (
                        1.0
                        + delayed_strategy.loc["2026-02-02":"2026-02-27"]
                    ).prod()
                    - 1.0
                ),
                "minimum_risk_exposure": float(
                    delayed_exposure.loc["2026-02-02":"2026-02-27"].min()
                ),
            }
        )

    event = raw.loc["2025-11-20":"2026-02-13"].copy()
    event["nav"] = nav.reindex(event.index)
    event["premium_on_close"] = event["close"] / event["nav"] - 1.0
    event["one_price_limit"] = (
        event["open"].eq(event["high"])
        & event["high"].eq(event["low"])
        & event["low"].eq(event["close"])
    )
    event["ag0_close"] = ag0.reindex(event.index)
    event.to_csv(ART / "silver_event_daily.csv")

    season_vol = raw.loc["2025-01-01":"2025-12-31", "volume"]
    feb_limit = raw.loc["2026-02-02":"2026-02-06"]
    qfq_ratio = qfq["close"].reindex(event.index) / event["close"]
    cross_source_diff = independent.reindex(event.index)[["open", "close"]] - event[
        ["open", "close"]
    ]
    one_price_days = int(event["one_price_limit"].loc["2026-02-02":"2026-02-06"].sum())
    limit_returns = event["close"].pct_change().loc["2026-02-03":"2026-02-06"]
    if not np.allclose(qfq_ratio.dropna(), 1.0, atol=1e-12):
        raise ValueError("raw and qfq prices differ during event")
    if float(cross_source_diff.abs().max().max()) > 1e-12:
        raise ValueError("independent silver price snapshot differs")
    if one_price_days != 5 or float(limit_returns.max()) > -0.098:
        raise ValueError("one-price limit-down sequence not confirmed")
    payload = {
        "status": "PRICE_IS_REAL_NAV_TREND_REAL_BUT_PREMIUM_FILL_AND_DD_SAME_DAY_GATE_ARE_MATERIAL",
        "period": ["2025-12-01", "2026-02-09"],
        "strategy_monthly": {
            "2025-12": {
                "same_day_dd_return": float(monthly.loc[pd.Period("2025-12", "M")]),
                "lagged_dd_return": float(
                    corrected_monthly.loc[pd.Period("2025-12", "M")]
                ),
                "average_risk_exposure": float(
                    exposure_monthly.loc[pd.Period("2025-12", "M")]
                ),
                "lagged_average_risk_exposure": float(
                    corrected_exposure_monthly.loc[pd.Period("2025-12", "M")]
                ),
                "holding": "161226.XSHE",
            },
            "2026-01": {
                "same_day_dd_return": float(monthly.loc[pd.Period("2026-01", "M")]),
                "lagged_dd_return": float(
                    corrected_monthly.loc[pd.Period("2026-01", "M")]
                ),
                "average_risk_exposure": float(
                    exposure_monthly.loc[pd.Period("2026-01", "M")]
                ),
                "lagged_average_risk_exposure": float(
                    corrected_exposure_monthly.loc[pd.Period("2026-01", "M")]
                ),
                "holding": "161226.XSHE",
            },
            "2026-02": {
                "same_day_dd_return": float(monthly.loc[pd.Period("2026-02", "M")]),
                "lagged_dd_return": float(
                    corrected_monthly.loc[pd.Period("2026-02", "M")]
                ),
                "average_risk_exposure": float(
                    exposure_monthly.loc[pd.Period("2026-02", "M")]
                ),
                "lagged_average_risk_exposure": float(
                    corrected_exposure_monthly.loc[pd.Period("2026-02", "M")]
                ),
                "holding": "518880.XSHG",
            },
        },
        "dd_time_alignment": {
            "reported_implementation": "same-day return determines the same-day DD cut",
            "spec_interpretation": "close decision should affect the next executable return",
            "same_day_metrics": R.B.metrics(
                strat,
                exposure,
                int((exposure.diff().abs() > 1e-12).sum()),
            ),
            "lagged_dd_metrics": R.B.metrics(
                corrected_strat,
                corrected_exposure,
                int((corrected_exposure.diff().abs() > 1e-12).sum()),
            ),
            "materially_different_days": int(
                (exposure.sub(corrected_exposure).abs() > 1e-12).sum()
            ),
            "all_variants": timing_rows,
            "status": "FAIL_SAME_DAY_LOOKAHEAD",
        },
        "silver_lof_return_decomposition": {
            "dec_price_open_return": dec_price_ret,
            "dec_nav_return": dec_nav_ret,
            "dec_premium_start": start_premium,
            "dec_premium_next_open": mid_premium,
            "jan_price_open_return": jan_price_ret,
            "jan_nav_return": jan_nav_ret,
            "jan_premium_start": mid_premium,
            "jan_premium_next_open": end_premium,
            "jan_log_share_from_nav": float(np.log1p(jan_nav_ret) / np.log1p(jan_price_ret)),
            "jan_log_share_from_premium_expansion": float(
                1.0 - np.log1p(jan_nav_ret) / np.log1p(jan_price_ret)
            ),
        },
        "silver_futures_check": {
            "dec_close_return": float(
                ag0.at[pd.Timestamp("2025-12-31")] / ag0.at[pd.Timestamp("2025-11-28")] - 1.0
            ),
            "jan_close_return": float(
                ag0.at[pd.Timestamp("2026-01-30")] / ag0.at[pd.Timestamp("2025-12-31")] - 1.0
            ),
            "feb_close_return": float(
                ag0.at[pd.Timestamp("2026-02-27")] / ag0.at[pd.Timestamp("2026-01-30")] - 1.0
            ),
        },
        "take_profit_and_exit": {
            "signal_date": "2026-01-29",
            "trail10": float(closes["161226.XSHE"].pct_change(10).at[pd.Timestamp("2026-01-29")]),
            "planned_exit": "2026-02-02 open",
            "planned_exit_price": end_price,
            "next_market_open": "2026-02-03",
            "one_price_limit_down_days": [
                str(day.date()) for day in feb_limit.index
            ],
            "feb_limit_volume": {
                str(day.date()): int(feb_limit.at[day, "volume"])
                for day in feb_limit.index
            },
            "median_2025_volume": float(season_vol.median()),
            "delay_sensitivity": delay_strategy_rows,
        },
        "execution_warning": "The 2026-02-02 sale was modeled at an unlimited open fill while the LOF printed open=high=low=close and -10%. Actual full-size execution is not established.",
        "data_checks": {
            "raw_qfq_identical": bool(
                np.allclose(qfq_ratio.dropna(), 1.0, atol=1e-12)
            ),
            "raw_close_and_qfq_close_max_abs_difference": float(
                (qfq_ratio.dropna() - 1.0).abs().max()
            ),
            "independent_snapshot_max_abs_difference": float(
                cross_source_diff.abs().max().max()
            ),
            "missing_market_dates": ["2026-01-22", "2026-01-30"],
            "nav_source": str(SILVER_NAV),
            "price_source": str(RAW_SILVER),
        },
        "conclusion": {
            "underlying_silver_move": "SUPPORTED_BY_NAV_AND_AG0",
            "market_price_series": "REAL_LOCAL_PRICE_WITH_LIMIT_MOVES",
            "clean_commodity_return": "NO_LOF_PREMIUM_AMPLIFIES_JANUARY",
            "strategy_execution": "OPTIMISTIC_UNTIL_LIMIT_FILL_IS_MODELED",
            "dd_timing": "FAIL_SAME_DAY_LOOKAHEAD",
            "previously_reported_dd_metrics": "SUPERSEDED_PENDING_LAGGED_DD_REBUILD",
            "production_change": False,
        },
    }
    (ART / "silver_event_audit.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    fig, ax = plt.subplots(figsize=(11, 6))
    ax.plot(event.index, event["close"], label="161226 market close", linewidth=1.7)
    ax.plot(event.index, event["nav"], label="161226 official NAV", linewidth=1.7)
    ax.set_ylabel("CNY per unit")
    ax.set_title("161226 silver LOF: market price versus NAV")
    ax.grid(alpha=0.2)
    ax.legend(frameon=False)
    fig.autofmt_xdate()
    fig.subplots_adjust(left=0.08, right=0.98, top=0.92, bottom=0.14)
    fig.savefig(ART / "silver_price_vs_nav.png", dpi=160)
    plt.close(fig)

    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
