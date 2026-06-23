# Codex 前端 handoff · tender 评审 UI 修复（2026-06-23）

> 分工：前端 `agent-front/` 由 codex 改；后端 server + `.claude` 由 CC 改（并行不冲突）。
> **关键前提（CC 实测确认）**：后端数据是对的——qwen 实跑 8 项打了真实分（企业实力6/6 业绩9/9 负责人3/3 技术21/25 总体方案13/15 实施5/5 培训3/3 售后4/4），三模型对客观项完全一致。**下列问题大多是"数据在、前端没渲染"**，不是后端没算。
> 数据源：`GET /tender/tasks/{rid}/result` 与 `GET /tender/projects/{pid}/results/{rid}`（两者均返回 enrich 后的 audit-result，含 `extracted_data.scoring/criteria/evidence_chain`、`verdict`、`policy_refs`）。契约见 `.claude/contracts/common/audit-result.schema.json` + `tender/criteria.schema.json`。

## 数据形状（真实样例，来自 qwen 张謇新和结果）

`extracted_data.scoring[]` 每项：
```jsonc
{
  "item": "技术参数指标", "max": 25, "score": 21, "status": "scored",
  "score_mode": "additive",          // deduction|banded|additive|formula|pass_fail|manual
  "basis": "……逐项说明（可能含 ⚠ 标注）",
  "award_hits": [{"award_id","condition","points_each","times","awarded","evidence":{"source","quote"}}],   // additive
  "deduction_hits": [...],            // deduction 模式
  "selected_band": {"level","points","reason"},  // banded 模式
  "resolution": {"status":"resolved|unresolved|weak_match|loc_only","page":"confirmed|page_mismatch|no_page"}  // R1 回查标注
}
```
- 价格分等：`"status":"manual_review","score":null` —— 这是**故意的**（低价优先需≥2家横比，单家算不出）。`basis` 写明"需横比/需外部数据"。
- `policy_refs`：CC 正在 enrich 成 `[{rule_id, name, source_text}]`（#6）。**改前是 `["tender_evalmethod_001",...]` 裸字符串**——codex 按对象数组渲染（兼容字符串兜底）。

## 任务清单

### #1 分析中心左侧"分项得分"不显示得分 【数据已在，纯渲染】
- 渲染 `extracted_data.scoring[]`：列 `item / score(或"—" if null) / max / 状态 / basis`。
- 不要只显示 verdict 总标签（manual_review）就把分项区留空。

### #7 评分表重构（也复用到 #1、#5）
- "废标项明细" **改名 → "评标项目明细"**。
- 列：**满分 / 实际得分 / 扣减(=max−score, banded/additive 显其逻辑)**。
- **分类聚合**：顶部总分 → 商务标(分项明细) → 技术标(分项明细)，可折叠/点击展开。criteria 项有 `tag`/分类线索；若后端没给分类，按 item 名归组（CC 可在 criteria 加 `category` 字段，见下「需要 CC 配合」）。
- **隐藏"待判断/待人工"标签**：`status:manual_review` 的项**不显示"待人工"字样**，直接显示 `basis`（依据文本，已写清"需横比/需外部数据"）。`basis` 里若仍有"待人工\外部输入"前缀，CC 会在 ④ 命令侧去掉。
- 此表做成**可复用组件**，分析中心(#1) + 评分对比(#5) 共用。

### #5 评分对比只有总分、无分项
- 评分对比(compare)界面：在综合总分下加**分项表**（商务总分10/扣减2/出处…），点击行 → **右侧弹出**该项明细（basis + evidence）。
- ⚠️ compare 需 **≥2 家**投标人（单家 `GET /projects/{id}/compare` 返回 **404**，正常）。compare 结果形状见 `.claude/contracts/tender/compare-result.schema.json`：`bidders[].{claim_id, price_score, other_score, total_score, rank}`。分项明细取各家 `results/{rid}` 的 `scoring[]`。

### #4 生成报告 500 【需 codex 复现定位】
- CC 实测：报告屏命中的后端端点全 **200**（`/projects/{pid}`、`/tender-doc`、`/results/{rid}`、`/tasks/{rid}/result`），`/compare` 单家 **404**（正常）。**服务端日志无 500**。
- 报告是前端 `buildTenderReviewData`(model.ts) 纯构建。500 可能来自：① 旧 build/旧数据；② 前端对 compare 404 处理不当当成报错；③ 某字段 null 未防御。
- **请在当前 build 复现"生成报告"，打开 Network 看哪个请求 500 + 抓 `X-Request-ID`/响应里的 `correlation_id`**，回传给 CC 定位（若确是后端）；若是前端 JS 错误（非 HTTP 500），codex 直接修。

## 需要 CC 配合的（CC 会做，codex 按此对接）
- #6：`policy_refs` enrich 成 `[{rule_id, name, source_text}]`。
- ④：scoring `basis` 去掉"待人工/外部输入"前缀，直接给依据文本。
- 评分项分类：CC 在 criteria item 上补 `category`（商务/技术/价格）字段供前端聚合（#7）——若 CC 来不及，codex 先按名归组兜底。

## 验收
- 分析中心左侧逐项分可见（#1）；评分表分类聚合+满分/得分/扣减+隐待人工（#7）；对比页分项表+右侧弹出（#5）；报告不再 500（#4）。
