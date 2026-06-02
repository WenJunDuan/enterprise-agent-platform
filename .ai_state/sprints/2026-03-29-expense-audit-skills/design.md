# Expense Audit Skills Design

## Context

- `.ai_state/docs/audit-skills/` 提供了更完整的报销审计草案，但当前 `.claude/skills/expense-audit/` 与相关 `common/system` skills 仍是占位版本。
- `knowledge/expense/*.json` 已经承载了当前 expense 域的结构化规则，但没有填写可追溯的 `source` 元数据。
- 当前仓库的真实制度源是 `knowledge/external/数睿员工手册.pdf`，expense 规则主要对应第六章 `6.3` 到 `6.7`。

## Goals

1. 以 `.ai_state/docs/audit-skills/SKILL.md` 的流程思想为基准，重写 `.claude/skills/expense-audit/` 的总 skill 和子 skills。
2. 同步增强 `.claude/skills/common/rule-query`、`.claude/skills/common/evidence-chain`、`.claude/skills/common/result-format`、`.claude/skills/system/rule-init`。
3. 为 `knowledge/expense/*.json` 补充真实制度来源路径与章节说明。
4. 保持现有 skill 名称不变，避免破坏 `.claude/agents/expense/auditor.md` 的已有引用。

## Non-Goals

- 不在本次任务中引入新的 MCP tool、插件或服务端执行器。
- 不重写 `hr`、`legal` 域规则。
- 不在本次任务中扩写超出当前结构化 rules 已表达范围的大量新业务条款。

## Design Decisions

### 1. Skill 体系保持原有命名，重写内容

- 保留 `expense-audit` 与现有 6 个子 skill 名称。
- 将 `expense-audit` 从“目录索引”升级为报销审核总控 skill。
- 每个子 skill 都明确：
  - 适用场景
  - 要读取的本地规则文件
  - 对应制度源路径
  - 缺规则、缺字段、证据冲突时如何降级为 `manual_review`

### 2. 规则执行以结构化 JSON 为准，PDF 仅用于追溯

- `knowledge/expense/*.json` 是审核时的可执行规则源。
- `knowledge/external/数睿员工手册.pdf` 是制度追溯源，不作为审核时临时自由提取规则的依据。
- 当结构化 rules 与源制度之间存在覆盖缺口时，审核阶段输出 `manual_review`，并建议后续运行 `system-rule-init` 补齐规则，而不是现场发明规则。

### 3. 为 expense 规则文件补 `source`

- 对以下文件补充顶层 `source`：
  - `knowledge/expense/general.rules.json`
  - `knowledge/expense/invoice.rules.json`
  - `knowledge/expense/loan.rules.json`
  - `knowledge/expense/entertainment.rules.json`
  - `knowledge/expense/travel.rules.json`
  - `knowledge/expense/transport.rules.json`
- 每个 `source` 至少包含：
  - `path`
  - `title`
  - `excerpt`

### 4. `thresholds.json` 保持派生文件定位

- `knowledge/expense/thresholds.json` 不是 `rule.schema.json` 约束下的规则文档。
- 本次不把它改造成统一规则文档，而是追加 `_meta`，说明：
  - 源制度路径
  - 派生来源规则文件
  - 章节映射

### 5. 输出契约与证据链要对齐现有 schema

- 所有 skill 内容统一对齐 `.claude/contracts/common/audit-result.schema.json`。
- `policy_refs` 必须引用 `rule_id`。
- `evidence_chain[].source` 必须是单个字符串，因此需要把 `rule_id + rule file path + source file path` 压缩成单条可读 source 文本。

## Source Mapping

| Rule File | Handbook Source |
| --- | --- |
| `knowledge/expense/general.rules.json` | `knowledge/external/数睿员工手册.pdf` 第 `6.3.1`、`6.3.2`、`6.3.4` 节 |
| `knowledge/expense/invoice.rules.json` | `knowledge/external/数睿员工手册.pdf` 第 `6.3.3`、`6.3.4` 节 |
| `knowledge/expense/loan.rules.json` | `knowledge/external/数睿员工手册.pdf` 第 `6.4.2`、`6.4.3` 节 |
| `knowledge/expense/entertainment.rules.json` | `knowledge/external/数睿员工手册.pdf` 第 `6.5.1`、`6.5.2`、`6.5.3` 节 |
| `knowledge/expense/travel.rules.json` | `knowledge/external/数睿员工手册.pdf` 第 `6.6.1`、`6.6.2`、`6.6.3`、`6.6.4` 节 |
| `knowledge/expense/transport.rules.json` | `knowledge/external/数睿员工手册.pdf` 第 `6.7.1`、`6.7.2`、`6.7.3` 节 |
| `knowledge/expense/thresholds.json` | 派生自上述 expense rule files，回指第六章费用制度 |

## Files To Change

- `.claude/skills/expense-audit/SKILL.md`
- `.claude/skills/expense-audit/amount-validate/SKILL.md`
- `.claude/skills/expense-audit/budget-check/SKILL.md`
- `.claude/skills/expense-audit/invoice-parse/SKILL.md`
- `.claude/skills/expense-audit/pre-approval-match/SKILL.md`
- `.claude/skills/expense-audit/travel-compliance/SKILL.md`
- `.claude/skills/expense-audit/entertainment-compliance/SKILL.md`
- `.claude/skills/common/rule-query/SKILL.md`
- `.claude/skills/common/evidence-chain/SKILL.md`
- `.claude/skills/common/result-format/SKILL.md`
- `.claude/skills/system/rule-init/SKILL.md`
- `knowledge/expense/general.rules.json`
- `knowledge/expense/invoice.rules.json`
- `knowledge/expense/loan.rules.json`
- `knowledge/expense/entertainment.rules.json`
- `knowledge/expense/travel.rules.json`
- `knowledge/expense/transport.rules.json`
- `knowledge/expense/thresholds.json`

## Verification

1. 所有变更后的 skill 文件不再包含 `/mnt/...` 或 `/path/to/skill/...` 之类占位路径。
2. 所有 expense 规则文件都包含真实的 `source.path`。
3. `thresholds.json` 包含来源说明但不破坏现有阈值结构。
4. 所有 JSON 文件可以被标准 JSON 解析器成功读取。
5. `common-result-format`、`common-evidence-chain` 与 `.claude/contracts/common/audit-result.schema.json` 保持一致。
