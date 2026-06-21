---
description: 评标：按招标文件评分标准对一袋投标文件评分与合规判定，一次性内联产出结论
allowed-tools: Read, Glob, Skill, Task
---

读取指定投标目录（含招标文件 + 投标文件各章节），**在当前会话内一次性完成评标并直接输出最终结论**。**若服务端已注入「OCR/直读底稿」**（确定性预处理文本，带 `【第N页】` 页锚点，并已按评标目的重点还原评分标准/扣分细则表格）**则优先使用它**；必要时再 `Read` 原文件（PDF/图片/文本均可）核验定位。

## 执行方式（单 agent 内联五步，少往返）

为把单次评标压进可控时延，**默认不 spawn 子 agent**，由你在本会话内连续完成 S0–S4。仅当投标章节特别多、单会话读不下时，才用 `Task` 把 S2 事实抽取按章节并行拆给子 agent，再合并。

### S0 立案清点
- 用**一次** `Glob` 列目录文件。按文件名/内容分类：招标文件、投标文件各章节、投标人标识。
- 形成文件清单（章节号 → 文件）。不要逐字深读，先建索引。

### S1 取本项目评分标准（定位招标文件里的评标办法 → criteria）
- 本项目的评分标准**就在它自己的招标文件里**（价格 X 分 / 技术 Y 分 / 信用 Z 分…全是项目专属）。`Read` 招标文件，**定位其中规定评分标准的部分**——它常以《评标办法》《评标标准》《评分办法》《评分细则》《评标方法》《评分标准》等为标题，**所在位置因标书而异**（可能在正文某章、评标须知、或附录；招标编号、章节号、标题写法各家不同），**以本招标文件实际结构为准，不要预设固定在"第三章"或某个固定标题**。必要时先读目录 / 浏览章节标题来定位。把定位到的评标办法**直读解析**为本项目评分标准，结构化写入 `extracted_data.criteria`，对齐 `.claude/contracts/tender/criteria.schema.json`：
  - `source_ref`（评标办法在本招标文件的**实际出处**：文件 + 章节/标题 + 页）、`method`（综合评估法 / 经评审的最低投标价法 / 其他）、`total_max`（满分合计）
  - `items[]`：每项除 `{item, max, scoring_rule 原文, source_ref, tag}` 外，**必须判定该项评分方式 `score_mode` 并按方式提取结构化细则**（对齐 criteria.schema v2）：
    - `deduction` 满分扣减 → `deductions[]`：逐条 `{condition 何情况扣, points 扣几分, unit(per_item/per_occurrence/per_percent), max_times 最多扣几次, max_deduct 封顶, source_quote 原文, source_ref}`。**这是"第一次读标书就把扣分项全摘出来"的落点**——招标文件列了几条扣分、每条扣几分/最多几次，逐条钉死，不留到 S3 临场猜。
    - `banded` 档次给分（如优10良7中4 等离散档，**不是从满分扣减**）→ `bands[]`：`{level, points, criteria 评定标准, source_quote}`。
    - `additive` 基础分+加分累计 → `base` + `awards[]`：`{condition, points, cap 封顶, source_quote}`（`max` 须为含加分封顶的最高分）。
    - `formula` 公式分（价格分等）→ `formula` 公式原文（通常 `tag:requires_cross_bid_comparison`）。
    - `pass_fail` 客观通过得满分否则 0 / `manual` 主观/现场/外部不可判定。
    - `evaluator_type`：`objective`/`subjective`/`mixed`——主观档次项标 `subjective`（S3 给建议分+依据，留低置信人工复核，不冒充客观分）。
  - **废标/资格条款 → 顶层 `rejection_rules[]`**（不是评分项！）：逐条提取 `{id, condition 何情况废标/资格不符, source_quote 招标文件原文, source_ref}`，供 S3 走**独立 gate** 判定，与逐项评分解耦。
  - `tag` 标"可判定性"（与 `score_mode` 正交）：可依投标文件判定 → `scored`；命中 `requires_live_event`（现场答辩）/ `requires_external_data`（外部信用）/ `requires_cross_bid_comparison`（价格横比）→ 留待 S3 走 `manual_review`。
- 这份 `criteria` 就是本次评标的**会话项目规则**，随结论持久化（落 data/）；S3 据它逐项评分。criteria 须**逐字依招标文件评标办法原文**（评分项 / 满分 / 规则不增删改），确保同一招标在不同投标人评标时得到**一致的 criteria**——这是后续多家公平横向比较的前提。
- 同时 `Read` 通则层国家法规作**法律底座**（注意：**不是**项目评分标准，而是废标 / 资格 / 一致性 / 程序的法定依据，跨项目稳定）：
  - `knowledge/tender/evalmethod.rules.json`（《评标委员会和评标方法暂行规定》，发改委12号令）
  - `knowledge/tender/regulation.rules.json`（《招标投标法实施条例》）
  - 读取每个文件顶层 `source_path` / `source_version` 作追溯。
- （可选 · G2 类型化计划）把读取 / 评分计划以结构化节点写入 `extracted_data.plan`，满足 `.claude/contracts/common/plan.schema.json`（每节点 `{step, intent, reads, tools, produces, tag}`，tag ∈ sequential/parallel/external_data/manual_review）。平台会校验其形；便于审计与（未来）按 `parallel` 节点并行拆分。
- **护栏**：招标文件载明的评分标准**直读即权威**——这是评标的法定方式（依据 `tender_evalmethod_001`：评标只依据招标文件规定的标准和方法；`tender_evalmethod_003`：综合评估法需量化的因素及权重应在招标文件中明确规定）。招标文件**没有写**的标准，不得用训练记忆或臆测补充。**缺招标文件、或招标文件里定位不到评标办法 / 评分标准** → 相关评分项降级 `manual_review`（`rule_gap`），并写清缺什么。

### S2 事实抽取（把大文件压成小底稿）
- 按 `extracted_data.criteria` 各评分项所需的证据（及可选 `plan` 标注的"需读章节"），逐个/分批 `Read` 相关投标文件，抽取评标所需事实，对齐 `.claude/contracts/tender/extract-result.schema.json`：
  - 投标人、统一社会信用代码、法定代表人
  - 拟派项目负责人：姓名 / 注册证号 / 出处（文件+页）
  - 业绩：每条 `项目名称 / 项目经理 / 出处（文件+页）`
  - 投标报价（**钉入 `extracted_data.bid_price` = `{amount: 数值, currency: "CNY"}`**，供后续多家价格横比统一收集）、章节-页码索引
- 一致性线索写进 `ambiguities`，例如"拟派负责人姓名在不同文件写法不一致（牛亚犇/生亚犇）""所报业绩项目经理与拟派负责人疑似不一致"。
- 只抽事实，不在本步给分。

### S3 逐项评判
- 对照 S1 的 `criteria` 每一项，结合事实底稿（必要时按页锚点 `【第N页】` 回读原文）判定，写入 `extracted_data.scoring`，每项 `{item, max, score, status, score_mode, basis, …按 mode 的明细}`（`item`/`max`/`score_mode` 与 criteria 对应项一致）。**按该项 `score_mode` 判分**：
  - `deduction`（满分扣减）→ **逐条核对该项 `deductions`**：命中写一条 `deduction_hits`：`{deduction_id 回链, condition, points_each, times 命中次数, deducted 本条共扣, evidence:{source 文件+第N页+章节, quote 触发扣分的投标原文片段}}`，未命中不写。`score = max − Σdeducted`（≥0，完全满足=max）。**已识别的每个问题点都要落成一条 `deduction_hits` 并摘上下文 quote**，禁止笼统"扣X分"或只写"不通过"。
  - `banded`（档次给分，优10良7中4 等离散档）→ 依 `bands` 选档写 `selected_band:{level, points, reason}`，`score = 该档 points`。**档次分是离散给分，不要伪造扣分明细**（那个 7 分不是"扣 3 分"）。
  - `additive`（基础分+加分）→ 逐条核对 `awards` 命中写 `award_hits:{award_id, condition, points_each, times, awarded, evidence:{source, quote}}`，`score = base + Σawarded`（≤max）。
  - `formula` / `tag:requires_cross_bid_comparison`（价格等需横比）→ `status:"manual_review"`、`score:null`，把本家 `bid_price={amount,currency}` 钉入 `extracted_data`，`basis` 写"横比数据已备，待全部投标汇总后统一算"。
  - `pass_fail` → 满足得 `max` 否则 0；命中不可判定标签（`requires_live_event`/`requires_external_data`）或 `manual` → `score:null`+`manual_review`，**绝不判 0**。
  - `status:"rejected"`（该项判 0）**仅当该评分项自身必交材料缺失/硬性不符**；**不要因整单废标就把本项判 0**（见下解耦）。
- **废标/资格独立 gate（与逐项评分解耦，关键，治"全是不通过没扣分"）**：对照 S1 的 `rejection_rules` 逐条核查投标文件，命中写 `extracted_data.disqualification_hits:[{rule_id 回链, finding, evidence:{source, quote}}]`；资格审查写 `extracted_data.eligibility_checks:[{check, status:pass/fail/manual, basis, evidence}]`。**废标/资格不符只决定最终 `verdict`，绝不把各评分项 `scoring[]` 一律归 0/rejected**——投标人确实交了业绩/方案/团队/商务，就照各项 `score_mode` 逐项给分；把"项目名不符"等记入 `disqualification_hits` + 相关项 `basis`，而非抹掉逐项评分。
- 一致性核验：若业绩的项目经理与拟派项目负责人不一致，该业绩项 `manual_review`/不得分，`manual_review_reason:"data_conflict"`，证据链**同时引用业绩页与拟派负责人页**两处出处（依据：实施条例第40/42条、业绩与拟派负责人应一致）。
- **证据定位准确性（硬要求，定位项必须 = 实际找到的）**：每条 `basis` / `evidence_chain` 的出处**只能引底稿里真实存在的页锚点 `【第N页】`**，且所引页**确实包含**你描述的内容——**严禁凭印象/猜测写页码**。写每条证据前自检一遍：「该原文/字段是否就在我所引的 `【第N页】`？」对不上就改到正确页或降为"未在底稿定位到"。出处尽量写成**「文件 + 第N页 + 所在章节/标题」**（如「投标文件第6页《应答函》」「招标文件第79页 报价表」），`finding` 摘所引页的**原文片段**，使定位可核验、带上下文。

### S4 汇总结论
- 合成最终 `verdict`：
  - `extracted_data.disqualification_hits` 非空，或任一 `eligibility_checks` status=fail → `rejected`（废标/资格否决由**独立 gate** 决定，不依赖某个评分项判 0）
  - 存在任一 `manual_review` 评分项，或关键证据缺失/规则缺口/证据冲突 → `manual_review`（填 `manual_review_reason`）
  - 全部评分项已按 `score_mode` 给分（`scored`/档次/加分/通过）且无否决项 → `approved`
- **`verdict` 与 `scoring[]` 解耦**：`verdict` 是整单结论，`scoring[]` 是逐项满分扣减的明细。**即使 `verdict=rejected`（废标），`scoring[]` 仍应保留各项有扣有得的逐项打分**（让评审看到每项扣在哪、扣多少），并在 `explanation` 说明废标主因。不要因 `verdict=rejected` 就把逐项分清零。（满分/实得合计由前端从 `scoring[]` 汇总，无需本步另出汇总字段。）
- **承重结论（`approved` / `rejected`）的 `policy_refs` 只引通则层真实 `rule_id`**（如 `tender_evalmethod_001` 评标依招标文件、`tender_evalmethod_003` / `tender_evalmethod_004` 综合评估法量化加权、`tender_evalmethod_005` / `tender_evalmethod_006` / `tender_evalmethod_008` 废标 / 资格否决）——这些才是平台真伪闸认可的法定依据。
- **`criteria` 各评分项的具体标准与命中**（来自招标文件评标办法、无 knowledge `rule_id`）**写进 `evidence_chain`**（同时引招标文件评标办法出处页 + 投标文件页），**不要塞进 `policy_refs`**（会被真伪闸当编造 `rule_id` 拒掉）。
- 给出页级 `evidence_chain`、`risk_score`，并把逐项 `scoring` 与 `criteria` 一并留在 `extracted_data` 中。

## 输出契约

1. 最终结论必须符合 `.claude/contracts/common/audit-result.schema.json`。决策只用 `verdict`（`approved` / `rejected` / `manual_review`），不要输出 `result` / `conclusion`（服务端从 `verdict` 派生）。
2. `claim_id` 为**投标人稳定标识**（优先统一社会信用代码，次投标人名称），便于 server 按投标人追加 / 去重；并把**招标项目标识**写入 `extracted_data.tender_project_id`（优先招标编号，次项目名），供 server 按招标分组、横向比较。
3. `explanation` / `reasons` / `evidence_chain` 用中文，措辞平实、专业、克制（像评标/审计意见）：禁用夸张或口语词（硬伤、铁证、实锤等），定性留有余地（用"疑似/需人工核实"，证据不确凿不下终局结论）。
4. `manual_review` 时，`explanation` 必须写明哪些评分项不能自动判定、缺什么材料、哪条规则无法闭合，并填 `manual_review_reason`（只能取 `missing_approval` / `rule_gap` / `data_conflict` / `insufficient_evidence` / `budget_exceeded` / `invoice_invalid` / `pre_approval_mismatch` 之一最贴切者）。
5. `extracted_data.scoring` 为逐项 `{item, max, score, status, score_mode, basis, …按 mode 的 deduction_hits/selected_band/award_hits}`；未判定项 `score:null` 不计入合计。废标/资格走 `extracted_data.disqualification_hits` / `eligibility_checks`（独立 gate，**不混入 scoring**）。并在文字中说明需要什么外部输入（现场记录/外部评价表/全部投标报价）。
6. 只返回一个 JSON 对象，直接符合 `audit-result` 契约；不要输出 Markdown、表格、前言或任何 JSON 之外的文字。
   - **整个回复必须是单个 JSON 对象**：**首字符是 `{`、末字符是 `}`**；分析/思考只能写在 `<think></think>` 内，`</think>` 之后只准有这一个 JSON 对象；**禁止任何英文散文、要点列表或 JSON 之外的解释性文字**（违反会致服务端解析失败、整单评标失败）。
   - **JSON 合法性（极重要，违反会致解析失败）**：字符串值内引用项目名 / 项目号 / 投标人 / 评分项时，**一律用中文引号「」或『』**，**严禁在字符串值里用半角双引号 `"`**（会提前闭合字符串、破坏 JSON）；确需则转义为 `\"`。例：写 `"未响应「华为南通」项目"`，不要写 `"未响应"华为南通"项目"`。
7. 评标只用本地规则与制度文件，不使用训练记忆中的规则，不编造缺失的规则、附件或评分依据。

## 单投标人边界与多投标人追加

- **本命令一次只评目录里的这一家投标人**（招标文件 + 该投标人投标文件）。**不要**尝试读取、比较其他投标人或既往评标结果——多投标人的横向比较、汇总、增量追加由上层 前端 / server 负责（每家一条结果存 data/，按招标项目分组；已出结果不重评）。
- 因此 `requires_cross_bid_comparison` 项（价格分、有效投标数等）本家单独无法判定，保持 `manual_review` + `score:null`（绝不判 0）；但须把**横比所需的本家数据钉入 `extracted_data.bid_price`**（`{amount, currency}`，本家投标报价金额 / 币种），并在该项 `basis` 写明"横比数据已具备（本家报价 X），待全部投标汇总后由上层统一计算"，让 server 后续能一次性横比。
- 当前为一次性内联评标，**默认不调度 `tender-reviewer`**；高风险 / 证据冲突在 `verdict` / `risk_score` / `explanation` 中如实标注，交人工处理。

参数: $ARGUMENTS
用法: /tender-evaluate data/tenders/r2024007
