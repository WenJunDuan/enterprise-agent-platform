# 第4轮 design · 思考流式到前端 + logs 调整 + effort 实测

> 用户 3 点新需求（2026-06-21）：① thinking effort（已 done，build_options 默认 xhigh）
> ② logs 调整（清噪音 + 落思考日志 + 轮转）③ 思考流式到 analyzing 界面（用户选轮询伪流式）。

## A. 思考流式（轮询伪流式）

**链**：`tender_worker._execute_inner → _run_evaluation → run_command_json → run_agent_json → query loop(TextBlock)`。
现状：评标走 run_command_json **收集完整结果**，中间 event 不暴露；progress_message 全程只有"评标 Agent 正在运行中"。

**方案**（最小侵入，不改执行流，加可选回调）：
1. `run_agent_json` 加 `on_progress: Callable[[str], None] | None = None`；query loop 里每个 assistant
   `TextBlock` 调 `on_progress(block.text)`（含 deepseek 思考/分析过程）。回调异常吞掉不中断评标。
2. `run_command_json` 显式透传 `on_progress`（像 project_id，不进 **opts → 防被 build_options 当 SDK 选项）。
3. `tender_worker._execute_inner`：
   - 定义 `on_progress(text)` → 更新内存 `progress_state["latest"]` + 落思考日志 `logger.info(tender_progress)`。
   - 起 asyncio **flusher** task：每 1.5s 把 latest 经 `to_thread` 写 task `progress_message`（节流，防每片段写 DB）。
   - 评标结束 `finally: flusher.cancel()`。
   - `_run_evaluation` 透传 on_progress 到 run_command_json。
4. `task_store` 加 `update_tender_progress(request_id, message)`：轻量 `UPDATE … SET progress_message`（不整条 upsert）。
5. 前端 `analyzing-view`：轮询（已有）拿 `progress_message`，append 到「实时分析输出」区（去重累积、自动滚动）。

## B. logs 三项

1. **清噪音**：uvicorn access log（`GET /health 200`、`/tasks` 轮询）刷屏。cli.py `uvicorn.run` 关 `access_log`，
   或加 log filter 过滤健康检查/轮询路径。保留有效请求日志。
2. **落 AI 思考日志**：on_progress 内 `logger.info("tender_progress", extra={request_id, snippet})`（A 内已含）；
   带 request_id 可事后排查某次评标为何这么判、effort 是否真生效（thinking 是否更长）。
3. **轮转**：RotatingFileHandler 已在（app.log/error.log）。确认思考日志走同一 root logger（受轮转约束），
   不另开无限文件；必要时调 maxBytes/backupCount。

## C. effort 实测

dogfood 华为南通标 + 烛照标：看 session log 有无 thinking 块、评标质量/稳定性是否改善（对比第2轮全 manual_review）。

## 影响范围

- server/common/json_bridge.py（on_progress 参数 + TextBlock 调用）
- server/common/command_adapter.py（显式透传）
- server/routes/tender_worker.py（on_progress + flusher task）
- server/stores/task_store.py（update_tender_progress 轻量更新）
- server/cli.py / server/platform/logging_setup.py（uvicorn access log 噪音）
- agent-front analyzing-view + use-tender-review-page（显示 progress）
- tests（on_progress 回调触发 / update_tender_progress / 噪音过滤）

## 风险与缓解

- **频繁 DB 写**：flusher 节流 1.5s + 只写最新片段（非每 TextBlock）。
- **audit 回归**：on_progress 默认 None，audit 不传 → 零行为变化。
- **回调异常**：try/except 吞掉，不中断评标主流程。
- **前端累积**：progress_message 是最新单条，前端按内容去重 append（防重复刷屏）。
- **关 access_log 过度**：只关健康检查/轮询噪音，保留 4xx/5xx 与业务请求（或仅降级到 DEBUG）。

## 验收

- 单测：on_progress 被 TextBlock 触发；update_tender_progress 写 DB；audit 不传 on_progress 零变化。
- dogfood：analyzing 界面实时滚动出评标分析片段（取标准/抽取/逐项）；serve.log 无 /health 刷屏。
- 回归：全套 passed + ruff。

## codex r4 review：REWORK → 全修

3 P1 + 3 P2 全采纳：
- **P1-1** 前端 `progressByRid` 按 request_id 存（防多 bidder 并发覆盖），多家并行按序号分段拼接、单家直接显示。
- **P1-2** effort 不全局默认 xhigh（拖慢 audit 180s 超时）→ 全局只认 env `CLAUDE_REASONING_EFFORT`（默认不设）+ 统一校验；评标 `tender_worker` per-call 传 `effort=xhigh`（`TENDER_REASONING_EFFORT`），audit 不受影响。
- **P1-3** access filter 改正则解析 exact path + status，只过滤 noise 路径的 2xx/3xx（保留 4xx/5xx），前缀边界匹配（`/tender/tasks` 命中轮询但不误伤 `?to=/health`）。
- **P2-4** flusher：DB 写异常 catch 不致 flusher 死；`finally` cancel 后 `await` + suppress `CancelledError`（cancel 仅下个 loop cycle 生效）。
- **P2-5** json_bridge 注释明确「文本模式思考在 TextBlock 内」。
- **P2-6** 补测试：command_adapter on_progress 透传（链不断 + audit 默认 None 零变化）+ effort per-call + access exact path/status。

471 passed/ruff/前端 lint+build。
