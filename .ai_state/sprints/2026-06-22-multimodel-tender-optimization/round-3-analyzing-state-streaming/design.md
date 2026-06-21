# R3 设计 · analyzing 状态机 bug + 思考流式实时

> Sprint 2026-06-22 · Round 3/6 · Path: System（前端 + 后端）· 并入 bug B-C、遗留①

## 背景（WHY）
1. **B-C（用户原话）**：「返回列表再回到分析中的界面，回不到真正的分析中的界面」。根因：
   `exitAnalyzing` 清 activeEval+localStorage（杀实时轮询 + 解锁 lazy-init）；列表 `onOpenProject`
   → `openAnalysis('detail')` → `screen='analysis'`（分析**中心**，非 'analyzing' 进度页）。进行中
   项目从列表点开落到空分析中心，无法 re-attach 实时进度。(dashboard 按钮文案是「查看进度」却跳错屏)
2. **遗留①**：qwen 思考流式不实时——qwen 端点一次性返回（session log 仅 1 个 assistant_text），
   on_progress 只在结束触发一次、flusher 已 cancel → progress 停"运行中"。

## 方案（HOW）

### B-C（✅ 已实现）
- `use-tender-review-page.ts` 新 `resumeOrOpenProject(projectId)`：拉项目详情 → 有未终态投标
  （status∉{completed,failed}）→ 重建 activeEval(requestIds=进行中bid) + `screen='analyzing'`，
  让 activeEvalQuery 按 requestIds re-attach 轮询、恢复实时进度；全完成 → openAnalysis 分析中心；
  拉取失败/无投标 → 安全回退分析中心。
- `screen-content.tsx`：dashboard `onOpenProject` + history `onAnalysis` → `resumeOrOpenProject`。

### 遗留①（待实现）
- 后端 `run_agent_json`：开 `include_partial_messages`，处理 StreamEvent partial（试 dashscope 是否
  支持流式 SSE）；**兜底**：flusher 退出前最后 flush 一次（`_flush_progress` cancel 前补一次写）。
- 简单兜底优先（flusher final-flush），include_partial_messages 视端点支持情况。
- **openrouter 兼容性同测**：openrouter base 是 OpenAI-compat `/chat/completions`，与本项目
  Anthropic-protocol SDK 是否兼容、是否吐 partial，R3 三模型轮换实测确认。

## 影响范围
- 前端：use-tender-review-page.ts、screen-content.tsx。
- 后端（遗留①）：server/common/json_bridge.py（run_agent_json 流式）、可能 tender_worker flusher。

## 风险与缓解
- B-C：resumeOrOpenProject 拉详情失败 → 回退分析中心（已做）。
- 流式：include_partial_messages 各端点支持不一 → flusher final-flush 作确定性兜底（端点无关）。

## 验收标准
1. B-C：进行中项目从列表/历史点开 → 回到「分析中」实时进度页（非空分析中心），离开/回来可恢复。
2. 流式：qwen 评标进度实时更新（非停"运行中"到结束才出）。
3. 3 模型轮换（qwen/deepseek/**openrouter**）：流式实时性 + openrouter 是否跑通（兼容性结论）。
4. tests + 前端 lint/build 绿。

## 进度
- B-C：用户实测仍落分析中心 → **复发根因 = react-query 缓存**：`resumeOrOpenProject` 的
  `fetchQuery(['tender-project',id])` 吃 dashboard `useQueries` 的 5s staleTime 缓存，返回旧的
  完成态/空态 bids → inProgress=0 → 误落分析中心。**修：fetchQuery 加 `staleTime:0` 强制新取**
  最新投标状态（后端已确认在途投标 status='running'，见 `_project_bid_roster` tender.py:220-231）。
  前端 lint/build 绿。⚠ 用户需重新 build/刷新 dev 才会生效。
- **openrouter 兼容（用户要求查链接）**：✅ **查实并跑通**——openrouter 有原生 Anthropic skin，
  base 应为 `https://openrouter.ai/api`（非用户原填的 `/api/v1/chat/completions` OpenAI 路径）。
  已修 .env openrouter 块 base URL。**R1 抽取实测 openrouter(z-ai/glm-5.2) 跑通：criteria ready 81s
  （三模型最快！qwen163/deepseek142/openrouter81）、14项 Σ=100、20废标**。tender_info 被 glm 漏/校验
  丢弃（best-effort，criteria 仍 ready）。openrouter 正式纳入轮换（替 anyrouter）。
- 遗留① qwen 思考流式实时：✅ **修复并实测跑通**。
  - 根因：SDK 默认只吐完整 AssistantMessage（qwen 一次性返回→on_progress 仅末尾一次）。
  - 修：①`include_partial_messages=True`（tender per-call，env `TENDER_STREAM_PARTIAL`）+ json_bridge
    处理 `StreamEvent`（content_block_delta 的 text/thinking 增量）→on_progress 实时；`saw_partial`
    防与完整消息双喂；partial 不进 text_accum（权威全文由完整消息给，JSON 抽取不受影响）。
    ②flusher 退出兜底 final-flush（防末次文本丢失）。③on_progress 不再 strip（保 delta 词间空格,
    治粘连）+ 日志按 `_PROGRESS_LOG_EVERY`(800字符) 节流（partial 1253 次回调→4 条 INFO）。
  - **实测 qwen 全量评标**：`tender_progress` 1253 次回调（vs 旧 1-3）= 真·逐字实时；progress_message
    逐字更新、空格正确、日志 4 条。→ **dashscope/qwen 确支持 SSE partial**，开关即实时。
  - deepseek/openrouter 流式实时性：待 3 模型轮换补测（机制端点无关，支持 SSE 即生效）。

## R3 端到端确认（2026-06-22）
qwen 全量评标：completed / verdict=rejected(投错标,纠偏生效) / 20项 scoring / 300s / **retries=0**(evidence_chain 修复消除契约重试) / 流式实时(progress逐字). 流式不破抽取(20项结论完整). 605 passed.
