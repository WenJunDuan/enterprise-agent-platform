# CC (Claude) 代码评审 — tender Phase 2 价格横比实现

> Reviewer: Claude(主实现方自审，独立维度) · commit Phase2(feat) · 2026-06-20 · 配套 codex-phase2-impl-review.md

## VERDICT: **CONCERNS（2 项非阻塞 + 1 已修 bug；核心正确）**

341 passed/ruff。codex 6 findings 全落实并测；实现中**测试抓到 1 个真 bug**（已修）。下列 2 项 CONCERNS 记 backlog。

## 一、codex 6 findings 落实核对（通过）

- **P1.1 不污染 results**：compare 经 `run_command_json(archive_to_results=False)` → `run_agent_json` 跳过 `archive_result_payload`；`test_compare_does_not_pollute_results_or_roster` 实证名册仍 2 家、`/results` 仍 2 家。✓
- **P1.2 task 分表**：`tender_compare_tasks` 独立绑泛型 TaskStore；`_project_bid_roster` 只查 `tender_tasks`（evaluate），compare task 不入名册。✓
- **P1.3 不读 subtotal**：compare 输入传 `scoring[]`，命令让 Claude 自算 `other_score`。✓
- **P1.4 criteria hash + P2.6 stale**：`compute_criteria_hash`(sort_keys 规范化) + `input_signature`(排序 request_id + hash)；`test_get_compare_result_and_stale` 实证追加第 3 家后旧 compare stale。✓
- **P1.5 推荐终局**：schema `recommended` 可 null + `provisional` + `warnings`；详情联动 `not compare_stale and not provisional` 才填 `recommended_bidder`；`test_compare_provisional_hidden_in_detail` 验证。✓

## 二、实现中修复的真 bug
- **`list_results_by_project` 的 payload 是未解析 JSON 字符串**（`SELECT *`，不像 `get_payload_by_request_id` 会 loads）→ worker `collect_compare_input` 原 `payload.get("response")` 对字符串失效、永远收集到 0 家。测试 `test_collect_compare_input_and_signature` 抓到，已加 `json.loads` 兜底。**教训**：list 与 get 的 payload 形态不一致是潜在坑，多处消费 list 结果需注意。

## 三、CONCERNS（非阻塞）

1. **[C1] compare 触发无幂等/防重**：`POST /compare` 每次都 `new_request_id` + schedule，无"已有 running compare 则拒/复用"。并发双击会起两个 compare task 算两遍（成本×2，结果 upsert 互相覆盖但不致错）。Phase 1 的 evaluate retry 有原子 `try_transition` 防重，compare 没有。建议：compare 也加在途守卫（同 project 有 running compare task 则 409）。记 backlog。
2. **[C2] criteria 一致性仅算 hash 存档，未在 compare 前硬校验**：worker `collect_compare_input` 取**第一家**的 criteria 算 hash 进 compare 输入，但**没校验其余家 criteria 是否同 hash**（design §4.5 说"不一致→manual_review"，实现把一致性判断推给了 Claude 命令）。即"任取一家"风险（codex P1.4）只做了一半——存了 hash 但没在收集时拒绝不一致。建议：collect 时对所有家 criteria 算 hash，不全一致则在 compare_input 标记 `criteria_inconsistent: true`，命令据此走 manual_review。记 backlog（v1 靠命令护栏 + 同招标 criteria 逐字依原文应一致）。

## 四、明确排除
- 租户隔离：compare/project 查询全 `tenant` 作用域（`get_compare_result`/`get_project`/`list_results_by_project` 都带 tenant）。
- archive=False 时 `result_file` 默认 None（try 前初始化），session record finally 仍正确写。
- 异步引用集 `_BACKGROUND_TASKS` 防 GC（同 Phase 1 范式）。
- SQL：compare store 表名硬编码、列名固定，无注入面。
- DRY：`_current_compare_signature` 复用 worker `collect_compare_input`，未重复收集逻辑。
