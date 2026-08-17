# 开放决策① · Critic 简评审（design S7 前置）— 2026-08-17

- 评审者: critic subagent（独立 context，只读）
- 对象: 续接边界去排版化（候选 A：hit-stop / 候选 B：现状+warning / 候选 C：额度硬上限）
- 材料: handoff §二/§四③、design S5（KD6-c）/S6、compound retrieval-quality learning、
  `evidence_retrieval.py`（`_continuation`/`_starts_sibling_section`/`retrieve_evidence` 单遍循环）、
  `evidence_chunks.py`（`_DECIMAL_HEADING_RE` 双职责）、`rag.py`/`rag_store.following_rows`、
  `injection_budget.py`（`chunks_per_item ≈ 1`）、两个证据测试文件用例清单

## VERDICT: 推荐 A（修正版）——采纳 hit-stop 边界，砍掉「顺带删 `_DECIMAL_HEADING_RE`」的过度捆绑，附数据闸

**Q1 可行性**：现状逐项单遍（`retrieve_evidence` for 循环内 `_search_item` → 立即
`_assemble_item`），续接时无其他项命中的全局视图 → A 必须两遍式。但检索与组装无共享状态
（`seen` 账本只在组装期，`plan_injection` 在循环前已定），拆成「先全项检索收集 `stop_ids`、
再逐项组装」是干净改造，集中在 `evidence_retrieval.py` 单文件约 30–50 行；S6 回退在第一遍
内完成，无冲突。**可行，改动面小。**

## Findings

### F1 [P0] 「可顺带删 `_DECIMAL_HEADING_RE`」不成立——它有第二消费者
- 该正则同时服务续接边界（`heading_rank`，A 后消失）与 **KD6-a 切片标签重推**
  （`slice_heading` → `_slice_chunk`，AC9 已评审已 ship）。
- 反例：删正则后 `chapter_path` 回退继承祖先链，`4.8.类似业绩` 重新渲染成
  `【…雷击事故应急预案】【第317页】`——正是 compound learning 里「出处标签独立失败面、
  回查闸失据」那次误判的成因；`EvidenceBlock.render()` 仍把 chapter_path 打进出处行，
  不删 relabel 就是渲染谎报标签。
- 处置：A 只删 `heading_rank` + `_starts_sibling_section`（孤儿），**保留**
  `slice_heading`/`_DECIMAL_HEADING_RE` 与 `test_切片标签跟着自身小节标题走`。
  按 handoff「标签不在规格里」降级为 file+页码属独立决策：须同时改 render、回退 AC9，
  **需用户拍板，不得夹带**。

### F2 [P1] A 不自动满足 AC2——它自己也有静默变薄面
- 反例三种：① 邻项 unresolved 或命中在节中部 → 边界后/前移；② 噪音命中制造伪边界提前
  截断；③ 末项之后无停止点，只剩预算收口吃附件（`chunks_per_item≈1`，停止点全库仅
  ~9–14 个，稀疏是常态）。三者都无痕。
- B 的 warning 只覆盖「正则没认出」一种原因且不恢复证据，治标；正解=**逐项注入量留痕**
  （`item_tokens` 已在 `_assemble_item` 算出，装进 `EvidenceResult` 进底稿），
  覆盖 A/B 全部变薄原因。此项 A/B 通吃，必做。

### F3 [P1] A 的边界质量依赖招标抢位先修（handoff §四② 顺序不可倒）
- 反例：basis 指向招标章节的项 top-1 是招标块时（抢位现症），该项在投标文件内贡献不了
  停止点——hit-stop 的「天然分段」出现空洞。
- 合入前用 `scripts/measure_tender_evidence.py` 真标书对比 A vs S5 基线，9 项逐项注入
  字数 + AC10 内容抽查不得回退；数据闸不过 → 回补 sibling-stop 作第二边界（hybrid），
  而非放弃 A。

### Q4（候选 C）否决
现状已有双兜底（`_continuation` per-item 前瞻预算 + 全局闭式账）；「额度自然收满即停」
= 预算内实测吃进「类似业绩」39 块的已否形态；chunk 数硬上限 = 新魔法常量（样本拟合换
马甲）。边界正则相对预算的真实增益只有「让额度花在本节内」——hit-stop 以零排版假设提供
同一增益（第四轮实测 4 个命中块全是小节标题块，两种边界重合）。

### P2 备注
`_starts_sibling_section` 的 formal 分支（第X章/一、）非样本拟合（全局 `chapter_heading`，
跨文档惯例）——「零排版假设」指控只对 decimal 分支成立；minimal A 先行，数据闸兜底。

## 实施要点与必保测试（若实施 A）

1. 两遍式 + `stop_ids`（全项命中并集）；`_continuation` 删 rule-1 前提与 sibling 判定，
   改查 `chunk_id in stop_ids`；budget 前瞻、`has_substance` 跳过、跨项去重、`truncated`
   语义全部不动。
2. 真红测试：「编号风格不被识别但邻项有命中」语料——旧代码静默不续接（缺陷复现），
   新代码续接且止于邻项命中块。
3. 改写 1 个：`test_续接止于同族同级的下一小节` → hit-stop 语义。
4. 必保（`tests/test_tender_evidence_index.py`）：`test_命中小节标题时续接后续正文`、
   `test_单项续接不得吃光全局额度`、`test_无实质内容的块不作为证据注入`、
   `test_切片标签跟着自身小节标题走`、`test_额度耗尽的项被记为truncated而不是静默消失`、
   `test_跨项去重按chunk_id`、S6 三件；（`test_tender_evidence_wiring.py`）
   `test_evidence_context_actually_injected`、
   `test_evidence_unresolved_warning_reaches_final_payload`；
   handoff 点名的 `test_basis_指向招标章节的项带出招标chunk`。
