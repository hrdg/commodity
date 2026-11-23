# ALGORITHM — H6 / BM5 dual12 fusion

| 项目 | 内容 |
|---|---|
| 策略 ID | `aw7_commodity_h6_dual_fusion_20261123-v1` |
| 模式 | two-layer fusion study |
| 状态 | F1 reject; F2 shadow only |
| 父版本 | R2 H6 + R3 dual filter |

## 1. 策略 text 流程图

```text
F1:
six ETF month-end closes
  -> 12m abs and relative momentum
  -> eligible nodes
  -> C5/B.choose + H6 top-two BM5 swap
  -> next-open ETF return
  -> TIP S + lagged DD + 5/20.5bp

F2:
H6 daily net -> monthly return
R3 BM5+dual12 lag1 -> realized monthly return
  -> common calendar months
  -> 50/50 weights, rebalance-cost proxy
  -> monthly blend NAV
```

## 2. 数学公式

| ID | 公式 | 代码符号 | 单位/时点 | 来源 |
|---|---|---|---|---|
| F1 | `M12_i=P_i,t/P_i,t-12-1` | `mom12` | month-end | local |
| F2 | `eligible_i=1[M12_i>0 and pct_rank>=.5]` | `absolute`, `dual` | month-end | dual |
| F3 | `C5_i=slope25_i*R2_250,i` | `c5_signal` | month-end | current |
| F4 | `swap=1[z1-z2<=.25 and BM5_2-BM5_1>1e-12]` | `apply_h6_near_tie` | month-end | H6 |
| F5 | `r_blend=.5*r_H6+.5*r_DUAL - cost*turnover` | `FUSION50` | monthly | local |

## 3. 变量状态图与时间契约

```text
ETF_WARMUP -> ETF_ELIGIBLE -> C5_RANKED -> H6_SWAP -> NEXT_OPEN -> POSITION
                         \-> fewer than 2 -> CASH

H6_MONTH + DUAL_MONTH -> COMMON_MONTH -> 50/50 -> REBALANCE_COST -> BLEND_NAV
```

## 4. 规格—代码—测试映射

| 项 | 代码 | 测试/日志 | 状态 |
|---|---|---|---|
| ETF双动量 | `monthly_eligibility` | `test_monthly_eligibility_combines_absolute_and_relative` | PASS |
| H6换序 | `M.apply_h6_near_tie` | `test_h6_rule_uses_only_eligible_top_two` | PASS |
| 50/50 | `main` F2 | `test_fixed_monthly_blend` | PASS |
| 成本与日期 | `daily_metrics`,`monthly_metrics` | `logs/run.log` | PASS |

## 5. 结果、验收与偏差

F1 `DUAL12_H6` Sharpe `1.536`，低于原H6 `1.845`；但高于 `DUAL12_C5` `1.471`。
F2 50/50 Sharpe `1.377` vs H6 monthly `1.153` and BM5_DUAL12 `0.628`；correlation
`-0.16`，但F2 vs H6 CI crosses zero。裁决：F1 REJECT，F2 SHADOW_ONLY。

## 6. 归档索引

见 `archive_manifest.json`。核心结果在 `artifacts/result.json`、`metrics_f1.csv`、
`metrics_f2.csv`、两个bootstrap文件和`nav_fusion.png`。
