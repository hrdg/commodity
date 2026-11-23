"""Six-commodity C5 monthly strategy with explicit 2015 proxy history."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

RUN = Path(__file__).resolve().parent
ART = RUN / "artifacts"
ROOT = RUN.parents[2]
PARENT = ROOT / "research/runs/c5_six_commodities_20261109"
_spec = importlib.util.spec_from_file_location("base_c5_six", PARENT / "run.py")
B = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(B)

FUNDS = B.FUNDS
START = pd.Timestamp("2015-01-05")
END = pd.Timestamp("2026-11-06")
PANEL_START = pd.Timestamp("2014-01-02")
FUT = Path("/Users/hsh/Documents/Quant/CTA策略/02_数据/futures_raw")
USO = Path("/Users/hsh/Documents/Quant/commodity_repo/原油/data/uso.csv")
MEAL = Path("/Users/hsh/Documents/Quant/commodity_repo/豆粕/data/M0_roll_adjusted_full.csv")
REFRESH = B.REFRESH

ACTUAL_SOURCES = {
    "160723.XSHE": Path(
        "/Users/hsh/Documents/Quant/大类择时/research/runs/kaiyuan_oil_gas_20261028/data/160723.csv"
    ),
    "159985.XSHE": Path("/Users/hsh/Documents/Quant/行业轮动/data/raw/local_cache/etf_qfq/159985.XSHE.csv"),
    "159980.XSHE": Path("/Users/hsh/Documents/Quant/行业轮动/data/raw/local_cache/etf_qfq/159980.XSHE.csv"),
    "159981.XSHE": Path("/Users/hsh/Documents/Quant/行业轮动/data/raw/local_cache/etf_qfq/159981.XSHE.csv"),
    "518880.XSHG": Path("/Users/hsh/Documents/Quant/择时策略/data/industry_etf/518880.XSHG.csv"),
    "161226.XSHE": Path("/Users/hsh/Documents/Quant/行业轮动/data/raw/local_cache/etf_qfq/161226.XSHE.csv"),
}

ACTUAL_START = {
    "160723.XSHE": pd.Timestamp("2017-05-05"),
    "159985.XSHE": pd.Timestamp("2019-12-05"),
    "159980.XSHE": pd.Timestamp("2019-12-24"),
    "159981.XSHE": pd.Timestamp("2020-01-17"),
    "518880.XSHG": pd.Timestamp("2013-12-02"),
    "161226.XSHE": pd.Timestamp("2015-08-17"),
}

PROXY_GROUPS = {
    "159980.XSHE": ("CU0", "AL0", "ZN0"),
    "159981.XSHE": ("TA0", "MA0", "FG0"),
}


def json_safe(value):
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_safe(v) for v in value]
    if isinstance(value, (np.floating, float)):
        return None if not np.isfinite(value) else float(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.bool_):
        return bool(value)
    return value


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_futures(code: str) -> pd.DataFrame:
    frame = pd.read_csv(FUT / f"{code}.csv", parse_dates=["date"])
    frame = frame.set_index("date").sort_index()
    if frame.index.has_duplicates:
        raise ValueError(f"duplicate futures dates: {code}")
    frame = frame[["open", "close"]].apply(pd.to_numeric, errors="coerce")
    frame = frame[(frame["open"] > 0) & (frame["close"] > 0)]
    return frame


def load_actual() -> tuple[dict[str, pd.DataFrame], list[dict]]:
    refresh = pd.read_parquet(REFRESH)
    refresh = refresh[refresh["adjust"].eq("qfq")].copy()
    refresh["date"] = pd.to_datetime(refresh["date"]).dt.tz_localize(None)
    refresh["fund"] = refresh["fund"].map(B.normalize_fund)
    out = {}
    source_rows = []
    for fund, path in ACTUAL_SOURCES.items():
        raw = pd.read_csv(path)
        raw["date"] = pd.to_datetime(raw["date"])
        frame = raw.set_index("date")[["open", "close"]].sort_index()
        frame = frame.apply(pd.to_numeric, errors="coerce")
        frame = frame[(frame["open"] > 0) & (frame["close"] > 0)]
        if frame.index.has_duplicates:
            frame = frame[~frame.index.duplicated(keep="last")]
        tail = refresh[refresh["fund"].eq(fund)][["date", "open", "close"]]
        tail = tail.set_index("date").sort_index()
        tail = tail[tail.index > frame.index.max()]
        merged = pd.concat([frame, tail]).sort_index()
        out[fund] = merged.loc[:END]
        source_rows.append(
            {
                "fund": fund,
                "path": str(path),
                "sha256": sha256(path),
                "first": str(frame.index.min().date()),
                "last": str(frame.index.max().date()),
                "refresh_rows": int(len(tail)),
            }
        )
    return out, source_rows


def group_return_path(
    groups: dict[str, tuple[str, ...]],
    calendar: pd.DatetimeIndex,
    end: pd.Timestamp,
) -> tuple[dict[str, pd.Series], pd.DataFrame]:
    """Build sector paths from open/close returns, never from stitched levels."""
    dates = calendar[(calendar >= PANEL_START) & (calendar <= end)]
    missing_rows = []
    paths = {}
    detail_rows = []
    for fund, group in groups.items():
        raw = {code: load_futures(code) for code in group}
        last_close = {code: np.nan for code in group}
        level_open = 1.0
        level_close = 1.0
        opens, closes, gs, hs = [], [], [], []
        for i, day in enumerate(dates):
            group_gap = []
            group_intra = []
            active = []
            for code, frame in raw.items():
                if day not in frame.index:
                    if np.isfinite(last_close[code]):
                        group_gap.append(0.0)
                        group_intra.append(0.0)
                        active.append(code)
                        missing_rows.append(
                            {
                                "fund": fund,
                                "code": code,
                                "date": str(day.date()),
                                "treatment": "stale valuation at prior close",
                            }
                        )
                    continue
                open_now = float(frame.at[day, "open"])
                close_now = float(frame.at[day, "close"])
                if np.isfinite(last_close[code]):
                    group_gap.append(open_now / last_close[code] - 1.0)
                    group_intra.append(close_now / open_now - 1.0)
                else:
                    # First observation joins without inventing an overnight return.
                    group_gap.append(0.0)
                    group_intra.append(close_now / open_now - 1.0)
                last_close[code] = close_now
                active.append(code)
            if not active:
                raise ValueError(f"no available futures for {fund} on {day}")
            gap = float(np.mean(group_gap))
            intra = float(np.mean(group_intra))
            level_open = level_close * (1.0 + gap) if i else 1.0
            level_close = level_open * (1.0 + intra)
            opens.append(level_open)
            closes.append(level_close)
            gs.append(gap)
            hs.append(intra)
            detail_rows.append(
                {
                    "date": day,
                    "fund": fund,
                    "members": ",".join(active),
                    "gap": gap,
                    "intra": intra,
                    "open": level_open,
                    "close": level_close,
                }
            )
        paths[fund] = pd.DataFrame({"open": opens, "close": closes}, index=dates)
    return paths, pd.DataFrame(detail_rows), pd.DataFrame(missing_rows)


def direct_proxy(code: str, calendar: pd.DatetimeIndex, end: pd.Timestamp) -> pd.DataFrame:
    raw = load_futures(code)
    dates = calendar[(calendar >= PANEL_START) & (calendar <= end)]
    re = raw.reindex(dates).ffill()
    re["open"] = re["open"].fillna(re["close"])
    return re / float(re["close"].dropna().iloc[0])


def meal_proxy(calendar: pd.DatetimeIndex, end: pd.Timestamp) -> pd.DataFrame:
    raw = pd.read_csv(MEAL, parse_dates=["date"]).set_index("date").sort_index()
    raw = raw[["open", "close"]].apply(pd.to_numeric, errors="coerce")
    dates = calendar[(calendar >= PANEL_START) & (calendar <= end)]
    re = raw.reindex(dates).ffill()
    re["open"] = re["open"].fillna(re["close"])
    return re / float(re["close"].dropna().iloc[0])


def crude_proxy(calendar: pd.DatetimeIndex, end: pd.Timestamp) -> pd.DataFrame:
    raw = pd.read_csv(USO, parse_dates=["date"]).set_index("date")["close"].sort_index()
    dates = calendar[(calendar >= PANEL_START) & (calendar <= end)]
    # At China date T, the last completed US close is date T-1.
    known = raw.reindex(calendar, method="ffill").reindex(calendar).shift(1)
    known = known.reindex(dates).ffill()
    return pd.DataFrame({"open": known, "close": known})


def build_asset_panel() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    actual, actual_sources = load_actual()
    gold = actual["518880.XSHG"].loc[lambda x: x.index >= PANEL_START]
    calendar = gold.index[(gold.index >= PANEL_START) & (gold.index <= END)]

    sector_paths, _, missing = group_return_path(PROXY_GROUPS, calendar, END)
    proxies = {
        "160723.XSHE": crude_proxy(calendar, END),
        "159985.XSHE": meal_proxy(calendar, END),
        "159980.XSHE": sector_paths["159980.XSHE"],
        "159981.XSHE": sector_paths["159981.XSHE"],
        "518880.XSHG": actual["518880.XSHG"].reindex(calendar),
        "161226.XSHE": direct_proxy("AG0", calendar, END),
    }

    opens = {}
    closes = {}
    splice_rows = []
    for fund in FUNDS:
        proxy = proxies[fund].reindex(calendar)
        if fund == "518880.XSHG":
            pan = actual[fund].reindex(calendar)
            opens[fund] = pan["open"]
            closes[fund] = pan["close"]
            continue
        switch = ACTUAL_START[fund]
        proxy_rows = calendar < switch
        if not proxy_rows.any():
            raise ValueError(f"proxy window empty for {fund}")
        prior = calendar[proxy_rows][-1]
        if not np.isfinite(proxy.at[prior, "close"]):
            raise ValueError(f"proxy close missing before splice for {fund}")
        act = actual[fund].reindex(calendar)
        actual_start = max(switch, calendar[calendar >= act["open"].first_valid_index()][0])
        act_open0 = float(act.at[actual_start, "open"])
        scale = float(proxy.at[prior, "close"]) / act_open0

        asset_open = proxy["open"].copy()
        asset_close = proxy["close"].copy()
        future = calendar >= actual_start
        asset_open.loc[future] = act.loc[future, "open"] * scale
        asset_close.loc[future] = act.loc[future, "close"] * scale
        # Force close continuity at the splice; the executable return starts on next open.
        asset_open.loc[actual_start] = float(proxy.at[prior, "close"])
        opens[fund] = asset_open
        closes[fund] = asset_close
        splice_rows.append(
            {
                "fund": fund,
                "proxy_end": str(prior.date()),
                "actual_start": str(actual_start.date()),
                "scale": scale,
                "proxy_close": float(proxy.at[prior, "close"]),
                "actual_open_unscaled": act_open0,
                "actual_close_scaled": float(asset_close.at[actual_start]),
            }
        )

    open_frame = pd.DataFrame(opens).reindex(calendar)[list(FUNDS)]
    close_frame = pd.DataFrame(closes).reindex(calendar)[list(FUNDS)]
    keep = open_frame.notna().all(axis=1) & close_frame.notna().all(axis=1)
    dates = calendar[keep]
    open_frame = open_frame.loc[dates]
    close_frame = close_frame.loc[dates]
    if not open_frame.index.equals(close_frame.index):
        raise ValueError("open/close date mismatch")
    proxy_check = pd.DataFrame(
        {fund: proxies[fund]["close"].reindex(calendar) for fund in FUNDS}
    )
    source_manifest = pd.DataFrame(actual_sources)
    splice_frame = pd.DataFrame(splice_rows)
    return open_frame, close_frame, proxy_check, splice_frame


def simulate_monthly(
    closes: pd.DataFrame,
    opens: pd.DataFrame,
    cost: float,
    *,
    rank_k: int,
    splices: pd.DataFrame,
) -> pd.DataFrame:
    scores = B.momentum_scores(closes, 25, 250)
    z_r2 = B.zscore(scores)
    eff = B.efficiency(closes)
    beta = B.beta252(closes)
    trail = closes.pct_change(10, fill_method=None)
    first = int(np.searchsorted(closes.index.values, START.to_datetime64(), side="left"))
    hold = None
    unlock: dict[str, int] = {}
    splice_dates = set(pd.to_datetime(splices["actual_start"])) if len(splices) else set()
    rows = []
    for i in range(first, len(closes) - 1):
        d = i - 1
        rebalance = (
            i == first
            or closes.index[i].month != closes.index[i - 1].month
        )
        if rebalance:
            target, unlock, take_profit, veto = B.choose(
                scores.iloc[d],
                z_r2.iloc[d],
                eff.iloc[d],
                beta.iloc[d],
                hold,
                trail.iloc[d],
                i,
                unlock,
                rank2=True,
                hold_k=rank_k,
            )
        else:
            target, take_profit, veto = hold, False, False
        turnover = 0.0 if target == hold else (1.0 if target is None or hold is None else 2.0)
        gross = 0.0 if target is None else float(
            opens.iloc[i + 1][target] / opens.iloc[i][target] - 1.0
        )
        splice_fee = 0.0
        if target is not None and target == hold and closes.index[i] in splice_dates:
            splice_fee = 2.0 * cost
        net = gross - cost * turnover - splice_fee
        rows.append(
            {
                "date": closes.index[i],
                "ret": net,
                "gross": gross,
                "turnover": turnover,
                "splice_fee": splice_fee,
                "hold": target,
                "take_profit": take_profit,
                "veto": veto,
            }
        )
        hold = target
    return pd.DataFrame(rows).set_index("date")


def daily_from_monthly(monthly: pd.Series, index: pd.DatetimeIndex) -> pd.Series:
    return pd.Series(
        [monthly.get(period - 1, np.nan) for period in index.to_period("M")],
        index=index,
    )


def tip_scores(index: pd.DatetimeIndex) -> pd.DataFrame:
    tip = pd.read_parquet(B.TIP).set_index("date")["close"].sort_index()
    monthly = tip.groupby(tip.index.to_period("M")).last()
    r1 = monthly / monthly.shift(1) - 1.0
    r3 = monthly / monthly.shift(3) - 1.0
    r6 = monthly / monthly.shift(6) - 1.0
    r12 = monthly / monthly.shift(12) - 1.0
    scores = pd.DataFrame(
        {
            "U13612": (r1 + r3 + r6 + r12) / 4.0,
            "U136": (r1 + r3 + r6) / 3.0,
            "W": (12.0 * r1 + 4.0 * r3 + 2.0 * r6 + r12) / 19.0,
            "S": monthly / monthly.rolling(12, min_periods=12).mean() - 1.0,
        }
    )
    return pd.DataFrame(
        {column: daily_from_monthly(scores[column], index) for column in scores},
        index=index,
    )


def apply_tip_dd(base: pd.Series, cost: float, *, tip_name: str | None, dd: bool):
    if tip_name is None:
        one = pd.Series(1.0, index=base.index)
        return base.copy(), one
    tip = tip_scores(base.index)
    tip_on = tip[tip_name].gt(0).astype(float).fillna(0.0)
    tip_off = 1.0 - tip_on
    bond = B.load_bond(base.index).fillna(0.0)
    tip_to = tip_on.diff().abs().fillna(tip_on.iloc[0]) + tip_off.diff().abs().fillna(
        tip_off.iloc[0]
    )
    tip_ret = tip_on * base + tip_off * bond - cost * tip_to
    if not dd:
        return tip_ret.rename("ret"), tip_on.rename("risk_exposure")
    nav = (1.0 + tip_ret).cumprod()
    drawdown = nav / nav.cummax() - 1.0
    state = 1.0
    gates = []
    for value in drawdown:
        if state == 1.0 and value <= -B.DD_TRIGGER:
            state = B.DD_CUT
        elif state < 1.0 and value >= -B.DD_RELEASE:
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


def concentration(ret: pd.Series) -> dict:
    monthly = (1.0 + ret).groupby(ret.index.to_period("M")).prod() - 1.0
    log_ret = np.log1p(monthly)
    positive = log_ret[log_ret > 0]
    total = float(log_ret.sum())
    return {
        "months": int(len(monthly)),
        "positive_months": int((monthly > 0).sum()),
        "top3_positive_log_share": float(positive.nlargest(3).sum() / total)
        if total > 0
        else None,
        "best_months": [
            {"month": str(idx), "return": float(value)}
            for idx, value in monthly.nlargest(5).items()
        ],
    }


def proxy_reconciliation(
    closes: pd.DataFrame,
    proxy_levels: pd.DataFrame,
    actual_sources: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    rows = []
    for fund, start in ACTUAL_START.items():
        if fund == "518880.XSHG":
            continue
        proxy = proxy_levels[fund].dropna()
        actual = actual_sources[fund]["close"].reindex(closes.index)
        proxy_ret = proxy.loc[start:END].pct_change(fill_method=None)
        actual_ret = actual.loc[start:END].pct_change(fill_method=None)
        pair = pd.concat(
            [proxy_ret.rename("proxy"), actual_ret.rename("actual")], axis=1
        ).dropna()
        rows.append(
            {
                "fund": fund,
                "start": str(pair.index.min().date()),
                "end": str(pair.index.max().date()),
                "days": int(len(pair)),
                "return_correlation": float(pair["proxy"].corr(pair["actual"])),
                "mean_abs_daily_difference": float(
                    (pair["proxy"] - pair["actual"]).abs().mean()
                ),
                "annualized_return_difference": float(
                    (pair["proxy"].mean() - pair["actual"].mean()) * 252.0
                ),
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    ART.mkdir(parents=True, exist_ok=True)
    opens, closes, proxy_levels, splices = build_asset_panel()
    asset_actual, actual_sources = load_actual()
    panel = pd.concat(
        {
            "open": opens,
            "close": closes,
            "proxy_close": proxy_levels.reindex(closes.index),
        },
        axis=1,
    )
    panel.to_csv(ART / "asset_panel.csv")
    splices.to_csv(ART / "splices.csv", index=False)

    stores = {}
    ledgers = {}
    switch_events = {}
    for cost_bps in (5, 20.5):
        cost = cost_bps / 10000.0
        for rank_k in (1, 2):
            sim = simulate_monthly(closes, opens, cost, rank_k=rank_k, splices=splices)
            base_name = f"RANK{rank_k}_NODD"
            base_event = sim["turnover"].gt(0) | sim["splice_fee"].gt(0)
            stores[(base_name, cost_bps)] = sim["ret"]
            ledgers[(base_name, cost_bps)] = sim["hold"].notna().astype(float)
            switch_events[(base_name, cost_bps)] = base_event
            if rank_k == 2:
                for tip_name in ("U13612", "U136", "W", "S"):
                    ret, exp = apply_tip_dd(
                        sim["ret"], cost, tip_name=tip_name, dd=True
                    )
                    name = f"RANK2_TIP{tip_name}_DD"
                    stores[(name, cost_bps)] = ret
                    ledgers[(name, cost_bps)] = exp
                    switch_events[(name, cost_bps)] = (
                        base_event | (exp.diff().abs() > 1e-12)
                    )
                ret, exp = apply_tip_dd(
                    sim["ret"], cost, tip_name="S", dd=False
                )
                stores[("RANK2_TIPS_NODD", cost_bps)] = ret
                ledgers[("RANK2_TIPS_NODD", cost_bps)] = exp
                switch_events[("RANK2_TIPS_NODD", cost_bps)] = (
                    base_event | (exp.diff().abs() > 1e-12)
                )
            else:
                ret, exp = apply_tip_dd(
                    sim["ret"], cost, tip_name="U13612", dd=True
                )
                stores[("RANK1_TIPU13612_DD", cost_bps)] = ret
                ledgers[("RANK1_TIPU13612_DD", cost_bps)] = exp
                switch_events[("RANK1_TIPU13612_DD", cost_bps)] = (
                    base_event | (exp.diff().abs() > 1e-12)
                )
        c5 = simulate_monthly(closes, opens, cost, rank_k=1, splices=splices)
        # Rank1 with the frozen buffer is behaviorally close to bare C5; retain the
        # explicit no-buffer label only when the underlying choice is the same.
        stores[("C5_R2_NODD", cost_bps)] = c5["ret"]
        ledgers[("C5_R2_NODD", cost_bps)] = c5["hold"].notna().astype(float)
        switch_events[("C5_R2_NODD", cost_bps)] = (
            c5["turnover"].gt(0) | c5["splice_fee"].gt(0)
        )

    common = stores[("RANK2_TIPS_DD", 5)].index
    common = common[
        (common >= START) & (common <= pd.Timestamp("2026-11-05"))
    ]
    metrics_rows = []
    for (name, cost_bps), ret in stores.items():
        exposure = ledgers[(name, cost_bps)].reindex(common)
        metrics_rows.append(
            {
                "arm": name,
                "cost_bps": cost_bps,
                **B.metrics(
                    ret.reindex(common),
                    exposure,
                    int(switch_events[(name, cost_bps)].reindex(common).sum()),
                ),
            }
        )
    metrics = pd.DataFrame(metrics_rows)
    metrics.to_csv(ART / "metrics.csv", index=False)
    pd.DataFrame(
        {f"{name}@{cost}": ret.reindex(common) for (name, cost), ret in stores.items()}
    ).to_csv(ART / "returns.csv")
    pd.DataFrame(
        {f"{name}@{cost}": exp.reindex(common) for (name, cost), exp in ledgers.items()}
    ).to_csv(ART / "exposures.csv")

    # All registered comparisons are fixed before looking at their results.
    comparison_specs = [
        ("RANK2_TIPS_DD", "RANK2_TIPU13612_DD", "tip_s_vs_u13612"),
        ("RANK2_TIPS_DD", "RANK2_NODD", "tip_s_dd_vs_raw"),
        ("RANK2_TIPU13612_DD", "RANK2_NODD", "tip_u13612_dd_vs_raw"),
        ("RANK2_TIPS_NODD", "RANK2_TIPS_DD", "dd_increment"),
        ("RANK2_TIPU13612_DD", "RANK1_TIPU13612_DD", "rank2_vs_rank1"),
    ]
    comp_rows = []
    for candidate, control, label in comparison_specs:
        comp_rows.append(
            {
                "label": label,
                "candidate": candidate,
                "control": control,
                **B.bootstrap(
                    stores[(candidate, 5)].reindex(common),
                    stores[(control, 5)].reindex(common),
                ),
            }
        )
    comp = pd.DataFrame(comp_rows)
    p = comp["p_two_sided"].to_numpy(float)
    order = np.argsort(p)
    adjusted = np.empty(len(p))
    running = 1.0
    for rank in range(len(p) - 1, -1, -1):
        pos = order[rank]
        running = min(running, p[pos] * len(p) / (rank + 1))
        adjusted[pos] = running
    comp["bh_q"] = np.clip(adjusted, 0.0, 1.0)
    comp.to_csv(ART / "bootstrap.csv", index=False)

    segment_defs = [
        ("2015-2019", pd.Timestamp("2015-01-05"), pd.Timestamp("2019-12-31")),
        ("2020-2021", pd.Timestamp("2020-01-01"), pd.Timestamp("2021-12-31")),
        ("2022-08-05:2026-11-05", pd.Timestamp("2022-08-05"), pd.Timestamp("2026-11-05")),
        ("full", pd.Timestamp("2015-01-05"), pd.Timestamp("2026-11-05")),
    ]
    segment_rows = []
    yearly_rows = []
    arm_names = [
        "C5_R2_NODD",
        "RANK1_TIPU13612_DD",
        "RANK2_NODD",
        "RANK2_TIPS_NODD",
        "RANK2_TIPU13612_DD",
        "RANK2_TIPS_DD",
    ]
    for name in arm_names:
        ret = stores[(name, 5)]
        exp = ledgers[(name, 5)]
        for label, start, end in segment_defs:
            x = ret.loc[start:end]
            segment_rows.append(
                {
                    "arm": name,
                    "segment": label,
                    "cost_bps": 5,
                    **B.metrics(
                        x,
                        exp.reindex(x.index),
                        int(
                            switch_events[(name, 5)]
                            .reindex(x.index)
                            .sum()
                        ),
                    ),
                }
            )
        for year, block in ret.groupby(ret.index.year):
            yearly_rows.append(
                {
                    "arm": name,
                    "year": int(year),
                    "return": float((1.0 + block).prod() - 1.0),
                }
            )
    segments = pd.DataFrame(segment_rows)
    yearly = pd.DataFrame(yearly_rows)
    segments.to_csv(ART / "segments.csv", index=False)
    yearly.to_csv(ART / "yearly.csv", index=False)

    recon = proxy_reconciliation(closes, proxy_levels, asset_actual)
    recon.to_csv(ART / "reconciliation.csv", index=False)

    # Compare the post-2022 strategy path against the existing actual-ETF run.
    parent_ret = pd.read_csv(PARENT / "artifacts/risk_lab_returns.csv", index_col=0, parse_dates=True)
    parent_ret = parent_ret["RANK2_TIPS_DD@5"]
    parent_ret = parent_ret[~parent_ret.index.duplicated()]
    pair = pd.concat(
        [
            stores[("RANK2_TIPS_DD", 5)].loc["2022-08-05":"2026-11-05"].rename("proxy_extended"),
            parent_ret.loc["2022-08-05":"2026-11-05"].rename("actual_parent"),
        ],
        axis=1,
    ).dropna()
    overlap = {
        "start": str(pair.index.min().date()),
        "end": str(pair.index.max().date()),
        "days": int(len(pair)),
        "return_correlation": float(pair["proxy_extended"].corr(pair["actual_parent"])),
        "mean_abs_daily_difference": float(
            (pair["proxy_extended"] - pair["actual_parent"]).abs().mean()
        ),
        "annualized_return_difference": float(
            (pair["proxy_extended"].mean() - pair["actual_parent"].mean()) * 252.0
        ),
    }
    pd.DataFrame([overlap]).to_csv(ART / "parent_overlap.csv", index=False)

    holds = pd.DataFrame(
        {
            name: store.rename(name)
            for name, store in {
                "RANK2_NODD": stores[("RANK2_NODD", 5)],
                "RANK2_TIPS_DD": stores[("RANK2_TIPS_DD", 5)],
            }.items()
        }
    )
    hold_frame = pd.DataFrame(
        {
            "RANK2_NODD": (1.0 + stores[("RANK2_NODD", 5)]).cumprod(),
            "RANK2_TIPS_DD": (1.0 + stores[("RANK2_TIPS_DD", 5)]).cumprod(),
        }
    )
    hold_frame.to_csv(ART / "nav.csv")
    monthly_holdings = pd.DataFrame(
        {
            "RANK2_NODD": simulate_monthly(
                closes, opens, 5 / 10000.0, rank_k=2, splices=splices
            )["hold"],
        }
    )
    monthly_holdings.to_csv(ART / "monthly_holdings.csv")

    conc = {
        name: concentration(stores[(name, 5)].reindex(common))
        for name in ("RANK2_NODD", "RANK2_TIPU13612_DD", "RANK2_TIPS_DD")
    }
    latest = {
        "as_of_return_date": str(common.max().date()),
        "last_market_close": str(closes.index.max().date()),
        "RANK2_NODD_last_hold": simulate_monthly(
            closes, opens, 5 / 10000.0, rank_k=2, splices=splices
        )["hold"].dropna().iloc[-1],
        "TIP_S_last_signal": float(tip_scores(common)["S"].iloc[-1]),
        "TIP_U13612_last_signal": float(tip_scores(common)["U13612"].iloc[-1]),
        "RANK2_TIPS_DD_last_risk_exposure": float(
            ledgers[("RANK2_TIPS_DD", 5)].loc[common.max()]
        ),
        "RANK2_TIPU13612_DD_last_risk_exposure": float(
            ledgers[("RANK2_TIPU13612_DD", 5)].loc[common.max()]
        ),
    }

    drawdown = hold_frame["RANK2_TIPS_DD"] / hold_frame["RANK2_TIPS_DD"].cummax() - 1.0
    summary = {
        "experiment": "C5_SIX_COMMODITY_PROXY2015_20261109",
        "status": "EXPLORATORY_PROXY_EXTENSION_NOT_OOS",
        "window": [str(common.min().date()), str(common.max().date())],
        "proxy_mapping": {
            "160723": "USO lagged close until 2017-05-04; ETF after 2017-05-05",
            "159985": "M0_roll_adjusted until 2019-12-04; ETF after 2019-12-05",
            "159980": "CU0/AL0/ZN0 equal-weight return chain until 2019-12-23; ETF after 2019-12-24",
            "159981": "TA0/MA0/FG0 equal-weight return chain until 2020-01-16; ETF after 2020-01-17",
            "518880": "actual ETF from 2013-12-02",
            "161226": "AG0 until 2015-08-14; ETF after 2015-08-17",
        },
        "metrics": metrics_rows,
        "segments": segment_rows,
        "bootstrap": comp.to_dict(orient="records"),
        "proxy_reconciliation": recon.to_dict(orient="records"),
        "parent_overlap": overlap,
        "latest_state": latest,
        "concentration": conc,
        "splices": splices.to_dict(orient="records"),
        "limits": [
            "Pre-listing commodity returns are proxy paths, not actual ETF history.",
            "USO is lagged and is not a directly executable China-open price.",
            "CU0/AL0/ZN0/TA0/MA0/FG0/AG0 are main-continuous prices with unverified roll treatment.",
            "M0 roll-adjusted history lacks a complete contract mapping and is not production-certified.",
            "LOF premiums and discounts are not modeled before or after ETF switches.",
            "All history has been observed; the 2022+ phase influenced the original model and this extension is not independent OOS.",
        ],
    }
    (ART / "summary.json").write_text(
        json.dumps(json_safe(summary), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (ART / "latest_state.json").write_text(
        json.dumps(json_safe(latest), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (ART / "concentration.json").write_text(
        json.dumps(json_safe(conc), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    fig, ax = plt.subplots(figsize=(12, 6.5))
    for label, column in (
        ("RANK2 raw C5", "RANK2_NODD"),
        ("RANK2 + TIP U13612 + DD", "RANK2_TIPU13612_DD"),
        ("RANK2 + TIP S + DD", "RANK2_TIPS_DD"),
    ):
        nav = (1.0 + stores[(column, 5)].reindex(common)).cumprod()
        ax.plot(nav.index, nav.values, label=label, linewidth=1.6)
    ax.set_title("Six-commodity C5 from 2015 with explicit proxies", loc="left")
    ax.set_ylabel("NAV")
    ax.grid(alpha=0.2)
    ax.legend(frameon=False, fontsize=8)
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    fig.subplots_adjust(left=0.08, right=0.98, top=0.93, bottom=0.08)
    fig.savefig(ART / "nav.png", dpi=160)
    plt.close(fig)

    print("PANEL", closes.index.min(), closes.index.max(), len(closes))
    print("\nMETRICS")
    print(metrics.to_string(index=False))
    print("\nSEGMENTS")
    print(segments.to_string(index=False))
    print("\nRECONCILIATION")
    print(recon.to_string(index=False))
    print("\nPARENT OVERLAP", overlap)
    print("\nLATEST", latest)


if __name__ == "__main__":
    main()
