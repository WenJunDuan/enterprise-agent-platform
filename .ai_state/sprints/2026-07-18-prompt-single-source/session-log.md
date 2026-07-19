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

## 续: E2 拍板→D3+D10 全流程收口(同会话后半)

10. **E2 用户拍方向 b**(Python 单源+D10 直连立项)→ design 定稿 → critic round1 NEEDS_REVISION
    (2P0+3P1+2P2)全应答并入 design → 主 agent 判 ready 进 impl。
11. **impl**(generator+worktree, T1-T5): audit.md 薄壳(判断纪律单源+首步强制 Read runner.py)/
    直连 server/audit/direct.py(AUDIT_DIRECT_CONNECT 门控默认关, trust_env=False, 归档接缝, 回落
    分流)/耗时指标落 AgentRunMeta/vision POC/runbook。
12. **review 三件套**: reviewer 无 P0(3 P1+1 P2)+ spec PASS + evaluator PASS。
13. **F1-F4 修复**(原 generator 会话中断被停, 主 agent 在 worktree 收尾, 有 D1 先例): 凭据分传
    (api_key/auth_token 按存在性分传, 不折叠)/传输类分类收窄(仅 401/429/5xx 回落, 4xx 原样传播)/
    opts 转发 fail-fast/超时注释。→ merge **13ec8b1**(893 绿)。
14. **真网关四项验收全过**(acceptance.md): flag off 893 绿 / on-off 对照直连 16.7s vs CLI 52.8s
    (×32%<70%)verdict 一致 / CC 路径 /audit 一致 / **T4 vision POC=deepseek-v4-flash 不支持
    vision→D10② 附件预嵌降 backlog**。
15. **Bash 安全 Hotfix 53e4bce**(critic 发现+主 agent SDK 源码坐实): 生产 agent 子进程 tools=None→
    CLI 默认含 Bash+bypassPermissions 全放行=评标处理攻击者可控投标 PDF 的 RCE 面; 显式设 tools
    白名单 6 项(排除 Bash/Edit), 895 绿 + CLI 审核实跑限定后正常。铁律[Hotfix 免审议]。
16. **push origin 304b624**(切 ship 窗口推、推毕回 plan); worktree/分支/stash 全清仅 main。

## 本 sprint 交付总账

- **D3(prompt 单源)= DONE**: audit.md 薄壳, 判断纪律单源化, .claude expense 资产标注非生产真相源。
- **D10①③④ = DONE**: 直连路径(flag 门控默认关)/耗时指标/runbook; **D10② vision 降 backlog**
  (网关模型不支持, 待部署机换 vision 模型) → items.yaml D10 status=in_progress。
- 附带: prompt-闸矛盾修复 ship(60d860c)、Bash 安全 Hotfix(53e4bce)、D11 先行设计+critic 应答
  (5f96a0f, 待立项)。

## 悬决(下一会话入口)

- **D11 立项**: design 定稿级+critic 九条应答已在册(sprints/2026-07-18-tender-discipline-residuals/
  design.md); 批次 A opus 安全轮(R4 ocr-page wiring, PreToolUse hooks 白名单)/批次 B codex 确定性
  (F04 evidence_chain 派生/R5 schema/R6 config)/C 条件项(glm 需网关可达/R7 前端需授权)。
- **E4 dependabot**(6 high)可并行。
- proposals.md 两条 delivery-gate 9.9.3 ship 契约结构性矛盾待用户裁。
- 部署机窗口: D8 runbook 四指标 / V4Pro 基线锁一致性硬门(=D4 前置)/ D10② vision 模型。
