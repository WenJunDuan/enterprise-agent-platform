---
name: multi-ocr-classify
description: 判定文档容器类型(Word/Excel/PDF/图片/文本)与是否含文本层，输出原生直读 / OCR / 人工的路由决策
---

# L1 容器分诊

按**文件类型**决定后续路径——"先分类再 OCR"的第一层。第二层（页内元素：正文/表格/印章）由 OCR 引擎的版面分析原生完成，不在此处理。

## 判定

实现：`server/ocr/classify.py`（纯标准库，`tests/test_ocr_classify.py` 覆盖），依据：

- 扩展名 → 容器类型（Excel / 文本 / 图片 / Word / PDF）
- PDF：字节探测字体(`/Font`)与图像滤镜(`/DCTDecode` 等)，判文本层 vs 扫描
- DOCX：探测 zip 内 `word/media/` 图像量 vs 正文文字量，判文本型 vs 图片型

## 输出

一行 JSON：`container` / `route`(native|ocr|manual) / `handler` / `has_text_layer` / `pages` / `reason`。

## 铁律

- Excel 一律 `route=native`，**绝不 OCR**（数字文件 OCR 会更慢且把金额/日期认错）。
- 拿不准（未知扩展名 / 损坏文件）→ `route=manual`，不猜。
