# Codex 任务书 — Tender Report Dimensions (Sprint 2026-06-25)

你是本仓库（企业智能审核平台：tender 评标 + expense 报销审核）的实施工程师。
本任务已通过设计确认，按下述 spec 实施。**先读 spec，再动手。**

## 必读（按序）

1. `.ai_state/sprints/2026-06-25-tender-report-dimensions/design.md` ← 完整 spec（修订版 v2，权威）
2. `.ai_state/sprints/2026-06-25-tender-report-dimensions/checklist.yaml` ← D0–D5 任务清单
3. `.claude/CLAUDE.md` 的 tender / expense 业务规则段（铁律护栏）

## 实施顺序：D0 → D5（严格按序，TDD：能先写测试就先写）

- **D0（最高优先）**：修复 `server/common/output_contracts.py` 的跨域回归。
  `_finalize_user_explanation` 现对所有审核结论生效，把 expense 合法结论误删/误替换。
  - 复现（修复前会重现，修复后必须消失）：
    ```bash
    uv run python -c "
    from server.common.output_contracts import enrich_audit_decision
    o = enrich_audit_decision({'verdict':'approved',
      'explanation':'发票与审批单一致，金额在预算内。综上，本次差旅报销合计 1200 元，符合制度规定，予以通过。',
      'extracted_data':{'invoice_no':'fp_2026_0420'}})
    print(o['explanation'])  # 修复前：'综上…予以通过' 被整句删除；修复后：必须保留完整结论
    "
    ```
  - 修复方向（见 design.md D0）：把 `_finalize_user_explanation` 及其剥离/小结逻辑**限定到
    tender**（判据：`extracted_data` 含 `scoring` 或 `eligibility_checks`；非 tender 原样返回）；
    把 `_sanitize_explanation_terms` 的 catch-all `\b[a-z]+(?:_[a-z0-9]+)+\b → 相关字段`
    改为**只替换已知内部字段名集合**，去掉通配。
  - 新增 `tests/` 回归用例：expense 结论含「综上…合计…。」不被删改、含下划线标识不被替换；
    tender happy-path 小结仍服务端重算（模型写错的总分被纠正）、tender rejected 仍加废标前缀。

- **D1**：在 `agent-front/src/features/contract/tender-review/model.ts` 实现
  `deriveReviewDimension(scoring, criteria)`，按 design.md「维度派生规则」表（结构化字段优先，
  名称仅旧数据兜底）。**不要**新增 `criteria.schema.json` / `extract-result.schema.json` 字段。
  在 `model.test.ts` 补单测覆盖三类 + 旧数据兜底。

- **D2**：报告明细区按固定顺序渲染五段（资格审查→价格分→商务客观分→技术主观分→综合结论）；
  商务客观分段出"客观分小计"；旧数据无法派生时归 business_objective，不崩。

- **D3**：价格分独立板块。单家：`requires_cross_bid_comparison`/`score:null` 显示"待全部投标报价
  一起计算/待补充"，**不显示 0 分**；多家：引用 compare 侧价格分计算式完整展示。价格分**不混入**
  商务客观分表。

- **D4**：技术主观分两家对比（compare 视图）。对每个 technical_subjective 项，从各投标人各自
  `AuditResult.extracted_data.scoring` 取 `score+basis+页码`并排；"优劣"只陈述分差+事实依据对照，
  **不臆造定性结论**；缺 compare/缺家 → 降级只列各家主观分+依据。主观项统一标
  "初评建议，最终以评标委员会评分为准"。

- **D5**：`.claude/commands/tender-evaluate.md` 的 S4「综合意见口径」可按 资格/价格/商务客观/技术主观
  四类分述 + 主观项标"初评建议"；**不要求模型标 review_dimension**（维度由前端派生）。S0–S3 判分规则不动。

## 硬约束（铁律，违反即返工）

- 招标文件 criteria 是评分规则唯一来源；外部提示词只定报告结构，**不作规则来源**。
- 展示层（Python/前端）**禁止改变任何 score**；不可判定项绝不判 0（保持 manual_review/score:null）。
- **不新增** schema 字段（维度靠派生）。不改 S0–S3 判分逻辑。
- 不提交 `knowledge/` 与 `data/`（已 gitignore）；不碰与本 Sprint 无关的文件。

## 验收门禁（必须全绿，把输出贴进结论）

```bash
uv run pytest -q
uv run ruff check .
cd agent-front && bun test src/features/contract/tender-review/model.test.ts && bun run lint && bun run build
```

## 收尾

- 按 Conventional Commits 分逻辑提交：D0 用 `fix(server): ...`；D1–D4 前端用 `feat(front): ...` /
  `test(front): ...`；D5 用 `docs(tender): ...`。subject ≤50 字符、祈使句。
- 更新 `checklist.yaml` 各项 status=done；如有取舍写进同目录 `session-log.md`。
- 结论里报告：改了哪些文件、D0 复现已消失的证据、三条门禁的实际输出（pass 数）。
