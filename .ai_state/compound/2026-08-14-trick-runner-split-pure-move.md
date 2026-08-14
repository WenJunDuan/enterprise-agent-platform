---
date: 2026-08-14
type: trick
slug: runner-split-pure-move
---

# 纯移动式拆分：边界由"测试怎么打桩"倒推，不由代码美学

`server/tender/runner.py` 419 → 289 行，拆出 `doc_context.py`(122) + `criteria_context.py`(45)，
`tests/test_tender_*` **零修改**全绿（`git diff --stat tests/` 为空）。

## 拆分边界的第一判据：monkeypatch 面不能被搬走

按内聚拆之前，先 `grep -rn "setattr(runner" tests` 把测试打桩面盘出来。测试打的是
**模块全局**（`monkeypatch.setattr(runner, "ocr_preprocess_block", ...)`），而被搬走的函数解析
的是**新模块的全局**——搬走调用点 = 打桩静默失效（更糟：桩没生效但测试仍可能因别的原因通过）。

本次的硬约束（决定了主流程必须留在 runner.py）：

- `runner.run_command_json` / `runner.ocr_preprocess_block` / `runner.resolve_project_criteria`
  被打桩 → 三者的**调用点**留 runner.py
- `runner.TENDER_CONTRACT_MAX_RETRY` 被打桩且被重试环现读 → 重试环留 runner.py
- `runner._ocr_integrity_warnings` / `runner._inject_ocr_warnings` 被测试**直接调用**（非打桩）
  → 搬走后在 runner.py re-export 即可（属性查找拿到同一对象）

反过来，`doc_layer.*` / `doc_rerun.*` 是在**它们自己的模块**上打桩的，搬家不受影响——
这正是 `_resolve_doc_layer` 能搬的原因。

## 第二判据：可观测输出的归属不能随搬家漂移

预算闸 `_bound_ocr_block` **没搬**，尽管它和底稿最内聚：它发
`logger.warning("tender_context_truncated")`，搬家会把 LogRecord 的 logger 名从
`server.tender.runner` 改成新模块名。测试里 `caplog.at_level(logger="server.tender.runner")`
仍会通过（记录照样传播到 root handler），但线上按 logger 名检索的运维日志会断——
**测试没红 ≠ 纯移动**。留在 runner.py 后 289 行仍达标，代价可接受。

## 外部引用盘点（改前 `grep -rn "from server.tender.runner import\|from server.tender import runner" server tests`）

- 生产侧 4 处：`tender/worker.py`（`run_tender_evaluation`）、`tender/eval.py`（同上）、
  `tender/doc_rerun.py` 与 `tender/doc_pipeline.py`（均取 `TENDER_OCR_PURPOSE`）——
  **全部只引未搬走的符号，零改动**（`TENDER_OCR_PURPOSE` 因此也不搬）。
- 测试侧 14 个文件 `from server.tender import runner`，其中只有 2 处触到搬走的符号
  （`_ocr_integrity_warnings`）→ 选 **re-export**（1 行）而非改 2 处引用点：改动面更小，
  且不给"内部函数的家在哪"这件事绑定测试。

## 纯移动怎么被机器锁住

1. 搬完先用脚本比对：从 runner 的 git 原文与新模块各自切出同名函数块，断言 `rstrip()` 后
   **逐字节相等**（6/6 IDENTICAL），再删原件——比肉眼 diff 可靠。
2. 行为锁是既有测试本身：`test_tender_context_budget.py`(7) + `test_tender_retry_non_retryable.py`(4)
   + 全部 `test_tender_*`(464 passed) 零修改全绿；全量 `FAILED|ERROR` 清单与基线 diff 为空。
3. 收尾核 `git diff --stat tests/` 必须为空——**测试有一行改动，"纯移动"的声明就不成立**。
