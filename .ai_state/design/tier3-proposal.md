# Tier 3 Proposal

## 3.1 Session 存储迁移到 SQLite

当前 `server/stores/session_store.py` 采用按月 JSONL 分片写入，优点是实现简单、审计友好、迁移成本低；缺点是查询路径需要全量扫描分片，随着租户、会话数和恢复链路增长，`resolve_latest_session_id()`、`/sessions`、`/conversations` 的延迟会越来越依赖磁盘吞吐。建议 Tier 3 采用“JSONL 继续作为 append-only 审计源，SQLite 作为查询索引”的双写方案，而不是直接替换掉原文件流。这样做的核心原因是：日志链路已经被外部脚本和人工排障依赖，直接移除 JSONL 风险过高；而 SQLite 更适合做按租户、按会话、按会话时间的筛选与聚合。

建议新增 `server/stores/session_store_sqlite.py`，实现与当前 `SessionStore` 等价的协议能力，并在内部维护以下表：

```sql
CREATE TABLE sessions (
  request_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  conversation_id TEXT NOT NULL,
  claude_session_id TEXT,
  resume_session_id TEXT,
  fork_from_session_id TEXT,
  schema_name TEXT,
  request_mode TEXT NOT NULL,
  prompt_preview TEXT NOT NULL,
  log_file TEXT NOT NULL,
  result_file TEXT,
  status TEXT NOT NULL,
  result_subtype TEXT,
  cost_usd REAL NOT NULL DEFAULT 0,
  started_at TEXT NOT NULL,
  finished_at TEXT
);

CREATE INDEX idx_sessions_tenant_started ON sessions (tenant_id, started_at DESC);
CREATE INDEX idx_sessions_conversation ON sessions (tenant_id, conversation_id, started_at DESC);
CREATE INDEX idx_sessions_claude_session ON sessions (tenant_id, claude_session_id);
```

这里 `request_id` 继续保持请求级唯一键，`tenant_id + conversation_id` 用于恢复最近会话，`tenant_id + claude_session_id` 用于详情页访问控制。为了支持 `/conversations` 聚合，还可以在查询层直接 `GROUP BY conversation_id`，避免 Python 端聚合所有分片。迁移脚本建议命名为 `scripts/migrate_sessions_to_sqlite.py`，采用“扫描 JSONL 分片 -> 幂等写入 SQLite -> 记录迁移游标”的方式实现。脚本应支持重复运行：如果 `request_id` 已存在则跳过；如果 `log_file` 或 `result_file` 发生变化则打印 warning 并保留第一次写入版本。回退方案要非常直接：保留现有 JSONL 写路径，只关闭 SQLite 读路径开关，服务即可回落到文件扫描模式，不需要回滚数据。

实施顺序建议是三步。第一步，抽象当前 session store 的创建入口，让 JSONL/SQLite 可以通过配置切换。第二步，上线双写但仍使用 JSONL 读路径，验证 SQLite 索引完整性。第三步，灰度把 `/sessions`、`/conversations`、`resolve_latest_session_id()` 切到 SQLite，持续保留 JSONL 作为审计源和回退源。这样即使 SQLite 文件损坏，也不会丢失原始事件与结果链路。

## 3.2 `/audit/submit` 租户级限流

当前 `/audit/submit` 已经具备租户鉴权和异步任务持久化，但没有并发和速率保护。单个租户如果在短时间内反复提交目录审核或批量上传，虽然不会突破 tenant isolation，却会占满 Claude 调用预算、任务存储和本地 IO。Tier 3 建议实现“单进程内存令牌桶 + 租户粒度锁”的轻量限流，优先解决单节点部署下的保护问题，而不是一开始就引入 Redis 之类的分布式协调组件。

推荐的数据结构是：

```python
@dataclass(slots=True)
class TenantRateBucket:
    tokens: float
    last_refill_ts: float
    lock: asyncio.Lock
```

服务启动时创建一个 `dict[str, TenantRateBucket]`，key 为 tenant，默认容量和补充速率来自配置项 `AUDIT_RATE_LIMIT_PER_MIN`，默认值可设为 `10`。每次命中 `/audit/submit` 时，先获取该租户的 `lock`，根据当前时间做令牌补充，再尝试扣减 1 个令牌。若扣减失败，则直接返回 `429 Too Many Requests`，并设置 `Retry-After` 响应头。这样可以避免同一租户并发请求同时读写桶状态导致的超发。

这个方案的优点是实现简单、和当前 `FastAPI + asyncio` 架构自然匹配、对本地单机部署足够有效。缺点也要提前讲清楚：一旦以后服务横向扩容到多进程或多副本，内存桶不会天然共享，这时需要把桶状态迁移到 Redis 或数据库；因此实现时最好把限流器入口抽成 `RateLimiterProtocol`，先提供 `InMemoryTenantRateLimiter`，未来再补 `RedisTenantRateLimiter`。此外，建议把限流只挂在 `/audit/submit`，而不是 `/chat`，因为两类流量成本和业务重要性不同；过早统一限流会把调试调用和生产审核混在一起。

## 3.3 结构化输出 semantic 规则外置

现在 `server/core.py` 的 `validate_structured_output_semantics()` 里直接硬编码了 `audit` 和 `init-rules` 两类业务规则。这个实现短期很有效，但规则一旦继续增加，Python 代码会逐渐变成“半 DSL、半 if/else”的状态，维护者既要理解 schema，又要理解业务语义，还得在代码里追条件组合。Tier 3 建议把这部分抽成“声明式规则文件 + 通用执行器”的结构，规则文件放到 `server/rules/validation_rules.json`，执行器放到 `server/rules/validator.py`。

DSL 可以先做最小闭环，不追求通用到任意布尔表达式，先满足当前两个业务域即可。例如：

```json
{
  "common/audit-result.schema.json": [
    {
      "when": {"field": "verdict", "equals": "approved"},
      "require": [
        {"field": "result", "equals": true},
        {"field": "conclusion", "equals": "合规"},
        {"field": "explanation", "non_empty": true}
      ]
    },
    {
      "when": {"field": "verdict", "equals": "manual_review"},
      "require": [
        {"field": "result", "equals": false},
        {"field": "conclusion", "equals": "待人工复核"}
      ]
    }
  ]
}
```

执行器接口建议为 `apply_rules(payload: StructuredJSON, rules: list[dict[str, Any]]) -> list[Violation]`。其中 `Violation` 可以是 dataclass，字段包括 `rule_index`、`field`、`reason`、`expected`、`actual`。`validate_structured_output_semantics()` 则只负责装载 schema 对应规则、调用执行器，并把 violations 格式化成现有 `JSONContractError`。这样一来，新增业务规则时，优先改 JSON 规则文件；只有当 DSL 不够表达时，才扩展执行器能力。

回退策略也很清晰：保留当前 Python 版本校验函数一段时间，先做双跑比对。服务在开发或诊断模式下可以同时执行“旧逻辑 + 新规则引擎”，如果两边结论不一致则打 warning 日志，但仍以旧逻辑为准。等规则文件经过一轮真实审核样本验证后，再切换默认执行路径。这样可以避免把语义校验从“代码可读”直接替换成“配置可写”后，线上才发现 DSL 表达力不够。
