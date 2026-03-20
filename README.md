# 企业智能审核平台

当前仓库已按 `docs/` 中的设计文档重新初始化，并从“纯目录骨架”推进到“最小可运行链路”阶段。

现在已经补上了一条最小可运行的本地 HTTP 服务链路，以及一条 CLI-only 的规则初始化链路：

- `server/api.py`：FastAPI 入口，提供 `/health` 和 `/chat`
- `server/config.py`：统一从 `.env` / 环境变量读取运行配置
- `server/core.py`：统一执行入口，供 API 和后续 CLI 复用
- `server/model_client.py`：直连 OpenAI 兼容接口的通用上游模型客户端
- `server/memory_writer.py`：把业务运行中的可复用判断沉淀到 `knowledge/memory/`
- `server/logging_config.py`：统一日志配置，支持 `DEBUG / INFO / WARNING / ERROR`
- `server/cli.py` + `server/rule_init.py`：CLI-only 的 `/init` 规则初始化骨架

## 当前状态

- `docs/` 是当前唯一完整的信息源，保留架构摘要、费控闭环设计、实施路线、维护规则和基础留档。
- 仓库已重新建立基础配置与精简目录结构，方便后续按文档逐步实现。
- `.claude/` 已补齐项目级非业务最小集，包括 `CLAUDE.md`、`settings.json` 和基础 commands 骨架。
- `knowledge/memory/` 已建立按年/月/日拆分的业务运行记忆目录，供 Claude 在业务运行中沉淀案例、判断和例外处理。
- 业务规则、agent prompt 和 skills 细节仍待逐步落地；本地测试用服务与基础日志能力已可用。

## 当前已初始化内容

- Python/uv 基础配置：`pyproject.toml`、`.python-version`、`.env.example`、`.gitignore`
- 目录骨架：`.claude/`、`knowledge/`、`data/`、`server/`、`logs/`、`tests/`
- `.claude/` 项目级最小集：`CLAUDE.md`、`settings.json`、`commands/` 下的非业务命令说明
- `knowledge/memory/` 业务运行记忆目录：按 `YYYY/MM/YYYY-MM-DD.md` 存放每日业务沉淀
- 协作状态模板：`.ai_state/`，包含 design、plan、status、quality 等工作区文件
- 最小结构测试：校验根目录配置、核心目录、文档导航和 `.claude/` 骨架约束

## 目录说明

- `data/`：后续放本地样例输入和联调数据。现在只保留最小骨架，不预建过多细分内容。
- `knowledge/memory/`：业务运行记忆，统一按 `knowledge/memory/YYYY/MM/YYYY-MM-DD.md` 存放；这里记录的是 Claude 在业务运行中沉淀的案例与判断，不是开发日志，`/init` 会优先读取这里的 Markdown 沉淀。
- `output/`：原本用于运行产物输出；当前还没开始实现运行链路，因此先不保留。
- `scripts/`：原本用于 hooks 和辅助脚本；等真正实现 hook 时再补更合适。
- `logs/service.log`：本地服务日志文件，默认同时输出到控制台和日志文件。

## 本地启动

### 1. 安装依赖

推荐：

```bash
uv sync --dev
```

如果你已经有可用环境，也可以直接确保 `fastapi`、`uvicorn`、`pytest` 等依赖可用。

### 2. 准备环境变量

本地模型网关可参考 `.env` / `.env.example`：

```bash
MODEL_BASE_URL=http://your-model-gateway.example.com
# MODEL_API_KEY=your-model-api-key
MODEL_NAME=your-model-name
APP_LOG_LEVEL=INFO
APP_LOG_FILE=logs/service.log
APP_MEMORY_ROOT=knowledge/memory
SLOW_REQUEST_THRESHOLD_SECONDS=10
UPSTREAM_TIMEOUT_SECONDS=60
```

说明：

- 当前配置优先读取进程环境变量；如果当前工作目录存在 `.env`，也会自动加载，不需要把配置写死在代码里。
- 模型地址、模型名和鉴权信息都应放在配置文件里，不要写死在代码中。
- 无鉴权网关时，不要把 `MODEL_API_KEY` 设成空字符串，直接整行省略或注释掉。
- 当前实现优先读取 `MODEL_*`，同时兼容旧的 `OPENAI_*`、`ANTHROPIC_*` 和 `AGENT_MODEL` 变量名，方便平滑迁移。
- `APP_LOG_LEVEL` 支持 `DEBUG`、`INFO`、`WARNING`、`ERROR`。
- `APP_MEMORY_ROOT` 控制业务运行记忆落盘目录，默认建议使用 `knowledge/memory`。
- `SLOW_REQUEST_THRESHOLD_SECONDS` 用来把慢请求打成 `WARNING`。
- `UPSTREAM_TIMEOUT_SECONDS` 控制单次上游调用的超时时间；如果你的模型首 token 比较慢，可以适当调大。

### 3. 启动服务

推荐前台启动，最容易观察日志，也最容易停止：

```bash
python3 -m uvicorn server.api:app --host 127.0.0.1 --port 8011 --env-file .env --reload
```

如果希望局域网内其他机器访问，把 `127.0.0.1` 改成 `0.0.0.0`。

如果你不需要热重载，可以去掉 `--reload`，进程会更简单：

```bash
python3 -m uvicorn server.api:app --host 127.0.0.1 --port 8011 --env-file .env
```

### 4. 停止服务

如果服务就是在你当前终端前台跑的，直接按：

```bash
Ctrl + C
```

如果你已经关了原终端，或者再次启动时提示端口占用，先查占用进程：

```bash
lsof -nP -iTCP:8011 -sTCP:LISTEN
```

拿到 PID 后正常停止：

```bash
kill <PID>
```

如果进程没有退出，再强制停止：

```bash
kill -9 <PID>
```

也可以直接按端口杀掉：

```bash
PID=$(lsof -ti tcp:8011); [ -n "$PID" ] && kill $PID
```

强制杀掉：

```bash
PID=$(lsof -ti tcp:8011); [ -n "$PID" ] && kill -9 $PID
```

停止后，建议确认端口已经释放：

```bash
lsof -nP -iTCP:8011 -sTCP:LISTEN
```

如果没有输出，就说明端口已经释放，可以重新启动。

### 5. 自己测试

- Swagger UI：`http://127.0.0.1:8011/docs`
- 健康检查：

```bash
curl http://127.0.0.1:8011/health
```

- 聊天测试：

```bash
curl -X POST http://127.0.0.1:8011/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"请用一句话回复：服务联通测试成功"}'
```

### 6. 端口占用排查

如果重启时看到 `Address already in use`，通常是上一次的 `uvicorn` 进程还没完全退出。

推荐排查顺序：

1. 先执行 `lsof -nP -iTCP:8011 -sTCP:LISTEN`
2. 如果查到 PID，先执行 `kill <PID>`
3. 再次执行 `lsof -nP -iTCP:8011 -sTCP:LISTEN` 确认端口已释放
4. 端口仍未释放时，再执行 `kill -9 <PID>`

如果你临时不想处理旧进程，也可以直接换端口启动，例如：

```bash
python3 -m uvicorn server.api:app --host 127.0.0.1 --port 8012 --env-file .env --reload
```

## 日志监控

默认日志文件：

```bash
logs/service.log
```

日志级别语义：

- `DEBUG`：请求进入、上游请求发起、调试细节
- `INFO`：服务启动、正常请求完成、正常上游响应
- `WARNING`：无鉴权模式启动提醒、慢上游响应、4xx 请求
- `ERROR`：上游调用失败、5xx 请求、响应解析失败

常用查看方式：

```bash
tail -f logs/service.log
```

```bash
grep " DEBUG " logs/service.log
grep " INFO " logs/service.log
grep " WARNING " logs/service.log
grep " ERROR " logs/service.log
```

如果你想把调试信息打全，启动前把 `.env` 里的 `APP_LOG_LEVEL=INFO` 改成 `APP_LOG_LEVEL=DEBUG`。

## 规则初始化

`/init` 只允许通过 CLI 运行，不通过 HTTP `serve` 暴露。

推荐命令：

```bash
python3 -m server.cli init
```

如果你已经安装了项目脚本，也可以用：

```bash
agent-cli init
```

执行行为：

- 先扫描 `knowledge/external/` 下的制度文件
- 读取 `docs/` 和 `knowledge/memory/` 中已有的业务运行记忆，生成初始化报告
- 运行前会先做交互确认
- 生成或补齐 `knowledge/_schema/rule.schema.json`
- 生成或补齐 `knowledge/expense/*.rules.json`
- 写入 `knowledge/expense/init-manifest.json` 和 `knowledge/expense/init-report.md`

当前边界：

- `.txt` / `.md` 制度文件会做低置信度占位规则提取，方便后续人工修订
- `.pdf` / `.docx` / 图片类文件会明确提示需要 OCR/向量化能力确认
- `/init` 会优先读取 `knowledge/memory/` 下的业务运行记忆，同时兼容旧的 `.cunzhi-memory/`
- `/init` 不会通过 `server/api.py` 暴露；HTTP 调用 `/init` 会返回 `404`

## 当前底座

- `server/config.py`：统一读取 `.env` / 环境变量，集中管理模型、日志和 memory 路径
- `server/core.py`：统一的执行包络，当前 `api` 已走这层，后续 CLI/结构化审核也会复用
- `server/memory_writer.py`：提供业务运行记忆追加能力，但当前不会把普通 `/chat` 自动写成业务记忆

## 文档导航

| 文档 | 用途 |
| --- | --- |
| [docs/architecture-summary.md](docs/architecture-summary.md) | 快速理解整体架构与优先业务 |
| [docs/expense-control-design.md](docs/expense-control-design.md) | 费控闭环业务设计与后续实现依据 |
| [docs/bootstrap-roadmap.md](docs/bootstrap-roadmap.md) | 分阶段实施路线 |
| [docs/doc-maintenance.md](docs/doc-maintenance.md) | 文档分工与更新规则 |
| [docs/enterprise-agent-dev-guide.md](docs/enterprise-agent-dev-guide.md) | 基础留档与完整背景 |

## 建议阅读顺序

1. [docs/architecture-summary.md](docs/architecture-summary.md)
2. [docs/expense-control-design.md](docs/expense-control-design.md)
3. [docs/bootstrap-roadmap.md](docs/bootstrap-roadmap.md)
4. [docs/doc-maintenance.md](docs/doc-maintenance.md)
5. [docs/enterprise-agent-dev-guide.md](docs/enterprise-agent-dev-guide.md)
