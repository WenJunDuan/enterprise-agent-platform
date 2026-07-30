# TDD Evidence — demo-full-doc-ocr

本文件只记录实际执行并取得结果的命令。`reviews/pass1.md` 中未被当轮测试覆盖的反例明确标为
“待补”，不以相邻测试集绿色或后续实现位置代替闭环证据。

## Pass 1

| Finding | RED 命令 / 失败摘要 | 实现锚点 | GREEN 命令 / 结果 | 来源标识 |
|---|---|---|---|---|
| F1 P0：`compare_worker` 只检查首份 criteria | **历史过程偏差不变**：Pass1 前没有针对“第一家价格项为数值、第二家为 manual/null”的 RED 执行证据。 | 后续实现位置：`server/tender/compare_worker.py:70-192`；Pass1 未验收。 | Pass1 当时无覆盖该反例的 GREEN。当前针对性回归：`uv run pytest -q tests/test_tender_compare.py::test_collect_checks_every_bidder_price_item_and_criteria_consistency tests/test_tender_info_extraction.py::test_criteria_looks_usable_rejects_illegal_null_max` 与 F2 合并执行 → `8 passed, 1 warning`；这是事后 GREEN，不倒签为先 RED。 | finding：`reviews/pass1.md#F1`；当前回归：`agent:/root/criteria_null_impl:pass3-current-f1-f2-green-8-pass` |
| F2 P0：manual/null 接受缺失 tag | **历史过程偏差不变**：Pass1 前没有针对 `score_mode=manual,max=null` 且缺少 `tag` 的 RED 执行证据。 | 后续实现位置：`server/tender/doc_pipeline.py:88-155`；Pass1 未验收。 | Pass1 当时无覆盖缺失 tag 反例的 GREEN。当前与 F1 合并执行对应参数化用例 → `8 passed, 1 warning`；覆盖 manual/null 的 missing/empty/illegal tag，属于事后 GREEN。 | finding：`reviews/pass1.md#F2`；当前回归：`agent:/root/criteria_null_impl:pass3-current-f1-f2-green-8-pass` |
| F3 P0：前端横比把部分 null 折为 0 | **历史过程偏差不变**：Pass1 前没有针对同一比较行混合 numeric/null cell 的 RED 执行证据。 | 后续实现位置：`agent-front/src/features/contract/tender-review/model.ts:725-764`、`types.ts:264-270`；Pass1 未验收。 | Pass1 当时无覆盖混合 null compare cell 的 GREEN。当前执行 `bun test src/features/contract/tender-review/model.test.ts -t 'compare groups preserve unknown bidder scores as null instead of zero'` → `1 pass, 47 filtered out`；属于事后 GREEN。 | finding：`reviews/pass1.md#F3`；当前回归：`agent:/root/criteria_null_impl:pass3-current-f3-green-1-pass` |
| F4 P1：部分页成功后缺 terminal error unit | `uv run pytest -q tests/test_ocr_streaming_callback.py::test_partial_pages_then_fallback_failure_emits_terminal_error_unit tests/test_ocr_engine_fallback.py::test_blocked_page_renderer_hits_hard_timeout tests/test_ocr_office_convert.py::test_timeout_escalates_term_to_kill_and_waits` → `2 failed, 1 passed`。F4 实际仅发出 `units=[(1, ok)]`，缺 terminal error；测试当时另有漏导入 `OcrDependencyError` 的 NameError，但 terminal error 缺失断言确实失败。 | 测试：`tests/test_ocr_streaming_callback.py:256`；实现：`server/ocr/pipeline.py:464`（终态分支 `505-511`）；job 终态：`server/routes/ocr_job_worker.py:83`。 | targeted：OCR engine/streaming/office/job/pipeline 相关 7 个测试文件 + Ruff + `git diff --check` → `122 passed`，Ruff/diff clean。full：`CLAUDE_CODE_MAX_OUTPUT_TOKENS=8192 uv run pytest -q && uv run ruff check . && git diff --check` → `1083 passed, 2 skipped, 9 warnings`，Ruff/diff clean。 | `agent:/root/ocr_core_impl:pass1-f4-f5-red-2-failed-1-passed`；`agent:/root/ocr_core_impl:pass1-green-122-pass`；`agent:/root/ocr_core_impl:pass1-full-1083-pass-2-skip` |
| F5 P1：页渲染超时不可中断 | 与 F4 共用 RED 命令 → `2 failed, 1 passed`；`_render_worker_argv` 不存在，触发 AttributeError。Office TERM→KILL 测试当时已通过。 | 测试：`tests/test_ocr_engine_fallback.py:267`；实现：`server/ocr/engine.py:191,254`；隔离 worker：`server/ocr/page_render_worker.py:1`。 | 与 F4 共用 targeted/full GREEN：`122 passed`；全量 `1083 passed, 2 skipped, 9 warnings`；Ruff/diff clean。 | `agent:/root/ocr_core_impl:pass1-f4-f5-red-2-failed-1-passed`；`agent:/root/ocr_core_impl:pass1-green-122-pass`；`agent:/root/ocr_core_impl:pass1-full-1083-pass-2-skip` |
| F6 P1：上传边界缺 manifest 后缀/magic 校验 | RED1：`uv run pytest -q tests/test_upload_helpers.py tests/test_ocr_routes.py tests/test_tender_upload_routes.py tests/test_ocr_native_formats.py` → collection `2 errors`，`validate_document_upload` 不存在。RED2：`uv run pytest -q tests/test_smoke_document_formats.py` → collection `1 error`，`scripts.smoke_document_formats` 不存在。 | 实现：`server/routes/upload_helpers.py:246,267,317`；路由 opt-in：`server/routes/ocr.py`、`ocr_jobs.py`、`tender/docs.py`、`tender/tasks.py`；测试：`tests/test_upload_helpers.py:71`、`tests/test_tender_upload_routes.py:115`、`tests/test_ocr_routes.py:75`。 | 最终相关 8 个测试文件 → `123 passed`，1 个 Starlette warning；同轮 Ruff 全通过。另有 `python3 scripts/generate_document_formats.py --check` 通过，前端格式契约 `2 passed`、build、eslint、`git diff --check` 均通过。真实远端/容器格式矩阵尚未执行，不记为通过。 | `agent:/root/formats_packaging_impl:pass1-f6-red-collection-2-errors`；`agent:/root/formats_packaging_impl:pass1-f6-green-123-pass` |

### F4/F5 targeted GREEN 原命令

```bash
uv run pytest -q \
  tests/test_ocr_engine_fallback.py \
  tests/test_ocr_streaming_callback.py \
  tests/test_ocr_office_convert.py \
  tests/test_ocr_job_worker.py \
  tests/test_ocr_engine.py \
  tests/test_ocr_pipeline.py \
  tests/test_ocr_pipeline_mixed_pdf.py \
&& uv run ruff check \
  server/ocr server/routes/ocr_job_worker.py \
  tests/test_ocr_engine_fallback.py \
  tests/test_ocr_streaming_callback.py \
  tests/test_ocr_office_convert.py \
  tests/test_ocr_job_worker.py \
&& git diff --check
```

### F6 最终 GREEN 原命令

```bash
uv run pytest -q \
  tests/test_upload_helpers.py \
  tests/test_routes_smoke.py \
  tests/test_ocr_routes.py \
  tests/test_ocr_job_routes.py \
  tests/test_tender_upload_routes.py \
  tests/test_tender_routes.py \
  tests/test_ocr_native_formats.py \
  tests/test_smoke_document_formats.py
```

Pass1 结论：F4–F6 已有可审计 RED/GREEN；F1–F3 没有先 RED 的历史事实不变。当前针对性 GREEN
只证明反例现已闭环，不能倒推 Pass1 当时满足 TDD 顺序。

## Pass 2 rework

本节的 F1/F3 对应 `reviews/pass2.md`，与 Pass1 的同编号 finding 无关。

| Finding | RED 命令 / 失败摘要 | 实现锚点 | GREEN 命令 / 结果 | 来源标识 |
|---|---|---|---|---|
| F1 P0：页像素上限在分配后检查 | `uv run pytest -q tests/test_ocr_engine_fallback.py -k 'preflights_page_rect or invalid_page_frame or remaining_document_budget'` → `10 failed`。其中 5 个超大、NaN、Inf、0、负尺寸用例均错误调用了 `get_pixmap`。 | `server/ocr/page_render_worker.py::_preflight_page_pixels`、`render`：按 `page.rect × scale` 校验 finite/positive，以 `ceil` 保守预估并在 `get_pixmap` 前拒绝；渲染后仍复核实际 pixmap。测试：`tests/test_ocr_engine_fallback.py::test_render_worker_preflights_page_rect_before_pixmap`。 | 同一 RED 命令复跑 → `10 passed, 15 deselected`。targeted：`uv run pytest -q tests/test_ocr_engine_fallback.py tests/test_ocr_engine.py tests/test_ocr_streaming_callback.py && uv run ruff check server/ocr/page_render_worker.py server/ocr/engine.py tests/test_ocr_engine_fallback.py && git diff --check` → `47 passed, 5 warnings`；scoped Ruff/diff check clean。 | `agent:/root/ocr_core_impl:pass2-f1-f3-red-10-failed`；`agent:/root/ocr_core_impl:pass2-f1-f3-green-10-pass`；`agent:/root/ocr_core_impl:pass2-targeted-47-pass` |
| F3 P2：framed 渲染协议未 fail-fast | 与 F1 共用 RED 命令 → `10 failed`。4 个非法 frame 未在 `read_exact` 前拒绝；累计剩余文档预算在读取 payload 后才报错。 | `server/ocr/engine.py::_render_pdf_pages`：在 `read_exact` 前验证 `type == "page"`、`page_number`、非 bool 正整数 `length` 及 `length <= remaining`。测试：`tests/test_ocr_engine_fallback.py::test_invalid_page_frame_rejected_before_read_exact`、`test_page_frame_length_respects_remaining_document_budget_before_read`。 | 与 F1 共用 GREEN：同组 `10 passed, 15 deselected`；targeted `47 passed, 5 warnings`；scoped Ruff/diff check clean。 | `agent:/root/ocr_core_impl:pass2-f1-f3-red-10-failed`；`agent:/root/ocr_core_impl:pass2-f1-f3-green-10-pass`；`agent:/root/ocr_core_impl:pass2-targeted-47-pass` |

### Pass2 formats / packaging / macro rework

RED 与 targeted GREEN 使用同一命令：

```bash
uv run pytest -q \
  tests/test_supported_document_formats.py \
  tests/test_smoke_document_formats.py \
  tests/test_ocr_office_convert.py \
  tests/test_office_macro_safety_smoke.py
```

- RED：`6 failed, 16 passed`。失败覆盖双 Dockerfile 未复制 scripts/fixtures、runbook 缺 scripts /
  `pipefail` / JSON 状态门禁、真实 fixtures 与 `SOURCES.json` 缺失、Office profile 未设置
  `DisableMacrosExecution=true`、宏安全 verifier 缺失。
- GREEN：同一命令 `22 passed in 1.51s`。
- 扩展 GREEN：追加 `tests/test_ocr_native_formats.py` 后 `37 passed in 1.47s`；同一批次 scoped
  Ruff `All checks passed!`，`python3 scripts/generate_document_formats.py --check` 与
  `git diff --check` 均 exit 0。
- 实现锚点：`Dockerfile`、`agent-front/deploy/Containerfile.agent-backend`、
  `scripts/build_document_format_fixtures.py`、`scripts/document_format_fixtures/`、
  `scripts/smoke_document_formats.py`、`scripts/verify_office_macro_safety.py`、
  `server/ocr/office_convert.py`、`deploy/TROUBLESHOOTING.md`。
- 测试锚点：上述 4 个 targeted 测试文件及扩展 `tests/test_ocr_native_formats.py`。
- 来源：`agent:/root/formats_packaging_impl:pass2-red-6-failed-16-pass`、
  `agent:/root/formats_packaging_impl:pass2-green-22-pass`、
  `agent:/root/formats_packaging_impl:pass2-extended-37-pass`。

宏安全 verifier 实际执行：

```bash
uv run python scripts/verify_office_macro_safety.py \
  --fixture scripts/document_format_fixtures/macro-on-open.odt \
  --evidence scripts/evidence/office-macro-safety-local-arm64.json
```

结果为 `status=ok`、宏/副作用代码/load event 均存在、`pdf_magic=%PDF-`、
`side_effect_created=false`、`profile_removed=true`、`residual_processes=[]`。证据文件是
`scripts/evidence/office-macro-safety-local-arm64.json`，其 scope 明确为
`local-host; rerun required in deployed Debian ARM64 backend image`：仅证明 Darwin arm64 +
LibreOfficeDev 26.8.0.0.alpha0 本机执行，不代表 demo 或成品 Debian ARM64 镜像已通过。
来源：`agent:/root/formats_packaging_impl:local-macro-safety-ok`。

## Pass 3 rework / M3

### F1 P0 · 前端不得重造 blocked 排名

- RED：`bun test src/features/contract/tender-review/model.test.ts src/features/contract/tender-review/components/criteria-null-display.test.ts`
  → `49 pass, 2 fail`。blocked/provisional compare 的 `total_score/rank=null` 被补成
  `0/1, 0/2`；卡片把待复核总分显示为 `56`。
- 实现锚点：`model.ts` 保留 compare nullable 并仅对非 provisional 的完整排名重排；`types.ts`
  将 `ReviewBidder/BidderCard.total/rank` 设为 nullable；`bidder-compare-cards.tsx` 对 null 总分显示
  “待确认”且不显示名次。
- GREEN：同命令 → `51 pass, 0 fail, 201 expect()`；全前端
  `bun run test && bun run build && bun run lint && git diff --check` →
  `164 pass, 0 fail, 473 expect()`，TypeScript/Vite build 成功（仅既有 chunk-size warning），
  ESLint/diff check 通过。
- 来源：`agent:/root/criteria_null_impl:pass3-f1-red-49-pass-2-fail`、
  `agent:/root/criteria_null_impl:pass3-f1-green-51-pass`、
  `agent:/root/criteria_null_impl:pass3-frontend-full-164-pass-build-lint`。

### F2 P1 · 图像解析与 Base64 前资源门禁

- 首次 RED：`uv run pytest -q tests/test_ocr_engine_fallback.py -k 'oversized_image_stat or image_parser_exception or legal_image_passes or image_byte_limit_default'`
  → `3 failed, 1 passed, 25 deselected`。失败证明超大 stat 后仍 `read_bytes`、parser exception 被吞后
  继续联网、独立 `OCR_MAX_IMAGE_BYTES` 不存在；合法小图当时已通过，不记为 RED。
- WebP RED：`uv run pytest -q tests/test_ocr_engine_fallback.py -k 'legal_webp or malformed_webp'`
  → `1 failed, 1 passed, 29 deselected`。合法 WebP 被 PyMuPDF 错拒；畸形 WebP 当时已通过，不记为 RED。
  像素超限反例本轮前已有门禁并保持 GREEN，同样不补写历史 RED。
- 最终 GREEN：`uv run pytest -q tests/test_ocr_engine_fallback.py tests/test_ocr_engine.py tests/test_ocr_pipeline.py`
  → `88 passed, 5 warnings in 2.28s`。
- 来源：`agent:/root/ocr_core_impl:pass3-f2-red-3-failed-1-pass`、
  `agent:/root/ocr_core_impl:pass3-f2-webp-red-1-failed-1-pass`、
  `agent:/root/ocr_core_impl:pass3-f2-green-88-pass`。

### M1 · 本机 canonical 格式 smoke

证据：`scripts/evidence/document-format-smoke-local-arm64.json`，`status=ok`，24/24 后缀通过上传校验、
路由并产出非空底稿：13 native、4 convert、7 OCR；7 个 OCR 均因故意不可达本地 VLM 端点走真实
Tesseract，标记 `degraded=true`。Tessdata 固定为 `tesseract-ocr/tessdata_fast` commit
`87416418657359cb625c412a48b6e1d6d41c29bd`：

- `chi_sim` SHA-256：`a5fcb6f0db1e1d6d8522f39db4e848f05984669172e584e8d76b6b3141e1f730`
- `eng` SHA-256：`7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2`

scope 严格限定为 `local Darwin arm64; deployed Debian ARM64 image must rerun T6`；不能据此宣称 demo
或成品镜像通过。来源：`evidence:document-format-smoke-local-arm64-24-of-24-ok`。

## Pass 4 rework

### F1 P1 · 全部图像 OCR backend 共用统一资源门禁

- RED：`uv run pytest -q tests/test_ocr_engine_fallback.py -k 'cloud_oversized_image or cloud_malformed_image or local_paddle_rejects_invalid_image or cloud_image_reuses_single'`
  → `5 failed, 31 deselected, 5 warnings in 0.18s`。超大/畸形图片均直接进入 cloud backend；两组
  本地 Paddle invalid payload 均进入 pipeline；cloud submit 未把已验证 bytes 传给 multipart，测试
  因缺少 `file_content` 参数失败。
- 实现：`recognize()` 在图像 backend 分派前统一执行 bounded stat/read + Pillow 校验；同一份
  validated bytes 传给 OpenAI-compatible 或 cloud，cloud 链
  `_recognize_via_paddle_cloud → _cloud_submit_job → _post_multipart` 不再二次读取；PDF 不进入
  `OCR_MAX_IMAGE_BYTES` 门禁。
- GREEN：同一 RED 命令复跑 → `5 passed, 31 deselected, 5 warnings in 0.11s`。
- targeted：`uv run pytest -q tests/test_ocr_engine_fallback.py tests/test_ocr_engine.py tests/test_ocr_pipeline.py tests/test_ocr_streaming_callback.py`
  → `109 passed, 5 warnings in 2.21s`。
- PDF/security 补充：`uv run pytest -q tests/test_ocr_pipeline_mixed_pdf.py tests/test_ocr_page_security.py tests/test_ocr_page_hook_integration.py`
  → `21 passed, 2 skipped, 1 warning in 0.31s`。
- TDD 例外：实际 `_post_multipart(file_content=...)` body 不二次读 path 的独立单测是在实现后补充，
  没有单独先 RED；“同一 validated bytes 贯穿 cloud 链”的验收行为已由上述 cloud reuse 集成 RED
  覆盖，但不得把后补单测倒签成新的 RED。
- 来源：`agent:/root/ocr_core_impl:pass4-f1-red-5-failed`、
  `agent:/root/ocr_core_impl:pass4-f1-green-5-pass`、
  `agent:/root/ocr_core_impl:pass4-targeted-109-pass`、
  `agent:/root/ocr_core_impl:pass4-pdf-security-21-pass-2-skip`。

### D1/D2 · 证据执行范围与当前 fixture SHA

- RED：`uv run pytest -q tests/test_smoke_document_formats.py::test_execution_scope_describes_the_current_runtime tests/test_office_macro_safety_smoke.py::test_real_macro_document_cannot_create_side_effect_and_leaves_no_process`
  → `2 failed`。格式 smoke 的执行范围不能描述实际 runtime，宏安全证据中的 fixture SHA 与当前
  `macro-on-open.odt` 不一致。
- GREEN：同一命令复跑 → `2 passed`。两个证据脚本现按实际 `platform.system()/machine()` 写入
  `execution_scope`，宏安全 verifier 每次从当前 fixture 计算 SHA-256。
- 来源：`agent:/root/formats_packaging_impl:pass4-scope-sha-red-2-failed`、
  `agent:/root/formats_packaging_impl:pass4-scope-sha-green-2-pass`。

Pass1 F1-F3、Pass3 合法小图/畸形 WebP/像素超限及本节 multipart 独立单测的历史 RED 例外均继续
保留；后续 GREEN 不改变当时没有单独先 RED 的事实。

## Pass 5 rework

### F1/F2 P1 · VLM 异常归一与成品 smoke 双路径硬门禁

- 首轮 RED：`uv run pytest -q tests/test_ocr_engine_fallback.py tests/test_smoke_document_formats.py`
  → `13 failed, 43 passed`。失败覆盖 OpenAI-compatible 的空白/非字符串 content、非法 UTF-8、协议
  截断未稳定归一为 `OcrDependencyError`，以及格式 smoke 未禁用/拒绝 cache hit、未对要求的 OCR
  后缀硬校验 VLM/Tesseract engine 与 degraded 状态、未写机器可断言的 OCR expectation。
- 资源错误边界 RED：
  `uv run pytest -q tests/test_ocr_engine_fallback.py::test_openai_compatible_http_error_detail_does_not_swallow_resource_error`
  → `1 failed`。HTTP error detail 读取时的 `MemoryError` 被过宽异常归一吞掉；该反例要求取消/资源
  错误继续原样传播，不能为了 fallback 捕获 `BaseException`。
- GREEN：`uv run pytest -q tests/test_ocr_engine_fallback.py tests/test_ocr_engine.py tests/test_smoke_document_formats.py`
  → `70 passed`。远端可恢复的编码/协议/返回结构异常进入 Tesseract fallback；资源与取消异常不被
  吞；smoke 禁用缓存并拒绝 `from_cache=true`，可分别硬门禁 VLM 正常路径与 Tesseract degraded 路径。
- 来源：`agent:/root/ocr_core_impl:pass5-f1-f2-red-13-failed-43-pass`、
  `agent:/root/ocr_core_impl:pass5-resource-boundary-red-1-failed`、
  `agent:/root/ocr_core_impl:pass5-ocr-smoke-green-70-pass`。

### F3 P1 · criteria 数值满分必须非负且有限

- RED：`uv run pytest -q tests/test_tender_info_extraction.py -k 'negative_or_non_finite_numeric_max'`
  → `4 failed`；`-1`、`NaN`、`Infinity`、`-Infinity` 均被语义闸错误接受。
- GREEN：同一命令复跑 → `4 passed`；全文件
  `uv run pytest -q tests/test_tender_info_extraction.py` → `44 passed`。
- 来源：`agent:/root/criteria_null_impl:pass5-f3-red-4-failed`、
  `agent:/root/criteria_null_impl:pass5-f3-green-4-pass`、
  `agent:/root/criteria_null_impl:pass5-f3-file-44-pass`。

### D1 P1 · 前端分类摘要复用 model 单一派生源

- RED：`bun test src/features/contract/tender-review/model.test.ts` → `47 pass, 1 fail`；组件仍各自
  reduce `item.max`，没有消费 model 统一生成的 category summaries。
- GREEN targeted：`bun test src/features/contract/tender-review/model.test.ts src/features/contract/tender-review/components/criteria-null-display.test.ts`
  → `51 pass`。
- 前端全量：`bun run test && bun run build && bun run lint` → `164 pass`；TypeScript/Vite build
  成功（仅既有 chunk-size warning），ESLint 通过。
- 来源：`agent:/root/criteria_null_impl:pass5-d1-red-1-failed-47-pass`、
  `agent:/root/criteria_null_impl:pass5-d1-green-51-pass`、
  `agent:/root/criteria_null_impl:pass5-frontend-full-164-pass-build-lint`。

### Pass5 targeted 质量门禁

- Python targeted Ruff 通过。
- `uv run python scripts/generate_document_formats.py --check` 通过。
- `uv run python scripts/smoke_document_formats.py --help` 通过。
- scoped `git diff --check` 通过。
- 来源：`main-agent:pass5-targeted-quality-generator-help-diff-green`。

本节只记录上述实际 RED/GREEN；没有为已经在实现后新增或只在最终回归中出现的断言补造先 RED。
T5 仍需 Pass6 与 System 强制 polish，T6 的 Debian ARM64 成品镜像/部署验收仍为 pending。

## Pass 6 FAIL rework

本轮 reviewer/evaluator 判定为 FAIL 后，以下反例均实际先失败。原始回报未附每个 RED 批次的完整
shell 展开，因此只记录真实测试锚点与结果，不反向编造命令文本。

### F1 · 空 OCR 页不得被页锚伪装成有效正文

- RED：pipeline 页锚有效性与格式 smoke 空底稿反例合计 `4 failed`。OCR pages 只有
  `【第 N 页】` 或空白内容时仍被判为有效，smoke 也会接受该伪底稿。
- 测试锚点：`tests/test_ocr_pipeline.py::test_is_ocr_text_valid_rejects_page_anchors_without_recognized_text`、
  `tests/test_smoke_document_formats.py::test_run_smoke_rejects_ocr_pages_containing_only_page_anchors`。

### F1/F2 · Tesseract 空 stdout 与 HTTPError detail I/O

- RED：Tesseract `None`/空 bytes/纯空白 stdout 与 HTTPError detail 可恢复 I/O 异常合计
  `7 failed`。前者被包装成带页锚的成功页；后者越过 `OcrDependencyError`，不能进入 fallback。
- 测试锚点：`tests/test_ocr_engine_fallback.py::test_tesseract_blank_stdout_is_dependency_failure`
  及 HTTPError detail I/O 参数化反例。

### F3 · 两层 MemoryError 必须原样传播

- RED：`2 failed`。`recognize()` 层资源耗尽及 native 抽取层资源耗尽均被外层普通错误/转换 fallback
  吞掉。
- 测试锚点：`tests/test_ocr_pipeline.py` 中 OCR backend 与 native presentation 两层
  `MemoryError` 传播反例。

### KD1-D1 · PPTX 图片元数据与混合扫描路由

- RED1：PPTX reader 图片元数据反例 `2 failed`，native 结果未稳定提供图片信号与非空白字符计数。
- RED2：混合 PPTX 路由反例 `1 failed`，少量标题 + 扫描图片错误停留在 native。
- 固定门禁：`image_count >= 1` 且 `non_whitespace_char_count < 80` 时升级到
  LibreOffice convert/OCR；纯文字、表格，或“含图片且非空白文字 >= 80 字符”均保持 native。
- 测试锚点：`tests/test_ocr_native_formats.py::test_real_pptx_reader_detects_scanned_picture_with_short_title`、
  `tests/test_ocr_pipeline.py::test_pptx_short_text_with_image_converts_to_pdf_and_ocr`、
  `test_pptx_without_scan_signal_or_with_sufficient_text_stays_native`。

### Pass6 targeted GREEN / 质量门禁

- OCR/格式 7 文件 targeted：`167 passed, 5 warnings`。范围为
  `tests/test_ocr_engine_fallback.py`、`tests/test_ocr_pipeline.py`、
  `tests/test_smoke_document_formats.py`、`tests/test_ocr_native_formats.py`、
  `tests/test_ocr_office_convert.py`、`tests/test_ocr_classify.py`、
  `tests/test_supported_document_formats.py`。
- 阶段性 targeted 后新增 `CompletedProcess.stdout is None` 反例，实际 RED `1 failed`；修复后同一
  7 文件 targeted 为 `168 passed, 5 warnings`。这是 Pass6 实现过程中的独立小闭环，不能把此前
  `167 passed` 覆盖成从未发生。
- targeted Ruff、`scripts/generate_document_formats.py --check` 与 scoped `git diff --check` 全绿。
- 来源：`agent:/root/ocr_core_impl:pass6-page-anchor-smoke-red-4-failed`、
  `agent:/root/ocr_core_impl:pass6-tesseract-http-detail-red-7-failed`、
  `agent:/root/ocr_core_impl:pass6-memory-red-2-failed`、
  `agent:/root/formats_packaging_impl:pass6-pptx-metadata-red-2-failed`、
  `agent:/root/formats_packaging_impl:pass6-pptx-mixed-route-red-1-failed`、
  `main-agent:pass6-ocr-format-targeted-167-pass-quality-green`、
  `agent:/root/ocr_core_impl:pass6-tesseract-none-stdout-red-1-failed`、
  `main-agent:pass6-ocr-format-targeted-168-pass-quality-green`。

最终全量结果尚待主 agent 补充；T5 仍为 `in_progress`，需 Pass7 与 System 强制 polish；T6 仍为
`pending`，不得提前宣称演示环境验收完成。

## Pass 7 CONCERNS closure

本轮只关闭 `reviews/pass7.md` 的两个 P1；RED 来自实现 agent 在修复前执行的真实反例，polish
另行抽取关键用例复核，不把复核结果倒签成 RED。

### F1 P1 · HTTP 200 响应体 I/O 失败必须进入 Tesseract fallback

- RED：HTTP 200 的 `response.read()` 抛 `OSError` / `ConnectionResetError` 反例为 `2 failed`；
  可恢复传输异常越过 `OcrDependencyError`，没有进入 Tesseract。
- GREEN：最终 OCR 三文件 targeted
  `tests/test_ocr_engine.py tests/test_ocr_engine_fallback.py tests/test_ocr_native_formats.py`
  → `89 passed, 5 warnings`；补充集成断言确认 connection reset 后结果为
  `engine=tesseract, degraded=true`，同时 `MemoryError` / 取消异常仍原样传播。
- 来源：`agent:/root/pass5_ocr_smoke_fix:pass7-f1-red-2-failed`、
  `agent:/root/pass5_ocr_smoke_fix:pass7-green-89-pass`、`reviews/pass7.md#F1`。

### F2 P1 · PPTX GroupShape 必须递归发现扫描图片

- RED：真实 grouped PPTX 与嵌套 mock 反例为 `2 failed`；短标题非空，但分组内扫描图片未计数，
  因而错误停在 native。
- GREEN：同一 `89 passed, 5 warnings` targeted 证明 GroupShape 递归后图片信号为 1，且嵌套
  文本、表格、图片均只统计一次；扫描型短文本 deck 会升级到 convert/OCR。
- 来源：`agent:/root/pass5_ocr_smoke_fix:pass7-f2-red-2-failed`、
  `agent:/root/pass5_ocr_smoke_fix:pass7-green-89-pass`、`reviews/pass7.md#F2`。

### Polish 独立复核

- 抽取上述可恢复 I/O、致命错误传播、Tesseract 集成 fallback、真实 grouped PPTX、嵌套唯一计数
  用例执行 → `8 passed, 5 warnings`。
- 来源：`chunk:10e727`。

## 最终独立回归

以下命令由主 agent 在所有已汇合改动上独立执行，不复用实现 agent 的 targeted 结论。

| 范围 | 命令 | 结果 | 来源标识 |
|---|---|---|---|
| 后端全量 | `CLAUDE_CODE_MAX_OUTPUT_TOKENS=8192 uv run pytest -q` | `1099 passed, 2 skipped, 9 warnings` | `main-agent:final-backend-1099-pass-2-skip` |
| 后端质量与生成物 | `uv run ruff check . && uv lock --check && uv run python scripts/generate_document_formats.py --check && git diff --check` | Ruff、lock、格式生成物漂移检查及 diff check 全部通过。 | `main-agent:final-backend-quality-green` |
| 前端全量 | `bun run test && bun run build && bun run lint` | `161 pass`；build 成功，仅有既有 chunk size warning；ESLint 通过。 | `main-agent:final-frontend-161-pass-build-lint-green` |
| 最新后端全量 | `CLAUDE_CODE_MAX_OUTPUT_TOKENS=8192 uv run pytest -q` | `1105 passed, 2 skipped, 9 warnings` | `main-agent:final-backend-1105-pass-2-skip` |
| 最新前端全量 | `bun run test && bun run build && bun run lint` | `164 pass`；build 成功，仅有既有 chunk size warning；ESLint 通过。 | `main-agent:final-frontend-164-pass-build-lint-green` |
| Pass4 最终后端全量 | `CLAUDE_CODE_MAX_OUTPUT_TOKENS=8192 uv run pytest -q` | `1112 passed, 2 skipped` | `main-agent:final-backend-1112-pass-2-skip` |
| Pass4 最终质量与生成物 | `uv run ruff check . && uv lock --check && uv run python scripts/generate_document_formats.py --check && git diff --check` | Ruff、lock、格式生成物漂移检查及 diff check 全部通过。 | `main-agent:pass4-final-quality-green` |
| Pass4 最终前端 | `bun run test && bun run build && bun run lint` | `164 pass`；build 成功，仅有既有 chunk size warning；ESLint 通过。 | `main-agent:final-frontend-164-pass-build-lint-green` |
| Pass5 首次后端全量（环境预算假红） | `uv run pytest -q` | `7 failed`；均为既有 `audit_direct` 测试在 token budget 门禁前失败，未使用演示实际 `CLAUDE_CODE_MAX_OUTPUT_TOKENS`。这是环境参数不一致，不是本轮产品 TDD RED。 | `main-agent:pass5-full-unbudgeted-7-failed-environment` |
| Pass5 最终后端全量 | `CLAUDE_CODE_MAX_OUTPUT_TOKENS=16000 uv run pytest -q` | `1131 passed, 2 skipped, 9 warnings` | `main-agent:pass5-final-backend-1131-pass-2-skip` |
| Pass5 最终后端质量与生成物 | `uv run ruff check . && uv lock --check && uv run python scripts/generate_document_formats.py --check && git diff --check` | Ruff、lock、格式生成物漂移检查及 diff check 全部通过。 | `main-agent:pass5-final-quality-green` |
| Pass6 首次后端整合（补丁前） | `CLAUDE_CODE_MAX_OUTPUT_TOKENS=16000 uv run pytest -q` | `1 failed, 1151 passed`；唯一失败即 `CompletedProcess.stdout is None`，发生在该小闭环补丁前，不能记为全绿。 | `main-agent:pass6-first-full-1-failed-1151-pass` |
| Pass6 最终后端全量 | `CLAUDE_CODE_MAX_OUTPUT_TOKENS=16000 uv run pytest -q` | `1152 passed, 2 skipped, 9 warnings` | `main-agent:pass6-final-backend-1152-pass-2-skip` |
| Pass6 最终后端质量与生成物 | `uv run ruff check . && uv lock --check && uv run python scripts/generate_document_formats.py --check && git diff --check` | Ruff、lock、格式生成物漂移检查及 diff check 全部通过。 | `main-agent:pass6-final-quality-green` |
| Polish 最终后端全量 | `CLAUDE_CODE_MAX_OUTPUT_TOKENS=16000 uv run pytest -q` | `1160 passed, 2 skipped, 9 warnings` | `chunk:b04fdd` |
| Polish 最终前端 | `bun run test && bun run build && bun run lint` | `164 pass`；build 成功（仅既有 chunk-size warning），ESLint 通过。 | `chunk:116481` |
| Polish 质量与本次前端格式 | `uv run ruff check . && uv lock --check && uv run python scripts/generate_document_formats.py --check && git diff --check`，再对本次 14 个前端变更文件执行 Prettier check | Ruff、lock、generator、diff 与 scoped Prettier 全绿。 | `chunk:32f89a` |
| 仓库级 Prettier 基线（信息项） | `bun run format:check` | 发现 99 个本 sprint 外既有文件未格式化；遵守“仅修本次范围”未批量改动，不计为本 sprint 失败。 | `chunk:116481` |

主 agent 最新质量与 evidence JSON 校验链全部通过；该回报未附完整 shell 展开，故不补写命令文本。
来源：`main-agent:final-quality-evidence-json-green`。

主 agent 另行独立执行格式扩展回归：

```bash
CLAUDE_CODE_MAX_OUTPUT_TOKENS=8192 uv run pytest -q \
  tests/test_supported_document_formats.py \
  tests/test_smoke_document_formats.py \
  tests/test_ocr_office_convert.py \
  tests/test_office_macro_safety_smoke.py \
  tests/test_ocr_native_formats.py \
&& uv run ruff check \
  server/ocr/office_convert.py scripts \
  tests/test_supported_document_formats.py \
  tests/test_smoke_document_formats.py \
  tests/test_ocr_office_convert.py \
  tests/test_office_macro_safety_smoke.py \
  tests/test_ocr_native_formats.py \
&& uv run python scripts/generate_document_formats.py --check \
&& git diff --check
```

结果：`37 passed`，Ruff、生成物漂移检查及 diff check 全绿。来源：
`main-agent:final-formats-37-pass-quality-green`。
