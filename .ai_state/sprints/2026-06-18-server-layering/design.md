# Server 分层整理 Design

> Sprint 2026-06-18 · Path: Refactor · **仅设计，不改代码**（用户选"先只出方案"）
> 目标：内容增多时让功能域互不影响、不互相直接调用，理顺分层依赖方向。

## Goal

`server/` 是平台的"运行壳"（Python 只负责服务/取输入/提交给 Claude，业务判断在 `.claude/` 侧）。
随着功能域增多（已有 `audit` 审核引擎 + `ocr` 文档识别），要保证：

1. **功能域之间零直接调用**（audit 不 import ocr，反之亦然）。
2. **依赖只向下**（上层用下层，下层不反向吃上层），避免环依赖与门面"毛球"。

本次只产出方案，下一轮再按用户确认范围动手。

## 现状勘察（依赖图）

### 好的部分 ✓

- `audit/` 与 `ocr/` **互不 import** —— 功能域隔离已成立。
- `stores/` 只依赖 `platform/`（持久层接近叶子）。

### 当前依赖（问题边用 ✗ 标）

```
            api.py ──┐ (CMD/app)
              ▲      │
   ✗ lazy import     ▼
            routes/ ───────────────► stores/ ──► platform/
              │  └► ocr/runner          ▲           ▲
              │  └► audit/runner        │           │
              ▼                         │           │
   features: audit/ , ocr/ ────────────┘           │
              │   │                                 │
              ▼   ▼                                 │
            core.py (门面) ◄──── common/command_adapter ✗ (core↔common 环)
              │  └► audit.contract                  │
              ▼                                     │
            common/ ──► stores/ , platform/         │
            json_bridge ──► audit.contract ✗ (通用层吃 audit 域)
                                                    │
            platform/diagnostics ──► core + 5×stores ✗ (地基反向吃上层)
            platform/maintenance ──► stores.audit_task_store ✗
```

### 四处结构债

| # | 问题 | 精确证据 | 危害 |
|---|---|---|---|
| 1 | **platform 反向依赖上层** | `platform/diagnostics.py:9-14` → `core` + 5×`stores.*`；`platform/maintenance.py:27` → `stores.audit_task_store` | 地基（config/paths/logging）本应是叶子，却反向吃 stores/core，分层倒挂 |
| 2 | **通用层 json_bridge 钉死 audit 域** | `common/json_bridge.py:26` import 7 个符号，其中 `enrich_audit_decision` 是 audit 专属——通用 SDK JSON 桥竟自动按"audit 决策"加工**所有**域输出（tender/ocr/init-rules 都被波及） | 域泄漏：新增功能域会被 audit 语义污染 |
| 3 | **routes↔api 循环（已打补丁）** | `routes/audit.py`(6) + `routes/ocr.py`(2) 共 8 处 `from server.api import verify_tenant  # lazy import breaks cycle`；`verify_tenant` 定义在 `api.py:65` | 用 lazy import 硬绕环，是创可贴；新增 route 都得重复这个 hack |
| 4 | **core.py 门面制造 core↔common 环** | `core.py` import `audit.contract`+`common.{agent_bridge,json_bridge,session_logging}`；`common/command_adapter.py:8` 又 `from server.core import ...` | 门面夹在 common 模块之间，形成逻辑环；platform→core→audit 倒挂也经它成立 |

> 注：core.py 是历史 back-compat 门面（84 行纯 re-export，注释明言"Import paths through server.core remain stable"）。真正的代码环只有 `command_adapter → core`，其余 common 文件对 core 的提及都在 docstring，非真依赖——面很窄。

## Key Decisions（与用户对齐 2026-06-18）

1. **本轮仅出方案**，零代码改动；看完再决定做哪几项。
2. **保持按技术分层**（routes/stores/platform/common 横切），新功能域作为 `audit`/`ocr` 的**兄弟模块**加入，**不**转向按功能域垂直切片（避免 YAGNI 过度设计；第三个功能域出现时再评估）。

## 目标分层（Target）

依赖严格单向向下，同层之间功能域互不 import：

```
  app 层      api.py · app_server.py · cli.py
                    │
  ops 层      ops/diagnostics.py · ops/maintenance.py        ← 新增（跨 store 编排从 platform 搬出）
                    │
  routes 层   routes/{audit,ocr,health}.py · routes/deps.py  ← deps.py 新增（verify_tenant）
                    │
  features    audit/ │ ocr/ │ <future>/      ← 兄弟，横向零 import
                    │
  common      agent_bridge · json_bridge · session_logging · contract(generic) ← 域中立
                    │
  stores      request/result/memory/session/audit_task/...
                    │
  platform    config · paths · logging · storage · sqlite     ← 纯地基，不 import 任何上层
```

判定规则：**任一模块只能 import 严格低于自己层级的模块**；功能域之间永不互相 import，只通过 common/stores/platform 间接复用。

## 方案：四项整理

### A1 · platform 反向依赖 → 抽 `ops/` 层（修 #1）

- 新建 `server/ops/`，把 `platform/diagnostics.py` → `ops/diagnostics.py`、`platform/maintenance.py` → `ops/maintenance.py`。
- 这俩本质是"跨 store 的运行时编排"，属于 routes 之下、stores 之上的 ops 层，不是地基。
- **影响 importer（3 处）**：`cli.py:24`、`app_server.py:17,19`、`routes/health.py:12` 改 `server.platform.*` → `server.ops.*`。
- 结果：`platform/` 不再 import `stores`/`core`，回归纯叶子。

### A2 · json_bridge 解 audit 耦合 → 依赖反转（修 #2，本次最关键）

- 病灶：通用 `run_agent_json` 内部硬调 `enrich_audit_decision`（audit 专属）。
- 方案（依赖反转）：`run_agent_json` 增加可选 `post_process: Callable[[dict], dict] | None` 参数；**audit 的 runner 在调用处传入** `enrich_audit_decision`，非 audit 域（ocr/tender/init-rules）不传，不被 audit 语义污染。
- 同时把 audit.contract 里**真正通用**的符号（`DEFAULT_OUTPUT_SCHEMA_NAME` / `JSONContractError` / `StructuredJSON` / `_extract_json_object` / `build_output_format` / `validate_structured_output_semantics`）下沉到 `common/contract.py`；**audit 专属**的 `enrich_audit_decision` / `AUDIT_DECISION_DERIVATION` 留在 `audit/`。
- 结果：`common/` 不再 import `audit/`，通用层域中立。

### A3 · routes↔api 环 → 抽 `routes/deps.py`（修 #3）

- 把 `verify_tenant`（+ `TENANT_KEYS` 鉴权逻辑）从 `api.py:65` 移到 `server/routes/deps.py`。
- `api.py` 与各 route 都从 `routes/deps` import；删除 8 处 `from server.api import verify_tenant` lazy import。
- `api.py` 可保留一行 re-export 兼容外部引用（`from server.routes.deps import verify_tenant`）。
- 结果：routes 不再反向 import api，环消除，新增 route 无需重复 hack。

### A4 · core.py 门面 → 收敛（修 #4，低优先）

- A1 完成后 `platform→core` 边自动消失（diagnostics 搬走）。
- 剩 `command_adapter → core → agent_bridge/json_bridge` 这一环：把 `command_adapter.py:8` 改为**直接** import `from server.common.agent_bridge import run_agent_full` + `from server.common.json_bridge import run_agent_json`，绕开门面。
- `core.py` 保留为对**外部/测试**的 back-compat re-export（注释已承诺稳定），但**内部模块一律直接 import 源模块**，不再经门面。可在后续单独 sprint 评估是否彻底删除。

### 备选方案（已否决）

**按功能域垂直切片**（每个域自带 routes+stores+logic）：隔离更彻底，但要把现有 `routes/`、`stores/` 拆散重分配到各域，改动 ~15-20 文件且回归风险高。用户选保持技术分层 + YAGNI——第三个功能域出现前不引入。

## 影响范围（文件级，供 impl 估算）

| 项 | 新增 | 移动 | 修改 importer |
|---|---|---|---|
| A1 | `ops/__init__.py` | diagnostics.py, maintenance.py | cli.py, app_server.py, routes/health.py |
| A2 | `common/contract.py` | audit.contract 部分符号下沉 | json_bridge.py, audit/runner.py（传 post_process）, core.py（re-export 跟随） |
| A3 | `routes/deps.py` | verify_tenant 定义 | api.py + routes/audit.py(6) + routes/ocr.py(2) |
| A4 | — | — | command_adapter.py, core.py |

合计约 **8-12 个文件**（含 3 个新增、2-3 个移动），不含测试同步。

## 风险与缓解

| 风险 | 缓解 |
|---|---|
| A2 改 `run_agent_json` 签名，回归面最大（所有域都走它） | `post_process` 设默认 `None` 保持向后兼容；先补测试覆盖"非 audit 域不被 enrich"，再改实现（TDD） |
| 移动模块漏改 importer 导致 ImportError | 每项改完跑 `uv run pytest -q`（现 212 通过基线）+ `python -c "import server.api"` 冒烟 |
| core.py 是外部承诺的稳定门面，删/改伤兼容 | A4 只改**内部** import 源，门面 re-export 表面不变；彻底删除留独立 sprint |
| Refactor 红区多写者 | 按铁律[零写入]，impl 阶段用 `isolation: worktree` 隔离执行 |

## 验收标准

1. `uv run pytest -q` 保持全绿（基线 212 passed），且新增"功能域隔离"断言测试。
2. 依赖方向校验：`platform/` 不出现 `from server.{stores,ops,routes,api,core}`；`common/` 不出现 `from server.audit`；`routes/` 不出现 `from server.api import`（lazy）。可用一条 grep 守卫脚本固化进 CI/测试。
3. `audit/` 与 `ocr/` 仍互不 import（隔离不退化）。
4. `python -c "import server.api, server.cli"` 无循环导入告警。

## 迁移顺序建议（确认范围后执行）

A3（最独立、低风险）→ A1（机械移动）→ A2（最关键、需 TDD）→ A4（收尾）。每步独立 commit + 跑测试，避免一次性大爆炸。
