# Enterprise Agent Platform

基于 Claude Agent SDK 的企业审核平台。Python 负责 HTTP/CLI 入口、鉴权、进程管理与归档；`.claude/` 与 `knowledge/` 承载审核规则、agent 工作流与输出契约；审核判断由 Claude（经模型网关）完成。

**运行链路**

```
前端(ui/dist) ──┐
                ├─→ 后端 FastAPI(:9999) ──→ LiteLLM(:4000) ──→ Qwen / 任意 Anthropic 兼容模型
浏览器/接口 ────┘     鉴权·归档·异步任务       Claude名映射·tool_use 翻译
```

后端默认同源托管前端 `ui/dist`，无需单独前端服务。模型层用 LiteLLM 把 `claude-*` 名映射到 Qwen 并双向翻译工具调用（LiteLLM 由运维独立部署管理）。

---

## 快速开始（本地）

```bash
uv sync                                   # 装 Python 依赖（含 claude-agent-sdk）
# 创建 .env（仓库不含模板，最小三项见下方“配置”）
uv run python -m server.cli runtime       # 配置自检：status=ok / errors=[]
uv run python -m server.cli serve         # 前台起后端（调试用）
```

前端联调：

```bash
cd ui && npm install
# 创建 ui/.env.local（仓库不含模板）：
#   VITE_API_BASE=/                               # 走 vite 代理，免跨域
#   VITE_API_PROXY_TARGET=http://127.0.0.1:9999   # 后端地址
#   VITE_TENANT_TOKEN=<后端 TENANT_KEYS 的某个 value>
npm run dev                               # http://localhost:5173
```

> 前置：Python 3.12+、`uv`、Node 18+（构建前端 + Claude Agent SDK 自带的 CLI 运行时）。

---

## 配置

`.env`（仓库不含 `.env.example`，按需创建，密钥不入库）。最小可运行：

```dotenv
MODEL_BASE_URL=http://127.0.0.1:4000          # LiteLLM 地址（或任意 Anthropic 兼容、能透传 tool_use 的端点）
MODEL_AUTH_TOKEN=<LiteLLM master key>
MODEL_NAME=claude-opus-4-8                     # 保持 Claude 名 → CLI 走完整能力档，LiteLLM 映射到真实模型
CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS=1       # 非 Anthropic 后端需剥掉 beta 头，否则常 400
TENANT_KEYS={"default":"sk-your-token"}        # HTTP API Bearer token 映射
```

常用可选项：

| 变量 | 说明 | 默认 |
| --- | --- | --- |
| `APP_SERVER_HOST` / `APP_SERVER_PORT` | 监听地址/端口；对外服务设 `0.0.0.0` | `127.0.0.1` / `8000` |
| `CORS_ALLOWED_ORIGINS` | 跨域白名单（逗号分隔，支持 `re:` 正则） | `localhost:5173` 等 |
| `MAX_BUDGET_USD` | 单次审核成本上限 | `1.0` |
| `ALLOW_INSECURE_DEFAULT_TENANT_KEY` | 允许默认示例 token；生产必须 `false` | `false` |
| `AUDIT_TIMEOUT_SEC` | 单次审核硬超时（秒）；现场内网模型/网络慢时调大 | `180` |
| `AUDIT_TASK_RUNNING_TIMEOUT_SECONDS` | 重启时回收残留 `running` 任务的阈值（秒） | `600` |
| `MAX_CONCURRENT_AUDITS` | 同时进行的审核上限，超额提交排队保持 `accepted` | `2` |
| `AUDIT_INLINE_MAX_TURNS` | 内联审核最大轮数，封顶最坏耗时 | `8` |

> `MODEL_NAME` 原样透传到 `ANTHROPIC_MODEL`。想用 SDK alias 路由可另配 `ANTHROPIC_DEFAULT_{OPUS,SONNET,HAIKU}_MODEL`。完整变量见 `server/platform/config.py`。
>
> 二次复核 hook 已从 `.claude/settings.json` 移除（一次性审核）；如需重启见 `.claude/CLAUDE.md` 的“二次复核成本治理”。

---

## 部署

两种部署方式，**Docker Compose 首选**；无 Docker 时用原地 + systemd。

### 方式 A · Docker Compose（推荐）

镜像自包含 SDK 自带的 `claude` CLI（无需 node）与同源前端 `ui/dist`，模型层 LiteLLM
与平台应用分成两个 compose 项目管理：

- `/opt/application/litellm/`：LiteLLM 的 `docker-compose.yml`、`litellm_config.yaml`、`litellm.env`
- `/opt/application/enterprise-agent-platform/`：平台自己的 `Dockerfile`、`docker-compose.yml`、`enterprise-agent.env`

```bash
# 1) 前端产物与规则必须存在
cd ui && npm install && npm run build && cd ..
test -f knowledge/expense/travel.rules.json

# 2) 目标机：准备共享网络
docker network create enterprise-agent-net || true

# 3) 启动 LiteLLM
cd /opt/application/litellm
cp litellm.env.example litellm.env
# 填 QWEN_API_BASE / QWEN_API_KEY / LITELLM_MASTER_KEY
docker compose up -d
curl http://127.0.0.1:4000/health/liveliness

# 4) 启动平台应用
cd /opt/application/enterprise-agent-platform
cp enterprise-agent.env.example enterprise-agent.env
# 填 MODEL_AUTH_TOKEN / TENANT_KEYS / CORS_ALLOWED_ORIGINS
docker compose up -d --build
curl http://127.0.0.1:9999/health
```

> 若目标机断网，先在同架构联网机器 `docker pull` + `docker save` LiteLLM 镜像，再在目标机
> `docker load`。LiteLLM 的 env 说明与运维命令见 `/opt/application/litellm/` 下的 compose 与配置。

### 方式 B · 原地运行 + systemd（无 Docker 时备选）

按依赖顺序：**LiteLLM → 规则 → 后端 → 前端**。

#### 0. 目标机依赖

| 组件 | 版本 | 说明 |
| --- | --- | --- |
| Python | 3.12+ | 系统包或 pyenv |
| `uv` | 最新 | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Node.js | 18+ | 构建前端 + SDK 自带 CLI 运行时（无需单独装 claude-code） |
| `poppler-utils` | 可选 | 仅 `init-rules` 解析 PDF 时需要 |

#### 1. 拉代码

```bash
git clone <your-remote> /opt/enterprise-agent-platform
cd /opt/enterprise-agent-platform
uv sync
```

#### 2. 起 LiteLLM（模型骨干，下游都依赖它）

LiteLLM 由运维独立部署管理（仓库不含其配置）。自备 `litellm_config.yaml`（`claude-*` → Qwen 映射）：

```bash
pip install "litellm[proxy]==<安全版本>"      # ⚠️ 避开被投毒的 1.82.7 / 1.82.8
#   准备 QWEN_API_BASE / QWEN_API_KEY / LITELLM_MASTER_KEY 等环境变量
litellm --config <你的 litellm_config.yaml> --port 4000
curl http://127.0.0.1:4000/health             # 应有响应
```

#### 3. 铺规则（关键：`knowledge/` 被 gitignore，不随仓库走）

审核读 `knowledge/expense/*.rules.json`，缺失会一律 `manual_review(rule_gap)`。二选一：

```bash
# A. 从现有机器同步 knowledge/（含 expense/*.rules.json 与 memory/）到同路径
# B. 现场初始化：制度源放 knowledge/external/，逐个生成
uv run python -m server.cli init-rules knowledge/external/制度.pdf expense
uv run python -m server.cli validate-assets   # status 应为 ok
```

#### 4. 起后端

填好 `.env`（见“配置”，`MODEL_BASE_URL=http://127.0.0.1:4000`、`MODEL_AUTH_TOKEN` = LiteLLM master key），然后**上线前必过工具调用门槛**：

```bash
uv run python -m server.cli runtime           # status=ok
uv run python -m server.cli ask "用 Read 工具读取 README.md，只回第一行"
ls -t logs/sessions/events/*/*/*/*.jsonl | head -1 | xargs grep -c '"event": "tool_call"'
#   ↑ 必须 ≥1。为 0 说明工具调用没透传，审核会编造结果，禁止上线
uv run app-server start                        # 后台常驻（开发期用；生产见 systemd）
```

#### 5. 构建前端（后端同源托管）

```bash
cd ui && npm install && npm run build && cd .. # 产物 ui/dist
uv run app-server restart                      # 后端默认 SERVE_UI_DIST=true，挂载 ui/dist
# 访问 http://<服务器>:<端口>/ 即前端页面
```

#### 6. systemd 守护（备选方式下的生产守护）

`/etc/systemd/system/litellm.service`：

```ini
[Unit]
Description=LiteLLM proxy
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=app
WorkingDirectory=/opt/enterprise-agent-platform
EnvironmentFile=/opt/application/litellm/litellm.env
ExecStart=/usr/local/bin/litellm --config /opt/application/litellm/litellm_config.yaml --port 4000
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
```

`/etc/systemd/system/enterprise-agent.service`：

```ini
[Unit]
Description=Enterprise Agent Platform
After=litellm.service
Requires=litellm.service

[Service]
Type=simple
User=app
WorkingDirectory=/opt/enterprise-agent-platform
EnvironmentFile=/opt/enterprise-agent-platform/.env
ExecStart=/usr/local/bin/uv run python -m uvicorn server.api:app --host ${APP_SERVER_HOST} --port ${APP_SERVER_PORT} --no-server-header
Restart=on-failure
RestartSec=5s
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now litellm enterprise-agent
journalctl -u enterprise-agent -f
```

> systemd 接管后由它直接拉起 uvicorn，不再走 `app-server` 后台管理；进程日志走 `journalctl`，状态用 `systemctl status` + `curl /health`（不再写 `logs/runtime/app-server/`）。

#### 7. 反向代理与验收

- nginx / Caddy 在前面挂 TLS + rate-limit，转发到后端端口；LiteLLM 只绑 `127.0.0.1`，不对外。
- 验收顺序：`LiteLLM /health` → `cli runtime` ok → **tool_call 探针 ≥1** → 前端首页 → 提交一单 → 任务 `completed` 且结果含真实 `policy_refs`/`evidence_chain`。

> 仅适合常驻实例（VM / 物理机 / systemd），不适合 Serverless：SDK 会拉起 CLI 子进程、单次审核可达数分钟、依赖本地 `.claude`/`knowledge`/`data`/`logs`。

---

## 命令

### 业务 CLI（`uv run python -m server.cli <cmd>`）

| 命令 | 用途 |
| --- | --- |
| `runtime` | 输出脱敏后的运行时配置自检 |
| `ask "<prompt>"` | 单轮 prompt |
| `audit <path>` / `audit-json <path>` | 对文件/目录触发审核（后者出结构化 JSON） |
| `init-rules <source> <domain>` | 从制度源初始化规则 |
| `validate-assets` | 校验 `knowledge/` 规则与 memory |
| `results` / `result-detail <id>` | 归档结构化结果 |
| `sessions` / `transcript <id>` / `requests` / `conversations` | 会话与请求追溯 |
| `memories` / `memory-detail <id>` | memory 资产 |
| `serve` | 前台启动 HTTP 服务 |

`--help` 查看完整列表。`distill-memory` 仅走 Claude command（`ask "/distill-memory ..."`），不作为 CLI 子命令。

### 服务管理（`uv run app-server <cmd>`）

`start` / `stop` / `restart` / `status` / `logs` / `doctor` / `maintain`。开发期用；生产由 systemd 接管。

---

## HTTP API

鉴权：所有业务接口带 `Authorization: Bearer <tenant-token>`（token 来自 `.env` 的 `TENANT_KEYS`），缺失/格式错/不匹配返回 `401`；`GET /health` 免鉴权。

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `POST` | `/audit/submit` | 提交审核（`directory` 或 `upload` 模式） |
| `GET` | `/audit/tasks/{id}` | 轮询任务状态（`accepted`/`running`/`completed`/`failed`） |
| `GET` | `/audit/tasks/{id}/result` | 拉取最终审核结果 |
| `GET` | `/health` | 健康探活（非 ok 返 `503`） |

异步流程：`submit` 拿 `request_id` → 轮询 `tasks/{id}` 到终态 → `completed` 时取 `result`。前端对接细节见 [`.ai_state/docs/前端审核服务对接文档.md`](.ai_state/docs/前端审核服务对接文档.md)。

错误响应除兼容 `detail` 外带结构化 `error`（`code`/`message`/`correlation_id`，与响应头 `X-Request-ID` 对齐）。

### 提交示例

```bash
# directory 模式（目录须在项目根 data/ 下）
curl -X POST http://127.0.0.1:9999/audit/submit \
  -H "Authorization: Bearer sk-your-token" -H "Content-Type: application/json" \
  -d '{"mode":"directory","directory_path":"data/your-sample"}'

# upload 模式（form_json 任意 JSON 对象，可放发票 OCR；files 0~N 个）
curl -X POST http://127.0.0.1:9999/audit/submit \
  -H "Authorization: Bearer sk-your-token" \
  -F 'mode=upload' \
  -F 'form_json={"case_id":"demo-001","invoice_ocr":{"invoice_no":"012","amount":880}}' \
  -F 'files=@/path/to/attachment.pdf'
```

---

## 排障

```bash
uv run ruff check .                            # lint
curl http://127.0.0.1:<port>/health            # 健康
uv run app-server doctor --require-running     # 运行时诊断
uv run app-server logs --lines 100             # 后台日志（非 systemd 模式）
```

审核“失败/编造”排查：看 `logs/sessions/events/.../*.jsonl`，若 `tool_call` 事件为 0，说明模型网关没透传工具调用（换用 LiteLLM 或确认端点支持 function calling）。

---

## 目录结构

```text
.claude/        Claude commands / agents / hooks / skills / contracts
knowledge/      规则、制度材料、memory 资产（gitignore，需单独铺设）
data/           样例目录与上传落盘（gitignore）
Dockerfile      审核后端+前端运行时镜像（含 SDK 自带 claude CLI，无需 node）
docker-compose.yml / docker-entrypoint.sh / enterprise-agent.env.example   平台编排、入口与 env 模板（LiteLLM 由运维独立管理）
server/         Python 服务外壳、CLI、平台层与 stores
ui/             React 前端（npm run build → ui/dist）
logs/           请求/结果/会话/runtime/review-delta 运行时归档（gitignore）
```

> 结构化输出由 SDK `output_format` + JSON Schema 强制约束；业务判断放在 `.claude/` 与 `knowledge/`，Python 不承载业务语义。
