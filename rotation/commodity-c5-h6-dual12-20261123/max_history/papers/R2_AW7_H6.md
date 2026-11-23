# R2-PACKAGE — H6 近分换序与最长历史对拍

## 1. 身份与来源

来源为 R2 research package：
`/Users/hsh/Documents/Quant/科技轮动/research/runs/aw7_commodity_switch_confirm_20261123`。
R1 提供合同级 BM5 和六节点映射，R2 提供已经冻结的 H6 near-tie 规则、下一开盘执行及
C5/RANK2/TIP/DD 账本。本页不复述成一篇外部论文，也不把本地 H6 参数归因给原文。

## 2. Text 逻辑架构

```text
month-end six-node C5 scores
  -> rank C5 and compute cross-sectional z-scores
  -> take C5 first and second
  -> require both mapped-node BM5 values
       missing either -> keep C5 order
       both present:
         gap = z1 - z2
         if gap <= 0.25 and BM5_2 - BM5_1 > 1e-12:
           swap the first two
         else:
           keep C5 order
  -> frozen B.choose / RANK2 / TIP S / next-session DD
  -> next trading-session open
  -> 5bp primary and 20.5bp stress ledger
```

## 3. 公式、单位与时点

| ID | 公式 | 单位/窗口 | 可用时点 |
|---|---|---|---|
| F1 | `C5_i=OLS_slope25(logP_i)*R2_250` | score；25/250个交易日 | 月末收盘后 |
| F2 | `z_i=(C5_i-mean(C5))/std(C5)` | 截面 z | 同一月末截面 |
| F3 | `gap=z_first-z_second` | z 差 | 同一月末截面 |
| F4 | `swap=1[both BM5 finite and gap<=0.25 and BM5_second-BM5_first>1e-12]` | boolean | 同一月末截面 |
| F5 | `ret_net=gross-cost*turnover` | 日收益，5/20.5bp单边成本 | 下一交易日开盘成交后的账本 |

最长历史扩展不改变 F1–F5。唯一变化是把 R2 的“六节点必须全部齐备”改为“C5 正常排序，
只有前二节点的 BM5 均真实可得时执行 F4”，否则回退原 C5。

## 4. 直觉与竞争解释

直觉是：C5 已经决定“哪两个商品接近领先”，BM5 只在两者分数接近时补足期限结构信息，
因此能降低错误换序而不是在全池替代趋势。竞争解释有三类：

- H6 的收益来自 2021、2023、2024 少数大事件；
- 风险层路径和持仓历史造成差异，而非月末换序本身；
- 延长到 2016–2020 只是增加空回退月份，没有增加有效识别样本。

可区分现象是：若机制跨周期有效，早期可观测换序应提供同方向贡献；若事件偶然，早期事件
会接近零或反向，且 BM5 标签置换不会达到95%分位。

## 5. 本地复现映射

`reproduction/run.py` 调用 R2 的冻结引擎 `R2M.simulate`，用 R1 的
`product_basis_momentum.csv` 重建六节点面板。`node_panel_partial` 对多合同组先做截面
z-score，再仅在组内全部有限时求均值；任何缺失保持 NaN，不填零。严格六节点窗口与 R2
日收益逐日对拍，最长窗口只增加可观测的前二 BM5 换序路径。

测试入口为 `reproduction/test_run.py`；结果分别落在 `artifacts/metrics.csv`、
`artifacts/yearly.csv`、`artifacts/h6_events.csv`、
`artifacts/h6_bm_permutation.csv` 和 `artifacts/nav_maxhistory.png`。

## 6. 结果、裁决与边界

严格六节点子窗与 R2 日收益最大误差为 `9.97e-17`。2016-02 至 2026-09：

| 成本 | C5 | H6 |
|---|---|---|
| 5bp | CAGR 28.75% / Sharpe 1.177 / MDD -24.02% | CAGR 33.06% / Sharpe 1.306 / MDD -24.02% |
| 20.5bp | CAGR 23.61% / Sharpe 1.022 / MDD -23.52% | CAGR 28.15% / Sharpe 1.167 / MDD -23.52% |

130个月中有6次 BM5 排序换序、5次实际改变持仓。200次 BM5 标签置换的实际Sharpe仅列
第87.5%分位，低于预注册95%门槛。裁决为 `KEEP_CANDIDATE / SHADOW_ONLY`：长历史方向性
增量为正，但不升级生产，也不把这批已查看历史称为独立OOS。

数据边界包括：2016–2020 ETF 历史含代理段；前二节点 BM5 不全时只能回退；供应商无历史
发布 vintage；主要正贡献集中在 2021–2024 少数事件。

## 7. 与其他论文的关系

BM5 的定义和排序窗承接 BP2019 与 Kwon等（2021），C5 及风险层承接 AW7 商品父策略。
H6 的 `gap=0.25`、BM 浮点容差 `1e-12` 和只处理 C5 前二是本地工程扩展，并非原论文直接
测试过的交易规则。与后续 R4 的关系是：R2 提供已查看历史证据，冻结后的 H6 shadow
只记录未来月份，不能把历史重新包装成前瞻确认。
