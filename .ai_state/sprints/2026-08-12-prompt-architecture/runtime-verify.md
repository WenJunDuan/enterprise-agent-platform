# runtime-verify — 2026-08-12-prompt-architecture

STATUS: DEFERRED

- 本档为 gate 标准位置档，实体记录见 `evidence/runtime-verify-defer.md`（内容为准，两处口径一致）。
- 授权链：review pass1 F2 [P1] → evaluator 最小解锁清单第 2 条 (b) 分支（`reviews/pass1.md`）→
  pass2 reviewer 核验"defer 记录完整、四待验项可执行" → evaluator pass2 `VERDICT: PASS`
  认定"显式 deferred + 待验项清单，满足'要么全完成要么标注并说明'，非静默假过"。
- defer 原因：运行时验证需能实际调起模型跑整单评标的环境（部署机窗口），本机/worktree 仅有
  静态检查与单测环境。与上一 program（tender-eval-hardening）遗留 runtime-verify 四项**同窗**执行。

## 待验项（4 条，窗口打开后逐条跑，产物落 `evidence/runtime-smoke.md`）

1. 6 条 Read 在真实 `/tender-evaluate` 会话全部执行且文件可达（每文件恰一次、无失败）。
2. 最终 JSON 过 `validate_tender_result`（verdict 三值 / score:null 必带 pending_reason /
   policy_refs 非空），无契约重试或重试后成功。
3. 实际 turn 数 vs `AUDIT_MAX_TURNS=30`（`agent_bridge.py:297`）余量评估（收 pass1-F7）。
4. fail-visible：临时撤走一个 reference 后须降 `manual_review(rule_gap)` 并在 explanation
   声明细则缺失，而非静默按记忆续判；跑完还原。

## 静态侧已闭合（不替代运行时证据）

6 条 Read 目标文件存在且工具面可达（frontmatter allowed-tools 含 Read）；5 references 各 ≤10,240B；
`validate_tender_result` 相关闸单测全绿且本 sprint 校验行为零变化（11 回归 + 3 tamper）。

## 回链

- `_index.md` `skip_runtime_verify` 注释已记 deferred（2026-08-13 ship 同步，commit 54ebe59）。
- `tdd-evidence.yaml` 顶层 `runtime_verify` 块与本档一致。
