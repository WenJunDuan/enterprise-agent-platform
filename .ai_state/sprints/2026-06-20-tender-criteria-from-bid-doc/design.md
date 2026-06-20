# Tender 评标改造 Design — 招标文件直读出标准，不再预建项目层

> Sprint 2026-06-20 · Path: **System/Refactor**（动 tender 核心数据流 + `.claude` 业务提示词）· 落档先于实现。
> **本设计供下一会话实现**（用户 2026-06-20 决定本会话只出设计、下会话实现）。

## Goal

让招投标评标对齐真实评标流程：**先读招标文件第三章《评标办法》拿到本项目评分标准 → 作为该会话的项目规则 → 再读投标（应标）文件按标准逐项评分 → 给出每项丢分/得分原因 → 出审核意见**。去掉"预建项目层规则文件"这个不符现实的中间层。

## 背景与问题（已查证）

- **现状（错的方向）**：tender 评分依赖**预建** `knowledge/tender/{招标编号}.rules.json`（"项目层"），由 `/init-rules` 生成；命令 S1 读它；**缺失即 `manual_review(rule_gap)`，且明令"不要现场从招标文件 PDF 编造评分规则"**。
- **现实（用户确认，对的方向）**：招投标**没有**预建的"项目规则库"；每个项目的评分标准就在**它自己的招标文件第三章《评标办法》**里（价格 X 分 / 技术 Y 分 / 信用 Z 分 …全是项目专属），评标时**直读招标文件**即可。
- **铁证**：本会话删除的 `r2024007.rules.json` 每条 `notes` 都写着"样例规则，待用原始招标文件第三章核验"、confidence=`medium`——连作者都标了它只是占位。**已于本会话删除**（gitignored，301 green / validate-assets ok）。
- **当前缺口（你的 6 步 vs 现状）**：
  | 步 | 现状 | 状态 |
  |---|---|---|
  | 1 读招标文件→拿本项目标准 | S0 识别出招标文件，但 S1 不读它、读预建 JSON + 禁读 PDF | ❌ 核心缺 |
  | 2 存 data/ 作会话项目规则 | 无此环节 | ❌ 全缺 |
  | 3 读投标文件 | S2 抽取（extract-result 契约） | ✅ |
  | 4 按标准评分 | S3 `scoring{item,max,score,status,basis}`，但标准源接的是预建 JSON | ⚠️ 机制在/源错 |
  | 5 丢分/得分原因 | 每项 `basis` + S4 `reasons/evidence_chain` | ⚠️ 大部在 |
  | 6 审核意见 | S4 `verdict/explanation` | ✅ |
  → **真缺的是第 1、2 步**（从招标文件取标准 + 存会话规则）；3–6 机制在，第 4 步标准源要改接。

## 方案：两段式 + 会话项目规则 + 通则层保留

```
[Phase 1 · 取标准]  招标文件第三章《评标办法》 ──AI直读解析──► 本项目评分标准(criteria) ──存会话(data/)──┐
[Phase 2 · 评分]    投标文件 ──抽取事实──► 按 criteria 逐项评分 ──► 每项丢/得分原因 ──► verdict/意见 ◄┘
通则层(不动)       evalmethod / regulation = 国家法规，作法律底座(废标/资格/串标红旗/一致性)
```

1. **会话项目规则 = `criteria`**（本设计核心新增）：S1 读招标文件第三章 → 产出结构化评分标准（评分项、满分、评分规则、出处页、不可判定标签）。
   - **持久化（推荐·最小改动）**：作为 `extracted_data.criteria` 随最终结论一起 `archive_result_payload` 落 data/——满足"存到 data/ 作会话规则"，无需新 store/新工具权限。
   - **备选（显式中间产物）**：给 tender 命令加 `Write` 工具，S1 把 `criteria.json` 写进案件目录 `data/submissions/<tenant>/<request_id>/`（更贴"先存再读"，但扩了写权限面）。v1 取推荐项，备选留后。
2. **翻转护栏**：招标文件第三章**直读即权威**，不是"编造"。新护栏措辞：「评分标准**直读**招标文件第三章；招标文件**没写**的标准不得用训练记忆/臆测补充」。删除"项目层缺失→rule_gap / 不要读招标文件 PDF"那套。
3. **通则层保留**：`evalmethod.rules.json`（评标方法暂行规定）、`regulation.rules.json`（实施条例）是国家法规、跨项目稳定，作法律底座——**不动**。它们的 `rule_id`（`tender_evalmethod_*` / `tender_regulation_*`）仍是真实可引的 `policy_refs`。
4. **与 H1 验证闸的交互（必处理）**：本会话 H1 已把 `RULE_REF_CHECK` 默认开（`policy_refs ⊆ knowledge 真实 rule_id`）。新流程里**评分项标准来自招标文件、无 knowledge rule_id**：
   - **方案 A（推荐，且更正确）**：`policy_refs` 只引**授权法规**（如 `tender_evalmethod_003`「需量化因素及权重应在招标文件中明确规定」——它正是项目自定评分的法定依据）；具体评分项标准与命中走 `evidence_chain`（引招标文件第三章页 + 投标文件页）。这样 `approved/rejected` 仍有真实 `policy_ref`，过得了真伪闸。
   - 方案 B（不取）：放宽真伪闸接受会话 criteria 伪 rule_id——侵蚀 H1 的反幻觉价值。
   - **S3/S4 提示词必须明确**：承重结论的 `policy_refs` 来自通则层 `rule_id`，criteria 项命中写进 `evidence_chain`，否则真伪闸会拒。

## 影响范围

- `.claude/CLAUDE.md` — tender 段：删"项目层 `{招标编号}.rules.json` 预建 / `/init-rules` 生成 / 缺失 rule_gap"，改为"通则层法规 + 招标文件第三章直读出会话评分标准"。
- `.claude/commands/tender-evaluate.md` — **S1 重写**（读招标文件第三章→criteria→`extracted_data.criteria`）；**翻护栏**；S3 对照 criteria 评分、`policy_refs` 走通则层 + criteria 走 evidence_chain；usage 示例。
- `.claude/contracts/tender/criteria.schema.json` — **新增**：会话评分标准结构（见下）；并在 `audit-result` 的 `extracted_data` 允许 `criteria`（或仅文档约束，按现 schema 宽松度定）。
- `.claude/agents/tender/evaluator.md` / `extractor.md` — 清 `statute` 死引用（`statute.rules.json` / `tender_statute_*` 已不存在）+ 对齐新流程。
- `.claude/skills/tender-eval/SKILL.md` — 清 `statute` + 两层改"通则层(法规)+会话标准(招标文件)"。
- `.claude/skills/system/rule-init/SKILL.md` — 去掉 tender "项目层=招标编号→`{编号}.rules.json`"那条（`/init-rules` 对 tender 只剩通则层/法规）。
- （可选）server：若取"显式 criteria.json"备选，给 tender 命令加 `Write` + 路径白名单；v1 不动 server。
- 测试：tender 命令产出 criteria + 按 criteria 评分 + 缺招标文件→manual_review 兜底；全量绿 / validate-assets ok。

### criteria.schema.json 草拟（会话评分标准）

```jsonc
{
  "source_ref": "招标文件第三章《评标办法》出处(文件+页)",
  "method": "综合评估法 | 经评审的最低投标价法 | 其他",
  "total_max": 100,
  "items": [
    {
      "item": "价格标",                 // 评分项名
      "max": 82,                        // 满分
      "scoring_rule": "按价格公式…",     // 该项怎么评(直引招标文件)
      "source_ref": "第三章 p.XX",       // 出处
      "tag": "scored | requires_live_event | requires_external_data | requires_cross_bid_comparison"
    }
  ]
}
```

## 风险与缓解

- **真伪闸冲突**（H1 RULE_REF_CHECK 默认开）：见方案 §4——`policy_refs` 走通则层法规、criteria 走 evidence_chain。**这是必须在 S3/S4 提示词里讲清的硬约束**，否则 tender 的 approved/rejected 会被真伪闸拒。
- **招标文件读不全/无第三章**：缺招标文件或解析不出评分办法 → `manual_review(rule_gap)`（兜底不变，只是"缺的对象"从预建文件变成招标文件本身）。
- **大招标文件上下文压力**：第三章直读 + 投标全读可能超窗 → 可走"S1 先抽 criteria 落 `extracted_data.criteria`、S2 按需读投标章节"的分段；超大时用 `Task` 拆（命令已支持按需 spawn `tender-extractor`）。
- **`.claude` 是生产 agent 系统提示词**：改 CLAUDE.md tender 段会进生产提示词，须 review（System 路径强制交叉审查）。

## 验收标准

- 给一袋只含招标文件 + 投标文件的目录，`/tender-evaluate` 能：① 从招标文件第三章产出 `extracted_data.criteria`（评分项+满分+出处）；② 按 criteria 逐项 `scoring{item,max,score,status,basis}`；③ 不可判定项 `score:null`（不判 0）；④ `policy_refs` 引通则层真实 `rule_id`、criteria 命中在 `evidence_chain`；⑤ 出 verdict + 每项丢/得分原因。
- 无招标文件 → `manual_review(rule_gap)` 兜底。
- `knowledge/tender/` 不再需要任何 `{招标编号}.rules.json`（项目层概念删除）；通则层两法规不动；`statute` 死引用清零。
- `uv run pytest -q` 全绿 + `ruff` clean + validate-assets ok。
- System 路径：交叉审查（reviewer + spec-compliance + evaluator）PASS 后 ship。

## 本会话已完成（前置）

- 删除 `knowledge/tender/r2024007.rules.json`（预建项目层样例，gitignored）。validate-assets ok / 301 green。
- 确认无 tracked 代码/测试依赖该文件（`test_cli_tender_evaluate.py` 用的是 `cases/r2024007` 目录路径 + mock，非该规则文件）。

## 关联

- 用户大白话流程（2026-06-20 本会话，权威）。
- 现状梳理：本 sprint 调研 + `tender-evaluate.md` S0–S4 + `server/routes/tender_worker.py`（worker 调 `run_command_json("/tender-evaluate")`）。
- H1 真伪闸：`../2026-06-20-backend-hardening/`（RULE_REF_CHECK 默认开，本设计 §4 必对齐）。
