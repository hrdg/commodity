# ALGORITHM — AW7 commodity switch confirmation

| 项目 | 内容 |
|---|---|
| 策略 ID | `aw7_commodity_switch_confirm_20261123-v1` |
| 规格 SHA256 | `1abe88a7860c27cd338c74eba5b1279122eae28c109df940c916007b2d5622b9` |
| 模式 | parent R1 baseline + two-rule extension |
| 状态 | `KEEP_CANDIDATE` for H6 shadow only; production unchanged |
| 父版本 | `aw7_commodity_basis_momentum_20261123-v1` |
| 数据 | R1 `AW7_COMMODITY_BASIS_PANEL_20261123`; current-revision proxy |

## 1. 策略 text 流程图

```text
月末最后共同交易日收盘
  -> ETF open/close、TIP、bond 在收盘时可用
  -> C5 = 25日斜率 × 250日R²
  -> 原 B.choose:
       C5降序
       + 10日涨幅>0.10时锁定40日
       + 现仓位于前2且z差<=0.25时执行RANK2 veto
       + 效率/E252恶化时保留现仓
  -> [H5 branch]
       若拟非止盈换仓且BM5(target)<BM5(hold) -> target=hold
  -> [H6 branch]
       若C5前二z差<=0.25且BM5(second)-BM5(first)>1e-12
       -> 先交换C5前二，再进入原B.choose
  -> 单商品目标或现金
  -> 下一交易日开盘成交
  -> 5bp主成本 / 20.5bp压力成本
  -> TIP S来自月末状态
  -> DD状态来自上一收盘nav
       -8% cut / -12% zero / -7% release
  -> risk权重持有商品，其余持511260债券
  -> 日净值

WARMUP:
  BM5不足12月历史或六节点不完整 -> 无BM信号
C5_UNAVAILABLE:
  月末C5不可得 -> 下一交易月不保留旧目标
BM_UNAVAILABLE:
  H5/H6回退到原C5决策，不插值
NO_ELIGIBLE:
  B.choose无合法目标 -> 现金
PRODUCTION:
  本run不写回生产；H6只允许影子观察
```

## 2. 数学公式

| 编号 | 公式 | 代码符号 | 符号/单位/频率 | 窗口/时点 | 来源/决定 |
|---|---|---|---|---|---|
| F1 | `S_t=trend25_t*R2_250,t` | `scores` | score | 月末收盘 | CURRENT-F1 |
| F2 | `z_t=(S_t-mean(S_t))/std(S_t)` | `z_r2` | cross-sectional z | 月末 | CURRENT-F1 |
| F3 | `BM5_t=prod_{j=t-5..t-1}(1+r1_j)-prod(1+r2_j)` | `bm5` | monthly decimal | t-5..t-1，不含t | R1-F1, KWON-F1 |
| F4 | `block_H5=1[target!=hold and BM5_target<BM5_hold]` | `h5_blocks_switch` | boolean | 非止盈换仓 | D004 |
| F5 | `near_H6=1[z_1-z_2<=0.25]` | `NEAR_TIE_GAP` | z gap | 月末前二 | D004 |
| F6 | `swap_H6=near_H6 and BM5_2-BM5_1>1e-12` | `apply_h6_near_tie` | boolean | 月末前二 | D004 |
| F7 | `ret_net=w_risk*ret_commodity+cost terms` | `ret` | daily decimal | 下一交易日 | CURRENT-F1 |
| F8 | `DD_t=nav_t/max(nav_<=t)-1` | `apply_tip_dd_lagged` | decimal | t收盘，t+1生效 | R1-F2 |

`1e-12` 是浮点比较容差，只排除数值零差，不作为收益阈值。

## 3. 变量状态图与时间契约

### 3.1 变量表

| 变量 | 含义 | 类型/单位 | 窗口 | available_at | 代码符号 | 缺失状态 |
|---|---|---|---|---|---|---|
| `close/open` | ETF价格 | price | daily | 当日收盘/开盘 | `closes/opens` | 不进入日历 |
| `C5` | 价格趋势效率分 | score | 25/250日 | 月末收盘 | `c5_daily` | 当月无目标 |
| `BM5` | 近中期期限压力 | decimal | 过去5月 | 月末收盘 | `bm5` | 回退C5 |
| `z_r2` | C5截面标准分 | z | 月末 | 月末收盘 | `z_r2` | RANK2不触发 |
| `H5_blocked` | 是否阻止换仓 | boolean | 事件 | 决策日 | `blocked` | false |
| `H6_swapped` | 是否交换前二 | boolean | 事件 | 决策日 | `swapped` | false |
| `risk_exposure` | 商品风险权重 | [0,1] | daily | 上一收盘状态 | `risk_exp` | bond |
| `hold` | 当前实际节点 | ETF/cash | monthly state | 上一成交 | `hold` | cash |

### 3.2 变量血缘图

```text
R1 contract snapshots
  -> BM5 six-node panel
  -> conditional H5/H6 event transform
                             |
ETF prices -> C5 -> z_r2 -----+-> B.choose -> target
                                           -> next-open return
                                           -> TIP/DD -> net return

TIP and bond are read at the appropriate prior close and combined
outside the event rule; H5/H6 never change the risk formula.
```

### 3.3 状态迁移图

```text
BM_WARMUP -> BM_VALID
  | missing node -> C5_FALLBACK

C5_VALID -> C5_RANKED -> B_CHOOSE
  | no C5 -> NO_NEW_TARGET -> CASH

B_CHOOSE -> H5_CHECK -> H6_TIE_BREAK -> TARGET
H5_CHECK: target!=hold and BM_target<BM_hold -> HOLD
H6_TIE_BREAK: z_gap<=0.25 and BM2>BM1 -> SWAPPED_RANK

TARGET -> ORDER_NEXT_OPEN -> POSITION
POSITION -> TIP_BOND_SPLIT -> DD_GATE -> NAV
```

## 4. 规格—代码—测试映射

| 规格/公式 | 代码入口 | 数据字段 | 测试或日志 | 状态 |
|---|---|---|---|---|
| 父 C5/RANK2 重放 | `simulate` mode=`b0` | ETF OHLC、C5 | `test_baseline_replay_matches_r1` | PASS |
| H5 相对确认 | `h5_blocks_switch` | BM5、target/hold | `test_h5_blocks_lower_bm5_candidate` | PASS |
| H5 止盈和缺失回退 | `simulate` | BM5、C5 | `test_h5_preserves_take_profit_and_missing_bm_fallback` | PASS |
| H6 0.25 近分 | `apply_h6_near_tie` | C5 z、BM5 | `test_h6_swaps_only_near_tie_when_bm5_disagrees` | PASS |
| 浮点零差保护 | `BM_TOL` | BM5 | `test_h6_does_not_trade_on_floating_zero` | PASS |
| 下一交易日执行 | `simulate` | ETF open | `logs/run.log` | PASS |
| 成本与净收益 | `simulate` | open、turnover | `artifacts/metrics_common_window.csv` | PASS |
| H5 相位安慰剂 | `h5_placebo` | event dates | `artifacts/h5_placebo.csv` | PASS |
| H6 留一事件 | `h6_leave_one_out` | H6 event dates | `artifacts/h6_leave_one_out.csv` | PASS |
| H6 BM5 标签置换 | `bm5_permute_seed` | BM5 six nodes | `artifacts/h6_bm_permutation.csv` | PARTIAL: 92nd percentile |

实现偏差与限制：

- `D-H6-EPS`：首次运行发现 BM5 近零浮点差会造成过度交换；加入 `1e-12` 比较容差，
  仅修复数值比较语义。该差异已由专门测试覆盖，未改变预设经济规则。
- H6 只有四个实际交换事件，不能把 200 次置换或单次 bootstrap 当作独立样本。
- 期货组合到 ETF 是代理映射；没有供应商历史 vintage。
- 父版本的历史已经暴露，本轮没有真正未查看 OOS。

## 5. 结果、验收与偏差

共同窗口为 2021-02-01—2026-09-30。B0 父基线 5bp 为
`CAGR 51.38% / Sharpe 1.635 / MDD -23.10%`；H6 为
`61.23% / 1.845 / -23.10%`。20.5bp 下 B0 `1.488`、H6 `1.703`。

H5 5bp 为 `12.49% / 0.639 / -45.95%`，并在匹配相位安慰剂第 `4.5%` 分位，明确否决。
H6 的配对 bootstrap 差 `+0.210`、BH q=`0.0024`，但只有 4 个触发决策；
BM5 标签置换只到第 `92%` 分位。因而 H6 是**有条件保留的研究候选**，不是生产策略。

`code_correctness=PASS`，`data/method validity=PARTIAL`（当前修订与研究代理），
`report_reproduction=PASS`（父会计、候选结果和失败均记录），
`live_profitability=NOT_ASSESSED`。

## 6. 归档索引

机器可读索引见 `archive_manifest.json`；结果与日志的哈希以该清单为准。

| 角色 | 文件 | SHA256 | 用途/边界 |
|---|---|---|---|
| communication | `PRE_REPRO.md` | `7e59c1597b18c9562abf83474c0e1057c598a2b9d74585f0f7459693ae66c9b7` | 执行前规格 |
| communication | `REPRO_INDEX.md` | 见归档清单 | 阅读与逐篇导航 |
| communication | `ALGORITHM.md` | 见归档清单 | 实现后沟通层 |
| evidence | `evidence.json` | 见归档清单 | 来源与事实 |
| spec | `strategy.json` | `1abe88a7860c27cd338c74eba5b1279122eae28c109df940c916007b2d5622b9` | 冻结规格 |
| validation | `validation.json` | 见归档清单 | 验收记录 |
| code | `reproduction/run.py` | 见归档清单 | 执行代码 |
| result | `artifacts/result.json` | 见归档清单 | 全部结果 |
| log | `logs/run.log` | 见归档清单 | 实际运行 |
| research_log | `iterations.jsonl` | 见归档清单 | H5/H6尝试账本 |
| research_log | `sample_access.jsonl` | 见归档清单 | 样本访问史 |
