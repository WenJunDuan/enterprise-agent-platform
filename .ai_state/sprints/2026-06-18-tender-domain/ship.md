# Tender 评标域 Ship Record

> 对话驱动交付，事后补档 2026-06-18。

## Scope

新增 `tender` 业务域骨架（v1 评分评审）。不改 `server/` 代码、不改其他域。

## Result

### 改动文件（git 跟踪）

- enum：`knowledge/_schema/rule.schema.json`、`.claude/contracts/system/init-rules-report.schema.json`（各 `+"tender"`）
- agent（新）：`.claude/agents/tender/{extractor,evaluator,reviewer}.md`
- 契约（新）：`.claude/contracts/tender/{extract-result,review-delta}.schema.json`
- skill（新）：`.claude/skills/tender-eval/SKILL.md`
- 路由：`.claude/CLAUDE.md`（业务域表 + tender 调度段 + 多域协同示例）
- skill：`.claude/skills/system/rule-init/SKILL.md`（加 tender 两层 + tags 说明）

### 落盘但 git 忽略（`knowledge/` 被 `.gitignore`，按既定约定"制度源材料不入库"）

- `knowledge/tender/README.md`（两层布局说明）
- `knowledge/tender/r2024007.rules.json`（川姜花苑样例规则，`confidence:medium`，每条 notes 注明"待用原始招标文件核验"）
- `knowledge/memory/tender/.gitkeep`

> 注意：`knowledge/tender/` 在磁盘上但不会进版本库；换机 / 重新 clone 后需用 `/init-rules` 基于真实招标文件重新生成。这是平台既有约定（见 `_index.md` gotchas），非疏漏。

## Verification

- jsonschema 21/21 通过：4 个新 schema 合法 Draft7；全部 `knowledge/**/*.rules.json`（含既有 expense×3 + 新 tender）仍合 `rule.schema`；`domain == 父目录名`；两处 enum 含 tender。
- dry-run（川姜花苑这单）跑过新契约：构造的 extract-result + audit-result 均 schema-valid；专门断言"无不可判定项被判 0"通过。
- 结果对比 DeepSeek：

  | 评分项 | DeepSeek | tender-evaluator |
  | --- | --- | --- |
  | 价格标 82 | 未评 | manual_review（requires_cross_bid_comparison）|
  | 施工组织设计 6 | 6 | 6（scored）|
  | 答辩 2 | **0** | manual_review（requires_live_event）|
  | 业绩 2 | **0** | manual_review（data_conflict，引 2.07 vs 2.08）|
  | 企业信用 8 | **0** | manual_review（requires_external_data）|

  整单 `verdict=manual_review` / `manual_review_reason=data_conflict`，三个假 0 全部消失。

- 回归：`tests/` 与 `server/` 无硬编码旧 domain 枚举，改动纯 additive。未跑 `uv run pytest`（项目 `.venv` 为 mac/py3.14，Linux sandbox 跑不起；改动 additive，回归风险极低）。

## Follow-ups（v2 候选）

- `rule-init/SKILL.md` 第 5 步把 rule_id 写成点号 `{domain}.{category}.{seq}`，与全部真实数据及 schema 描述的下划线 `{domain}_{category}_{seq}` 不一致——潜在 bug，待修（本次按下划线落地，未动该行）。
- `audit-result.risk_dimensions.name` 枚举（`invoice/amount/approval/budget/anomaly`）为报销味，套不进评标；tender v1 不输出该可选字段，v2 加 tender 维度（价格/资格/业绩/一致性）。
- `statute.rules.json` 通则层未生成：把招标投标法 / 政府采购法等放 `knowledge/external/`，再 `/init-rules <源文件> tender` 生成。
- 样例 `r2024007` 规则 `confidence:medium`，投产前用原始招标文件 PDF 重生成覆盖。
- v2：资格审查 / 一票否决 / 串标围标识别；`/audit` 按域自动路由（`runner.py` 加 domain 参数）。

代码尚未 commit。
