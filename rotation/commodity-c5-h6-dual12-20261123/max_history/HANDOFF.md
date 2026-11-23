# HANDOFF — AW7 H6 maximum history

| 项目 | 当前值 |
|---|---|
| 目标/模式 | 把六商品 H6 回测拉到可用最长历史；sample extension |
| 当前阶段 | `validated`；研究结论 `SHADOW_ONLY` |
| 策略 | `aw7_commodity_h6_maxhistory_20261123-v1` |
| 规格哈希 | `0be3faa2fee42565b5049f620cbfb1a6f1251e55f67bc7b9c74c497632cc1d16` |
| 代码哈希 | `4df5e88fb6b943813935fcc638fdecccb4964be0772950403d90411849809f91` |
| 数据证书 | `data_certificate.json`，PARTIAL；无供应商历史 vintage，2016–2020含ETF代理 |
| 已看样本 | 2016-01-29—2026-09-30；全部历史已看，不是 OOS |
| 验收 | 严格六节点对拍误差 `9.97e-17`；分项结构门禁见 `validation.json` |
| 关键结果 | 5bp CAGR/Sharpe/MDD：C5 `28.75% / 1.177 / -24.02%`，H6 `33.06% / 1.306 / -24.02%` |
| 关键否证 | 200次BM5标签置换仅第87.5%分位；6次换序、5次实际持仓改变 |
| 生产边界 | 保持 `C5 + RANK2 + TIP/DD`；H6仅前瞻影子，不替换生产 |

最快复核顺序：`REPORT.md` → `AUDIT.md` → `ALGORITHM.md` → `artifacts/metrics.csv`。
逐源页面见 `REPRO_INDEX.md`，完整哈希见 `archive_manifest.json`。

下一步仅有两种合法路径：按 `aw7_commodity_h6_shadow_20261123` 继续积累冻结后的前瞻月末
快照；或在新的冻结版本中验证更宽合同级横截面。不得在已看历史中继续搜索 gap、BM5窗口、
资产池或风险层参数。
