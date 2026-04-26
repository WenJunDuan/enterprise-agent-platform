# Enterprise Agent Platform

一个基于 Claude Agent SDK 的企业审核平台脚手架。

项目分工很明确：

- Python 侧负责 HTTP / CLI 入口、鉴权、进程管理、归档和诊断
- `.claude/` 与 `knowledge/` 承载业务规则、agent 工作流与输出契约
- `logs/` 保存请求、会话、结果、review delta 和运行时状态

如果你只想先跑起来，先看“快速开始”；如果你想查端口和命令，直接看“端口与地址”和“命令总览”。

## 快速开始

### 1. 前置依赖

- Python `3.12+`
- Node.js `20+`
- `uv`

说明：

- Claude Agent SDK 依赖 Claude Code CLI 运行时，所以本机和容器都需要 Node.js。
- 仓库统一使用 `uv` 管理依赖和命令运行。

### 2. 安装依赖

```bash
uv sync
```

### 3. 初始化环境文件

```bash
cp .env.example .env
```

最小可运行配置通常只需要这三项：

```bash
MODEL_BASE_URL=http://your-model-gateway.example.com
MODEL_API_KEY=your-model-api-key
MODEL_NAME=gpt-5.4
```

### 4. 运行时检查

```bash
uv run python -m server.cli runtime
```

这个命令会输出脱敏后的运行时配置，能帮你确认：

- 模型网关地址是否生效
- 鉴权信息是否已注入 Claude SDK
- 当前模型名是否被正确映射

### 5. 启动服务

前台启动，适合本地调试：

```bash
uv run python -m server.cli serve
```

后台启动，适合持续运行：

```bash
uv run app-server start
uv run app-server status
```

### 6. 做一次最小冒烟

CLI：

```bash
uv run python -m server.cli ask "你好"
```

HTTP：

```bash
APP_SERVER_PORT="$(grep '^APP_SERVER_PORT=' .env | tail -n 1 | cut -d= -f2- | tr -d '\r')"
APP_SERVER_PORT="${APP_SERVER_PORT:-8000}"

curl "http://127.0.0.1:${APP_SERVER_PORT}/health"
```

## 端口与地址

当前项目只有一个 HTTP 服务端口，没有单独的管理端口。

- 监听地址来自 `APP_SERVER_HOST`
- 监听端口来自 `APP_SERVER_PORT`
- `.env.example` 默认值是 `127.0.0.1:8000`
- 对外提供服务时，通常把 host 改成 `0.0.0.0`

常用地址：

- `http://127.0.0.1:${APP_SERVER_PORT}/health`
- `http://127.0.0.1:${APP_SERVER_PORT}/docs`
- `http://127.0.0.1:${APP_SERVER_PORT}/redoc`

说明：

- `/health` 当前返回精简摘要：`status`、`app_server`、`failing_checks`、`advisories`
- 当 `status != "ok"` 时，`/health` 会返回 `503`
- 更完整的本地运行诊断继续走 `uv run app-server doctor`

查看当前实际绑定值：

```bash
uv run app-server status
```

如果你是前台运行，也可以直接看 `.env`：

```bash
grep '^APP_SERVER_HOST=' .env
grep '^APP_SERVER_PORT=' .env
```

## 命令总览

项目有两套 CLI：

1. `python -m server.cli`
2. `app-server`

前者偏业务和查询，后者偏服务进程管理。

### 业务 CLI

完整帮助：

```bash
uv run python -m server.cli --help
```

常用命令：

| 命令 | 用途 |
| --- | --- |
| `runtime` | 输出当前脱敏后的 Claude 运行时配置 |
| `ask` | 执行一次单轮 prompt |
| `audit` | 对文件或目录触发审核流程 |
| `audit-json` | 执行审核并打印结构化 JSON 结果 |
| `init-rules` | 从源材料初始化结构化规则 |
| `sessions` | 查看已记录的应用会话 |
| `transcript` | 查看某个 session 的 Claude transcript |
| `conversations` | 查看 conversation 摘要 |
| `requests` | 查看服务请求审计记录 |
| `request-detail` | 查看单条请求审计 |
| `results` | 查看归档后的结构化结果 |
| `result-detail` | 查看单条归档结果 |
| `memories` | 查看 memory 资产索引 |
| `memory-detail` | 查看单条 memory 资产 |
| `review-deltas` | 查看复核差异索引 |
| `review-delta-detail` | 查看单条 review delta |
| `validate-assets` | 校验 `knowledge/` 下 rules 和 memory 资产 |
| `serve` | 以前台方式启动 HTTP 服务 |

示例：

```bash
uv run python -m server.cli runtime
uv run python -m server.cli ask "你好"
uv run python -m server.cli init-rules knowledge/external/数睿员工手册.pdf expense
uv run python -m server.cli audit data/case1
uv run python -m server.cli audit-json data/case1
uv run python -m server.cli results --limit 20
uv run python -m server.cli review-deltas --limit 20
```

补充说明：

- `distill-memory` 当前不作为 Python CLI 子命令暴露。
- 如果需要触发记忆沉淀，走 Claude command 路径即可，例如 `ask "/distill-memory ..."`。

### 服务管理 CLI

完整帮助：

```bash
uv run app-server --help
```

常用命令：

| 命令 | 用途 |
| --- | --- |
| `start` | 后台启动 API 服务 |
| `stop` | 停止后台服务 |
| `restart` | 重启后台服务 |
| `status` | 查看当前运行状态、host、port、日志文件位置 |
| `logs` | 查看后台服务日志 |
| `maintain` | 执行轻量维护任务 |
| `doctor` | 运行运行时诊断，可加严格检查 |

示例：

```bash
uv run app-server start
uv run app-server status
uv run app-server logs --lines 100
uv run app-server doctor --require-running
uv run app-server stop
```

## 环境变量

最常用的配置项如下：

| 变量 | 说明 | 默认值 |
| --- | --- | --- |
| `MODEL_BASE_URL` | 模型网关地址 | 无 |
| `MODEL_API_KEY` | 模型网关 API Key | 无 |
| `MODEL_AUTH_TOKEN` | 可选的额外鉴权 token | 无 |
| `MODEL_NAME` | 实际调用的模型名 | 无 |
| `MODEL_CUSTOM_HEADERS` | 可选的额外请求头，支持 JSON 对象 | 无 |
| `TENANT_KEYS` | HTTP API Bearer token 映射 | `{"default":"sk-default"}` |
| `APP_SERVER_HOST` | 服务监听地址 | `127.0.0.1` |
| `APP_SERVER_PORT` | 服务监听端口 | `8000` |
| `MAX_BUDGET_USD` | 单次调用预算上限 | `1.0` |
| `AUDIT_TASK_RUNNING_TIMEOUT_SECONDS` | 异步审核 running 超时阈值 | `600` |
| `SUBMISSION_RETENTION_DAYS` | 上传目录保留天数 | `7` |
| `MAX_UPLOAD_FILE_BYTES` | 单文件上传大小上限 | `10485760` |
| `ALLOW_UNSCOPED_CONTINUE_RECENT` | 是否允许未指定 conversation 时继续最近会话 | `false` |
| `APP_SERVER_LOG_MAX_BYTES` | app-server 单个日志文件最大字节数 | `5242880` |
| `APP_SERVER_LOG_BACKUPS` | app-server 日志轮转数量 | `5` |

说明：

- 如果 `MODEL_NAME` 是自定义网关模型名，例如 `gpt-5.4`，运行时会自动映射到 Claude SDK 可识别的别名。
- 如果网关要求自定义请求头，可以用 `MODEL_CUSTOM_HEADERS` 注入。
- 如果你忘了配置 `TENANT_KEYS`，服务会退回默认值并给出告警；开发环境可用，生产环境不要这样配。

## HTTP API

### 鉴权方式

服务从 `.env` 的 `TENANT_KEYS` 读取 Bearer token。

示例：

```bash
TENANT_KEYS={"default":"sk-your-token"}
```

请求头写法：

```http
Authorization: Bearer sk-your-token
```

### 路由清单

文档与诊断：

- `GET /openapi.json`
- `GET /docs`
- `GET /redoc`
- `GET /health`

业务调用：

- `POST /audit/submit`

异步审核：

- `GET /audit/tasks/{request_id}`
- `GET /audit/tasks/{request_id}/result`

边界说明：

- HTTP API 现在只保留最小业务调用面
- 追溯、治理、查询和详细排障统一走 CLI

### 基础调用示例

```bash
APP_SERVER_PORT="$(grep '^APP_SERVER_PORT=' .env | tail -n 1 | cut -d= -f2- | tr -d '\r')"
APP_SERVER_PORT="${APP_SERVER_PORT:-8000}"
TOKEN="sk-your-token"
```

```bash
curl "http://127.0.0.1:${APP_SERVER_PORT}/health"
```

## 审核流程

### 目录模式

适合本地样例、联调和压测：

```bash
curl -X POST "http://127.0.0.1:${APP_SERVER_PORT}/audit/submit" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"mode":"directory","directory_path":"data/case1"}'
```

约束：

- `directory_path` 必须存在
- 目录必须位于项目根 `data/` 下

### 上传模式

更接近真实生产请求：

```bash
curl -X POST "http://127.0.0.1:${APP_SERVER_PORT}/audit/submit" \
  -H "Authorization: Bearer ${TOKEN}" \
  -F 'mode=upload' \
  -F 'form_json={"company_form_id":"case1","payload":{"任意字段":"任意值"}}' \
  -F 'files=@data/case1/dzfp_26322000002323013701_南通烛照智能云平台有限公司_20260326133128.pdf'
```

上传校验：

- `form_json` 可选；传入时必须是 JSON 对象
- 除 `mode` / `form_json` / `files` 外的普通 multipart 文本字段会原样归档到 `fields`
- Python 不校验任何业务字段；不同公司、不同业务线的表单语义交给 Claude agent 审核
- `files` 可选，支持 0 个或多个附件；服务端不按业务扩展名白名单拦截
- 只有完全空的上传（无 `form_json`、无普通字段、无附件）会被拒绝
- 空文件会被拒绝
- 文件大小不能超过 `MAX_UPLOAD_FILE_BYTES`

上传落盘位置：

- `data/submissions/{request_id}/audit-request.json`
- `data/submissions/{request_id}/<uploaded files>`

### 异步轮询流程

推荐顺序：

1. `POST /audit/submit`
2. `GET /audit/tasks/{request_id}`
3. `GET /audit/tasks/{request_id}/result`

任务状态有四种：

- `accepted`
- `running`
- `completed`
- `failed`

`GET /audit/tasks/{request_id}` 当前只返回业务侧真正需要的字段：

- `request_id`
- `status`
- `mode`
- `claim_id`
- `error_detail`
- `progress_message`
- `submitted_at`
- `started_at`
- `finished_at`
- `updated_at`

轻量结果接口 `GET /audit/tasks/{request_id}/result` 会直接返回最终审核 payload，通常包含：

- `claim_id`
- `verdict`
- `result`
- `conclusion`
- `explanation`
- `reasons`
- `policy_refs`
- `risk_score`
- `extracted_data`
- `evidence_chain`
- `manual_review_reason`
- `risk_dimensions`

## CLI 查询与追溯

为避免 HTTP API 和 CLI 暴露重复接口，查询、治理和详细排障已经统一收回到 CLI。

常用命令：

- `uv run python -m server.cli runtime`
- `uv run python -m server.cli ask "你好"`
- `uv run python -m server.cli init-rules <source> <domain>`
- `uv run python -m server.cli audit <path>`
- `uv run python -m server.cli audit-json <path>`
- `uv run python -m server.cli sessions`
- `uv run python -m server.cli transcript <session_id>`
- `uv run python -m server.cli conversations`
- `uv run python -m server.cli requests`
- `uv run python -m server.cli request-detail <request_id>`
- `uv run python -m server.cli results`
- `uv run python -m server.cli result-detail <request_id>`
- `uv run python -m server.cli memories`
- `uv run python -m server.cli memory-detail <memory_id>`
- `uv run python -m server.cli review-deltas`
- `uv run python -m server.cli review-delta-detail <request_id>`
- `uv run python -m server.cli validate-assets`

## 错误返回

HTTP 错误统一保留兼容字段 `detail`，并补充结构化 `error`：

```json
{
  "detail": "Audit task not found",
  "error": {
    "code": "not_found",
    "message": "Audit task not found",
    "status_code": 404,
    "path": "/audit/tasks/req-missing",
    "correlation_id": "f7d7d6e6f0a64f72b7d00cbf13f7e3d3"
  }
}
```

说明：

- `detail` 保留给旧调用方兼容使用
- `error.code` 适合前端做稳定分支判断
- `error.correlation_id` 与响应头 `X-Request-ID` 对齐，便于日志排查

## 部署

### Docker

构建镜像：

```bash
docker build -t enterprise-agent-platform:local .
```

运行：

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

### Docker Compose

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f agent-server
docker compose down
```

当前 `docker-compose.yml` 会挂载：

- `./.claude:/app/.claude`
- `./knowledge:/app/knowledge`
- `./data:/app/data`
- `./logs:/app/logs`

### 部署约束

这个项目更适合常驻实例，不适合 Serverless：

- Claude Agent SDK 会拉起 CLI 子进程
- 单次调用可能持续几十秒到几分钟
- 服务依赖本地文件系统访问 `.claude`、`knowledge`、`data`、`logs`

更适合的部署形态：

- VM
- 常驻容器
- 有状态主机

## 测试与排障

### 测试

```bash
uv run pytest
uv run ruff check .
```

### 常用健康检查

```bash
curl "http://127.0.0.1:${APP_SERVER_PORT}/health"
uv run app-server doctor --require-running
```

### 本地冒烟

CLI：

```bash
uv run python -m server.cli runtime
uv run python -m server.cli ask "你好"
uv run python -m server.cli audit-json data/case1
```

HTTP：

```bash
curl -X POST "http://127.0.0.1:${APP_SERVER_PORT}/audit/submit" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"mode":"directory","directory_path":"data/case2"}'
```

### 压测样例

目录模式压测可直接使用：

- `data/case2` 到 `data/case9`：相对合法样例
- `data/case10` 到 `data/case13`：缺件或缺文件
- `data/case14` 到 `data/case17`：脏数据或越界
- `data/case18` 到 `data/case21`：重复、冲突、脏文本、伪文件

详细场景见 [`data/scenario-index.json`](./data/scenario-index.json)。

## 目录结构

最常用的目录如下：

```text
.claude/              Claude commands, agents, hooks, skills, contracts
knowledge/            结构化规则、制度材料、memory 资产
data/                 本地 case 样例与上传落盘目录
logs/                 请求、结果、会话、runtime、review delta 等运行时归档
server/               Python 服务外壳、CLI、平台层与 stores
tests/                测试代码与 fixtures
```

运行时最常查的路径：

```text
logs/runtime/app-server/
  server.pid
  server.status.json
  stdout.log
  stderr.log

logs/service/requests/
  requests-YYYY-MM.jsonl
  index.sqlite3

logs/service/audit-tasks/
  tasks.json

logs/results/
  index.sqlite3
  by-request/YYYY/MM/DD/{request_id}.json

logs/review-deltas/
  index.sqlite3
  by-request/YYYY/MM/DD/{request_id}.json

logs/knowledge/
  memory-index.sqlite3

logs/sessions/
  index.sqlite3
  events/YYYY/MM/DD/*.jsonl
```

## 补充说明

- 结构化 JSON 输出由 Claude Agent SDK `output_format` + JSON Schema 强制约束，不依赖提示词口头约定
- 请求审计日志保留在 `logs/service/requests/*.jsonl`，查询索引使用 SQLite
- 会话、结果、memory、review delta 查询索引当前都使用 SQLite
- 原始事件流和最终结果归档仍保留在文件系统中，并通过 `request_id` 串联
- post-write 二审 hook 不是全量执行，只对高风险或冲突场景触发
- 业务判断继续放在 `.claude/` 与 `knowledge/`；Python 不直接承载业务语义
