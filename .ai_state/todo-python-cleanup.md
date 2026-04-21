# Python 层调整 — TODO Checklist

> 完整设计见 `.ai_state/handoff.md`。本文件是可勾选的核对清单，每一项对应具体文件 + 行号 + 完成判据。
>
> 执行顺序：**1.x → 2.5 → 2.4 → 2.2 → 2.1 → 2.3 → 3.x 设计文档**（2.5/2.4 先做是因为 2.2 的 logging 需要它们定义的字段）。
>
> 每完成一项：① 打勾 ② 独立 commit（前缀 `[tierX.Y]`）③ 跑 `pytest` + `ruff check server/ tests/`

---

## Tier 1 — Immediate

### 1.1 补齐 store 类型注解
- [ ] `server/stores/session_store.py:98` — `def __init__(self, shard_dir) -> None` → `def __init__(self, shard_dir: Path) -> None`
- [ ] `server/stores/request_store.py:71` — 同上
- [ ] `server/stores/result_store.py:79` — `def __init__(self, shard_dir, archive_root)` → 两个参数都加 `: Path`
- [ ] `server/stores/audit_task_store.py` — 若有 `__init__` 同样处理；若是模块函数则检查函数签名
- [ ] `server/stores/runtime_store.py` — 同上扫描一次
- [ ] `load_records()` 等公开方法如果返回 `list[dict[str, Any]]`，改成已有的 `list[SessionRecord]` / `list[ResultRecord]`（stores 里已有 dataclass）
- **判据**：`mypy server/stores/` 或 `pyright server/stores/` 无 Missing type annotation 告警

### 1.2 租户默认密钥显式化
- [ ] `server/platform/config.py:218` — `load_tenant_keys()` 中若 `raw == '{"default":"sk-default"}'`（即使用默认值），加一次性启动告警：`logging.warning("TENANT_KEYS env var not set, using insecure default — set TENANT_KEYS=... before production")`
- [ ] `server/platform/diagnostics.py` — runtime snapshot 增加字段 `tenant_keys_are_default: bool`（不暴露密钥本身）
- [ ] 新增测试 `tests/test_tenant_key_defaults.py`：断言默认时 diagnostics 字段为 `True`，设置 env 后为 `False`
- **判据**：启动日志能看到告警行；`/ready` 响应 JSON 含新字段

### 1.3 Store 容量保护
- [ ] `server/platform/config.py` 的 `AppSettings` 新增：
  - `session_store_max_shard_bytes: int`（默认 `50 * 1024 * 1024`）
  - `session_store_max_shards: int`（默认 `24`）
  - 对应从 env `SESSION_STORE_MAX_SHARD_BYTES` / `SESSION_STORE_MAX_SHARDS` 读取
- [ ] `server/stores/session_store.py` append 路径（`append_record` / `_append_to_shard`）：写入后检查分片大小和总分片数，超出 `logging.warning("session shard over limit", extra={...})`，**不阻断写入**
- [ ] `request_store` / `result_store` 同样套用（配置项复用或各自独立，看你偏好）
- **判据**：单元测试模拟大文件，断言告警被触发、写入不中断

---

## Tier 2 — Short-term

### 2.5 Logging + correlation id 细节约定（优先，后面都依赖它）
- [ ] 新建 `server/platform/logging_setup.py`：
  - `configure_logging(level: str, format: Literal["json","kv"])` 初始化 root logger
  - JSON formatter 输出字段：`timestamp / level / logger / message / request_id / tenant / session_id`
  - `DEV=true` 或 `LOG_FORMAT=kv` 时切 kv 格式
  - 通过 `contextvars.ContextVar[str]` 暴露 `current_request_id()` / `current_tenant()` / `current_session_id()`
- [ ] 在 `server/api.py` 启动处加 FastAPI middleware：
  - 读 header `X-Request-ID`，有则沿用，无则 `uuid.uuid4().hex`
  - 写入 ContextVar
  - 响应 header 回写 `X-Request-ID: <同一个值>`
- [ ] `verify_tenant()` 成功后同时写入 `tenant` ContextVar
- [ ] 约定：每条 JSONL 写入必须带 `request_id / tenant / session_id`（若相关）
- **判据**：`curl -H "X-Request-ID: abc123" ...` 后响应 header 同值，且该 request 产生的所有日志行都含 `abc123`

### 2.4 租户隔离硬化
- [ ] 把所有 stores 公开方法的 `tenant: str | None = None` 改为 `tenant: str`（**必填，不给默认值**）：
  - `session_store.py`: `load_records` / `get_record_by_request_id` / `get_record_by_session_id` / `resolve_latest_session_id` / `list_logged_sessions` / `list_conversation_summaries` / `list_known_session_ids`
  - `audit_task_store.py`: `get_audit_task` / `list_audit_tasks`
  - `request_store.py`、`result_store.py` 同类方法
- [ ] 如有真正需要跨租户的内部操作（比如 maintenance），新开 `_admin_load_all_records()`（下划线前缀）并加注释：`# DANGEROUS: bypasses tenant isolation — admin-only`
- [ ] `SessionLogger._write()` 的 record dict 里强制注入 `tenant` 字段（从 ContextVar 读）
- [ ] 新建 `tests/test_tenant_isolation.py`：
  - fixture 启两个 tenant key（tenantA=sk-A，tenantB=sk-B）
  - 用 A 跑一次 `/chat` + 一次 `/audit/submit`，拿到 `request_id_A` / `session_id_A`
  - 用 B 调用：
    - `GET /sessions` → 不含 A 的 session
    - `GET /conversations` → 不含 A 的 conversation
    - `GET /requests` → 不含 A 的 request
    - `GET /results` → 不含 A 的 result
    - `GET /requests/{request_id_A}` → 404
    - `GET /results/{request_id_A}` → 404
    - `GET /audit/tasks/{request_id_A}` → 404
    - `GET /audit/tasks/{request_id_A}/result` → 404
    - `GET /sessions/{session_id_A}/messages` → 403 或 404
  - 所有断言必须**严格**：B 不能看到 A 的任何 id 泄露
- **判据**：新测试全部通过；原有测试无回归

### 2.2 改造现有异常与 session 事件流
- [ ] `server/core.py:345` `except Exception as exc:` → `logger.exception("claude_bridge_failed", extra={"session_id": ..., "request_id": ...})` 后再按原逻辑 raise
- [ ] `server/api.py:486` 同类处理
- [ ] `SessionLogger._write()` 在 session_start / session_end 事件处，同步 `logger.info("session_event", extra={"event": "...", ...})`（保留 JSONL 写盘不变）
- [ ] `server/app_server.py` 子进程 stdout/stderr — 确认子进程启动时 `PYTHONUNBUFFERED=1` 且入口调用 `configure_logging()`，不要让业务代码里残留 `print()`
- **判据**：故意触发一次 Claude 调用异常，查 logs 能同时看到 JSON 格式的 error log（含 request_id）和 JSONL 里的 `bridge_error` 事件

### 2.1 Prompt 外置
- [ ] 新建目录 `server/prompts/`
- [ ] 新建 `server/prompts/audit.md`，内容即 `command_adapter.py:19-34` 的 prompt 文本，`{path}` 作占位符替换原 `normalized_path`
- [ ] 新建 `server/prompts/init-rules.md` — 扫 `command_adapter.py` 看有没有 init-rules 相关硬编码（如没有，查 `api.py` 的 `/init-rules` 端点上下文再决定）
- [ ] `server/command_adapter.py` 新增：
  ```python
  def load_prompt(name: str, **kwargs: str) -> str:
      path = PROMPTS_DIR / f"{name}.md"
      template = path.read_text(encoding="utf-8")
      return template.format_map(kwargs)  # 占位符缺失抛 KeyError
  ```
- [ ] `build_audit_prompt(path)` 改为 `load_prompt("audit", path=path)`
- [ ] 启动时调 `validate_prompts()` — 遍历 prompts 目录，检查必需模板存在，占位符与调用点匹配，缺则 `RuntimeError`
- [ ] 新建 `tests/test_command_adapter.py` 覆盖：
  - (a) 正常渲染：`load_prompt("audit", path="/tmp/x")` 返回含 `/tmp/x` 的字符串
  - (b) 占位符缺失：`load_prompt("audit")` → `KeyError`
  - (c) 模板文件缺失：`load_prompt("nonexistent")` → `FileNotFoundError` 或 `RuntimeError`
- **判据**：`/audit` 端点行为字节级一致（可用现有测试 `test_audit_submit_attachments.py` 回归）

### 2.3 Session 集成测试
- [ ] 新建 `tests/test_session_lifecycle.py`：
  - fixture：临时目录覆盖 `PROJECT_ROOT / logs/` 和 `data/submissions/`，mock `claude_agent_sdk.query()` 返回固定事件序列（`SystemMessage(session_id="s1") → AssistantMessage(text="ok") → ResultMessage(cost=0.01)`）
  - 测试 1：`test_resume_session_id` — 先 `/chat` 拿 session_id，再用 `resume_session_id=<该id>` 继续，断言第二次 query 调用时 `options.resume` 被设置
  - 测试 2：`test_fork_session_id` — 类似，断言 `options.fork_session` 被设置
  - 测试 3：`test_continue_recent` — 带 `conversation_id` 连续两次不传 session_id 但 `continue_recent=True`，第二次应自动拿到第一次的 session_id
- **判据**：3 个测试全部通过；`pytest -k session_lifecycle` 独立跑也通过

---

## Tier 3 — 只产出设计文档（`docs/design/tier3-proposal.md`）

- [ ] 新建目录 `docs/design/`
- [ ] 写 `tier3-proposal.md`，三章：
  - **3.1 Session 存储迁移 SQLite**：表结构 (`sessions / conversations / results`)，索引 (`idx_tenant_created`, `idx_conversation`)，迁移脚本步骤，回退策略（保留 JSONL 作为 source of truth）
  - **3.2 `/audit/submit` 租户级限流**：令牌桶实现方案（每 tenant `asyncio.Lock` + 计数器 + 时间戳），配置项 `AUDIT_RATE_LIMIT_PER_MIN`（默认 10），超限返回 429 + `Retry-After`
  - **3.3 Semantic 规则外置**：`server/rules/validation_rules.json` DSL 草案（`when / require / forbid` 三段式），执行器接口 `apply_rules(payload, rules) -> list[Violation]`
- **判据**：每章 ≥ 300 字；有表/示例代码片段；用户可直接拍板进入实施

---

## 最终验收

- [ ] Tier 1 / Tier 2 所有打勾项完成
- [ ] `pytest` 全绿（新增 + 原有）
- [ ] `ruff check server/ tests/` 无新增告警
- [ ] `docs/design/tier3-proposal.md` 写完
- [ ] `.ai_state/reviews/sprint-python-cleanup.md` 自审报告（改了什么、为什么、遗留/风险、需要人工决策项）
- [ ] 每个 Tier 子项独立 commit，`git log --oneline` 能看到 `[tier1.1]` / `[tier2.5]` ... 序列

---

## 执行约束（硬红线）

1. 不改 `.claude/` / `knowledge/` / `logs/` / `data/`
2. 不改 HTTP API 契约（入参/出参/status code 保持兼容）
3. 不改 JSONL 目录层级（只能扩展字段）
4. TDD：Tier 2 先写测试再写实现
5. 不 `git push`（只本地 commit）
