---
date: 2026-08-14
type: issue-report
slug: tender-eval-blocked
path: Bugfix
---

# 2026-08-14 评标无结论（生产 P0）

部署机 100.91.100.13 实测。部署实态：`MODEL_NAME=deepseek-v4-flash`、
`MODEL_CONTEXT_WINDOW=1048576`、`CLAUDE_CODE_MAX_OUTPUT_TOKENS=32000`、
`AUDIT_MAX_TURNS` 未设（默认 30）、`TENDER_CONTEXT_MAX_BYTES` 未设（默认 64000）。

前情：用户报「回退提示词好像没生效」。实测证伪——容器内 `tender-evaluate.md` 38,754 B、
`SKILL.md` 5,868 B，与基线逐字节一致，回滚已生效；失败换了新原因。

## 现象 A：评标耗尽 30 轮无结论

日志 `tender_context_truncated original_bytes=103335 kept_bytes=63999 limit_bytes=64000`。

模型思考原文：`"does NOT include 第四章 评审方法和程序 (the critical evaluation
method/scoring criteria section). This is a critical problem."` 模型反复 Read 原文件
找评分标准 → `result_subtype: error_max_turns`。

## 现象 B：投标文件完全读不出

日志 `PaddleOCR 云调用失败：<urlopen error EOF occurred in violation of protocol
(_ssl.c:2427)>` → `tender_bid_doc_ocr_failed`。

逐层实测定位：

| 实测项 | 结果 |
|---|---|
| 投标 PDF 体量 | 400 页 / 43.2 MB |
| TLS 握手 | 正常（TLSv1.2 ECDHE-RSA-AES256-GCM-SHA384），非证书/协议问题 |
| 单页 302 KB 上传 | 成功返回 jobId |
| 43 MB **走代理** | `EOF in violation of protocol`（中途断连） |
| 43 MB **绕过代理** | 完整传完 56.6s，但服务端回 `HTTP 400` |
| 50 页 / 3.24 MB | 成功 |
| 80 页 | `HTTP 400` |
| 连发大包后 2 页 | `HTTP 400`；冷却几十秒恢复（服务端限流） |
| `extract_pdf_subset` 裸存 | 100 页子集 43.6 MB > 400 页原文件 43.2 MB；50 页子集 20.3 MB |
| 同上加 `garbage=4/deflate/clean` | 50 页 → 3.24 MB（6 倍压缩） |

代理配置：`.env` 设 `HTTP_PROXY/HTTPS_PROXY=http://192.168.1.180:6152`，
`NO_PROXY` **不含** `paddleocr.aistudio-app.com`。公网端点直连实测均可达
（api.deepseek.com 0.15s / paddleocr.aistudio-app.com 0.2s）。

## 相关档案

`.ai_state/compound/2026-08-14-learning-prompt-budget-must-be-per-session.md`
（同日上游事故：提示词重构导致的上下文预算教训）
