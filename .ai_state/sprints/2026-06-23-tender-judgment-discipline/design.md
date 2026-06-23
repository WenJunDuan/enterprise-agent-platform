# 设计 · 评标判分纪律强化（张謇验收残留 41 项）

> Sprint: 2026-06-23-tender-judgment-discipline　Path: System　Stage: design→impl
> 来源：张謇 3 模型真标验收后 `tender-residual-discovery` workflow（5 路 finder）产出 **41 条残留项**，
> 全量见 `logs/tmp/wzqwqntpo.output`（workflow 结果）。

## 背景

混合 PDF 子集 OCR 修复已闭环（60 扫描页补回、证书依赖项出真分）。但 3 模型 e2e 暴露 41 条
**判分纪律 / 校验闸 / 鲁棒性 / 契约 / 前端** 残留。核心症状：① 大量 manual（技术参数等本可判却 punt）；
② deepseek 对读不清的信用截图误判 rejected（自相矛盾）；③ 大底稿致文本模式 JSON 偶发不出（重试）；
④ evidence_chain 空、policy_refs 缺、schema 越界字段、reviewed_by 错标 expense-auditor 等。

## 用户两项决策（本设计的总纲，优先于一切保守默认）

1. **决断优先、压低 manual**：`manual_review` **只留给客观算不出**的项（单家价格横比 / 外部信用未配 /
   现场答辩）。文档判得了的（技术参数偏离表、证书已 OCR）一律出分 / 给 verdict，**子项级**降级而非整项 punt。
2. **证据读不清 → 先重识别该页再判**（不猜、不误废标）：判罚相关页读不清时，先用 `ocr-page` skill
   重识别该页（含印章/截图），读清后再决断；**重识别后仍不可读 → 落入"客观算不出" → manual**。

## 41 项聚类 → 8 簇（详见 workflow 结果）

| 簇 | 涉及 finding | 症结 | 修法面 |
|---|---|---|---|
| **C1 废标/决断纪律** P0 | F01·F2·F4·GATE-01·GATE-02·MODEL-01 | 废标闸对"疑似/未确认/读不清"命中也强制 rejected；rejected 不要求 confirmed + 废标类 policy_ref | gate + prompt |
| **C2 子项级判分·收窄 manual** P1 | F02·F1(prompt)·MODEL-02·GATE-03·GATE-06·F6 | 技术参数"无偏离"=0 正偏离应判 0 分(scored)；性能参数有检测报告应 scored；整项 unresolved→null 粒度过粗 | prompt + gate |
| **C3 引证/证据纪律** P1 | F03·F04·F3(prompt)·F09·GATE-04·GATE-05·EVIDENCE-01·EVIDENCE-02·F06 | policy_refs 空/虚引；evidence_chain 空 conclusion/finding；reasons 空；manual 也须引 ref | prompt + gate |
| **C4 JSON 抽取鲁棒性** P0 | F1(other)·F2(other)·GATE-07·F5(prompt)·INFRA-03·F3(config) | **`_extract_json_object` 遇 trailing `</think>` 返 None / text_accum 被 `</think>` 覆盖 → 抽取静默失败 → 重试**；MAX_OUTPUT_TOKENS 无兜底 | server/common bridge + config（确定性 Bugfix）|
| **C5 schema/契约对齐** P2 | F07·F10·F4(reviewed_by)·F7·F11 | result/conclusion 越界字段、evidence_chain.resolution 越界；reviewed_by=expense-auditor 错；manual_review_reason 缺 tender 枚举；policy_refs_detail 未入约；score_mode 缺失 | schema + prompt |
| **C6 可审计** P2 | F08·F05·F12 | risk_score 无 risk_dimensions 不可复现；explanation 口头总分 64≠结构化 43；主观档次无统一策略 | prompt |
| **C7 前端防御**（#4 报告 500 潜根因）P2 | FE-01·FE-02·FE-03 | report-view getItemBadge/DetailSection、analysis-workbench 缺 null guard → 'undefined / N 分'、越界 | agent-front（codex）|
| **C8 配置/部署** P1/P2 | INFRA-01·INFRA-02·F5(config) | TENDER_TIMEOUT_SEC=OCR_VL_CLOUD_MAX_WAIT=1200（OCR 可耗尽评标预算）；cache v2 首跑重 OCR 部署提示 | .env/.env.example + 文档 |

## 实施轮次（本会话核心 = R1–R5 + R8；R6 配置随手；R7 交 codex）

- **R1 JSON 抽取鲁棒性（确定性 Bugfix，TDD，最高 ROI——直接消除重试）**：修 `_extract_json_object`
  对 trailing `</think>`/思考闭合 token 的处理；`CLAUDE_CODE_MAX_OUTPUT_TOKENS` setdefault 兜底。
- **R2 校验闸强化（gate，TDD）**：① rejected 只允许在 disqualification_hit `confirmed:true` 且引
  废标类 policy_ref 时（否则降级 manual/data_conflict，落 C1+用户决策1）；② score=null↔status=manual
  双向一致（GATE-03）；③ requires_* tag→status 必 manual（GATE-06）；④ evidence_chain 项 finding/
  conclusion 非空校验（GATE-04）；⑤ 任何 verdict 必引 ≥1 通则层 policy_ref（GATE-05/EVIDENCE-02）。
- **R3 评判纪律 prompt（tender-eval SKILL.md / 命令）**：落用户两决策 + C2/C3/C6 —— 子项级降级
  （无偏离=0 分 scored、性能参数有检测报告=scored、整项只在缺招标偏离表时 manual）；manual 只留客观
  算不出；读不清→#8a 重识别再判（接 R4）；policy_refs/evidence_chain/reasons 必填非空；rejected 须
  confirmed；去 result/conclusion、reviewed_by 正确、score_mode 必填、虚引清除、explanation 总分=结构
  化和、risk_dimensions 必填、主观档次统一策略。
- **R4 #8a ocr-page wiring（安全敏感，落用户决策2）**：把 `.claude/skills/ocr-page` 接进 tender-eval，
  `can_use_tool` 回调限死 Bash 只能跑 `ocr.py`（评标处理含可注入投标 PDF + bypassPermissions，裸 Bash=RCE），
  对抗性验证。判罚相关页读不清 → agent 调 ocr-page 重识别再判。
- **R5 schema/契约对齐（TDD）**：audit-result.schema.json 加 `policy_refs_detail`、`manual_review_reason`
  补 tender 枚举（如 cross_bid_required/subjective_review/credit_unverifiable）；evidence_chain 允许
  `resolution`；prompt 去 result/conclusion（verdict 已覆盖）。
- **R6 配置/部署**：INFRA-01（TENDER_TIMEOUT_SEC 1200→2400 或令 OCR_VL_CLOUD_MAX_WAIT≤0.5×TENDER）；
  enterprise-agent.env.example 补 cache v2 首跑重 OCR 提示（INFRA-02）。
- **R7 前端防御（交 codex 并行）**：FE-01/02/03 null guard（顺带闭合 #4 报告 500）。
- **R8 runtime-verify**：重跑 3 模型 e2e（TENDER_READ_DOC_LAYER=0 新鲜 OCR）确认——技术参数出分(子项级)、
  manual 只剩单家价格、无矛盾 rejected、evidence_chain 非空、引证齐、零重试。用户随后重新部署手测。

## 影响范围
`server/common/{json_bridge 或 run_command_json 实现, contract.py, output_contracts.py}`、
`.claude/{skills/tender-eval 或 commands/tender-evaluate.md, contracts/common/audit-result.schema.json}`、
`.env / enterprise-agent.env.example`、`agent-front/.../tender-review/*`（codex）、`tests/`。

## 风险与缓解
- **prompt 改动是模型行为、非确定性** → R8 必须 e2e 重跑 3 模型验证（不能只单测）。
- **#8a wiring 安全** → can_use_tool 白名单 + 对抗性注入测试，未过则不接（保留 skill 手动用）。
- **gate 收紧可能误杀合法输出** → 每条 gate 加 env 门控 + TDD 正反例；承重闸不放松但新规可灰度。
- **schema 删 result/conclusion** → 确认无下游消费（前端读 verdict）再删；policy_refs_detail 入约向后兼容。

## 验收
R8 三模型重评：① 技术参数 scored（子项级，至少性能参数 21）；② 整单 manual 仅因单家价格；③ 无自相矛盾
rejected（读不清→重识别→仍不可读才 manual）；④ evidence_chain 非空、policy_refs 齐、reviewed_by 正确；
⑤ 零文本模式重试。`uv run pytest -q` + ruff + format 全绿。用户重新部署手动测试通过。
