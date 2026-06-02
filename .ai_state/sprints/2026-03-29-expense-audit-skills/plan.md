# Expense Audit Skills Overhaul Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite the expense audit skill stack so it references real local rule paths and handbook sources, then add traceable source metadata to the existing expense rules.

**Architecture:** Keep the current `.claude` skill names and agent wiring intact, but replace placeholder skill content with executable local-process guidance. Expense rule JSON remains the executable rule source, while the handbook PDF becomes the traceability source captured in top-level metadata.

**Tech Stack:** Markdown skills, JSON rule documents, ripgrep, jq or Python JSON parsing

---

### Task 1: Write Design + Task Trace

**Files:**
- Create: `.ai_state/superpowers/specs/2026-03-29-expense-audit-skills-design.md`
- Create: `.ai_state/superpowers/plans/2026-03-29-expense-audit-skills-overhaul.md`
- Modify: `.ai_state/plan.md`
- Modify: `.ai_state/doing.md`
- Modify: `.ai_state/session.md`

- [ ] **Step 1: Record the approved design**

```markdown
## Goals
- Rewrite expense-audit and related common/system skills
- Add source metadata to knowledge/expense/*.json
- Keep existing skill names stable
```

- [ ] **Step 2: Add the execution plan**

Run: `test -f .ai_state/superpowers/plans/2026-03-29-expense-audit-skills-overhaul.md`
Expected: exit code `0`

- [ ] **Step 3: Update `.ai_state` to reflect the active skill-overhaul task**

```markdown
- [ ] T-009: 重写 expense audit skills 并补齐 knowledge/expense 规则来源元数据
```

### Task 2: Rewrite Expense Audit Skills

**Files:**
- Modify: `.claude/skills/expense-audit/SKILL.md`
- Modify: `.claude/skills/expense-audit/amount-validate/SKILL.md`
- Modify: `.claude/skills/expense-audit/budget-check/SKILL.md`
- Modify: `.claude/skills/expense-audit/invoice-parse/SKILL.md`
- Modify: `.claude/skills/expense-audit/pre-approval-match/SKILL.md`
- Modify: `.claude/skills/expense-audit/travel-compliance/SKILL.md`
- Modify: `.claude/skills/expense-audit/entertainment-compliance/SKILL.md`

- [ ] **Step 1: Replace placeholder descriptions with discovery-oriented descriptions**

```yaml
description: Use when 审核报销、发票、差旅或招待事项，需要按本地 expense 规则文件输出可追溯结论
```

- [ ] **Step 2: Add real local rule paths and handbook source path to each skill**

```markdown
- `knowledge/expense/travel.rules.json`
- `knowledge/expense/transport.rules.json`
- `knowledge/external/数睿员工手册.pdf`
```

- [ ] **Step 3: Add manual-review downgrade rules**

```markdown
未命中结构化规则、关键字段缺失、规则冲突或 OCR 置信度不足时，不得自行补规则，输出 `manual_review`。
```

- [ ] **Step 4: Verify no placeholder path remains**

Run: `rg -n '/mnt/|/path/to/skill|占位符' .claude/skills/expense-audit`
Expected: no matches from the rewritten expense-audit skill files

### Task 3: Rewrite Common + System Skills

**Files:**
- Modify: `.claude/skills/common/rule-query/SKILL.md`
- Modify: `.claude/skills/common/evidence-chain/SKILL.md`
- Modify: `.claude/skills/common/result-format/SKILL.md`
- Modify: `.claude/skills/system/rule-init/SKILL.md`

- [ ] **Step 1: Make `common-rule-query` return rule ids plus source metadata**

```markdown
返回项至少包含：`rule_id`、`action`、`priority`、`rule_file`、`source_path`
```

- [ ] **Step 2: Make `common-evidence-chain` conform to audit-result schema**

```json
{
  "source": "rule:expense.travel.004 @ knowledge/expense/travel.rules.json",
  "finding": "住宿标准为一类城市 500 元/晚",
  "conclusion": "violate"
}
```

- [ ] **Step 3: Make `common-result-format` enforce verdict rules**

```markdown
- `approved`: 所有必需检查完成且 `policy_refs` 非空
- `rejected`: 命中明确拒绝规则
- `manual_review`: 缺证据、缺规则、规则冲突、结构化信息不足
```

- [ ] **Step 4: Make `system-rule-init` write `source.path/title/excerpt`**

Run: `rg -n 'source\\.path|source\\.title|source\\.excerpt' .claude/skills/system/rule-init/SKILL.md`
Expected: all three fields are mentioned

### Task 4: Add Source Metadata To Expense Rules

**Files:**
- Modify: `knowledge/expense/general.rules.json`
- Modify: `knowledge/expense/invoice.rules.json`
- Modify: `knowledge/expense/loan.rules.json`
- Modify: `knowledge/expense/entertainment.rules.json`
- Modify: `knowledge/expense/travel.rules.json`
- Modify: `knowledge/expense/transport.rules.json`
- Modify: `knowledge/expense/thresholds.json`

- [ ] **Step 1: Add top-level `source` to rule documents**

```json
"source": {
  "path": "knowledge/external/数睿员工手册.pdf",
  "title": "数睿员工手册 第6.6节 差旅费报销管理制度",
  "excerpt": "涵盖交通工具标准、住宿标准、出差补助、出差申请与差旅报销要求。"
}
```

- [ ] **Step 2: Add `_meta` to `thresholds.json` without changing threshold keys**

```json
"_meta": {
  "source_path": "knowledge/external/数睿员工手册.pdf",
  "derived_from": {
    "travel": ["knowledge/expense/travel.rules.json"]
  }
}
```

- [ ] **Step 3: Validate JSON integrity**

Run: `python - <<'PY'\nimport json, pathlib\nfor path in pathlib.Path('knowledge/expense').glob('*.json'):\n    json.loads(path.read_text())\n    print('OK', path)\nPY`
Expected: every expense JSON file prints `OK`

### Task 5: Final Consistency Verification

**Files:**
- Verify: `.claude/skills/expense-audit/`
- Verify: `.claude/skills/common/`
- Verify: `.claude/skills/system/`
- Verify: `knowledge/expense/`

- [ ] **Step 1: Check every rewritten skill references real repo paths**

Run: `rg -n 'knowledge/external/数睿员工手册\\.pdf|knowledge/expense/' .claude/skills/expense-audit .claude/skills/common .claude/skills/system`
Expected: matches in all rewritten target skills

- [ ] **Step 2: Check no placeholder runtime path survives**

Run: `rg -n '/mnt/|/path/to/skill|references/default_rules\\.yaml' .claude/skills`
Expected: no matches in the rewritten skills

- [ ] **Step 3: Mark the task done in `.ai_state`**

```markdown
- [x] T-009: 重写 expense audit skills 并补齐 knowledge/expense 规则来源元数据
```
