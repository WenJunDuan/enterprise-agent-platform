# Roadmap · 合同审计功能平台化（+ tender 路由整合）

> slug: `contract-audit-platform` · created 2026-06-19 · 由用户 goal 驱动
> **2026-06-19 重拍**：折入已就绪的 tender 评标路由 sprint，定序 **tender 路由先行**（用户拍板）。
> 状态机入口: `.ai_state/_index.md` (current_roadmap_slug)

## 背景

用户 goal：在补做合同审计能力之前，先对上一轮(2026-06-18→19)涉及面较广的后端重构
做一轮加强质量复核（Phase 0，已完成）；复核通过后，PACE 一步步完成合同审计功能完善 + 对外 API。

**2026-06-19 整合**：项目同时挂着一份独立、已完成设计的 `tender-ingestion-workflow` sprint
（tender 评标 harness 的 CLI + HTTP 路由 + 测试，T1-T3 立即可写，T4 端到端卡用户真标）。
经梳理发现两条流共享一个 item0 延后项——**「后重构第一个新路由要定 ops/routes 层序 + 补分层守卫」**。
tender 路由是 Phase 1 第一个新路由，故把该决策从原计划的 contract-api 处**前移到 tender sprint**，
并定序 **tender 路由先行 → contract 功能 → contract API**（用户确认）。tender 立的「镜像 audit 的异步
路由」模板供 contract-api 直接复用。

## 拆解(4 item，执行序)

| # | item | 复杂度 | 硬依赖 | 说明 |
|---|---|---|---|---|
| 0 | `review-backend-refactor` | L | — | ✅ completed (3深度+1codex；de-scope 后修 4 项代码质量，241 passed) |
| 1 | `tender-ingestion` | M | item0 | tender 路由+CLI+测试；**在此关掉 item0 延后的 ops/routes 层序决策+补守卫**（后重构第一个新路由）；T4 e2e materials-gated 横切 |
| 2 | `contract-audit-feature` | L | item0 | 合同审计功能完善(contract store + legal schema + 编排)；需独立 design；与 tender **无硬依赖**，按用户定序排其后 |
| 3 | `contract-audit-api` | M | item2 + item1(模板) | 合同审计 HTTP API，复用 tender 立的新路由模板，纯加法 |

### Phase 0 · review-backend-refactor ✅ completed

- **范围**: `bbf40ac..a337fd7`，路径 `server/ tests/ deploy/` + 顶层配置；排除 `agent-front/ .ai_state/ knowledge/`。
- 3 轮深度(R1 数据/迁移完整性 · R2 架构/分层一致性 · R3 安全/健壮性) + 第 4 轮 codex 交叉，read-only 门禁。
- 结果：R1/R2/R3 均 CONCERNS + codex REWORK(C1 迁移漏 JSONL / C2 litellm 暴露)。用户 de-scope
  (demo/内网/key 自轮替/litellm 不管) → 丢弃 C1·F1-key·C2，聚合回落 CONCERNS。
- 修了 4 项纯代码质量(commit `3222e8d`/`def90fe`/`afe060a`/`e0e3c87`)，241 passed/ruff clean。
- **延后项**(文档化于 `sprints/2026-06-19-review-backend-refactor/reviews/summary.md`)：
  **架构分层守卫(ops/routes 层序决策) 已前移到 Phase 1 tender 路由**；API 脱敏、并发测试、migrate 可观测性、polish 列 backlog。

### Phase 1 · tender-ingestion（route + CLI + tests + 层序决策）— next

- sprint: `2026-06-19-tender-ingestion-workflow`（design/plan/checklist 已就绪，stage=impl，从 T1 起）。
- 范围: T1 CLI `evaluate-bid`(+json) + T2 `/tender/evaluate` 路由/worker(镜像 audit，优先复用
  `audit_task_store`) + T3 `tests/test_tender_routes.py` 与分层守卫回归。
- **整合新增(T2.5)**: 解决 item0 延后的 ops/routes 层序 + 修 3 处上向 import(`routes/health.py`、
  `ops/diagnostics.py`、`routes/audit.py`) + 补 ops/stores 分层守卫（summary R2-F1/F3/F4 門禁#5）。
  tender 路由是后重构第一个新路由，在此一并定，**只做一次，contract-api 复用**。
- T4 端到端(真招标+投标文件)materials-gated，**横切**，用户给料随时插。
- 复用: T2 立的「镜像 audit 的异步路由+worker+task_store」模板 → contract-api 照抄。

### Phase 2a · contract-audit-feature

- 需独立 design 阶段(原 `design-data-storage.md` 的 §C 仅为布局占位，无详细设计)。
- 预期改动: `stores/contract_store.py`(入统一库新表) + `data/contracts/<id>/`(原件留文件) +
  evidence_chain 回链 `contract_id` + 新建 `.claude/contracts/legal/` 契约 schema + contract-reviewer 编排。
- Path 待 design 定(Feature 或 System)。**与 tender-ingestion 无硬依赖**，按用户定序串行排其后。

### Phase 2b · contract-audit-api

- 新增 `server/routes/contract.py` 并注册进 app，仿 `routes/audit.py`(submit/tasks/result) +
  `routes/ocr.py`(extract/fill) + **Phase 1 tender 立的异步路由模板**。
- 纯加法；层序守卫已在 Phase 1 定稿，直接复用。

## 全程硬约束(合同相关 item 的 design 必须复述并验证)

1. **不破坏既有接口**: `routes/audit.py` + `routes/ocr.py` + `routes/tender.py`(Phase 1 新增) 零改；只新增 `routes/contract.py`。
2. **JSON schema 收紧只动新建**: 仅 `.claude/contracts/legal/*`；不碰 `common/audit-result`、`expense/*`、`tender/*`、`ocr/*`。
3. **复用校验注册表**: 加新 schema = 一次 `register_schema_processor`，与既有天然隔离。
4. **contract store 入统一库新表**，不改既有表结构与迁移。

## 执行纪律

- 每个 impl 步骤 = 短任务 + 即时 commit，不挂长 agent(项目教训)。
- 不引入 milestone/epic 三层；一次只跑本 roadmap；不中途插队(除非用户显式要求)。

## 进度

- [x] item0 review-backend-refactor — **completed**（3深度+1codex；de-scope 后修 4 项代码质量，241 passed）
- [~] item1 tender-ingestion — **可写完成**（T1/T2/T2.5/T3 done，260 passed）；仅 T4 端到端卡用户真标
- [x] item2 contract-audit-feature — **completed**（C1-C6 + 交叉审查 PASS 4.1/5.0；276 passed/ruff/layering）
- [ ] item3 contract-audit-api — **next**（unblocked；HTTP /contract/review，复用 Phase 1 tender 异步路由模板，纯加法）
