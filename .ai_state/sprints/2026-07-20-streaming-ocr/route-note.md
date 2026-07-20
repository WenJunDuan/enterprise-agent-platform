# Route Note · D9 页级流式 OCR (2026-07-20)

## 任务来源

- roadmap `2026-07-doc-intelligence` item **D9**（slug `streaming-ocr`，wave 3，effort M，`redzone: agent-front`）。
- 触发：2026-07-20 用户拍板 D9 立项并授权 agent-front 红区（部署机窗口另交 codex，本机主线转 D9）。

## 候选路径与证据

| 候选 | 证据 | 判定 |
|---|---|---|
| Feature（选定） | roadmap 标 `stream: feature`；范围=OCR 单域（pipeline 接缝 + jobs 端点 + 前端 workbench），无跨域行为重构 | ✅ |
| System | 若引入平台级 streaming 框架才成立；反过度工程判据：无第二消费者（audit/tender 走既有 TaskStore 轮询），不建通用机制 | ✗ |

**写入分区**：后端=黄区（单 feature 模块，Agent subagent）；agent-front=红区（worktree 强制 + 已获授权，沿用 D11-R7 先例）。

## depends_on D4 解除（软依赖判定）

items.yaml 写 `depends_on: [D4]`，代码核验为执行序偏好而非硬前置：

- streaming 接缝在 `pipeline.extract_dir` / routes 层，engine 选型在 `engine.recognize()` 内部（`server/ocr/engine.py:464`），两者正交；D4 落地 EngineRegistry 后事件流形态不变。
- 用户 2026-07-20 明确拍 D9 先行（D4 卡部署机 V4Pro 基线）。re-route 只升不降不受影响（Feature 维持）。

## 关键侦察事实（2026-07-20 实测）

1. **平台无 SSE**：`grep StreamingResponse|text/event-stream` server/ 零命中——roadmap D9 note「复用平台 SSE 进度流机制」前提不成立，需在 design 拍传输形态。
2. **OCR 是唯一同步阻塞域**：`/ocr/extract`、`/ocr/fill`（server/routes/ocr.py:72,144）一次性响应；audit/tender 均为 TaskStore submit→poll 异步形态。
3. **页级粒度自适应**：native pymupdf 逐页循环（native.py:182）、VLM `_recognize_via_openai_compatible` 逐页识别循环（engine.py:228-239；`_render_pdf_pages` 仅切图）可页级；cloud aistudio job-poll 整档返回（engine.py:323-393）仅文件级。注意 native/paddle-pipeline 页循环在 FITZ_LOCK/PADDLE_LOCK 临界区内（critic F2，回调须锁外触发）。
4. 前端落点：`agent-front/src/features/ocr/ocr-workbench-page.tsx`（critic F6 勘正；workbench/ 子目录仅 mock-data/shared）；停轮询先例=`use-tender-review-page.ts`（refetchInterval L487/L284/L315，null/404=终态防御）。

## 决策

进入 **design stage**（Feature 但含红区前端 + 新增异步端点契约，值得 critic 一轮）。方案候选（任务化+部分结果轮询 vs 新建 SSE）的权衡放 design.md Round 1。

**置信度：高**——范围与 roadmap 一致，唯一前提偏差（平台 SSE 不存在）已实证并纳入设计分叉。
