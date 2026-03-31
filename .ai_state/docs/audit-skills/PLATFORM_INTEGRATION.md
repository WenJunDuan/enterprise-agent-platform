# 报销审计模块 — Agent SDK 平台集成设计

> 从 Skill MVP 到生产级 Agent 的升级路径

---

## 定位

本文档定义如何将 `expense-audit` Skill 的核心逻辑移植到你的 Claude Agent SDK 平台，对接现有的七层架构。

Skill（形态A）验证了审计逻辑的可行性，本文档（形态B）解决的是：多用户并发、规则热更新、审计轨迹持久化、与其他部门插件共存。

---

## 架构映射

Skill 中的概念如何映射到你平台的七层：

| Skill 概念 | 平台层 | 落地位置 |
|---|---|---|
| SKILL.md 工作流 | Agent 层 | `agents/expense-auditor/agent.md` |
| 文件解析逻辑 | Skills 层 | `skills/doc-parser/` |
| 交叉比对逻辑 | Skills 层 | `skills/expense-reconcile/` |
| default_rules.yaml | Knowledge 层 | `knowledge/rules/expense-audit.yaml` |
| rule_schema.md | Knowledge 层 | `knowledge/schemas/expense-rule.schema.yaml` |
| audit_check.py | Tools 层 | `tools/business/audit-engine/` (MCP server) |
| 审计报告生成 | Skills 层 | `skills/report-gen/` |
| 审计结果存储 | Storage 层 | `storage/audit/` (JSONL dev / PostgreSQL prod) |
| 输出审查 | Hooks 层 | 复用现有 `PostToolUse` hook (Haiku review) |

---

## 目录结构增量

基于你现有项目结构，新增/修改的文件：

```
project-root/
├── .claude/
│   └── CLAUDE.md                          # 追加 expense-audit 路由规则
├── agents/
│   └── expense-auditor/
│       └── agent.md                       # Agent 指令：编排 Phase 0-4
├── skills/
│   ├── doc-parser/
│   │   └── skill.md                       # 多格式文件解析 → 结构化数据
│   ├── expense-reconcile/
│   │   └── skill.md                       # 交叉比对逻辑
│   └── report-gen/
│       └── skill.md                       # 审计报告生成
├── knowledge/
│   ├── rules/
│   │   └── expense-audit.yaml             # 从 Skill 的 default_rules.yaml 迁移
│   └── schemas/
│       └── expense-rule.schema.yaml       # 规则校验 schema (JSON Schema 格式)
├── tools/
│   └── business/
│       └── audit-engine/
│           ├── server.py                  # MCP server: 暴露 audit_check 为工具
│           └── engine.py                  # 从 Skill 的 audit_check.py 迁移
├── plugins/
│   └── expense-audit/
│       └── plugin.yaml                    # 插件声明
└── storage/
    └── audit/
        └── README.md                      # 审计记录存储说明
```

---

## 关键模块设计

### 1. CLAUDE.md 路由追加

```markdown
## expense-audit 路由
当用户意图涉及以下场景时，路由到 expense-auditor agent:
- 报销审核/审计
- 出差费用检查
- 发票/行程单/报销单校验
- 上传了报销相关文件

路由至: agents/expense-auditor/agent.md
```

纯路由，零业务逻辑。与你现有的 dispatcher 模式一致。

### 2. Agent 指令 (agent.md)

agent.md 是**编排器**，不包含任何硬编码规则或金额。它的职责：

1. 调用 `skills/doc-parser` 提取结构化数据
2. 加载 `knowledge/rules/expense-audit.yaml`（支持热更新）
3. 调用 `tools/business/audit-engine` 执行规则检查
4. 调用 `skills/expense-reconcile` 做交叉比对
5. 调用 `skills/report-gen` 生成报告
6. 写入 `storage/audit/` 保存审计轨迹

**agent.md 不知道住宿标准是500还是800。** 这个数字只存在于 knowledge 层。

### 3. MCP Tool Server (audit-engine)

将 `audit_check.py` 封装为 MCP server，注册到 `mcp__biz__` 命名空间：

```python
# tools/business/audit-engine/server.py
from mcp import Server
from .engine import run_audit

server = Server("audit-engine")

@server.tool("run_expense_audit")
async def run_expense_audit(
    expenses_json: str,   # Phase 1 提取的结构化数据
    rules_path: str,      # knowledge 层规则文件路径
    user_id: str          # 审计发起人（用于存储隔离）
) -> dict:
    """执行报销审计检查，返回审计结果"""
    expenses = json.loads(expenses_json)
    rules = load_rules(rules_path)
    results = run_audit(expenses, rules)
    # 写入审计轨迹
    save_audit_trail(user_id, expenses, results)
    return results
```

为什么用 MCP tool 而不是 skill？因为审计引擎是**确定性逻辑**（给定输入必须产生确定输出），用 tool 保证 Claude 不会"创造性地"跳过某些检查。

### 4. 规则热更新

```
knowledge/rules/expense-audit.yaml
```

这个文件是 agent 在**每次审计时重新读取**的，不是启动时缓存的。修改规则 → 下次审计立即生效。

自定义规则上传流程：
1. 用户上传公司制度文档
2. `doc-parser` skill 提取规则
3. 与 `knowledge/schemas/expense-rule.schema.yaml` 校验
4. 合并写入 `knowledge/rules/expense-audit-custom-{tenant_id}.yaml`
5. 后续审计优先加载 custom 文件

### 5. Plugin 声明

```yaml
# plugins/expense-audit/plugin.yaml
plugin_id: expense-audit
name: 出差报销审计
version: "1.0.0"
description: 出差报销材料的自动化审计

agent: agents/expense-auditor/agent.md
skills:
  - skills/doc-parser
  - skills/expense-reconcile
  - skills/report-gen
tools:
  - tools/business/audit-engine
knowledge:
  - knowledge/rules/expense-audit.yaml
  - knowledge/schemas/expense-rule.schema.yaml

capabilities:
  - file_upload        # 需要处理用户上传的文件
  - structured_output  # 输出结构化审计结果
  - report_generation  # 生成审计报告
```

新增一个审计领域 = 新增一个 `plugins/xxx/plugin.yaml` + 对应文件。零框架代码修改。

### 6. 存储设计

**开发环境** (JSONL):
```
storage/audit/
  └── {YYYY-MM-DD}/
      └── {user_id}_{timestamp}.jsonl
```

**生产环境** (PostgreSQL):
```sql
CREATE TABLE audit_trails (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     TEXT NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT now(),
    trip_summary JSONB,        -- 出差基本信息
    expenses    JSONB,         -- 提取的结构化费用
    rules_version TEXT,        -- 使用的规则版本
    results     JSONB,         -- 审计结果
    report_url  TEXT           -- 生成的报告存储地址
);

CREATE INDEX idx_audit_user ON audit_trails (user_id, created_at DESC);
```

---

## 从 Skill MVP 迁移清单

| 步骤 | 来源 (Skill) | 目标 (平台) | 改动程度 |
|------|------|------|------|
| 1 | `references/default_rules.yaml` | `knowledge/rules/expense-audit.yaml` | 直接复制 |
| 2 | `references/rule_schema.md` | `knowledge/schemas/` (转为 JSON Schema) | 中等 |
| 3 | `scripts/audit_check.py` | `tools/business/audit-engine/engine.py` | 小改：加 MCP 包装 |
| 4 | `SKILL.md` Phase 0-1 | `skills/doc-parser/skill.md` | 提取为独立 skill |
| 5 | `SKILL.md` Phase 2 | `skills/expense-reconcile/skill.md` | 提取为独立 skill |
| 6 | `SKILL.md` Phase 4 | `skills/report-gen/skill.md` | 提取为独立 skill |
| 7 | 整体流程 | `agents/expense-auditor/agent.md` | 重写为编排指令 |
| 8 | — | `plugins/expense-audit/plugin.yaml` | 新建 |
| 9 | — | `storage/audit/` | 新建 |

---

## 已知约束与风险

**并发**: 文件解析（Phase 1）是 CPU/IO 密集型。CLI subprocess 并发瓶颈仍然存在。对于批量审计场景（如月末集中报销），考虑队列化处理。

**OCR 质量**: 扫描件质量差时，提取置信度低。生产环境考虑集成专业 OCR 服务（如百度/腾讯 OCR API）作为 doc-parser 的增强路径。

**规则冲突**: 自定义规则与默认规则合并时可能产生冲突（如自定义规则放宽了默认规则的限制）。需要在 schema 校验层做冲突检测。

**审计可追溯性**: 审计结果必须关联到使用的规则版本。规则文件变更时应保留历史版本（git 或 version 字段）。
