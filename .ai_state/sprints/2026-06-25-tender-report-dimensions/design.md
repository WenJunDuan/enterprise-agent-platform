# Sprint Design — Tender Report Dimensions（修订版 v2）

> v1 由 codex 起草；v2 经审查修正：①维度改"派生"不新增 LLM 字段 ②折入已提交
> `84c1f53` 的跨域回归修复 ③明确技术主观分两家对比的落点与降级。本文件即 codex 实施 spec。

## 背景

用户给了一段外部评标提示词（资深政府评标专家口吻）作为**报告结构参考**，核心诉求是把评审报告的
表达顺序与分区讲清楚，固定为五段：

1. 资格性审查情况（表格：审查项 / 通过·不通过·待人工 / 页码依据）
2. 价格分（**独立板块**，展示计算过程，不混入商务客观分）
3. 商务客观分（表格逐项 + 页码依据 + 客观分小计）
4. 技术主观分（逐项初评建议 + 依据；多家时并排两家分数+理由+优劣差异）
5. 综合得分与推荐结论

现有系统已具备：资格审查优先（`eligibility_checks`）、逐项 `score_mode` 评分、废标与评分明细解耦、
服务端按 `scoring[]` 重算小结。本 Sprint 只吸收这段提示词的**报告结构**，不改判分规则。

## 铁律护栏（不可违反）

- **招标文件直读即权威**：外部提示词只定报告"结构与顺序"，**绝不**成为评分规则来源。规则永远以
  招标文件解析出的 `extracted_data.criteria` 为准。
- **不可判定项绝不判 0**：价格横比 / 外部信用 / 现场答辩 / 读不清 → `manual_review` + `score:null`。
- **展示层不改分**：Python / 前端只做"展示归类 + 文字兜底"，禁止改变任何 `score`。

## v2 相对 codex 初稿（v1）的三处修正

1. **维度改为"派生"，不新增 LLM 标注字段**。v1 想在 `criteria.items[]` 加 `review_dimension`
   三枚举由模型标注——这会与既有 `evaluator_type`(objective/subjective/mixed) + `tag` + `score_mode`
   形成**第三套可自相矛盾的轴**（出现 `evaluator_type=objective` 却 `review_dimension=technical_subjective`）。
   改为从**已有结构化字段确定性派生**，零判分影响、不动 schema。
2. **折入 `84c1f53` 的跨域回归修复**（见 D0）。该 commit 的 `_finalize_user_explanation` 外溢污染了
   expense 结论文案，且与本 Sprint 的"报告综合意见"同处 `output_contracts.py`，须一并修。
3. **明确技术主观分两家对比的落点**：放 compare（多家）视图，按各投标人各自 `scoring[item].basis`
   并排；数据不足时降级"列各家主观分 + 各自依据"，不臆造定性比较结论。

## 维度派生规则（单一真相 · 禁止新增 LLM 字段）

对每个 `extracted_data.scoring[]` 项（join 同名 `criteria.items[]` 取 `evaluator_type/score_mode/tag`），
按**结构化字段优先**确定展示维度 `review_dimension ∈ {price, business_objective, technical_subjective}`：

| 优先级 | 判据 | 维度 |
|---|---|---|
| 1 | `tag == requires_cross_bid_comparison` 或 `score_mode == formula` | `price` |
| 2 | `evaluator_type ∈ {subjective, mixed}` | `technical_subjective` |
| 3 | 其余（objective 可量化：deduction/banded/additive/pass_fail + objective） | `business_objective` |
| 兜底 | 旧数据缺 `evaluator_type/score_mode`：名称命中「价格/报价/投标报价/最高限价」→ price；否则 business_objective | — |

- **价格优先用结构化信号**（`tag`/`score_mode`），名称关键词仅作旧数据兜底（名称匹配脆弱）。
- 资格审查（`eligibility_checks`）**天然是第 1 段**，不参与上述三分。
- **派生位置：前端展示层**（`agent-front/.../tender-review/model.ts`）。纯展示归类，**不动**
  `criteria.schema.json` / `extract-result.schema.json` / 后端判分。

## 设计方案（实施顺序：D0 → D5）

### D0（最高优先）修复 `output_contracts` 跨域回归

- **现状（已实证）**：`enrich_audit_decision` 对所有 dict 调 `_finalize_user_explanation`
  （[server/common/output_contracts.py:273](../../server/common/output_contracts.py)），expense
  （`routes/audit.py:195`）与 tender 共用。其中：
  - `_strip_existing_score_summary` 的正则 `综上[，,].*?(?:合计|总分).*?(?:。|$)`
    （:292）会删掉 expense 合法结论。实证：
    `"…金额在预算内。综上，本次差旅报销合计 1200 元，符合制度规定，予以通过。"`
    → 被截成 `"…金额在预算内"`（连「予以通过」一起丢）。
  - `_sanitize_explanation_terms` 的兜底正则 `\b[a-z]+(?:_[a-z0-9]+)+\b → "相关字段"`
    （:302）会误伤合法标识（发票号 `fp_2026_0420`、文件名等）。
- **修复**：
  1. 把 `_finalize_user_explanation`（及其 `_strip_existing_score_summary` / `_score_summary` /
     得分小结拼接）**限定到 tender 结论**。判据：`extracted_data` 含 `scoring` 或
     `eligibility_checks`（二者皆 tender 专有）；非 tender 直接返回，**不动** `explanation`。
  2. 把 catch-all snake_case 正则改为**只替换 `_TECH_TERM_REPLACEMENTS` 已知内部字段名集合**，
     去掉通配替换（或将通配限制在确定的内部字段白名单内）。
- **回归测试**（`tests/`，新增）：
  - expense 结论含「综上…合计…。」**不被删改**；含下划线合法标识不被替换。
  - tender happy-path 小结仍由服务端正确重算（模型写错的总分被纠正）。
  - tender rejected（资格 fail）仍加「资格审查不通过，按废标处理」前缀并抑制小结。

### D1 维度派生函数 + 单测

- 在 `model.ts` 实现 `deriveReviewDimension(scoringItem, criteriaItem)`，按上表派生。
- 单测覆盖：price（formula / cross_bid / 名称兜底）、technical_subjective（subjective / mixed）、
  business_objective（objective deduction/banded/additive/pass_fail）、旧数据缺字段兜底。

### D2 前端报告五段式重构

- 报告明细区按**固定顺序**渲染五段：资格审查 → 价格分 → 商务客观分 → 技术主观分 → 综合结论。
- 资格审查段复用现有 `buildEligibilityChecks`（表：审查项 / 状态 / 页码依据）。
- 商务客观分段：表格逐项（项 / 满分 / 实得 / 页码依据），段尾出"客观分小计"。
- 兼容旧数据：无法派生维度时按最保守归 `business_objective`，报告不崩。
- 左侧评审导航可暂不大改；本 Sprint 聚焦明细/报告区分段。

### D3 价格分独立板块

- **单家**：价格项命中 `requires_cross_bid_comparison` / `score:null` → 板块显示
  「待全部投标报价一起计算 / 待补充」，并说明需要什么输入（**不显示为 0 分**）。
- **多家**：引用 compare 侧已算的价格分与公式计算过程（基准价/评标价/得分），**完整展示计算式**。
- 价格分**绝不**混进商务客观分表。

### D4 技术主观分两家对比（compare 视图）

- 多家评标完成后，对每个 `technical_subjective` 项，从各投标人各自 `AuditResult.extracted_data.scoring`
  取 `score` + `basis` + 页码，**并排展示**（前端已加载各家结果，无需后端改动）。
- "优劣差异"**只陈述分差 + 各家事实依据对照**，不臆造定性结论（保守原则）。
- **降级**：若 compare 未跑或个别家结果缺失 → 只列已有各家主观分 + 依据，差异分析标
  `manual_review`/backlog，不编造。
- 主观项一律标注「**初评建议，最终以评标委员会评分为准**」。

### D5 S4 prompt 微调（最小改动）

- `tender-evaluate.md` S4「综合意见口径」：可按 资格 / 价格 / 商务客观 / 技术主观 四类**分述**；
  但**不要求模型标 `review_dimension`**（维度由前端派生）。
- 强调主观项措辞为"初评建议"。其余 S0-S3 判分规则**不动**。

## 非目标

- 不引入新的政府采购法律判断来源。
- 不让 Python / 前端改变任何分数（只做展示归类与文字兜底）。
- **不新增** `criteria.schema.json` / `extract-result.schema.json` 字段（维度靠派生）。
- 不改多家价格横比总逻辑（价格分仍由 compare 侧统一算）。
- 不做 UI 大改版。

## 验收标准

- D0：expense 回归测试通过（结论不被误删/误替换）；tender happy-path / rejected 小结行为不变。
- D1：维度派生单测覆盖三类 + 旧数据兜底，全绿。
- D2/D3：报告五段顺序固定；价格分独立、不混入商务客观；单家价格显示"待横比"非 0。
- D4：多家时主观项并排两家分数+依据；缺数据降级不臆造。
- 兼容：旧结果（无 `evaluator_type`）仍可展示。
- 全绿门禁：`uv run pytest -q` 全过；`agent-front` 下 `bun test src/features/contract/tender-review/model.test.ts`
  全过；`uv run ruff check .` 与前端 lint/build 通过。

## 风险与处理

- 风险：维度派生靠名称匹配价格 → 脆弱。处理：**优先 `tag`/`score_mode` 结构化信号**，名称仅旧数据兜底。
- 风险：D0 限定条件误伤 tender。处理：判据用 tender 专有字段（`scoring`/`eligibility_checks`），并补
  tender happy-path 回归测试守住。
- 风险：单家价格分页面显示 0。处理：`price` 维度遵守现有 `score:null/manual_review`，显示"待横比/待补充"。
- 风险：主观项被误认为机器终局分。处理：统一标"初评建议，最终以评委会为准"。
- 风险：D4 缺 compare 数据。处理：降级只列各家主观分 + 依据，不编造差异结论。

## 实施与验收结论（2026-06-25，CC 接手 codex 卡死后完成）

D0–D6 全部完成（codex 跑出 D0–D5 edits 后收尾两次卡死、未 commit；CC 接手验证 + 补 D6）。

- **D0**：`_finalize_user_explanation` 限定 tender（判据 scoring/eligibility_checks），收窄兜底正则；
  补 expense/tender 回归测试。修复跨域删句 bug，实证消失。
- **D1–D5**（codex edits，CC 验证）：review_dimension 派生（不新增 LLM 字段）、报告分段、价格独立、
  主观初评建议、S4 综合意见四类口径 + 不要求模型标 review_dimension。
- **D6**（用户追加，CC 实现）：报告类目改为**按招标文件实际要素动态分栏**——criteria.items[] 加
  `category`（标书原文类目名）、S1 提示词抽 `category`、前端按真实类目动态分栏（资格审查恒首位、
  缺不显、多全显、旧数据回退推断）。资格审查另从 eligibility 误归 'tech' 修正为独立 'qual' 列。

**验收**：见 `runtime-verify.md`。门禁全绿（后端 727 / ruff / 前端 11 + build + lint）；真实 UI 评标
跑通（deepseek，用户确认「效果可以」）。**已知边界**：D6 真实类目需新评标才带 category。

**踩坑**：① codex headless 被 HTTP(S)_PROXY 挂起 streaming（见 compound trick）；② 本机 Claude Code
启动后端会继承 `ANTHROPIC_BASE_URL=api.anthropic.com`，须 `env -u` 清掉才不撞离线护栏。
