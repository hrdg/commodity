# 数据覆盖

| 文件 | 字段 | 覆盖 | 来源 |
|---|---|---|---|
| `wti.csv` | date, value | 1986-01-02–2026-10-20 | EIA `RWTCd` |
| `gasoline.csv` | date, value | 1986-06-02–2026-10-20 | EIA `EER_EPMRU_PF4_RGC_DPGd` |
| `heating_oil.csv` | date, value | 1986-06-02–2026-10-20 | EIA `EER_EPD2F_PF4_Y35NY_DPGd` |
| `cushing.csv` | date, value | 2004-04-16–2026-10-16 | EIA `W_EPC0_SAX_YCUOK_MBBLw` |
| `160723.csv` | date, open/high/low/close/volume/amount | 2017-05-05–2026-10-27 | Sina/AKShare LOF 日线 |
| `nav_160723.csv` | date, nav | 2017-04-20–2026-10-27 | Sina `CaihuiFundInfoService.getNav` |
| `501018.csv` / `nav_501018.csv` | price / nav | 2016-06-29–2026-10-28 | Sina LOF 日线 / NAV |
| `161129.csv` / `nav_161129.csv` | price / nav | 2017-02-15–2026-10-28 | Sina LOF 日线 / NAV |
| `160216.csv` / `nav_160216.csv` | price / nav | 2015-04-07–2026-10-28 | Sina LOF 日线 / NAV |
| `159981.csv` | date, close | 2020-01-17–2026-10-28 | Sina ETF 日线 |
| `dxy.csv` | date, value | 2006-01-02–2026-10-23 | FRED `DTWEXBGS` |

## 口径

- 裂解价差：`(2×汽油×42 + 取暖油×42 − 3×WTI)/3`，美元/桶。
- 库欣：周度库存，52 周滚动均值减 4 周前；上升=1。
- 溢价：`收盘价 / 滞后1日NAV − 1`；未使用 IOPV 或申购状态。
- 交易：收盘决策、下一交易日持有；3bp 单边。

## 限制

1. NAV 为基金披露值，QDII 净值有 T+1/T+2 延迟；策略用滞后 1 天，并做过滞后 2/3 天敏感性。
2. EIA 库存是当前修订序列，不是 as-released vintage；可能有修订偏差。
3. 未纳入申购状态、场内流动性、IOPV、汇率对冲和分红。
4. 160723 是 LOF，不是 ETF；收盘价可能含溢价/折价变动。
5. 501018/161129/160216/159981/DXY 只用于增强假设测试，不进入当前正式策略。
