# Codex Handoff — T-007: 重建完整测试套件

## 背景

`tests/` 目录当前完全为空（所有测试文件已被手动清理）。
需要从零重建一套覆盖后端服务核心链路的测试，确保主要模块可回归验证。

## 项目技术栈

- Python ≥ 3.12，用 `uv` 管理
- FastAPI + Starlette（HTTP 服务）
- Claude Agent SDK（`claude_agent_sdk`）
- 测试命令：`UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q`
- Lint 命令：`UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .`

## 目录结构（当前 server/）

```
server/
├── __init__.py
├── api.py                  # FastAPI app，路由：/health /audit/submit /audit/tasks/*
├── app_server.py           # Typer CLI: start/stop/restart/status/logs/doctor/maintain
├── cli.py                  # 另一个 Typer CLI（本地直连）
├── core.py                 # Claude Agent SDK 桥接，结构化输出，validate_structured_output_semantics
├── command_adapter.py      # build_command_prompt / run_command_full / run_command_json
└── platform/               # config, paths, logging_setup, diagnostics, maintenance
    ├── __init__.py
    ├── config.py
    ├── paths.py
    ├── logging_setup.py
    ├── diagnostics.py
    └── maintenance.py
└── stores/                 # SQLite 查询索引 + JSONL 归档
    ├── __init__.py
    ├── audit_task_store.py
    ├── request_store.py
    ├── result_store.py
    ├── session_store.py
    ├── review_delta_store.py
    ├── memory_store.py
    └── runtime_store.py
```

## Hooks（`.claude/hooks/`）

### `check-before-write.py`
- Pre-write hook，拦截不完整的审核结果
- `REQUIRED_FIELDS`：`claim_id`, `verdict`, `result`, `conclusion`, `explanation`, `reasons`, `policy_refs`, `risk_score`, `extracted_data`, `evidence_chain`, `reviewed_by`, `timestamp`
- 函数：`_is_non_empty_string(value)`, `_resolve_audit_result(payload)`

### `review-output.py`
- Post-write hook，对写入 `logs/results/` 的结果触发二次复核
- 函数：`_is_result_write(file_path: str)`, `_has_runtime_credentials()`

## 契约 Schema（`.claude/contracts/`）

```
.claude/contracts/
├── common/audit-result.schema.json
├── expense/extract-result.schema.json
├── expense/review-delta.schema.json
└── system/init-rules-report.schema.json
```

## core.py 关键函数（供 mock）

```python
def validate_structured_output_semantics(schema_name: str, structured_output: dict) -> None
def load_output_schema(schema_name: str) -> dict
def build_output_format(schema_name: str) -> dict
async def run_agent_json(prompt, ..., schema_name, ...) -> tuple[dict, AgentRunMeta]
```

## command_adapter.py 关键函数

```python
def build_command_prompt(command_name: str, *arguments: str) -> str
def _serialize_command_argument(argument: str) -> str
async def run_command_full(command_name: str, *arguments: str, **opts) -> str
async def run_command_json(command_name: str, *arguments: str, schema_name: str, **opts)
```

## API 路由（`server/api.py`）

| 方法 | 路径 | 鉴权 |
|---|---|---|
| GET | `/health` | 无 |
| POST | `/audit/submit` | Bearer token |
| GET | `/audit/tasks` | Bearer token |
| GET | `/audit/tasks/{request_id}` | Bearer token |
| GET | `/audit/tasks/{request_id}/result` | Bearer token |

CORS：允许 `http://localhost:5173` / `http://127.0.0.1:5173`

## 需要编写的测试文件

### 1. `tests/__init__.py`（空文件，标记包）

### 2. `tests/conftest.py`
- `tmp_path` fixture（pytest 内置，不需手写）
- `test_client` fixture：FastAPI TestClient，设置 `TENANT_KEYS=test-key-001` env
- 通用 stub schema fixture

### 3. `tests/test_command_adapter.py`
覆盖：
- `build_command_prompt("audit", "tests/fixtures/expense/travel-missing-preapproval")` → 期望输出格式
- `_serialize_command_argument("path with spaces")` → 期望 JSON 转义
- `build_command_prompt` 空参数边界
- `run_command_full` mock（patch `server.command_adapter.run_agent_full`）

### 4. `tests/test_core_schema.py`
覆盖（不涉及真实 Claude 调用，全部静态/单元测试）：
- `load_output_schema("common/audit-result")` 返回非空 dict
- `load_output_schema` 路径逃逸防护（`../../etc/passwd` 应 raise）
- `validate_structured_output_semantics` 正确路径：完整合法 audit-result 对象
- `validate_structured_output_semantics` 错误路径：verdict=manual_review 但 manual_review_reason 缺失 → 应 raise
- `validate_structured_output_semantics` 错误路径：risk_dimensions 含非 0-10 整数 → 应 raise
- `validate_structured_output_semantics` 错误路径：verdict 与 result 不一致 → 应 raise

### 5. `tests/test_api_health.py`
覆盖（TestClient，不需 Claude 凭证）：
- `GET /health` → 200
- `GET /health` 返回 body 含 `status` 字段
- `GET /health` 返回体不包含完整 diagnostics（精简摘要）
- `GET /audit/tasks` 无 token → 401 或 403

### 6. `tests/test_api_submit.py`
覆盖（TestClient，mock `run_agent_json` / `audit_task_store`）：
- `POST /audit/submit` mode=upload，含有效 Bearer token → 202
- `POST /audit/submit` 无 token → 401
- `POST /audit/submit` 含 form_json（合法 JSON object）→ 正常接收
- `POST /audit/submit` form_json 非 JSON → 400/422
- `POST /audit/submit` 零附件 → 允许（不应因 0 files 拒绝）
- `POST /audit/submit` 多附件 → 正常接收并返回 request_id

### 7. `tests/test_hook_check_before_write.py`
直接 import 并单测 `check-before-write.py` 的函数：
- `_is_non_empty_string("")` → False
- `_is_non_empty_string(None)` → False
- `_is_non_empty_string("ok")` → True
- `_resolve_audit_result` 含全部 REQUIRED_FIELDS → 通过
- `_resolve_audit_result` 缺少任意一个 REQUIRED_FIELD → 输出 block/拦截信号
- `_resolve_audit_result` verdict 非法 → 拦截

### 8. `tests/test_tenant_isolation.py`
覆盖：
- 使用错误 token → 401
- 使用合法 token → 正常响应

## 约束

1. **不调用真实 Claude API**：所有涉及 `run_agent_json` / `run_agent_full` 的测试必须 mock
2. **不依赖 data/ 目录**：测试数据自行构造或引用 `tests/fixtures/`
3. **不改动 `server/` 生产代码**（只写 `tests/`）
4. `conftest.py` 的 `test_client` 必须设置足够的环境变量让 FastAPI app 可以启动

## 验收标准

- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q` → 全部通过，零 skip，零 error
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .` → 通过
- 测试覆盖：`test_command_adapter`、`test_core_schema`、`test_api_health`、`test_api_submit`、`test_hook_check_before_write`、`test_tenant_isolation` 六个文件均存在
- 每个测试文件至少 4 个测试用例
