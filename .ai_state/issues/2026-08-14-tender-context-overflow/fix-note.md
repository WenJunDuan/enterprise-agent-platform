---
date: 2026-08-14
type: fix-note
slug: tender-context-overflow
path: Bugfix
base: dc4dce4
---

# 修法与红绿证据

## Bug 1 · 底稿注入无预算闸 → commit `ba36397`

**修法**（`server/tender/runner.py`）：在注入点前加一道**与配置无关**的字节闸。

- 新增 env `TENDER_CONTEXT_MAX_BYTES`，`_context_max_bytes()` 每次调用现读（对齐
  `AUDIT_MAX_TURNS` 的 `os.getenv` 风格，支持运行时调参与测试 monkeypatch）。
- `_bound_ocr_block()` 超限时 `raw[:limit].decode("utf-8", errors="ignore")` —— 丢掉上限处被
  切开的半个多字节字符，产物严格 UTF-8 可解码；随后追加显式标记行
  `【底稿超出上下文预算，已截断：保留前 N 字节 / 原始 M 字节；后续内容未注入，涉及被截材料的评分项按证据缺失处理】`，
  并打 `logger.warning("tender_context_truncated", extra={request_id, original_bytes, kept_bytes, limit_bytes})`
  （对齐既有 `tender_ocr_source` 的 extra 风格）。
- 闸放在 `ocr_block` 变量上、两条来源（`doc_layer_reuse` / `inline_ocr`）之后，故预热底稿路径同样过闸；
  `evidence_source` 与模型看到的底稿因此**同源**（否则出处回查会指向未注入内容）。
- **`server/ocr/` 未动**（禁改令）：OCR 产物本身该完整，只有"注入给模型"这一步有预算。

**为什么既有 `context_slim.bound_tender_context` 没兜住**：它是**配置态**闸——
`_preextract_char_budget()` 在部署未声明模型 context window + max output tokens 时返回 `None`，
整条闸静默失效，事故当天正是这个状态。新闸与配置无关，是硬地板。

### 默认值 64,000 B 推导

按部署矩阵里**窗口最小**的模型算（不按开发机的 Claude 算）：

| 项 | token |
|---|---|
| 窗口下限（DeepSeek / qwen 系内网部署保守估） | 64,000 |
| − 输出 + 扩展思考预留（评标默认 `effort=xhigh`，思考计入输出预算） | 16,000 |
| − 单次评标脚手架（实测 55,439 B 中文提示词，3 B/字 ≈ 1 token/字） | 18,500 |
| − criteria 注入 + 底稿告警 + 估算误差余量 | 8,000 |
| = 底稿可用 | 21,500 |

21,500 token ≈ 21,500 汉字 ≈ 64,500 B → 取整 **64,000 B**。
脚手架实测值出处：`.ai_state/compound/2026-08-14-learning-prompt-budget-must-be-per-session.md`
（改后 55,439 B / 改前 48,706 B，取较大者）。1 token/汉字 的保守估与 `context_slim._DEFAULT_CHARS_PER_TOKEN = 1.0` 同源。

**取舍**：偏小的代价是被截材料按证据缺失处理（可见、有标记、可人工补），偏大的代价是整单无结论。
故取保守侧。

### 红 → 绿

红（`git checkout dc4dce4 -- server/tender/runner.py` 后跑新测试）：

```
FAILED tests/test_tender_context_budget.py::test_inline_ocr_block_over_budget_is_truncated_with_visible_marker
FAILED tests/test_tender_context_budget.py::test_truncation_cuts_on_utf8_boundary
FAILED tests/test_tender_context_budget.py::test_truncation_emits_structured_warning_log
FAILED tests/test_tender_context_budget.py::test_doc_layer_reuse_path_is_also_bounded
FAILED tests/test_tender_context_budget.py::test_evidence_source_matches_the_bounded_block
FAILED tests/test_tender_context_budget.py::test_default_budget_bounds_a_whole_directory_dump
6 failed, 1 passed in 0.21s
```

（唯一通过的是对照用例 `test_under_budget_block_is_passed_through_unchanged`——不超限时本就不该改动。）

绿：`7 passed in 0.18s`。

## Bug 2 · 确定性错误进了重试环 → commit `76a2bcf`

**修法**（`server/tender/runner.py`）：模块级 `NON_RETRYABLE_MARKERS = ("Prompt is too long",)`，
`_is_non_retryable(exc)` 在 `except` 分支**第一时间**命中即 `raise`，不进重试、不打 retrying 日志；
其余错误的重试行为逐字不变（含 `meta.retry_count` 语义）。

**识别方式为什么按消息子串**：`JSONContractError`（`server/common/contract.py:29`，`ValueError` 子类）
不携带 subtype——它在 `server/common/json_bridge.py:281` 用 SDK `ResultMessage.result` 的**原文**构造，
错误分类信息只存在于消息字符串里。子串取自事故日志的网关错误原文，匹配大小写不敏感。

### 红 → 绿

红（`git checkout ba36397 -- server/tender/runner.py` 后跑新测试）：

```
>       assert len(attempts) == 1
E       AssertionError: assert 3 == 1
E        +  where 3 = len(['rid-retry', 'rid-retry', 'rid-retry'])
>       assert not [r for r in caplog.records if "retrying" in r.getMessage()]
E       assert not [<LogRecord: server.tender.runner, 30, ... "tender attempt failed (%s, %d/%d), retrying: %s">]
FAILED tests/test_tender_retry_non_retryable.py::test_prompt_too_long_raises_on_first_attempt
FAILED tests/test_tender_retry_non_retryable.py::test_non_retryable_marker_short_circuits_before_the_retry_log
2 failed, 2 passed in 0.20s
```

（通过的两条是对照：其余契约失败仍重试满 `TENDER_CONTRACT_MAX_RETRY + 1` 次；一次可重试失败后成功的路径不受影响。）

绿：`11 passed in 0.19s`（两个测试文件合跑）。

## 待办：audit 侧同型重试环（本次**不**改）

同型循环还有两处，本次按派工只修 tender，避免顺手扩散：

- `server/audit/runner.py:218` — `for attempt in range(settings.contract_max_retry + 1)`，
  日志 `audit attempt failed (...), retrying`（L239）
- `server/audit/direct.py:204` — `DirectContractError` 重试环，日志 L234

两处同样会把 `Prompt is too long` 当可重试错误。修法可直接复用 `_is_non_retryable`，
但 `NON_RETRYABLE_MARKERS` 届时应上提到 `server/common/`（出现第二个消费者才抽象，铁律[反过度工程]）。

## 验证与影响面

- 全量：`uv run pytest -q -p no:randomly` → `34 failed, 1347 passed, 3 skipped`；
  `FAILED|ERROR` 清单与基线（main `dc4dce4`）**diff 为空**（34 条全部是环境缺依赖等既有失败）。
- `uv run ruff check server tests` → All checks passed!
- 行数：`server/tender/runner.py` 344 → 419（基线即已超 300 行；本次只加两处闸与常量，未拆分——
  拆分属重构范畴，不在 Bugfix 派工范围，记为后续待办）。
- 未触碰：`server/ocr/`、`server/tender/worker.py`、`.claude/` 提示词、schema。
