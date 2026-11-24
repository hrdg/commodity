# -*- coding: utf-8 -*-
"""
架构 v4：移植 codex 双动量层（mom1 secondary / slope secondary / 绝对动量门 / 软倾斜）
到 D2 骨架。PRE_REGISTER.md 冻结口径，单遍执行，双动量线最后一批。
"""
import os
import json
import numpy as np
import pandas as pd
from scipy import stats

PREV = "/Users/hsh/Documents/Quant/科技轮动/research/runs/aw7_commodity_bm_mainchain_20261124/artifacts"
RUN = "/Users/hsh/Documents/Quant/科技轮动/research/runs/aw7_commodity_mom_arch_v4_20261124"
ART = f"{RUN}/artifacts"
os.makedirs(ART, exist_ok=True)

COST_MAIN, COST_STRESS = 0.0005, 0.00205
MIN_XS, TOPBOT = 8, 1 / 3
START = "2006-01-01"

panel = pd.read_csv(f"{PREV}/monthly_panel.csv", parse_dates=["month"])
panel = panel.sort_values(["sym", "month"]).reset_index(drop=True)
panel["mom1"] = panel["r_ex"]                                  # 冻结：上一月收益
panel["ds6"] = panel["slope"] - panel["slope_lag6"]
panel["vol12"] = panel.groupby("sym")["r_ex"].transform(
    lambda x: x.rolling(12, min_periods=6).std() * np.sqrt(12))

def nw_t(x, lags=3):
    x = np.asarray(x, float); n = len(x); mu = x.mean(); e = x - mu
    s = (e @ e) / n
    for l in range(1, lags + 1):
        w = 1 - l / (lags + 1)
        s += 2 * w * (e[l:] @ e[:-l]) / n
    return mu / np.sqrt(s / n)

def ivw_weights(leg):
    """腿内逆波动权重（D2 原生）。"""
    v = leg.set_index("sym")["vol12"].reindex(leg["sym"].values)
    iv = (1.0 / v).replace([np.inf, -np.inf], np.nan).dropna()
    return (iv / iv.sum()) if len(iv) else None

def rank_weights(leg, col, descending):
    """腿内按 secondary 排序权重。descending=True → 信号值越大权重越大；
    False → 信号值越小权重越大（空头腿用于放大最弱者）。"""
    s = leg.set_index("sym")[col].reindex(leg["sym"].values).dropna()
    r = s.rank(ascending=True)                                  # r=1 为最小值
    k = (len(s) + 1 - r) if descending else r
    return k / k.sum() if len(k) else None

def build_weights(d, variant):
    d = d.dropna(subset=["MOM12"]).sort_values("MOM12", ascending=False)
    n = len(d)
    if n < MIN_XS:
        return None
    k = max(1, int(n * TOPBOT))
    hi, lo = d.head(k), d.tail(k)

    if variant == "D2":
        wl, ws = ivw_weights(hi), ivw_weights(lo)
    elif variant == "E1":                                       # secondary=mom1
        wl0, ws0 = ivw_weights(hi), ivw_weights(lo)
        rl, rs = rank_weights(hi, "mom1", True), rank_weights(lo, "mom1", False)
        wl = 0.5 * wl0.reindex(rl.index).fillna(0) + 0.5 * rl
        ws = 0.5 * ws0.reindex(rs.index).fillna(0) + 0.5 * rs
        wl, ws = wl / wl.sum(), ws / ws.sum()                   # 冻结：各腿归一毛重1
    elif variant == "E2":                                       # secondary=slope
        wl0, ws0 = ivw_weights(hi), ivw_weights(lo)
        rl, rs = rank_weights(hi, "slope", True), rank_weights(lo, "slope", False)
        wl = 0.5 * wl0.reindex(rl.index).fillna(0) + 0.5 * rl
        ws = 0.5 * ws0.reindex(rs.index).fillna(0) + 0.5 * rs
        wl, ws = wl / wl.sum(), ws / ws.sum()
    elif variant == "E3":                                       # 绝对动量门
        hi2 = hi[hi["MOM12"] > 0]
        lo2 = lo[lo["MOM12"] < 0]
        wl = ivw_weights(hi2) if len(hi2) else None
        ws = ivw_weights(lo2) if len(lo2) else None
        if wl is None and ws is None:
            return None
        w = pd.Series(0.0, index=d["sym"].values)
        if wl is not None and ws is not None:
            w.loc[wl.index] += wl
            w.loc[ws.index] -= ws
        elif wl is not None:                                    # 空腿剔空 → 另一腿满仓(毛重1)
            w.loc[wl.index] = wl / wl.abs().sum()
        else:
            w.loc[ws.index] = -ws / ws.abs().sum()
        return w, None
    elif variant == "E4":                                       # 软倾斜（中位数界）
        med = d["MOM12"].median()
        v = d.set_index("sym")["vol12"].reindex(d["sym"].values)
        iv = (1.0 / v).replace([np.inf, -np.inf], np.nan).fillna(1.0 / v.mean())
        w = pd.Series(0.0, index=d["sym"].values)
        for names, sgn in [(d["MOM12"] > med, 1.0), (d["MOM12"] <= med, -1.0)]:
            names = d["sym"].values[names.values]
            if len(names) == 0:
                continue
            core = d.set_index("sym")["MOM12"].loc[names]
            tt = (core > med).values if sgn > 0 else (core <= med).values
            wgt = iv.loc[names] * np.where(tt, 1.5, 0.5)
            w.loc[names] = sgn * wgt / wgt.sum()
        return w, None

    if wl is None or ws is None:
        return None
    # 冻结：全截面显式零记账（离腿=平仓，成本必须计入；与 v3/paper44 同口径）
    w = pd.Series(0.0, index=d["sym"].values)
    w.loc[wl.index] += wl
    w.loc[ws.index] -= ws
    return w, None

def backtest(panel, variant, base="next_r_raw", start=START):
    p = panel[panel["month"] >= pd.Timestamp(start)]
    rets, w_prev = [], pd.Series(dtype=float)
    for m, d in p.groupby("month"):
        bw = build_weights(d, variant)
        if bw is None:
            continue
        w = bw[0]
        r = d.dropna(subset=[base]).set_index("sym")[base].reindex(w.index).fillna(0)
        port = float((w * r).sum())
        to = float((w - w_prev.reindex(w.index).fillna(0)).abs().sum())
        rets.append((m, port, to)); w_prev = w
    return pd.DataFrame(rets, columns=["month", "ret", "to"])

def metrics_from(ret, to, cost):
    rc = ret - to * cost
    ann = (1 + rc).prod() ** (12 / len(rc)) - 1
    vol = rc.std() * np.sqrt(12)
    sh = rc.mean() / rc.std() * np.sqrt(12) if rc.std() > 0 else np.nan
    nav = (1 + rc).cumprod()
    dn = rc[rc < 0].std() * np.sqrt(12)
    return {"CAGR": ann, "Vol": vol, "Sharpe": sh, "Sortino": rc.mean() * 12 / dn if dn > 0 else np.nan,
            "MDD": float((nav / nav.cummax() - 1).min()), "nw_t": nw_t(rc),
            "avg_to": to.mean(), "win": (rc > 0).mean(), "n": len(rc)}

runs = {}
for v in ["D2", "E1", "E2", "E3", "E4"]:
    runs[v] = backtest(panel, v)
    assert len(runs[v]) >= 200, v

rows = []
for v, r in runs.items():
    for cname, cost in [("5bp", COST_MAIN), ("20.5bp", COST_STRESS)]:
        rows.append({"variant": v, "cost": cname, **metrics_from(r["ret"], r["to"], cost)})
res = pd.DataFrame(rows)
res.to_csv(f"{ART}/v4_metrics.csv", index=False)
print("== 主窗 RAW ==")
print(res.round(4).to_string(index=False))

m_d2 = metrics_from(runs["D2"]["ret"], runs["D2"]["to"], COST_MAIN)
sh_d2, mdd_d2 = m_d2["Sharpe"], m_d2["MDD"]
print(f"\n基线 D2: Sharpe {sh_d2:.4f}, MDD {mdd_d2:.4f}")

tests, verdicts = [], {}
for v in ["E1", "E2", "E3", "E4"]:
    m = metrics_from(runs[v]["ret"], runs[v]["to"], COST_MAIN)
    verdicts[v] = "PASS" if (m["Sharpe"] >= sh_d2 - 0.05 and m["MDD"] >= mdd_d2) else "NO_INCREMENT"
    dom = m["Sharpe"] > sh_d2 and m["MDD"] > mdd_d2
    j = runs["D2"].merge(runs[v], on="month", suffixes=("_d2", f"_{v}"))
    diff = (j[f"ret_{v}"] - j[f"to_{v}"] * COST_MAIN) - (j["ret_d2"] - j["to_d2"] * COST_MAIN)
    t = nw_t(diff)
    p = 2 * (1 - stats.t.cdf(abs(t), len(diff) - 1))
    tests.append({"variant": v, "verdict": verdicts[v], "dominates_d2": dom,
                  "sharpe": m["Sharpe"], "mdd": m["MDD"], "diff_nw_t": t, "p_two": p})
tst = pd.DataFrame(tests)
tst["p_bh4"] = (tst["p_two"].rank() * 4 / tst["p_two"]).clip(upper=1.0)
tst.to_csv(f"{ART}/v4_gate_tests.csv", index=False)
print("\n== 门槛裁决（vs D2 1.7599/-10.81%）==")
print(tst.round(4).to_string(index=False))

yr = pd.concat([
    pd.DataFrame({"year": r["month"].dt.year, "rc": (r["ret"] - r["to"] * COST_MAIN).values})
    .groupby("year")["rc"].apply(lambda x: (1 + x).prod() - 1).rename(v)
    for v, r in runs.items()], axis=1)
yr.to_csv(f"{ART}/v4_yearly.csv")
print("\n== 分年（5bp净）==")
print(yr.round(3).to_string())

c = pd.DataFrame({v: (r["ret"] - r["to"] * COST_MAIN).values for v, r in runs.items()},
                 index=runs["D2"]["month"])
print("\n== 月收益相关 ==")
print(c.corr().round(3).to_string())
c.to_csv(f"{ART}/v4_monthly_net.csv")

json.dump({"variants": ["E1_D2_MOMTS", "E2_D2_TSROLL", "E3_D2_ABSGATE", "E4_D2_MEDTILT50"],
           "verdicts": verdicts}, open(f"{ART}/run_meta.json", "w"), ensure_ascii=False, indent=2)
print("\nDONE")
