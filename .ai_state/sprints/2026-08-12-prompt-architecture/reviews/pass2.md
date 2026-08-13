# Review Pass 2（增量重核）— 2026-08-12-prompt-architecture

- 日期: 2026-08-13
- 性质: **增量重核**（evaluator pass1 明文授权: reviewer 核 F1/F2/F3 关闭证据 + design diff 三处, spec-compliance 仅复核 AC1, 不重开全量三件套; 理由 = 修复均为验收记账/事实更正, 无 scope 变化）
- 复核基准: `7e7feb1..HEAD`（fix commits `beb1ce3` + `e4388c5`, 8 文件 +124/-27）

## Reviewer（增量）

- **F1 CLOSED**: 双脚本复跑 EXIT=0 零 OVER（containment 123/未命中1/白名单1; section_budget 8/8, 合计 12,442≤13,750, 整文件 ≤15,000）。判据放宽面核实: section_budget.py 仅两处数值变更（700→750、TOTAL_CAP 13,700→13,750）, FILE_CAP 与其余 7 节 cap 逐字未动; 新 cap 750 相对实测 746 仅留 4B, 比"原公式+同等余量"更紧, 属据实收紧非放水。tdd-evidence KD1 口径逐项与实测相符（含 s3 10,198→9,796 同步、commits 占位更正为 beb1ce3）。
- **F3 CLOSED**: s3 L10 现为单行硬闸+指向速查表, 三条行为规则对照界前 L76 逐字保留; 逐值语义仅速查表一份（权威=schema）; WHITELIST 恰 1 条（key=76, 类别=AC2 预留「枚举语义迁 schema」）; 脚本自带 STALE_WHITELIST 反向失效检测, 白名单无法沉淀为永久豁免; test_tender_pending_reason 11 条仍全绿。
- **F2 CLOSED（defer 分支）**: evidence/runtime-verify-defer.md 存在, 状态明写 deferred, 四条待验项完整可执行（6 Read 各恰一次/validate_tender_result 无重试/turn 数 vs AUDIT_MAX_TURNS=30 收 F7/撤 reference 须降 manual_review(rule_gap)）; tdd-evidence 顶层 runtime_verify 块与之逐条对应; D6(AC7 eval 基线)与 D7(runtime-verify)互相点名区分; _index 留待主 agent ship 时写。
- **design diff 三处 CLOSED**: 仅 3 个 hunk 全为记账/事实更正——预算表修订块（附漏算原因与出处）、AC5 删被盘点证伪的悬空名断言（义务本体逐字未动, 防后人误删 7 个有消费者的子 skill）、AC3 "11 条零修改"→"11 条断言零修改"并补更严硬约束（断言/用例数/PENDING_REASONS 常量不得动）。scope 变化=0, 新增义务=0, 语义放宽=0。**F4/F5 未被顺带改动**（output.py 与 test_prompt_budget.py 不在变更文件内, 修复无扩散）。
- 回归快查: baseline/after diff 空; 现场 `pytest -k "tender or prompt"` 468 passed/2 failed 且 2 条逐名在 baseline 内（NO_NEW_FAILURES 守恒）; ruff 净; 21 条相关测试全绿; 工作树除 reviews/ 外干净; _index.md 未入任何 commit。

### 新 findings
- **N1 [P2]** design.md:336「Round 2」历史记录仍写"合计 ≤13,700"——历史轮次记录非活判据, 不产生门禁矛盾, 但属 pass1 F1 同类的"design 内两数互斥"残留 → polish 时加一句修订指向, 或记录在案不动。
- **N2 [INFO]** 「执行方式+S0」cap 余量仅 4B, 有意的据实收紧; 后续动该节文案须回 design 预算表走修订流程, 不得就地改 cap。
- **N3 [INFO]** containment 白名单有 STALE_WHITELIST 反向失效检测, F3 白名单路径不构成机制放水, 记录在案。

## Spec-Compliance（仅 AC1 + AC2 联动）

- **AC1 PASS**: 整文件 12,442≤15,000; 骨架自 ceb5e19 起零改动（diff 0 字节, 修复未碰生产骨架; 唯一生产文件改动=s3 单行去重）; 逐节 8/8 无 OVER, 脚本 cap 与 design 修订版预算表逐值一致, 修订表算术自洽（=13,750）; 5 references 全部 ≤10,240B（s3 现 9,796）; 6 条 Read 指令路径逐一存在且每文件恰读一次（L12 为权威指向句非 Read）; test_prompt_budget 7 passed。
- **AC2 联动 PASS**: containment 122 逐字命中+1 白名单、EXIT=0 复现; WHITELIST 唯一条目 key=76、类别合法; 三轮判分纪律 grep 逐条命中（报价拆层 s3:36-38/主观直接给分 s3:29+s1:19-20/一致性二分 s4:15/留余地限定 s3:29+s4:27）, 删复本未误伤。
- MISSING=0 / DEVIATED=0 / scope creep=0; EXTRA 合理 1 项（runtime-verify-defer.md, 属 F2 配套）。
- 建议: PASS（就增量复核范围）。

## 主 agent 合并意见

pass1 触发 CONCERNS 的 F1/F2 均以可复跑证据闭合, F3 顺手收口且被证实无机制放水; 修复零扩散、生产语义面零变化。新增仅 P2×1（历史记录残留）+ INFO×2, 均不阻塞。交 evaluator 重判。

## VERDICT (evaluator, pass2)

**PASS**

- Evidence Cross-Check（增量）: pass1 最小解锁清单 5 条逐一 ✅（F1 双脚本 evaluator 现场复跑 EXIT=0; F2 defer 记录双处一致; F3 白名单唯一且 STALE_WHITELIST 在位; F4/F5 defer 边界未被越过—两文件不在 fix commits 变更面; pass2 增量授权记录在档）。done_without_evidence=0, over-engineering=0。
- CONCERNS 触发条件全部消除; 未解决项仅 F4/F5/N1（P2, 显式 defer 至 polish）+ N2/N3（INFO）。
- N1 裁定不阻塞（历史轮次记录非活判据）, 入 polish 队列。runtime-verify deferred 属 pass1 授权 (b) 分支合规闭合, 非静默假过。
- Sisyphus 三项全勾: 任务全完成 / 验收过测试（双脚本+7 passed+NO_NEW_FAILURES 空 diff）/ 准备进 polish。
- ship 前待办: ① 先 polish（队列 F4/F5/N1; 注意 N2—「执行方式+S0」余量仅 4B, 不得触碰该节文案）② 提交 reviews/ 并合并 worktree ③ ship 时一次性同步 _index（runtime_verify: deferred / next_action / route_history）④ 遗留移交部署机窗口: runtime-verify 4 待验项 + AC7 eval 基线（与 tender-eval-hardening 遗留同窗）; push 用 ATHENA_ALLOW_PUSH=1。
