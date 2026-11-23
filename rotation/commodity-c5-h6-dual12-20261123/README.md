# AW7 Commodity C5 / H6 / Dual12

本目录发布 AW7 六商品轮动基线与后续 H6、dual momentum 和资本层融合研究。
所有结果都是历史研究，不是未来收益承诺，也不代表当前生产已经改变。

## 结论先行

| 策略 | 状态 | 说明 |
|---|---|---|
| 六商品 C5/RANK2/TIP/DD | 生产基线 | 当前商品腿逻辑，研究历史含代理段 |
| 原 H6 | 历史影子候选 | 4次触发，经济结果好但标签置换仅92%分位 |
| dual12后C5 | 否决 | 六ETF双动量过滤明显破坏C5反弹收益 |
| dual12后H6 | 否决 | H6局部有效，但不能抵消过滤损失 |
| H6 + dual12后C5 | 否决为资本增强 | 与单独H6相关0.930，混合后Sharpe下降 |
| H6 + dual12后H6 | 否决为资本增强 | 与单独H6相关0.936，仅比C5混合高0.016 Sharpe |
| H6 + 宽商品BM5+dual12 | 影子组合 | 历史分散化明显，但跨ETF/期货载体，非单一可执行策略 |

## 七个策略的代码入口

| 编号 | 策略 | 代码/配置 | 结果 |
|---|---|---|---|
| 1 | 六商品 C5/RANK2/TIP/DD | `code/c5_rank2_tipdd_run.py`, `code/c5_event_audit.py` | `results/c5_metrics.csv`, `figures/c5_nav.png` |
| 2 | 原 H6 | `code/h6_switch_run.py` | `results/h6_metrics_common_window.csv`, `figures/h6_nav.png` |
| 3 | dual12后C5 | `code/h6_dual_fusion_run.py` (`DUAL12_C5`) | `results/h6_dual_fusion_metrics_f1.csv` |
| 4 | dual12后H6 | `code/h6_dual_fusion_run.py` (`DUAL12_H6`) | `results/h6_dual_fusion_metrics_f1.csv` |
| 5 | H6 + dual12后C5 | `code/sleeve_b_run.py` (`H6_PLUS_DUAL12_C5`) | `results/sleeve_b_metrics.csv` |
| 6 | H6 + dual12后H6 | `code/sleeve_b_run.py` (`H6_PLUS_DUAL12_H6`) | `results/sleeve_b_metrics.csv` |
| 7 | H6 + 宽商品 BM5+dual12 | `code/h6_dual_fusion_run.py` (`FUSION50`) | `results/h6_dual_fusion_metrics_f2.csv` |

## 目录

```text
code/       原始研究代码快照及测试
configs/    对应 strategy.json
data/       发布所需派生面板（非原始供应商全库）
results/    指标、日/月收益、bootstrap、事件和相关性
figures/    各阶段净值图
reports/    完整报告、算法说明和审计
```

代码快照保留了原研究环境的绝对数据路径，便于审计原始实现；`data/` 中的派生面板可供
检查字段和口径，但仓库不包含所有供应商原始行情。若要在其他机器重跑，需要按各
`reports/validation/*_data_certificate.json` 恢复对应数据，或先改写 code 顶部路径常量。

## 阅读顺序

1. [七套策略 text 架构](STRATEGY_ARCHITECTURES.md)
2. [绩效表](PERFORMANCE.md)
3. [验证与限制](VALIDATION_AND_LIMITS.md)
4. [C5 基线报告](reports/C5_RANK2_TIPDD_REPORT.md)
5. [H6 报告](reports/H6_REPORT.md)
6. [dual12 过滤报告](reports/DUAL_FILTER_REPORT.md)
7. [H6/dual12 融合报告](reports/H6_DUAL_FUSION_REPORT.md)
8. [Sleeve B 比较报告](reports/SLEEVE_B_REPORT.md)
9. [文件哈希清单](MANIFEST.sha256)

## 生产边界

当前生产商品腿不变。H6 只允许继续前瞻影子；`H6 + 宽商品BM5+dual12`
仅作为设计参考，若要实施必须先建立统一ETF/期货执行、保证金、资金流与风控账本。
