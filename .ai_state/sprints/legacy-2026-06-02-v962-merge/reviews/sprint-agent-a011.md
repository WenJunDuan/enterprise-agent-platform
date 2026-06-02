# A-011 自审：业务 API / CLI 边界收口 + 业务返回面整理

## 结论

- VERDICT: PASS

## 本轮问题

1. HTTP API 与 CLI 仍然重复暴露了大量查询/治理接口
   - `/sessions`
   - `/conversations`
   - `/requests*`
   - `/results*`
   - `/memories*`
   - `/review-deltas*`
   - `/governance/assets`
2. 业务主链路的异步审核返回还带了不必要的内部字段
   - `/audit/submit` 带 `result_url`
   - `/audit/tasks/{request_id}` 带 `source_mode`、`case_path`、`result_file`、`session_id` 等

## 实际改动

- 更新 `server/api.py`
  - 移除 HTTP 上重复的查询/治理接口：
    - `/sessions`
    - `/sessions/{session_id}/messages`
    - `/conversations`
    - `/requests`
    - `/requests/{request_id}`
    - `/results`
    - `/results/{request_id}`
    - `/memories`
    - `/memories/{memory_id}`
    - `/review-deltas`
    - `/review-deltas/{request_id}`
    - `/governance/assets`
  - `/audit/submit` 删除 `result_url`
  - `/audit/tasks/{request_id}` 改为紧凑业务模型，只返回前端真正需要的字段
- 更新 `server/app_server.py`
  - `service_http.urls` 去掉已删除的查询面 URL
- 更新测试
  - `tests/test_query_surfaces.py` 改为锁定“这些 HTTP 路由已不再暴露”以及审核任务状态的紧凑返回
  - `tests/test_tenant_isolation.py` 收口到仍保留的业务接口
  - `tests/test_audit_submit_attachments.py` 锁定 `/audit/submit` 不再返回 `result_url`
  - `tests/test_cli_serve.py` 补 route absence 断言
- 更新文档
  - `README.md` 明确“HTTP API 只保留业务调用面，查询/治理统一走 CLI”
  - `.ai_state/docs/前端审核服务对接文档.md` 同步新的 `/audit/submit` 和任务状态返回

## 为什么这样更好

1. API 和 CLI 的职责终于清晰了。
2. 前端只面对业务主链路，不再被历史排障面干扰。
3. 追溯/治理仍然保留，但都通过 CLI 进入，不会在对外 API 上形成第二套接口体系。

## 当前边界

HTTP API 现在只保留：

- `GET /health`
- `POST /chat`
- `POST /chat/stream`
- `POST /audit`
- `POST /audit/submit`
- `GET /audit/tasks/{request_id}`
- `GET /audit/tasks/{request_id}/result`
- `POST /init-rules`

CLI 继续保留：

- runtime / ask / audit / audit-json / init-rules
- sessions / transcript / conversations
- requests / request-detail
- results / result-detail
- memories / memory-detail
- review-deltas / review-delta-detail
- validate-assets
- serve
- app-server 系列运维命令

## 业务接口进一步精简建议

这轮已经把重复查询面收走了，下一步如果继续瘦业务返回，优先级建议：

1. `/chat` / `/chat/stream`
   - 这两个仍偏“调试/通用能力”，后续可以考虑只留 CLI，不再保留为 HTTP
2. `/audit`
   - 同步版审核和 CLI `audit-json` 有明显重叠；如果对外只走异步模式，可以考虑删除
3. `/init-rules`
   - 更偏知识治理动作，未来也可以考虑收回 CLI

## 验证

- `uv run pytest -q` 通过，当前共 71 项
- `uv run ruff check .` 通过
