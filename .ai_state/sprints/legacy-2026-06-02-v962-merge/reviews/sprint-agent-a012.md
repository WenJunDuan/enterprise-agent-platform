# A-012 自审：最小业务 HTTP 面落地

## 结论

- VERDICT: PASS

## 本轮目标

把 HTTP API 继续收紧到“前端真正需要的最小业务面”，不再保留任何命令型入口。

## 实际改动

- 更新 `server/api.py`
  - 移除：
    - `/chat`
    - `/chat/stream`
    - `/audit`
    - `/init-rules`
  - 当前公开 HTTP 只保留：
    - `/health`
    - `/audit/submit`
    - `/audit/tasks/{request_id}`
    - `/audit/tasks/{request_id}/result`
  - 顺手修复 `/audit/submit` 的 JSON body 校验：缺少 `mode` / `directory_path` 时现在走统一 422 错误 envelope，而不是落成 500
- 更新 `server/app_server.py`
  - `doctor` 的服务 URL 快照同步改为最小业务面
- 更新测试
  - `tests/test_query_surfaces.py` 锁定最小 HTTP 路由集合
  - `tests/test_cli_serve.py` 锁定 `/chat`、`/audit`、`/init-rules` 不再暴露
  - `tests/test_audit_submit_attachments.py` 锁定 `/audit/submit` 紧凑返回
  - 删除 `tests/test_session_lifecycle.py`，因为它依赖已删除的 `/chat` HTTP 入口
- 更新文档
  - `README.md` 与前端审核对接文档都改为只描述这 4 个 HTTP 端点

## 当前边界

HTTP：

- `GET /health`
- `POST /audit/submit`
- `GET /audit/tasks/{request_id}`
- `GET /audit/tasks/{request_id}/result`

CLI：

- runtime / ask / audit / audit-json / init-rules
- sessions / transcript / conversations
- requests / request-detail
- results / result-detail
- memories / memory-detail
- review-deltas / review-delta-detail
- validate-assets
- serve
- app-server 系列运维命令

## 为什么这样更好

1. 前端和业务调用方只需要面对 4 个 HTTP 端点。
2. 命令型能力不再同时存在于 HTTP 和 CLI 两处。
3. 查询/治理/排障全部回到 CLI 后，API surface 明显更稳定。

## 验证

- `uv run pytest -q` 通过，当前共 68 项
- `uv run ruff check .` 通过

## 下一步建议

- 当前 HTTP 面已经很小了，后续如果还想进一步收口，最多只剩考虑是否保留 `/health` 的字段多少，不建议再删业务链路本身
