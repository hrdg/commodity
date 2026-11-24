# -*- coding: utf-8 -*-
"""
架构 v3 收尾：D1 slope极端连续缩放 / D2 腿内逆波动 / D3 12-1跳月 / D4 C×B组装。
PRE_REGISTER.md 冻结口径，单遍执行，本架构线最后一批变体。
"""
import os
import json
import numpy as np
import pandas as pd
from scipy import stats

PREV = "/Users/hsh/Documents/Quant/科技轮动/research/runs/aw7_commodity_bm_mainchain_20261124/artifacts"
RUN = "/Users/hsh/Documents/Quant/科技轮动/research/runs/aw7_commodity_mom_arch_v3_20261124"
ART = f"{RUN}/artifacts"
os.makedirs(ART, exist_ok=True)

COST_MAIN, COST_STRESS = 0.0005, 0.00205
MIN_XS, TOPBOT = 8, 1 / 3
TARGET_VOL, CAP_M = 0.12, 1.5
START = "2006-01-01"

panel = pd.read_csv(f"{PREV}/monthly_panel.csv", parse_dates=["month"])
panel = panel.sort_values(["sym", "month"]).reset_index(drop=True)

# ---- 冻结信号 ----
panel["MOM12_SKIP"] = (1 + panel["MOM12"]) / (1 + panel["r_ex"]) - 1      # D3: 12-1
panel["ds6"] = panel["slope"] - panel["slope_lag6"]
panel["vol12"] = panel.groupby("sym")["r_ex"].transform(
    lambda x: x.rolling(12, min_periods=6).std() * np.sqrt(12))            # D2: 逆波动

def xz(s):
    mu, sd = s.mean(), s.std()
    return (s - mu) / sd if sd and not np.isnan(sd) else s * np.nan

def residual_sig(d):
    """C: MOM12 ⊥ ds6 截面残差。"""
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

def build_weights(d, variant):
    """返回 (w Series, market_guard float)。guard 供 D1 缩放。"""
    if variant == "D1":
        sig = d["MOM12"]
        guard = float(d["BM5"].rank(pct=True).mean())          # 冻结：R̄_t
    elif variant == "D3":
        sig = d["MOM12_SKIP"]
        guard = 0.5
    elif variant == "D4":
        sig = residual_sig(d)
        guard = 0.5
    else:                                                      # S1 / D2
        sig = d["MOM12"]
        guard = 0.5
    d = d.assign(_sig=sig).dropna(subset=["_sig"]).sort_values("_sig", ascending=False)
    n = len(d)
    if n < MIN_XS:
        return None, guard
    k = max(1, int(n * TOPBOT))
    hi, lo = d.head(k), d.tail(k)
    w = pd.Series(0.0, index=d["sym"].values)
    if variant == "D2":                                        # 腿内逆波动
        v = d.set_index("sym")["vol12"].reindex(d["sym"].values)
        for leg, sgn in [(hi, 1.0), (lo, -1.0)]:
            iv = (1.0 / v.loc[leg["sym"].values]).replace([np.inf, -np.inf], np.nan).dropna()
            if len(iv):
                w.loc[iv.index] = sgn * iv / iv.sum()
    else:
        w.loc[hi["sym"].values] = 1 / len(hi)
        w.loc[lo["sym"].values] = -1 / len(lo)
    return w, guard

def backtest(panel, variant, base="next_r_raw", start=START):
    p = panel[panel["month"] >= pd.Timestamp(start)]
    rets, w_prev, hist = [], pd.Series(dtype=float), []
    for m, d in p.groupby("month"):
        w, guard = build_weights(d, variant)
        if w is None:
            continue
        if variant in ("D1",):                                 # 斜率极端连续缩放
            w = w * float(np.clip(1 - (guard - 0.5), 0.5, 1.0))
        if variant in ("D4",):                                 # C×B 组装
            m_sc = (min(CAP_M, TARGET_VOL / (np.std(hist[-12:], ddof=1) * np.sqrt(12)))
                    if len(hist) >= 6 and np.std(hist[-12:], ddof=1) > 0 else 1.0)
            w = w * m_sc
        r = d.dropna(subset=[base]).set_index("sym")[base].reindex(w.index).fillna(0)
        port = float((w * r).sum())
        to = float((w - w_prev.reindex(w.index).fillna(0)).abs().sum())
        net = port - to * COST_MAIN
        rets.append((m, port, to, net)); w_prev = w
        if variant in ("D4",):
            hist.append(net)
    return pd.DataFrame(rets, columns=["month", "ret", "to", "net"])

def metrics_from(ret, to, cost):
    rc = ret - to * cost
    ann = (1 + rc).prod() ** (12 / len(rc)) - 1
    vol = rc.std() * np.sqrt(12)
    sh = rc.mean() / rc.std() * np.sqrt(12) if rc.std() > 0 else np.nan
    nav = (1 + rc).cumprod()
    return {"CAGR": ann, "Vol": vol, "Sharpe": sh, "MDD": float((nav / nav.cummax() - 1).min()),
            "nw_t": nw_t(rc), "avg_to": to.mean(), "n": len(rc)}

runs = {}
for v in ["S1", "D1", "D2", "D3", "D4"]:
    runs[v] = backtest(panel, v)
    assert len(runs[v]) >= 200

rows = []
for v, r in runs.items():
    for cname, cost in [("5bp", COST_MAIN), ("20.5bp", COST_STRESS)]:
        rows.append({"variant": v, "cost": cname, **metrics_from(r["ret"], r["to"], cost)})
res = pd.DataFrame(rows)
res.to_csv(f"{ART}/v3_metrics.csv", index=False)
print("== 主窗 RAW ==")
print(res.round(4).to_string(index=False))

# ---- 门槛 ----
m_s1 = metrics_from(runs["S1"]["ret"], runs["S1"]["to"], COST_MAIN)
sh_s1, mdd_s1 = m_s1["Sharpe"], m_s1["MDD"]
print(f"\n基线 S1: Sharpe {sh_s1:.4f}, MDD {mdd_s1:.4f}")

tests, verdicts = [], {}
for v in ["D1", "D2", "D3", "D4"]:
    m = metrics_from(runs[v]["ret"], runs[v]["to"], COST_MAIN)
    verdicts[v] = "PASS" if (m["Sharpe"] >= sh_s1 - 0.05 and m["MDD"] > mdd_s1) else "NO_INCREMENT"
    dom = m["Sharpe"] > sh_s1 and m["MDD"] > mdd_s1
    j = runs["S1"].merge(runs[v], on="month", suffixes=("_s1", f"_{v}"))
    diff = (j["ret_s1"] - j["to_s1"] * COST_MAIN) - (j[f"ret_{v}"] - j[f"to_{v}"] * COST_MAIN)
    t = nw_t(diff)
    p = 2 * (1 - stats.t.cdf(abs(t), len(diff) - 1))
    tests.append({"variant": v, "verdict": verdicts[v], "dominates_s1": dom,
                  "sharpe": m["Sharpe"], "mdd": m["MDD"], "diff_nw_t": t, "p_two": p})
tst = pd.DataFrame(tests)
tst["p_bh4"] = (tst["p_two"].rank() * 4 / tst["p_two"]).clip(upper=1.0)
tst.to_csv(f"{ART}/v3_gate_tests.csv", index=False)
print("\n== 门槛裁决（PASS=Sharpe>=1.56且MDD更浅）==")
print(tst.round(4).to_string(index=False))

# ---- 分年 + 相关 ----
yr = pd.concat([
    pd.DataFrame({"year": r["month"].dt.year,
                  "rc": (r["ret"] - r["to"] * COST_MAIN).values})
    .groupby("year")["rc"].apply(lambda x: (1 + x).prod() - 1).rename(v)
    for v, r in runs.items()], axis=1)
yr.to_csv(f"{ART}/v3_yearly.csv")
print("\n== 分年（5bp净）==")
print(yr.round(3).to_string())

c = pd.DataFrame({v: (r["ret"] - r["to"] * COST_MAIN).values for v, r in runs.items()},
                 index=runs["S1"]["month"])
print("\n== 月收益相关 ==")
print(c.corr().round(3).to_string())
c.to_csv(f"{ART}/v3_monthly_net.csv")

json.dump({"variants": ["D1_SLOPEGUARD", "D2_INVVOL_LEG", "D3_MOM12_SKIP1", "D4_C_VOLTARGET"],
           "verdicts": verdicts}, open(f"{ART}/run_meta.json", "w"), ensure_ascii=False, indent=2)
print("\nDONE")
