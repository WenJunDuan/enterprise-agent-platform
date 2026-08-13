# runtime-verify · DEFERRED（review pass1 F2 / 最小解锁清单第 2 条 (b) 分支）

- 记录时间：2026-08-13
- 状态：**deferred**（未执行，非"已通过"，也非"不需要"）
- 决策人：generator（按 evaluator 给出的 (a)/(b) 二选一，选 (b)）

## 为什么 defer

本 sprint 的运行时验证需要**能实际调起模型跑一整单评标**的环境（部署机 / 可调模型窗口）。
当前 worktree 只有静态检查与单元测试环境，跑不了真实 `/tender-evaluate` 会话。该窗口与上一
program（tender-eval-hardening）遗留的 runtime-verify 四项**同窗**，宜在同一次部署机窗口内一并跑，
不单独占用一次窗口。

注意区分：AC7 defer 的是 **D1 eval 收益基线（A/B 三数字）**，与本条 runtime-verify 不是同一件事
（review pass1 F2 已指出这一点）。本文件专记 runtime-verify。

## 静态侧已闭合（可减小运行时风险，但不能替代运行时证据）

- 6 条 `Read` 指令的目标文件全部存在且路径正确（骨架 grep 实测 6 条 Read → 6 个文件，每文件恰一次）。
- 命令 frontmatter `allowed-tools` 含 `Read`，工具面可达。
- 5 个新 references 均 ≤10,240B，单档可一次读完。
- 输出契约相关的服务端闸（`validate_tender_result` / `pending_reason` 语义闸）单测全绿，
  且校验行为在本 sprint 内零变化（11 条既有回归 + 3 条新 tamper 用例）。

## 待验项清单（部署机窗口打开后逐条跑，跑完落 `evidence/runtime-smoke.md`）

1. **6 条 Read 在真实会话全部执行且文件可达**：跑一单真实 `/tender-evaluate`，从会话轨迹确认
   `s1-locate-criteria.md` / `s1-criteria-structuring.md` / `evidence-citation.md` /
   `s3-scoring-modes.md` / `s4-verdict-summary.md` / `output-json.md` 各被 Read 恰一次、无失败。
2. **输出仍过 `validate_tender_result`**：该单最终 JSON 通过服务端契约校验（含 `verdict` 三值、
   `score:null` 必带 `pending_reason`、`policy_refs` 非空），无契约重试或重试后成功。
3. **turn 余量（收 F7）**：记录该单实际 turn 数，与 `AUDIT_MAX_TURNS` 默认 30（`agent_bridge.py:297`）
   对比。强制 Read 使轮次 +5 左右，重案卷若逼近 30 需评估是否上调默认值。
4. **fail-visible 行为**：人为撤走一个 reference（如临时改名 `s3-scoring-modes.md`）后再跑一单，
   确认模型按骨架 L18 的语义**降 `manual_review`（`rule_gap`）并在 `explanation` 声明细则文件缺失**，
   而不是静默按记忆续判。跑完把文件改回。

## 关联

- `_index.md` 的 `runtime_verify` 标记由主 agent 在 ship 时统一写（generator 不碰 `_index.md`）。
- tdd-evidence.yaml 中有对应的 `runtime-verify-defer` 记录，两处口径须一致。
