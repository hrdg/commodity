# AW7 Commodity Switch Confirmation — Independent Audit

审计日期：2026-11-23
对象：`aw7_commodity_switch_confirm_20261123-v1`
范围：H5 相对换仓确认、H6 C5 近分 tie-break；六 ETF 代理、已查看历史。

## 结论

```text
implementation_conformance: PASS
accounting_reproduction: PASS
data_and_method_validity: PARTIAL
economic_increment_for_H6: CONDITIONAL_KEEP_CANDIDATE
economic_increment_for_H5: REJECT
independent_oos: BLOCKED
production_promotion: NOT_AUTHORIZED
live_profitability: NOT_ASSESSED
```

H6 在预设主指标和成本/回撤/敞口门槛上通过，但只有四次实际触发。对 BM5 节点标签做
200 次置换后，实际 Sharpe 位于第 `92%` 分位，低于常用 95% 门槛。因此统计证据不足以
支持生产替换，只足以支持冻结规则后的前瞻影子。

## 检查表

| 检查 | 判据 | 实际结果 | 状态 | 证据 |
|---|---|---|---|---|
| 实现与规格一致 | H5/H6 只改预设事件层 | 代码和测试覆盖 H5/H6、回退和浮点零差 | PASS | `reproduction/run.py`, `reproduction/test_run.py` |
| 会计与父策略 | B0 与 R1 逐日一致 | 最大误差 `9.97e-17` | PASS | `artifacts/result.json`, `logs/run.log` |
| 时点 | 月末信号、下一交易日开盘 | 执行日期与父账本一致 | PASS | `simulate`, `logs/run.log` |
| 成本 | 5bp 与 20.5bp 同方向 | H6 两个成本均改善 | PASS | `artifacts/metrics_common_window.csv` |
| 预设主指标 | H6 Sharpe 至少 +0.05 | `+0.210` | PASS | `artifacts/bootstrap.csv` |
| 回撤 guard | MDD 不恶化超过 2pp | 两者均 `-23.10%` | PASS | `artifacts/metrics_common_window.csv` |
| 敞口 guard | 平均风险敞口差 <=0.05 | H6 `57.11%` vs B0 `54.81%` | PASS | `artifacts/metrics_common_window.csv` |
| 子区间 | 不只一个子区间贡献 | 三个区间 Sharpe 均不低于 B0 | PASS | `artifacts/segments.csv` |
| 留一事件 | 去除任一 H6 事件仍优于 B0 | 四个留一 Sharpe 均 >=1.758 | PASS | `artifacts/h6_leave_one_out.csv` |
| H6 机制置换 | BM5 标签无信息；实际应接近上尾 | 仅第 92% 分位 | FAIL | `artifacts/h6_bm_permutation.csv` |
| H5 机制置换 | 匹配交易次数随机冻结 | 实际仅第 4.5% 分位 | FAIL | `artifacts/h5_placebo.csv` |
| 多重尝试 | 记录 H1–H6 与两成本 | 账本保留，未删失败 | PASS | `iterations.jsonl`, `artifacts/bootstrap.csv` |
| 数据 lineage | 当前修订代理可追溯 | 继承 R1 PARTIAL，无发布 vintage | PARTIAL | R1 `data_certificate.json` |
| 独立 OOS | 未查看且可外推的样本 | 所有历史已在 R1 查看 | BLOCKED | `sample_access.jsonl` |

## 统计解释

- 21 日 circular block bootstrap 保留了收益序列的短期依赖，但没有解决跨策略的共同
  数据路径和小事件数，不能替代独立 OOS。
- 两条候选分别在 5bp/20.5bp 做 BH 校正；H6 两个成本 q 值分别为 `0.0024` 和
  `0.0020`，但这不能抵消四次触发的低功效。
- H6 留一事件仍显示正增量，排除了“单次事件全部贡献”的简单解释；却仍可能由共同市场
  路径或 ETF 代理误差驱动。
- BM5 节点置换下，随机标签的 Sharpe 均值 `1.739`，95% 上界约 `1.855`；实际
  `1.845` 未越过 95% 上界。结论是机制支持不足，不是 H6 的收益已完全消失。

## 失败与偏差

1. 首次 H6 运行将若干 `1e-16` 级零差视作严格 BM5 优势，已加入 `1e-12` 数值容差
   并增加回归测试；这是数值实现修复，不是阈值搜索。
2. 初次运行超过预注册结束日，已改为严格截止 `2026-09-30` 并重跑。
3. H5 的相位安慰剂 realized block 数量区间为 `23—38`，无法做到每个随机相位都
   精确命中 38 次；这使 H5 安慰剂是保守的诊断，而 H5 本身已在收益和回撤上失败。

## 处置

保持生产 B0 不变。H6 仅在冻结 `0.25` 与 `1e-12` 常量后进入未来前瞻影子；
若未来影子不足以增加独立触发，或 BM5 标签置换仍弱于 95% 门槛，停止该方向。
