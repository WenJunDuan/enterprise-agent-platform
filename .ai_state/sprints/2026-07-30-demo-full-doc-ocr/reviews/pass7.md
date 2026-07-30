# Pass 7 Review — 2026-07-30-demo-full-doc-ocr

## Reviewer (代码层 findings, pass7)

### F1 [P1] HTTP 200 响应体读取异常绕过 Tesseract fallback

- `_call_openai_compatible_vlm` 只把 `HTTPError` 详情读取的 `OSError` 归一；正常 HTTP 200 分支的
  `response.read()` 若抛 `OSError` / `ConnectionResetError`，会原样越过 `OcrDependencyError` 边界。
- 独立反例确认 `ConnectionResetError("peer reset during successful response body")` 原样逃逸，扫描件不会进入
  已设计的 Tesseract 降级链，影响 AC4 的远端失败续跑语义。

### F2 [P1] PPTX GroupShape 内图片未递归计数

- `read_presentation` 只遍历 slide 顶层 shape；当扫描图片嵌套在 GroupShape 中时，图片信号被漏掉。
- 独立真实 PPTX 反例得到 `image_count=0, text_char_count=4`。短标题使 native 非空，但
  `_presentation_needs_ocr` 因图片数为零返回 false，扫描正文停留在 native，影响 KD1 / AC1。

### 既有 findings 闭环

- Pass6 F1-F3 与 KD1-D1 的既有反例已闭环；本轮未发现其回归。

## Spec Compliance (spec-compliance, pass7)

### MISSING (做少了)

- 无。

### EXTRA (做多了)

- 无不合理 scope creep。

### DEVIATED (做偏了)

- 无。

Spec Compliance 总评：**PASS**。

## VERDICT (evaluator, pass7)

**判定**: CONCERNS

### 评分依据 (4 维)

| 维度 | 得分 (0-5) | 说明 |
|---|---:|---|
| Functionality | 3.4 | 主矩阵已实现，但 F1、F2 分别破坏远端失败 fallback 与分组扫描 PPTX 正文读取 |
| Spec Compliance | 4.5 | spec-compliance 无 MISSING / EXTRA / DEVIATED；问题属于实现边界缺陷 |
| Craft | 3.8 | 既有 TDD 与全量回归充分，但 HTTP 200 body I/O 和递归 shape 两个反例未被覆盖 |
| Robustness | 3.2 | 正常响应读取异常未归一，嵌套 Office 结构未完整遍历 |

总评: **3.7 / 5.0**

### 触发判定的关键 findings

- F1 (P1)：正常 HTTP 200 的 `response.read()` 可抛 `ConnectionResetError` 并绕过 Tesseract fallback。
- F2 (P1)：GroupShape 内图片不计数，短标题 + 分组扫描图 PPTX 会错误停在 native。
- 两条 P1 少于 3 条且 spec PASS，不触发 REWORK；但 T5 尚未完成、T6 仍 pending，Sisyphus 不完整，
  因而触发 CONCERNS。

### 行动建议

- 进入 System 强制 polish 时先以 TDD 修复 F1、F2，并执行 OCR/PPTX targeted 与后端全量回归。
- F1 应仅归一可恢复 I/O 异常并保留 `MemoryError` 等资源错误传播；F2 应递归遍历 GroupShape，且避免
  重复统计文本、表格或图片。
- 两项关闭并完成 cleanup/architecture 后再进入 T6；不得在修复前构建或替换 demo 容器。

### Sisyphus 完整性检查

- [ ] design.md 中所有 Task 完成（T5 in_progress；T6 pending）
- [ ] 所有 Task 验收标准过测试（F1、F2 尚缺 RED→GREEN；AC5/8/9/10 待 T6）
- [x] (Refactor/System 路径) 可进入 polish stage，先关闭 Pass7 concerns
