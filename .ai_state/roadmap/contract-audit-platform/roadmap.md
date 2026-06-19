# Roadmap · 合同审计功能平台化

> slug: `contract-audit-platform` · created 2026-06-19 · 由用户 goal 驱动
> 状态机入口: `.ai_state/_index.md` (current_roadmap_slug)

## 背景

用户 goal：在补做合同审计能力之前，先对上一轮(2026-06-18→19)涉及面较广的后端重构
做一轮加强质量复核；复核通过后，PACE 一步步完成合同审计功能完善 + 对外 API 接口。

上一轮后端重构含四块：server 分层整理 / 企业级运行日志 / validate 校验注册表(OCP) /
data 业务存储重构(统一单库)。已经过一轮 codex review(session `2026-06-19-codex-review.md`)，
盲点集中在**迁移完整性 / schema drift / 统一库写锁放大**。本 goal 的 Phase 0 针对性加深。

## 拆解(3 item，拓扑顺序)

| # | item | 复杂度 | 依赖 | 说明 |
|---|---|---|---|---|
| 0 | `review-backend-refactor` | L | — | 3 轮深度 review + 1 轮 codex 交叉，read-only 门禁 |
| 1 | `contract-audit-feature` | L | item0 | 合同审计功能完善(contract store + schema + 编排) |
| 2 | `contract-audit-api` | M | item1 | 仿 ocr/audit 的 HTTP API，纯加法 |

### Phase 0 · review-backend-refactor

- **范围**: `bbf40ac..a337fd7`，路径 `server/ tests/ deploy/` + 顶层配置；排除 `agent-front/ .ai_state/ knowledge/`。
- **3 轮(按风险主题，用户确认)**:
  - R1 数据/迁移完整性 —— migrate 逐表 payload/blob/指针、schema drift、统一库写锁、事务原子性(上次 codex 盲点重灾区)。
  - R2 架构/分层一致性 —— 依赖单向无环、ops/deps 抽离、注册表 OCP、SRP/文件长度。
  - R3 安全/健壮性 —— 日志不泄密(key/token)、错误处理脱敏、边界与失败注入、security-checklist。
- 每轮: `reviewer` + `spec-compliance` 并行(read-only) → `evaluator` 汇总给 VERDICT。
- **第 4 轮 codex 交叉**: `codex exec -s read-only` 独立复审同范围。
- 出 REWORK → 插入修复子步骤(黄/红区按铁律路由)，全绿 + 全量 pytest 通过才标 completed。

### Phase 1a · contract-audit-feature

- 需独立 design 阶段(原 `design-data-storage.md` 的 §C 仅为布局占位，无详细设计)。
- 预期改动: `stores/contract_store.py`(入统一库新表) + `data/contracts/<id>/`(原件留文件) +
  evidence_chain 回链 `contract_id` + 新建 `.claude/contracts/legal/` 契约 schema + contract-reviewer 编排。
- Path 待 design 定(Feature 或 System)。

### Phase 1b · contract-audit-api

- 新增 `server/routes/contract.py` 并注册进 app，仿 `routes/audit.py`(submit/tasks/result) + `routes/ocr.py`(extract/fill)。
- 纯加法。

## 全程硬约束(每个 item 的 design 必须复述并验证)

1. **不破坏既有接口**: `routes/audit.py` + `routes/ocr.py` 零改；只新增 `routes/contract.py`。
2. **JSON schema 收紧只动新建**: 仅 `.claude/contracts/legal/*`；不碰 `common/audit-result`、`expense/*`、`tender/*`、`ocr/*`。
3. **复用校验注册表**: 加新 schema = 一次 `register_schema_processor`，与既有天然隔离。
4. **contract store 入统一库新表**，不改既有表结构与迁移。

## 执行纪律

- 每轮 review / 每个 impl 步骤 = 短任务 + 即时 commit，不挂长 agent(项目教训)。
- 不引入 milestone/epic 三层；一次只跑本 roadmap；不中途插队(除非用户显式要求)。

## 进度

- [x] item0 review-backend-refactor — **completed**（3深度+1codex；de-scope 后修 4 项代码质量，241 passed）
- [ ] item1 contract-audit-feature — next（需 design 阶段）
- [ ] item2 contract-audit-api — pending（blocked_by item1）
