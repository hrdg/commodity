# Sleeve B Variant Audit

日期：2026-11-23
对象：`aw7_commodity_sleeveb_fusion_20261123-v1`

## 结论

```text
implementation_conformance: PASS
same-carrier B1/B2 diversification: FAIL
dual12_H6_vs_dual12_C5_incremental: small and insignificant
broad BM5+dual12 remains preferred Sleeve B: YES_IN_HISTORY
independent OOS: BLOCKED
production_promotion: NOT_AUTHORIZED
```

## 检查表

| 检查 | 结果 | 状态 | 证据 |
|---|---|---|---|
| 月收益转换 | 日频收益按月复合，3条腿共同68月 | PASS | `artifacts/returns_monthly.csv` |
| 再平衡成本 | 50/50收益后漂移恢复目标并计成本 | PASS | `reproduction/test_run.py` |
| H6与B1相关 | 0.930 | PASS（高重合） | `artifacts/correlations.csv` |
| H6与B2相关 | 0.936 | PASS（高重合） | `artifacts/correlations.csv` |
| B1组合 vs H6 | Sharpe 1.045<1.153 | FAIL | `artifacts/metrics.csv` |
| B2组合 vs H6 | Sharpe1.061<1.153 | FAIL | `artifacts/metrics.csv` |
| B2 vs B1增量 | +0.016 Sharpe, CI跨零 | NO_INCREMENT | `artifacts/bootstrap.csv` |
| 宽商品B3 | Sharpe1.377, corr -0.16 | BEST_IN_HISTORY | `artifacts/metrics.csv` |
| 独立OOS | 无 | BLOCKED | `sample_access.jsonl` |

## 处置

不采用同载体B1/B2作为H6的资本层增强。B2可作为“如果必须ETF-only”时的收益优先研究，
B1可作为回撤优先研究，但均不升级生产。宽商品B3仅保留影子研究。
