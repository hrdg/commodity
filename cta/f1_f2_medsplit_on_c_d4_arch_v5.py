# -*- coding: utf-8 -*-
"""
架构 v5：把 E4 的中位分割移植到 C（F1）和 D4（F2）。
PRE_REGISTER.md 冻结口径，单遍执行。信号/权重/风控层与 v3 的 C/D4 逐字一致，只改分割层。
"""
import os
import json
import numpy as np
import pandas as pd
from scipy import stats

PREV = "/Users/hsh/Documents/Quant/科技轮动/research/runs/aw7_commodity_bm_mainchain_20261124/artifacts"
RUN = "/Users/hsh/Documents/Quant/科技轮动/research/runs/aw7_commodity_mom_arch_v5_20261124"
ART = f"{RUN}/artifacts"
os.makedirs(ART, exist_ok=True)

COST_MAIN, COST_STRESS = 0.0005, 0.00205
MIN_XS = 8
TARGET_VOL, CAP_M = 0.12, 1.5
START = "2006-01-01"

panel = pd.read_csv(f"{PREV}/monthly_panel.csv", parse_dates=["month"])
panel = panel.sort_values(["sym", "month"]).reset_index(drop=True)
panel["ds6"] = panel["slope"] - panel["slope_lag6"]

def residual_sig(d):
    """C/D4: MOM12 ⊥ ds6 截面残差（与 v3 逐字一致）。"""
    d2 = d.dropna(subset=["MOM12", "ds6"])
    if len(d2) < MIN_XS:
        return pd.Series(np.nan, index=d.index)
    X = np.column_stack([np.ones(len(d2)), d2["ds6"]])
    beta, *_ = np.linalg.lstsq(X, d2["MOM12"].values, rcond=None)
    return pd.Series(d2["MOM12"].values - X @ beta, index=d2.index)

def nw_t(x, lags=3):
    x = np.asarray(x, float); n = len(x); mu = x.mean(); e = x - mu
    s = (e @ e) / n
    for l in range(1, lags + 1):
        w = 1 - l / (lags + 1)
        s += 2 * w * (e[l:] @ e[:-l]) / n
    return mu / np.sqrt(s / n)

def build_weights_median(d):
    """F1/F2：残差信号 + 中位数分割 + 腿内等权。全截面显式零记账。"""
    sig = residual_sig(d)
    d = d.assign(_sig=sig).dropna(subset=["_sig"])
    n = len(d)
    if n < MIN_XS:
        return None
    med = d["_sig"].median()
    hi = d[d["_sig"] > med]["sym"].values
    lo = d[d["_sig"] <= med]["sym"].values
    w = pd.Series(0.0, index=d["sym"].values)
    if len(hi):
        w.loc[hi] = 1 / len(hi)
    if len(lo):
        w.loc[lo] = -1 / len(lo)
    return w

def backtest(panel, variant, base="next_r_raw", start=START):
    p = panel[panel["month"] >= pd.Timestamp(start)]
    rets, w_prev, hist = [], pd.Series(dtype=float), []
    for m, d in p.groupby("month"):
        w = build_weights_median(d)
        if w is None:
            continue
        if variant == "F2":                                    # 波控（与 v3-D4 逐字一致）
            m_sc = (min(CAP_M, TARGET_VOL / (np.std(hist[-12:], ddof=1) * np.sqrt(12)))
                    if len(hist) >= 6 and np.std(hist[-12:], ddof=1) > 0 else 1.0)
            w = w * m_sc
        r = d.dropna(subset=[base]).set_index("sym")[base].reindex(w.index).fillna(0)
        port = float((w * r).sum())
        to = float((w - w_prev.reindex(w.index).fillna(0)).abs().sum())
        net = port - to * COST_MAIN
        rets.append((m, port, to, net)); w_prev = w
        if variant == "F2":
            hist.append(net)
    return pd.DataFrame(rets, columns=["month", "ret", "to", "net"])

def metrics_from(ret, to, cost):
    rc = ret - to * cost
    ann = (1 + rc).prod() ** (12 / len(rc)) - 1
    vol = rc.std() * np.sqrt(12)
    sh = rc.mean() / rc.std() * np.sqrt(12) if rc.std() > 0 else np.nan
    nav = (1 + rc).cumprod()
    dd = nav / nav.cummax() - 1
    underwater = (dd < -1e-9).astype(int)
    streak = underwater * (underwater.groupby((underwater != underwater.shift()).cumsum()).cumcount() + 1)
    return {"CAGR": ann, "Vol": vol, "Sharpe": sh,
            "MDD": float(dd.min()), "K": ann / abs(float(dd.min())) if dd.min() < 0 else np.nan,
            "nw_t": nw_t(rc), "avg_to": to.mean(), "n": len(rc),
            "win": float((rc > 0).mean()),
            "max_dd_months": int(streak.max())}

# ---- 基座对账数据（v2 落盘 C、v3 落盘 D4，用于差值检验与相关性）----
V2F = "/Users/hsh/Documents/Quant/科技轮动/research/runs/aw7_commodity_mom_arch_v2_20261124/artifacts/v2_monthly_net.csv"
V3F = "/Users/hsh/Documents/Quant/科技轮动/research/runs/aw7_commodity_mom_arch_v3_20261124/artifacts/v3_monthly_net.csv"
base_nets = {}
if os.path.exists(V2F):
    base_nets["C"] = pd.read_csv(V2F, parse_dates=["month"]).set_index("month")["C"]
if os.path.exists(V3F):
    base_nets["D4"] = pd.read_csv(V3F, parse_dates=["month"]).set_index("month")["D4"]

runs = {}
for v in ["F1", "F2"]:
    runs[v] = backtest(panel, v)
    assert len(runs[v]) >= 200

rows = []
for v, r in runs.items():
    for cname, cost in [("5bp", COST_MAIN), ("20.5bp", COST_STRESS)]:
        rows.append({"variant": v, "cost": cname, **metrics_from(r["ret"], r["to"], cost)})
res = pd.DataFrame(rows)
res.to_csv(f"{ART}/v5_metrics.csv", index=False)
print("== v5 主窗 RAW ==")
print(res.round(4).to_string(index=False))

# ---- 与基座逐项对比（C/F1，D4/F2）----
BASES = {"F1": ("C", 1.5987, -0.1472), "F2": ("D4", 1.6557, -0.1240)}   # v2/v3 REPORT 冻结值
net = pd.DataFrame({v: runs[v].set_index("month")["net"] for v in runs})
for v, bname, *_ in [(k, val[0]) for k, val in BASES.items()]:
    if bname in base_nets:
        j = net[[v]].join(base_nets[bname].rename(bname), how="inner").dropna()
        if len(j):
            dt = nw_t(j[v] - j[bname])
            rho = stats.pearsonr(j[v], j[bname]).statistic
            print(f"\n{v} vs {bname}: 月差值 NW t = {dt:.2f}, 相关 {rho:.3f}, n={len(j)}")

# ---- 分年表 ----
print("\n== 分年净收益 ==")
yr = net.copy()
yr["year"] = yr.index.year
print((yr.groupby("year").agg(**{v: (v, lambda x: (1 + x).prod() - 1) for v in runs}) * 100).round(1).to_string())

# ---- 门槛裁决 ----
print("\n== 冻结门槛 ==")
for v, (bname, b_sh, b_mdd) in BASES.items():
    m = metrics_from(runs[v]["ret"], runs[v]["to"], COST_MAIN)
    mdd_impr = (abs(m["MDD"]) - abs(b_mdd)) / abs(b_mdd)          # >0 为更深
    ok_sh, ok_mdd = m["Sharpe"] >= b_sh - 0.10, mdd_impr <= -0.20
    dom = m["Sharpe"] >= b_sh and ok_mdd
    verdict = "DOMINATES" if dom else ("PASS" if (ok_sh and ok_mdd) else "NO_INCREMENT/REJECT")
    print(f"{v} vs {bname}: Sharpe {m['Sharpe']:.3f} (基座 {b_sh:.3f}, {'+' if m['Sharpe']-b_sh>=0 else ''}{(m['Sharpe']-b_sh)*100:.1f}%) | "
          f"MDD {m['MDD']*100:.2f}% vs {b_mdd*100:.2f}% ({mdd_impr*100:+.1f}%) => {verdict}")

json.dump({"variants": ["F1_C_MEDSPLIT", "F2_D4_MEDSPLIT"],
           "family_count_after": 20}, open(f"{ART}/v5_meta.json", "w"))
net.reset_index().to_csv(f"{ART}/v5_monthly_net.csv", index=False)
print("\n落盘: v5_metrics.csv / v5_monthly_net.csv / v5_meta.json")
