# AW7 Commodity C5 / H6 / Dual12

本目录发布 AW7 六商品轮动基线与后续 H6、dual momentum 和资本层融合研究。
所有结果都是历史研究，不是未来收益承诺，也不代表当前生产已经改变。

## 结论先行

| 策略 | 状态 | 说明 |
|---|---|---|
| 六商品 C5/RANK2/TIP/DD | 生产基线 | 当前商品腿逻辑，研究历史含代理段 |
| 原 H6 | 历史影子候选 | 4次触发，经济结果好但标签置换仅92%分位 |
| H6 最长历史 | 历史影子候选 | 起点前移至2016-02，Sharpe增量收缩且置换87.5%分位 |
| dual12后C5 | 否决 | 六ETF双动量过滤明显破坏C5反弹收益 |
| dual12后H6 | 否决 | H6局部有效，但不能抵消过滤损失 |
| H6 + dual12后C5 | 否决为资本增强 | 与单独H6相关0.930，混合后Sharpe下降 |
| H6 + dual12后H6 | 否决为资本增强 | 与单独H6相关0.936，仅比C5混合高0.016 Sharpe |
| H6 + 宽商品BM5+dual12 | 影子组合 | 历史分散化明显，但跨ETF/期货载体，非单一可执行策略 |

## 参考论文

这些论文提供机制或对照，不表示原文曾测试过本文的完整策略。

| 文献 | 在本文中的用途 | 原文边界 |
|---|---|---|
| Boons & Porras Prado (2019), *Basis-Momentum in the Futures Curve and Volatility Risk*, Journal of Finance, DOI [10.1111/jofi.12738](https://doi.org/10.1111/jofi.12738) | first/second-nearby basis-momentum；检验对未来 nearby 和 spread 收益的预测 | 原文使用更宽的商品期货横截面；本文后续主要映射到六ETF和47个合同品种代理 |
| Kwon, Kang & Yun (2021), *Basis-momentum strategies and ranking periods*, Finance Research Letters, DOI [10.1016/j.frl.2021.101997](https://doi.org/10.1016/j.frl.2021.101997) | 把 BM 历史拆成当前月、近五个月和更早窗口；支持使用 BM(5,1) | 排序周期研究不是六ETF交易规则；H6 的 `gap=0.25` 来自 AW7 父策略，不是本文参数 |
| Koijen, Moskowitz, Pedersen & Vrugt (2018), *Carry*, Journal of Financial Economics, DOI [10.1016/j.jfineco.2017.11.002](https://doi.org/10.1016/j.jfineco.2017.11.002) | 当前期货曲线斜率/展期收益的对照变量 | 本文没有用 Carry 作为最终商品腿主排序 |
| Moskowitz, Ooi & Pedersen (2012), *Time Series Momentum*, Journal of Financial Economics, DOI [10.1016/j.jfineco.2011.11.003](https://doi.org/10.1016/j.jfineco.2011.11.003) | 绝对动量和 time-series momentum 的机制背景 | 本文双动量过滤为本地工程规则，不是 TSMOM 原策略复现 |
| Antonacci (2012), *Risk Premia Harvesting Through Dual Momentum*, SSRN [2042750](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2042750) | “绝对动量 + 相对动量”双动量资格框架 | 本文使用固定的12个月、相对前50%与商品ETF/合同池；这些参数和载体并非原文完整移植 |

### 哪些是原论文、哪些是本项目扩展

- **原论文机制**：BP/Kwon 的 first/second-nearby BM 定义与 BM5 排序窗；Carry 的曲线斜率定义；TSMOM/双动量的绝对与相对动量概念。
- **AW7 现有基线**：六商品 ETF 上的 C5、RANK2、TIP S、下一交易日 DD。C5 来自现有公开策略/父代码，不把它归因给上述 BM 论文。
- **本项目扩展**：H6 近分换序、BM5+dual12 过滤、各策略的 50/50 月收益融合。只有明确的代码和实验结果才证明这些扩展在本历史样本中的表现。

## 改进思路与演化路径

```text
1. 现有商品腿：C5价格动量
   -> 趋势清楚时有效，但可能忽略期限结构，并依赖短周期反弹

2. BP2019 / Kwon2021：加入 first/second-nearby BM5
   -> 直接替代、50/50融合、绝对确认均未改善扣费结果

3. H6：只让BM5处理C5无法区分的近分状态
   -> 局部经济结果改善，但触发少、标签置换不达95%分位

4. H6最长历史：缺失节点不填零，仅前二BM5可得时换序
   -> 2016-02起仍有正向增量，但早期贡献弱、置换降至87.5%分位

5. dual12：先用绝对+相对动量过滤候选，再按BM5排序
   -> 47商品邻近日收益缺少稳定增量；六ETF过滤也删除过多反弹收益

6. H6 + dual12后C5/H6：同池资本融合
   -> 两条腿相关0.93–0.94，混合后跑输单独H6

7. H6 + 宽商品BM5+dual12：跨载体资本融合
   -> 月收益相关约-0.16，历史Sharpe/MDD改善
   -> 但没有统一ETF/期货执行账本、无独立OOS，所以仅保留影子
```

改进假设与对应裁决：

| 假设 | 改动层 | 裁决 |
|---|---|---|
| BM5 可以替代 C5 | 排序 | 否决：nearby/spread 与扣费结果不足 |
| BM5 可以辅助 C5 融合 | 排序 | 否决：50/50拉低 Sharpe |
| BM5 适合 C5 近分 tie-break | 事件层 | 历史影子；4次触发，92%置换分位 |
| 双动量过滤能改善 BM5 | 候选资格/预算 | 6个月否决；12个月只在特定口径局部改善 |
| H6 和 dual12 串行融合 | 排序+事件 | 否决：过滤损失大于 H6 局部增益 |
| H6 和宽商品 BM5+dual12 资本融合 | 组合/配置 | 历史影子，需统一执行和 OOS |
| H6 延长到2016–2026 | 样本层 | 方向性增量仍在，但统计识别更弱；生产不变 |

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
| 8 | H6 最长历史 | `max_history/reproduction/run.py` | `max_history/artifacts/metrics.csv`, `max_history/artifacts/nav_maxhistory.png` |

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
9. [H6 最长历史报告](max_history/REPORT.md)
10. [H6 最长历史审计](max_history/AUDIT.md)
11. [文件哈希清单](MANIFEST.sha256)

## 生产边界

当前生产商品腿不变。H6 及最长历史 H6 都只允许继续前瞻影子；`H6 + 宽商品BM5+dual12`
仅作为设计参考，若要实施必须先建立统一ETF/期货执行、保证金、资金流与风控账本。
