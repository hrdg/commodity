# -*- coding: utf-8 -*-
"""
中国改造版架构 v2：H-A 多窗动量 / H-B 波动率目标 / H-C 残差动量。
PRE_REGISTER.md 冻结口径，单遍执行。基线 S1 与上 run 逐位一致（同面板同逻辑）。
"""
import os
import json
import numpy as np
import pandas as pd
from scipy import stats

PREV = "/Users/hsh/Documents/Quant/科技轮动/research/runs/aw7_commodity_bm_mainchain_20261124/artifacts"
RUN = "/Users/hsh/Documents/Quant/科技轮动/research/runs/aw7_commodity_mom_arch_v2_20261124"
ART = f"{RUN}/artifacts"
os.makedirs(ART, exist_ok=True)

COST_MAIN, COST_STRESS = 0.0005, 0.00205
MIN_XS, TOPBOT = 8, 1 / 3
TARGET_VOL, CAP_M = 0.12, 1.5          # 冻结：B 的波动率目标与杠杆上限
START = "2006-01-01"

panel = pd.read_csv(f"{PREV}/monthly_panel.csv", parse_dates=["month"])
panel = panel.sort_values(["sym", "month"]).reset_index(drop=True)

# ---- 信号构建（冻结） ----
g = panel.groupby("sym")
for w in [3, 6]:
    panel[f"MOM{w}"] = panel.groupby("sym")["r_ex"].transform(
        lambda x: (1 + x).rolling(w).apply(np.prod, raw=True) - 1)
panel["ds6"] = panel["slope"] - panel["slope_lag6"]

def xz(s):
    """截面 z 标准化。"""
    mu, sd = s.mean(), s.std()
    return (s - mu) / sd if sd and not np.isnan(sd) else s * np.nan

def build_signal(panel, variant):
    if variant == "A":
        def f(d):
            z = pd.concat([xz(d["MOM3"]), xz(d["MOM6"]), xz(d["MOM12"])], axis=1)
            z.columns = ["z3", "z6", "z12"]
            return z.mean(axis=1, skipna=False)     # 冻结：三者均非缺失
        return f, ["MOM3", "MOM6", "MOM12"]
    if variant == "C":
        def f(d):
            d2 = d.dropna(subset=["MOM12", "ds6"])
            if len(d2) < MIN_XS:
                return pd.Series(np.nan, index=d.index)
            X = np.column_stack([np.ones(len(d2)), d2["ds6"]])
            beta, *_ = np.linalg.lstsq(X, d2["MOM12"].values, rcond=None)
            return pd.Series(d2["MOM12"].values - X @ beta, index=d2.index)
        return f, ["MOM12", "ds6"]
    # S1 / B 共用
    return lambda d: d["MOM12"], ["MOM12"]

def nw_t(x, lags=3):
    x = np.asarray(x, float); n = len(x); mu = x.mean(); e = x - mu
    s = (e @ e) / n
    for l in range(1, lags + 1):
        w = 1 - l / (lags + 1)
        s += 2 * w * (e[l:] @ e[:-l]) / n
    return mu / np.sqrt(s / n)

def hl_weights(d, sig):
    """S1 骨架：HL 1/3 等权。sig 为与 d 对齐的 Series。"""
    d = d.assign(_sig=sig).dropna(subset=["_sig"]).sort_values("_sig", ascending=False)
    n = len(d)
    if n < MIN_XS:
        return None
    k = max(1, int(n * TOPBOT))
    w = pd.Series(0.0, index=d["sym"].values)
    w.loc[d.head(k)["sym"].values] = 1 / k
    w.loc[d.tail(k)["sym"].values] = -1 / k
    return w

def backtest(panel, variant, base="next_r_raw", start=START):
    sig_f, needs = build_signal(panel, variant)
    p = panel[panel["month"] >= pd.Timestamp(start)]
    rets, w_prev, hist = [], pd.Series(dtype=float), []
    for m, d in p.groupby("month"):
        w = hl_weights(d, sig_f(d))
        if w is None:
            continue
        if variant in ("B",):
            if len(hist) >= 6:
                vol = np.std(hist[-12:], ddof=1) * np.sqrt(12)
                m_sc = min(CAP_M, TARGET_VOL / vol) if vol > 0 else 1.0
            else:
                m_sc = 1.0                       # 冻结：历史不足 6 个月 m=1
            w = w * m_sc
        r = d.dropna(subset=[base]).set_index("sym")[base].reindex(w.index).fillna(0)
        port = float((w * r).sum())
        to = float((w - w_prev.reindex(w.index).fillna(0)).abs().sum())
        net = port - to * COST_MAIN
        rets.append((m, port, to, net)); w_prev = w
        if variant in ("B",):
            hist.append(net)
    return pd.DataFrame(rets, columns=["month", "ret", "to", "net"])

def metrics(net, to, cost):
    rc = net - (to - to) * cost + net * 0  # net 已含 5bp；压力口径需重算
    raise RuntimeError("unused")

def metrics_from(ret, to, cost):
    rc = ret - to * cost
    ann = (1 + rc).prod() ** (12 / len(rc)) - 1
    vol = rc.std() * np.sqrt(12)
    sh = rc.mean() / rc.std() * np.sqrt(12) if rc.std() > 0 else np.nan
    nav = (1 + rc).cumprod()
    return {"CAGR": ann, "Vol": vol, "Sharpe": sh, "MDD": float((nav / nav.cummax() - 1).min()),
            "nw_t": nw_t(rc), "avg_to": to.mean(), "n": len(rc)}

# ---- 基线 S1 + 三变体 ----
runs = {}
for v in ["S1", "A", "B", "C"]:
    runs[v] = backtest(panel, v)
    assert len(runs[v]) >= 200, f"{v} 月数不足"

rows = []
for v, r in runs.items():
    for cname, cost in [("5bp", COST_MAIN), ("20.5bp", COST_STRESS)]:
        rows.append({"variant": v, "cost": cname, **metrics_from(r["ret"], r["to"], cost)})
res = pd.DataFrame(rows)
res.to_csv(f"{ART}/v2_metrics.csv", index=False)
print("== 主窗 RAW（5bp / 20.5bp）==")
print(res.round(4).to_string(index=False))

# ---- 门槛裁决 ----
s1 = runs["S1"]
sh_s1 = metrics_from(s1["ret"], s1["to"], COST_MAIN)["Sharpe"]
mdd_s1 = metrics_from(s1["ret"], s1["to"], COST_MAIN)["MDD"]
print(f"\n基线 S1: Sharpe {sh_s1:.3f}, MDD {mdd_s1:.4f}")

tests, verdicts = [], {}
for v, gate in [("A", "G-A"), ("C", "G-C")]:
    r = runs[v]
    m = metrics_from(r["ret"], r["to"], COST_MAIN)
    ok = m["Sharpe"] >= sh_s1 - 0.05 and m["MDD"] > mdd_s1
    verdicts[v] = "PASS" if ok else "NO_INCREMENT"
    j = s1.merge(r, on="month", suffixes=("_s1", f"_{v}"))
    diff = (j["ret_s1"] - j["to_s1"] * COST_MAIN) - (j[f"ret_{v}"] - j[f"to_{v}"] * COST_MAIN)
    t = nw_t(diff)
    tests.append({"gate": gate, "variant": v, "sharpe": m["Sharpe"], "mdd": m["MDD"],
                  "verdict": verdicts[v], "diff_nw_t": t,
                  "p_one": 1 - stats.t.cdf(abs(t), len(diff) - 1)})
# G-B
r = runs["B"]; m = metrics_from(r["ret"], r["to"], COST_MAIN)
mdd_ok = m["MDD"] >= mdd_s1 * 0.8
verdicts["B"] = ("PASS" if mdd_ok and m["Sharpe"] >= sh_s1 else
                 "PARTIAL" if mdd_ok else "REJECT")
tests.append({"gate": "G-B", "variant": "B", "sharpe": m["Sharpe"], "mdd": m["MDD"],
              "verdict": verdicts["B"], "diff_nw_t": np.nan, "p_one": np.nan})
tst = pd.DataFrame(tests)
tst["p_bh3"] = (tst["p_one"].rank() * 3 / tst["p_one"]).clip(upper=1.0)
tst.to_csv(f"{ART}/v2_gate_tests.csv", index=False)
print("\n== 门槛裁决 ==")
print(tst.round(4).to_string(index=False))

# ---- 分年 + 相关 ----
yr_rows = []
for v, r in runs.items():
    rc = r["ret"] - r["to"] * COST_MAIN
    ydf = pd.DataFrame({"year": r["month"].dt.year, "rc": rc.values})
    yr_rows.append(ydf.groupby("year")["rc"].apply(lambda x: (1 + x).prod() - 1).rename(v))
yr = pd.concat(yr_rows, axis=1)
yr.to_csv(f"{ART}/v2_yearly.csv")
print("\n== 分年（5bp净）==")
print(yr.round(3).to_string())

print("\n== 月收益相关（5bp净）==")
c = pd.DataFrame({v: (r["ret"] - r["to"] * COST_MAIN).values for v, r in runs.items()},
                 index=runs["S1"]["month"])
print(c.corr().round(3).to_string())
c.to_csv(f"{ART}/v2_monthly_net.csv")

json.dump({"variants": ["A_MOM36_12_HL", "B_S1_VOLTARGET", "C_MOM12_RES_HL"],
           "verdicts": verdicts, "target_vol": TARGET_VOL, "cap_m": CAP_M},
          open(f"{ART}/run_meta.json", "w"), ensure_ascii=False, indent=2)
print("\nDONE")
