# ALGORITHM — AW7 dual-momentum filter

| 项目 | 内容 |
|---|---|
| 策略 ID | `aw7_commodity_dual_filter_20261123-v1` |
| 模式 | post-R3 filter extension |
| 状态 | research-only; BM5+dual12 shadow only |
| 父版本 | `aw7_commodity_contract_xsection_20261123-v1` |

## 1. 策略 text 流程图

```text
R3 monthly contract panel
  -> compute MOM6 and MOM12
  -> for each month:
       rank products by momentum
       eligible = MOM_h > 0 and momentum percentile >= 0.50
       if eligible <3 -> cash
       else rank by BM5 / Carry / MOM
       select top third equal-weight
  -> next-month nearby return
  -> paper-like and lag1 execution
  -> 5bp / 20.5bp turnover cost
```

## 2. 数学公式

| ID | 公式 | 代码符号 | 单位/时点 | 来源 |
|---|---|---|---|---|
| F1 | `MOM_h=prod(1+r_first)-1` | `mom6`,`mom12` | monthly | local |
| F2 | `rank=pct_rank(MOM_h)` | `rel` | monthly cross-section | dual filter |
| F3 | `eligible=1[MOM_h>0 and rank>=0.5]` | filter | month-end | DM |
| F4 | `ret=sum(w*y)-cost*sum|Δw|` | `returns_for_arm` | next month | R3 |

## 3. 变量状态图与时间契约

```text
FACTOR_WARMUP -> ELIGIBLE -> RANKED -> WEIGHTED -> NEXT_MONTH_RETURN
             \-> FILTER_EMPTY/<3 -> CASH
```

`MOM12` uses only completed monthly returns; relative rank is computed in the same
cross-section; labels `y_nearby` and `y_nearby_lag1` are inherited unchanged from R3.

## 4. 规格—代码—测试映射

| 项 | 代码 | 测试/日志 | 状态 |
|---|---|---|---|
| 6/12月动量 | `add_momentum` | `test_momentum_window_is_compounded` | PASS |
| dual filter | `portfolio_weights` | `test_dual_filter_requires_both_absolute_and_relative` | PASS |
| cash guard | `portfolio_weights` | `test_filtered_cash_when_fewer_than_three` | PASS |
| cost and labels | `returns_for_arm` | `logs/run.log`, `artifacts/metrics.csv` | PASS |

## 5. 结果、验收与偏差

BM5+dual12 的 paper-like 5bp Sharpe `0.7125`（未过滤 `0.6965`），CAGR `14.02%`
（`10.66%`），但 MDD `-24.94%`（`-23.94%`）；lag1 Sharpe `0.8669` vs `0.6979`，
bootstrap CI `[-0.213,+0.569]`、q=`0.658`。H6未通过，只保留BM5+dual12前瞻影子。

## 6. 归档索引

见 `archive_manifest.json`；核心结果在 `artifacts/metrics.csv`、`artifacts/bootstrap.csv`、
`artifacts/result.json` 和 `artifacts/nav_dual_filter.png`。
