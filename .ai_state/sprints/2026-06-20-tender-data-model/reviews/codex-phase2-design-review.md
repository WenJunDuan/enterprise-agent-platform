# Codex Phase 2 设计评审 — tender 价格横比

> Reviewer: Codex CLI (gpt-5.5) · 2026-06-20 · 对象 phase2-design.md · 148K tokens

## VERDICT: **APPROVE-WITH-CHANGES**

§7 五个决策点全部认同（Claude 侧横比 / 新表 A / 异步 / 不重读投标用已落库 scoring / criteria 不任取一家）。但 6 处实现陷阱需在终版/实施纳入。

## Findings（全部纳入终版）

| # | 级别 | 问题 | 终版处置 |
|---|---|---|---|
| 1 | P1 | compare 走 `run_command_json` 会固定归档进 `results`（json_bridge:200），而 `_project_bid_roster` 把 results 每行当 completed bid → compare 变"伪投标人"污染名册/回看 | `run_agent_json` 加 `archive_to_results: bool=True` 显式参数；compare 传 **False**（不写 results），结果由 compare runner 自存 `tender_compare_results` |
| 2 | P1 | compare 异步任务若复用 `tender_tasks`（mode=directory/upload，不承载类型）+ 同 group_id → 被 project detail 当在途 bid | 新建 **`tender_compare_tasks`** 表（绑泛型 TaskStore，表名隔离）；`_project_bid_roster` 只聚合 `tender_tasks`（evaluate），不碰 compare |
| 3 | P1 | `scored_subtotal` 非现有契约字段，不能假设可读（Phase1 只钉 scoring[]/bid_price） | compare 输入传每家 **`scoring[]`**，由 Claude 自算/校验 `other_score`；不读 subtotal，不改 Phase1 契约 |
| 4 | P1 | criteria 取"任一家 payload"无一致性保证 | compare 收集时对各家 `payload.criteria` 算 **criteria_hash**，要求一致；不一致 → compare 结果 `manual_review` + warning，不任取 |
| 5 | P1 | 推荐中标人不能无条件=排名第一（`tender_evalmethod_013` 仅国有资金；异常低价 010 需澄清；有效投标<3 触发 012） | compare schema 允许 **`recommended: null`** + `provisional`(bool) + `warnings[]`；输入带 `funding_type/control_price/method`；Claude 判能否终局推荐 |
| 6 | P2 | 追加投标后旧 compare 过时返回陈旧推荐 | `tender_compare_results` 存 **`input_result_ids` + `criteria_hash` + `computed_at`**；GET/detail 重算当前 completed set 签名，不匹配标 **`stale=true`**，不展示旧推荐 |

## §7 决策（codex 确认，已定）
1. 横比 Claude 侧；Python 只收集/校验/调度/持久化。
2. 存储新表 A（`tender_compare_results`），但杜绝 results 副作用污染（见 P1.1）。
3. 异步，但 compare task 分表（见 P1.2）。
4. 总分不重读投标，用已落库 scoring[]/bid_price/criteria，Claude 合成。
5. criteria 不任取一家，hash 校验一致后再 compare（见 P1.4）。
