# Codex 代码评审 — tender Phase 2 价格横比实现

> Reviewer: Codex CLI (gpt-5.5) · commit Phase2(feat) · 2026-06-20 · 128K tokens

## VERDICT: **REWORK**（2 P1 + 2 P2；设计 6 findings 的落实确认 OK）

codex 确认设计 findings 已落实（P1.1 archive 透传 / P1.2 task 分表 / P1.3 scoring[] 不读 subtotal），
但实现层发现 4 个新问题。

## Findings（全部修复）

| # | 级别 | 问题 | 修复 |
|---|---|---|---|
| 1 | P1 | **criteria 一致性没真正实现**：worker 只读第一条 result 的 criteria 算 hash，后续 bidder criteria 没读没比 → 不一致时仍任取第一份公式；签名也只覆盖第一份（重评非第一条时 stale 漏判）。**= cc 自审 C2，codex 升 P1** | worker 收集**全量** criteria hash，不一致标 `criteria_inconsistent` 进 compare 输入（命令据此 manual_review）；签名覆盖全量 hash 集 |
| 2 | P1 | **provisional 缺失被当终局推荐**：schema 没 required `provisional`，路由用 `not payload.get("provisional")` 判终局 → `{recommended:"B1"}`(无 provisional) 会被 `not None=True` 误当终局展示 | schema required 加 `recommended/provisional/warnings/policy_refs`；路由改 `provisional is False and recommended`；加语义校验 `provisional=true ⇒ recommended is null` |
| 3 | P2 | **污染回归测试假覆盖**：`test_compare_does_not_pollute` 直接 upsert 专表，没跑 `execute_compare_task→run_command_json`，archive flag 透传若断仍绿 | 重写：monkeypatch `run_command_json` 真跑 `execute_compare_task`，断言 `archive_to_results is False` + results 表无新增 compare 行 |
| 4 | P2 | **compare payload project_id 未校验**：直接把 Claude payload 存当前 project compare row，没查 `payload["project_id"]==project_id` → GET 可能返回自相矛盾结果 | worker 存前覆盖 `payload["project_id"]=project_id` |

## Confirmed OK（codex 明确排除）
- P1.1 archive_to_results=False 从 run_command_json 透传到 run_agent_json，archive_result_payload 被 gated。
- P1.2 compare 用 tender_compare_tasks，roster 只读 tender_tasks/results。P1.3 传 scoring[] 未读 subtotal。
- payload JSON loads、tenant 查询、TaskStore 表名白名单、后台 task 强引用集均无阻塞问题。

## 另：cc 自审独立发现并已修
- C1 compare 触发防重（Phase1 evaluate 有原子防重，compare 缺）→ 已加 `has_active_compare` + 409。
