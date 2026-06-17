---
name: multi-ocr-recognize
description: 对扫描 PDF / 图片 / 图片型 Word 调用 PaddleOCR-VL 完整 pipeline，输出版面、文本、表格(Markdown/JSON)
---

# 扫描件 OCR（PaddleOCR-VL）

仅用于**没有文本层**的输入。引擎自带 PP-DocLayoutV2 版面分析：页内自动定位+分类区域（正文/表格/公式/印章/图）并排序，再逐区域识别——"先分类再识别"在引擎内部完成，调用方无需手写元素路由。

## 调用

实现：`server/ocr/engine.py:recognize`（模型/端点/参数见 `references/engines.md`）。

- 默认模型 `PaddleOCR-VL-1.6`（当前 OmniDocBench v1.6 SOTA），经 env `OCR_VL_MODEL` 可调。
- **必须走完整 pipeline（版面+VLM），不要只打裸 VLM 端点**，否则易掉精度/幻觉（官方明确提示）。
- vLLM/SGLang 加速后端地址经 env `OCR_VL_BACKEND_URL` 注入。

## 输出

JSON：每页 `markdown` + `layout`(区域 bbox/类别) + 分离出的印章/图，置信度随附。
表格优先以 Markdown/HTML 结构保留，供子表抽取。

## 注意

数字/日期是回填高风险位——OCR 结果中的金额、计划日期一律带置信度回传，低于阈值交 `multi-ocr-form-fill` 标记人工。
