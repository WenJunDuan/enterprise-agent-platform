# Session Log · 2026-07-18 (D3/D10 spike + prompt-闸修复会话)

> 单会话完成: 分诊 → D3 三模式 spike → 产品缺陷发现与修复(opus4.8) → 真网关验收 →
> 执行序重排 → E1 D10 直连 spike → E2 拍板包。全部证据在本目录 spike/*.jsonl。

## 时间线

1. **分诊**(route-note.md): 本机可动项唯 D3 spike; D4/D5/D9/D10 被部署机基线或依赖卡。
2. **D3 spike**(spike/results.jsonl, 13 attempts): A 内联 56.1s / B1 command 58.9s / B2 command+context
   55.5s → 延迟不卡方向; 意外主发现=A 契约失败 4/6(漏 explanation) vs B 侧 1/7 → 两源漂移已兑换成
   生产可靠性差; B1 verdict 漂移 1/3 淘汰。
3. **产品缺陷①坐实**: AUDIT_INSTRUCTIONS「数据真实性拒绝允许空 policy_refs」vs 承重闸 rejected 须
   ≥1 ref → flash(literal 模型)下必挂, D1 audit golden 假红。学习档
   compound/2026-07-18-learning-prompt-gate-contradiction-literal-model.md。
4. **修复 ship**(用户拍方向 c): opus4.8 generator + worktree, fix `07f1dc8` merge `60d860c`;
   prompt 从严闸零动; 主 agent 独立验 861 绿+ruff 净; worktree/分支即清。
5. **真网关验收 6/6 全过全首试成功**(spike/verify-results.jsonl): placeholder 3/3 rejected 引
   expense_travel_026(修复前 0% 成功), taxi 3/3 引 expense_travel_005; explanation 缺失归零。
6. **执行序重排**(roadmap.md「执行序重排」节 + items.yaml execution_order): E1 D10①直连 spike 前置,
   D11 升窗口并行, D4 保持部署机前置卡位。
7. **delivery-gate 核查**: 9.9.3 ship 契约对中程 roadmap+子范围 Bugfix 结构性不可满足(validateRoadmap
   全 item completed / tdd-evidence 时间戳) → 不造档不绕闸, stage 如实回退 plan, 两条 harness 矛盾落
   proposals.md 待用户裁。
8. **E1 D10①直连 spike**(spike/d10-results.jsonl): anthropic SDK 直打网关, 中位 19.0s vs 当日 CLI
   8 样本 ~31s = 快 40-60%; 6/6 verdict/refs 正确; 网关 prompt cache 红利(重复 input 7059→19-59);
   SOCKS 代理坑增补进 compound/2026-06-25-trick-codex-proxy-hangs-streaming.md。
9. **收口**(用户指令): worktree/分支/stash 复核全清, main 推 origin, 文档完善, design.md 预案备妥。

## 悬决(下一会话入口)

- **E2 拍板(用户)**: a=command 单源 / b=Python 单源+D10 直连立项(主 agent 推荐 b, 论证=route-note
  「E2 拍板包」)。拍板后按 design.md(DRAFT)进 critic → impl。
- proposals.md 两条 delivery-gate 矛盾待裁。
- 窗口并行可起: E3 D11 / E4 dependabot; 部署机窗口: D8 runbook + V4Pro 基线锁硬门。
