# 沪铜数据覆盖

| 数据 | 文件 | 覆盖 | 口径/限制 |
|---|---|---|---|
| CU0 主连 | `CU0_main.csv` | 2010-01-04..2026-10-20 | Sina 不复权主连，日收益 ±6% 截断 |
| 美元指数 | `eastmoney_usd_index_udi.csv` | 1986..2026 | 东方财富 UDI 镜像，非官方 ICE |
| VIX | `cboe_VIX_History.csv` | 1990..2026 | CBOE 收盘 |
| ISM | `ism_manufacturing_pmi_eastmoney.csv` | 2008..2026 | 月度，使用 `publish_date` |
| CFTC 铜净持仓 | `cftc_copper_net.csv` | 2010..2026，879 周 | Socrata 6dca-aqww；发布日 = report_date+3 天 |

## 缺失的 28 篇因子

- 铜精矿 TC/RC、6μm 铜箔加工费、SHFE 社会库存、精废价差（SMM/Wind）。
- LME/COMEX 库存、SHFE 期货库存（公开源可补，尚未纳入）。
- 量价 7 因子（日内动量、双均线、中值双均线、KAMA、CCI、TRIX、反弹动量）在 CU0 上两段样本外为负，未纳入。

## 结论

当前只覆盖 4/14 个宏观/基本面因子；策略是公开宏观子集，不是系列 28 的完整复现。
