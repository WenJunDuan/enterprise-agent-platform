---
name: vision-page
description: 就指定文件指定页的**一个判定点**带图问 VLM（证书有效期 / 公章归属 / 大写金额 / 检测报告标识等像素必需项），返回纯文本答案。当该页是扫描/盖章件、底稿转写为空或读不清、而判定又只差一个事实时使用。
---

# vision-page · 判定时刻带图问答

底稿是转写产物；扫描盖章页的转写常为空或失真。**要判定结论就直接看图**，不要先把图降维成
有损文字再去读。本技能不转写整页，只就一个问题问一次。

## 何时用（与 ocr-page 的分工）

| 你要什么 | 用哪个 |
|---|---|
| 一个判定结论：这页的章是谁的 / 有效期到哪天 / 大写与小写金额是否一致 / 检测报告上是什么标识 | **vision-page** |
| 整页文字：核 `【第N页】` 页锚、逐字引原文进 `evidence_chain` | `ocr-page` |

底稿里该页文字残缺 / 标了低置信（`evidence_resolution.low_clarity_files`）/ 印章压字 —
先带图问，问不出再退回 `ocr-page` 重识别。

## 怎么用

```bash
uv run python .claude/skills/vision-page/vision.py <PDF绝对路径> --page N --question "问句"
```

- `<PDF绝对路径>`：评标目录内的真实 PDF（工具面闸只放行本案目录内的文件）。
- `--page N`：页号，取底稿 `【第N页】` 锚点数字（不是文档印刷页号）。
- `--question`：**必须加引号**、一次只问一个判定点（问句内不得带引号或 shell 运算符，闸会拒）。
  好问句：`"这一页的公章上写的单位名称是什么"`、`"证书的有效期截止日期是哪天"`。
  坏问句：`"评一下这页"`（不是判定点）、`"把这页所有文字抄下来"`（那是 ocr-page 的活）。

## 读输出

- stdout 是**纯文本答案**。答案是模型读图的结论，**不是可逐字回查的原文**：据它判定可以，
  但写进 `evidence_chain` 的 `quote` 仍须引底稿逐字原文，页号照旧取底稿页锚。
- 答"图中看不清"/"图中没有该信息" → 按"读不清"窄情形降 `manual_review`
  （`insufficient_evidence`），**不要据此判 0**。
- `[错误] …`（stderr，非 0 退出）：`4` 渲染失败、`5` 端点不可用 → 改用 `ocr-page` 转写；
  仍不可读同样降 `manual_review`。

## 边界

- 只读、不写文件、不改库；渲染用的单页临时 PDF 用完即删。
- 只支持 PDF 页（渲染复用服务端隔离渲染进程，带像素/字节/超时上界）；其它形态用 `ocr-page`。
- 端点：`VISION_PAGE_URL` / `VISION_PAGE_MODEL`（OpenAI 兼容带图问答端点），未设时回落
  `OCR_VL_SERVER_URL` / `OCR_VL_MODEL_NAME`。**OCR_CLOUD=1 的部署必须单独设**——那时
  `OCR_VL_SERVER_URL` 是云 job API，不是 chat/completions。
- 一页一问一次调用：判定点多就多问几次，不要把多个问题塞进一句。
