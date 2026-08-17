# Review Pass 3 — 2026-08-17（范围 aa08c4e..HEAD：第二波 + S5/S6/S7/S8 + 死代码清理 + 提示词收敛）

- 流程：reviewer + spec-compliance 并行（只读，前台返回）→ 主 agent 合并本档 → evaluator 追加 VERDICT
- 基线 review：impl-pass2.md（PASS，落在 923b4cb）；本 pass 覆盖其后全部改动（37 commits，86 文件，+6592/−872）
- runtime-verify：Refactor 路径义务，E2E/真标书部分明确 deferred 至部署机窗口（AC16/AC7，tdd-evidence 有档），单元/子集层实测在案
- 主 agent 合并注记：spec-compliance 的 M2（S6 八字段补记）与 M3（AC13 后半并入 AC16）已在本 pass 合并前闭合
  （tdd-evidence `s6_kd7` 补记 + design S7 实施修订④）；M1 的全量回归在 evaluator 运行时进行中，结果落
  tdd-evidence `s7_full_regression`（见 evaluator 后附）。E3/E4 待用户拍板。

---

## Reviewer Findings（独立只读审查）

### F1 [P1] 证据层路径下，出处回查闸的文件归属被检索顺序打乱（跨文件误归属）
- File: `server/tender/runner.py:258`（`"evidence_source": ocr_block`）、`server/tender/evidence_retrieval.py:35-38`（`EvidenceBlock.render`）、`server/common/corpus.py:299-336`（`flush()` 仅在 `cur_file is not None` 时产段）
- 问题：走证据层时 `ocr_block` = 证据块拼接文本，块之间**按检索顺序**排列，而 `parse_corpus` 是**流式状态机**——遇到 `### 文件: X` 后，其后所有页锚都归到 X，直到下一个 `### 文件:` 行。证据块来自不同 chunk，`### 文件:` 行是否落在某个 chunk 里完全取决于切分位置。实测：`【投标文件·__bid__】【第 10 页】` + `### 文件: 投标文件.pdf` + 两页 → parse_corpus 得 2 段全归 `投标文件.pdf`、tier 退化 `whole`。只要某个招标块排在含 `### 文件: 投标文件.pdf` 的块之后而自己不带 file 行，它的 `【第N页】` 就会被归到投标文件名下。`evidence.py` 注释明写「多家投标各自 `【第N页】` 从 1 重置 → 必须 file 级」，而这里 file 级归属已不再由文档结构决定。tier 亦退化成 `whole`（`__bid__`/`__tender__` 层信息渲染时丢失）。
- 建议：证据块渲染时每块自带 `### 文件: <原文件名>` 头（chunk 保留来源 file 名），或给 `resolve_audit_evidence` 传结构化 `(file, page, text)` 段；至少补一条「证据层 context 过 `parse_corpus` 后每段 file 与来源块一致」的测试。

### F2 [P1] hit-stop 在「下一个命中块超出前瞻额度」时把已取到的续接整批丢弃，AC14 修复只在小语料成立
- File: `server/tender/evidence_continuation.py:40-54`（`_walk_following` 预算耗尽 → `return picked, False`）、`:102-103`（`return picked if stopped_at_hit else _bounded_by_layout(...)`）
- 问题：`used >= budget` 即返回 `stopped_at_hit=False` → 走 `_bounded_by_layout`；命中块标题不被识别（正是 AC14 语料前提）时 `boundary is None` → 返回 `[]`，**已取到的正文全部丢弃**。实测（AC14 语料中间块 ~2.8K→~14K 字）：`rep=200` item_tokens 2873 / 续页在注入 ✅；`rep=1000` item_tokens **28** / 续页不在 ❌——证据从 2873 掉到 28 token，正是 S7 声称根治的「变薄且无痕」。生产口径 `per_item ≈ 6.6K` token，真实投标 163K 字 / 9 项，相邻命中块平均间隔远大于 6.6K，**该兜底路径是常态而非极端**。
- 建议：预算耗尽时保留已收集块（截到额度为止）；补测试「邻项命中块落在前瞻额度之外时续接不得归零」。

### F3 [P1] 提示词取材/出处纪律建立在「`### 文件:` 底稿」形态上，与证据层实际注入形态不符
- File: `.claude/commands/tender-evaluate.md:8`、`:14-19`、`:27`
- 问题：S0「文件清单从 `### 文件:` 行读取」在证据层注入形态下不可执行（该行是否出现取决于切分巧合）；出处纪律要求「文件名+第N页+章节」而 `EvidenceBlock.render` 抬头 `【投标文件·<chapter_path>】【第 N 页】` **无文件名**（直接影响 F1 回查闸与 `page_corrected` 纠偏）；`:8`「底稿即全部材料」与证据层头部「未出现不等于未提供」（`evidence_context.py:29-34`）口径相反。
- 建议：命令补「证据片段形态」的取材/出处规则，或服务端在证据块抬头补真实文件名后统一口径。

### F4 [P2] 死代码清理留下孤儿类方法与 Protocol 声明
- `review_delta_store.py:71,101,109,165`、`result_store.py:48,144`、`request_store.py:46,109`：模块级 wrapper 已删但类方法与 Protocol 条目留存，现无任何调用方（全仓核验 `.list_records(` 只剩 `memory_store.py:230` 一处在用）。建议同轮删除或显式记保留原因。

### F5 [P2] `UnresolvedItem.hit_count` 恒为 0 的死字段 + 永真断言
- `evidence_retrieval.py:41-47`（定义）、`:238`（唯一构造点不传）、`tests/test_tender_evidence_index.py:205`（`assert == 0` 永真）。建议删字段与断言。

### F6 [P2] 跨模块访问私有函数
- `doc_context.py:231` 调 `doc_layer._parse_stored_criteria(...)`。建议公开命名或下沉。

### F7 [INFO] `chunks_per_item` 生产口径恒为 1
- `injection_budget.py:144-152`：9 项时 `6653//4000=1`，每项 1 个候选块，证据量全依赖续接——放大 F2 影响。记录为观察（AC16 deferred 已涵盖）。

### 分领域「已查无 findings」
两遍式 stop_ids 与逐项组装一致性、跨项去重、闭式账目（`Σ item_tokens == total ≤ 额度` 有测试咬）；S8 层序与留痕；security（SQL 占位符 / LIKE 转义 / FTS5 phrase 转义、无 subprocess 新增）；契约形态（`ocr_warnings` 在 `additionalProperties: true` 的 `extracted_data` 内）；死代码删除本身（11 符号全仓零引用）；测试质量（语料前提守卫模式，永真仅 F5）；提示词决策表自洽（矛盾仅 F3）。

---

## Spec Compliance（独立核对）

（逐条对照表全文见本节，结论先行：**功能覆盖 FULL，证据覆盖 GAPS**）

- S5 KD6-a/b/c/d + AC9/10/11：实现+测试齐，真标书数字为 S5 时点（tdd-evidence s5_kd6）。AC12 部分：ruff 复跑净；全量见 M1。
- S6 KD7 + 度量脚本去项目化：齐；AC13 前半齐（dry-run 第六轮），后半见 M3。
- S8：投标层优先 / 兜底两情形（以投标层零命中统一判据）/ SQL 限层 / 语料前提守卫，全齐（tdd-evidence s8_bid_layer_first 真红）。
- S7：两遍式 stop_ids / hybrid（按实施修订口径）/ AC14 真红 / AC15 穿透到最终 payload，全齐；AC16 显式 deferred + 口径警告。HEAD 复跑证据层 7 文件 160 passed。
- **M1**：S8 `5e083c7` 与 S7 `2d8f434` 后无全量回归记录（仅子集 204/207）→ NO_NEW_FAILURES 在 HEAD 未取证。【主 agent 注：已在跑，结果后附】
- **M2**：S6/KD7 缺八字段轮次 →【主 agent 注：已补 `s6_kd7`（补记记法，红绿皆当日真实实测）】
- **M3**：AC13 后半 8 项逐项比对未留档 →【主 agent 注：已记 design 实施修订④，并入 AC16 部署窗口】
- 显式 deferred 合规：AC16 / AC7 10 分钟 E2E / AC9-10 重测，均有落盘记录，无假装完成。
- EXTRA：E1 提示词收敛（compound 决策档为据，成立）；E2 死代码清理（explore 档+用户拍板为据，成立）；**E3** 第二波约 10 个 commit（contract_repair.py + 仲裁收敛等）无 design 锚点，非 scope creep 但需表态（补 design 增量 or 记已接受范围外交付）；**E4** 三条测试语料含真实项目痕迹（`直播间总体方案设计`/`青岛诺德中心`/`4.8.类似业绩`，tests/test_tender_evidence_index.py:371,553,612），项目数据纪律未枚举测试但性质相同，需用户确认豁免或匿名化。
- DEVIATED：0（S7 hybrid 偏离已双处归档且在 critic 预授权内）。

**Spec Compliance 总评：GAPS**（M1/M2/M3 均为取证缺口，功能均有实现+单元测试；解锁清单见上，M2/M3 已闭、M1 进行中）

---

## Evaluator（Evidence Cross-Check + VERDICT）

**VERDICT: CONCERNS**

核证：F1–F7 与 E4 逐条 **CONFIRMED**（对照主 checkout 实码：F1 链路 `doc_context.py:127-129` → `runner.py:167,258`，块抬头无 `### 文件:` 行；F2 `_walk_following` 预算耗尽 `return picked, False` → `_bounded_by_layout` 在 `boundary is None` 返 `[]`，已收块整批丢弃属实，生产口径 per_item≈6.6K 使该路径为常态；F3 三处口径矛盾均在；F4 全仓 `.list_records(` 仅 `memory_store.py:230` 在用；F5 永真断言在 `tests/test_tender_evidence_index.py:205`；F7 `6653//4000=1`）。

Done Contract 对照：AC14/15（s7_hit_stop 真红）✅；AC9/10/11（s5_kd6，S5 时点）✅；AC13 前半（s6_kd7 补记，合规 backfill）✅；S8（s8_bid_layer_first）✅；AC16/AC7/AC0b 显式 deferred（合规非假过）✅；**AC12/AC8 NO_NEW_FAILURES @HEAD：`s7_full_regression` 评估时点未落档（M1 未闭）**。`done_without_evidence = 0`。

判定理由：无 P0，不及 REWORK；F1/F2/F3 三条 P1 CONFIRMED 未解决（≥3 P1 → CONCERNS）；F4/F5 属未解决可删死代码（unresolved over-engineering 上限 CONCERNS）；M1 未落档 → Sisyphus 不完整。

**pass4 前必须闭**：① F2（预算耗尽保留已收块 + 「超前瞻额度续接不得归零」测试——评分正确性缺陷，不得 defer）；② F1+F3 合修（同根：证据块携带真实文件名 / 回查闸结构化段 + 命令侧取材出处口径 + `runner.py:255` 失真注释 + 逐段 file 归属测试）；③ M1（`s7_full_regression` 落 tdd-evidence）；④ E4 用户拍板（测试语料匿名化 or 显式豁免）；⑤ E3 用户表态（第二波补 design 锚点 or 记已接受范围外交付）。
**defer 至 polish**：F4 / F5 / F6。**随 AC16 窗口**：F7。

Sisyphus：已完成项均有真红转绿；AC16/AC7 合规 deferred；须 pass4 PASS 才进 polish。

---

## 修复轮追记（主 agent，2026-08-17 深夜）

### F2 已修并合入（`09343a2`+`e07e067`，merge 见 main）
`_walk_following` 把「前瞻额度用尽」归位成**合法终点**（与撞上 `stop_ids` 同级），`_bounded_by_layout`
职责一字未动、退为「未耗尽额度就走完整份文档」时才管边界。真红先于实现取得并二次复现
（复现用 `git show HEAD:… >` 覆盖而非 `git stash`——`refs/stash` 全仓共享，会与并行 worktree 抢栈）。
脱钩守卫非空过：40 页/400 页两份投标注入量同为 88 token（比值 1.0，要求 ≤1.2）；额度即上界的
直接测量：同语料 gap 取 1/6/20 页（底稿 6,450→59,802 字，9.3 倍）该项 `item_tokens` 恒 4,825。
证据落 tdd-evidence `pass3_f2`。

**主 agent 复核 `truncated` 口径判断（修复者请求复核）**：接受。`truncated` 语义仍为「有命中却
一块都没进注入」；「吃满自己额度」刻意不记 truncated——生产口径下几乎每项都会吃满，记进去会把
该信号变成常态噪音，且与 `test_额度充足时没有任何项被记为truncated` 反向守卫对冲；既有 hit-stop
路径被 `_assemble_item` 按 per_item 截断时同样不记，口径一致。该形态由 `item_tokens` 逐项账留痕
（AC15 本职），账目闭式由新测试末两条断言咬住。

### F8 [P1，新发现，本轮不修] 单块超过每项额度时续接完全不发生
- 来源：修复 F2 时查清 reviewer 原 repro（单块 14K 字）修复后仍为 2,018 token——**机制不同，不属 F2**。
- 机制：`split_oversized_chunks` 按行切，遇到**整行无换行的超长文本**切不动 → 单 chunk 远超
  `_assemble_item` 的每项额度 → 首块之后即 break，续接完全不发生。
- 触发条件有二，第二条是常态风险：① 单行 > `MAX_CHUNK_CHARS`(4,000)，OCR 表格丢换行即可产生；
  ② **`criteria` 评分项数 ≥ 15** 使 `per_item = evidence_tokens / n_items < 4,000`，此时任何满尺寸
  chunk 都装不下（20 项时 per_item ≈ 2,994）。真实标书 15+ 评分项常见，而本 sprint 全部实测用的是
  9 项的那一份——**该形态从未被真实数据覆盖**。
- 与 **F7 同根**（`chunks_per_item = per_item // MAX_CHUNK_CHARS` 恒为 1）：都是「每项额度 vs 单块尺寸」
  的量纲冲突。
- 后果与既有信号：该项仍能拿到首块（不归零、不静默），且 `item_tokens` 会显示其偏小——AC15 使其
  **可见**，故不构成 pass3 那类「变薄且无痕」。
- **本轮不盲修的理由**：候选修法（A 允许不可分单块借用全局额度 / B 超长行按字符数兜底切分 /
  C 视为固有约束）各有代价，其中 A 会破坏刚建立的闭式账目不变量。**应在 AC16 部署窗口用真实
  多评分项标书测出实际形态后再定**，而非凭合成语料盲改。已并入 AC16 任务清单。
