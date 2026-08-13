# 输出 JSON 细则（权威版）

> 由 `/tender-evaluate` 产出最终 JSON **之前**确定性 `Read`（一次）。命令骨架只留输出契约
> 核心（单 JSON、`verdict` 三值、禁 `review_dimension`、措辞口径），**枚举全文、字段契约
> 对照与 JSON 合法性细则以本文件为权威**。

## manual_review_reason 枚举（全文）

- `manual_review` 时，`explanation` 必须写明哪些评分项不能自动判定、缺什么材料、哪条规则无法闭合，并填 `manual_review_reason`（只能取 `missing_approval` / `rule_gap` / `data_conflict` / `insufficient_evidence` / `budget_exceeded` / `invoice_invalid` / `pre_approval_mismatch` 之一最贴切者）。

## extracted_data 字段契约对照

- `extracted_data.eligibility_checks` 为最高优先级资格审查结果，必须先于 `scoring` 产出；`extracted_data.scoring` 为逐评分项 `{item, max, score, status, score_mode, basis, pending_reason（仅 score=null 时必填）, …按 mode 的 deduction_hits/selected_band/award_hits}`。资格审查不计入合计，未判定评分项 `score:null` 不计入合计。废标/资格走 `extracted_data.disqualification_hits` / `eligibility_checks`（独立 gate，**不混入 scoring**）。并在文字中说明需要什么外部输入（现场记录/外部评价表/全部投标报价）。

## 结论必须钉入的案卷头字段

- 结论须钉入 `extracted_data.bidder_info`（投标单位名称以投标函/营业执照原文为准，附 `source_refs` 页锚，对齐 `.claude/contracts/tender/bidder-info.schema.json`）与 `extracted_data.tender_info`（招标底稿/已注入 criteria 上下文可得时，对齐 `.claude/contracts/tender/tender-info.schema.json`，取 `project_name`/`tender_no`/`tenderee` 等子集即可）。**识别不到的字段省略，不编造**（保守原则）。

## JSON 合法性与单对象输出

   - **整个回复必须是单个 JSON 对象**：**首字符是 `{`、末字符是 `}`**；分析/思考只能写在 `<think></think>` 内，`</think>` 之后只准有这一个 JSON 对象；**禁止任何英文散文、要点列表或 JSON 之外的解释性文字**（违反会致服务端解析失败、整单评标失败）。
   - **JSON 合法性（极重要，违反会致解析失败）**：字符串值内引用项目名 / 项目号 / 投标人 / 评分项时，**一律用中文引号「」或『』**，**严禁在字符串值里用半角双引号 `"`**（会提前闭合字符串、破坏 JSON）；确需则转义为 `\"`。例：写 `"未响应「华为南通」项目"`，不要写 `"未响应"华为南通"项目"`。
