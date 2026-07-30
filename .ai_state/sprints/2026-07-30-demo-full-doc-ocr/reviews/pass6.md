# Pass 6 Review — 2026-07-30-demo-full-doc-ocr

## Reviewer (代码层 findings, pass6)

### F1 [P0] Tesseract 空 stdout 被页锚包装成有效识别结果

- `server/ocr/engine.py` 的 `_recognize_tesseract_page` 在返回码为 0 时直接返回
  `output.strip()`，没有拒绝空白 stdout；上层仍生成 `pages`。
- `server/ocr/pipeline.py::_render_body` 会为该空页加入 `【第 N 页】`，随后
  `is_ocr_text_valid` 把页锚当成真实内容，导致全空 OCR 被报告为 ready。
- 影响：扫描标书可能静默成为“识别成功但无正文”，直接破坏 AC1/AC4 的非空底稿与可靠 fallback。

### F2 [P1] HTTPError body 读取异常仍可绕过 Tesseract fallback

- `_call_openai_compatible_vlm` 读取 HTTPError body 时仅捕获 `UnicodeDecodeError` 与
  `HTTPException`；`TimeoutError` 等可恢复读取异常会原样越过 `OcrDependencyError` 边界。
- 现有测试只覆盖 detail-read `MemoryError` 不应被吞，未覆盖可恢复的 `TimeoutError` 应归一后触发
  fallback。影响：网关已返回错误但错误体读取超时时，扫描件仍会直接失败。

### F3 [P1] pipeline 外层吞掉 MemoryError

- `_extract_one_raw` 以 `except Exception` 将所有失败归一为单文件 error，包含 `MemoryError`。
- 这与 Pass5 已建立的“资源错误不得被 fallback/归一吞掉”边界不一致；进程资源耗尽会被伪装成普通
  解析失败并继续运行，扩大不稳定状态。

### Pass5 闭环

- Pass5 F1-F3 与 D1 已有 RED→GREEN 及全量回归证据，本轮维持 CLOSED。
- AC5、AC8、AC9、AC10 仍按设计留给 Debian ARM64 成品镜像与 demo 部署验收，未提前宣称通过。

## Spec Compliance (spec-compliance, pass6)

### MISSING (做少了)

#### KD1-D1 [P1] 含少量标题与扫描图片的 PPTX 不会升级到转换/OCR

- KD1 明确要求 `.pptx` “含图且文字不足/抽空”走 LibreOffice→PDF→VLM→Tesseract。
- 当前分类对所有 PPTX 无条件选择 native；`read_presentation` 只抽文本/表格，不记录图片信号；pipeline
  又只在文本完全为空时转换。因此“少量标题 + 扫描图片正文”会因标题非空停在 native，图片正文丢失。
- 需要加入 PPTX 图片信号与“文字不足”门禁，并以真实混合 fixture 验证转换/OCR 路径及非空正文。

### EXTRA (做多了)

- 无不合理 scope creep。

### DEVIATED (做偏了)

- 无新增；本轮主要问题为 KD1 明确能力缺失。

Spec Compliance 总评：**REWORK**。

## VERDICT (evaluator, pass6)

**判定**: FAIL

### 评分依据 (4 维)

| 维度 | 得分 (0-5) | 说明 |
|---|---:|---|
| Functionality | 2.7 | F1 可把空 OCR 误报成功，KD1-D1 会丢 PPTX 扫描图片正文 |
| Spec Compliance | 2.9 | KD1 路由梯存在明确 MISSING；部署 AC 仍待 T6 |
| Craft | 3.5 | Pass5 已闭环且回归充分，但新增边界缺少针对性测试 |
| Robustness | 2.3 | F2 绕过 fallback，F3 吞资源耗尽，失败语义不可靠 |

总评: **2.9 / 5.0**

### 触发判定的关键 findings

- F1 (P0)：空 Tesseract stdout 被页锚误判为有效；未修复 P0 触发 FAIL。
- F2、F3 (P1)：可恢复 HTTPError 读取异常绕过 fallback，资源错误被外层吞掉。
- KD1-D1 (P1, MISSING)：PPTX 混合扫描内容未实现设计规定的升级路径。

### 行动建议

- 必须立即修：F1，并补空 stdout→结构化失败/terminal error 回归。
- 同轮修复 F2、F3、KD1-D1，分别锁住可恢复异常、资源错误传播与混合 PPTX 路由。
- 修复后执行新的 reviewer + spec-compliance + evaluator；通过后才可进入 System 强制 polish。
- AC5/8/9/10 继续 defer 到 T6 成品镜像和 demo 部署实证。

### Sisyphus 完整性检查

- [ ] design.md 中所有 Task 完成（T5 in_progress；T6 pending）
- [ ] 所有 Task 验收标准过测试（F1-F3、KD1-D1 未闭环；AC5/8/9/10 待 T6）
- [ ] (Refactor/System 路径) 准备进入 polish stage（FAIL，不可进入）
