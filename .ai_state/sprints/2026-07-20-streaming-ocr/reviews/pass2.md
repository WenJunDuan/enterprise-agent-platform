# D9 streaming-ocr · Review Pass 2（F1 修复复审）

> stage=review · 2026-07-20 · 复审对象=pass1 P0 F1 修复（merge 176e91c）
> **过程说明**：pass2 独立 reviewer+spec 因用户断网被中断、harness 不可恢复。pass1 已含完整独立 reviewer（发现该 P0）+ spec-compliance（PASS）覆盖全surface；F1 修复为针对该单一 finding 的窄改动，故 pass2 由**主 agent 亲自复审**（代码逐路径核对 + 测试真实性验证 + 全量回归实证），透明记录，非冒充独立子 agent。

## VERDICT: PASS（2 个 P2 留 polish）

pass1 唯一阻塞项 P0 F1 已解决，无新 P0/P1。System 路径 PASS → polish。

## F1 逐路径复审（主 agent，读 merge 后代码）

| 路径 | 修复前缺陷 | 修复后（pipeline.py） | 判定 |
|---|---|---|---|
| font-only 扫描 PDF 回退 | native 先发空白页 + OCR 再发真实 = 重复 | `_dispatch_native_pdf_text:340-349` 仅 OCR 侧 `_call_recognize_with_seal(..., on_page)` 发 | ✅ 无重复 |
| 混合 PDF 子集增强成功 | augment 修正内容不推流,前端停在空白 native | `:356-357` `_emit_pages_from_blocks(augmented["blocks"], on_page)` 发修正内容 | ✅ 无过期 |
| 混合 PDF 整份回退 | native 先发 + 整份 OCR 再发 = 重复 | `:365-367` 仅 OCR 侧发 | ✅ 无重复 |
| 纯 native | (原 line 320 即时发是根因) | `:368-369` 从最终 `native["blocks"]` 发一次 | ✅ 单发 |
| native 读取 | `_call_native_read(path, on_page)` 即时流 | `_dispatch_extract:387` 改 `_call_native_read(path, None)` 只读不流 | ✅ 根因消除 |

**无新缺陷核验**：
- 页锚保真：`_emit_pages_from_blocks:319` `enumerate(blocks, start=1)` 与 `_render_body` pdf_text 分支页号约定一致（真实页号=下标+1，空白页保留页号）。
- 默认零行为：`on_page is None`（on_unit_complete=None 时）→ `_emit_pages_from_blocks` 由 `if on_page is not None` 守卫不发；`_call_native_read(path, None)` 走原签名分支，存量 monkeypatch mock 不破。
- 非 pdf_text native（word/excel/text）与 ocr/manual 路由：行为不变，走 `_extract_one_raw` 的 page_emitted=False 文件级兜底。
- helper 抽出（`_dispatch_native_pdf_text` / `_emit_pages_from_blocks`）：SRP + DRY，降 `_dispatch_extract` 圈复杂度，无逻辑回归。

**F2 测试真实性**（tests/test_ocr_streaming_callback.py，3 新用例）：
- font-only：`assert pages == [1,2]`（非 pre-fix 的 [1,2,1,2]）+ payload markdown 为真实内容。
- subset augment：`assert pages == [1,2,3]` + 扫描页 `text == "修正后-页N内容"`（非空白 native 版）——直接守卫过期缺陷。
- subset failure：`assert pages == [1,2,3]` 单发自整份 OCR。
- generator RED 证据（pre-fix）：`[1,2,1,2]` / 空白 `''` / `[1,2,3,1,2,3]` 三处失败，与缺陷精确对应=真守卫。

**全量回归（主 agent 独立跑）**：`uv run pytest -q` → 955 passed / 2 skip（952 基线 + 3 新，零回归）；`ruff check .` 净。

## P2（留 polish stage）
- **P2-a**：`_extract_one_raw` docstring（pipeline.py:409-412）仍描述「native pdf_text 走 buffer-then-fire（页结果在 FITZ_LOCK 内收集锁外回放）」——F1 修复后 pdf_text 改为读后从 blocks 发，此描述已过时，polish 时更正。
- **P2-b**：`native.read_pdf_text` 的 `on_page` 参数 + buffer-then-fire 逻辑（critic round1 F2 遗产）现被生产路径旁路（`_call_native_read` 恒传 None），仅 T1 单测触达 → 轻度 dead-path。polish 评估：删除简化 vs 保留（有测试、无害）。不阻塞。

## 结论
pass1 全独立 review（reviewer 发现 P0 + spec PASS）+ pass2 主 agent 复审确认 F1 解决/无新阻塞 = **PASS**。下一步 System 路径：polish（清 P2-a/P2-b + doc-style/security 扫描）→ runtime-verify（实跑 /ocr/jobs + 前端点击流，需起服务）→ ship（review-manifest.yaml 等契约）。
