# S4 · 废标 gate / 一致性 / verdict 合成与结论表述（权威版）

> 由 `/tender-evaluate` S4 开头确定性 `Read`（一次）。决断总纲与"每袋投标是独立评审单元"
> 留在命令骨架，**废标 gate、一致性二分决断、verdict 合成、explanation / policy_refs /
> evidence_chain 口径以本文件为权威**。

## 废标 / 资格独立 gate（与逐项评分解耦）

- **废标/资格独立 gate（与逐项评分解耦，关键，治"全是不通过没扣分"）**：资格审查已按最高优先级输出 `eligibility_checks`；再对照 S1 的 `rejection_rules` 逐条核查投标文件，命中写 `extracted_data.disqualification_hits:[{rule_id 回链, finding, confirmed, evidence:{source, quote}}]`。**资格失败/废标只决定最终 `verdict`，绝不把各评分项 `scoring[]` 一律归 0/rejected**——投标人确实交了业绩/方案/团队/商务，就照各项 `score_mode` 逐项给分；把"项目名不符"等记入 `disqualification_hits` + 相关项 `basis`，而非抹掉逐项评分。
  - **`confirmed` 是废标决断的闸（关键，治"把读不清的疑似信号误判废标"）**：仅当废标事实**已确认**（底稿可读、逐字可核、语义明确，如确认逾期/确认投错项目/确认资质缺失）才写 `confirmed:true` → 触发 `rejected`。**疑似 / 读不清 / 扫描截图未还原 / 自相矛盾 / 须人工登官网核验**的信号一律 `confirmed:false`——它只进 `risk_score` + `eligibility_checks.status:manual` 提示人工，**绝不触发 rejected**。典型反例：信用中国查询截图 OCR 只读到页面标题（"…失信…名单"）却读不全查询结果、且投标人把它放在"未被列入"自证章节 → 常规理解是自证清白，**`confirmed:false`**，不得据此废标合规投标人。
  - **废标/扣分相关证据读不清 → 先重识别再判**（落"读不清先重识别该页再判"）：判罚/扣分相关页若底稿读不清（扫描/印章/截图），**若评标环境提供 `ocr-page` 技能则先对该页重识别**（含 `--seal` 印章页）读清后再判；**重识别后仍不可读 → `confirmed:false` + 须人工核验**，绝不据读不清直接判废标或判 0（"读不清≠违规"，同"读不清≠没提供"）。

## 一致性核验

- 一致性核验（**二分决断，不给"或"**）：业绩的项目经理与拟派项目负责人比对——①两处逐字可核、**确认是不同的人**（姓名完全不同）→ 该业绩**直接不得分**（`score` 按无此业绩计，`status:"scored"`，`basis` 写「业绩项目经理 X 与拟派负责人 Y 不一致，该业绩不予认可」）；②仅**写法存疑同一人**（简繁/形近字/OCR 易混字，如 牛亚犇/生亚犇）→ 才 `manual_review`（`data_conflict`）。两种情形证据链都**同时引用业绩页与拟派负责人页**两处出处（依据：实施条例第40/42条）。确认不同人还标 manual 是把"已判定"当"没判定"。

## verdict 合成

- 合成最终 `verdict`：
  - `extracted_data.disqualification_hits` 含**至少一条 `confirmed:true`**（已确认废标事实），或任一 `eligibility_checks` status=fail → `rejected`（资格审查/废标否决由**最高优先级独立 gate** 决定，不依赖某个评分项判 0）。**全部 disqualification_hits 都是 `confirmed:false`（疑似/读不清），或资格审查只有 `manual` 缺口 → 不得 rejected**，转 manual_review 或正常打分 + 风险标注。
  - 存在任一 `manual_review` 评分项（且确属上"总纲"客观算不出类），或关键证据缺失/规则缺口/证据冲突 → `manual_review`（填 `manual_review_reason`）
  - 全部评分项已按 `score_mode` 给分（`scored`/档次/加分/通过）且无确认否决项 → `approved`

## 结论表述与依据（explanation / policy_refs / evidence_chain）

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
