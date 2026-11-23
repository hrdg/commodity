# Reproduction Index — H6 maximum history

## 研究结论

H6可前移到2016年，长历史仍优于C5，但增量收缩且标签置换仅87.5%分位。

## 逻辑脉络

```text
H6 strict-six starts 2021
  -> four BM5 nodes available from 2016
  -> missing node fallback to C5
  -> 2016-2026 max-history
  -> Sharpe +0.129 vs C5
  -> early period adds little; 2017 event negative
  -> permutation 87.5th percentile
```

## 逐篇复现索引

| ID | 来源 | 结果 |
|---|---|---|
| MAX-H6 | R1/R2 research packages | max-history extension |

独立来源页：

- [R1-PACKAGE：BM5 机制与合同节点覆盖](papers/R1_AW7_basis_momentum.md)
- [R2-PACKAGE：H6 冻结规则与严格六节点对拍](papers/R2_AW7_H6.md)

两页分别回答“BM5 从哪里来、哪些节点何时可用”和“H6 怎样在 C5 近分状态中换序”。
本 run 新增的是可用历史与缺失回退，没有新增 BM5 或 H6 参数。

## 文件导航

- `PRE_REPRO.md`
- `REPORT.md`
- `AUDIT.md`
- `ALGORITHM.md`
- `artifacts/metrics.csv`
- `artifacts/yearly.csv`
- `artifacts/h6_events.csv`

## 最快阅读顺序

1. `REPORT.md`
2. `AUDIT.md`
3. `ALGORITHM.md`
4. `artifacts/metrics.csv`

## 复现层级

- strict-six：与R2逐日复现；
- 2016–2020：部分节点，代理历史；
- 独立OOS：无。
