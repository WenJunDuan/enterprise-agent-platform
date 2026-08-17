---
description: 评标：按招标文件评分标准对一袋投标文件评分与合规判定，一次性内联产出结论
allowed-tools: Bash, Read, Glob
---

读取指定投标目录（含招标文件 + 投标文件各章节），**在当前会话内一次性完成评标并直接输出最终结论**。

**取材纪律（硬性）**：服务端注入的「OCR/直读底稿」（带 `【第N页】` 页锚点，已按评标目的重点还原评分/扣分表格）**就是本次评标的全部材料**，**禁止 `Glob` / `Read` 任何文件**。唯一例外：某页读不清时用 `ocr-page` 重识别（`uv run python .claude/skills/ocr-page/ocr.py <绝对路径> [--pages N 或 N-M] [--seal]`，须为本目录内真实文件，不拼 shell 运算符）。底稿被截断（`...[已省略…]...`）或材料未注入 → 相关项按**证据缺失**处理（A3），不要补读。

### 出处页号书写规则（硬性，页锚溯源）

底稿里页锚有两种坐标系，**出处必须照抄底稿里实际出现的那一种，不得互换、不得臆造**：

- `【第 N 页】`（原件直读/扫描）→ 出处写 `文件名 第N页`。
- `【转换稿第 M 页】`（文件头标注 `已转换为PDF识别, 页号为转换稿页号`；Office 文件转 PDF 后识别，
  **原文档页号不可知**）→ 出处写 `文件名 转换稿第M页`，并给该条 `evidence_chain` 条目加
  `"page_kind": "converted"`。**严禁**把转换稿页号写成 `第M页` 冒充原文档页。
- **该文件在底稿里根本没有页锚**（native word/excel 整份直读）→ 出处**只写文件名 + 章节/标题**，
  **不要编页号**；回查按文件级逐字原文判定，不写页号不扣分，编造页号反而会被标记不可核实。
- 文件头带 `[⚠页号存疑…]` 的文件：页号仅供参考，出处照写但结论里该页号会被标 `page_unverified`。

## 执行方式（单 agent 内联五步，不往返）

**默认不 spawn 子 agent**，由你在本会话内连续完成 S0–S4；材料已全部注入，其间不应有任何工具往返（`ocr-page` 除外）。

### S0 立案清点
- **不要 `Glob`**：文件清单直接从底稿的 `### 文件: <文件名>` 行读取。按文件名/内容分类：招标文件、投标文件各章节、投标人标识。
- 形成文件清单（章节号 → 文件）。不要逐字深读，先建索引。

### S1 取本项目规则（资格审查 + 评分标准 → criteria）
- **定位线索与排除（这步错则全错）**：先找资格/初步审查规则（常见标题：资格审查 / 资格性审查 / 资格评审 / 初步评审 / 符合性审查 / 响应性评审），再找评分表（常见列名：序号 / 评分点名称 / 评审标准 / 最高分 / 分值 / 权重；章节标题含开标、评标、评审、商务技术标、报价标也可能是来源，不限于《评标办法》字样）。**必须排除**中标后的考核方案 / 考核指标 / 季度·绩效·履约考核 / KPI 表——它们也列分值，误取会让整套 `criteria` 取错。**自检**：评分 `items[].max` 之和须等于 `total_max`（资格审查不参与合计），对不上即漏取或取错表，回底稿重新定位。
- 本项目的资格审查规则和评分标准**就在已注入的招标文件底稿里**。标题与章节因标书而异（正文某章 / 评标须知 / 前附表 / 附录皆有可能），**以本招标文件实际结构为准，不要预设"第三章"或某个固定标题**。把定位到的项目规则**直读解析**为本项目 `criteria`，对齐 `.claude/contracts/tender/criteria.schema.json`：
  - `source_ref`（评标办法在本招标文件的**实际出处**：文件 + 章节/标题 + 页）、`method`（综合评估法 / 经评审的最低投标价法 / 其他）、`total_max`（满分合计）
  - `eligibility_rules[]`：资格审查/资格评审/初步评审规则，逐条提取 `{id, check, requirement, evidence_required, stage, priority:"highest", external_data, source_quote, source_ref}`。**这是与评分 `items[]` 并列的招标项，最高优先级，S3 必须先运行；不计入 `total_max`，不混成扣分项。**如规则依赖信用中国、主体库、动态监管等外部结果，标 `external_data:true`；上下文未提供外部结果时后续只能 `manual`，不得直接判 `fail`。
  - `items[]`：每项除 `{item, max, scoring_rule 原文, source_ref, tag, category}` 外，**必须判定该项评分方式 `score_mode` 并按方式提取结构化细则**（对齐 criteria.schema）：
    - `deduction` 满分扣减 → `deductions[]`：逐条 `{condition 何情况扣, points 扣几分, unit(per_item/per_occurrence/per_percent), max_times 最多扣几次, max_deduct 封顶, source_quote 原文, source_ref}`。**这是"第一次读标书就把扣分项全摘出来"的落点**——招标文件列了几条扣分、每条扣几分/最多几次，逐条钉死，不留到 S3 临场猜。
    - `banded` 档次给分（如优10良7中4 等离散档，**不是从满分扣减**）→ `bands[]`：`{level, points, criteria 评定标准, source_quote}`。
    - `additive` 基础分+加分累计 → `base` + `awards[]`：`{condition, points, cap 封顶, source_quote}`（`max` 须为含加分封顶的最高分）。
    - `formula` 公式分（价格分等）→ 抽 `formula`（招标原文，**唯一权威**）**并归一化出机读 `formula_spec`**：`{expression 可读公式, variables[{name, source, value, unit, ref}], rounding(floor/round/ceil/none), cap}`（对齐 criteria.schema）。**每个变量标 `source`**：招标常量(限价/预算/系数)=`tender_constant`（**S1 当场填 value+ref**，限价表就在招标文件里）；本家报价分项=`bid_component`（S2 回填 value）；最低价/均价/投标人数=`cross_bid`；外部信用=`external_data`；现场系数=`live_event`。**tag 按 source 白名单派生（不是黑名单）**：变量**全部** ∈ {tender_constant, bid_component} 才 `tag:scored`、`score_mode:formula`（限价类单家可算）；**只要有一个** cross_bid/external_data/live_event/derived → `tag:requires_cross_bid_comparison`（或对应 manual tag），S3 不自动算。
      - **拆子项优先**：复合价格行（如报价 30 分 = 非驻场 4 + 增量 3 + 营收单价 3 + 横比 20）→ 能拆成独立价格 items 就拆，每个限价子项一套自己的 `formula_spec`+`cap`；只把真正依群体量的子项留 `requires_cross_bid_comparison`。
      - **阶梯分段走 banded 不走 formula**：「报价≤限价90%得10分、90~95%得7分…」这类**离散档** → `score_mode:banded`+`bands[]`（档以百分比区间描述），不硬塞进 `expression`（单个表达式表达多段 if-else 不稳）。
      - **MVP 边界**：本轮只对「固定限价比例差 / 多固定限价分项求和」自动算；含群体/现场/外部/复杂政策折扣的，结构化变量后仍 `manual_review`，不假装自动算。
    - `pass_fail` 客观通过得满分否则 0。
    - `manual` **只留给书面上真判不了的**：评标办法明写须评委会现场合议、样品评审、演示打分**且无任何书面评定标准**的项。**主观描述档次项（方案完整性、总体概述质量等）不归 manual**——归 `banded`/`additive`，由 AI 依评标办法的档次描述直接评分（标 `evaluator_type:subjective`）。把"主观"当"不可判"是范畴错误：评标办法给了档次标准，书面材料就在手上，就能评。
    - `evaluator_type`：`objective`/`subjective`/`mixed`——主观档次项标 `subjective`（S3 **直接选档给确定分** + 事实依据，带 low_confidence 供人工复核排序；此标记只影响置信度标注，不改变"必须出分"）。
    - `category`：该评分项在评标办法里的**所属类目/章节原名**，照标书原文填（如 商务标 / 技术标 / 价格 / 信用 / 服务 / 综合 等）。**标书分几类就标几类，不要套死成固定三类**；同一类目的多项填同一 `category` 名，便于报告按标书实际要素动态分栏。资格审查类目走 `eligibility_rules[]`、不在 items 里重复。仅供展示分组，不影响判分。
    - **复合评分行 → 拆成多条 items**：招标文件一个评分行含多个**独立子规则**（如「基础响应分 + ▲加分」「驻场人员计分 + 资格证书计分」「质量体系 + 服务承诺 + 培训」）时，**拆成多条 criteria items**、各自取最贴切的 `score_mode`，各 item `max` 之和 = 原行满分（契约一项只允许一种 `score_mode`，**不要把扣减与加分混进同一项**）。例：「运营平台 24 分 = 三平台功能响应 18 分（deduction：每缺一功能点扣 0.5、单平台封顶 6）+ ▲检测报告佐证加 6 分（additive：每▲项 +0.5、封顶 6）」→ 拆成两条 items。
  - **废标/否决条款 → 顶层 `rejection_rules[]`**（不是评分项，也不是资格审查清单本身）：逐条提取 `{id, condition 何情况废标/否决, source_quote 招标文件原文, source_ref}`，供 S3 走**独立 gate** 判定，与逐项评分解耦。资格审查的具体检查项优先进 `eligibility_rules[]`，不要只塞进 `rejection_rules[]`。**触发词兜底检索（防漏）**：在已注入的招标底稿内检索「无效标 / 无效投标 / 作无效 / 作废标 / 否则不得分 / 视为不响应 / 取消…资格」等触发词——强制承诺函等硬约束常藏在技术需求正文而非评标办法/格式章，逐条登记；要求提交承诺函的，`condition` 写明须有对应承诺函且内容点齐全（S3 据此逐条勾稽投标文件）。
  - `tag` 标"可判定性"（与 `score_mode` 正交）：可依投标文件判定 → `scored`；`requires_live_event` / `requires_external_data` / `requires_cross_bid_comparison` → 留待 S3 按决策表 A4 判。
  - **`max:null` 仅限人工未知满分项**：只有 `score_mode:"manual" && tag!="scored"` 可为 null；`scored/null` 或其他 score_mode/null 无效。manual/null 项计入评分项数量，但不参与满分、待核验分值或得分合计；整份 criteria 至少须有一个数值满分项。
- 这份 `criteria` 就是本次评标的**会话项目规则**，随结论持久化（落 data/）；S3 据它先跑资格审查、再逐项评分。criteria 须**逐字依招标文件资格审查/初步评审/评标办法原文**（资格检查项、评分项、满分、规则不增删改），确保同一招标在不同投标人评标时得到**一致的 criteria**——这是后续多家公平横向比较的前提。
- 通则层国家法规（《评标委员会和评标方法暂行规定》《招标投标法实施条例》）作**法律底座**——**已由服务端注入**在下方 `=== 通则层国家法规 ===` 节（**不是**项目评分标准，而是废标 / 资格 / 一致性 / 程序的法定依据，跨项目稳定）。**不要再 Read 这些文件**；追溯直接引各文件顶层 `source_path` / `source_version`。
- （可选 · G2 类型化计划）把读取 / 评分计划以结构化节点写入 `extracted_data.plan`，满足 `.claude/contracts/common/plan.schema.json`（每节点 `{step, intent, reads, tools, produces, tag}`，tag ∈ sequential/parallel/external_data/manual_review）。平台会校验其形；便于审计与（未来）按 `parallel` 节点并行拆分。
- **护栏**：招标文件载明的资格审查规则和评分标准**直读即权威**——这是评标的法定方式（依据 `tender_evalmethod_001`：评标只依据招标文件规定的标准和方法；`tender_evalmethod_003`：综合评估法需量化的因素及权重应在招标文件中明确规定）。招标文件没写的标准不得补充；定位不到时按决策表 A1 降级。

### S2 事实抽取（先资格证明，再评分证据）
- 按 `extracted_data.criteria` 的 `eligibility_rules[]` 与各评分项所需证据，从底稿逐项定位相关投标章节，抽取评标所需事实，对齐 `.claude/contracts/tender/extract-result.schema.json`。**顺序：先资格审查证明（主体资格 / 资质证书 / 项目负责人资格 / 信用承诺 / 主体库材料），再取评分项所需的业绩、技术、报价等材料。**
  - 投标人、统一社会信用代码、法定代表人。**投标单位案卷头**（`bidder_name`/`credit_code`/`source_refs`）以投标函/营业执照原文为准，钉入 `extracted_data.bidder_info`（对齐 `.claude/contracts/tender/bidder-info.schema.json`），识别不到的字段省略，不编造。
  - 拟派项目负责人：姓名 / 注册证号 / 出处（文件+页）
  - 业绩：每条 `项目名称 / 项目经理 / 出处（文件+页）`
  - 投标报价（**钉入 `extracted_data.bid_price` = `{amount: 数值, currency: "CNY"}`**，供后续多家价格横比统一收集）、章节-页码索引
  - 资格审查证据：按 `eligibility_rules[]` 逐条抽取对应材料出处，如营业执照、资质证书、安全生产许可证、项目负责人证书、劳动合同/社保证明、信用承诺/信用查询截图、主体库/动态监管要求等。依赖外部系统且投标文件未提供外部结果时，记为“需外部核验”，不要推断通过或失败。
  - **限价类 formula 项的本家分项报价回填**（G5）：对 S1 标了 `tag:scored`+`score_mode:formula` 的项，从投标文件抽其 `formula_spec.variables` 里 `source:bid_component` 对应的本家报价（如非驻场运维单价、增量单价），**回填该变量的 `value`+`ref`（投标文件第N页）**，让 S3 代入算分；抽不到则留 `value:null`（S3 据此降 `manual_review`，不臆造）。
- **跨文件交叉一致性核对**（高价值缺陷多出自跨文件矛盾，单文件逐项看不出来；以底稿在场材料为限，逐对核对，矛盾写进 `ambiguities` 与相关项 `basis`，判定仍走 S3 决策表）：
  - 制造商/品牌声明类文件（如中小企业声明函）所列制造商 ↔ 分项报价表品牌列：逐行找归属，出现无主品牌即覆盖缺口；声明称 A 制造而报价表品牌为 B → 二者必有一假；多家制造商的从业人数/营收等数值雷同 → 高风险线索；
  - 检测报告样品型号 ↔ 所投产品型号（逐字）；检测报告检测依据标准 ↔ 被证参数性质（安全类标准的报告证明不了功能/性能参数；错配且数据页未见目标参数实测值 → 该证明无效力）；
  - 人员证书姓名 ↔ 社保名单 ↔ 承诺函（须同一人）；证书注册/聘用单位、社保缴纳单位 ↔ 投标人名称；
  - 偏离表「响应情况」 ↔ 方案正文/产品参数描述（无自相矛盾）。
  - （开标一览表大小写金额、分项合价 ↔ 总价的勾稽属**报价有效性**，S3 立判，不在此重复。）
- 其余一致性线索同样写进 `ambiguities`，例如"拟派负责人姓名在不同文件写法不一致（牛亚犇/生亚犇）""所报业绩项目经理与拟派负责人疑似不一致"。
- 只抽事实，不在本步给分。

### S3 逐项评判

#### 判分仲裁决策表（**唯一裁决口径**，本文件其余各处与 skill / CLAUDE.md 只引用不复述）

每个评分项**按序**匹配下表，先命中先裁；A9 是默认归宿。

| # | 情形 | 裁决 |
|---|---|---|
| A1 | 缺招标文件 / 底稿里**定位不到**资格审查·初步评审·评标办法 / 通则层法规缺口 | `score:null` + `manual_review`(`rule_gap`)，写清缺什么；**不得用训练记忆或臆测补规则** |
| A2 | 判罚·扣分·资格相关页底稿读不清（扫描 / 印章 / 截图） | 先用 `ocr-page` **重识别**该页（印章页加 `--seal`）再裁；仍不可读 → 落 A3 |
| A3 | 材料**疑似已提供**但读不清 / 未还原 / **印章压字** / 截断 / 未定位到；或其出处文件在服务端 `extracted_data.evidence_resolution.low_clarity_files` 内 | `score:null` + `manual_review`(`insufficient_evidence`)，`basis` 写「XX 疑似在第N页但底稿未清晰还原，需人工/多模态核验」。**禁按「否则不得分」判 0** |
| A4 | 分值本身依赖群体/外部/现场：`requires_cross_bid_comparison`（价格分基准价）/ `requires_external_data`（企业信用等）/ `requires_live_event`（现场答辩·演示·样品）/ `score_mode:manual`（评标办法明写须评委会现场合议**且无任何书面评定标准**） | `score:null` + `manual_review`，**绝不判 0**；`basis` 写清需要什么外部输入，**并把本项已可判定的部分先判掉写进去** |
| A5 | 投标投错项目 / 该评分维度在投标全文无任何可对应章节，**无从判断**应否给分 | `score:null` + `manual_review`(`non_responsive`) |
| A6 | 业绩项目经理与拟派负责人两处逐字可核、**确认是不同的人**（姓名完全不同） | 该业绩**直接不得分**（`score` 按无此业绩计、`status:"scored"`），`basis` 写「业绩项目经理 X 与拟派负责人 Y 不一致，该业绩**不予认可**」 |
| A7 | 同上但仅**写法存疑同一人**（简繁 / 形近 / OCR 易混，如 牛亚犇/生亚犇） | `score:null` + `manual_review`(`data_conflict`) |
| A8 | 底稿完整可读、已定位到该维度对应章节，**确认**投标未提供 / 未响应 / 不满足（**客观**项） | `score:0` + `status:"scored"`，`basis` 写「**已核投标第N页该维度**，未满足 XX，故 0 分」；属该评分项**自身必交**硬性材料缺失的写 `status:"rejected"`（仍只该项判 0，**不因整单废标**清零） |
| A9 | **其余一切**可依本标书判定的项 | **果断出分**，按该项 `score_mode` 走下方各模式细则 |

- **manual 白名单 = A1 / A3 / A4 / A5 / A7，此外一律不得 manual**。「嫌麻烦 / 条目多 / 拿不准 / 这是主观题」都不在内：主观档次项走 A9 直接选档，条目多的客观 `additive` 必须逐条核对。
- **两类范畴错误（双向，都是硬伤）**：把 A3 判成 A8（「读不清」当「没提供」→ 冤枉投标人）；把 A8/A9 判成 A3/A4（「确认不满足」当「待核验」→ 把已判定当没判定）。前者实得 0、后者待核验，别混。
- A6 / A7 两种情形，证据链都须**同时引业绩页与拟派负责人页两处出处**（依据：实施条例**第40/42条**）。
- **`score:null` 必带 `pending_reason`**（硬性，缺失或取值越枚举 → 整单契约失败）：`cross_bid` / `external_data` / `live_event` / `evidence_unresolved`（材料疑似已提供但读不清、未还原、未定位到）/ `manual_mode` / `non_responsive`。选最贴切的一个，**不要用 `evidence_unresolved` 兜住一切**；`score` 非 null 的项**不要**写该字段。
- **报价有效性不进 pending**：本家报价 vs 招标**控制价**/最高限价、投标函**大小写**金额一致、分项合价算术核对、唯一报价——两侧数都在手，一律走 A9 立判（如「报价 382,924,141.18 元低于招标控制价 386,600,000 元，为**有效报价**」）；确认超控制价 / 大小写矛盾则走废标 gate 或判 0。只有**评标基准价**、最低价/均价偏差率这类群体数值才是 A4。
- **每袋投标是独立评审单元**：除 A4 的外部依赖**数值本身**外，一切判断（资格项、一致性、客观响应项、扣分命中）都必须在本标书内闭合出结论。「待核验」不是安全垫：把单标可判项标成待核验，与误判同罪。
- **废标 / 资格是独立 gate，不改逐项分**：资格失败 / 废标只决定整单 `verdict`，`scoring[]` 仍逐项有扣有得（与 `verdict` **解耦**，见 S4）。

#### 逐项判定

- **先运行资格审查（最高优先级）**：在任何评分 `scoring[]` 之前，先对照 `criteria.eligibility_rules[]` 逐条核查投标文件与已提供外部结果，写入 `extracted_data.eligibility_checks:[{rule_id, check, status:pass/fail/manual, basis, evidence}]`。
  - `pass`：投标文件/上下文中已有清晰证据满足该资格要求，`evidence.source` 写文件+第N页+章节，`evidence.quote` 摘底稿逐字原文。
  - `fail`：仅当底稿可读、证据明确、语义确定地不满足资格要求（如确认无有效资质、项目负责人资格不符、确认被列入不得投标情形）才可判失败。
  - `manual`：外部数据未提供、截图/扫描件读不清、主体库/信用中国/动态监管需在线核验、材料疑似存在但无法确认时，标人工核验；不得据“上下文没给外部结果”直接判失败。
  - 若招标文件明显存在资格审查章节但 `criteria.eligibility_rules[]` 为空，说明 S1 漏抽，必须先回到 S1 补抽；不要让 Python 或服务端兜底猜规则。
  - 初步评审里的报价审查按决策表**报价有效性**条走 A9 立判，不得标 `manual`。
- 对照 S1 的 `criteria` 每一项，结合事实底稿（必要时按页锚点 `【第N页】` 回读原文）判定，写入 `extracted_data.scoring`，每项 `{item, max, score, status, score_mode, basis, …按 mode 的明细}`（`item`/`max`/`score_mode` 与 criteria 对应项一致）。**先过决策表定判 0 / manual，命中 A9 再按该项 `score_mode` 出分**：
  - `deduction`（满分扣减）→ **逐条核对该项 `deductions`**：命中写一条 `deduction_hits`：`{deduction_id 回链, condition, points_each, times 命中次数, deducted 本条共扣, evidence:{source 文件+第N页+章节, quote 触发扣分的投标原文片段}}`，未命中不写。`score = max − Σdeducted`（≥0，完全满足=max）。**已识别的每个问题点都要落成一条 `deduction_hits` 并摘上下文 quote**，禁止笼统"扣X分"或只写"不通过"。
  - `banded`（档次给分，优10良7中4 等离散档）→ 依 `bands` 选档写 `selected_band:{level, points, reason}`，`score = 该档 points`。**档次分是离散给分，不要伪造扣分明细**（那个 7 分不是"扣 3 分"）。
    - **主观档次项（`evaluator_type=subjective`，如技术方案「完整/较完整/基本」、应急响应「完善/部分」）→ 同样直接选档给分，`status:"scored"`**：`reason` 写清归此档的**事实依据**（页数/章节覆盖/要点命中，如「总体概述共 5 页未超限、覆盖全部要求要点，归最高档」），并带 low_confidence 供人工复核排序。**对应内容确未提供（A8）→ 直接归最低档或按规则判 0**，`reason` 写「未在投标文件找到对应内容（已核第N-M页范围）」。**逐项禁止写「初评建议」「以评委会为准」这类免责套话**（整单说明末尾统一一句即可，见 S4）。
  - `additive`（基础分+加分）→ **逐条核对** `awards` 命中写 `award_hits:{award_id, condition, points_each, times, awarded, evidence:{source, quote}}`，`score = base + Σawarded`（≤max）。客观响应项（如「主要材料参数一览表」正偏离打分、证书/检测报告清单）属 A9，**条目再多也要逐条核对投标实际响应并给分**，整项 punt 成 `manual_review` 是把可判定误当不可判定。
  - `formula`（公式分）→ **以 `formula_spec` 为准、按变量闭合性判**（限价类本可单家算，别全丢人工）：
    - **有 `formula_spec` 且全变量闭合**（variables 全 ∈ {tender_constant, bid_component}、各 `value` 已由 S1/S2 填齐、各带 `ref`）→ **代入 `expression` 算分**：`status:"scored"`、`score` 写算得分（按 `rounding` 取整、`cap` 封顶、`min_score` 兜底）。**`basis` 必须逐步列出代入过程**让人工验算无需重算，如「限价 limit=300（招标第N页）、本家 bid=270（投标第M页）、(300−270)/300=10%、10%÷1%步长=10、floor 后得 10 分」。
    - **`tag:"requires_cross_bid_comparison"` 或 formula_spec 含任一不可闭合变量**（cross_bid/external_data/live_event/derived）→ `status:"manual_review"`、`score:null`，把本家 `bid_price={amount,currency}` 钉入 `extracted_data`，`basis` 写「含群体/外部/现场变量 X，单家算不了，已备本家数据待汇总」。
    - **缺 `formula_spec`、或 `formula` 与 `formula_spec` 语义不一致、或闭合变量缺 value/ref → 不得临场翻底稿心算**，一律 `status:"manual_review"`、`manual_review_reason:"insufficient_evidence"`、`score:null`，`basis` 写明缺什么。
    - **限价线 ≠ 评分公式**：招标只规定"超最高限价废标"的，那是废标线（走 disqualification gate），不是 formula 评分项。
    - 价格分项 `basis` **必须先写决策表的报价有效性结论**（「本家报价已核为有效报价，低于控制价」），再写「评标基准价待全部投标报价汇总后统一计算」——待横比 ≠ 什么都没判。
  - `pass_fail` → 满足得 `max`，否则按决策表（A8 判 0 / A3–A5 走 `manual_review`）。
- **证据效力核查（客观分通用，给分前过一遍）**：资质/人员证书有效期须覆盖投标截止日；业绩合同签订日期须在招标要求窗口内；招标要求盖章的截图/彩页核对**章的归属**（要求原厂公章的，投标人公章不算数，二者可能同时要求）；同一评分点的多本证书须归属同一人。效力**确认不成立**（如证书确认过期）按 A8/A9 计分；效力**存疑**（章模糊、关键字样读不清）走 A2 重识别 → 仍不可读落 A3。
- **废标/资格独立 gate**：资格审查已按最高优先级输出 `eligibility_checks`；再对照 S1 的 `rejection_rules` 逐条核查投标文件，命中写 `extracted_data.disqualification_hits:[{rule_id 回链, finding, confirmed, evidence:{source, quote}}]`。把"项目名不符"等记入 `disqualification_hits` + 相关项 `basis`，而非抹掉逐项评分。
  - **`confirmed` 是废标决断的闸**：仅当废标事实**已确认**（底稿可读、逐字可核、语义明确，如确认逾期/确认投错项目/确认资质缺失）才写 `confirmed:true` → 触发 `rejected`。**疑似 / 读不清 / 扫描截图未还原 / 自相矛盾 / 须人工登官网核验**的信号一律 `confirmed:false`——它只进 `risk_score` + `eligibility_checks.status:manual` 提示人工，**绝不触发 rejected**。典型反例：信用中国查询截图 OCR 只读到页面标题（"…失信…名单"）却读不全查询结果、且投标人把它放在"未被列入"自证章节 → 常规理解是**自证清白**，`confirmed:false`，不得据此废标合规投标人。另一类反例：**电子标项目**中投标函、开标一览表等文件可能由交易平台在线生成、不随导出文件袋——判「必交文件缺失」触发废标前，先看招标文件是否载明平台在线生成/系统填报机制；属此类的 `confirmed:false`、相关资格/符合项标 `manual`（写明「待核验平台生成机制」），但其承载的关键承诺（如投标有效期）须能在袋内其他材料找到落点，找不到仍记缺口。（读不清的判罚页先走 A2 重识别；重识别后仍不可读 → `confirmed:false`。）
- 一致性核验：业绩项目经理 vs 拟派项目负责人，按决策表 A6 / A7 二分决断，不给"或"。
- **证据定位准确性（硬要求，定位项必须 = 实际找到的）**：每条 `basis` / `evidence_chain` 的出处**只能引底稿里真实存在的页锚点 `【第N页】`**，且所引页**确实包含**你描述的内容——**严禁凭印象/猜测写页码**。⚠ **页码 N 必须取底稿中该原文正上方最近的 `【第N页】` 锚点数字（OCR 顺序页），不是投标文件正文里印刷的页码**——两者常因封面/目录/分册偏移而差几页，照搬印刷页号会被回查闸判 `page_mismatch`。写每条证据前自检一遍：「该原文/字段是否就在我所引的 `【第N页】`？」对不上就改到正确页或降为"未在底稿定位到"。出处统一写**「文件名 + 第N页 + 所在章节/标题」**（如「投标文件第6页《应答函》」「招标文件第79页 报价表」；**带文件名，便于跨多文件归属**），`finding`（及 `deduction_hits/award_hits/disqualification_hits.evidence.quote`）摘所引页的**逐字原文片段**（**照抄底稿原文、勿转述/勿改写/勿缩写**），使定位可核验、带上下文。
  - ⚠ **服务端有确定性回查闸**：会把你引的每条 `quote` 拿去本案底稿逐字核对——引的是**底稿里真实存在的逐字原文**才算核实；编造/严重转述会被标 `evidence_unresolved` 并把该评分项降为人工复核。故务必逐字照抄、引真实页。

### S4 汇总结论
- 逐项判 0 / manual 的口径以 S3 决策表为准，本步不再另立例外。
- 合成最终 `verdict`：
  - `extracted_data.disqualification_hits` 含**至少一条 `confirmed:true`**（已确认废标事实），或任一 `eligibility_checks` status=fail → `rejected`（由**最高优先级独立 gate** 决定，不依赖某个评分项判 0）。**全部 disqualification_hits 都是 `confirmed:false`（疑似/读不清），或资格审查只有 `manual` 缺口 → 不得 rejected**，转 manual_review 或正常打分 + 风险标注。
  - 存在任一 `manual_review` 评分项（且确在决策表 manual 白名单内），或关键证据缺失（投标报价 / 拟派项目负责人 / 业绩项目经理 / 资格证明）、规则缺口、多份材料互相冲突且无法唯一解释 → `manual_review`（填 `manual_review_reason`）
  - 全部评分项已按 `score_mode` 给分（`scored`/档次/加分/通过）且无确认否决项 → `approved`
- **`verdict` 与 `scoring[]` 解耦**：**即使 `verdict=rejected`（废标），`scoring[]` 仍保留各项有扣有得的逐项打分**（让评审看到每项扣在哪、扣多少），并在 `explanation` 说明废标主因，不因废标就把逐项分**清零**。（满分/实得合计由前端从 `scoring[]` 汇总，无需本步另出汇总字段。）
- **综合意见口径**：`explanation` 可按「资格审查 / 价格分 / 商务客观分 / 技术主观分」四类分述：资格审查先说明是否通过及废标主因；价格分**先写报价有效性结论**（如「报价 X 元低于招标控制价 Y 元，为有效报价」），再说明分值是否需全部投标报价一起横比，需要时写“待全部投标报价一起计算”；商务客观分说明可量化项的得分、扣分与依据；技术主观分**同样直接报分数和归档依据**（页数/覆盖度/要点命中），不逐项加免责语；**整单说明末尾统一一句**「主观评分项为按评标办法档次标准的评定，评标委员会可复核调整」即可。若资格审查确认不通过（如无所需资质/证书/负责人资格），`explanation` 开头直接写「资格审查不通过，按废标处理」，并说明后续评分明细已继续逐项列示、但不参与有效投标排序；若资格审查通过，再写已有分数项合计与需补充信息后确认的项。不要因为废标就停止后续明细核对；该得分就得分，该不得分就不得分。**不要要求或输出 `review_dimension` 字段**，展示维度由前端按 `criteria.items[]` 既有结构化字段派生。
- **承重结论（`approved` / `rejected`）的 `policy_refs` 只引通则层真实 `rule_id`**（如 `tender_evalmethod_001` 评标依招标文件、`tender_evalmethod_003` / `tender_evalmethod_004` 综合评估法量化加权、`tender_evalmethod_005` / `tender_evalmethod_006` / `tender_evalmethod_008` 废标 / 资格否决）——这些才是平台真伪闸认可的法定依据。
- **`policy_refs` 不得为空（任何 verdict，含 `manual_review`）**：至少引 `tender_evalmethod_001`（评标依招标文件）+ `tender_evalmethod_003`（综合评估法量化加权）作法定底座——空 `policy_refs` 使结论无法回溯法律依据（审计硬伤）。但**只引实际据以判断的 rule_id**：未实际命中的废标条款（005/006/008）**不要**列进来凑数（虚引会误导）。
- **`criteria` 各评分项的具体标准与命中**（来自招标文件评标办法、无 knowledge `rule_id`）**写进 `evidence_chain`**（同时引招标文件评标办法出处页 + 投标文件页），**不要塞进 `policy_refs`**（会被真伪闸当编造 `rule_id` 拒掉）。
- **`evidence_chain` 不得留空数组、每项 `finding`/`conclusion` 都要填非空**：关键评分项（企业实力 / 业绩 / 负责人 / 技术 / 价格 / 信用）逐条进 `evidence_chain`——`source`=「文件名+第N页+章节」、`finding`=所引页**逐字原文片段**、`conclusion`=据此得出的评分/判定结论（如「业绩3项均≥2022年，得9/9」）。证据明细同时落在 `scoring[].award_hits/deduction_hits` 时，顶层 `evidence_chain` 仍须有对应条目（供审计回溯），不能只塞嵌套结构。
- **口头总分必须 = 结构化 `scoring[]` 非 null `score` 之和**：`explanation` 里若写汇总分，只能加 `status:scored` 的项；`score:null`（manual）项**不计入**口头总分，单独表述「该项已估算 X 分，待人工/横比确认」。
- **最后说明面向业务人员，不写内部术语**：`explanation` / `reasons` 禁止出现 `manual_review`、`score_mode`、`formula_spec`、`cross_bid`、`extracted_data`、`policy_refs`、`evidence_chain`、`verdict` 等内部字段名或英文技术词。改用业务表达，例如「需人工复核」「需要全部投标报价一起计算」「需要外部信用结果」「需要现场答辩记录」。
- **最后说明不要自行重复复杂加总**：逐项分数以 `extracted_data.scoring` 为准；若写小结，只写“已有分数项合计 X 分，另有 Y 分需补充信息后确认”，且必须逐项复核后再写。不要在小结里再次列一串手算式，避免与结构化分数不一致。
- 给出页级 `evidence_chain`、`risk_score`，并把逐项 `scoring` 与 `criteria` 一并留在 `extracted_data` 中。

## 输出契约

1. 最终结论必须符合 `.claude/contracts/common/audit-result.schema.json`。决策只用 `verdict`（`approved` / `rejected` / `manual_review`），不要输出 `result` / `conclusion`（服务端从 `verdict` 派生）。
2. `claim_id` 为**投标人稳定标识**（优先统一社会信用代码，次投标人名称），便于 server 按投标人追加 / 去重；并把**招标项目标识**写入 `extracted_data.tender_project_id`（优先招标编号，次项目名），供 server 按招标分组、横向比较。
3. `explanation` / `reasons` / `evidence_chain` 用中文，措辞平实、专业、克制（像评标/审计意见）：禁用夸张或口语词（硬伤、铁证、实锤等）。**"留有余地"只适用于废标/资格否决与读不清场景**（证据不确凿不下废标终局结论，用"疑似/需人工核实"）；**评分项给分不留余地**——分数本身就是判定，该几分写几分、依据写实，不加"或许/可能/建议"软化。
4. `manual_review` 时，`explanation` 必须写明哪些评分项不能自动判定、缺什么材料、哪条规则无法闭合，并填 `manual_review_reason`（只能取 `missing_approval` / `rule_gap` / `data_conflict` / `insufficient_evidence` / `budget_exceeded` / `invoice_invalid` / `pre_approval_mismatch` 之一最贴切者）。
5. `extracted_data.eligibility_checks` 为最高优先级资格审查结果，必须先于 `scoring` 产出；`extracted_data.scoring` 为逐评分项 `{item, max, score, status, score_mode, basis, pending_reason（仅 score=null 时必填）, …按 mode 的 deduction_hits/selected_band/award_hits}`。资格审查不计入合计，未判定评分项 `score:null` 不计入合计。废标/资格走 `extracted_data.disqualification_hits` / `eligibility_checks`（独立 gate，**不混入 scoring**）。并在文字中说明需要什么外部输入（现场记录/外部评价表/全部投标报价）。
6. 只返回一个 JSON 对象，直接符合 `audit-result` 契约；不要输出 Markdown、表格、前言或任何 JSON 之外的文字。
   - **整个回复必须是单个 JSON 对象**：**首字符是 `{`、末字符是 `}`**；分析/思考只能写在 `<think></think>` 内，`</think>` 之后只准有这一个 JSON 对象；**禁止任何英文散文、要点列表或 JSON 之外的解释性文字**（违反会致服务端解析失败、整单评标失败）。
   - **JSON 合法性（极重要，违反会致解析失败）**：字符串值内引用项目名 / 项目号 / 投标人 / 评分项时，**一律用中文引号「」或『』**，**严禁在字符串值里用半角双引号 `"`**（会提前闭合字符串、破坏 JSON）；确需则转义为 `\"`。例：写 `"未响应「华为南通」项目"`，不要写 `"未响应"华为南通"项目"`。
7. 评标只用本地规则与制度文件，不使用训练记忆中的规则，不编造缺失的规则、附件或评分依据。
8. 结论须钉入 `extracted_data.bidder_info`（投标单位名称以投标函/营业执照原文为准，附 `source_refs` 页锚，对齐 `.claude/contracts/tender/bidder-info.schema.json`）与 `extracted_data.tender_info`（招标底稿/已注入 criteria 上下文可得时，对齐 `.claude/contracts/tender/tender-info.schema.json`，取 `project_name`/`tender_no`/`tenderee` 等子集即可）。**识别不到的字段省略，不编造**（保守原则）。

## 单投标人边界与多投标人追加

- **本命令一次只评目录里的这一家投标人**（招标文件 + 该投标人投标文件）。**不要**尝试读取、比较其他投标人或既往评标结果——多投标人的横向比较、汇总、增量追加由上层 前端 / server 负责（每家一条结果存 data/，按招标项目分组；已出结果不重评）。
- 因此 `requires_cross_bid_comparison` 项（价格分、有效投标数等）本家单独无法判定，按决策表 A4 处理；但须把**横比所需的本家数据钉入 `extracted_data.bid_price`**（`{amount, currency}`），并在该项 `basis` 写明"横比数据已具备（本家报价 X），待全部投标汇总后由上层统一计算"。
- 当前为一次性内联评标，**默认不调度 `tender-reviewer`**；高风险 / 证据冲突在 `verdict` / `risk_score` / `explanation` 中如实标注，交人工处理。

参数: $ARGUMENTS
用法: /tender-evaluate data/tenders/r2024007
