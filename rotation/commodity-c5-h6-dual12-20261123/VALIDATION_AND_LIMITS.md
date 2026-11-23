# Validation and Limits

## 已验证

- 父 C5/RANK2 裸账本在 R1 与 parent run 的最大逐日误差：
  `9.97e-17`。
- H6 规则：gap `0.25`、BM5 浮点容差 `1e-12`、RANK2/TIP/DD继承；
- dual12：绝对动量 `>0`、相对动量上半区、合格节点少于2时现金；
- 资本融合：共同月对齐、50/50收益后漂移恢复、跨腿再平衡成本；
- H6最长历史：缺失前二节点BM5时不换序、不填零；严格六节点子窗与R2日收益最大误差
  `9.97e-17`；200次BM5标签置换实际结果第`87.5%`分位；
- 各阶段单元测试均为本地通过，源研究包通过 `check_run.py --gate audit` 结构检查。

## 关键限制

1. **数据 vintage**：商品合同/ETF快照是当前修订版本，未认证历史发布日期与修订链。
2. **代理历史**：上市前商品ETF使用期货或USO等代理；USO与160723的相关性明显偏低。
3. **映射代理**：期货组到六个ETF节点不是供应商正式crosswalk。
4. **样本**：全部历史均已查看；不是独立OOS。
5. **H6触发少**：R2共同窗只有4次近分换序、置换92%分位；拉长到2016后增至6次排序换序、
   5次持仓改变，但置换反而降至87.5%分位。
6. **月频风险**：融合策略用月末净收益，MDD不能与日频盯市MDD横比。
7. **跨载体**：H6为ETF，宽商品BM5+dual12为合同级期货代理；当前没有统一的保证金、资金流和成交账本。
8. **最长历史不是OOS**：2016–2026全部已查看，且2016–2020含ETF代理段；不能把扩展样本
   重新称为独立确认。

## 状态

```text
production: C5 + RANK2 + TIP S + next-session DD
H6: SHADOW_ONLY
max-history H6: SHADOW_ONLY / VIEWED_HISTORY_NOT_OOS
dual12 filters: REJECT
H6 + dual12 after C5/H6: REJECT
H6 + broad BM5+dual12: SHADOW_ONLY / CROSS_CARRIER
live profitability: NOT_ASSESSED
```
