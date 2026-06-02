# A-007 自审：项目级整体架构 review + API 返回集优化 + 发布前整理

## 结论

- VERDICT: PASS

## 本轮 review 发现

1. 查询接口契约仍有不一致
   - `/requests`、`/results`、`/memories`、`/review-deltas` 等列表接口虽然都有过滤能力，但返回体缺少统一 `meta`，前端拿到结果后无法稳定回显当前分页和过滤条件。
2. HTTP 错误返回仍偏“框架默认值”
   - 旧行为主要只有 `detail`，适合人看，不适合前端稳定按 `code` 分支处理；同时缺少和日志对齐的 trace/correlation 字段。
3. 发布前质量门并不真的全绿
   - `pytest` 虽已通过，但 `uv run ruff check .` 仍被 `.ai_state/docs/audit-skills/audit_check.py` 中的历史 lint 问题阻塞，这会让发布判断失真。

## 实际改动

- 更新 `server/api.py`
  - 为 `/sessions`、`/conversations`、`/requests`、`/results`、`/memories`、`/review-deltas`、`/sessions/{session_id}/messages` 增加统一 `meta`
  - `meta` 当前包含 `limit`、`offset`、`returned`，必要时附带 `filters`
  - 新增统一 HTTP 异常处理，返回 `detail + error{code,message,status_code,path,correlation_id}`
  - 保留原有 `detail` 字段，避免对现有调用方造成硬破坏
- 更新 `tests/test_query_surfaces.py`
  - 补查询面 `meta` 回归测试
  - 补 404 / 422 结构化错误响应回归测试
- 更新 `README.md` 与 `.ai_state/docs/前端审核服务对接文档.md`
  - 同步新的列表返回约定与错误返回契约
- 更新 `.ai_state/docs/audit-skills/audit_check.py`
  - 清理历史 lint 问题，恢复全仓 `ruff check .` 通过

## 为什么这样收口

1. 这轮是发布前整理，不适合做“全 API 重新套一层 envelope”这种高破坏性动作。
2. 在保留 `detail` 的同时新增结构化 `error`，可以让前端逐步迁移到稳定字段，而不是被迫一次性改完。
3. 列表接口补 `meta` 是最低风险、最高收益的收口方式，能立刻降低前端对“请求参数回显 / 当前页条数”的猜测成本。

## 验证

- `uv run pytest -q` 通过，当前共 69 项
- `uv run ruff check .` 通过

## 风险与遗留

- `GET /audit/tasks/{request_id}` 和 `GET /audit/tasks/{request_id}/result` 仍保持“轻量直出”风格，没有再额外包一层 envelope；这是有意保留，优先照顾前端主流程的简单性。
- `POST /chat/stream` 的 SSE 错误事件仍使用流式事件自己的返回格式，没有强行与普通 HTTP 错误 envelope 合并；如果后续要继续统一，建议单独定义 SSE 事件契约，而不是硬套 HTTP 模型。
- 列表接口的 `meta` 当前不提供全量 `total`，因为底层 store 还没有统一 count 查询接口；如果后续 UI 真需要总页数，应补 store 级 count API，而不是在服务层猜。

## 下一步建议

- 进入一次真实前端联调 smoke test，重点验证 `error.code`、`error.correlation_id` 与当前页面错误提示链路
- 如果准备发版，优先再过一遍部署面 checklist：`.env`、Docker、持久化挂载、`/ready` 诊断项
