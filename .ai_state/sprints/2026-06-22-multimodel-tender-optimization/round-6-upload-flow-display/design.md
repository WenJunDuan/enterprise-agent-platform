# R6 设计 · 评标创建流程 UX 重构 + 信息展示完善

> Sprint 2026-06-22 · Round 6 · Path: System（前端 + 后端）
> 用户反馈（2026-06-22）：上传完卡在「OCR 识别中，请稍候…」无法下一步；OCR 近 5 分钟实际不可能等；
> 应「上传就 OCR，我一直下一步，直到点开始分析，人可以离开去看别的」；区1/区2 信息（招标项目名称/
> 投标公司名称/招标信息要素/扣减分数项）还是没好好展示。

## 背景（WHY）
R4-A 实现「上传即 OCR」，但「开始分析」按钮卡在 `isOcrReady`（等招标+所有投标 OCR 全 ready），
OCR 近 5min → 用户被卡在第二步。**根因**：把 OCR 就绪当成了进入下一步的拦路闸。
另：Explore 实测——**评标重复 OCR**：evaluate 另建新 bid_id、重传文件、worker 收 `bid_id=None` →
`_load_doc_layer_context` 早退 None → inline 重 OCR（预热的 bid OCR 永不复用，等于 OCR 跑两遍）。

## 需求分解

### R1（P0）开始分析不被 OCR 阻塞
- 上传文件即后台 OCR（已有）。
- **「开始分析」在文件上传完（项目建好 + ≥1 家投标已传）即可点，不等 OCR ready**。
- 点击立即进入「分析中」页面；OCR + criteria 抽取 + 评标在后台连续跑；用户可离开/回来恢复（已有长任务解耦 activeEval）。
- 验收：上传后秒级可点开始分析；点后进分析中页；离开列表再回来能恢复。

### R2（P1）评标复用预热 OCR（不重复 OCR 两遍）
- 评标用预热的 bid（uploadBid 返回的 bid_id），worker 复用其 OCR 底稿，不再重传 + inline 重 OCR。
- 方案（Explore 推荐 Option a + 兜底 b）：evaluate 接受 prewarm `bid_id`（前端已持有）→ 透传到
  `schedule_tender_evaluation_task(bid_id=...)` → worker `_load_doc_layer_context` 命中预热 OCR（管线已就绪，仅缺这一传参）。case_path 用预热 bid 目录，免重传。
- **用户可离开**：评标即时提交、后台跑；若提交时 OCR 未就绪，worker 短轮询等预热 OCR ready（兜底超时才 inline），保证复用且不阻塞前端。
- 验收：单次评标只 OCR 一遍（serve log 无第二次 bid OCR）；省一遍 ~5min。

### R3（P0）区1 基本信息展示
- 招标项目名称、招标人、**投标公司名称**、控制价、评标办法 — OCR+抽取完即在「分析中」页/分析中心显示。
- 现状：区1 fallback tenderInfo→form，但 auto-upload 不填 form → OCR 慢时长时间空；投标公司名（bidder_name）未在区1 露出。
- 改：区1 加投标公司名（docsStatus.bids[].bidder_name / 评标结果 claim_id）；tenderInfo 到达即填；空字段「识别中」。

### R4（P0）区2 招标信息要素 + 扣减分数项
- 评分项、扣分点（扣减分数项目）、废标条款 — criteria 抽取完即显示（已有 CriteriaSummary，验证数据流 + 区2 在分析中页可见）。
- 现状：criteria_status=ready 才显（需 OCR 慢 + 抽取）。R1/R2 提速后更快到达；验证展示正确。

## 影响范围
- 前端：use-tender-review-page.ts（canStartReview 闸、submitReview 用 prewarm bid_id）、create-review-view.tsx（按钮态）、analyzing-view.tsx（区1 投标公司名 + 展示完善）。
- 后端：server/routes/tender.py（evaluate 接受 bid_id + 复用 case_path）、tender_worker.py（worker 短轮询等预热 OCR）。

## 风险与缓解
- 评标早于 OCR 提交 → worker 等预热 OCR（兜底超时 inline，不死等）。
- bid_id 透传破坏现有 directory/legacy 评标 → bid_id 可选，缺省走原路径（向后兼容）。
- 用户离开后评标仍需跑 → 即时提交（后台 task），不依赖前端轮询触发。

## 执行顺序
1. R1 开始分析不阻塞（解 #1 痛点，最高优先）。
2. R3/R4 区1/区2 展示完善（解 #2 痛点）。
3. R2 OCR 复用（省一遍 OCR，优化）。
每步前端 lint/build + 后端 pytest + 接口自测；R2 后 3 模型轮询验单次 OCR。

## 进度
- _pending — 即将开工 R1_
