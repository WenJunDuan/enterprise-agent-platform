# Tender 评标展示修复 — Codex Handoff

> 来源：用户 2026-06-21 实测评标页反馈。后端已修通（OCR 截断 40K→200K + tender 文本模式 + JSON 硬化 +
> 输出 token），评标现在能产出**完整结构化结论**。本文件交 codex 改前端展示。

## 后端数据契约（评标结论，`GET /tender/tasks/{request_id}/result` 实测形状）
```jsonc
{
  "verdict": "rejected | approved | manual_review",
  "risk_score": 95,
  "explanation": "详尽中文理由（废标时写清为何不响应本项目等）",
  "reasons": ["短句1", "短句2"],
  "policy_refs": ["tender_evalmethod_005", ...],   // 法定依据 rule_id
  "extracted_data": {
    "criteria": [ {"item","max","scoring_rule","source_ref","tag"} ],   // 评标办法（4 大类）
    "scoring":  [ {"item","max","score","status","basis"} ],            // 逐项评分（实测 14 项）
    "tender_project_id": "...", "bid_price": {"amount","currency"}
  }
}
```
- `scoring[].status` ∈ `scored`（给分）/ `manual_review`（score:null，需外部输入）/ `rejected`（废标项，0 分）。
- 废标（verdict=rejected）时所有 scoring 项 status=rejected、score=0 —— 这是**正确**表现（无效投标不逐项给分），不是 bug。

## 涉及文件（`agent-front/src/features/contract/tender-review/`）
- `components/report-view.tsx`（结论展示）
- `components/dashboard-view.tsx`（项目列表/进度）
- `use-tender-review-page.ts`（轮询 / compare）+ `api.ts`（compare 404）
- `model.ts`（progress / 状态派生）

验收：`npm --prefix agent-front run lint && build` 过；后端 9999 + 前端 5173 浏览器核对。

---

## T1 不要把"投标文件原文"当主内容展示；按 verdict 分别渲染
- 现状：结论区偏向展示原文/底稿。
- 改：以 `verdict` 分流——
  - `rejected`（废标）：突出展示 `explanation`（为何废标）+ `policy_refs`（法定依据）+ `reasons`，**不要**铺投标文件原文。
  - `approved` / 有 scoring：展示**评分汇总**（见 T2）+ 逐项 `scoring` 明细（item/max/score/status/basis）。
  - `manual_review`：展示需补的外部输入说明。

## T2 右上角展示评分汇总（满分 / 实得 / 扣分项）
- 现状：右上角没有评分汇总。
- 改：从 `extracted_data.scoring` 计算并展示：
  - **满分合计** = Σ `max`；**实得合计** = Σ（status=scored 的 `score`）；
  - **扣分项 / 未得分项**列表：status=scored 且 `score < max` 的项（扣了多少 = max-score，附 `basis`），以及 status=rejected/manual_review 的项。
  - 未判定项（status=manual_review, score=null）单列"待人工/外部输入"，不计入实得也不算 0。
- 注：废标时实得=0、全部 rejected，属正常（页面应说明"整标废标"而非逐项罗列扣分）。

## T3 修"已完成却一直显示评标任务进行中 0%"
- 现状：项目有已完成投标人（名册 roster 有 completed 结论），但项目卡显示 `progress=0%` / 状态"分析中(doing)"。
  涉及 `dashboard-view.tsx:262/271`（`project.progress`）+ `model.ts` 的 progress/status 派生。
- 改：progress / 状态应**从名册派生**——有 ≥1 个 completed 投标人结论时，progress 反映已完成比例（completed / 总投标人），
  全部完成则显示"已完成(done)"，而非永远 doing 0%。若后端 `project.status` 不翻转，前端按 roster 实际完成数派生展示状态。

## T4 compare 404 静默（停止无效轮询刷屏）
- 现状：`use-tender-review-page.ts:117-122` 的 `compareQuery` 带 `refetchInterval` 持续轮询
  `/tender/projects/{id}/compare`，单投标人时后端恒 404 → 日志/网络刷屏（实测连续 404）。
- 改：`compareQuery` 仅在**投标人数 ≥ 2 且需要横比**时 `enabled`；或 `getTenderCompareOrNull` 返回 null（404）后
  **停止 refetchInterval**（返回 false），不要对单投标人项目持续轮询。404 本身已静默处理（api.ts:278 返回 null），
  只需把轮询关掉。

---
> 后端侧本次已交付（已 push origin/main）：`2c693b0` OCR 截断 200K、`774feb7` tender 文本模式+JSON 硬化+输出 token、
> `21dd161` 报销 manual_review_reason 剥离、`1b2d289` 报销 prompt 硬化。前端无需改后端。
