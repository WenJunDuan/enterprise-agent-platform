---
description: 评标：按招标文件评分标准对一袋投标文件评分与合规判定，一次性内联产出结论
allowed-tools: Read, Glob, Skill, Task
---

读取指定投标目录（含招标文件 + 投标文件各章节），**在当前会话内一次性完成评标并直接输出最终结论**。你直接 `Read` 文件（PDF/图片/文本均可），不依赖 OCR 预处理。

## 执行方式（单 agent 内联五步，少往返）

为把单次评标压进可控时延，**默认不 spawn 子 agent**，由你在本会话内连续完成 S0–S4。仅当投标章节特别多、单会话读不下时，才用 `Task` 把 S2 事实抽取按章节并行拆给子 agent，再合并。

### S0 立案清点
- 用**一次** `Glob` 列目录文件。按文件名/内容分类：招标文件、投标文件各章节、投标人标识。
- 形成文件清单（章节号 → 文件）。不要逐字深读，先建索引。

### S1 取本项目评分标准（定位招标文件里的评标办法 → criteria）
- 本项目的评分标准**就在它自己的招标文件里**（价格 X 分 / 技术 Y 分 / 信用 Z 分…全是项目专属）。`Read` 招标文件，**定位其中规定评分标准的部分**——它常以《评标办法》《评标标准》《评分办法》《评分细则》《评标方法》《评分标准》等为标题，**所在位置因标书而异**（可能在正文某章、评标须知、或附录；招标编号、章节号、标题写法各家不同），**以本招标文件实际结构为准，不要预设固定在"第三章"或某个固定标题**。必要时先读目录 / 浏览章节标题来定位。把定位到的评标办法**直读解析**为本项目评分标准，结构化写入 `extracted_data.criteria`，对齐 `.claude/contracts/tender/criteria.schema.json`：
  - `source_ref`（评标办法在本招标文件的**实际出处**：文件 + 章节/标题 + 页）、`method`（综合评估法 / 经评审的最低投标价法 / 其他）、`total_max`（满分合计）
  - `items[]`：每项 `{item 评分项名, max 满分, scoring_rule 评分规则原文/转述, source_ref 出处页, tag}`
  - `tag` 标"可判定性"：可依投标文件判定 → `scored`；命中 `requires_live_event`（现场答辩）/ `requires_external_data`（外部信用）/ `requires_cross_bid_comparison`（价格横比）→ 留待 S3 走 `manual_review`。
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
- 对照 S1 得到的 `extracted_data.criteria` 每一项（`item` / `max` / `scoring_rule` / `tag`），结合事实底稿（必要时按页码回读该章节原文）判定，写入 `extracted_data.scoring`，每项 `{item, max, score, status, basis}`（`item` / `max` 须与 criteria 对应项一致）：
  - 规则可依文档判定 → `status:"scored"`，给 `score` 与 `basis`
  - 命中"不可判定"标签 → `status:"manual_review"`、`score:null`，**绝不判 0**：
    - `requires_live_event`（项目负责人答辩等现场环节）
    - `requires_external_data`（企业信用等外部公示数据，不在投标文件内）
    - `requires_cross_bid_comparison`（价格分、有效投标数等需横向比较所有投标）
  - 命中废标 / 资格一票否决（未实质性响应、重大偏差、资格不符等）→ `status:"rejected"`
- 一致性核验：若业绩的项目经理与拟派项目负责人不一致，该业绩项 `manual_review`/不得分，`manual_review_reason:"data_conflict"`，证据链**同时引用业绩页与拟派负责人页**两处出处（依据：实施条例第40/42条、业绩与拟派负责人应一致）。

### S4 汇总结论
- 合成最终 `verdict`：
  - 命中任一废标/资格否决 → `rejected`
  - 存在任一 `manual_review` 评分项，或关键证据缺失/规则缺口/证据冲突 → `manual_review`（填 `manual_review_reason`）
  - 全部评分项 `scored` 且无否决项 → `approved`
- **承重结论（`approved` / `rejected`）的 `policy_refs` 只引通则层真实 `rule_id`**（如 `tender_evalmethod_001` 评标依招标文件、`tender_evalmethod_003` / `tender_evalmethod_004` 综合评估法量化加权、`tender_evalmethod_005` / `tender_evalmethod_006` / `tender_evalmethod_008` 废标 / 资格否决）——这些才是平台真伪闸认可的法定依据。
- **`criteria` 各评分项的具体标准与命中**（来自招标文件评标办法、无 knowledge `rule_id`）**写进 `evidence_chain`**（同时引招标文件评标办法出处页 + 投标文件页），**不要塞进 `policy_refs`**（会被真伪闸当编造 `rule_id` 拒掉）。
- 给出页级 `evidence_chain`、`risk_score`，并把逐项 `scoring` 与 `criteria` 一并留在 `extracted_data` 中。

## 输出契约

1. 最终结论必须符合 `.claude/contracts/common/audit-result.schema.json`。决策只用 `verdict`（`approved` / `rejected` / `manual_review`），不要输出 `result` / `conclusion`（服务端从 `verdict` 派生）。
2. `claim_id` 为**投标人稳定标识**（优先统一社会信用代码，次投标人名称），便于 server 按投标人追加 / 去重；并把**招标项目标识**写入 `extracted_data.tender_project_id`（优先招标编号，次项目名），供 server 按招标分组、横向比较。
3. `explanation` / `reasons` / `evidence_chain` 用中文，措辞平实、专业、克制（像评标/审计意见）：禁用夸张或口语词（硬伤、铁证、实锤等），定性留有余地（用"疑似/需人工核实"，证据不确凿不下终局结论）。
4. `manual_review` 时，`explanation` 必须写明哪些评分项不能自动判定、缺什么材料、哪条规则无法闭合，并填 `manual_review_reason`（只能取 `missing_approval` / `rule_gap` / `data_conflict` / `insufficient_evidence` / `budget_exceeded` / `invoice_invalid` / `pre_approval_mismatch` 之一最贴切者）。
5. `extracted_data.scoring` 为逐项 `{item, max, score, status, basis}`；未判定项 `score:null` 不计入合计，并在文字中说明需要什么外部输入（现场记录/外部评价表/全部投标报价）。
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
