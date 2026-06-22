# R2 设计 · BOQ 感知抽取 + 截断策略（报价规模正确）

> Sprint: `2026-06-22-tender-evidence-accuracy-hardening` · Round 2
> 路径分类: **Feature**（新增确定性 BOQ 抽取模块 + 改 build_extraction_block 截断策略；~3 文件 + 1 新模块）
> 行号 2026-06-22 实测 grep；**BOQ 结构为本会话实读 R2024-007 二建 1.05 已标价工程量清单.pdf（8417 页）所得**。

---

## 一、背景（WHY）

**痛点（codex 二审纠偏后的准确表述）**：超大 BOQ（已标价工程量清单）被 `build_extraction_block`（`pipeline.py:250`）`full_body[:MAX_FILE_BLOCK_CHARS]`（`:24`，默认 200000）**从头截**到前 ~210 页。问题**不是**"投标总价被截到尾部丢失"——实读发现真总价在 **p2 扉页**（在头部 200k 内、未被截）。真问题是三重：
1. **总价淹没在噪音里→引用不稳定**：p2 的 `381574199.97` 埋在 ~210 页密集 BOQ 表行（项目编码/工程量/综合单价/特征描述）里，模型要从 200k 噪音中找出并正确引用总价，不稳定（易脑补/漏引/引成某单位工程小计）。
2. **97% 清单未见**：8417 页只注入前 ~210 页（2.5%），其余单位工程的分部分项/措施/规费税金合计全不可见 → 报价结构性失据。
3. **上下文浪费**：200k BOQ 噪音挤占模型上下文预算，拖累整单评判。
4. **尾部汇总变体**：部分 BOQ 把工程项目总价汇总放在**末尾**，此时头截**确会丢总价**——本方案一并覆盖。

**修法**：**BOQ 感知确定性抽取**——把投标总价/各类合计/Top-N 高价从 8M 里结构化抽出，注入几 KB 紧凑摘要（显式提升 grand total 为结构化字段），替代"210 页噪音从头截"。既治引用不稳定，又省上下文，也覆盖尾部汇总变体。

**实读 grounding（修正深潜，关键）**：本会话实读 R2024-007 二建 BOQ（8417 页，pymupdf）：
- **真·投标总价 = `381574199.97`（≈3.82 亿）在 p2「扉页·投标总价」**，格式：
  ```
  投标总价(小写): ______
  381574199.97
  (大写): ______
  叁亿捌仟壹佰伍拾柒万肆仟壹佰玖拾玖元玖角柒分   ← 大写校验
  ```
  **深潜说的「合计 851,886 @p8414」是错的**——那只是其中一个单位工程（电梯工程075）的**税金合计**。本标是多单位工程大项目，每个单位工程各有自己的「分部分项合计/单价措施合计/规费/税金/合计」，**真总价在扉页汇总**。
- **label 与金额在相邻行**（PDF 单元格逐行抽取）：如 `分部分项合计\n3012424.9`、`投标总价(小写):\n381574199.97`。
- **12 位"数字"是项目编码**（如 `040501004012`），非金额——**必须排除**。判别：金额带小数点或千分逗号；项目编码/序号/工程量是纯整数（编码常 9-12 位）。

**结论**：靠"从头截"必丢尾部总价；靠模型在 8M 字符里找总价也不可靠。需 **BOQ 感知确定性抽取**：识别 BOQ 大表 → 抽关键金额（投标总价/各类合计/Top-N 高价）注入紧凑摘要（几 KB），而非把 8M 从头截。

---

## 二、方案（HOW）

### A. 新模块 `server/ocr/boq.py`（纯函数，确定性，可测）

> 独立模块（不塞进 pipeline.py，守 SRP）。无模型、无网络。输入 = `build_extraction_block` 里 `_render_body` 产出的**带页锚点全文** `full_body`（含 `【第 N 页】`）+ 文件名；输出 = 紧凑摘要字符串或 None。

**A1. BOQ 识别 `is_boq(name, full_body) -> bool`**
- **文件名信号**（主，鲁棒）：含任一 `{工程量清单, 已标价清单, 已标价工程量, 分部分项, 综合单价}`。
- **内容信号**（辅）：body 命中表头特征 `项目编码` + `综合单价` + (`合价`|`金额`) + 多个 `分部分项合计`/`合计`。
- 任一满足即 BOQ。**仅对会被截断的大文件启用**（`len(full_body) > MAX_FILE_BLOCK_CHARS`），小清单照常全量注入、不动。

**A2. 金额解析（两档，治"整数总价漏抽" critic F1）**
- **严格档**（Top-N / 各类合计用）：金额必须带**千分逗号或小数点** `\d{1,3}(?:,\d{3})+(?:\.\d+)?` | `\d+\.\d{1,2}`——干净排除 12 位整数项目编码 / 序号 / 工程量整数。
- **宽松档**（仅"投标总价" label 上下文用）：相邻行金额允许**纯整数 ≥5 位**（如某软件导出 `投标总价(小写):\n4950000`，无小数无逗号也要抽）——因有 label 锚定，不会误纳编码。
- `normalize_amount(s) -> float`：去逗号转 float。（R1 协同：codex 已核 `normalize_text` 去逗号 → 摘要 `381574199.97` 与模型引 `381,574,199.97` 规范化后同串，回查命中，无需特殊处理。）

**A3. 关键金额抽取 `extract_boq_summary(name, full_body, *, top_n=8) -> str | None`**
维护「当前页号」：仅 `【第 N 页】` 锚点更新；**`full_body` 尾部 tables 段无页锚点（codex P1#4，`_render_body:208` tables 追加在所有 blocks 后、`native.py:78` table 无 page）→ 该段金额页号置 `None`（"页未知"），绝不继承最后一个 block 的页号**（防张冠李戴）。
抽四类：
1. **投标总价（grand total，最重要，候选打分 codex#5）**：收集所有含「投标总价」的位置为候选，**打分选最优**而非简单取首个：
   - +扉页/前 5 页（`page ≤ 5`）、+同行/3 行内含「小写」、+3 行内有**大写中文金额**校验行、+宽松档金额命中；
   - −上下文含「单位工程/税金/分部分项/措施/某某工程(NNN)」（这些是局部小计，非总价）。
   - 取最高分为 `chosen`，同时在摘要列出**全部候选**（页 + 值 + 入选理由），人可核。大写行并列。
2. **汇总类**：含 `{工程项目总价, 单位工程汇总, 汇总}` + 金额的行。
3. **各类合计**：含 `{分部分项合计, 单价措施合计, 措施项目, 其他项目, 规费, 税金, 合计}`（严格档金额）→ 按金额降序取前 K（默认 12），**报总条数**（"共 86 处合计行，列最大 12"——透明不静默截断）。
4. **Top-N 高价金额**：严格档金额候选去重降序，排除已列总价，取前 `top_n`，带页锚点 + 行片段（异常价抽查）。
- 组装紧凑摘要——**页锚点独占一行**（codex P1#3 / critic F4：R1 `_PAGE_RE` 要求 `【第N页】` 单独成行，否则破 R1 page 解析），逐字保留金额原文（R1 可回查）：
  ```
  ### [本块为 BOQ 结构化摘要] 已标价工程量清单原文 8417 页/8.0M 字符过大，已按结构抽取关键金额，未全文注入。
  【第 2 页】
  投标总价(小写): 381574199.97  (大写: 叁亿捌仟壹佰伍拾柒万…元玖角柒分)  [grand total · 入选:扉页+小写+大写校验]
  投标总价候选(全部，供人核): p2=381574199.97✓ / p3527=... / ...
  各类合计(共 K 处，列金额最大 12)：
  【第 8388 页】
  税金 合计 851886.14
  …
  Top-8 高价金额(供异常价抽查)：
  【第 3645 页】
  铺种草皮 合价 254974.30
  …
  [完整逐行清单未注入；逐项核验请人工查原文件 1.05]
  ```
- **摘要长度上限**（critic F5）`MAX_BOQ_SUMMARY_CHARS = MAX_FILE_BLOCK_CHARS // 4`：优先保投标总价段，超限则裁减合计/Top-N 条数 + 末尾标注，确保摘要远小于全量（不会比头截还大）。
- **任一抽取异常 / 抽不到投标总价且抽不到任何合计 → 返回 None**（调用方回落截断，不更差）。

### B. `build_extraction_block` 截断策略改造（`pipeline.py:239-262`）

```python
full_body = _render_body(result)
if len(full_body) > MAX_FILE_BLOCK_CHARS:
    summary = boq.extract_boq_summary(name, full_body) if boq.is_boq(name, full_body) else None
    if summary is not None:
        body = summary                 # BOQ 感知紧凑摘要（含页锚点，逐字金额）
    else:
        body = _truncate(full_body)    # 默认头截（向后兼容）；env 开则首尾截
else:
    body = full_body
```
- **BOQ 摘要是 R2 的真交付**（治痛点）。通用截断改为**保守**：
- **head-tail 改成 env-gated 默认关**（codex P2#6 纠偏）：`_truncate(full_body)` 默认仍 `full_body[:MAX]`（**不动 expense/audit 现有头部字段语义**——发票/合同关键字段在头部，贸然减头部预算会回归）；`OCR_TRUNCATE_HEAD_TAIL=1` 时才首尾截（head≈70%/tail≈30%）。**不再宣称"首尾严格优于头截"**——它是可选项，跨域默认不启用。tender 大非 BOQ 文件若需保尾，按需开 env。
- 截断标记沿用现有格式 `\n\n...[内容已截断：...]`（critic F6：**不含 `【第N页】` 字样**，免破 R1 `parse_corpus` 页索引）。
- 识别不到 BOQ / 抽取失败 → 回落 `_truncate`（默认头截，与现状一致，绝不更差）。

### C. 与 R1 evidence-resolution 协同
- R2 后，BOQ 在底稿里 = 紧凑摘要；R1 的 `evidence_source` = 同一 `build_extraction_block` 产物 → 模型看摘要、引摘要里的金额，R1 回查同一摘要 → **一致**（摘要逐字保留金额原文，回查命中）。
- 故 R2 不破 R1：模型引「投标总价 381574199.97 @p2」→ R1 在摘要里逐字命中 → resolved。

---

## 三、影响范围

| 文件 | 改动 | 风险 |
|---|---|---|
| `server/ocr/boq.py` | **新建**（is_boq / 金额解析 / extract_boq_summary，纯函数） | 新增，无回归面 |
| `server/ocr/pipeline.py` | `build_extraction_block` 截断分支：BOQ→摘要 / 其他大文件→`_truncate`（默认头截，env 开首尾截） | 中（改底稿组装；BOQ 分支仅 is_boq 命中走，非 BOQ 默认行为不变） |
| `tests/test_boq.py` | **新建**：is_boq / 金额两档(排除编码+整数总价) / 投标总价候选打分 / table 段无页号 / 合计 / TopN / 摘要超限裁减 / 非BOQ回落 / 异常回落 / R1 parse_corpus(摘要) page confirmed | — |
| `tests/test_ocr_pipeline.py` | 加：大 BOQ→摘要、大非 BOQ→默认仍头截、env 开→首尾截、小文件不变 | — |

**不改**：classify/native/engine（识别层）；R1 evidence_resolution（协同验证即可）；schema/契约。
**范围边界（critic F3）**：R2 仅处理 **native blocks 路径** BOQ（数字文本层，R2024-007 即此类）。**扫描件 BOQ（OCR pages 路径，管道表格格式）超本轮范围 → 留 R3**（OCR/confidence 轮）。is_boq 对 pages 路径返回 False（回落截断），不误处理。

---

## 四、风险与缓解

| 风险 | 缓解 |
|---|---|
| **BOQ 格式各异**（不同造价软件导出） | 多同义词兜底（合计/总计/价款/总价/分部分项/措施/规费/税金）；label-金额相邻行双向找；识别不到/抽不到 → 回落首尾截（不更差） |
| **投标总价抽错**（抽成某单位工程小计） | 候选**打分**（扉页/前5页 + 小写 + 3行内大写校验，减"单位工程/税金/合计"上下文）取最优；全部候选并列供人核；Top-N/合计另列 |
| **金额误纳项目编码** | 严格档强制带小数/千分逗号（实测干净排除 12 位编码）；宽松档仅在「投标总价」label 锚定下允许整数 |
| **整数投标总价漏抽**（critic F1） | 投标总价宽松档允许纯整数 ≥5 位（label 锚定不误纳编码） |
| **prewarm 旧 ocr_text 滞留**（critic F2 / codex P0#2） | content-sha 缓存只存 per-file 识别结果（`cache.py`），`build_extraction_block` 每次重跑 → **directory 模式立即生效**；但 prewarm 把组装文本存进 `tender_doc_store.ocr_text`（`tender.py:952`），评标复用旧头截版。**缓解**：dogfood 走 **directory 模式**（不读 DB 旧文本）；生产侧记 followup（需重传或加 `ocr_version` 失效，留 R6/backlog）。单测覆盖"directory 模式 BOQ 走新摘要" |
| **table 段金额张冠李戴**（codex P1#4） | tables 追加段无页锚点 → 该段金额页号置 None（不继承末 block 页号）；测试覆盖 |
| **摘要漏关键金额致模型仍失据** | 摘要显式声明"已结构化抽取、非全文"+ 列投标总价/候选/各合计/TopN；逐项核验指引人工查原件；R4 据 dogfood 增补字段 |
| **改 build_extraction_block 跨域回归**（codex P2#6） | head-tail 默认关（非 BOQ 大文件行为与现状一致）；BOQ 分支仅 is_boq 命中走；全回归 + dogfood 兜底 |
| **摘要本身超 MAX**（critic F5） | `MAX_BOQ_SUMMARY_CHARS = MAX//4` 上限，优先保总价段，超限裁减条数 |
| **性能**（8M 字符扫描） | 单遍逐行 O(n)，实测 pymupdf 全量秒级；正则编译一次 |

---

## 五、验收标准

1. **单测**（`test_boq.py`）：
   - `is_boq`：文件名/内容信号命中；普通文件不误判。
   - 金额解析：`040501004012`(编码) 排除；`381574199.97`/`3,012,424.90`/`69358.72` 纳入。
   - 投标总价抽取：合成扉页文本 → 抽出 `381574199.97` + 大写 + 页号。
   - 各类合计 + Top-N：多合计行 → 降序取前 K + 报总数；TopN 排除总价。
   - 投标总价候选打分：扉页真总价 vs 后部单位工程小计并存 → chosen=扉页。
   - table 段金额：无页锚点段 → 页号 None（不继承末 block 页）。
   - 摘要超限 → 裁减后 < MAX//4。
   - 回落：非 BOQ 大文件 → None；抽取异常 → None；pages 路径 BOQ → is_boq False。
   - **R1 协同**：`parse_corpus(摘要)` 能解析出页号；模型引「投标总价381574199.97@p2」→ resolved + page **confirmed**（非 page_mismatch）。
2. **pipeline 集成**：大 BOQ → body 是摘要（含投标总价、远小于 8M）；大非 BOQ → 默认头截（行为不变）/ `OCR_TRUNCATE_HEAD_TAIL=1` → 首尾截尾部保留；小文件 → 全量不变。
3. **回归**：`uv run pytest -q` 全绿（R1 644 + 新增）+ `ruff check .`。
4. **R2024-007 dogfood（BOQ 纳入，本轮重点，走 directory 模式避 prewarm 滞留）**：二建（**含 8417 页 BOQ**）评标：
   - 底稿 BOQ 段是摘要、含 `投标总价 381574199.97`（实测真值，directory 模式新逻辑立即生效）。
   - 模型报价项 basis 有据（引到真总价，非脑补/非失据）。
   - R1 evidence-resolution：模型引的总价在摘要里 resolved（协同不破）。
   - DeepSeek + qwen 各一遍，记报价项 status/score/basis + 是否引到真总价 + 耗时 + 上下文规模对比（含 BOQ 前后）。
5. **零误伤**：含 BOQ 后评标不崩、不超时（摘要使上下文远小于全量）。

---

## 六、实施顺序（TDD）
1. 写 `test_boq.py`（红）。
2. 实现 `server/ocr/boq.py` 至绿。
3. 改 `build_extraction_block` + `_truncate`(env-gated head-tail) + pipeline 集成测试。
4. 全回归 + ruff。
5. R2024-007 dogfood（含 BOQ，directory 模式）× DeepSeek/qwen → 回写自测结果 + 进度。

## 七、设计审查记录（impl 前）

| 审查者 | VERDICT | 关键 findings | 处理 |
|---|---|---|---|
| critic（ultrathink） | NEEDS_REVISION | F1[P0]金额正则排除整数总价；F2[P0]prewarm 旧 ocr_text 滞留；F3[P1]pages 路径 BOQ 格式不同；F4[P1]摘要页锚点须独占行(破 R1)；F5[P2]摘要超 MAX；F6[P2]截断标记格式 | **全修**：A2 两档(整数总价)；§四 prewarm 缓解+dogfood directory；§三 pages 留 R3；A3 页锚点独占行；A3 MAX_BOQ_SUMMARY_CHARS；B 截断标记无页锚字样 |
| codex exec（read-only grounding） | REWORK | P0#1 根因表述矛盾(总价在 p2 头部非尾部丢失)；P0#2 prewarm 滞留(同 F2)；P1#3 页锚点(同 F4)；P1#4 table 段无页号张冠李戴；P1#5 投标总价多候选选择规则不硬；P2#6 head-tail 跨域回归(非严格优于) | **全修**：§一 WHY 重写(噪音淹没+97%未见+上下文浪费+尾部变体，非"尾部丢失")；A3 候选打分+全候选并列；A3 table 段页号 None；B head-tail env-gated 默认关 |

> codex 另确认：金额逗号格式非 blocker（R1 `normalize_text` 去逗号 → `381574199.97`/`381,574,199.97` 同串）。两轮无残留 P0/P1，可进 impl。

## 八、自测结果（impl 后回填）
_（待回填）_

## 九、进度回写（impl 后回填）
_（待回填）_
