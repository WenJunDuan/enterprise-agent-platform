# 日志工程化 + 存储态梳理 Design

> Sprint 2026-06-19 · Path: Refactor/Feature · 三线：B 企业日志(实现) · A validate 注册表(实现) · C 合同存储(仅设计)

## Goal

1. 把运行日志按 log4j2 风格工程化：级别分流(INFO+/WARN+) + 文件 appender + 滚动 + 保留。
2. validate 调度器去 if/elif，改注册表（OCP，加 schema 不改分发器）。
3. 为后续合同审计设计持久合同库 + 结构态（本轮不实现）。

## Key Decisions（与用户对齐 2026-06-19）

- **日志**：级别分流 + 滚动，**业务归档(results/sessions/…)留 logs/ 原位不动**，改动集中在
  `logging_setup.py` + `paths.py`。
- **合同存储**：持久合同库 + 结构态（`data/contracts/<id>/`），本轮**只出设计**。
- 已先行清理：`logs/tmp` 23M 陈旧 OCR 测试残渣已删（生产代码内存渲染 PDF，不写盘，不再生）。

## 现状

- `logging_setup.py`：结构化(JSON/KV) + MDC context(request_id/tenant/session) 已有；但**只有
  `StreamHandler(stdout)`**，无文件 appender、无级别分流、无滚动。落盘仅靠 app-server 把
  stdout/stderr 整坨捕获到 `logs/runtime/app-server/`。
- `logs/` 现状是干净的业务归档 taxonomy（service/sessions/results/review-deltas/knowledge +
  各 sqlite 索引 + 按日期分片），但和"运行日志"概念混用。本轮不挪它，只新增运行日志层。

---

## B · 企业日志（log4j2 → Python 映射）

| log4j2 概念 | Python 实现 |
|---|---|
| Appender (Console / RollingFile) | `StreamHandler` / `logging.handlers.RotatingFileHandler` |
| PatternLayout / JSONLayout | 现有 `_KVFormatter` / `_JSONFormatter` |
| ThreadContext (MDC) | 现有 `ContextVar` + `_ContextFilter`（request_id/tenant/session） |
| Logger level / Root | `logging` level + root logger |
| ThresholdFilter (按级别分流) | handler.setLevel(WARNING) → error.log 只收 WARN+ |
| RollingFile + SizeBasedTriggeringPolicy | `RotatingFileHandler(maxBytes, backupCount)` |
| DefaultRolloverStrategy + gz | handler.rotator/namer 自定义 → 备份 gzip 压缩 |
| 声明式 XML 配置 | 参数 + 环境变量驱动（12-factor 等价；可选 dictConfig） |

### 目录 taxonomy（新增运行日志层，业务归档不动）

```
logs/
  app/                    ← 新增：运行日志(operational)
    app.log     INFO+ 全量      RotatingFileHandler, gz 备份
    error.log   WARNING+ 独立    setLevel(WARNING) 分流
  runtime/app-server/     保留：进程级 pid/status/原始 stdout-stderr
  service/ sessions/ results/ review-deltas/ knowledge/   保留：业务归档(原位不动)
```

### `configure_logging` 改造

新增可选参数（环境变量兜底，**现有调用点 api.py:40 不用改**，靠 env 激活）：

```
configure_logging(level, format, *, to_files=None, log_dir=None, max_bytes=None, backup_count=None)
  to_files     LOG_TO_FILES (默认 False — 保证测试不写盘)
  log_dir      默认 paths.APP_LOG_DIR (logs/app)
  max_bytes    LOG_MAX_BYTES (默认 50MB)
  backup_count LOG_BACKUP_COUNT (默认 10)
```

- console appender 始终在（容器 stdout / 开发），格式跟 `format` 参数。
- 文件 appender **始终 JSON**（机器可解析）；`to_files=True` 时挂 app.log(INFO+) + error.log(WARN+)。
- 滚动：size-based + gz 压缩备份（stdlib `rotator`/`namer`）。按天滚动(TimedRotating)留作 toggle，
  本轮先 size+gz（log4j2 最常用的 SizeBasedTriggeringPolicy）。
- `paths.py` 新增 `APP_LOG_DIR = LOGS_ROOT / "app"` + 纳入 `ensure_local_layout()`。
- serve 路径(app_server/cli serve)设 `LOG_TO_FILES=true` 激活；测试默认不写盘。

### 验收
- INFO 记录 → app.log；WARN/ERROR → app.log + error.log；error.log 不含 INFO。
- 文件超 max_bytes 滚动，备份 gz。
- 全量 pytest 绿（含新 test_logging）；现有 stdout 行为不回归。

---

## A · validate 调度器 → 注册表（OCP）

把 `common/contract.py` 里 `validate_structured_output_semantics` 的 `if schema_name==…` 分发，
和 `json_bridge` 里 `if schema_name==DEFAULT: enrich_audit_decision` 的特判，统一成注册表：

```python
# common/contract.py
@dataclass
class SchemaProcessor:
    validate: Callable[[StructuredJSON], None] | None = None   # 违约 raise JSONContractError
    enrich:   Callable[[StructuredJSON], StructuredJSON] | None = None

_SCHEMA_PROCESSORS: dict[str, SchemaProcessor] = {}
def register_schema_processor(schema_name, *, validate=None, enrich=None): ...
def apply_schema_semantics(schema_name, output) -> StructuredJSON:  # validate + enrich, 未注册则原样返回

# 内置平台契约在 contract.py 注册（契约一致性属平台职责）
register_schema_processor(DEFAULT_OUTPUT_SCHEMA_NAME, validate=_validate_audit_result, enrich=enrich_audit_decision)
register_schema_processor(INIT_RULES_REPORT_SCHEMA_NAME, validate=_validate_init_rules_report)
```

- `json_bridge` 两处 `validate(...) + if schema==DEFAULT enrich(...)` → 一句 `apply_schema_semantics(schema, output)`。
  json_bridge 不再知道任何具体 schema 名。
- `validate_structured_output_semantics(schema, output)` 保留为薄包装（查注册表的 validate），
  现有 test_core_pure 直接调它，零改动。
- **价值**：加新 schema = 一次 register（OCP），不再改 if/elif；外部域可从自己模块注册。

### 验收
- test_core_pure 全绿（validate 行为不变）。
- 新增测试：注册新 schema 后 apply_schema_semantics 生效；未注册 schema 原样返回不报错。
- json_bridge 不再出现字面量 schema 名特判。

---

## C · 合同审计存储态（仅设计，待合同审计开工时实现）

合同 ≠ expense 的"上传即弃"：合同是**可长期复引的参考文档**（expense 付款要校验合同条款、
合同付款节点要预测）。故引入**持久合同库**，与 ephemeral 的 `data/submissions/` 分离。

```
data/contracts/<contract_id>/
  source.<ext>        合同原件（PDF/Word，持久保留）
  clauses.json        抽取的条款结构（付款/违约/期限/金额…）
  payment_nodes.json  付款节点子表（节点→金额/时间/条件，供预测付款）
  meta.json           contract_id / 版本 / 状态 / 来源 / 录入时间 / 关联方
```

存储态（lifecycle）：
1. `intake` — 上传走 submissions（ephemeral）。
2. `registered` — 审核/录入成功 → 提升为持久 `data/contracts/<id>/`，落 source + meta。
3. `extracted` — OCR/抽取 → clauses.json + payment_nodes.json。
4. `referenced` — expense/tender 审核交叉引用 contract_id（结论 evidence_chain 回链）。

- 新增 store：`server/stores/contract_store.py`（sqlite 索引 + by-id 目录，对齐现有 result_store 模式）。
- `paths.py` 加 `CONTRACT_ROOT_DIR = PROJECT_ROOT / "data" / "contracts"`。
- 审核结论(logs/results)的 evidence_chain 增加 `contract_ref: {contract_id, clause_id}` 回链能力。
- gitignore：`data/` 已忽略；合同库属运行态数据，不入库（与 submissions 一致）。

> 注：`data/` 当前为空、0 追踪文件、被 gitignore——并无"已提交的初始数据"，需要 seed/样例合同时
> 另行约定（参考 expense 的做法，样例放 data/ 但不入库）。

## 执行顺序

B(日志，独立、价值高) → A(validate 注册表，小而清晰) → C 留设计。每步 design→TDD→独立 commit。
