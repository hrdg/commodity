# ALGORITHM — Sleeve B alternatives

| 项目 | 内容 |
|---|---|
| 策略 ID | `aw7_commodity_sleeveb_fusion_20261123-v1` |
| 模式 | Sleeve B comparison |
| 状态 | same-carrier variants no increment |
| 父研究 | H6/dual12 fusion + dual filter |

## 1. 策略 text 流程图

```text
H6 daily net returns ───────────────────────┐
DUAL12_C5 daily net returns ───────────────┤
DUAL12_H6 daily net returns ───────────────┤
R3 BM5+dual12 lag1 monthly net returns ────┤
                                           ├─ monthly common dates
                                           → selected pair
                                           → 50/50
                                           → post-return drift
                                           → rebalance cost
```

## 2. 数学公式

| ID | 公式 | 代码 | 单位/时点 |
|---|---|---|---|
| F1 | `r_m=prod(1+r_d)-1` | `monthly_compound` | 月频 |
| F2 | `r_raw=.5*r_H6+.5*r_B` | `blend_two` | 月频 |
| F3 | `cost=c*2*|w_end-.5|` | `blend_two` | 月频 |

## 3. 变量状态图与时间契约

```text
DAILY_SLEEVE -> MONTHLY_REALIZED -> COMMON_MONTH -> BLEND
missing common month -> exclude
```

## 4. 规格—代码—测试映射

| 项 | 代码 | 测试/日志 | 状态 |
|---|---|---|---|
| 月收益转换 | `monthly_compound` | `test_common_month_alignment` | PASS |
| 50/50与再平衡成本 | `blend_two` | `test_blend_cost_is_symmetric` | PASS |
| 相关性 | `main` | `artifacts/correlations.csv` | PASS |
| 绩效 | `metric` | `artifacts/metrics.csv` | PASS |

## 5. 结果、验收与偏差

B1/B2与H6相关0.93–0.94；50/50 Sharpe分别为1.045/1.061，低于H6的1.153。
B2相对B1增量仅0.016，CI跨零。宽商品B3与H6相关-0.16，50/50 Sharpe1.377，
仍是历史最优的Sleeve B，但跨载体。

## 6. 归档索引

见`archive_manifest.json`。
