---
description: 合同审查：读取合同与条款，按本地 legal 规则判定风险与合规，一次性内联产出结论并抽取合同结构
allowed-tools: Read, Glob, Skill
---

读取指定合同目录或文件（含主合同、补充协议、附件等），**在当前会话内一次性完成审查并直接输出最终结论**。你直接 `Read` 文件（PDF/图片/文本均可），不依赖 OCR 预处理。

## 执行方式（单 agent 内联五步，少往返）

为把单次审查压进可控时延，**默认不 spawn 子 agent**，由你在本会话内连续完成 S0–S4。

### S0 立案清点
- 用**一次** `Glob` 列目录文件。按文件名/内容分类：主合同、补充协议、附件、发票、审批单。
- 形成文件清单。不要逐字深读，先建索引。

### S1 规则计划
- `Read` 本案适用的本地 legal 规则：`knowledge/legal/*.rules.json`（合同审查通则 / 付款合规 / 条款必备项等）。
- 把规则逐项展开为审查计划：每项记 `{check_item, rule_ids, 需读条款}`。
- 规则缺失时，对相关审查项按降级走 `manual_review`（`rule_gap`），**不要现场从合同文本编造合规规则**。

### S2 事实抽取（把大文件压成小底稿）
- `Read` 合同相关文件，抽取审查所需事实，对齐 `.claude/contracts/legal/extract-result.schema.json`：
  - `parties`：各方 `名称 / 角色（甲方/乙方/担保方…）`
  - `contract_meta`：标题 / 合同编号 / 签订日期 / 合同金额 / 币种 / 期限
  - `clauses`：关键条款 `{clause_id, type（付款/违约/保密/质保/争议解决…）, text, page}`
  - `payment_nodes`：付款节点 `{node_id, name（预付款/进度款/质保金…）, amount, ratio, due_condition, due_date, page}`
  - `attachments`：附件清单及类型
- 一致性线索写进 `ambiguities`，例如"合同金额与付款节点合计不符""签约主体与发票抬头不一致""补充协议与主合同付款条款冲突"。
- 只抽事实，不在本步下结论。把抽出的结构整理为 `extracted_data.contract`（供平台落入合同库）。

### S3 风险 / 合规评判
- 对审查计划每一项，结合事实底稿（必要时按页码回读条款原文）判定：
  - 条款合规（必备条款是否齐备、是否违反 legal 规则）
  - 付款合理性（付款节点合计是否等于合同金额、比例/条件是否异常、是否缺质保金等）
  - 主体一致性（签约方与发票/审批主体是否一致；补充协议与主合同是否冲突）
- 命中不可依文档判定的项（需外部数据/需业务确认）→ 该项 `manual_review`，**不要主观臆断为合规或违规**。
- 一致性冲突（金额不符、主体不一致、条款冲突）→ 相关项 `manual_review`，`manual_review_reason:"data_conflict"`，证据链**同时引用冲突的两处出处**（条款页 + 对照页）。

### S4 汇总结论
- 合成最终 `verdict`：
  - 命中重大违规/缺必备条款且不可补正 → `rejected`
  - 存在 `manual_review` 审查项，或关键证据缺失/规则缺口/证据冲突 → `manual_review`（填 `manual_review_reason`）
  - 全部审查项合规且无冲突 → `approved`
- 给出 `policy_refs`（命中的 legal `rule_id`）、`evidence_chain`、`risk_score`，并把合同结构留在 `extracted_data.contract`。

## 输出契约

1. 最终结论必须符合 `.claude/contracts/common/audit-result.schema.json`。决策只用 `verdict`（`approved` / `rejected` / `manual_review`），不要输出 `result` / `conclusion`（服务端从 `verdict` 派生）。
2. `claim_id` 为合同编号或合同标识（找不到填合同标题）。
3. `explanation` / `reasons` / `evidence_chain` 用中文，措辞平实、专业、克制（像法务审查意见）：禁用夸张或口语词（硬伤、铁证、实锤等），定性留有余地（用"疑似/需人工核实"，证据不确凿不下终局结论）。
4. `evidence_chain[].source` 写明条款与页码出处（如"采购合同 第3.1条 (p.2)"）；合同库主键 `contract_id` 由平台在落库时生成，**你不要编造 contract_id**。
5. `manual_review` 时，`explanation` 必须写明哪些审查项不能判定、缺什么材料、哪条规则无法闭合，并填 `manual_review_reason`（只能取 `missing_approval` / `rule_gap` / `data_conflict` / `insufficient_evidence` / `budget_exceeded` / `invoice_invalid` / `pre_approval_mismatch` 之一最贴切者）。
6. `extracted_data.contract` 为本次抽取的合同结构 `{parties, contract_meta, clauses, payment_nodes, attachments}`（供平台落入合同库）。
7. 只返回一个 JSON 对象，直接符合 `audit-result` 契约；不要输出 Markdown、表格、前言或任何 JSON 之外的文字。
8. 合同审查只用本地规则与制度文件，不使用训练记忆中的规则，不编造缺失的规则、条款或审批记录。

## 复核

- 当前为一次性内联审查，**默认不调度 `contract-reviewer`**；高风险/证据冲突在 `verdict`/`risk_score`/`explanation` 中如实标注，交人工处理。

参数: $ARGUMENTS
用法: /review-contract data/contracts/<合同目录或文件>
