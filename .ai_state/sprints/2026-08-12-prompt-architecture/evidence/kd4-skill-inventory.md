# KD4 · 占位 skill 盘点记录（2026-08-13，处置前实测）

盘点命令（仓库根，worktree `agent-adb233b1dd1ec8a09`）：

```bash
grep -rn "skills/common\|skills/system\|system-rule-init\|system-memory-distill\|common-skills\|system-skills" \
  --exclude-dir=node_modules --exclude-dir=.venv --exclude-dir=.git --exclude-dir=.ai_state .
grep -rn "common-rule-query\|common-memory-query\|common-anomaly-detect\|common-evidence-chain\|common-result-format" \
  --exclude-dir=.ai_state --exclude-dir=.git --exclude-dir=node_modules --exclude-dir=.venv .
```

## 实测目录内容（`find .claude/skills/common .claude/skills/system -type f`）

| 文件 | frontmatter `name` | 性质 |
|---|---|---|
| `.claude/skills/common/SKILL.md` (406B) | `common-skills` | **分组空壳**：正文只列 5 个子 skill 名，无能力内容 |
| `.claude/skills/common/rule-query/SKILL.md` | `common-rule-query` | 真实 skill |
| `.claude/skills/common/memory-query/SKILL.md` | `common-memory-query` | 真实 skill |
| `.claude/skills/common/anomaly-detect/SKILL.md` | `common-anomaly-detect` | 真实 skill |
| `.claude/skills/common/evidence-chain/SKILL.md` | `common-evidence-chain` | 真实 skill |
| `.claude/skills/common/result-format/SKILL.md` | `common-result-format` | 真实 skill |
| `.claude/skills/system/SKILL.md` (273B) | `system-skills` | **分组空壳**：正文只列 2 个子 skill 名 |
| `.claude/skills/system/rule-init/SKILL.md` | `system-rule-init` | 真实 skill |
| `.claude/skills/system/memory-distill/SKILL.md` | `system-memory-distill` | 真实 skill |

## 引用清单（.ai_state 历史档不计，只看生产面）

| 被引用名 | 引用处 | 结论 |
|---|---|---|
| `common-rule-query` | `.claude/agents/expense/{auditor,reviewer}.md`、`.claude/agents/tender/{evaluator,reviewer}.md` frontmatter `skills:` | 有活消费者 |
| `common-memory-query` | `.claude/agents/expense/auditor.md`、`.claude/agents/tender/evaluator.md` | 有活消费者 |
| `common-anomaly-detect` | `.claude/agents/expense/auditor.md` | 有活消费者 |
| `common-evidence-chain` | 4 个 agent + `.claude/hooks/check-before-write.py:122` 提示文案 | 有活消费者 |
| `common-result-format` | `.claude/agents/expense/auditor.md`、`.claude/agents/tender/evaluator.md` | 有活消费者 |
| `system-rule-init` | `.claude/CLAUDE.md` ×3、`.claude/commands/init-rules.md:6`、`.claude/skills/tender-eval/SKILL.md:57`、`.claude/skills/expense-audit/SKILL.md:37`、`.claude/skills/common/rule-query/SKILL.md:30` | 有活消费者，**且实体存在** |
| `system-memory-distill` | `.claude/CLAUDE.md` ×2、`.claude/commands/distill-memory.md:6`、自身正文 | 有活消费者，**且实体存在** |
| `common-skills` | 仅 `.claude/skills/common/SKILL.md` 自身 | **零外部引用** |
| `system-skills` | 仅 `.claude/skills/system/SKILL.md` 自身 | **零外部引用** |

## 与 design KD4 两处假设的偏差（以盘点结果为准，design 明写"二选一，以盘点为准"）

1. **design 说 `common/`(406B) / `system/`(273B) 是空壳目录、可删目录**——实测那 406B/273B
   只是**分组级 `SKILL.md`**；两个目录下各有 5 个 / 2 个**有活消费者的真实子 skill**。
   → 处置改为：**只删两个分组空壳 `SKILL.md`**，子 skill 目录原样保留。删目录会连带删掉 4 个
   agent frontmatter 正在声明的 5 个能力，属破坏性误伤。
2. **design 说 `system-rule-init` / `system-memory-distill` 是悬空名**——实测两者是
   `.claude/skills/system/{rule-init,memory-distill}/SKILL.md` 的 frontmatter `name`，**不悬空**。
   → CLAUDE.md 调度表仍按派工改为直接引用 `/init-rules`、`/distill-memory` 两个 command（更贴近
   用户实际调用面），并在括号里保留其背后的 skill 名，调度语义不变；AC5 机械核对因此需要能同时
   解析 command 文件名、skill frontmatter name 与 agent 文件名三类实体。

## 处置后复核

```bash
grep -rn "common-skills\|system-skills" --exclude-dir=.ai_state --exclude-dir=.git \
  --exclude-dir=node_modules --exclude-dir=.venv .   # 期望 0 命中
```
