# Validation and Limits

## 已验证

- 父 C5/RANK2 裸账本在 R1 与 parent run 的最大逐日误差：
  `9.97e-17`。
- H6 规则：gap `0.25`、BM5 浮点容差 `1e-12`、RANK2/TIP/DD继承；
- dual12：绝对动量 `>0`、相对动量上半区、合格节点少于2时现金；
- 资本融合：共同月对齐、50/50收益后漂移恢复、跨腿再平衡成本；
- 各阶段单元测试均为本地通过，源研究包通过 `check_run.py --gate audit` 结构检查。

## 关键限制

1. **数据 vintage**：商品合同/ETF快照是当前修订版本，未认证历史发布日期与修订链。
2. **代理历史**：上市前商品ETF使用期货或USO等代理；USO与160723的相关性明显偏低。
3. **映射代理**：期货组到六个ETF节点不是供应商正式crosswalk。
4. **样本**：全部历史均已查看；不是独立OOS。
5. **H6触发少**：历史上只有4次近分换序，BM5标签置换只到92%分位。
6. **月频风险**：融合策略用月末净收益，MDD不能与日频盯市MDD横比。
7. **跨载体**：H6为ETF，宽商品BM5+dual12为合同级期货代理；当前没有统一的保证金、资金流和成交账本。

## 状态

```text
production: C5 + RANK2 + TIP S + next-session DD
H6: SHADOW_ONLY
dual12 filters: REJECT
H6 + dual12 after C5/H6: REJECT
H6 + broad BM5+dual12: SHADOW_ONLY / CROSS_CARRIER
live profitability: NOT_ASSESSED
```
