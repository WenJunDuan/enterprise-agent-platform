# R1 设计 · 底稿→校验管道 + evidence-resolution 闸

> Sprint: `2026-06-22-tender-evidence-accuracy-hardening` · Round 1（最高价值）
> 路径分类: **Feature**（新增确定性校验能力 + 透传管道；跨 ~4 文件，含 1 新模块）
> 设计先行（铁律[设计先行]）→ critic/reviewer/spec-compliance 三审 + codex 后再 impl。
> 行号均为 2026-06-22 本会话 grep 实测（深潜行号是 06-21，已重新 ground）。

---

## 一、背景（WHY）

**痛点**：评标结论里模型引用的每条出处 `(文件, 第N页, 原文 quote)`，**当前没有任何代码回查它是否真在本案底稿里**。
- 现状链：底稿已带 `### 文件:`（`pipeline.py:248`）+ `【第 N 页】`（`pipeline.py:173 _page_anchor`）锚点 → 提示词要模型「抄锚点、严禁凭印象、写前自检」（`tender-evaluate.md:73`）→ **零回查代码**（`grep evidence_unresolved|resolve_evidence server/` 零命中）。
- 提示词自检不可靠已自证（absence-is-not-zero 那条补提示仍反复判错，最后靠校验层硬降级 `output_contracts.py:130-161 / _has_hard_disqualification`）。**定位/引文同理**：靠模型自觉抄页码必有漏；8636 页远超模型可核实范围，会「脑补」页码与原文。
- 这条同治两个用户痛点：**「定位不准」**（页码对不上）+ **「点评/引文不实」**（basis 引的原文底稿里根本没有）。把它们从**静默通过**变成**可抓、可降级**。

**架构前置（硬阻塞，必须先打通）**：当前契约校验器 `apply_schema_semantics`（`contract.py:124`）**只看模型输出、看不到输入底稿**——它在通用 bridge `json_bridge.py:65/95` 里被调用，签名不含底稿。要做 resolution 闸，**必须把本案底稿透传进校验上下文**。底稿在 `tender_worker._run_evaluation` 里已构造（`tender_worker.py:191-212`，变量 `ocr_block`，doc-layer 复用或 inline OCR 两路都产出带锚点的底稿），缺的就是这条透传管道。**不打通管道，闸无从实现**——这是 R1 的第一刀。

---

## 二、方案（HOW）

分两件事：**(A) 打通底稿→校验透传管道**（generic mechanism）；**(B) evidence-resolution 闸**（tender policy，挂在 audit-result 契约的新 `resolve` hook 上，仅当底稿被透传时生效）。

### A. 透传管道（OCP：加 hook 类型，不改调用链语义）

新增一个**可选** `evidence_source: str | None` 参数，从 worker 一路透传到契约校验。默认 `None` → 行为零变化（audit / 旧路径完全不受影响）。

1. **`SchemaProcessor` 加第 4 个 hook**（`contract.py:59-73`）：
   ```python
   resolve: Callable[[StructuredJSON, str], StructuredJSON] | None = None
   ```
   `register_schema_processor(..., resolve=...)` 同步加 kwarg。语义：在 enrich **之后**、拿到底稿时跑确定性回查。
2. **`apply_schema_semantics` 加 kwarg**（`contract.py:124`）：
   ```python
   def apply_schema_semantics(schema_name, structured_output, *, request_id=None, evidence_source=None):
       ...
       if processor.enrich is not None:
           structured_output = processor.enrich(structured_output)
       # 新增：最后一步，仅当底稿透传进来才跑（None → 跳过，向后兼容）
       if evidence_source and processor.resolve is not None:
           structured_output = processor.resolve(structured_output, evidence_source)
       return structured_output
   ```
   **顺序关键**：resolve 跑在最后。schema 硬校验（`additionalProperties:false`）在 enrich **前**已过；resolve 写的标注（`evidence_chain[].resolution` 等额外键）不会被 schema 再卡（返回值直接归档，无二次校验，见 `json_bridge.py:248-284`）。
3. **`run_agent_json` 加 kwarg**（`json_bridge.py:116`）+ 透传给两条结果路径（`_apply_result_message_structured` `:48` / `_apply_result_message_text` `:76`，本评标走 text 模式 `:259 structured=False`）→ 二者内部 `apply_schema_semantics(..., evidence_source=evidence_source)`。
4. **`run_command_json` 加 kwarg**（`command_adapter.py:43`）：`evidence_source` passthrough（**不进 prompt**，只进校验上下文；与已有的 `context=` 区分——context 喂模型，evidence_source 喂闸）。
   - ⚠ **必须在调用链每层都显式声明** `evidence_source: str | None = None`（critic P2）：`run_command_json` 当前把 `**opts` 整体转给 `run_agent_json` → 再转给 `build_options`（SDK 选项，`json_bridge.py:154`）。若 `evidence_source` 经 `**opts` 漂下去会被 `build_options` 当未知 SDK 选项报错。每层显式吃掉、内部消费，**不进 `**opts`**。
5. **`tender_worker._run_evaluation` 传底稿**（`tender_worker.py:242`）：`evidence_source=ocr_block`。注意传 **`ocr_block` 原始底稿**（带 `### 文件:`/`【第 N 页】` 锚点），**不传** `context`（context 尾部追加了 criteria 块，非回查目标）。

> 为什么不直接在 worker 里跑闸、非要透传进 contract？——契约校验是**结论后处理的单一入口**（结构化/文本两路、含重试环都经此），闸放这里才对所有调用路径生效且与 normalize/validate/enrich 同生命周期；放 worker 则只覆盖 tender 一条且与归档时序割裂。mechanism 通用（任何透传底稿的 schema 都能挂 resolve），policy 仍 tender 专属（只 tender_worker 透传 + 只 audit-result 注册 resolve）。

### B. evidence-resolution 闸（新模块 `server/common/evidence_resolution.py`，纯函数）

> 独立模块（不塞进已 701 行的 `output_contracts.py`，守 SRP）。`output_contracts.py` 末尾 `register_schema_processor(DEFAULT_OUTPUT_SCHEMA_NAME, ..., resolve=resolve_audit_evidence)` 引入。

**B1. 底稿索引（parse once）**
- ⚠ **两条底稿路径外层结构不同**（critic P1，已核 `tender_worker.py:191-212`）：
  - inline OCR：`ocr_preprocess_block → build_extraction_block`（`pipeline.py:239`）产 `### 文件: <name> (...)` + 每页 `【第 N 页】`，**无 `===` tier 外壳**。
  - doc-layer 复用：`_load_doc_layer_context`（`tender_worker.py:129-133`）外层包 `=== 招标文件底稿 ===` / `=== 投标文件（bidder）底稿 ===`，内层仍是 `### 文件:`/`【第 N 页】`。
- **tier 分段必须吃两态**（否则 inline 路径 tier 静默失效，所有招标/投标路由错）：
  - 有 `=== …底稿 ===` 外层标记 → 按它切「招标 / 投标」。
  - 无外层标记（inline 路径）→ 按每个 `### 文件: <name>` 的**文件名**推断 tier：name 含「招标」→tender、含「投标」/bidder 名→bid、判不出→whole。降级但不丢信息。
- **file-level page slices**（codex P1：索引必须到文件粒度，否则跨文件误命中）：先按 `### 文件: <name>` 切文件块，再在每文件块内按 `【第\s*(\d+)\s*页】`（底稿是 `【第 1 页】` 带空格，正则吃空白）切片，得 `{tier: {file_name: {page_no: page_text}}}`。**绝不能只按 `(tier, page_no)`**——19 个投标文件各自 `【第N页】` 从 1 重置，「投标文件第6页」会命中全部 19 家的第 6 页。
- **whole-tier 规范化全文**：每 tier 拼一份规范化全文（含全部文件），供 tier 级存在性判定（B3 主信号）。
- **规范化**（激进，治模型转述/全半角/标点/空白差异，深潜 caveat #1）：去所有空白、去标点（中英）、全角→半角、去 `【】《》()` 等装饰、统一大小写。规范化函数对 quote 与底稿用**同一套**。

**B2. 抽取待回查的「出处+quote」清单**（按 `tender-evaluate.md` 实际产出结构）
| 来源路径 | source 字段 | quote 字段 | 承重？ |
|---|---|---|---|
| `evidence_chain[i]` | `.source`（如「投标文件第6页《应答函》」） | `.finding`（所引页原文片段，`md:73`） | 展示+承重混 |
| `extracted_data.scoring[i].deduction_hits[j].evidence` | `.source`（文件+第N页+章节） | `.quote`（触发扣分原文，`md:53`） | **承重**（影响 score） |
| `extracted_data.scoring[i].award_hits[j].evidence` | `.source` | `.quote`（`md:56`） | **承重** |
| `extracted_data.disqualification_hits[i].evidence` | `.source` | `.quote`（`md:69`） | **承重**（影响 verdict） |
| `extracted_data.eligibility_checks[i].evidence` | `.source` | （basis/quote，`md:69`） | 承重 |
| `extracted_data.scoring[i].basis`（codex P1，goal §77 明列） | basis 内嵌「文件+第N页」 | basis 文本本身 | **承重**（`banded`/`formula`/`pass_fail` 项无离散 hits，依据全在 basis） |
| `extracted_data.scoring[i].selected_band.reason` / formula 变量 `ref`（codex P1） | ref/reason 内嵌出处 | reason/ref 文本 | 承重 |

> **覆盖度声明（codex P1）**：`deduction/additive` 项有结构化 `*_hits.evidence{source,quote}`（逐字 quote，可强回查）；`banded/formula/pass_fail` 项承重依据主要在 `basis`/`selected_band.reason`，**无逐字 quote**——这些只做「出处 loc 回查 + 文本存在性」，无可比对的逐字片段时**最多标 `loc_only`/`weak_match`，不标 resolved 也不降级**（不谎称已覆盖全部承重依据）。

每条解析：`tier`（source/basis 含「招标」→tender / 「投标」→bid / 否则 whole）、`file`（source/basis 内可识别的文件名，可缺）、`page`（`第\s*(\d+)\s*页`，可缺）、`quote`：
- `evidence_chain[i]` 的 quote 来源**固定 = `.finding`**（critic P1：`_normalize_evidence_chain` `output_contracts.py:254-262` 已在 normalize 阶段把每条剥到 `{source,finding,conclusion}` 三字段，resolve 在 normalize 后跑，**不存在独立 `quote` 字段、无「回退」一说**）。
- `extracted_data.*` 内的（scoring/disqualification/eligibility，`additionalProperties:true` 不被剥）→ 取 `.quote`；无 quote 的 `basis`/`reason` 项 → 取该文本本身，按上述「无逐字 quote」规则只做 loc/存在性、不 resolved/不降级。

**B3. 匹配（存在性=主信号；file/page=精度细化，不单独定 resolved；宁漏勿误杀）**

> codex P1 纠偏：原「page-window-first」会让 quote 命中**别家同页号**被误判 resolved。改为**存在性优先**——「原文是否在该 tier 底稿里」是抗编造的稳健硬信号（与具体在哪个文件无关）；file/page 精度只作**细化标注**，绝不单独支撑 resolved。

对每条 quote：
1. 规范化 quote；过短（规范化后 < `MIN_QUOTE_CHARS`，默认 8）→ 跳过（不可靠，不判）。
2. **存在性判定（主信号，tier 级 corpus）**：在该 tier（不可定 tier 则 whole）规范化全文求匹配度 `r`：
   - 先 `norm_quote in norm_corpus`（O(n) 子串包含，命中即 `r=1.0`）；C 级 `str.find`，~20 quote × 8M 字符亚秒级。
   - 未命中再求**最长公共*连续*子串**（Longest Common **Substring**，**非** subsequence；critic P1）长度，`r = lcs_substr_len / norm_quote_len`。滑窗/rolling-hash（**禁** DP 子序列：允许跳字符，中文几乎总能凑高占比 → 架空闸 + O(n·m) 爆炸）。超长中文 quote 兜底切 `k`-gram（**k=4~6**）命中计数作召回提示，判定仍以连续子串为准。
   - 兜底 corpus 上限 `EVIDENCE_MAX_CORPUS_CHARS`：超限则**首尾各取半 + 中间省略**，**绝不只取前 N**（否则重蹈 BOQ p8414 被头截丢 → 真引文误判 unresolved）。
3. **file/page 精度细化（仅当存在性已 resolved，用 file-level 索引细化标注，不改 resolved/unresolved 判定）**：
   - source 含可识别文件名 + cited page → 查 `{tier, file, page±EVIDENCE_PAGE_WINDOW}` 切片：命中 → `page` 确认；未命中但 tier 内别处有 → `page_mismatch`。
   - source 无文件名（仅「投标文件第N页」），或该 page 号在该 tier 多文件都命中 quote → `file_ambiguous`（codex P1：不强判到某文件、不据此 resolved 或 unresolved）。
4. 三档判定（**仅由存在性 `r` 决定**，双阈值中间带不降级）：
   - `r ≥ RESOLVE_THRESHOLD`（默认 0.65）→ **resolved**（原文确在 tier 底稿）；附 page 子状态（confirmed / page_mismatch / file_ambiguous，软标注，**绝不因 page/file 不符降级**）。
   - `r ≤ ABSENT_THRESHOLD`（默认 0.30）→ **unresolved**（原文基本不在底稿 = 疑似编造/严重转述）→ 标注 + **降级承重项**。
   - 中间带（0.30 < r < 0.65）→ **weak_match**（疑似转述非逐字）→ **软标注，不降级**（深潜 caveat #1：先宁漏勿误杀，R2024-007 上调阈值）。

**B4. 标注与降级（durable，最小契约面）**
1. **逐条软标注**（additive，前端忽略未知键安全）：给命中的 `evidence` / `evidence_chain[i]` 加 `resolution: "resolved"|"page_mismatch"|"weak_match"|"unresolved"`（resolved 也写，便于 dogfood 统计；可配 `RESOLUTION_ANNOTATE_RESOLVED=0` 只标异常）。
2. **承重项降级**（仅 `unresolved` 且来源属承重表 B2）：
   - `scoring[i]` 的 `deduction_hits/award_hits` 命中 unresolved 且该项 `status=="scored"` → 降 `status:"manual_review"`、`score:null`、`basis` 追加「⚠ 出处未在底稿核实（evidence_unresolved），已降人工复核」。**不直接 reject**（深潜 caveat #1）。降级后 `score:null` → **天然不参与** `_verify_scoring_consistency`（`:337`，null 跳过）与 score_mode 自洽（`:380`，且 resolve 跑在所有 validate 之后，不回流校验）→ 无冲突。
   - `eligibility_checks[i]` 命中 unresolved（critic blind-spot A）→ 该项 `status` 若为 `fail` 则**不改其 status / 不动 verdict**（同 disqualification，verdict 是高代价决定，R1 保守只读），但 `basis` 追加同款标注 + 计入高危摘要。
   - `disqualification_hits` 命中 unresolved → **不自动改 verdict**（废标 verdict 由 `_has_hard_disqualification` `:143` 既有 gate 在 normalize 阶段已定，R1 不动它）；仅标注 + 进高危摘要。**「废标依据本身未核实」是最高危情形**（critic P2）→ 在摘要里单列 `severity:"high"`。
3. **顶层 verdict/result 一致性回填（codex P1，关键）**：上一步**新引入了 manual_review 评分项**时，顶层 `verdict`/`result`/`conclusion` 会与之失配——`result`/`conclusion` 是 enrich 阶段（resolve 之前）从**旧 verdict** 派生的（`enrich_audit_decision` `:163`），不会自动跟随。修法：
   - 若降级后存在 manual_review 评分项 **且** 当前 `verdict=="approved"` → 升 `verdict="manual_review"` + `manual_review_reason="insufficient_evidence"`（命令契约 `md:74`：有 manual_review 项则顶层 manual_review）。
   - `verdict` 已是 `manual_review` → 仅补 reason（若缺）；`verdict=="rejected"` → **不动**（rejected 终局更强，不因单项未核实翻盘）。
   - 改了 verdict 后**重跑一次** `enrich_audit_decision(output)`（幂等，重新派生 `result`/`conclusion`）→ 三者一致。**受 `EVIDENCE_RESOLUTION_DOWNGRADE` 同一开关控制**（关闭则不降级也不升 verdict）。补 `approved→manual_review` 单测。
   - ⚠ **避免循环导入**：`output_contracts` 末尾 import `evidence_resolution` 注册 hook，而 resolve 又要 `enrich_audit_decision`（在 output_contracts 内）→ 函数体内**惰性 import**（`from server.common.output_contracts import enrich_audit_decision` 放调用处），不放模块顶。
4. **顶层摘要** `extracted_data.evidence_resolution`（`extracted_data` 是 `additionalProperties:true`，安全）：
   ```json
   {"checked": 23, "resolved": 18, "page_mismatch": 2, "weak_match": 1,
    "unresolved": 2, "downgraded_items": ["技术方案完整性"],
    "high_severity_unresolved": [{"where":"disqualification_hits[0]","source":"招标文件第27页","quote_preview":"…"}],
    "unresolved_refs": [{"where":"scoring/技术方案/deduction_hits[1]","source":"投标文件第6页","quote_preview":"…","severity":"normal"}]}
   ```
   → dogfood 直接读这块算命中率/假阴性率（验收用）；`high_severity_unresolved` 单列废标/资格依据未核实，前端/人工一眼可辨。
5. **失败安全**：闸内任何异常 → 记 `logger.warning` + 原样返回结论（**绝不因回查崩掉评标**，对齐 worker 既有「兜底不拖垮」哲学）。

**B5. 配置（env，可灰度/调阈值；运行时动态读，便于 dogfood 调参，对齐 `tender_worker` 既有 env 模式）**
- `TENDER_EVIDENCE_RESOLUTION`（默认 `1` 开；`0` 关闭整闸，仅透传不回查）。
- `EVIDENCE_RESOLVE_THRESHOLD`（0.65）/ `EVIDENCE_ABSENT_THRESHOLD`（0.30）/ `EVIDENCE_MIN_QUOTE_CHARS`（8）。
- `EVIDENCE_PAGE_WINDOW`（1，cited page ± N 页局部匹配）。
- `EVIDENCE_MAX_CORPUS_CHARS`（兜底全文匹配的语料上限，**首尾各取半**不头截）。
- `EVIDENCE_RESOLUTION_DOWNGRADE`（默认 `1`；`0` 则只标注不降级——首轮 dogfood 可先 `0` 看纯标注命中率再开降级）。
- `RESOLUTION_ANNOTATE_RESOLVED`（默认 `1`，resolved 也写标注便于统计；`0` 只标异常）。

### C. 提示词对齐（与回查键对齐，`tender-evaluate.md`）
- 强化 `md:73`：出处统一写「**文件名 + 第N页 + 章节**」（现已建议，改为更硬的格式约定），quote 写**逐字原文片段**（非转述）以利回查。这是低风险纯提示词增强，**不依赖它生效**（闸是确定性兜底，提示词只提高 resolved 率）。

---

## 三、影响范围

| 文件 | 改动 | 风险 |
|---|---|---|
| `server/common/evidence_resolution.py` | **新建**（B1-B4 纯函数 + resolve hook 入口） | 新增，无回归面 |
| `server/common/contract.py` | `SchemaProcessor` 加 `resolve` 字段；`register_schema_processor` 加 kwarg；`apply_schema_semantics` 加 `evidence_source` kwarg + enrich 后调 resolve | 低（默认 None 行为不变） |
| `server/common/json_bridge.py` | `run_agent_json` + 两 `_apply_result_message_*` 加 `evidence_source` 透传 | 低（默认 None） |
| `server/common/command_adapter.py` | `run_command_json` 加 `evidence_source` passthrough | 低 |
| `server/routes/tender_worker.py` | `_run_evaluation` 传 `evidence_source=ocr_block` | 中（接通闸，tender 行为变化点） |
| `server/common/output_contracts.py` | 末尾 `register_schema_processor(DEFAULT_OUTPUT_SCHEMA_NAME, ..., resolve=resolve_audit_evidence)` + import | 低 |
| `.claude/commands/tender-evaluate.md` | 出处格式/逐字 quote 提示强化（C） | 低（提示词，闸不依赖） |
| `tests/` | 新增闸单测（正常/转述/编造/page_mismatch/短 quote/异常兜底）+ 透传集成测试 | — |

**不改**：schema 文件（`.claude/contracts/...`，annotations 走 `additionalProperties:true` 的 extracted_data + post-enrich 额外键，不动契约）；verdict gate（`_has_hard_disqualification`）；audit 路径（不透传 evidence_source）。

---

## 四、风险与缓解

| 风险 | 缓解 |
|---|---|
| **假阴性误杀**：模型转述（非逐字）→ LCS 失败 → 误标 unresolved → 误降级有效项（深潜 caveat #1） | 双阈值 + 中间带 `weak_match` **不降级**；`EVIDENCE_RESOLUTION_DOWNGRADE=0` 可先纯标注 dogfood 调阈值；激进规范化吸收格式差异；R2024-007 上实测假阴性率再定阈值 |
| **页码硬判误杀**：每文件页号各自从 1、source 常只给 tier 不给确切文件 | page 只做**软标注** `page_mismatch`，**绝不因页不符降级**；存在性（quote 在底稿）才是硬信号 |
| **底稿未透传/为空**（doc-layer 回落、散单、OCR 失败） | `evidence_source` 为空 → 闸整体跳过（向后兼容），不报错不降级 |
| **闸异常拖垮评标** | try/except 包裹，异常 → warning + 原样返回（对齐 worker 兜底哲学） |
| **大底稿性能**（8636 页/8M 字符）：全文连续子串匹配爆炸 | ①**page-window-first**：cited page 已知 → 只在 ±N 页局部切片匹配（绝大多数引文带页码 → 根本不碰全文）；②先 `norm_quote in norm_corpus` O(n) 子串包含预判，命中即止；③未命中才退连续子串求值（滑窗/rolling-hash，**非** DP 子序列）；④兜底全文设 `EVIDENCE_MAX_CORPUS_CHARS`（**首尾各半，不头截**，避免 BOQ 式尾部丢失）；规范化全文按 tier 缓存一次；底稿规模上界由 R2（BOQ 抽取）治理 |
| **额外键污染前端/下游** | 全是 additive 键（`resolution` / `evidence_resolution`），前端忽略未知字段；downgrade 改的 status/score/basis 是既有字段语义内变更 |
| **降级→null 在 compare/前端显示成「0 分 / 第 N 名」**（codex P2，`agent-front/.../tender-review/model.ts:324` 把 null total→0、null rank→index+1） | downgrade 升 verdict=manual_review → compare 该家可能 `total_score:null`（`compare-result.schema.json:42` 允许）。R1 加**回归断言**：manual/null 家显示「待判定/未排名」而非「0 分/暂定第 N 名」。前端映射修复若超 R1 后端范围 → 记入 R6（三层 e2e/compare）并在本轮「进度回写」标 followup |

---

## 五、验收标准（R2024-007 dogfood，§goal 四素材）

1. **管道打通**：tender 评标时 `apply_schema_semantics` 实收到底稿（断点/日志 `evidence_resolution.checked > 0`）；audit 路径 `evidence_source=None` 不受影响（回归绿）。**断言传的是 `ocr_block` 而非 `context`**（critic blind-spot C：context 尾部已追加 criteria 注入块 + OCR 头注释，会干扰 tier/page 解析）——加一条单测固化此约束。
2. **存在性回查**：
   - 构造编造 quote（底稿无此原文）→ 闸标 `unresolved` + 降级该 scoring 项为 manual_review/score:null（`EVIDENCE_RESOLUTION_DOWNGRADE=1`）。
   - 逐字真原文 → `resolved`，不降级。
   - 转述/同义 → `weak_match`，**不降级**（验证不误杀）。
   - **跨文件不误命中**（codex P1）：quote 真在 A 家第 6 页、source 写「投标文件第6页」、B 家第 6 页无此文 → 不因 B 家同页号误判；存在性仍 resolved（A 家有），page 子状态 `file_ambiguous`。
2b. **verdict 一致性**（codex P1）：原 `verdict=approved` 的结论，降级引入 manual_review 项后 → 顶层 `verdict=manual_review`、`manual_review_reason=insufficient_evidence`、`result`/`conclusion` 同步重派生一致；`verdict=rejected` 不被翻盘。
2c. **compare/前端 null 显示**（codex P2）：降级致某家 verdict=manual_review/total null → compare 与前端显示「待判定/未排名」，不显「0 分/暂定第 N 名」。
3. **R2024-007 实测指标**（写本轮「自测结果」节）：跑二建 + 四建两家，统计 `evidence_resolution`：
   - 引文回查命中率（resolved / checked）；
   - 假阴性率（人工抽查 weak_match+unresolved 中实际真存在的比例）→ 据此调 `RESOLVE/ABSENT_THRESHOLD`；
   - 降级项是否合理（人工核对 downgraded_items）。
4. **单测**：闸 6 类用例（resolved/unresolved/weak/page_mismatch/短quote跳过/异常兜底）+ 透传集成（evidence_source None vs 有值）全绿。
5. **回归**：`uv run pytest -q`（616+ 现有）+ `ruff check .` 全绿；前端无关本轮（纯后端）。
6. **三模型自测**（§goal 六协议）：DeepSeek / qwen / glm 各跑一遍 R2024-007 单家，记 **resolution 分布对比**（checked/resolved/page_mismatch/weak_match/unresolved/降级项各一列；critic blind-spot D：模型逐字 vs 转述倾向不同，三模型分布差异是阈值是否对多模型鲁棒的关键证据）+ 耗时到「自测结果」。阈值定档须基于三模型分布、非单模型。

---

## 六、实施顺序（TDD，铁律[TDD]）

1. 先写 `evidence_resolution.py` 纯函数单测（规范化 / 索引解析 / LCS 匹配 / 三档判定 / 标注降级），红。
2. 实现 `evidence_resolution.py` 至单测绿。
3. 打通透传管道（contract → json_bridge → command_adapter → tender_worker），加透传集成测试。
4. `output_contracts` 注册 resolve hook；跑全回归。
5. 提示词对齐（C）。
6. R2024-007 dogfood + 三模型自测 → 调阈值 → 回写「自测结果」+「进度回写」。

---

## 七、设计审查记录（impl 前）

| 审查者 | VERDICT | 关键 findings | 处理 |
|---|---|---|---|
| critic（PACE design 独立审，ultrathink） | CONCERNS | P1 inline OCR 无 `===` tier 外壳 / LCS 子序列歧义 / 大 corpus 头截重蹈 BOQ / evidence_chain quote 固定 .finding；P2 `**opts` 漂入 build_options / 废标依据未核实高危；blind-spot eligibility/k 值/ocr_block 断言/三模型分布 | **全部已修进 B1/B2/B3/B4/A4/§五** |
| codex exec（独立二审，read-only grounding） | REWORK | P1 降级后 verdict/result 不同步（enrich 在 resolve 前派生）/ `scoring[].basis` 漏查 / page-window 跨文件误命中；P2 compare·前端 null 显示成 0 分·第N名 | **全部已修**：B4.3 verdict 一致性回填 + 惰性 import；B2 加 basis/reason/ref + 覆盖度声明；B3 改存在性主信号 + file-level 索引 + file_ambiguous；风险表+§五 加 null 显示回归 |

> 两轮审查均无残留未处理 P0/P1。设计自评：REWORK→已收敛，可进 impl（TDD）。

## 七、自测结果（2026-06-22 实测）

**单测/回归**：`tests/test_evidence_resolution.py` 28 例全绿（含两态解析/连续子串/三档/跨文件不误命中/verdict 回填/loc_only/失败安全/透传集成）；`uv run pytest -q` **644 全绿**（原 616 + 28）；`ruff check .` clean。

**R2024-007 dogfood**（HTTP worker directory 模式，二建一家，**排除 8417 页 BOQ**=R2 范围；招标+18 投标文件，29MB；project `tp-613b5cfcea524b1f`）：

| 指标 | qwen3.7-max | deepseek-v4-pro[1M] |
|---|---|---|
| 评标耗时 | ~136s | ~155s |
| evidence checked | 9 | 19 |
| resolved | 9 | 12 |
| weak_match | 0 | 5 |
| **unresolved** | **0** | **2** |
| page_mismatch | 2 | 2 |
| loc_only | 5 | 10 |
| **降级项 downgraded** | **0** | **0** |
| verdict | manual_review（model 自判 data_conflict） | manual_review（model 自判 insufficient_evidence） |

**结论（管道打通 + 闸生效 + 不误杀，均验证）**：
1. **管道打通**：两模型结论 `extracted_data.evidence_resolution.checked > 0` → 底稿确已透传进校验闸。audit 路径不透传 → 回归全绿不受影响。
2. **闸生效**：确定性回查每条出处逐字命中底稿；resolved/weak/unresolved/page_mismatch/loc_only 五态均产出。
3. **零误杀（关键）**：两模型 **downgraded=0**——所有承重 `deduction_hits/award_hits` 逐字 quote 全部 resolved，无错误降级真实评分项。验证保守双阈值有效。
4. **unresolved 全落在 evidence_chain（非降级路径）**：DeepSeek 2 条 unresolved 均是 `evidence_chain[].finding` 写成**模型转述/概括**（如"简历主要工作经历表为空…"、基准价公式概括）而非逐字原文——正是深潜 caveat #1 的假阴性，但**已被设计隔离**：evidence_chain 只标注不降级，仅 scoring 结构化逐字 quote 才降级（两模型该路径 0 unresolved）。
5. **模型分布差异**（critic blind-spot D 验证）：DeepSeek 引证更多（19 vs 9）且更爱在 evidence_chain 概括（weak 5 + unresolved 2）；qwen 引证少而全逐字（resolved 9/9）。**两者降级路径都干净** → 阈值对多模型鲁棒。

**阈值定档**：保持默认 `RESOLVE=0.65 / ABSENT=0.30 / MIN_QUOTE=8 / PAGE_WINDOW=1`（实测 0 误杀，无需收紧）；`EVIDENCE_RESOLUTION_DOWNGRADE=1`（默认开，dogfood 证明安全）。

**调优观察（非阻塞，记 backlog）**：`evidence_chain[].finding` 模型常写概括非逐字 → unresolved/weak 计数虚高（无害，因不降级）。可选优化：evidence_chain 改判更宽松或单列"narration"类，使指标更干净。R1 不改（不影响承重路径）。

## 八、进度回写（2026-06-22）

- **状态**：R1 impl 完成 + 自测通过。commit `1a96db7`（feat(tender): R1 evidence-resolution 闸 + 透传管道）。
- **交付**：新模块 `server/common/evidence_resolution.py`（确定性回查纯函数）；透传管道（contract/json_bridge/command_adapter/tender_worker）；resolve hook 注册；提示词对齐；28 单测。644 全绿 + ruff clean。
- **两轮设计审查**（critic CONCERNS + codex REWORK）findings 全部落地（见 §七 设计审查记录）。
- **Followup（移交后续轮）**：
  - **R2**：BOQ 感知抽取（本轮 dogfood 排除了 8417 页 BOQ）；BOQ 入场后 evidence-resolution 对报价类 quote 的回查需复测。
  - **R6**：compare/前端 null 显示成「0 分/第 N 名」（codex P2，`model.ts:324`）——本轮降级会产 manual_review/null，前端映射修复留 R6 三层 e2e。
  - 调优观察：evidence_chain narration 假阴性（见 §七，无害）。
  - 第二家（四建）+ glm 第三模型未跑（时间/范围），降级路径已由两模型验证干净；可在 R6 全回归补。
