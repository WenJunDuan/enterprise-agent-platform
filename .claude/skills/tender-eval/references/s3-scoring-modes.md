# S3 · 逐项评判与五种 score_mode 裁决细则（权威版）

> 由 `/tender-evaluate` S3 开头确定性 `Read`（一次）。资格审查与决断纪律留在命令骨架，
> **逐项怎么判分以本文件为权威**。证据/页锚书写细则见 S2 开头已读的 `evidence-citation.md`，
> 本文件不重复。

## 评分产出与 pending_reason 硬闸

- 对照 S1 的 `criteria` 每一项，结合事实底稿（必要时按页锚点 `【第N页】` 回读原文）判定，写入 `extracted_data.scoring`，每项 `{item, max, score, status, score_mode, basis, …按 mode 的明细}`（`item`/`max`/`score_mode` 与 criteria 对应项一致）。**按该项 `score_mode` 判分**：
  - ⚠ **凡 `score:null` 的项，必须同时给 `pending_reason`（硬性，缺失或取值不在枚举内 → 整单契约失败）**：六个合法取值与各自语义见下方速查表。`score` 非 null 的项**不要**写该字段。选最贴切的一个，不要用 `evidence_unresolved` 兜住一切。

`pending_reason` 取值速查（**权威定义 = `.claude/contracts/common/audit-result.schema.json`
的 `extracted_data.scoring.items.pending_reason` enum + description**，服务端按该 schema 校验；
下表仅为 S3 运行时速查，与 schema 冲突时以 schema 为准）：

| 取值 | 一句话语义 |
|---|---|
| `cross_bid` | 需全部投标报价一起横比（如评标基准价、价格分数值） |
| `external_data` | 需外部数据（企业信用查询结果、主体库、动态监管等） |
| `live_event` | 需现场环节（答辩、演示、样品评审） |
| `evidence_unresolved` | 材料疑似已提供但底稿读不清 / 未还原 / 未定位到 |
| `manual_mode` | 该项评分方式本身是主观人工项（`score_mode:manual`） |
| `non_responsive` | 投标实质性不响应，该维度无任何可评事实 |

## 按 score_mode 判分（五种方式的裁决细则）

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
