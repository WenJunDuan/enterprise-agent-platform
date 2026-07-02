---
doc_type: decision
date: 2026-07-02
slug: ocr-routing-ladder
sprint: 2026-07-02-eval-tender-scaffold
---

# Decision · OCR 五级路由决策梯（D4 设计基准）

> 2026-07-02 用户拍板。D4（L2 多模型路由）的设计基准，实施时以此为纲。
> 部署前提：部署机三 OCR 模型（PaddleOCR / PaddleOCR-VL / Unlimited-OCR）+ litellm 网关。

## 决策梯（成本单调递增，只升不降）

```
T0 直读（零模型成本）—— 能直读绝不 OCR
   excel/csv/text → openpyxl 等包直读
   .docx 有文本层 → python-docx；.doc → 原生文本抽取
   PDF 有文本层 → 直抽；混合 PDF → 数字页直读 + 扫描页子集 OCR 回填
   （classify L1 + native.py 已实现，保持不动）

T1 打底 OCR —— 清晰印刷扫描页 → PaddleOCR 经典管道（最快最便宜）

T2 升级 —— _page_confidence 低 / 版面复杂 / 表格
   → PaddleOCR-VL（extract_pdf_subset 只重跑差页，不重跑全本）

T2s 专科 —— 印章页 → seal 产线（编排进主流程，现有 recognize_seal）

T3 长程 —— 整本需全局结构（标书章节树/目录/跨页表格）
   → Unlimited-OCR（一次前向数十页，喂 D6 结构化 + D8 底稿瘦身）

T4 兜底 —— 手写/疑难/以上全部低置信
   → 系统配置文件配置的多模态大模型（MODEL_BASE_URL/MODEL_NAME 网关配置，
     platform/config.py _forward_model_env；当前部署=内网 qwen3.6-27b）
```

## Why

1. **期望成本最小化**：绝大多数页停在 T0/T1，只有低置信页向上付费；
   "最佳效能"= 期望成本最低，不是每页用最强模型。
2. **T4 不 pin 型号**（用户修正）：兜底大模型复用系统级模型配置单一来源，
   不新增 OCR 专属 model env——换模型改 .env 不改代码，与 D3
   "prompt 单源统一"同一哲学（配置也单源）。
3. **直读优先显式化为 T0**（用户修正）：直读不是 OCR 的旁路，是阶梯底座；
   混合 PDF 的页级"直读+补 OCR"（pipeline._augment_mixed_pdf_blocks）
   已是 T0/T1 混排的生产先例。

## How to apply（D4 实施锚点）

- engine.recognize() 的 env if/elif → EngineRegistry + 能力画像 + 路由策略。
- 升级信号复用现成资产：_page_confidence / file_clarity / extract_pdf_subset。
- cache._engine_fingerprint 升 per-engine 进 cache key（防跨引擎缓存污染）。
- 各级能力画像与置信阈值以 D4 POC 实测为准（铁律[出处优先]，不凭记忆填基准）。
- 页锚【第N页】全链路保真是每一级的硬约束（evidence-resolution 红线）。
- 改动须过 D1 golden case 回归闸（D1 前置）。

相关：[[2026-07-01-learning-flash-tender-eval-inconsistency]]（底稿超长是根因，T3 服务于此）
