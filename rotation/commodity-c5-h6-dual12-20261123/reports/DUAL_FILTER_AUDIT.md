# AW7 Dual-Momentum Filter — Audit

日期：2026-11-23
对象：`aw7_commodity_dual_filter_20261123-v1`

## 结论

```text
implementation_conformance: PASS
no_lookahead_on_labels: PASS
dual6_filter: REJECT
dual12_bm5: SHADOW_ONLY
other_dual_filters: REJECT_OR_NO_INCREMENT
independent_oos: BLOCKED
production_promotion: NOT_AUTHORIZED
live_profitability: NOT_ASSESSED
```

## 检查表

| 检查 | 判据 | 实际结果 | 状态 | 证据 |
|---|---|---|---|---|
| 动能窗口 | 6/12月完整连续窗口 | tests pass | PASS | `reproduction/test_run.py` |
| 双动量资格 | ABS>0 且相对分位>=0.5 | test pass | PASS | `reproduction/test_run.py` |
| 过滤后不足3名 | 当月现金 | test pass | PASS | `reproduction/test_run.py` |
| 同日期同成本 | 所有臂同一R3标签网格 | 核对通过 | PASS | `artifacts/metrics.csv` |
| 6个月过滤 | 改善净值且不过度恶化MDD | BM5+dual6 lag1 Sharpe0.254 | FAIL | `artifacts/metrics.csv` |
| 12个月 BM5 paper-like | 5bp Sharpe至少+0.10 | +0.016, MDD -1.0pp | FAIL | `artifacts/metrics.csv` |
| 12个月 BM5 lag1 | bootstrap支持 | Sharpe+0.169 but CI[-.213,+.569], q=.658 | FAIL/UNCONFIRMED | `artifacts/bootstrap.csv` |
| 同一策略其它载体 | EW/Carry/MOM过滤不更差 | 多数变差 | FAIL | `artifacts/metrics.csv` |
| 数据 vintage | 当前修订快照 | PARTIAL | PARTIAL | `data_certificate.json` |
| 独立 OOS | 未查看样本 | 全部历史已看 | BLOCKED | `sample_access.jsonl` |

## 关键归因

- 12个月 filter 后的平均敞口为96.9%，所以优势不完全是空仓；但4个现金月仍是
  额外路径变化。
- BM5+dual12 lag1 的历史净值提升，同时组合波动从16.2%升至20.7%，风险预算变化
  需要由同风险/同平均敞口再验证。
- paper-like 与 lag1 的差异较大，不能用单一净值图宣称策略已具备执行优势。

## 处置

不进入AW7生产；只保留 `BM5+dual12` 作为后续前瞻影子候选。停止在6/12以外的窗口和
40%/50%/60%分界上搜索。
