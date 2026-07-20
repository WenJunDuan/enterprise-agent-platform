# D9 runtime-verify · mac mini 实跑交接单

> 2026-07-20 · 用户 mac mini 亲自部署实跑，codex 规整日志回传 → 主 agent 收口 runtime-verify.md + ship 契约。
> 本机 impl/review/polish 全绿并 push origin（至 3d80836），唯缺端到端实跑证据。

## 部署前置（沿用 deploy-window-checklist.md）
- `git pull origin main`（含 D9，至 3d80836）→ `uv sync --extra ocr`（必须带 extra）→ 前端 `npm --prefix agent-front run build`。
- 新 flag 保持默认关不影响 D9（/ocr/jobs 是新增端点，独立于 AUDIT_DIRECT_CONNECT/TENDER_SLIM_CONTEXT）。
- 起服务 `uv run python -m server.cli serve`。

## 需要实跑验证的点（这些跑通=runtime-verify PASS）
1. **提交流式任务**：前端 OCR 工作台切「流式识别」模式 → 传一个**多页 PDF**（最好含扫描页，能触发页级 OCR）→ 提交返回 202 + request_id。
2. **渐进渲染**：轮询期间前端**边识别边出**，第 N 页识别完就显示第 N 页（不是等全部完成才一次性出）；进度条 done/total 单调递增不回退。
3. **终态**：completed 后停止轮询（不无限转圈）；failed 时显示错误原因 + 重试入口；空结果有引导。
4. **双模式并存**：切回「识别+回填」模式，原 /ocr/fill 回填流程正常（未被流式改动破坏）。
5. **边界**（可选）：传空目录/无效文件看是否立即 completed 不悬空；跨会话 request_id 应 404。

## 请 codex 规整回传的日志/证据
- 后端服务日志：/ocr/jobs 的 POST/GET 请求序、每个单元事件（file/page/status/from_cache）、progress 更新序。
- **units.jsonl 内容**（`data/submissions/<tenant>/ocr/<request_id>/units.jsonl`）：确认逐行 JSON、页号真实【第N页】保真、扫描页内容非空白（F1 修复的核心：混合 PDF 扫描页应是 OCR 修正内容而非空白）。
- 前端观察：截图或描述「渐进出现」的实际体感 + 终态行为。
- 任何异常/报错栈。

## 回传后主 agent 动作
用日志核对上述 1-5 是否达标 → 写 `runtime-verify.md`（## 测试场景 + 实跑结果）→ 若达标则完成 System ship 契约（review-manifest.yaml 等）+ roadmap D9→done + fable5 全局扫描（用户已约定的收尾动作）。若暴露 bug → 回 impl 修。
