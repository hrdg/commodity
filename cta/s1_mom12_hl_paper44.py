# -*- coding: utf-8 -*-
"""
论文思路 × 中国 38 商品主连策略（PRE_REGISTER.md 冻结口径，单遍执行）。
复用 aw7_commodity_bm_mainchain_20261124 的冻结面板，只做组合层组装。
"""
import os
import json
import numpy as np
import pandas as pd
from scipy import stats

PREV = "/Users/hsh/Documents/Quant/科技轮动/research/runs/aw7_commodity_bm_mainchain_20261124/artifacts"
RUN = "/Users/hsh/Documents/Quant/科技轮动/research/runs/aw7_commodity_paper44_strategy_20261124"
ART = f"{RUN}/artifacts"
os.makedirs(ART, exist_ok=True)

COST_MAIN, COST_STRESS = 0.0005, 0.00205
MIN_XS = 8
TOPBOT = 1 / 3
BM_TILT = 0.10  # 冻结：BM5 截面百分位剔除阈值（多头剔 ≥90%，空头剔 ≤10%）

panel = pd.read_csv(f"{PREV}/monthly_panel.csv", parse_dates=["month"])
panel = panel.sort_values(["sym", "month"]).reset_index(drop=True)
print(f"面板: {panel['month'].min().date()} ~ {panel['month'].max().date()}, {len(panel)} 行, "
      f"{panel['sym'].nunique()} 商品")

def nw_t(x, lags=3):
    x = np.asarray(x, float); n = len(x); mu = x.mean(); e = x - mu
    g0 = (e @ e) / n; s = g0
    for l in range(1, lags + 1):
        w = 1 - l / (lags + 1)
        s += 2 * w * (e[l:] @ e[:-l]) / n
    return mu / np.sqrt(s / n)

def weights(d, variant):
    """返回 (权重 Series)。d 为某月末截面，含 MOM12/BM5/sym。"""
    d = d.dropna(subset=["MOM12"]).sort_values("MOM12", ascending=False)
    n = len(d)
    if n < MIN_XS:
        return None
    k = max(1, int(n * TOPBOT))
    hi, lo = d.head(k), d.tail(k)
    if variant == "S2":                       # long-only
        w = pd.Series(0.0, index=d["sym"].values)
        w.loc[hi["sym"].values] = 1 / len(hi)
        return w
    if variant == "S3":                       # BM 反转 tilt
        pct = d["BM5"].rank(pct=True)         # 截面百分位（NaN 自然剔除）
        drop_hi = hi[pct.reindex(hi.index) >= 1 - BM_TILT]["sym"].values
        drop_lo = lo[pct.reindex(lo.index) <= BM_TILT]["sym"].values
        keep_hi = [s for s in hi["sym"] if s not in set(drop_hi)]
        keep_lo = [s for s in lo["sym"] if s not in set(drop_lo)]
        w = pd.Series(0.0, index=d["sym"].values)
        if keep_hi and not keep_lo:
            w.loc[keep_hi] = 1 / len(keep_hi)          # 多腿剔空空头 → 多腿满仓
        elif keep_lo and not keep_hi:
            w.loc[keep_lo] = -1 / len(keep_lo)
        elif keep_hi and keep_lo:
            w.loc[keep_hi] = 1 / len(keep_hi)
            w.loc[keep_lo] = -1 / len(keep_lo)
        return w
    # S1 / REF
    w = pd.Series(0.0, index=d["sym"].values)
    if variant == "S1":
        w.loc[hi["sym"].values] = 1 / len(hi)
        w.loc[lo["sym"].values] = -1 / len(lo)
    elif variant == "REF":
        w.loc[d["sym"].values] = 1 / n
    return w

def backtest(panel, variant, base, start):
    p = panel[panel["month"] >= pd.Timestamp(start)]
    rets, tos, w_prev = [], [], pd.Series(dtype=float)
    for m, d in p.groupby("month"):
        w = weights(d, variant)
        if w is None:
            continue
        r = d.dropna(subset=[base]).set_index("sym")[base].reindex(w.index).fillna(0)
        port = float((w * r).sum())
        to = float((w - w_prev.reindex(w.index).fillna(0)).abs().sum())
        rets.append((m, port, to)); w_prev = w
    return pd.DataFrame(rets, columns=["month", "ret", "to"])

def metrics(r, to, cost):
    rc = r - to * cost
    ann = (1 + rc).prod() ** (12 / len(rc)) - 1
    vol = rc.std() * np.sqrt(12)
    sharpe = rc.mean() / rc.std() * np.sqrt(12) if rc.std() > 0 else np.nan
    nav = (1 + rc).cumprod()
    mdd = float((nav / nav.cummax() - 1).min())
    t = nw_t(rc)
    return {"CAGR": ann, "Vol": vol, "Sharpe": sharpe, "MDD": mdd, "nw_t": t,
            "avg_to": to.mean(), "n": len(rc)}

PRIMARY_START = "2006-01-01"
rows = []
for variant in ["S1", "S2", "S3", "REF"]:
    for base, bname in [("next_r_raw", "RAW"), ("next_r_ex", "EXJUMP")]:
        for start, wname in [(PRIMARY_START, "primary2006"), ("2015-01-01", "main2015")]:
            r = backtest(panel, variant, base, start)
            if len(r) < 24:
                continue
            for cname, cost in [("5bp", COST_MAIN), ("20.5bp", COST_STRESS)]:
                rows.append({"variant": variant, "base": bname, "window": wname, "cost": cname,
                             **metrics(r["ret"], r["to"], cost)})
res = pd.DataFrame(rows)
res.to_csv(f"{ART}/strategy_metrics.csv", index=False)

print("\n== 预注册变体（主窗 primary2006，RAW，5bp）==")
m = res[(res["window"] == "primary2006") & (res["base"] == "RAW") & (res["cost"] == "5bp")]
print(m.round(4).to_string(index=False))
print("\n== 压力口径（20.5bp）==")
print(res[(res["window"] == "primary2006") & (res["base"] == "RAW") & (res["cost"] == "20.5bp")]
      .round(4).to_string(index=False))

# ---------- BH 校正（3 个预注册检验，RAW 主窗 5bp） ----------
tests = []
for v in ["S1", "S2", "S3"]:
    d = res[(res["variant"] == v) & (res["base"] == "RAW") & (res["window"] == "primary2006")
            & (res["cost"] == "5bp")]
    if len(d):
        row = d.iloc[0]
        p = 1 - stats.t.cdf(row["nw_t"], row["n"] - 1)   # 单侧：收益>0
        tests.append({"variant": v, "sharpe": row["Sharpe"], "nw_t": row["nw_t"],
                      "n": row["n"], "p_one_sided": p})
tst = pd.DataFrame(tests)
tst["p_bh"] = (tst["p_one_sided"] * len(tst) / tst["p_one_sided"].rank()).clip(upper=1.0)
tst.to_csv(f"{ART}/significance_tests.csv", index=False)
print("\n== 显著性（BH 校正，单侧）==")
print(tst.round(4).to_string(index=False))

# ---------- G2：S3 vs S1 增量 ----------
r1 = backtest(panel, "S1", "next_r_raw", PRIMARY_START)
r3 = backtest(panel, "S3", "next_r_raw", PRIMARY_START)
j = r1.merge(r3, on="month", suffixes=("_s1", "_s3"))
sh1 = metrics(r1["ret"], r1["to"], COST_MAIN)["Sharpe"]
sh3 = metrics(r3["ret"], r3["to"], COST_MAIN)["Sharpe"]
corr = stats.pearsonr(j["ret_s1"], j["ret_s3"]).statistic
print(f"\n== G2 S3-S1 增量: {sh3 - sh1:+.3f} (S1={sh1:.3f} → S3={sh3:.3f}), "
      f"月收益相关 {corr:.3f}, "
      f"{'PASS' if sh3 - sh1 >= 0.1 else 'NO_INCREMENT'} ==")

# ---------- 分年（S1/S3, RAW 主窗 5bp） ----------
yr_rows = []
for name, r in [("S1", r1), ("S3", r3)]:
    rc = r["ret"] - r["to"] * COST_MAIN
    ydf = pd.DataFrame({"year": r["month"].dt.year, "rc": rc.values})
    y = ydf.groupby("year")["rc"].apply(lambda x: (1 + x).prod() - 1)
    yr_rows.append(y.rename(name))
yr = pd.concat(yr_rows, axis=1)
yr.to_csv(f"{ART}/yearly_s1_s3.csv")
print("\n== 分年收益（S1 / S3, RAW 主窗, 5bp）==")
print(yr.round(3).to_string())

# ---------- G4：LOO（S1 RAW 主窗 5bp） ----------
base_sh = sh1
syms = panel["sym"].unique()
loo = []
for s in syms:
    sub = panel[panel["sym"] != s]
    r = backtest(sub, "S1", "next_r_raw", PRIMARY_START)
    if len(r) >= 24:
        sh = metrics(r["ret"], r["to"], COST_MAIN)["Sharpe"]
        loo.append({"dropped": s, "sharpe": sh, "delta": sh - base_sh})
loo = pd.DataFrame(loo).sort_values("delta")
loo.to_csv(f"{ART}/loo_s1.csv", index=False)
print(f"\n== G4 LOO（基线 Sharpe={base_sh:.3f}）最弱5个 ==")
print(loo.head(5).round(3).to_string(index=False))
print(f"最弱增量: {loo['delta'].min():+.3f} (G4 {'PASS' if base_sh + loo['delta'].min() > 0 else 'FAIL'})")

# 保存主窗月收益
j.to_csv(f"{ART}/monthly_returns_s1_s3.csv", index=False)
json.dump({"primary_start": PRIMARY_START, "n_commodities": int(panel["sym"].nunique()),
           "variants": ["S1_MOM12_HL", "S2_MOM12_LONG", "S3_MOM12_BMREV_HL", "REF_EW"]},
          open(f"{ART}/run_meta.json", "w"), ensure_ascii=False, indent=2)
print("\nDONE")
