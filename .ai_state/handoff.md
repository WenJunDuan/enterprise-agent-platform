# Python 层调整计划 — Codex 实施 Handoff

**背景**：Claude Code 已完成 Python 层代码审查（server/ 目录），识别出性能、可观测性、规则耦合三大短板。本 handoff 将调整工作交给 Codex 实施。

**项目根**：`/Users/mi_manchi/workspace/enterprise-agent-platform`
**目标目录**：`server/`（不触碰 `.claude/`、`knowledge/`、`logs/`、`data/`）

---

## Tier 1 — Immediate（低风险，优先实施）

### 1.1 补齐 store 类型注解
- 文件：`server/stores/session_store.py:98`（`__init__(self, shard_dir)` 缺 `: Path`）
- 同类问题扫描：`stores/request_store.py`、`stores/result_store.py`、`stores/audit_task_store.py`、`stores/runtime_store.py`
- 要求：`__init__` 参数全部加类型注解；公开方法返回类型从 `list[dict[str, Any]]` 收紧到明确 dataclass 列表（若已存在）。

### 1.2 租户默认密钥显式化
- 文件：`server/platform/config.py:218` — `TENANT_KEYS` 默认 `{"default": "sk-default"}`
- 改造：
  - 启动时若检测到默认密钥在使用，调用 `logging.warning()` 输出**醒目告警**（包含修复提示）。
  - `diagnostics.py` 的 runtime snapshot 增加 `tenant_keys_are_default: bool` 字段（不输出密钥本身）。

### 1.3 Store 容量保护
- 新增 `server/platform/config.py` 配置项：
  - `SESSION_STORE_MAX_SHARD_BYTES`（默认 50 MiB）
  - `SESSION_STORE_MAX_SHARDS`（默认 24 = 2 年）
- 在 `stores/session_store.py` 的 append 路径做超限检查，超出输出 `logging.warning`（不阻断写入，避免破坏审计链）。
- 同样配置应用到 `request_store`、`result_store`。

---

## Tier 2 — Short-term（中等风险，需测试）

### 2.1 Prompt 外置到模板文件
- 现状：`server/command_adapter.py:20-34` 硬编码中文 audit prompt；init-rules prompt 也在该文件。
- 目标：
  - 新建目录 `server/prompts/`（不要放 `.claude/` 下，那是 agent 定义）
  - 文件：`server/prompts/audit.md`、`server/prompts/init-rules.md`（Markdown，支持 `{variable}` 占位符）
  - `command_adapter.py` 重构为 `load_prompt(name: str, **kwargs) -> str`，内部读文件 + `str.format_map`
  - 模板加载支持启动时校验（缺文件或占位符缺失则 `RuntimeError`）
- 测试：`tests/test_command_adapter.py` 覆盖（a）正常渲染、（b）占位符缺失、（c）模板文件缺失。

### 2.2 引入标准 logging + correlation id
- 新建 `server/platform/logging_setup.py`：
  - `configure_logging(level: str, json_format: bool)` — 初始化 root logger
  - JSON 格式器：输出 `timestamp / level / logger / message / request_id / tenant_id / session_id`
  - 通过 `contextvars.ContextVar` 传递 correlation id
- FastAPI 中间件（`server/api.py` 启动处）：
  - 每个请求注入 `request_id`（若 header 无则生成 UUID），写入 ContextVar
  - 响应 header 回写 `X-Request-ID`
- 改造点：
  - `server/core.py:345` 的 `except Exception as exc:` → `logger.exception("claude_bridge_failed", extra={"session_id": ..., "request_id": ...})`
  - `server/api.py:486` 同类处理
  - `SessionLogger._write()` 保持 JSONL 输出（事件流），但同时在关键节点 `logger.info` 摘要（便于 grep）
- `app_server.py` 的子进程 stdout/stderr 改为读取 logging 输出（不是 print）。

### 2.4 租户隔离硬化（新增，优先级高）

**背景**：当前 `verify_tenant()` 在 API 入口已校验，stores 也按 `tenant` 过滤；但 `tenant: str | None = None` 的默认值意味着只要内部代码漏传，就会返回**全部租户数据**。这是数据泄漏 footgun。

改造：
- 在所有 store 公开方法里，把 `tenant: str | None = None` 改为 `tenant: str`（必填）。内部如确需跨租户（比如运维脚本），新开 `_load_records_admin()` 等显式命名的函数，并加注释 "DANGEROUS — bypasses tenant isolation"。
- `/sessions/{session_id}/messages` 等详情端点已经用 `_require_session_access()` 做了前置校验，保留。
- 事件 JSONL 的 record 里**补写 `tenant` 字段**（`SessionLogger._write()` 注入），便于将来审计和文件级过滤。
- 新增测试 `tests/test_tenant_isolation.py`：
  - 配置两个租户 key（A / B）
  - 用 A key 创建 session / audit result
  - 用 B key 调用 `/sessions`、`/conversations`、`/requests`、`/results`、`/audit/tasks/{A的request_id}`、`/sessions/{A的session_id}/messages` — **全部应返回空或 404**
  - 不允许 B 能看到 A 的任何字段（包括 session id 列表）

### 2.5 Logging 与 correlation id 细节确认

- 格式：**JSON 默认**，`DEV=true` 或 `LOG_FORMAT=kv` 时切 key=value 人类可读
- Correlation id 来源：**客户端 `X-Request-ID` header 优先**，缺则服务端 UUID4；响应 header 统一回写 `X-Request-ID`
- 事件目录结构：**保持 `logs/sessions/events/YYYY/MM/DD/` 不变**
- 要求：SessionLogger、request_store、result_store、audit_task_store 的每条 JSONL 都必须包含 `request_id`、`tenant`、`session_id`（若相关）三个字段，便于 `rg request_id=xxx logs/` 拉全链路

### 2.3 Session 集成测试
- 新建 `tests/test_session_lifecycle.py`：
  - 测试 `resume_session_id` 流程（创建 → 恢复 → 断言事件接续）
  - 测试 `fork_session_id`（创建 → 分叉 → 两条独立线）
  - 测试 `continue_recent=True` 路径（无 session_id 时拉取最近会话）
- 使用 FastAPI TestClient + 临时目录 fixture（隔离 `logs/`）
- Mock Claude SDK `query()` 返回固定 SystemMessage → AssistantMessage → ResultMessage 流。

---

## Tier 3 — Medium-term（高风险，暂缓执行）

以下 3 项**先不实施**，Codex 仅产出设计文档 `docs/design/tier3-proposal.md`，等用户确认再落地：

### 3.1 Session 存储迁移 SQLite
- 设计要点：
  - `stores/session_store_sqlite.py` 实现现有 `SessionStore` Protocol
  - 表设计：`sessions(id, conversation_id, tenant_id, created_at, …)` + 索引
  - JSONL 保留为 append-only 审计流；SQLite 作为查询索引
  - 迁移脚本 `scripts/migrate_sessions_to_sqlite.py`（可重入）
- Codex 任务：只写 `docs/design/tier3-proposal.md`，给出表结构、迁移步骤、回退方案。

### 3.2 `/audit/submit` 租户级限流
- 设计要点：令牌桶 per-tenant（默认 10 req/min），使用 `asyncio.Lock` + 内存计数器
- Codex 任务：`docs/design/tier3-proposal.md` 中加一节说明方案与配置项。

### 3.3 结构化输出 semantic 规则外置
- 现状：`server/core.py:96-155` 的 `validate_structured_output_semantics()` 硬编码了 audit/init-rules 的字段关系规则
- 设计要点：抽到 `server/rules/validation_rules.json` + `server/rules/validator.py` 通用执行器
- Codex 任务：`docs/design/tier3-proposal.md` 中给出规则 DSL 草案。

---

## 执行约束（Codex 必须遵守）

1. **作用域**：只修改 `server/`、`tests/`、新建 `server/prompts/` 与 `docs/design/`。不动 `.claude/`、`knowledge/`、`logs/`、`data/`。
2. **TDD**：Tier 2 的每个改动先写测试再写实现。
3. **逐项提交**：每个编号（1.1 / 1.2 / 1.3 / 2.1 / 2.2 / 2.3 / 3.*）独立 commit，commit message 前缀 `[tier1.1]` 这样的格式。
4. **测试回归**：每次 commit 前跑 `pytest` 全量，失败则不提交。
5. **不改 API 契约**：所有 HTTP 端点的入参、出参、status code 保持向后兼容。
6. **不删除已有 JSONL 路径结构**：只能扩展字段，不能改目录层级（避免破坏已有日志）。
7. **权限**：Codex 以 full-auto / write 模式运行（允许读写 server/、tests/、docs/、新建 server/prompts/）。

---

## 验收标准

- [ ] Tier 1 全部完成，`pytest` 通过
- [ ] Tier 2 全部完成，新增测试覆盖率 ≥ 80%
- [ ] Tier 3 设计文档 `docs/design/tier3-proposal.md` 产出
- [ ] `ruff check server/ tests/` 无新增告警
- [ ] 每个 commit 的 diff 可独立 review（不要巨型 commit）
- [ ] 最终回一个 summary：改了哪些文件、测试数、已知遗留

完成后在 `.ai_state/reviews/` 追加本次变更的自审记录。
