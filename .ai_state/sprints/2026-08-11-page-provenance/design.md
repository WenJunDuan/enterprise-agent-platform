---
sprint_slug: "2026-08-11-page-provenance"
path: "System"
created: "2026-08-11"
last_updated: "2026-08-11"
executor: "generator subagent model=opus, isolation: worktree (红区)"
---

# Design — H2 页锚溯源：page-provenance 字段 + 转换页透传 + 截断按锚切 + 表格带锚

## 背景

实跑症状"证据链页码与文档实际页对不上"。根因（2026-08-11 评审，主 agent 抽查坐实）：

- **转换页无人知情**：Office→PDF 后页锚 = 转换稿 PDF 页号（LibreOffice 分页 ≠ Word 分页），
  `converted_from` 全仓仅 pipeline.py:486 一处写入、零处读取；底稿文件头（pipeline.py:729-747）、
  评标 prompt、前端都不知道页号属于一个已销毁的临时渲染物。页锚契约"页号属于哪个 artifact"
  维度缺失——这是 0730 convert 路径合入后的契约破裂点（架构评审病根 1）。
- **截断锚点错挂**：`_trim_context_block`（context_slim.py:87-98）按字符硬切 head 2/3 + tail 1/3，
  tail 段截断点到下一锚点之间的内容在模型视角归属 head 末锚（早得多的页）；锚点行可能被切半。
  评标主链路无条件套用（runner.py:265-267）。大标书必触发，是与症状最吻合的主链路机制。
- **表格归末页**：`read_pdf_text` 收集 tables 丢页号（native.py:277-294），表格文本无锚拼在底稿
  末尾（pipeline.py:645-664）→ 模型按"最近锚点"把任意页的表格引成最后一页，且回查闸判 confirmed。
- **回查不救**：`page_mismatch` 只计数不纠正不降级（evidence.py:96-99），错页畅通进结论。
- 次级：云 OCR 页号按结果顺序枚举无守卫（engine.py:743-759，跳页即全局平移）；native word/excel
  路径整份无锚但 prompt 硬要求"第N页"（模型只能臆造）；多文件袋内页号各自从 1 重置的出处歧义。

## 目标

1. 每个页级单元携带显式溯源：页号属于哪个文件、哪个 artifact（原件/转换稿/子集/云序号）。
2. 转换稿页号在底稿、评标 prompt、最终结论、前端展示全链路如实标注，不再冒充原文档页。
3. context 截断不再制造锚点错挂；表格文本带真实页锚。
4. 回查闸对可纠正的页错就地纠正，不可纠正的显式降级标注。
5. 无页概念的 native 路径（word/excel 文本直读）不再逼模型编页号。

## 非目标

- 不做 doc-structure schema 全量重构（那是 OCR 独立服务 API 契约，见 compound/2026-07-20 决策；
  本 sprint 只做单元级字段 + 渲染/解析双端的最小前铺，字段命名与该决策对齐以便未来平移）。
- 不改多文件"袋内各文件页号从 1 起"的既有语义（出处歧义靠 source 必带文件名约束收敛，已是
  prompt 义务；本 sprint 只加 file_ambiguous 的回查降级）。
- 不动 OCR 识别质量与路由梯本身。

## 已调研的现成方案

页锚溯源是本系统底稿格式的内部契约，无现成组件可替代（检索范围：PyMuPDF 页对象模型、
unstructured/docling 的 element metadata——后两者的 `metadata.page_number` 证实"页级 provenance
字段"是行业通行做法，但引入整库替换抽取层远超本 sprint 范围且与 0730 刚验收的路由梯冲突）。
结论：自研单元级字段，字段语义对齐 docling 的 page provenance 惯例（origin + page_no）。

## 关键决策

### KD1 · 页单元 provenance 模型

extract 单元（pipeline.py:145-151 的 units 已有 `page: int|None`）扩展为：

```
{page: int|None,            # 语义改为 original_page：用户可回查的原文档页号；不可回查=None
 artifact: "original"|"converted"|"subset"|"cloud_seq",
 artifact_page: int|None,   # 页号在 artifact 坐标系里的值（subset 回填后与 page 相同）
 source_file: str}
```

- `original` (pdf 直读/图片/逐页渲染)：page = artifact_page，现状不变。
- `converted` (Office→PDF)：artifact_page = 转换稿页号，**page = None**（原 docx/xls 无可靠页映射，
  如实置空，不猜）。
- `subset` (混合 PDF 抽页)：回填后 page = 真页号（现有守卫保留）。
- `cloud_seq`：加守卫——classify 已产出 page_count（pipeline 侧可得）与云返回页数不一致时，
  整份标 `page_confidence=low` 并 warning，页号仍按序钉但降级处理（见 KD5）。

`【第N页】` 降级为渲染格式：page 非空渲染 `【第N页】`；converted 渲染 `【转换稿第M页】`；
两者皆无不渲染锚。corpus.py 两个解析正则同步识别 `【转换稿第M页】` 变体并在 parse 结果上带
artifact 标记。

### KD2 · 转换稿语义贯通

- `build_extraction_block` 文件头渲染 `converted_from`：
  `### 文件: 投标文件.docx (route=convert, 已转换为PDF识别, 页号为转换稿页号)`。
- `tender-evaluate.md` / `audit` prompt 补充义务：引用转换稿证据时 source 写
  `文件名 转换稿第M页`，并在结论 evidence_chain 的该条目带 `page_kind: converted`。
- audit-result schema 的 evidence 条目增可选 `page_kind: "original"|"converted"`（缺省 original，
  存量兼容）。前端 model.ts source 解析同步识别并显示"转换稿第M页（原文档页号不可用）"。
- ocr-page skill 文档注明：对 converted 文件核锚需先经同参数 LibreOffice 转换（同版本容器内
  确定性可复现），不能直接翻原件。

### KD3 · 截断按锚切

`_trim_context_block` 重写切割规则：

- head/tail 切点吸附到**页锚行边界**（切点向前回退到最近锚点行首；锚行永不切半）。
- tail 段起始处**补插当前页锚**：取 tail 首内容所属页（从被切段向前扫描最近锚点）在 tail 开头
  重放该锚，消除"tail 内容挂到 head 末锚"的错挂。
- 找不到任何锚的块（native word 等）按现状字符切，但截断 marker 文案注明"本文件无页锚"。
- `_truncate_body`（pipeline.py:699-712，OCR_TRUNCATE_HEAD_TAIL=1 路径）同规则同修。

### KD4 · 表格带锚

`read_pdf_text` 的 find_tables 收集时保留页号（当前循环里页号在手，只是丢弃）；`_render_body`
把表格文本渲染进**所属页锚之下**（与该页正文相邻），不再统一拼尾。表格与正文重复的现状保留
（模型侧有用），但都在正确页锚下。

### KD5 · 回查闸升级

`evidence.py` 对 `page_mismatch`：quote 唯一命中某页段时**就地纠正** source 页号（结论以底稿
坐标为准），并在 evidence_chain 该条记 `page_corrected: {from, to}`；多处命中或 `file_ambiguous`
→ 不猜，该条降级 `resolution: page_unverified` 且计入结论 warnings（不再静默）。
`page_confidence=low`（云守卫触发）的文件整体：其证据页号全部标 page_unverified。
native 无锚文件：source 只要求文件名、不要求页号——**义务落点是 prompt（tender-evaluate.md 的
source 产出规则）与回查闸，不是 schema**：evidence_chain 条目本无独立 page 字段（页码内嵌
source 字符串，且 additionalProperties:false，Round1-P2 措辞校正；KD2 的 page_kind 可选字段
才是本 sprint 唯一的 evidence 条目 schema 变更）。回查按
文件级 quote 命中判定——消灭"逼模型编页号再拿臆造值当 confirmed"（corpus.py:283-291 的
window=1 对 key=0 段判 confirmed 的分支同步修掉）。

## 影响范围

```text
server/ocr/pipeline.py        KD1 单元字段/渲染, KD4 表格渲染, KD2 文件头（基线 791 行已越线，
                              豁免：渲染逻辑如净增 >40 行则拆 server/ocr/draft_render.py）
server/ocr/native.py          KD4 页号保留
server/ocr/engine.py          KD1 cloud_seq 守卫（基线 887 行已越线，豁免：只加守卫数行，
                              拆分并入 OCR 服务迁移）
server/common/corpus.py       KD1 解析变体, KD5 key=0 分支
server/tender/context_slim.py KD3
server/tender/evidence.py     KD5
server/tender/runner.py       穿参（如需）
.claude/contracts/common/audit-result.schema.json  KD2 page_kind / KD5 page 允许空
.claude/commands/tender-evaluate.md, audit 相关 command   KD2/KD5 义务
.claude/skills/ocr-page/      KD2 说明
agent-front/.../model.ts, report-view.tsx 等        KD2 展示
tests/test_ocr_pipeline.py, test_ocr_native_formats.py, test_tender_*  全 KD 红→绿
```

## 已验证基线（2026-08-11 主 agent 实测）

- 全量测试收集数 = 1162（`uv run pytest --collect-only -q | tail -1`）。
- `server/ocr/pipeline.py` = 791 行、`server/ocr/engine.py` = 887 行、
  `server/tender/context_slim.py` = 284 行（`wc -l`）。前两者基线已越 300 线，豁免见影响范围节
  （上界：净增 ≤60 行**仅限 pipeline.py / engine.py 两文件**，超出即拆新模块；corpus/evidence
  的上界以下方"基线补记与豁免"表为准，两处并存不矛盾——pass2-N1 澄清）；context_slim 改后须 ≤300。

### 基线补记与豁免（review pass1 D3，2026-08-11 补测）

design 初稿漏核两个被改文件的行数基线，补记如下（`wc -l`，基线 = main@4d0a54c）：

| 文件 | 基线 | 本 sprint 终值 | 判定 |
|---|---|---|---|
| `server/common/corpus.py` | 321 | 543 | **豁免**，上界 560 |
| `server/tender/evidence.py` | 367 | 473 | **豁免**，上界 490 |

两者**基线即已越 300 线**，按 coding-standards「量化验收标准必先核基线」属"基线已越线的对象"，
本 sprint 显式记豁免而非落笔即不可达的门槛。理由与边界：

- 增量本身是本 sprint 的核心交付、且高内聚：corpus 的 +222 行全部是**页锚字符串协议单点化**
  （协议定义/解析/渲染/按锚切分）——正是为消灭 5 处平行正则而集中到此，再散开等于回退 KD0。
- evidence 的 +106 行是页精度标注的纠正/降级分支（`_annotate_page` / `_corrected_page` /
  `_emit_page_warnings`），与既有回查闸同一职责链。
- **不在本 sprint 拆**的理由：拆分（corpus → `server/common/page_anchor.py`、evidence →
  `evidence_page.py`）会改动 8 个 import 点，属纯结构变更，与本 sprint 的行为修复混在一个
  review 周期里会让 diff 失焦；且拆完两文件仍分别约 390 / 385 行，仍需豁免，收益不改变判定。
- **承接**：拆分列为 polish/后续 sprint 动作；超过上述上界前必须执行。

## 风险与缓解

- 底稿格式变化影响缓存：单元结构变更 → OCR cache 版本 v5→v6 随行 bump（部署后每文件重跑一次，
  与 0730 v4→v5 同语义，写进部署说明）。
- `【转换稿第M页】` 新锚变体是跨"6 生产点/5 解析点"的字符串协议扩面：解析端全部走 corpus.py
  单点正则（先收拢再扩展——本 sprint 顺带把 boq.py:36 / context_slim.py:43 / **pipeline.py:604
  `_PAGE_ANCHOR_PATTERN`** 的独立正则替换为 corpus 导出的公共 pattern，消灭平行解析点）。
  pipeline.py:604 是 `is_ocr_text_valid` 剥锚行判有效的依据，漏收拢则"仅含转换稿锚的空底稿"
  会被判有效假 ready（Round1-F4，0730 教训"只有页锚必须失败"的直接回归风险）。
- converted 文件 `original_page=None` 是**用户可见行为变化**（此前显示的是冒充原文档页的转换页
  号），部署说明须预告（Round1-P2）。
- 评标 prompt 放开"native 无锚文件页号可空"可能被模型泛化到有锚文件 → prompt 用条件句 + 回查闸
  对有锚文件页号缺失照旧 page_mismatch 处理，双向夹住。

## 验收标准

- [ ] AC1 转换链路：docx fixture（scripts/document_format_fixtures/sample.docx）走 convert →
  底稿文件头带转换声明、锚为【转换稿第M页】、结论 evidence 带 page_kind=converted、前端显示
  转换稿文案。原件路径（pdf/图片）输出与现状逐字节一致（golden 对比，防无关回归；golden
  fixture 须声明**不含表格**——含表格文件的输出按 KD4 有意变化，另测不入 golden，Round1-P2）。
- [ ] AC1b 有效性守卫：仅含【转换稿第M页】锚行、无正文的底稿 → `is_ocr_text_valid=False`
  （Round1-F4 单测，锚变体纳入剥除集的直接验证）。
- [ ] AC2 截断：构造 head/tail 切点落页中与落锚行中两种 fixture → tail 首行为重放锚；任何输出中
  不存在被切半的锚（正则扫描 `【第\s*\d*$` 类残片=0）；无锚块按现状切且 marker 注明。
- [ ] AC3 表格：多页 PDF 含中部页表格 → 表格文本出现在所属页锚之下；底稿末尾无游离无锚表格段。
- [ ] AC4 回查：quote 唯一命中他页 → source 页号被纠正且记 page_corrected；多处命中 → 
  page_unverified 进 warnings；云页数守卫触发 → 该文件证据全部 page_unverified。
- [ ] AC5 native 无锚：文本型 docx 评标 → 证据 source 无页号且回查按文件级判定；不再出现
  "第1页恒 confirmed"（corpus key=0 分支单测）。
- [ ] AC6 质量门：先红后绿证据齐；`uv run pytest -q` 全绿收集数 ≥1162+新增构成式；ruff 净；
  cache 版本 bump 且带理由注释（补 0730 v5 漏掉的注释惯例）；前端 test/build/eslint 绿；
  部署说明含 converted 页号行为变化预告。

---

## Round 1 (initial draft by Fable 5)

页单元 provenance 字段、转换稿页号如实透传、截断按锚切、表格带锚、回查闸就地纠正。

## Round 1 · Critic Findings

VERDICT: NEEDS_REVISION（三设计合审，本档相关项）

- F4 [P1] 锚变体收拢清单漏 pipeline.py:604 `_PAGE_ANCHOR_PATTERN`，仅转换稿锚的空底稿会假 ready。
- P2: AC1 golden"逐字节一致"与 KD4 表格挂锚互斥，须声明 fixture 无表格；KD5 "schema 放开 page"
  措辞失准（evidence_chain 无 page 字段，additionalProperties:false，义务实际落 prompt+回查闸）；
  converted 页 None 属用户可见行为变化，部署说明应预告。

## Round 2 (revised by Fable 5)

- F4 CLOSED：pipeline.py:604 纳入公共 pattern 收拢清单（风险节改写），新增 AC1b 单测直接验证。
- P2 全部 CLOSED：AC1 声明 golden fixture 不含表格；KD5 措辞校正为义务落 prompt+回查闸、
  page_kind 是唯一 evidence schema 变更；风险节 + AC6 增部署预告。
- 另接受 roadmap 级 F7：合并序 H1→H2→H3，共享契约文件（audit-result.schema.json /
  tender-evaluate.md / 前端 model.ts）在本 sprint rebase H1 后做契约合并复核。
