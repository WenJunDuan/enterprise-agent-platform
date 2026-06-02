# A-006 自审：多域协同与二次复核成本治理

## 结论

- VERDICT: PASS

## 本轮目标

- 把 reviewer 的自动触发条件写成明确规则
- 把 HR / Legal 辅助域的触发条件从“泛化声明”收紧成可执行判断
- 让 post-write 二审 hook 不再默认全量执行，改为风险驱动

## 实际改动

- 更新 `.claude/CLAUDE.md`
  - 明确 `expense-reviewer` 自动触发条件：
    - 用户明确要求复核
    - `risk_score >= 70`
    - `manual_review_reason ∈ {data_conflict, pre_approval_mismatch, missing_approval, invoice_invalid}`
    - 证据冲突或无法形成稳定解释
  - 明确 HR 辅助域触发条件：
    - 差旅/交通报销涉及周末、节假日、考勤、请假、调休、加班、出勤冲突
  - 明确 Legal 辅助域触发条件：
    - 合同/协议/付款约定附件
    - 高额付款、采购、合作、供应商结算需合同条款佐证
  - 明确二审 hook 的成本治理规则：
    - `rejected`
    - `risk_score >= 70`
    - 高风险 `manual_review_reason`
- 更新 `.claude/commands/audit.md`
  - 将 reviewer / HR / Legal 的触发规则写到实际审核入口中
- 更新 `.claude/hooks/review-output.py`
  - 新增 `_should_run_second_review()`
  - 现在默认跳过：
    - 低风险 `approved`
    - 普通 `manual_review(insufficient_evidence / rule_gap)`
  - 只对高风险 / 冲突结果进入二审
- 更新 `README.md`
  - 对外说明二审 hook 并非全量执行，而是风险驱动

## 测试

- 新增 `tests/test_orchestration_triggers.py`
  - 锁定多域和 reviewer 触发规则确实写进 Claude 侧入口
- 扩展 `tests/test_review_output_hook.py`
  - 验证低风险 `approved` 跳过二审
  - 验证高风险 `approved`、`rejected`、高风险 `manual_review` 会进入二审
- `uv run pytest` 通过，当前共 67 项
- `uv run ruff check server tests` 通过

## 为什么这版更对

1. 多域协同不再只是“理论上支持”，而是有触发规则了。
2. reviewer 不再默认出现在所有审核路径里，而是由风险和冲突驱动，成本更可控。
3. 二审 hook 从“默认全量”收紧为“有意义才做”，避免不必要的 Claude 开销。

## 风险与遗留

- 这轮落地的是“Claude 侧触发规则 + hook gating”，不是“Python 运行时显式编排多域/复核流程”。这符合当前边界，但也意味着 reviewer/HR/Legal 的真正执行仍由 Claude 在运行时遵循指令完成。
- `review_delta` 的查询和存储层已就绪，但 reviewer 自动产物还没有被主链稳定持续写入；后续如果要做更强的复核运营面，还可以继续增强。

## 下一步建议

- 进入一次新的整体架构 review
- 或者直接进入发布前整理：
  - 统一 API 返回集
  - 发布文档收口
  - 环境/运维清单
