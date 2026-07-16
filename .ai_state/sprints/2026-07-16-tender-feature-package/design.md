# D2 · server/tender/ feature 包重构 — design【DRAFT / 预研】

> roadmap: 2026-07-doc-intelligence / Wave0 / D2 (tender-feature-package)
> path: **Refactor（红区，server-refactor）** · effort L · 状态: **DRAFT 预研**
>
> ⚠️ **本文档是 D1 收尾间隙的预研草稿，非可直接 impl 的定稿。impl 前置三条**：
> 1. **D1 merge 回 main**——D2 是"纯移动为主"重构，迁移基线必须是 D1 merge 后的 main
>    （D1 已前置迁走评标核心到 server/tender/runner.py、tender_worker 变调度壳、
>    tender_doc_pipeline 改 import、tender_output 加 is_real_number）。本清单基于 D1
>    worktree 当前状态推演，**D1 merge 后须用 rg/wc 精确复核迁移面**。
> 2. **用户拍板 F6 分层决策**（方案 A / B，见下）——决定迁移清单大小与是否有行为接缝。
> 3. **critic 一轮**（红区 System/Refactor 门禁）。
> 4. 红区铁律：generator + `isolation: worktree` 强制。

## 背景（WHY）

2026-07-02 全仓架构评估 P0-1：**tender 域没有 feature 包**，约 3250 行评标逻辑散在
`routes/`（tender_worker/tender_compare_worker/tender_doc_pipeline/tender.py）与
`common/`（tender_output/evidence_resolution）。后果：

1. **分层混乱**：业务逻辑挤在 routes 层（本应只做 HTTP 壳）与 common 层（本应只放跨域
   共享物）。audit/ocr 都有独立 feature 包，唯 tender 没有——D1 已开头（runner.py 落地），
   D2 收全。
2. **22 文件超 300 行红线**，tender.py 单文件 912 行。
3. **D8 底稿瘦身的落点依赖 D2**：D8 要改的 tender_worker 检索逻辑必须先归位 server/tender/，
   否则二次搬迁（items.yaml D8 depends_on D2）。

## 方案

### 迁移清单（基于 D1 worktree 现状推演，D1 merge 后复核）

| 源 | 目标 | 性质 |
|---|---|---|
| `routes/tender_worker.py`（D1 后仅剩调度壳） | `server/tender/worker.py` | 纯移动 |
| `routes/tender_compare_worker.py` | `server/tender/compare_worker.py` | 纯移动 |
| `routes/tender_doc_pipeline.py`（D1 后 TENDER_OCR_PURPOSE 已挪走） | `server/tender/doc_pipeline.py` | 纯移动+接缝 |
| `common/tender_output.py` | `server/tender/output.py` | **取决于 F6** |
| `common/evidence_resolution.py` | `server/tender/evidence.py`（或留 common，见深评#10） | **取决于 F6** |
| `routes/tender.py`(912) | 拆薄为 HTTP 壳 + 按 banner 分节 | 拆分 |

### 🔑 F6 决策（待用户拍板）：tender_output / evidence_resolution 归属

**根因**（已核验代码）：`common/contract.py:252` 末尾 import `output_contracts` →
`output_contracts.py:30-37` import `tender_output` 6 个校验函数 + `:460` import
`evidence_resolution.resolve_audit_evidence` → `:462-470` **全挂在共享
`DEFAULT_OUTPUT_SCHEMA_NAME`(audit-result) 上**。双重耦合：
- **分层**：common(output_contracts) → tender_output/evidence。若直接把这两个模块迁进
  `server/tender/`(feature)，就是 common→feature 逆向依赖，撞 layering 守卫（撞 T5 (d)）。
- **行为**：tender 专属校验（scoring/plan/disqualification 一致性）无条件跑在
  expense/audit 结果上；纯 audit 调用也被 contract.py:252 副作用拉入 tender 模块。

**方案 A（schema 分家，深评 #7 推荐）**
- 注册 tender 专属 schema 处理器：tender 的 6 校验 hook + resolve_audit_evidence 挂
  **tender schema 名**；expense/audit 用纯通用处理器（不再跑 tender 校验）。
- tender_output/evidence 从 tender 模块自己调 `register_schema_processor` →
  可**合法迁入 server/tender/**（feature 自注册，output_contracts 不再 import 它们）。
- 附带修 contract.py:252 import-time 副作用（纯 audit 不再拉入 tender）。
- **代价/风险**：tender_worker/runner 现传 `schema_name=DEFAULT_OUTPUT_SCHEMA_NAME`，
  分家后要改传 tender schema 名——**这是行为接缝，非纯移动**，需 D1 eval 回归闸 +
  针对性测试护航（证明 expense 结果不再跑 tender 校验、tender 结果校验不变）。
- 彻底解分层+行为纠缠，D2 目标"tender 逻辑全归位"达成。

**方案 B（两模块留 common）**
- tender_output/evidence_resolution **不迁**，留 common 层；D2 只迁 worker/compare_worker/
  doc_pipeline + 拆 tender.py。
- **零行为变更、最省事**，但 tender 逻辑仍有一部分留在 common（output/evidence 共约
  ？行），D2"归位"目标打折扣，耦合债留到未来（D7 会再碰 evidence_resolution，见深评#10）。

**主 agent 倾向**：方案 A（一次解干净，与 D1 分层拍板同调；D1 eval 闸正好为这类行为接缝
兜底）。但 A 的 schema 名变更要谨慎回归。**请 D1 收口后拍板。**

### 范围附加项（深评 #8 / #12，随 F6 一并定）

- **#8 worker background job harness**：audit/tender/compare 三 worker 的
  准入闸+强引用集+信号量+超时+三态 upsert 60-70% 同构，第三消费者已在。深评建议
  "D2 tender worker 迁包时顺手抽"。**建议作为 D2 内独立一步**（先纯迁移绿、再抽 harness
  绿，各自 commit），或若 D2 已够大则降级独立 sprint——待定。
- **#12 tender.py 分节**：banner 已就位（:133/223/441/627/854），
  tasks(~250)/projects(~185)/docs(~225)/compare(~60) 拆分低风险，深评评"方案可行"。

### 明确不进 D2（防范围膨胀）

- 深评 #9 stores admin/tenant 双份查询参数化（~150-200 行）→ 独立绿区项，不搭 D2。
- 深评 #5 cache fingerprint 修复 / #6 死代码删除 → D4 首任务或独立绿区。
- 深评 #10 evidence_resolution 匹配内核升格 → D7 起点，不在 D2。

## 影响范围（待 D1 merge 后精确化）

- 移动：server/routes/tender_*.py（3-4 文件）→ server/tender/
- F6=A 时额外：common/tender_output+evidence → server/tender/ + output_contracts/contract
  的 schema 注册重构（行为接缝）
- 测试护航：文件名含 tender 14 个 / 内容引用 tender 25 个（D1 Round 2 F7 实测）+
  test_layering 守卫扩展（server/tender/ 子模块全部纳入）
- 不动：audit 域、ocr 域、expense 域（F6=A 时 expense 校验行为变化须专门验证=不再跑
  tender 校验，属预期改善不是回归）

## 风险与缓解

| 风险 | 缓解 |
|---|---|
| 纯移动引回归 | D1 eval 回归闸 + 14/25 测试全量护航；红区 worktree 隔离；每步单独 commit |
| F6=A schema 名变更改行为 | 针对性接缝测试（expense 不跑 tender 校验 / tender 校验不变）；D1 eval 复跑 |
| 迁移基线漂移（D1 未 merge） | **本 draft 不定稿**；D1 merge 后 rg/wc 复核清单再进 critic |
| D2 范围过大（迁移+harness+拆分） | 分步 commit；harness 抽取可降级独立 sprint |

## 验收标准（草稿，待定稿细化）

- [ ] （前置）D1 已 merge 回 main，迁移基线确认
- [ ] （前置）用户拍板 F6=A/B，范围附加项（#8/#12）确定
- [ ] T1 worker/compare_worker/doc_pipeline 迁 server/tender/，routes 留 HTTP 壳改 import
- [ ] T2 [若 F6=A] schema 分家 + tender_output/evidence 迁入 + 接缝测试
- [ ] T3 [若纳入] worker background job harness 抽取
- [ ] T4 tender.py 按 banner 拆分
- [ ] T5 test_layering 守卫扩展至 server/tender/ 全子模块；全量 pytest 绿 + ruff 净
- [ ] D1 eval 回归闸复跑无劣化（部署机，属 runbook 验收）

## 备选（放弃）

- 一次性大爆炸迁移（不分步）：红区纯移动 3250 行不分步 = 回归定位噩梦，违反"每步 commit
  可回滚"。放弃。

---
_参考：compound/2026-07-03-explore-arch-deep-review-deltas.md #7/#8/#9/#12；
items.yaml D2 note；D1 design.md Round 2 F6。_
