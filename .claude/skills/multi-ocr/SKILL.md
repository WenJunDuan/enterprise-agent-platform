---
name: multi-ocr-skills
description: Use when 需要把上传文档(Word/Excel/PDF/图片/文本)识别成结构化数据并回填表单字段，含合同付款节点抽取到预测付款子表
---

# 多源文档识别 → 表单回填总控

**先按文件类型分类，再决定走"原生直读"还是"OCR 识别"，最后映射到表单字段（含子表）。**
核心原则：能直读的绝不 OCR（更快、零识别误差、保留结构）；只有扫描件/图片才送 OCR 模型。

## 子能力

- `multi-ocr-classify` — L1 容器分诊：文件类型 + 是否含文本层 → 路由决策
- `multi-ocr-native-read` — 原生直读：Excel / 文本型 Word / 纯文本 / 文本层 PDF
- `multi-ocr-recognize` — 扫描件 OCR：扫描 PDF / 图片 / 图片型 Word → PaddleOCR-VL 全流程
- `multi-ocr-seal` — 印章/签章专项：印章定位 + 章内文字（印章压字硬指标）
- `multi-ocr-form-fill` — 字段映射：识别内容 → 6 类组件 + 合同预测付款子表

## 执行流程

确定性识别（分类 + 直读 / OCR）由 Python 包 `server/ocr/` 完成；本 skill / 模型只负责
**字段映射**这一判断步骤。两种用法：

- **服务端热路径**：`server/ocr/runner.py` 进程内调 `server.ocr.pipeline.extract_dir`
  （0 网关往返）→ 组装识别底稿 → **一次**模型映射 → 契约校验输出，无需任何工具。
- **交互式 `/multi-ocr`**：发**一次** Bash `python -m server.ocr <dir>` 拿整目录识别底稿
  （分类 + 直读 + OCR 已在 Python 内跑完），再据底稿映射到目标表单。

映射规则（见 `multi-ocr-form-fill` / `references/form-components.md`）：
- 单行 / 多行 / 下拉（命中 options）/ 数字（去千分位）/ 日期（归一 ISO）。
- 合同付款节点逐条抽取进预测付款子表，产出符合 `.claude/contracts/ocr/form-fill.schema.json`。
- 任一关键字段（金额 / 日期 / 付款节点）低置信或证据冲突 → 写入 `low_confidence` 并置
  `needs_review=true`，不强行回填（沿用本平台 manual_review 兜底文化）。

## 降级（任一即标 needs_review）

- 文件类型不在白名单 / classify 返回 `manual`
- OCR 置信度不足以稳定提取关键字段
- 印章压字 / 手写无法高置信识别（硬指标场景）
- 子表行数或列含义无法唯一确定

## 结构

```
server/ocr/            OCR 业务：确定性流水线 + 服务端薄层（单一来源，tests/ 可覆盖）
  classify.py  native.py  engine.py  pipeline.py  __main__.py  runner.py
.claude/skills/multi-ocr/
  SKILL.md             本文件（总控）
  classify|native-read|recognize|seal|form-fill/SKILL.md   子能力文档
  references/          routing.md · engines.md · form-components.md
.claude/contracts/ocr/ extract-result · form-fill schema
```

> 识别在 `server.ocr`（确定性、可测），映射判断在模型侧；对齐 `server.audit.runner` 的内联单跳，砍掉逐文件网关往返。
