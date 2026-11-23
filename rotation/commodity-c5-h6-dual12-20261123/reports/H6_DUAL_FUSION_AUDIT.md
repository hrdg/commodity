# H6 + BM5 Dual12 Fusion — Audit

日期：2026-11-23
对象：`aw7_commodity_h6_dual_fusion_20261123-v1`

## 结论

```text
F1 implementation: PASS
F1 economic result: FAIL
H6 conditional lift inside filtered universe: PASS but insufficient
F2 monthly diversification: SUPPORTED_IN_HISTORY
F2 statistical confirmation vs H6: NOT_CONFIRMED
single-live-carrier feasibility: BLOCKED
independent_oos: BLOCKED
production_promotion: NOT_AUTHORIZED
```

## 检查

| 检查 | 结果 | 状态 | 证据 |
|---|---|---|---|
| 六ETF双动量资格 | 每月按12月ETF收益计算绝对+相对过滤 | PASS | `reproduction/run.py`, `artifacts/eligibility.csv` |
| H6只在过滤后前二换序 | 正确调用冻结H6规则 | PASS | `reproduction/test_run.py` |
| B0/H6父账本 | 与R2共同窗口一致 | PASS | `artifacts/metrics_f1.csv` |
| F1成本 | 5/20.5bp均运行 | PASS | `artifacts/metrics_f1.csv` |
| F1预设增量 | 过滤后组合优于原H6 | DUAL12_H6 1.536 < H6 1.845 | FAIL | `artifacts/metrics_f1.csv` |
| H6局部增量 | 过滤后H6优于过滤后C5 | +0.065 Sharpe | PASS/INSUFFICIENT | `artifacts/bootstrap_f1.csv` |
| F2对齐 | 两端转月末并取共同月 | 68月 | PASS | `artifacts/returns_f2_monthly.csv` |
| F2相关 | 应实质低于1 | -0.16 | PASS | `artifacts/metrics_f2.csv` |
| F2 Sharpe | 高于两条腿 | 1.377 > 1.153 > .628 | IN_HISTORY | `artifacts/metrics_f2.csv` |
| F2 bootstrap vs H6 | 需显著 | 95% CI `[-.158,+.721]`, q=.201 | FAIL | `artifacts/bootstrap_f2.csv` |
| 可执行载体 | 同一平台/成本/保证金 | H6 ETF vs 期货代理不同载体 | BLOCKED | `REPORT.md` |
| 独立OOS | 未查看样本 | 无 | BLOCKED | `sample_access.jsonl` |

## 解释与处置

F1证明 H6 是**局部有价值、全局不能救错误过滤**：在双动量筛选后的子集里，H6比较
未过滤C5有约0.065 Sharpe增量；但筛选本身删掉了过多反弹收益。

F2的负相关可能提供真实分散化，但月频指标和两套执行账本不能等价成可交易单策略。
由于相对较强基准H6的统计区间跨零，分类为`SHADOW_ONLY`。

保持生产C5/RANK2/TIP/DD不变。
