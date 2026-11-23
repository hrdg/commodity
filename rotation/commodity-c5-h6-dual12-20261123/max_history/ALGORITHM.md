# ALGORITHM — H6 maximum history

| 项目 | 内容 |
|---|---|
| 策略 ID | `aw7_commodity_h6_maxhistory_20261123-v1` |
| 模式 | sample extension |
| 状态 | research-only |
| 父策略 | R2 H6 |

## 1. 策略 text 流程图

```text
six ETF closes
  -> C5 score
  -> candidate order
  -> look up BM5 for C5 top two
       both available?
         yes -> H6 gap/tolerance rule -> order swap if true
         no  -> keep C5 order
  -> B.choose/RANK2/TP lock
  -> next-open ETF
  -> TIP S + lagged DD + 5/20.5bp
```

## 2. 数学公式

| ID | 公式 | 代码符号 | 单位/时点 |
|---|---|---|---|
| F1 | `C5=OLS_slope25(logP)*R2_250` | `c5_signal` | month-end |
| F2 | `BM5=prod(1+r1)-prod(1+r2)` | `bm5` | t-5..t-1 |
| F3 | `swap=1[both finite and gap<=.25 and BM5_2-BM5_1>1e-12]` | `apply_h6_near_tie` | month-end |
| F4 | `ret_net=gross-cost*turnover` | R2 ledger | next-open |

## 3. 变量状态图与时间契约

| 变量 | 含义 | available_at | 缺失状态 |
|---|---|---|---|
| `C5` | six-node trend score | month-end | no new target |
| `BM5` | node curve pressure | month-end | no H6 swap |
| `hold` | actual ETF | after next open | carry |
| `risk_exposure` | after TIP/DD | prior-close state | bond |

```text
C5_VALID -> TOP2
              -> BM5_FULL -> H6_CHECK -> TARGET
              -> BM5_MISSING -> C5_TARGET
TARGET -> NEXT_OPEN -> POSITION -> TIP_DD -> NAV
```

## 4. 规格—代码—测试映射

`node_panel_partial` constructs node history without filling. `R2M.simulate` is the
frozen baseline/H6 engine. `test_run.py` checks group completeness and node identity.
The strict-six replay is the principal integration check.

## 5. 结果、验收与偏差

Longest window starts 2016-02-01. H6 5bp `28.75→33.06 CAGR`, `1.177→1.306 Sharpe`,
MDD unchanged `-24.02%`; 20.5bp `1.022→1.167`. Strict-six replay error `9.97e-17`.
Label permutation 87.5th percentile. Therefore no production change.

## 6. 归档索引

See `archive_manifest.json`; key outputs are `artifacts/metrics.csv`,
`artifacts/yearly.csv`, `artifacts/h6_events.csv`,
`artifacts/h6_bm_permutation.csv`, and `artifacts/nav_maxhistory.png`.
