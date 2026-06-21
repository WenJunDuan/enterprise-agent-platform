# Codex 代码评审 · 第 1 轮 impl（r1）

> reviewer: codex exec review (gpt-5.5, read-only, git diff)。152k tokens。
> **VERDICT: REWORK**

## P1
- **[P1-1] 删项目漏 guard `accepted` 任务**（tender.py 删项目端点 / tender_project_store `count_running_bids`）：只查 `running`，但 `_submit_bid_evaluation` 先写 `accepted` 再排程 worker → 删项目时 accepted 任务的 worker 后续会把已删项目任务 upsert 成 running（孤儿）。**修**：active 扩为非终态（`NOT IN completed/failed`），补 accepted 窗口测试。
- **[P1-2] 删项目没拒 active compare**（store 级联删 tender_compare_tasks）：`has_active_compare()` 已存在但 DELETE 未用。**修**：删项目前拒 active compare（409）。
- **[P1-3] cloud purpose 与 design 不一致**（engine.py `_recognize_via_paddle_cloud` 仅 `_=purpose` 丢弃）：design §4 措辞要求 cloud 用 purpose，但 cloud job API 物理不支持自定义 prompt。**修**：改 design/验收明确 cloud 不支持（已知限制），实现保留注释。
- **[P1-4] score_mode 缺失无兜底**（output_contracts `_verify_score_mode_consistency`）：design 承诺"缺 score_mode 按 deduction 兜底+warning"未实现。**修**：缺失记 warning + 有 deduction_hits 时按 deduction 校验。
- **[P1-5] 缺 criteria 完整性软校验**：design 要求"score_mode=deduction 要有 deductions、banded 要有 bands"等容器匹配校验未实现。**修**：加 criteria mode 容器匹配软校验。

## P2
- **[P2-6]** `_normalize_for_hash` 只剔空值没补默认（evaluator_type:objective vs 省略 → 不同 hash）。**修**：归一已知默认值。
- **[P2-7]** evaluator.md 输出要求仍写旧形状 `{item,max,score,status,basis}`，与步骤4不一致。**修**：同步 score_mode + 明细。
- **[P2-8]** 测试缺口：accepted 删除竞态、active compare 删除、cloud purpose、旧 criteria 缺 score_mode warning、mode 容器缺失 warning、默认字段 hash 兼容。**修**：随各修复补。
