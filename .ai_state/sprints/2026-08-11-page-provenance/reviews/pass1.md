# Review Pass 1 — 2026-08-11-page-provenance (H2)

审对象：worktree agent-a4910ffcb97ec7942，6 commits（基线 4d0a54c，审查用 merge-base diff 排除
H1 干扰）。reviewer 实跑：NO_NEW_FAILURES 成立（33 条基线逐条一致）、collect 1230、ruff 净；
前端三件由主 agent 装依赖后补跑全绿（167 pass / build ✓ / eslint 净）。

## VERDICT 预判：REWORK（evaluator 待 pass2）

## Findings（reviewer）

- **F1 [P0] tdd-evidence 证据落盘缺失**：实测仅 1/7 AC 有记录（AC1b），AC1-AC6 六条零记录。
  测试代码真实存在且复跑绿（非伪造绿），但门禁要求逐 AC 八字段。修法：逐 AC 补真实红绿记录；
  确属先实现后补测的按 backfill 记法显式声明，不得编造 red。
- **F2 [P0] 回查闸跨文件误纠**（evidence.py:78-82 + corpus.py:479-487）：`locate_quote_pages`
  全文件域找 quote，全局唯一命中即改写页号但 source 文件名不动 → 产出底稿中不存在的出处且标
  page_corrected 正面状态。修法：只在 source 点名文件范围内找唯一命中（复用
  `_source_mentions_file`），跨文件/未点名 → page_unverified 不改写；补跨文件误纠红测。
- **F3 [P1] rag.py 生产点未收拢**：`_format_page_anchor` 硬编码 `【第 M 页】`，RAG-slim 链路
  converted 页号继续冒充原文档页；区间锚 `【第3-5页】` 协议不认。修法：走 corpus 单点 +
  artifact 传递（docstructure.py:53-55 丢 artifact），或 design 显式豁免。
- **F4 [P1] RESOLUTION_ANNOTATE_RESOLVED=0 时页号被改写但 page_corrected 痕迹消失**
  （evidence.py:160-161）：静默改写无留痕。修法：page_corrected/page_unverified 属异常态，
  无条件写 resolution。
- **F5 [P1] KD2 两个交付物缺失**：ocr-page skill 无 converted 说明且其 ocr.py:23 自有第 6 个
  未收拢解析正则（converted 文件 --pages 过滤返回空，失效场景恰是本 sprint 引入）；audit
  command 义务未同步。
- **F6 [P1] 部署预告与 architecture 更新缺失**；`latest_architecture_update` 时间戳与事实不符
  （diff 无 architecture 变更却被改新）。
- F7 [P2] page_mismatch 计数三态重复计。F8 [P2] `_render_body` 兼容别名 + reserve 双轮循环
  可读性。golden 锁定面窄（第二 golden 可 defer）。

## Spec Compliance

- KD 矩阵：KD3/KD4/KD5 完全覆盖；KD1 covered（D1 字段名偏离已接受）；KD2 部分。
- **MISSING×5**：M1 report-view 主视图未接转换稿标注（types.ts 缺 page_kind、getEvidenceSources
  直出裸 source）；M2=F5 skill；M3=F5 audit command；M4=F6 部署预告；
  **M5 未 rebase H1（合并阻断项）**——共享契约文件（schema/tender-evaluate.md/model.ts）main 侧
  已被 H1 改动，现状合并必冲突或回退 H1。
- EXTRA×3 全合理（draft_render 预授权 / docstructure 跟改 / helper 抽取），scope creep=0。
- DEVIATED：D1 接受；D2 AC1 端到端降级为合成 dict（真实 LibreOffice 转换链路无端到端）；
  D3 corpus.py 321→526、evidence.py 370→456 越 300 线无豁免（基线核对不完整）。
- 附注：AC4 的 page_corrected 落盘受 RESOLUTION_ANNOTATE_RESOLVED 门控（=F4）。

## 自报偏离评估

①file 键复用：接受。②cloud_seq 落 pipeline：接受，但 artifact 枚举降维成 page_confidence 布尔面
需记一句偏离，且 OpenAI 兼容路径不受守卫保护（INFO）。③draft_render 拆分：接受且正解。

## Pass 2 返工清单（发 generator）

必修：F1（证据补录）、F2（跨文件误纠）、M5（rebase H1 + 共享契约复核）、F3、F4、F5/M2/M3、
F6/M4（部署预告 + architecture 记录或回退时间戳）、M1、D3（拆分或豁免记账）。
酌情：D2（AC1 用真 fixture 跑通 convert 链路端到端，若 LibreOffice 不可得则显式标注环境限制）。
留 polish：F7、F8、第二 golden。
