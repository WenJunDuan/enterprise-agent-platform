# Enterprise Agent Platform

一个基于 Claude Agent SDK 的企业智能审核平台脚手架。业务规则和审核工作流放在 `.claude/` 与 `knowledge/`

Python 侧只负责运行服务、暴露 HTTP/CLI 接口、获取外部输入、做鉴权与持久化，并把输入提交给 Claude。真正的审核判断、规则命中、证据组织和结论生成都由 Claude 完成。

## 项目概览

- `server/api.py`：FastAPI HTTP 服务入口，提供审核、规则初始化、查询、健康检查等接口
- `server/cli.py`：本地 CLI 外壳，适合开发调试和单次命令调用
- `server/app_server.py`：后台服务管理入口，负责启动、停止、状态检查、日志查看和维护任务
- `server/core.py`：Claude Agent SDK 调用桥接、结构化输出约束、会话控制
- `knowledge/`：结构化规则和制度材料
- `data/`：目录审核样例、上传落盘数据和压测样例
- `logs/`：请求、结果、会话、后台服务状态等运行时数据

## 环境填写

### 1. 前置依赖

本地开发至少需要：

- Python `3.12+`
- Node.js `20+`
- `uv`

说明：

- Claude Agent SDK 依赖 Claude Code CLI 运行时，因此本机和容器都需要 Node.js。
- 仓库当前通过 `uv` 管理依赖和命令运行。

### 2. 安装依赖

```bash
uv sync
```

### 3. 复制环境文件

```bash
cp .env.example .env
```

### 4. 最小可运行配置

如果你只想先把 CLI 或本地服务跑起来，`.env` 至少填写这 3 项：

```bash
MODEL_BASE_URL=http://your-model-gateway.example.com
MODEL_API_KEY=your-model-api-key
MODEL_NAME=gpt-5.4
```

说明：

- `MODEL_BASE_URL`：模型网关地址
- `MODEL_API_KEY`：模型网关 API Key
- `MODEL_NAME`：后端实际模型名。当前运行时会自动把它映射到 Claude SDK 可识别的别名

### 5. 常用环境变量说明

下面这些项通常会一起配置：

```bash
# 可选：当网关把 token 和 API Key 分开时使用
# MODEL_AUTH_TOKEN=your-claude-gateway-access-token

# 可选：额外请求头，支持 JSON 对象
# MODEL_CUSTOM_HEADERS={"HTTP-Referer":"https://your-app.example.com","X-Title":"enterprise-agent-platform"}

# HTTP API 鉴权 token，左边是租户名，右边是 Bearer token
TENANT_KEYS={"default":"sk-wdsddferfer1243HJGTIOJlL809jjl90dasdn9"}

# 后台服务监听地址与端口
APP_SERVER_HOST=127.0.0.1
APP_SERVER_PORT=8000

# 单次调用预算上限
MAX_BUDGET_USD=1.0

# 异步审核运行超时秒数
AUDIT_TASK_RUNNING_TIMEOUT_SECONDS=600

# 上传目录保留天数
SUBMISSION_RETENTION_DAYS=7

# 单文件上传大小限制
MAX_UPLOAD_FILE_BYTES=10485760
```

建议：

- 只调 CLI 时，优先确认 `MODEL_BASE_URL`、`MODEL_API_KEY`、`MODEL_NAME`
- 要调 HTTP API 时，再补 `TENANT_KEYS`
- 要对外提供服务时，把 `APP_SERVER_HOST` 改成 `0.0.0.0`

### 6. 启动前运行时检查

先确认配置已经被运行时正确识别：

```bash
uv run python -m server.cli runtime
```

如果环境变量缺失，CLI 会在调用模型前直接报出可读错误，而不是等到 SDK 深处才失败。

## 项目启动

### 1. CLI 启动方式

本地开发和调试时，最常用的是直接走 CLI：

```bash
uv run python -m server.cli ask "你好"
uv run python -m server.cli init-rules knowledge/external/数睿员工手册.pdf expense
uv run python -m server.cli audit data/case1
uv run python -m server.cli audit-json data/case1
```

说明：

- `ask`：单次 prompt 调用
- `init-rules`：把原始制度文件初始化为结构化规则
- `audit`：调用审核流程，输入可以是文件也可以是目录
- `audit-json`：直接拿结构化 JSON 结果，适合调试
- `distill-memory`：当前只保留为 Claude 命令路径，适合通过 `ask "/distill-memory ..."` 触发，不暴露 HTTP API

### 2. 前台启动 HTTP 服务

适合本机调试、联调和查看实时报错：

```bash
uv run python -m server.cli serve --host 127.0.0.1 --port 8000
```

如果你已经在 `.env` 里配置了 `APP_SERVER_HOST` 和 `APP_SERVER_PORT`，也可以直接用默认参数：

```bash
uv run python -m server.cli serve
```

### 3. 后台启动服务

适合持续运行和部署后运维：

```bash
uv run app-server start
uv run app-server status
uv run app-server inspect
uv run app-server doctor --strict
uv run app-server logs --lines 100
uv run app-server stop
```

常用检查：

```bash
uv run app-server doctor --require-running --require-ready
```

### 4. 本地维护命令

```bash
uv run app-server maintain
```

这个命令会处理轻量维护任务，例如清理过期上传目录、归档旧日志等。

## HTTP API 使用

### 1. 服务能力面

当前服务主要暴露这些接口：

- `POST /chat`
- `POST /chat/stream`
- `POST /init-rules`
- `POST /audit`
- `POST /audit/submit`
- `GET /audit/tasks/{request_id}`
- `GET /audit/tasks/{request_id}/result`
- `GET /health`
- `GET /ready`
- `GET /sessions`
- `GET /conversations`
- `GET /requests`
- `GET /requests/{request_id}`
- `GET /results`
- `GET /results/{request_id}`
- `GET /review-deltas`
- `GET /review-deltas/{request_id}`
- `GET /memories`
- `GET /memories/{memory_id}`
- `GET /governance/assets`
- `GET /sessions/{session_id}/messages`

### 2. 鉴权方式

服务从 `.env` 的 `TENANT_KEYS` 读取 Bearer token。

例如：

```bash
TENANT_KEYS={"default":"sk-wdsddferfer1243HJGTIOJlL809jjl90dasdn9"}
```

请求头写法：

```http
Authorization: Bearer sk-wdsddferfer1243HJGTIOJlL809jjl90dasdn9
```

如果你修改了 `.env` 中的 token，需要重启服务。

### 3. 基础调用示例

先从 `.env` 读取服务端口，避免示例里的端口和实际配置漂移：

```bash
APP_SERVER_PORT="$(grep '^APP_SERVER_PORT=' .env | tail -n 1 | cut -d= -f2- | tr -d '\r')"
APP_SERVER_PORT="${APP_SERVER_PORT:-8000}"
```

```bash
curl -X POST "http://127.0.0.1:${APP_SERVER_PORT}/chat" \
  -H "Authorization: Bearer sk-wdsddferfer1243HJGTIOJlL809jjl90dasdn9" \
  -H "Content-Type: application/json" \
  -d '{"message":"你好"}'

curl -X POST "http://127.0.0.1:${APP_SERVER_PORT}/init-rules" \
  -H "Authorization: Bearer sk-wdsddferfer1243HJGTIOJlL809jjl90dasdn9" \
  -H "Content-Type: application/json" \
  -d '{"source_path":"knowledge/external/数睿员工手册.pdf","domain":"expense"}'

curl -X POST "http://127.0.0.1:${APP_SERVER_PORT}/audit" \
  -H "Authorization: Bearer sk-wdsddferfer1243HJGTIOJlL809jjl90dasdn9" \
  -H "Content-Type: application/json" \
  -d '{"path":"data/case1"}'
```

## 审核与压测教程

### 1. 目录审核模式

目录模式适合本地样例、前端联调和压力测试。

```bash
curl -X POST "http://127.0.0.1:${APP_SERVER_PORT}/audit/submit" \
  -H "Authorization: Bearer sk-wdsddferfer1243HJGTIOJlL809jjl90dasdn9" \
  -H "Content-Type: application/json" \
  -d '{"mode":"directory","directory_path":"data/case1"}'
```

当前约束：

- `directory_path` 必须指向真实存在的目录
- 目录必须位于项目根 `data/` 下面

压测时可以直接使用：

- `data/case1`
- `data/case2` 到 `data/case21`
- `data/scenario-index.json` 用于查看每个 case 的场景说明

### 2. 上传审核模式

上传模式更接近真实生产请求：

```bash
curl -X POST "http://127.0.0.1:${APP_SERVER_PORT}/audit/submit" \
  -H "Authorization: Bearer sk-wdsddferfer1243HJGTIOJlL809jjl90dasdn9" \
  -F 'mode=upload' \
  -F 'form_json={"case_id":"case1","applicant_name":"张三","expense_type":"业务招待"}' \
  -F 'files=@data/case1/dzfp_26322000002323013701_南通烛照智能云平台有限公司_20260326133128.pdf'
```

以上 HTTP 示例统一使用 `.env` 中的 `APP_SERVER_PORT`，默认值是 `8000`。

当前上传校验规则：

- `form_json` 必须能解析成 JSON 对象
- 必填字段：
  - `case_id`
  - `applicant_name`
  - `expense_type`
- 允许的文件扩展名：
  - `.pdf`
  - `.png`
  - `.jpg`
  - `.jpeg`
  - `.webp`
- 空文件会被拒绝
- 文件大小不能超过 `MAX_UPLOAD_FILE_BYTES`

成功上传后，服务会把材料落到：

- `data/submissions/{request_id}/audit-request.json`
- `data/submissions/{request_id}/<uploaded files>`

### 3. 异步审核轮询流程

推荐前后端集成流程：

1. 调 `POST /audit/submit` 提交任务
2. 调 `GET /audit/tasks/{request_id}` 轮询状态
3. 调 `GET /audit/tasks/{request_id}/result` 读取最终审核结果
4. 只有在你需要完整归档包时，才去调 `GET /results/{request_id}`

任务状态接口返回的核心字段包括：

- `request_id`
- `status`
- `mode`
- `source_mode`
- `case_path`
- `claim_id`
- `result_file`
- `error_detail`
- `progress_message`
- `submitted_at`
- `started_at`
- `finished_at`
- `updated_at`

状态值包括：

- `accepted`
- `running`
- `completed`
- `failed`

轻量结果接口 `GET /audit/tasks/{request_id}/result` 会直接返回最终审核 payload，通常包含：

- `result`
- `conclusion`
- `explanation`
- `reasons`
- `policy_refs`
- `risk_score`
- `extracted_data`
- `evidence_chain`
- `verdict`
- `manual_review_reason`（`verdict == "manual_review"` 时必填，枚举：`missing_approval` / `rule_gap` / `data_conflict` / `insufficient_evidence` / `budget_exceeded` / `invoice_invalid` / `pre_approval_mismatch`）
- `risk_dimensions`（可选，各维度打分数组，`name` ∈ `invoice` / `amount` / `approval` / `budget` / `anomaly`，`score` 取整数 0–10）

### 5. 查询与追溯能力

当前查询面已经支持这些常用过滤：

- `GET /requests`
  - 返回 `items + meta`
  - `conversation_id`
  - `claude_session_id`
  - `route`
  - `status`
- `GET /results`
  - 返回 `items + meta`
  - `conversation_id`
  - `claim_id`
  - `verdict`
  - `manual_review_reason`
- `GET /results/{request_id}`
  - 返回 `record`
  - 返回 `payload`
  - 返回 `linked_memories`（由该结果沉淀出的 memory 资产）
- `GET /review-deltas`
  - 返回 `items + meta`
  - `claim_id`
  - `final_recommendation`
  - `reviewer_verdict`
  - `agrees_with_initial`
- `GET /review-deltas/{request_id}`
  - 返回 `record`
  - 返回 `payload`
- `GET /memories`
  - 返回 `items + meta`
  - `domain`
  - `category`
  - `recommended_verdict`
  - `manual_review_reason`
  - `source_request_id`
- `GET /governance/assets`
  - 返回 rules / memory 资产校验结果

说明：

- `distill-memory` 不暴露 HTTP API；memory 资产通过 `GET /memories` / `GET /memories/{memory_id}` 查询。
- 当前请求日志仍保留在 `logs/service/requests/*.jsonl`，但查询索引已经切到 SQLite。
- 所有查询类列表接口的 `meta` 当前至少包含：`limit`、`offset`、`returned`，有过滤条件时会额外返回 `filters`。

### 6. 错误返回契约

HTTP 错误现在统一保留兼容字段 `detail`，同时补充结构化 `error` 对象，便于前端稳定处理与日志追踪：

```json
{
  "detail": "Result not found",
  "error": {
    "code": "not_found",
    "message": "Result not found",
    "status_code": 404,
    "path": "/results/req-missing",
    "correlation_id": "f7d7d6e6f0a64f72b7d00cbf13f7e3d3"
  }
}
```

说明：

- `detail` 继续保留，兼容旧调用方。
- `error.code` 适合前端分支判断。
- `error.correlation_id` 与响应头 `X-Request-ID` 对齐，便于联调和日志排查。

## 部署教程

### 1. Docker 镜像构建

仓库已经自带 [Dockerfile](./Dockerfile)，包含 Python 和 Node.js 运行时。

构建镜像：

```bash
docker build -t enterprise-agent-platform:local .
```

### 2. 直接用 Docker 运行

```bash
APP_SERVER_PORT="$(grep '^APP_SERVER_PORT=' .env | tail -n 1 | cut -d= -f2- | tr -d '\r')"
APP_SERVER_PORT="${APP_SERVER_PORT:-8000}"

docker run --rm \
  --env-file .env \
  -p "${APP_SERVER_PORT}:${APP_SERVER_PORT}" \
  -v "$(pwd)/.claude:/app/.claude" \
  -v "$(pwd)/knowledge:/app/knowledge" \
  -v "$(pwd)/data:/app/data" \
  -v "$(pwd)/logs:/app/logs" \
  enterprise-agent-platform:local
```

这里先从 `.env` 中提取 `APP_SERVER_PORT`，再把宿主机端口和容器端口同时映射到这个值，避免你改了 `.env` 还要再手工改 `docker run` 命令。

启动后可以直接访问：

- `http://127.0.0.1:${APP_SERVER_PORT}/health`
- `http://127.0.0.1:${APP_SERVER_PORT}/ready`

### 3. 使用 Docker Compose

仓库自带 [docker-compose.yml](./docker-compose.yml)：

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f agent-server
docker compose down
```

当前 compose 文件会挂载：

- `./.claude:/app/.claude`
- `./knowledge:/app/knowledge`
- `./data:/app/data`
- `./logs:/app/logs`

说明：

- `.claude`、`knowledge`、`data`、`logs` 建议作为持久化卷保留
- Compose 现在会从 `.env` 读取 `APP_SERVER_PORT` 作为宿主机和容器内的服务端口
- Compose 现在会从 `.env` 读取 `APP_SERVER_NAME` 作为容器名，默认回退为 `enterprise-agent-platform`
- Compose 使用 `restart: unless-stopped`

### 4. 部署约束

这个项目更适合常驻实例，不适合 Serverless：

- Claude Agent SDK 底层会拉起 CLI 子进程，单次调用可能持续几十秒到几分钟
- 服务依赖本地文件系统，需要访问 `.claude`、`knowledge`、`data`、`logs`
- 生产建议部署在长期运行的 VM、容器或有状态主机上

## 测试教程

### 1. 运行全部测试

```bash
uv run pytest
```

### 2. 只跑主测试文件

```bash
uv run pytest tests/test_bootstrap.py -v
```

### 3. 运行静态检查

```bash
uv run ruff check .
```

### 4. 启动后健康检查

前台或后台服务启动后，可以这样检查：

```bash
curl "http://127.0.0.1:${APP_SERVER_PORT}/health"
curl "http://127.0.0.1:${APP_SERVER_PORT}/ready"
```

如果你走后台服务，还可以执行：

```bash
uv run app-server doctor --require-running --require-ready
```

### 5. 本地冒烟测试

#### CLI 冒烟

```bash
uv run python -m server.cli runtime
uv run python -m server.cli ask "你好"
uv run python -m server.cli audit-json data/case1
```

#### HTTP 冒烟

```bash
curl -X POST "http://127.0.0.1:${APP_SERVER_PORT}/audit/submit" \
  -H "Authorization: Bearer sk-wdsddferfer1243HJGTIOJlL809jjl90dasdn9" \
  -H "Content-Type: application/json" \
  -d '{"mode":"directory","directory_path":"data/case2"}'
```

### 6. 压力测试建议

如果你要做目录模式压测，建议直接用这批本地样例：

- 合法样例：`data/case2` 到 `data/case9`
- 缺件与缺文件：`data/case10` 到 `data/case13`
- 表单脏数据与越界：`data/case14` 到 `data/case17`
- 重复材料、冲突材料、脏文本、伪文件：`data/case18` 到 `data/case21`

详细场景说明见 [scenario-index.json](./data/scenario-index.json)。

## 本地目录结构

运行时最常用的目录如下：

```text
logs/
  runtime/app-server/
    server.pid
    server.status.json
    stdout.log
    stderr.log
  service/requests/
    requests-YYYY-MM.jsonl
    index.sqlite3
  service/audit-tasks/
    tasks.json
  knowledge/
    memory-index.sqlite3
  sessions/
    index.sqlite3
    events/YYYY/MM/DD/*.jsonl
  results/
    index.sqlite3
    by-request/YYYY/MM/DD/{request_id}.json
  review-deltas/
    index.sqlite3
    by-request/YYYY/MM/DD/{request_id}.json
data/
  case1/
  case2/
  ...
  case21/
  submissions/{request_id}/
    audit-request.json
    <uploaded files...>
```

## 补充说明

- 结构化 JSON 输出通过 Claude Agent SDK 的 `output_format` 强制约束，不依赖提示词“约定”
- 请求审计日志保留在 `logs/service/requests/*.jsonl`
- 请求查询索引当前使用 SQLite：`logs/service/requests/index.sqlite3`
- 会话与结果查询索引当前使用 SQLite：`logs/sessions/index.sqlite3`、`logs/results/index.sqlite3`
- memory 查询索引当前使用 SQLite：`logs/knowledge/memory-index.sqlite3`
- review_delta 查询索引当前使用 SQLite：`logs/review-deltas/index.sqlite3`
- 原始事件流和结果归档仍保留在文件系统里，并通过 `request_id` 串联
- post-write 二审 hook 当前不是全量执行；只对 `rejected`、`risk_score >= 70`、以及部分高风险 `manual_review_reason` 场景触发，避免不必要的二次成本
- 业务规则放在 `.claude/` 和 `knowledge/`；Python 不直接承载业务判断
- `MODEL_NAME` 如果是自定义网关模型，例如 `gpt-5.4`，运行时会自动映射 Claude 别名，例如 `sonnet`
- 如果网关需要额外鉴权头，可以通过 `MODEL_CUSTOM_HEADERS` 传入
