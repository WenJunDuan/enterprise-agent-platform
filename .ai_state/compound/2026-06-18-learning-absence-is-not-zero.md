---
name: absence-is-not-zero
description: 审核中"输入里没有证据"≠"客观得0分"，不可判定项必须 manual_review；附"新增业务域是纯配置驱动、零 Python"
metadata:
  type: learning
---

## 缺证据 ≠ 0 分（不可判定项 → manual_review）

DeepSeek 快速模式评一份真实标（川姜花苑 R2024-007）时，把三项判了 0：

- 项目负责人答辩（评标**现场**环节，投标文件里当然没有）
- 企业信用（来自**外部**市级公示评价表，不在投标文件内）
- 价格分（须**横向比较**所有投标报价，单份标无法算）

这是**范畴错误**：把"我手里的输入里找不到"当成"客观为 0"。后果是系统性低估投标人、且对方无从申辩——恰好是本平台宪法（证据不足 / 规则缺失 / 需外部输入 → `manual_review`，不下过度确定结论）禁止的。

**正解**：给这类评分项在规则里打标 `requires_live_event` / `requires_external_data` / `requires_cross_bid_comparison`；评分时命中即 `status:"manual_review"`、`score:null`，并写清需要什么外部输入（现场记录 / 外部评价表 / 全部报价）。绝不判 0。

**Why:** 0 是一个**确定的判定值**，只有在"规则可依据当前材料判定且确实不达标"时才成立。当判定依赖当前材料之外的输入时，正确状态是"未判定"，不是"判 0"。用缺省值（0 / 空 / false）冒充"未判定"，会把不确定性悄悄洗成确定结论。
**How to apply:** 任何审核域，凡"结论依赖当前材料之外的输入"的检查项，默认 `manual_review` 并说明缺口；评分类输出用三态 `scored / manual_review / rejected`，未判定项 `score:null` 不计入合计。关联 [[cross-review-and-soft-timeout]]。

## 新增业务域是配置驱动（零 Python 改动）

给平台加第 5 个域 `tender`，没动一行 `server/` 代码。扩展点全在 `.claude/` + `knowledge/`：

- 两处 enum 加 domain key：`knowledge/_schema/rule.schema.json`、`.claude/contracts/system/init-rules-report.schema.json`
- 目录：`.claude/agents/{domain}/`、`.claude/contracts/{domain}/`、`.claude/skills/{domain}-*/`、`knowledge/{domain}/`、`knowledge/memory/{domain}/`
- `CLAUDE.md` 路由表 + 调度段

约束：domain key 必须**小写 ascii 且 == 父目录名**（`server/platform/asset_validation.py` 用 `path.parent.name` 校验 `payload["domain"]`）；rule_id 用下划线 `{domain}_{category}_{seq}`（注意 `rule-init/SKILL.md` 里写的是点号，与真实数据不符，别跟它）。

**Why:** 审核判断、规则、记忆都在 Claude 侧（`.claude/` 配置 + `knowledge/` 规则）完成，Python 只跑服务 / 取外部输入 / 提交——所以"加域"是改 prompt + 契约 + 知识，不是改代码。
**How to apply:** 加新域照搬 expense 三段式（extractor / auditor(evaluator) / reviewer + 契约 + skill），改 domain 词与领域字段；别给 `risk_dimensions` / `manual_review_reason` 这类**共享枚举**塞领域专属值，尽量复用 `common` 契约。dedicated-agent 模式（如 legal/hr）可绕开 expense 专属的内联 `/audit`，避免动 `runner.py`。
