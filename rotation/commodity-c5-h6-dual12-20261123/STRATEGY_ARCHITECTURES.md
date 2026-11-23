# Strategy Text Architectures

所有可用时点均为月末收盘；成交与风险层按各策略单独标注。

## 1. 六商品 C5/RANK2/TIP/DD

```text
六ETF open/close（上市前使用冻结代理）
  -> C5_i = 25日对数价格OLS斜率 × 250日 R²
  -> B.choose:
       C5截面排序
       10日涨幅>0.10时锁定40日
       现仓仍在前2且z差<=0.25时，效率/Beta恶化可保留现仓
  -> 单一商品目标
  -> 下一交易日开盘买入
  -> TIP S月频开关
  -> DD：上一收盘净值触发 -8%减半、-12%清仓、-7%恢复
  -> 风险关闭部分转511260
  -> 5/20.5bp 单边成本
```

关键：`RANK2` 是换仓缓冲，不是持有两个商品。

代码：`code/c5_rank2_tipdd_run.py`、`code/c5_event_audit.py`
配置：`configs/c5_rank2_tipdd.strategy.json`

## 2. 原 H6

```text
六ETF月末 C5 分数
  -> C5 前二名
  -> z1-z2 <= 0.25?
  -> 且 BM5(second)-BM5(first) > 1e-12?
  -> 交换前二，仅此一处
  -> 原 B.choose/RANK2/TIP/DD
  -> 下一交易日开盘
```

BM5 为过去五个月、不含当月的 first/second-nearby 复合收益差。

代码：`code/h6_switch_run.py`
配置：`configs/h6.strategy.json`

## 3. dual12后C5

```text
六ETF 12个月收益
  -> relative percentile >= 0.5
  -> absolute return > 0
  -> eligible nodes
  -> 只在eligible集合内做C5排名
  -> RANK2/TIP/DD
  -> 下一交易日开盘
```

合格节点少于2个时当月商品目标为现金。

代码：`code/h6_dual_fusion_run.py` 的 `DUAL12_C5` 分支
结果：`results/h6_dual_fusion_metrics_f1.csv`

## 4. dual12后H6

```text
dual12 eligibility
  -> eligible C5 前二
  -> near gap + BM5 tie-break
  -> 原 RANK2/TIP/DD
  -> 下一交易日开盘
```

代码：`code/h6_dual_fusion_run.py` 的 `DUAL12_H6` 分支
结果：`results/h6_dual_fusion_metrics_f1.csv`

## 5. H6 + dual12后C5

```text
Sleeve A：H6 月净收益
Sleeve B：dual12后C5 月净收益
  -> common realized months
  -> 50/50
  -> 月末恢复到50/50并计跨腿成本
```

代码：`code/sleeve_b_run.py` (`H6_PLUS_DUAL12_C5`)
结果：`results/sleeve_b_metrics.csv`

## 6. H6 + dual12后H6

```text
Sleeve A：H6 月净收益
Sleeve B：dual12后H6 月净收益
  -> common realized months
  -> 50/50
  -> 月末恢复到50/50并计跨腿成本
```

代码：`code/sleeve_b_run.py` (`H6_PLUS_DUAL12_H6`)
结果：`results/sleeve_b_metrics.csv`

## 7. H6 + 宽商品 BM5+dual12

```text
Sleeve A：六ETF H6 月净收益
Sleeve B：47合同商品 BM5+dual12(lag1) 月净收益
  -> common months 2021-02—2026-09
  -> 50/50
  -> 跨腿再平衡成本
```

这是跨执行载体的资本层研究组合，不是单一ETF策略。

代码：`code/h6_dual_fusion_run.py` (`FUSION50`)
结果：`results/h6_dual_fusion_metrics_f2.csv`
