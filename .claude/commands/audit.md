---
description: 审核单个输入文件或目录
allowed-tools: Read, Write, Glob, Skill, Task
---

**定性**：本文件是 CC 对话渠道（`/audit` 斜杠命令）的**审核执行入口**——生产入口，与 `server/routes/audit.py` HTTP 路径并列（路由表见项目 `CLAUDE.md`）。**判断纪律的唯一真相源 = `server/audit/runner.py:AUDIT_INSTRUCTIONS`**（HTTP 内联审核路径 `run_inline_directory_audit` 读的同一份常量）。本文件不重复判断细节，只负责本渠道特有的输入解析步骤与输出契约提示。

## 第一步（强制，不可跳过，不靠自觉）

判断前**必须** `Read server/audit/runner.py`，取其中 `AUDIT_INSTRUCTIONS` 常量原文，作为本次审核的判断纪律（规则命中优先级、金额/预算/流程判断、数据真实性核验、措辞规范、`manual_review` 分支、JSON 输出纪律等，一律以该常量原文为准）——不要凭训练记忆或上次会话的印象自行发挥，也不要只读本文件就下判断。若该文件不可读，直接输出 `verdict=manual_review`、`manual_review_reason=rule_gap`，并在 `explanation` 中说明无法取得判断纪律。

## 输入解析（低延迟：单 agent 内联，不嵌套子 agent）

为把单次审核压进 ~2 分钟，**默认不再 spawn `expense-extractor` / `expense-auditor` 子 agent**，由你在本会话内一次性完成"事实提取 + 合规判断 + 输出"（提取到判断的方法论以第一步取到的 `AUDIT_INSTRUCTIONS` 为准）。只有在确需跨域旁证（如报销材料是扫描件需先 OCR 识别）时才按需协同。

1. 解析输入，尽量少往返：
   - 目录：用**一次** `Glob` 列出目录内文件，再 `Read` 关键材料（`audit-request.json`、申请单、报销单、发票、行程单、酒店单据等），综合全部材料，不要只看第一个文件。
   - 单文件：直接 `Read`。
   - 不要用 `Bash test -d` / `find` 这类额外探测，能用 `Read` / `Glob` 就不要多发往返；同一份材料只读一次。
2. **一次性** `Read` 本案适用的本地规则文件（按 `category` 选择，可一并读取）：
   - 差旅 / 住宿 / 交通 / 伙食补助 → `knowledge/expense/travel.rules.json`
   - 工作餐 / 快餐 → `knowledge/expense/meal.rules.json`
   - 接待 / 商务餐 / 公务接待 / 陪餐 → `knowledge/expense/entertainment.rules.json`
   读取每个规则文件顶层 `source` 作为追溯信息；不要现场从 PDF 重新造规则。规则文件缺失时按 `AUDIT_INSTRUCTIONS` 的降级规则输出 `manual_review`（`rule_gap`），不要编造规则。
3. 如 `knowledge/memory/expense/` 中存在与本案高度相似的案例 / 异常 / 复核记忆，作为辅助证据（`memory:` 来源）写入 `evidence_chain`，不能替代结构化规则。

### 出处页号书写规则（硬性，页锚溯源）

底稿里页锚有两种坐标系，**出处必须照抄底稿里实际出现的那一种，不得互换、不得臆造**：

- `【第 N 页】`（原件直读/扫描）→ 出处写 `文件名 第N页`。
- `【转换稿第 M 页】`（文件头标 `已转换为PDF识别, 页号为转换稿页号`；Office 文件转 PDF 后识别，
  **原文档页号不可知**）→ 出处写 `文件名 转换稿第M页`，并给该条 `evidence_chain` 加
  `"page_kind": "converted"`。**严禁**写成 `第M页` 冒充原文档页。
- **该文件在底稿里没有页锚**（word/excel 整份直读）→ 出处只写文件名 + 章节/标题，**不要编页号**。
- 文件头带 `[⚠页号存疑…]` 的文件：页号仅供参考，结论里该页号会被标 `page_unverified`。

## 复核与辅助域

- 【暂时关闭复核】一律只做一次性审核，**不调度 `expense-reviewer`**；即使命中高风险、证据冲突或 `manual_review`，也只在结论中如实标注，交人工另行处理，不在本流程内发起第二轮 SDK 复核。

## 输出契约

最终审核结论必须直接符合 `.claude/contracts/common/audit-result.schema.json`（该 schema 是形的唯一权威；措辞规范 / `manual_review_reason` 枚举 / JSON 输出纪律等细节以第一步取到的 `AUDIT_INSTRUCTIONS` 原文为准，此处不重复）。只返回一个 JSON 对象，不要输出 Markdown、表格、解释性前言、分节标题或任何 JSON 之外的文字；不要手工再包装一层新的 envelope，也不要手工写入重复的 `logs/results/by-request/...` 文件。

参数: $ARGUMENTS
用法: /audit data/case1
目录示例: /audit data/case1
