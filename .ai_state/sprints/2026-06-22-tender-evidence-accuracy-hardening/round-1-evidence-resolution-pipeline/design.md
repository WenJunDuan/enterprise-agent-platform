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
- **page slices**：在每 tier 内按 `【第\s*(\d+)\s*页】`（底稿是 `【第 1 页】` 带空格，正则吃空白）切片，得 `{tier: {page_no: [page_text,...]}}`（同页号跨多文件，存 list）。**page slice 索引同时服务「按 cited page 局部窗口匹配」**（见 B3 大 corpus 策略）。
- **whole-tier 规范化全文**：每 tier 拼一份规范化全文，供「不限页」存在性兜底。
- **规范化**（激进，治模型转述/全半角/标点/空白差异，深潜 caveat #1）：去所有空白、去标点（中英）、全角→半角、去 `【】《》()` 等装饰、统一大小写。规范化函数对 quote 与底稿用**同一套**。

**B2. 抽取待回查的「出处+quote」清单**（按 `tender-evaluate.md` 实际产出结构）
| 来源路径 | source 字段 | quote 字段 | 承重？ |
|---|---|---|---|
| `evidence_chain[i]` | `.source`（如「投标文件第6页《应答函》」） | `.finding`（所引页原文片段，`md:73`） | 展示+承重混 |
| `extracted_data.scoring[i].deduction_hits[j].evidence` | `.source`（文件+第N页+章节） | `.quote`（触发扣分原文，`md:53`） | **承重**（影响 score） |
| `extracted_data.scoring[i].award_hits[j].evidence` | `.source` | `.quote`（`md:56`） | **承重** |
| `extracted_data.disqualification_hits[i].evidence` | `.source` | `.quote`（`md:69`） | **承重**（影响 verdict） |
| `extracted_data.eligibility_checks[i].evidence` | `.source` | （basis/quote，`md:69`） | 承重 |

每条解析：`tier`（source 含「招标」→tender / 「投标」→bid / 否则 whole）、`page`（`第\s*(\d+)\s*页`，可缺）、`quote`：
- `evidence_chain[i]` 的 quote 来源**固定 = `.finding`**（critic P1：`_normalize_evidence_chain` `output_contracts.py:254-262` 已在 normalize 阶段把每条剥到 `{source,finding,conclusion}` 三字段，resolve 在 normalize 后跑，**不存在独立 `quote` 字段、无「回退」一说**）。
- `extracted_data.*` 内的（scoring/disqualification/eligibility，处于 `additionalProperties:true` 不被剥）→ 取 `.quote`，缺则回退 `.basis`/finding 文本。

**B3. 匹配（quote-first，page 为辅；宁漏勿误杀）**
对每条 quote：
1. 规范化 quote；过短（规范化后 < `MIN_QUOTE_CHARS`，默认 8）→ 跳过（不可靠，不判）。
2. **匹配语料选择（治大 corpus，critic P1）**：
   - cited page 已知 → **优先只在「cited page ± `EVIDENCE_PAGE_WINDOW`（默认 1）页」的局部切片**里匹配（page slice 索引直接支持）。命中即 `resolved`，**既快又准、且天然避开 8M 全文扫描**。
   - cited page 缺 / 局部窗口未命中 → 退到 tier（不可定 tier 则 whole）规范化全文做存在性兜底。**超大 corpus 截断必须「首尾各取 K 字符 + 中间省略」**（`EVIDENCE_MAX_CORPUS_CHARS`），**绝不只取前 N**（否则重蹈 BOQ p8414 被头截丢的覆辙 → 把真引文误判 unresolved）。
3. **匹配度量 = 最长公共*连续*子串**（Longest Common **Substring**，**非** subsequence；critic P1）：先 `norm_quote in norm_corpus`（O(n) 子串包含，命中即 `r=1.0`）；未命中再求最长连续公共子串长度，`r = lcs_substr_len / norm_quote_len`。算法用滑窗 / rolling-hash（**禁** DP 子序列：子序列允许跳字符，中文几乎总能凑高占比 → 架空闸；且 O(n·m) 爆炸）。中文超长 quote 兜底可切 `k`-gram（**k=4~6**，2 太碎随机命中、10 等同子串）命中计数，最终命中率仍以连续子串为准、k-gram 只作召回提示。
4. 三档判定（双阈值，中间带不降级）：
   - `r ≥ RESOLVE_THRESHOLD`（默认 0.65）→ **resolved**（原文确在底稿）。再看 page：cited page 窗口里命中 → `resolved`；不在 cited page 但在 tier 内别处命中 → `page_mismatch`（**软标注，不降级**——每文件页码各自从 1 起、source 常只给 tier 不给确切文件，硬判页易误杀）。
   - `r ≤ ABSENT_THRESHOLD`（默认 0.30）→ **unresolved**（原文基本不在底稿 = 疑似编造/严重转述）→ 标注 + **降级承重项**。
   - 中间带（0.30 < r < 0.65）→ **weak_match**（疑似转述非逐字）→ **软标注，不降级**（深潜 caveat #1：先宁漏勿误杀，R2024-007 上调阈值）。

**B4. 标注与降级（durable，最小契约面）**
1. **逐条软标注**（additive，前端忽略未知键安全）：给命中的 `evidence` / `evidence_chain[i]` 加 `resolution: "resolved"|"page_mismatch"|"weak_match"|"unresolved"`（resolved 也写，便于 dogfood 统计；可配 `RESOLUTION_ANNOTATE_RESOLVED=0` 只标异常）。
2. **承重项降级**（仅 `unresolved` 且来源属承重表 B2）：
   - `scoring[i]` 的 `deduction_hits/award_hits` 命中 unresolved 且该项 `status=="scored"` → 降 `status:"manual_review"`、`score:null`、`manual_review_reason` 不动（项级无此字段，写进 basis）、`basis` 追加「⚠ 出处未在底稿核实（evidence_unresolved），已降人工复核」。**不直接 reject**（深潜 caveat #1）。
   - `disqualification_hits` 命中 unresolved → **不自动改 verdict**（废标 verdict 由 `_has_hard_disqualification` 既有 gate 决定，R1 不动它）；仅标注 + 写进 `evidence_resolution` 摘要供人工。R1 对 verdict 保守只读不改。
3. **顶层摘要** `extracted_data.evidence_resolution`（`extracted_data` 是 `additionalProperties:true`，安全）：
   ```json
   {"checked": 23, "resolved": 18, "page_mismatch": 2, "weak_match": 1,
    "unresolved": 2, "downgraded_items": ["技术方案完整性"],
    "unresolved_refs": [{"where":"scoring/技术方案/deduction_hits[1]","source":"投标文件第6页","quote_preview":"…"}]}
   ```
   → dogfood 直接读这块算命中率/假阴性率（验收用）。
4. **失败安全**：闸内任何异常 → 记 `logger.warning` + 原样返回结论（**绝不因回查崩掉评标**，对齐 worker 既有「兜底不拖垮」哲学）。

**B5. 配置（env，可灰度/调阈值）**
- `TENDER_EVIDENCE_RESOLUTION`（默认 `1` 开；`0` 关闭整闸，仅透传不回查）。
- `EVIDENCE_RESOLVE_THRESHOLD`（0.65）/ `EVIDENCE_ABSENT_THRESHOLD`（0.30）/ `EVIDENCE_MIN_QUOTE_CHARS`（8）。
- `EVIDENCE_RESOLUTION_DOWNGRADE`（默认 `1`；`0` 则只标注不降级——首轮 dogfood 可先 `0` 看纯标注命中率再开降级）。

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
| **大底稿性能**（8636 页规范化全文）：LCS 朴素 O(n·m) 在 8M 字符上爆炸 | 规范化全文按 tier 缓存一次；LCS 用「滑窗 + 子串包含快速预判」：先 `norm_quote in norm_corpus`（O(n) 子串查找，命中即 resolved），未命中再退化到**有上界**的近似（如按 quote 长度切 k-gram 命中计数，避免全量 LCS）；底稿规模上界由 R2（BOQ 抽取）治理，R1 对超大 corpus 设 `EVIDENCE_MAX_CORPUS_CHARS` 截断兜底 |
| **额外键污染前端/下游** | 全是 additive 键（`resolution` / `evidence_resolution`），前端忽略未知字段；downgrade 改的 status/score/basis 是既有字段语义内变更 |

---

## 五、验收标准（R2024-007 dogfood，§goal 四素材）

1. **管道打通**：tender 评标时 `apply_schema_semantics` 实收到底稿（断点/日志 `evidence_resolution.checked > 0`）；audit 路径 `evidence_source=None` 不受影响（回归绿）。
2. **存在性回查**：
   - 构造编造 quote（底稿无此原文）→ 闸标 `unresolved` + 降级该 scoring 项为 manual_review/score:null（`EVIDENCE_RESOLUTION_DOWNGRADE=1`）。
   - 逐字真原文 → `resolved`，不降级。
   - 转述/同义 → `weak_match`，**不降级**（验证不误杀）。
3. **R2024-007 实测指标**（写本轮「自测结果」节）：跑二建 + 四建两家，统计 `evidence_resolution`：
   - 引文回查命中率（resolved / checked）；
   - 假阴性率（人工抽查 weak_match+unresolved 中实际真存在的比例）→ 据此调 `RESOLVE/ABSENT_THRESHOLD`；
   - 降级项是否合理（人工核对 downgraded_items）。
4. **单测**：闸 6 类用例（resolved/unresolved/weak/page_mismatch/短quote跳过/异常兜底）+ 透传集成（evidence_source None vs 有值）全绿。
5. **回归**：`uv run pytest -q`（616+ 现有）+ `ruff check .` 全绿；前端无关本轮（纯后端）。
6. **三模型自测**（§goal 六协议）：DeepSeek / qwen / glm 各跑一遍 R2024-007 单家，记 checked/resolved/unresolved/降级差异 + 耗时到「自测结果」。

---

## 六、实施顺序（TDD，铁律[TDD]）

1. 先写 `evidence_resolution.py` 纯函数单测（规范化 / 索引解析 / LCS 匹配 / 三档判定 / 标注降级），红。
2. 实现 `evidence_resolution.py` 至单测绿。
3. 打通透传管道（contract → json_bridge → command_adapter → tender_worker），加透传集成测试。
4. `output_contracts` 注册 resolve hook；跑全回归。
5. 提示词对齐（C）。
6. R2024-007 dogfood + 三模型自测 → 调阈值 → 回写「自测结果」+「进度回写」。

---

## 七、自测结果（impl 后回填）

_（待 impl 后填：管道打通证据、R2024-007 命中率/假阴性率/降级项、三模型差异、阈值定档）_

## 八、进度回写（impl 后回填）

_（待回填）_
