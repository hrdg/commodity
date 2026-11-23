# H6 Max-History Audit

日期：2026-11-23  
对象：`aw7_commodity_h6_maxhistory_20261123-v1`

## 结论

```text
implementation_conformance: PASS
strict_six_replay: PASS (9.97e-17 max error)
max_history_economic_increment: IMPORTANT_BUT_FRAGILE
permutation_test: FAIL (87.5th percentile)
independent_oos: BLOCKED
production_promotion: NOT_AUTHORIZED
```

## 检查

| 检查 | 结果 | 状态 | 证据 |
|---|---|---|---|
| 节点覆盖 | WTI/有色/金银2016起，豆粕2019起，能化2021起 | PASS | `artifacts/node_bm5_partial.csv` |
| 缺失处理 | 前二BM5缺失时不换序，不填零 | PASS | `reproduction/run.py` |
| 严格六节点对拍 | 最大日收益误差9.97e-17 | PASS | `artifacts/result.json` |
| 5bp经济增量 | Sharpe 1.306 vs 1.177 | PASS | `artifacts/metrics.csv` |
| 20.5bp | Sharpe 1.167 vs 1.022 | PASS | `artifacts/metrics.csv` |
| 回撤 | 均-24.02% | PASS | `artifacts/metrics.csv` |
| 早期增量 | 2016–2020基本无贡献，2017负 | FAIL_TO_ADD_ROBUSTNESS | `artifacts/yearly.csv` |
| BM5置换 | 实际87.5%分位 | FAIL | `artifacts/h6_bm_permutation.csv` |
| 数据vintage | 无历史发布修订链 | PARTIAL | `data_certificate.json` |
| 独立OOS | 全历史已看 | BLOCKED | `sample_access.jsonl` |

## 解释

长历史把H6的Sharpe增量从R2短窗的`+0.210`收缩到`+0.129`，方向未反转，但新增的
2016–2020阶段大多没有可用换序，2017年唯一显著新增事件为负贡献。主要正贡献仍来自
2021、2023、2024三次换仓。

长历史增加了样本月数，没有实质增加早期独立触发数，因此不自动提高统计置信。

保持生产C5不变。
