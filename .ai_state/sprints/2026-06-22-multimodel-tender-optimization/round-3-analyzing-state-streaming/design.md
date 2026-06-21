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
- B-C：✅ 已实现 + 前端 lint/build/17 tests 绿（待用户 dev 眼验"返回再进"恢复实时）。
- 遗留① 流式 + openrouter 兼容实测：_pending（下一步）_。
