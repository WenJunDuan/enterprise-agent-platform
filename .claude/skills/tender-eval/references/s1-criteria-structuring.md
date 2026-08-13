# S1 · criteria 结构化提取细则（权威版）

> 由 `/tender-evaluate` S1 开头确定性 `Read`（与 `s1-locate-criteria.md` 一并读，各读一次）。
> 命令骨架只留 S1 的目标句与 `rule_gap` 硬门，**criteria 怎么提、字段怎么填以本文件为权威**。
> 本文件含 S1 必做的两个动作：① 直读招标文件解析 criteria；② 读通则层国家法规作法律底座。

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
