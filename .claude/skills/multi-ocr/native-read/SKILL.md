---
name: multi-ocr-native-read
description: 对 Excel / 文本型 Word / 纯文本 / 文本层 PDF 直接读取结构化内容，不经 OCR（更快且零识别误差）
---

# 原生直读

数字文件直接读：毫秒级、零 OCR 误差、保留行列/合并单元格/公式/数据类型。

## 处理

实现：`server/ocr/native.py`：

- Excel → openpyxl（`read_only` + `data_only`），逐 sheet 输出行
- 文本型 Word → python-docx，输出段落 + 原生表格
- 纯文本 / CSV → 直读
- 文本层 PDF → pypdf 抽文本

## 输出

JSON：`kind` + `blocks`(文本) + `tables`(行列)，语义对齐 `.claude/contracts/ocr/extract-result.schema.json`。

## 注意

- 缺依赖（openpyxl / python-docx / pypdf）时 `server/ocr/native.py` 抛 `OcrDependencyError`（带安装提示），不静默失败。
- 超大 Excel 单 sheet 截断到安全行数上限，避免撑爆上下文（见 `server/ocr/native.py:MAX_EXCEL_ROWS`）。
