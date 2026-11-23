# Pre-reproduction gate — H6 maximum-history extension

冻结时间：2026-11-23。此扩展只把 H6 的可用历史拉长，不修改其经济规则。

## 1. 基准/待复现策略 text 架构

```text
six ETF daily closes
  -> C5 = OLS log-price slope25 × R2_250
  -> original B.choose / RANK2 / take-profit lock
  -> H6:
       current C5 top two
       if both BM5 values are available:
          gap = z(C5 first)-z(C5 second)
          if gap<=0.25 and BM5(second)-BM5(first)>1e-12:
             swap top two
       else:
          keep original C5 order
  -> target ETF
  -> next trading-session open
  -> TIP S, next-session DD, 5/20.5bp
```

## 2. 待改进环节

```text
[CHANGE] sample start only
  R2 strict-six H6 starts 2021-01-29 when all six BM5 nodes exist.
  Max-history H6 starts at the first month where C5 exists and at least the
  C5 top-two nodes have finite BM5, currently expected 2016-01-29.

[KEEP]
  C5 formula/order, H6 gap=0.25, BM tolerance=1e-12,
  RANK2, TIP S, next-session DD, transaction costs, ETF universe.

[MISSING]
  If either top-two BM5 is missing, no H6 swap. Never fill BM5 with zero.
```

The node history is:

| node | first valid BM5 |
|---|---|
| WTI/160723 | 2016-01-29 |
| meal/159985 | 2019-07-31 |
| metals/159980 | 2016-01-29 |
| chemicals/159981 | 2021-01-29 |
| gold/518880 | 2016-01-29 |
| silver/161226 | 2016-01-29 |

## 3. 公式

| ID | 公式 | 符号/单位 | 时点 |
|---|---|---|---|
| F1 | `C5_i=OLS_slope25(logP_i)*R2_250` | score | month-end |
| F2 | `BM5_i=prod(1+r1)-prod(1+r2)` over t-5..t-1 | decimal | month-end |
| F3 | `swap=1[BM5_1 finite and BM5_2 finite and gap<=.25 and BM5_2-BM5_1>1e-12]` | bool | month-end |
| F4 | `ret_net=weighted commodity/bond return-cost` | daily decimal | next-open path |

## 4. 直觉逻辑

如果 H6 的三次有效换序只是 2021 后局部行情，那么加入2016–2020的独立早期路径会稀释其
Sharpe；如果 BM5 近分换序确实有跨周期信息，长历史应保留相似方向的增量，并把触发样本
从4次扩展到更多事件。

## 5. 竞争解释与反证

| 竞争解释 | 可区分现象 | 反证 |
|---|---|---|
| H6只依赖4次幸运事件 | 长历史Sharpe增量显著弱化 | 包含早期样本后超额消失 |
| TIP/DD路径驱动 | NODD与TIP/DD增量不一致 | 扣风险层后无增量 |
| 缺失节点导致选择偏差 | 早期可换序样本集中在少数资产 | 分年份、分节点贡献不稳 |
| C5本身主导 | H6与B0高相关 | 长历史相关性>0.99且增量小 |

验收：

- 最长窗口从首个C5+BM5可用月开始，主结束日2026-09-30；
- 5bp Sharpe相对长历史C5至少 +0.05，20.5bp同方向；
- MDD不恶化2pp；
- 当前六节点全齐子窗必须与R2 H6逐日一致（误差<1e-12）；
- 报告每一年度、每个商品腿贡献和触发次数；
- 不搜索 gap、BM5窗口或风险层参数。

## 6. 有界实验与验收

只跑：

1. `B0_C5_MAXHISTORY`：C5/RANK2/TIP/DD，2016–2026；
2. `H6_MAXHISTORY`：前二 BM5 可得时启用 H6；
3. `B0_C5_STRICT2021` 与 `H6_STRICT2021`：保持R2原六节点全齐窗口，作为对拍；
4. NODD/TIPDD × 5/20.5bp；
5. 200次 BM5 标签置换，每月只置换可用节点；
6. 逐年绩效和 H6触发/实际换手变化。

停止条件：上述臂和长历史诊断完成即停止。
