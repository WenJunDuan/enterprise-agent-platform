---
description: 评标：按招标文件评分标准对一袋投标文件评分与合规判定，一次性内联产出结论
allowed-tools: Read, Glob, Skill, Task
---

读取指定投标目录（含招标文件 + 投标文件各章节），**在当前会话内一次性完成评标并直接输出最终结论**。**若服务端已注入「OCR/直读底稿」**（确定性预处理文本，带 `【第N页】` 页锚点，并已按评标目的重点还原评分标准/扣分细则表格）**则优先使用它**；必要时再 `Read` 原文件（PDF/图片/文本均可）核验定位。

### 出处页号书写规则（硬性，页锚溯源）

底稿里页锚有两种坐标系，**出处必须照抄底稿里实际出现的那一种，不得互换、不得臆造**：

- `【第 N 页】`（原件直读/扫描）→ 出处写 `文件名 第N页`。
- `【转换稿第 M 页】`（文件头标注 `已转换为PDF识别, 页号为转换稿页号`；Office 文件转 PDF 后识别，
  **原文档页号不可知**）→ 出处写 `文件名 转换稿第M页`，并给该条 `evidence_chain` 条目加
  `"page_kind": "converted"`。**严禁**把转换稿页号写成 `第M页` 冒充原文档页。
- **该文件在底稿里根本没有页锚**（native word/excel 整份直读）→ 出处**只写文件名 + 章节/标题**，
  **不要编页号**；回查按文件级逐字原文判定，不写页号不扣分，编造页号反而会被标记不可核实。
- 文件头带 `[⚠页号存疑…]` 的文件：页号仅供参考，出处照写但结论里该页号会被标 `page_unverified`。

## 执行方式（单 agent 内联五步，少往返）

为把单次评标压进可控时延，**默认不 spawn 子 agent**，由你在本会话内连续完成 S0–S4。仅当投标章节特别多、单会话读不下时，才用 `Task` 把 S2 事实抽取按章节并行拆给子 agent，再合并。

### S0 立案清点
- 用**一次** `Glob` 列目录文件。按文件名/内容分类：招标文件、投标文件各章节、投标人标识。
- 形成文件清单（章节号 → 文件）。不要逐字深读，先建索引。

### S1 取本项目规则（资格审查 + 评分标准 → criteria）
- **定位线索与排除（这步错则全错）**：`Read .claude/skills/tender-eval/references/s1-locate-criteria.md`，按其中的定位优先级、关键排除与自检执行。
- 本项目的资格审查规则和评分标准**就在它自己的招标文件里**。`Read` 招标文件，**定位其中规定资格审查、初步评审、评标办法/评分标准的部分**——标题与章节因标书而异（可能在正文某章、评标须知、前附表或附录；招标编号、章节号、标题写法各家不同），**以本招标文件实际结构为准，不要预设固定在"第三章"或某个固定标题**。必要时先读目录 / 浏览章节标题来定位。把定位到的项目规则**直读解析**为本项目 `criteria`，对齐 `.claude/contracts/tender/criteria.schema.json`：
  - `source_ref`（评标办法在本招标文件的**实际出处**：文件 + 章节/标题 + 页）、`method`（综合评估法 / 经评审的最低投标价法 / 其他）、`total_max`（满分合计）
  - `eligibility_rules[]`：资格审查/资格评审/初步评审规则，逐条提取 `{id, check, requirement, evidence_required, stage, priority:"highest", external_data, source_quote, source_ref}`。**这是与评分 `items[]` 并列的招标项，最高优先级，S3 必须先运行；不计入 `total_max`，不混成扣分项。**如规则依赖信用中国、主体库、动态监管等外部结果，标 `external_data:true`；上下文未提供外部结果时后续只能 `manual`，不得直接判 `fail`。
  - `items[]`：每项除 `{item, max, scoring_rule 原文, source_ref, tag, category}` 外，**必须判定该项评分方式 `score_mode` 并按方式提取结构化细则**（对齐 criteria.schema）：
    - `deduction` 满分扣减 → `deductions[]`：逐条 `{condition 何情况扣, points 扣几分, unit(per_item/per_occurrence/per_percent), max_times 最多扣几次, max_deduct 封顶, source_quote 原文, source_ref}`。**这是"第一次读标书就把扣分项全摘出来"的落点**——招标文件列了几条扣分、每条扣几分/最多几次，逐条钉死，不留到 S3 临场猜。
    - `banded` 档次给分（如优10良7中4 等离散档，**不是从满分扣减**）→ `bands[]`：`{level, points, criteria 评定标准, source_quote}`。
    - `additive` 基础分+加分累计 → `base` + `awards[]`：`{condition, points, cap 封顶, source_quote}`（`max` 须为含加分封顶的最高分）。
    - `formula` 公式分（价格分等）→ 抽 `formula`（招标原文，**唯一权威**）**并归一化出机读 `formula_spec`**：`{expression 可读公式, variables[{name, source, value, unit, ref}], rounding(floor/round/ceil/none), cap}`（对齐 criteria.schema）。**每个变量标 `source`**：招标常量(限价/预算/系数)=`tender_constant`（**S1 当场填 value+ref**，限价表就在招标文件里）；本家报价分项=`bid_component`（S2 回填 value）；最低价/均价/投标人数=`cross_bid`；外部信用=`external_data`；现场系数=`live_event`。**tag 按 source 白名单派生（不是黑名单）**：变量**全部** ∈ {tender_constant, bid_component} 才 `tag:scored`、`score_mode:formula`（限价类单家可算）；**只要有一个** cross_bid/external_data/live_event/derived → `tag:requires_cross_bid_comparison`（或对应 manual tag），S3 不自动算。
      - **拆子项优先**（治"含一个横比子项就把可算分整体丢人工"）：复合价格行（如报价 30 分 = 非驻场 4 + 增量 3 + 营收单价 3 + 横比 20）→ 能拆成独立价格 items 就拆，每个限价子项一套自己的 `formula_spec`+`cap`；只把真正依群体量的子项留 `requires_cross_bid_comparison`。
      - **阶梯分段走 banded 不走 formula**：「报价≤限价90%得10分、90~95%得7分…」这类**离散档** → `score_mode:banded`+`bands[]`（档以百分比区间描述），不硬塞进 `expression`（单个表达式表达多段 if-else 不稳）。
      - **MVP 边界**：本轮只对「固定限价比例差 / 多固定限价分项求和」自动算；含群体/现场/外部/复杂政策折扣的，结构化变量后仍 `manual_review`，不假装自动算。
    - `pass_fail` 客观通过得满分否则 0。
    - `manual` **只留给书面上真判不了的**：评标办法明写须评委会现场合议、样品评审、演示打分**且无任何书面评定标准**的项。**主观描述档次项（方案完整性、总体概述质量等）不归 manual**——归 `banded`/`additive`，由 AI 依评标办法的档次描述直接评分（标 `evaluator_type:subjective`）。把"主观"当"不可判"是范畴错误：评标办法给了档次标准，书面材料就在手上，就能评。
    - `evaluator_type`：`objective`/`subjective`/`mixed`——主观档次项标 `subjective`（S3 **直接选档给确定分** + 事实依据，带 low_confidence 供人工复核排序；此标记只影响置信度标注，不改变"必须出分"）。
    - `category`：该评分项在评标办法里的**所属类目/章节原名**，照标书原文填（如 商务标 / 技术标 / 价格 / 信用 / 服务 / 综合 等）。**标书分几类就标几类，不要套死成固定三类**；同一类目的多项填同一 `category` 名，便于报告按标书实际要素动态分栏。资格审查类目走 `eligibility_rules[]`、不在 items 里重复。仅供展示分组，不影响判分。
    - **复合评分行 → 拆成多条 items**：招标文件一个评分行含多个**独立子规则**（如「基础响应分 + ▲加分」「驻场人员计分 + 资格证书计分」「质量体系 + 服务承诺 + 培训」）时，**拆成多条 criteria items**、各自取最贴切的 `score_mode`，各 item `max` 之和 = 原行满分（契约一项只允许一种 `score_mode`，**不要把扣减与加分混进同一项**）。例：「运营平台 24 分 = 三平台功能响应 18 分（deduction：每缺一功能点扣 0.5、单平台封顶 6）+ ▲检测报告佐证加 6 分（additive：每▲项 +0.5、封顶 6）」→ 拆成两条 items。
  - **废标/否决条款 → 顶层 `rejection_rules[]`**（不是评分项，也不是资格审查清单本身）：逐条提取 `{id, condition 何情况废标/否决, source_quote 招标文件原文, source_ref}`，供 S3 走**独立 gate** 判定，与逐项评分解耦。资格审查的具体检查项优先进 `eligibility_rules[]`，不要只塞进 `rejection_rules[]`。
  - `tag` 标"可判定性"（与 `score_mode` 正交）：可依投标文件判定 → `scored`；命中 `requires_live_event`（现场答辩）/ `requires_external_data`（外部信用）/ `requires_cross_bid_comparison`（价格横比）→ 留待 S3 走 `manual_review`。
  - **`max:null` 仅限人工未知满分项**：只有 `score_mode:"manual" && tag!="scored"` 可为 null；`scored/null` 或其他 score_mode/null 无效。manual/null 项计入评分项数量，但不参与满分、待核验分值或得分合计；整份 criteria 至少须有一个数值满分项。
- 这份 `criteria` 就是本次评标的**会话项目规则**，随结论持久化（落 data/）；S3 据它先跑资格审查、再逐项评分。criteria 须**逐字依招标文件资格审查/初步评审/评标办法原文**（资格检查项、评分项、满分、规则不增删改），确保同一招标在不同投标人评标时得到**一致的 criteria**——这是后续多家公平横向比较的前提。
- 同时 `Read` 通则层国家法规作**法律底座**（注意：**不是**项目评分标准，而是废标 / 资格 / 一致性 / 程序的法定依据，跨项目稳定）：
  - `knowledge/tender/evalmethod.rules.json`（《评标委员会和评标方法暂行规定》，发改委12号令）
  - `knowledge/tender/regulation.rules.json`（《招标投标法实施条例》）
  - 读取每个文件顶层 `source_path` / `source_version` 作追溯。
- （可选 · G2 类型化计划）把读取 / 评分计划以结构化节点写入 `extracted_data.plan`，满足 `.claude/contracts/common/plan.schema.json`（每节点 `{step, intent, reads, tools, produces, tag}`，tag ∈ sequential/parallel/external_data/manual_review）。平台会校验其形；便于审计与（未来）按 `parallel` 节点并行拆分。
- **护栏**：招标文件载明的资格审查规则和评分标准**直读即权威**——这是评标的法定方式（依据 `tender_evalmethod_001`：评标只依据招标文件规定的标准和方法；`tender_evalmethod_003`：综合评估法需量化的因素及权重应在招标文件中明确规定）。招标文件**没有写**的标准，不得用训练记忆或臆测补充。**缺招标文件、或招标文件里定位不到资格审查 / 初步评审 / 评标办法 / 评分标准** → 相关资格或评分项降级 `manual_review`（`rule_gap`），并写清缺什么。

### S2 事实抽取（先资格证明，再评分证据）
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
- **先运行资格审查（最高优先级）**：在任何评分 `scoring[]` 之前，先对照 `criteria.eligibility_rules[]` 逐条核查投标文件与已提供外部结果，写入 `extracted_data.eligibility_checks:[{rule_id, check, status:pass/fail/manual, basis, evidence}]`。
  - `pass`：投标文件/上下文中已有清晰证据满足该资格要求，`evidence.source` 写文件+第N页+章节，`evidence.quote` 摘底稿逐字原文。
  - `fail`：仅当底稿可读、证据明确、语义确定地不满足资格要求（如确认无有效资质、项目负责人资格不符、确认被列入不得投标情形）才可判失败。资格失败优先决定 `verdict=rejected`，但不得把后续评分项一律清零。
  - `manual`：外部数据未提供、截图/扫描件读不清、主体库/信用中国/动态监管需在线核验、材料疑似存在但无法确认时，标人工核验；不得据“上下文没给外部结果”直接判失败。
  - 若招标文件明显存在资格审查章节但 `criteria.eligibility_rules[]` 为空，说明 S1 漏抽，必须先回到 S1 补抽；不要让 Python 或服务端兜底猜规则。
  - **初步评审中的报价审查必须果断判**：是否超招标控制价/最高限价、投标函大小写金额是否一致、是否唯一报价——两侧数据都在招标文件与投标函里，**pass/fail 立判**，不得标 `manual`、更不得推给"待横比"（评标基准价才需要横比，报价有效性不需要）。
- 对照 S1 的 `criteria` 每一项，结合事实底稿（必要时按页锚点 `【第N页】` 回读原文）判定，写入 `extracted_data.scoring`，每项 `{item, max, score, status, score_mode, basis, …按 mode 的明细}`（`item`/`max`/`score_mode` 与 criteria 对应项一致）。**按该项 `score_mode` 判分**：
  - ⚠ **凡 `score:null` 的项，必须同时给 `pending_reason`（硬性，缺失或取值不在枚举内 → 整单契约失败）**：`cross_bid`（需全部投标报价一起横比，如价格分）/ `external_data`（需外部数据，如企业信用查询结果）/ `live_event`（需现场答辩、演示、样品评审）/ `evidence_unresolved`（材料疑似已提供但底稿读不清、未还原、未定位到）/ `manual_mode`（该项评分方式本身是主观人工项，`score_mode:manual`）/ `non_responsive`（投标实质性不响应、该维度无任何可评事实）。`score` 非 null 的项**不要**写该字段。选最贴切的一个，不要用 `evidence_unresolved` 兜住一切。
  - `deduction`（满分扣减）→ **逐条核对该项 `deductions`**：命中写一条 `deduction_hits`：`{deduction_id 回链, condition, points_each, times 命中次数, deducted 本条共扣, evidence:{source 文件+第N页+章节, quote 触发扣分的投标原文片段}}`，未命中不写。`score = max − Σdeducted`（≥0，完全满足=max）。**已识别的每个问题点都要落成一条 `deduction_hits` 并摘上下文 quote**，禁止笼统"扣X分"或只写"不通过"。
  - `banded`（档次给分，优10良7中4 等离散档）→ 依 `bands` 选档写 `selected_band:{level, points, reason}`，`score = 该档 points`。**档次分是离散给分，不要伪造扣分明细**（那个 7 分不是"扣 3 分"）。
    - **主观档次项（`evaluator_type=subjective`，如技术方案「完整/较完整/基本」、应急响应「完善/部分」）→ 同样直接选档给分，`status:"scored"`（用户拍板：AI 评定就出确定分，不畏首畏尾）**：`reason` 写清归此档的**事实依据**（页数/章节覆盖/要点命中，如「总体概述共 5 页未超限、覆盖全部要求要点，归最高档」），并带 low_confidence 供人工复核排序。**对应内容在投标文件里没有（底稿完整可读、已核对应章节范围确未提供）→ 直接归最低档或按规则判 0**，`reason` 写「未在投标文件找到对应内容（已核第N-M页范围）」——缺失就是扣分事实，不是待核验理由。**逐项禁止写「初评建议」「以评委会为准」这类免责套话**（整单说明末尾统一一句即可，见 S4）。
  - `additive`（基础分+加分）→ 逐条核对 `awards` 命中写 `award_hits:{award_id, condition, points_each, times, awarded, evidence:{source, quote}}`，`score = base + Σawarded`（≤max）。**additive 客观响应项（如「主要材料参数一览表」正偏离打分、证书/检测报告清单）属可依投标判定，必须逐条核对投标实际响应并给分，禁止因条目多/嫌麻烦就整项标 `manual_review`**——只有该项材料读不清 / 真缺（窄情形见下）才 manual。整项 punt 是把"可判定"误当"不可判定"，与"读不清判 0"同为范畴错误。
  - `formula`（公式分）→ **以 `formula_spec` 为准、按变量闭合性判（治 G5：限价类本可单家算，别全丢人工）**：
    - **有 `formula_spec` 且全变量闭合**（variables 全 ∈ {tender_constant, bid_component}、各 `value` 已由 S1/S2 填齐、各带 `ref`）→ **代入 `expression` 算分**：`status:"scored"`、`score` 写算得分（按 `rounding` 取整、`cap` 封顶、`min_score` 兜底）。**`basis` 必须逐步列出代入过程**让人工验算无需重算，如「限价 limit=300（招标第N页）、本家 bid=270（投标第M页）、(300−270)/300=10%、10%÷1%步长=10、floor 后得 10 分」。
    - **`tag:"requires_cross_bid_comparison"` 或 formula_spec 含任一不可闭合变量**（cross_bid/external_data/live_event/derived）→ `status:"manual_review"`、`score:null`，把本家 `bid_price={amount,currency}` 钉入 `extracted_data`，`basis` 写「含群体/外部/现场变量 X，单家算不了，已备本家数据待汇总」。
    - **缺 `formula_spec`、或 `formula` 与 `formula_spec` 语义不一致、或闭合变量缺 value/ref → 不得临场翻底稿心算**，一律 `status:"manual_review"`、`manual_review_reason:"insufficient_evidence"`、`score:null`，`basis` 写明缺什么（治"回退旧路径模型心算漂移"）。
    - **限价线 ≠ 评分公式**：招标只规定"超最高限价废标"的，那是废标线（走 disqualification gate），不是 formula 评分项。
    - **报价判断拆层（治"跟报价沾边就全待横比"，用户实测痛点）**：报价相关判断分两层，**只有第②层才 pending**：
      - ① **报价有效性——单标必判，果断出结论**：本家报价 vs 招标控制价/最高限价（两个数都在手：控制价是招标常量、报价在投标函）、大小写金额一致、分项合价算术核对、唯一报价。有效就明确判定并写依据，如「报价 382,924,141.18 元低于招标控制价 386,600,000 元，为**有效报价**（招标第N页控制价、投标第M页投标函）」；确认超控制价/大小写矛盾 → 按招标规定走废标 gate（`confirmed:true`）或判 0。**严禁把有效性判断卷进"待横比"**——它不含任何群体变量。
      - ② **价格分数值**（评标基准价 = 全部有效投标报价按方法一/方法二统一计算、最低价/均价偏差率等）→ 才是 `cross_bid` pending。且该项 `basis` **必须先写第①层已判定的结论**（「本家报价已核为有效报价，低于控制价」），再写「评标基准价待全部投标报价汇总后统一计算」——**待横比 ≠ 什么都没判**，有效性结论是本项已完成的判断，要让业务人员看见。
  - `pass_fail` → 满足得 `max` 否则 0；命中不可判定标签（`requires_live_event`/`requires_external_data`）或 `manual` → `score:null`+`manual_review`，**绝不判 0**。
  - **「否则不得分」客观项 → 判 0 前必须二分（治「附件读不清就误判 0」）**：招标文件大量「提供…扫描件，否则不得分 / 未提供不得分」，而业绩合同 / 软著证书 / 资格证书 / 毕业证书等多为**扫描盖章件**。判 0 前先分清：
    - (a) 底稿完整、**确认投标文件未提供**该材料 → 按规则 `score:0, status:scored`，`basis` 写「已核投标文件无 XX」；
    - (b) 材料**疑似已提供但底稿读不清 / 扫描件未还原 / 印章压字 / 截断 / 未定位到**（OCR 低置信）→ **不得按「否则不得分」判 0**，该项 `score:null, status:manual_review, manual_review_reason:insufficient_evidence`，`basis` 写「XX 疑似在第 N 页但底稿未清晰还原，需人工 / 多模态核验」。
    - **「读不清」≠「没提供」**；把未还原的扫描附件当「客观 0 分」是范畴错误（与「不可判定绝不判 0」同源）。服务端会确定性给出 `extracted_data.evidence_resolution.low_clarity_files`（OCR 低置信文件清单）——**凡判 0 的"未提供/缺失"，若其出处文件在该清单内，必降 `manual_review` 而非 0**（R3 兜底）。
  - **投标确认未满足某客观评分项（底稿完整可读）→ 默认判 0 分 `score:0, status:"scored"`，不要 manual_review（治"明明不对应却标待核查/待人工"，用户实测痛点）**：只要底稿完整、可读、已定位到该评分维度对应章节，而**确认投标未提供 / 未响应 / 不满足**该**客观**条件（非主观档次项、非现场/外部/横比类），就按规则判 `score:0, status:"scored"`，`basis` 写「已核投标第N页该维度，未满足 XX，故 0 分」；属**该评分项自身必交硬性材料缺失**的判 `status:"rejected"`（该项判 0）。**仅以下窄情形才 `manual_review` 不判 0**：(i) 材料疑似已提供但底稿读不清/未还原/印章压字/截断/未定位到（OCR 低置信，见上 (b)）；(ii) 投标根本投错项目、该评分维度在投标全文无任何可对应章节、**无从判断应否给分**（真不可判定）；(iii) 现场答辩 / 外部数据 / 横向比价 / `data_conflict` / `rule_gap`。**主观档次项不在此列**——它走 banded 直接选档给分（含缺失归最低档/判 0），见上。**把"确认不满足"误判 `manual_review`，与把"读不清"误判 0 分，同为范畴错误**——前者实得 0、后者待核验，别混。
  - `status:"rejected"`（该项判 0）**仅当该评分项自身必交材料缺失/硬性不符**；**不要因整单废标就把本项判 0**（见下解耦）。
- **废标/资格独立 gate（与逐项评分解耦，关键，治"全是不通过没扣分"）**：资格审查已按最高优先级输出 `eligibility_checks`；再对照 S1 的 `rejection_rules` 逐条核查投标文件，命中写 `extracted_data.disqualification_hits:[{rule_id 回链, finding, confirmed, evidence:{source, quote}}]`。**资格失败/废标只决定最终 `verdict`，绝不把各评分项 `scoring[]` 一律归 0/rejected**——投标人确实交了业绩/方案/团队/商务，就照各项 `score_mode` 逐项给分；把"项目名不符"等记入 `disqualification_hits` + 相关项 `basis`，而非抹掉逐项评分。
  - **`confirmed` 是废标决断的闸（关键，治"把读不清的疑似信号误判废标"）**：仅当废标事实**已确认**（底稿可读、逐字可核、语义明确，如确认逾期/确认投错项目/确认资质缺失）才写 `confirmed:true` → 触发 `rejected`。**疑似 / 读不清 / 扫描截图未还原 / 自相矛盾 / 须人工登官网核验**的信号一律 `confirmed:false`——它只进 `risk_score` + `eligibility_checks.status:manual` 提示人工，**绝不触发 rejected**。典型反例：信用中国查询截图 OCR 只读到页面标题（"…失信…名单"）却读不全查询结果、且投标人把它放在"未被列入"自证章节 → 常规理解是自证清白，**`confirmed:false`**，不得据此废标合规投标人。
  - **废标/扣分相关证据读不清 → 先重识别再判**（落"读不清先重识别该页再判"）：判罚/扣分相关页若底稿读不清（扫描/印章/截图），**若评标环境提供 `ocr-page` 技能则先对该页重识别**（含 `--seal` 印章页）读清后再判；**重识别后仍不可读 → `confirmed:false` + 须人工核验**，绝不据读不清直接判废标或判 0（"读不清≠违规"，同"读不清≠没提供"）。
- 一致性核验：若业绩的项目经理与拟派项目负责人不一致，该业绩项 `manual_review`/不得分，`manual_review_reason:"data_conflict"`，证据链**同时引用业绩页与拟派负责人页**两处出处（依据：实施条例第40/42条、业绩与拟派负责人应一致）。
- **证据定位准确性（硬要求，定位项必须 = 实际找到的）**：每条 `basis` / `evidence_chain` 的出处**只能引底稿里真实存在的页锚点 `【第N页】`**，且所引页**确实包含**你描述的内容——**严禁凭印象/猜测写页码**。⚠ **页码 N 必须取底稿中该原文正上方最近的 `【第N页】` 锚点数字（OCR 顺序页），不是投标文件正文里印刷的页码**——两者常因封面/目录/分册偏移而差几页，照搬印刷页号会被回查闸判 `page_mismatch`。写每条证据前自检一遍：「该原文/字段是否就在我所引的 `【第N页】`？」对不上就改到正确页或降为"未在底稿定位到"。出处统一写**「文件名 + 第N页 + 所在章节/标题」**（如「投标文件第6页《应答函》」「招标文件第79页 报价表」；**带文件名，便于跨多文件归属**），`finding`（及 `deduction_hits/award_hits/disqualification_hits.evidence.quote`）摘所引页的**逐字原文片段**（**照抄底稿原文、勿转述/勿改写/勿缩写**），使定位可核验、带上下文。
  - ⚠ **服务端有确定性回查闸**：会把你引的每条 `quote` 拿去本案底稿逐字核对——引的是**底稿里真实存在的逐字原文**才算核实；编造/严重转述会被标 `evidence_unresolved` 并把该评分项降为人工复核。故务必逐字照抄、引真实页。

### S4 汇总结论
- **决断优先、压低 manual（总纲）**：文档判得了的客观项**一律出分 / 给 verdict，不 punt**；`manual_review` **只留给客观算不出**的——单家价格横比 / 外部信用未配 / 现场答辩 / 读不清且重识别后仍未还原 / `data_conflict` / `rule_gap`。把"嫌麻烦/拿不准"的可判定项标 manual 是错误。
- **每袋投标是独立评审单元**：除 `cross_bid`/`external_data`/`live_event` 三类外部依赖的**数值本身**外，其余一切判断——报价有效性 vs 控制价、资格项、一致性、客观响应项、扣分命中——都必须在**本标书内**果断闭合出结论（给分 / 判 0 / pass / fail + 依据）。「待核验」不是安全垫：把单标可判项标成待核验，与误判同罪；pending 项也要把**其中已可判定的部分先判掉写进 basis**（如价格分项先判报价有效性），只留真正算不了的数值待外部输入。
- 合成最终 `verdict`：
  - `extracted_data.disqualification_hits` 含**至少一条 `confirmed:true`**（已确认废标事实），或任一 `eligibility_checks` status=fail → `rejected`（资格审查/废标否决由**最高优先级独立 gate** 决定，不依赖某个评分项判 0）。**全部 disqualification_hits 都是 `confirmed:false`（疑似/读不清），或资格审查只有 `manual` 缺口 → 不得 rejected**，转 manual_review 或正常打分 + 风险标注。
  - 存在任一 `manual_review` 评分项（且确属上"总纲"客观算不出类），或关键证据缺失/规则缺口/证据冲突 → `manual_review`（填 `manual_review_reason`）
  - 全部评分项已按 `score_mode` 给分（`scored`/档次/加分/通过）且无确认否决项 → `approved`
- **`verdict` 与 `scoring[]` 解耦**：`verdict` 是整单结论，`scoring[]` 是逐项满分扣减的明细。**即使 `verdict=rejected`（废标），`scoring[]` 仍应保留各项有扣有得的逐项打分**（让评审看到每项扣在哪、扣多少），并在 `explanation` 说明废标主因。不要因 `verdict=rejected` 就把逐项分清零。（满分/实得合计由前端从 `scoring[]` 汇总，无需本步另出汇总字段。）
- **综合意见口径**：`explanation` 可按「资格审查 / 价格分 / 商务客观分 / 技术主观分」四类分述：资格审查先说明是否通过及废标主因；价格分**先写报价有效性结论**（如「报价 X 元低于招标控制价 Y 元，为有效报价」），再说明分值是否需全部投标报价一起横比，需要时写“待全部投标报价一起计算”；商务客观分说明可量化项的得分、扣分与依据；技术主观分**同样直接报分数和归档依据**（页数/覆盖度/要点命中），不逐项加免责语；**整单说明末尾统一一句**「主观评分项为按评标办法档次标准的评定，评标委员会可复核调整」即可。若资格审查确认不通过（如无所需资质/证书/负责人资格），`explanation` 开头直接写「资格审查不通过，按废标处理」，并说明后续评分明细已继续逐项列示、但不参与有效投标排序；若资格审查通过，再写已有分数项合计与需补充信息后确认的项。不要因为废标就停止后续明细核对；该得分就得分，该不得分就不得分。**不要要求或输出 `review_dimension` 字段**，展示维度由前端按 `criteria.items[]` 既有结构化字段派生。
- **承重结论（`approved` / `rejected`）的 `policy_refs` 只引通则层真实 `rule_id`**（如 `tender_evalmethod_001` 评标依招标文件、`tender_evalmethod_003` / `tender_evalmethod_004` 综合评估法量化加权、`tender_evalmethod_005` / `tender_evalmethod_006` / `tender_evalmethod_008` 废标 / 资格否决）——这些才是平台真伪闸认可的法定依据。
- **`policy_refs` 不得为空（任何 verdict，含 `manual_review`）**：至少引 `tender_evalmethod_001`（评标依招标文件）+ `tender_evalmethod_003`（综合评估法量化加权）作法定底座——空 `policy_refs` 使结论无法回溯法律依据（审计硬伤）。但**只引实际据以判断的 rule_id**：未实际命中的废标条款（005/006/008）**不要**列进来凑数（虚引会误导）。
- **`criteria` 各评分项的具体标准与命中**（来自招标文件评标办法、无 knowledge `rule_id`）**写进 `evidence_chain`**（同时引招标文件评标办法出处页 + 投标文件页），**不要塞进 `policy_refs`**（会被真伪闸当编造 `rule_id` 拒掉）。
- **`evidence_chain` 不得留空数组、每项 `finding`/`conclusion` 都要填非空**：关键评分项（企业实力 / 业绩 / 负责人 / 技术 / 价格 / 信用）逐条进 `evidence_chain`——`source`=「文件名+第N页+章节」、`finding`=所引页**逐字原文片段**、`conclusion`=据此得出的评分/判定结论（如「业绩3项均≥2022年，得9/9」）。证据明细同时落在 `scoring[].award_hits/deduction_hits` 时，顶层 `evidence_chain` 仍须有对应条目（供审计回溯），不能只塞嵌套结构。
- **口头总分必须 = 结构化 `scoring[]` 非 null `score` 之和**：`explanation` 里若写汇总分，只能加 `status:scored` 的项；`score:null`（manual）项**不计入**口头总分，单独表述「该项已估算 X 分，待人工/横比确认」（治"explanation 说 64 但结构化只 43"的口径不一致）。
- **最后说明面向业务人员，不写内部术语**：`explanation` / `reasons` 禁止出现 `manual_review`、`score_mode`、`formula_spec`、`cross_bid`、`extracted_data`、`policy_refs`、`evidence_chain`、`verdict` 等内部字段名或英文技术词。改用业务表达，例如「需人工复核」「需要全部投标报价一起计算」「需要外部信用结果」「需要现场答辩记录」。
- **最后说明不要自行重复复杂加总**：逐项分数以 `extracted_data.scoring` 为准；若写小结，只写“已有分数项合计 X 分，另有 Y 分需补充信息后确认”，且必须逐项复核后再写。不要在小结里再次列一串手算式，避免与结构化分数不一致。
- 给出页级 `evidence_chain`、`risk_score`，并把逐项 `scoring` 与 `criteria` 一并留在 `extracted_data` 中。

## 输出契约

1. 最终结论必须符合 `.claude/contracts/common/audit-result.schema.json`。决策只用 `verdict`（`approved` / `rejected` / `manual_review`），不要输出 `result` / `conclusion`（服务端从 `verdict` 派生）。
2. `claim_id` 为**投标人稳定标识**（优先统一社会信用代码，次投标人名称），便于 server 按投标人追加 / 去重；并把**招标项目标识**写入 `extracted_data.tender_project_id`（优先招标编号，次项目名），供 server 按招标分组、横向比较。
3. `explanation` / `reasons` / `evidence_chain` 用中文，措辞平实、专业、克制（像评标/审计意见）：禁用夸张或口语词（硬伤、铁证、实锤等），定性留有余地（用"疑似/需人工核实"，证据不确凿不下终局结论）。
4. `manual_review` 时，`explanation` 必须写明哪些评分项不能自动判定、缺什么材料、哪条规则无法闭合，并填 `manual_review_reason`（只能取 `missing_approval` / `rule_gap` / `data_conflict` / `insufficient_evidence` / `budget_exceeded` / `invoice_invalid` / `pre_approval_mismatch` 之一最贴切者）。
5. `extracted_data.eligibility_checks` 为最高优先级资格审查结果，必须先于 `scoring` 产出；`extracted_data.scoring` 为逐评分项 `{item, max, score, status, score_mode, basis, pending_reason（仅 score=null 时必填）, …按 mode 的 deduction_hits/selected_band/award_hits}`。资格审查不计入合计，未判定评分项 `score:null` 不计入合计。废标/资格走 `extracted_data.disqualification_hits` / `eligibility_checks`（独立 gate，**不混入 scoring**）。并在文字中说明需要什么外部输入（现场记录/外部评价表/全部投标报价）。
6. 只返回一个 JSON 对象，直接符合 `audit-result` 契约；不要输出 Markdown、表格、前言或任何 JSON 之外的文字。
   - **整个回复必须是单个 JSON 对象**：**首字符是 `{`、末字符是 `}`**；分析/思考只能写在 `<think></think>` 内，`</think>` 之后只准有这一个 JSON 对象；**禁止任何英文散文、要点列表或 JSON 之外的解释性文字**（违反会致服务端解析失败、整单评标失败）。
   - **JSON 合法性（极重要，违反会致解析失败）**：字符串值内引用项目名 / 项目号 / 投标人 / 评分项时，**一律用中文引号「」或『』**，**严禁在字符串值里用半角双引号 `"`**（会提前闭合字符串、破坏 JSON）；确需则转义为 `\"`。例：写 `"未响应「华为南通」项目"`，不要写 `"未响应"华为南通"项目"`。
7. 评标只用本地规则与制度文件，不使用训练记忆中的规则，不编造缺失的规则、附件或评分依据。
8. 结论须钉入 `extracted_data.bidder_info`（投标单位名称以投标函/营业执照原文为准，附 `source_refs` 页锚，对齐 `.claude/contracts/tender/bidder-info.schema.json`）与 `extracted_data.tender_info`（招标底稿/已注入 criteria 上下文可得时，对齐 `.claude/contracts/tender/tender-info.schema.json`，取 `project_name`/`tender_no`/`tenderee` 等子集即可）。**识别不到的字段省略，不编造**（保守原则）。

## 单投标人边界与多投标人追加

- **本命令一次只评目录里的这一家投标人**（招标文件 + 该投标人投标文件）。**不要**尝试读取、比较其他投标人或既往评标结果——多投标人的横向比较、汇总、增量追加由上层 前端 / server 负责（每家一条结果存 data/，按招标项目分组；已出结果不重评）。
- 因此 `requires_cross_bid_comparison` 项（价格分、有效投标数等）本家单独无法判定，保持 `manual_review` + `score:null`（绝不判 0）；但须把**横比所需的本家数据钉入 `extracted_data.bid_price`**（`{amount, currency}`，本家投标报价金额 / 币种），并在该项 `basis` 写明"横比数据已具备（本家报价 X），待全部投标汇总后由上层统一计算"，让 server 后续能一次性横比。
- 当前为一次性内联评标，**默认不调度 `tender-reviewer`**；高风险 / 证据冲突在 `verdict` / `risk_score` / `explanation` 中如实标注，交人工处理。

参数: $ARGUMENTS
用法: /tender-evaluate data/tenders/r2024007
