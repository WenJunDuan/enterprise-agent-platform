# Review Pass 1 — tender-data-model goal（Phase 1 + Phase 2）

> 交叉审查汇总入口（双 reviewer：codex 外部 + cc 自审）。详细 findings 见同目录分报告。
> 模式：用户要求 codex + cc 各自独立 review。VERDICT 经 REWORK→fixed 收敛至 PASS。

## Reviewer（代码层 findings 汇总）

### Phase 1（招标项目实体 + 多投标人追加 + 回看）
- codex 代码评审 **REWORK→fixed**（`codex-impl-review.md`）：P1.1 retry 丢 project_id 覆盖结论 / P1.2 空 tender_no 500，均已修+回归测试。
- cc 自审 **CONCERNS→fixed**（`cc-impl-review.md`）：P1 删任务后回看详情 404 → 加 `GET /projects/{id}/results/{request_id}` 直读 results。
- 设计评审 codex **APPROVE-WITH-CHANGES**（`codex-design-review.md`），5 findings 全纳入。

### Phase 2（价格横比 / 排名 / 推荐中标人）
- codex 设计评审 **APPROVE-WITH-CHANGES**（`codex-phase2-design-review.md`），6 findings 全纳入。
- codex 代码评审 **REWORK→fixed**（`codex-phase2-impl-review.md`）：P1.1 criteria 一致性只 hash 第一份 / P1.2 provisional 缺失被当终局推荐 / P2.3 污染测试假绿 / P2.4 payload project_id 未校验，全修+测试。
- cc 自审 **CONCERNS→fixed**（`cc-phase2-impl-review.md`）：C1 compare 防重 / C2 criteria 一致性（= codex P1.1）。

### 净结论
所有 P1（Phase1 3 个 + Phase2 2 个）全修 + 回归测试覆盖；P2 测试盲区补齐。**344 passed / ruff clean**。

## Spec Compliance（对照 design 验收逐条）

### Phase 1（design.md §6 验收）
| 验收项 | 结论 |
|---|---|
| 同 project 追加多家 → 名册列全部 / results 回看全部 | ✅ `test_evaluate_under_project_appears_in_roster` / `test_results_recall_survives_task_deletion` |
| 删某 task 后其余结论回看不受影响 | ✅ codex P1.1 回归 `test_project_result_detail_survives_task_deletion` |
| get-or-create 幂等（同 tenant+tender_no 返回同一 id） | ✅ `test_create_project_idempotent` |
| 旧 /tender/evaluate + /tasks/* 不破（向后兼容） | ✅ 既有 20 用例全过 |
| pytest 全绿 + ruff + 迁移幂等 | ✅ |

### Phase 2（phase2-design.md §6 验收）
| 验收项 | 结论 |
|---|---|
| ≥2 家 completed → POST /compare 异步；不足回 400 | ✅ `test_trigger_compare_requires_two_bidders` / `_accepted` |
| compare 不污染 results / bid 名册（真链路） | ✅ `test_compare_does_not_pollute_results_or_roster`（跑 execute_compare_task 断言 archive=False + results 无新增） |
| compare task 不进名册（分表） | ✅ 名册只聚合 tender_tasks |
| criteria 不一致 → 标记 manual_review | ✅ `test_collect_flags_criteria_inconsistent` |
| 追加投标后旧 compare 标 stale | ✅ `test_get_compare_result_and_stale` |
| 推荐终局：provisional 才隐藏 recommendedBidder | ✅ `test_compare_provisional_hidden_in_detail` |
| 承重 policy_refs 引通则层真实 rule_id（过真伪闸） | ✅ 命令护栏 + schema |
| pytest 全绿 + ruff + 路由表基线 | ✅ 344 passed |

### MISSING / DEVIATED
- 无 MISSING（design 验收逐条覆盖）。
- 无 DEVIATED。
- EXTRA（合理）：cc C1 防重（Phase1 evaluate 有、Phase2 补齐对齐）；architecture 档 `system-tender-data-model.md`（System 路径强制）。

## 总评：**PASS**

System 路径：设计先行 ✓ · 双 reviewer 交叉审查（REWORK→fixed）✓ · architecture 档更新 ✓ · 全绿 ✓。可 ship。
backlog（非阻塞）：compare 触发 TOCTOU 窗口、前端对接（下 sprint）——见 checklist phase2_backlog。
