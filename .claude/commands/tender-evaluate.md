---
description: 评标：按招标文件评分标准对一袋投标文件评分与合规判定，一次性内联产出结论
allowed-tools: Read, Glob, Skill, Task
---

读取指定投标目录（含招标文件 + 投标文件各章节），**在当前会话内一次性完成评标并直接输出最终结论**。**若服务端已注入「OCR/直读底稿」**（确定性预处理文本，带 `【第N页】` 页锚点，并已按评标目的重点还原评分标准/扣分细则表格）**则优先使用它**；必要时再 `Read` 原文件（PDF/图片/文本均可）核验定位。

### 出处页号书写规则（硬性，页锚溯源）· 简版

- 出处**照抄底稿实际出现的坐标系，不得互换、不得臆造**：`【第 N 页】`→写 `文件名 第N页`；`【转换稿第 M 页】`→写 `文件名 转换稿第M页` 并给该条 `evidence_chain` 加 `"page_kind":"converted"`。
- 底稿里该文件**没有页锚**→只写文件名+章节，**不编页号**；`[⚠页号存疑…]` 文件的页号仅供参考、照写。
- 本节是简版，**完整规则以 `.claude/skills/tender-eval/references/evidence-citation.md` 为权威**（S2 开头读一次）。

## 执行方式（单 agent 内联五步，少往返）

为把单次评标压进可控时延，**默认不 spawn 子 agent**，由你在本会话内连续完成 S0–S4。仅当投标章节特别多、单会话读不下时，才用 `Task` 把 S2 事实抽取按章节并行拆给子 agent，再合并。

- **细则文件 `Read` 失败（部署缺陷）不得静默续判**：整单降 `manual_review`（`rule_gap`），`explanation` 写明「评分细则文件缺失，本单按骨架规则保守评定」。

### S0 立案清点
- 用**一次** `Glob` 列目录文件。按文件名/内容分类：招标文件、投标文件各章节、投标人标识。
- 形成文件清单（章节号 → 文件）。不要逐字深读，先建索引。

### S1 取本项目规则（资格审查 + 评分标准 → criteria）
- **定位线索与排除（这步错则全错）**：`Read .claude/skills/tender-eval/references/s1-locate-criteria.md`，按其中的定位优先级、关键排除与自检执行。
- **提取细则**：`Read .claude/skills/tender-eval/references/s1-criteria-structuring.md`（字段定义、通则层法规 Read、护栏），本步按其执行。
- 目标：直读招标文件的**资格审查/初步评审**与**评标办法**，解析为 `extracted_data.criteria`（`eligibility_rules[]`+评分 `items[]`+出处），对齐 `.claude/contracts/tender/criteria.schema.json`，随结论持久化为会话规则。
- **硬门**：招标文件没写的标准不得臆测补；缺招标文件 / 定位不到资格审查或评标办法 / 通则层缺失 → 相关项降 `manual_review`（`rule_gap`）并写清缺什么。

### S2 事实抽取（先资格证明，再评分证据）

- **先读证据书写细则（一次，S3/S4 沿用不重读）**：`Read .claude/skills/tender-eval/references/evidence-citation.md`。
- 按 `extracted_data.criteria` 的 `eligibility_rules[]` 与各评分项所需证据（及可选 `plan` 标注的"需读章节"），逐个/分批 `Read` 相关投标文件，抽取评标所需事实，对齐 `.claude/contracts/tender/extract-result.schema.json`。**读取优先级：先资格审查证明文件 / 主体资格 / 资质证书 / 项目负责人资格 / 信用承诺 / 主体库导入材料，再读评分项所需的业绩、技术、报价等材料。**
  - 投标人、统一社会信用代码、法定代表人。**投标单位案卷头**（`bidder_name`/`credit_code`/`source_refs`）以投标函/营业执照原文为准，钉入 `extracted_data.bidder_info`（对齐 `.claude/contracts/tender/bidder-info.schema.json`），识别不到的字段省略，不编造。
  - 拟派项目负责人：姓名 / 注册证号 / 出处（文件+页）
  - 业绩：每条 `项目名称 / 项目经理 / 出处（文件+页）`
  - 投标报价（**钉入 `extracted_data.bid_price` = `{amount: 数值, currency: "CNY"}`**，供后续多家价格横比统一收集）、章节-页码索引
  - 资格审查证据：按 `eligibility_rules[]` 逐条抽取对应材料出处，如营业执照、资质证书、安全生产许可证、项目负责人证书、劳动合同/社保证明、信用承诺/信用查询截图、主体库/动态监管要求等。依赖外部系统且投标文件未提供外部结果时，记为“需外部核验”，不要推断通过或失败。
  - **限价类 formula 项的本家分项报价回填**（G5）：对 S1 标了 `tag:scored`+`score_mode:formula` 的项，从投标文件抽其 `formula_spec.variables` 里 `source:bid_component` 对应的本家报价（如非驻场运维单价、增量单价），**回填该变量的 `value`+`ref`（投标文件第N页）**，让 S3 代入算分；抽不到则留 `value:null`（S3 据此降 `manual_review`，不臆造）。
- 一致性线索写进 `ambiguities`，例如"拟派负责人姓名在不同文件写法不一致（牛亚犇/生亚犇）""所报业绩项目经理与拟派负责人疑似不一致"。
- 只抽事实，不在本步给分。

### S3 逐项评判

- **先读判分细则（一次）**：`Read .claude/skills/tender-eval/references/s3-scoring-modes.md`（五种 `score_mode` 的裁决细则、`pending_reason` 取值速查、判 0 与 manual 的范畴边界）。证据书写按 S2 已读的 `evidence-citation.md`。
- **先运行资格审查（最高优先级）**：在任何评分 `scoring[]` 之前，先对照 `criteria.eligibility_rules[]` 逐条核查投标文件与已提供外部结果，写入 `extracted_data.eligibility_checks:[{rule_id, check, status:pass/fail/manual, basis, evidence}]`。
  - `pass`：投标文件/上下文中已有清晰证据满足该资格要求，`evidence.source` 写文件+第N页+章节，`evidence.quote` 摘底稿逐字原文。
  - `fail`：仅当底稿可读、证据明确、语义确定地不满足资格要求（如确认无有效资质、项目负责人资格不符、确认被列入不得投标情形）才可判失败。资格失败优先决定 `verdict=rejected`，但不得把后续评分项一律清零。
  - `manual`：外部数据未提供、截图/扫描件读不清、主体库/信用中国/动态监管需在线核验、材料疑似存在但无法确认时，标人工核验；不得据“上下文没给外部结果”直接判失败。
  - 若招标文件明显存在资格审查章节但 `criteria.eligibility_rules[]` 为空，说明 S1 漏抽，必须先回到 S1 补抽；不要让 Python 或服务端兜底猜规则。
  - **初步评审中的报价审查必须果断判**：是否超招标控制价/最高限价、投标函大小写金额是否一致、是否唯一报价——两侧数据都在招标文件与投标函里，**pass/fail 立判**，不得标 `manual`、更不得推给"待横比"（评标基准价才需要横比，报价有效性不需要）。
- 资格审查之后，对照 S1 的 `criteria` 逐项判分，写入 `extracted_data.scoring`（每项 `{item, max, score, status, score_mode, basis, …按 mode 的明细}`，`item`/`max`/`score_mode` 与 criteria 对应项一致）；**按该项 `score_mode` 判分的全部细则以 `s3-scoring-modes.md` 为准**。
- ⚠ **硬闸**：凡 `score:null` 的项**必须同时给 `pending_reason`**（缺失或取值不在枚举内 → 整单契约失败）；**取值与各值语义见 `.claude/contracts/common/audit-result.schema.json`**（服务端按该 schema 校验，选最贴切的一个）。`score` 非 null 的项不要写该字段。

### S4 汇总结论

- **先读汇总细则（一次）**：`Read .claude/skills/tender-eval/references/s4-verdict-summary.md`（废标 / 资格独立 gate 与 `confirmed` 闸、一致性二分决断、`verdict` 合成、`explanation` / `policy_refs` / `evidence_chain` 口径与口头总分一致性）——本步的判定与表述一律以该文件为准。
- **决断优先、压低 manual（总纲）**：文档判得了的客观项**一律出分 / 给 verdict，不 punt**；`manual_review` **只留给客观算不出**的——单家价格横比 / 外部信用未配 / 现场答辩 / 读不清且重识别后仍未还原 / `data_conflict` / `rule_gap`。把"嫌麻烦/拿不准"的可判定项标 manual 是错误。
- **每袋投标是独立评审单元**：除 `cross_bid`/`external_data`/`live_event` 三类外部依赖的**数值本身**外，其余一切判断——报价有效性 vs 控制价、资格项、一致性、客观响应项、扣分命中——都必须在**本标书内**果断闭合出结论（给分 / 判 0 / pass / fail + 依据）。「待核验」不是安全垫：把单标可判项标成待核验，与误判同罪；pending 项也要把**其中已可判定的部分先判掉写进 basis**（如价格分项先判报价有效性），只留真正算不了的数值待外部输入。
- 产出：`verdict`（三值）+ `explanation` / `reasons` + 页级 `evidence_chain` + `risk_score`，并把逐项 `scoring`、`eligibility_checks`、`disqualification_hits` 与 `criteria` 一并留在 `extracted_data`。**不要要求或输出 `review_dimension` 字段**（展示维度由前端按 `criteria.items[]` 既有结构化字段派生）。

## 输出契约

- **产出 JSON 前先读一次**：`Read .claude/skills/tender-eval/references/output-json.md`（`manual_review_reason` 枚举全文、`extracted_data` 字段契约对照、JSON 合法性细则）——下列 1-7 是核心硬门，细则以该文件为准。
1. 最终结论必须符合 `.claude/contracts/common/audit-result.schema.json`。决策只用 `verdict`（`approved` / `rejected` / `manual_review`），不要输出 `result` / `conclusion`（服务端从 `verdict` 派生）。
2. `claim_id` 为**投标人稳定标识**（优先统一社会信用代码，次投标人名称），便于 server 按投标人追加 / 去重；并把**招标项目标识**写入 `extracted_data.tender_project_id`（优先招标编号，次项目名），供 server 按招标分组、横向比较。
3. `explanation` / `reasons` / `evidence_chain` 用中文，措辞平实、专业、克制（像评标/审计意见）：禁用夸张或口语词（硬伤、铁证、实锤等）。**"留有余地"只适用于废标/资格否决与读不清场景**（证据不确凿不下废标终局结论，用"疑似/需人工核实"）；**评分项给分不留余地**——分数本身就是判定，该几分写几分、依据写实，不加"或许/可能/建议"软化。
4. `manual_review` 时必须填 `manual_review_reason`（**枚举全文见 `output-json.md`**），并在 `explanation` 写明哪些评分项不能自动判定、缺什么材料、哪条规则无法闭合。
5. `extracted_data` 须含 `eligibility_checks`（最高优先级，先于 `scoring` 产出）、`scoring`、废标走 `disqualification_hits`（独立 gate，**不混入 scoring**），以及 `bidder_info` / `tender_info` 案卷头——**各字段契约对照见 `output-json.md`**。
6. 只返回一个 JSON 对象，直接符合 `audit-result` 契约；不要输出 Markdown、表格、前言或任何 JSON 之外的文字。
7. 评标只用本地规则与制度文件，不使用训练记忆中的规则，不编造缺失的规则、附件或评分依据。

## 单投标人边界与多投标人追加

- **本命令一次只评目录里的这一家投标人**（招标文件 + 该投标人投标文件）。**不要**尝试读取、比较其他投标人或既往评标结果——多投标人的横向比较、汇总、增量追加由上层 前端 / server 负责（每家一条结果存 data/，按招标项目分组；已出结果不重评）。
- 因此 `requires_cross_bid_comparison` 项（价格分、有效投标数等）本家单独无法判定，保持 `manual_review` + `score:null`（绝不判 0）；但须把**横比所需的本家数据钉入 `extracted_data.bid_price`**（`{amount, currency}`，本家投标报价金额 / 币种），并在该项 `basis` 写明"横比数据已具备（本家报价 X），待全部投标汇总后由上层统一计算"，让 server 后续能一次性横比。
- 当前为一次性内联评标，**默认不调度 `tender-reviewer`**；高风险 / 证据冲突在 `verdict` / `risk_score` / `explanation` 中如实标注，交人工处理。

参数: $ARGUMENTS
用法: /tender-evaluate data/tenders/r2024007
