# Review Pass 1 — 2026-08-12-prompt-architecture

- 日期: 2026-08-13
- 范围: `76fa148..HEAD`（7 commits, 28 files）, worktree `agent-adb233b1dd1ec8a09`
- 来源: reviewer + spec-compliance 并行独立审查, 主 agent 合并

## Reviewer Findings

### F1 [P1] KD1 的 green_command 实测退出码 1, 与 "green" 矛盾
- `tdd-evidence.yaml:20` / `evidence/section_budget.py:16`
- 复跑 `containment_check.py && section_budget.py` → EXIT=1: 「执行方式+S0」746B > design 上界 700B（OVER 46）。
- D1 实质理由成立（design 预算表未给自己强制的 fail-visible 行留预算, 该行已压至 208B 为保语义下限; 合计 12,442≤13,700、整文件 ≤15,000 均达标）, 但 evidence 层留下一条"跑起来是红的 green_command", delivery-gate 复跑会命中。
- 建议: section_budget.py 该行 cap 改 750/760 并旁注 D1 出处, 同步修正 tdd-evidence 口径; 或在 tdd-evidence 显式记「section_budget EXIT=1, 唯一超界项=D1」。

### F2 [P1] 无运行时证据, 而风险面恰在运行时
- `_index.md` `skip_runtime_verify: false`; sprint 目录无 runtime 产物。
- 本 sprint 行为面 = 模型是否真按 6 条 Read 拉齐细则并仍产出合法 JSON; 现有证据全为静态文本检查。AC7 defer 的是 eval 收益基线, 不等于 defer runtime-verify。
- 建议: 跑一次真实 `/tender-evaluate` 冒烟（确认 6 个 Read 执行 + 输出过 `validate_tender_result`）, 或在 _index/tdd-evidence 显式记「runtime-verify 待部署机窗口」并写清待验项。

### F3 [P2] pending_reason 逐值语义在 s3 内重复两份
- `s3-scoring-modes.md:10`（界前 L76 逐字搬运）与 `:12-23`（新增速查表）各含一份六值语义, 实况 3 处复本, 与 tdd-evidence "收敛到 2 处"表述不符。
- 建议: 删 L10 逐值罗列（留硬闸句 + 指向速查表/schema）, 该行按 AC2 预留白名单类别「枚举语义迁 schema」入 containment WHITELIST; 同步修正 tdd-evidence 口径。

### F4 [P2] 惰性加载放在早退检查之前
- `server/tender/output.py:433-436`: schema 读取在 extracted/scoring 类型早退之前, expense 路径首次校验也触发文件读。行为无可观察变化, 但作用面大于必要。建议下移 3 行至确认 scoring 为 list 之后。

### F5 [P2] 预算门禁两处机械脆弱点
- `tests/test_prompt_budget.py:57`: references glob 只覆盖一层, 子 skill 的 references 漏检 → 改 `skills/**/references/*.md`。
- `:77`: `_known_entities` 只扫 md 前 6 行找 `name:`, frontmatter 稍长即误判（保守方向）→ 扫描到第二个 `---`。

### F6 [P2] containment 为单向核对（缓解充分, 记录在案）
- 新增文本收敛为 build_skeleton.py 的 9 个具名块, reviewer 已逐块比对: 页锚简版与权威版一致、目标句/指向句无新规则、fail-visible 行与 design KD1 一致, 未发现语义偏移。

### F7 [INFO] 强制 Read +5 轮 vs `AUDIT_MAX_TURNS` 默认 30（`agent_bridge.py:297`）
- 重案卷轮次余量收窄, 建议 F2 冒烟时顺带记录实际 turn 数。

### Reviewer 已核实无 finding 项（摘）
output.py 无模块加载期读、路径走 resolve_output_schema_path、schema 缺失/损坏 fail-fast 无静默降级、716≤720、旧公有名 PENDING_REASONS 无外部消费者; tamper 三向直调 loader; 骨架 6 条 Read 路径全存在、每文件恰读一次、fail-visible 在骨架 L18; Read 在生产路径可达（agent_bridge 工具面 + settings allow）; worker.py 零改动; _index.md 未进提交; schema 未改 oneOf/const; security 清单无命中; 反过度工程双向无命中。

## Spec-Compliance 结论

- AC1-AC6 全 PASS, AC7 合规 defer; MISSING=0; EXTRA=3 全部合理, scope creep=0。
- AC2 强复核: containment 123/0/0 可复现且脚本无放水（归一化不过宽; 严格逐行相等仅 1 行差异且可解释; 行粒度=段落级, 中位 286B）; 另加反向 containment（新增仅 57 行, 无夹带判分规则）与附录 A 全部 47 行组去向逐一验证（不符=0）。未发现任何语义丢失。
- 三轮判分纪律逐条 grep 命中（报价拆层 s3 L37-38 / 主观直接给分 s1 L19-20+s3 L28 / 一致性二分 s4 L15 / 留余地限定 骨架 L67）。
- AC3 注记: 两个 schema 在本 diff 零改动, description 为既有状态满足（audit-result=H1 6c766a5 已交付; criteria 在 base 已存在, design 漏声明）——AC3 该子项非本 sprint 产出, evaluator 知悉。
- AC4: 上界表与 design 逐值一致; CLAUDE.md 上界 9,600 比 8,412×1.15 更紧, 属更严非放水; 红证据三探针各自命中对应断言, 非恒真。
- AC6: NO_NEW_FAILURES diff 为空（33 条基线, 走 design F5 "以自己环境实测清单为准"分支）; ruff 净; bun 189 pass（evidence 记录, spec 未复跑）; tdd-evidence 6 条×10 字段空=0, backfill 记法与 doc-style 模板同构无占位缩写。

### 偏离裁断（6 报告项 → 实质偏离 0）
- D1: design 内部矛盾（预算表漏算自己强制的 fail-visible 行）, 非缩水; 建议按"修正 design 预算表 700→≥746"结案, 不删语义。
- D2/D3/D6: design 明文许可分支。
- D4: design L219 "system-rule-init/system-memory-distill 即悬空名"断言被盘点证伪（实为 `.claude/skills/system/{rule-init,memory-distill}/SKILL.md` 的 frontmatter name, 被多方消费）; 按字面删目录会误伤 7 个生产 skill。generator 拒绝盲从正确且必要。
- D5: 仅 fixture 读取范围扩为「骨架+s3」两文件, 11 条断言/用例/常量逐字未动; design 影响范围明文许可, AC3 字面"零修改"与之矛盾属 design 表述瑕疵。

### design 侧待修正（非阻塞, 留给收尾）
1. KD1 预算表「执行方式+S0」700B → ≥746B（补 fail-visible 行的账）。
2. design L219 悬空名断言更正, 防后人按错误前提删目录。
3. AC3 "11 条零修改"与影响范围"许可 fixture 调整"统一表述。

## 主 agent 合并意见

无 P0。P1×2（F1 evidence 一致性、F2 runtime 证据缺位）均为**证据/流程层**问题, 不涉及交付代码与文本的语义正确性; P2×4 为质量改进项。spec 侧零缺口零缩水。交 evaluator 判定。

## VERDICT (evaluator)

**CONCERNS** — 修复后可 ship, 不构成 REWORK（交付语义面零缺口: AC2 强复核零丢失、偏离实质缩水=0）。

- Evidence Cross-Check: done_without_evidence=0、over-engineering=0; KD1 证据在但 green_command 复跑 EXIT=1（如实披露, 非假过）; runtime-verify 既未执行也未显式 defer。
- 触发 CONCERNS 的两条: F1（Sisyphus「验收过测试」不满足, delivery-gate 复跑必命中; 根因是 design 预算表契约内部矛盾, 须回 design 修订后重核, 不得现场改判据）、F2（Refactor 路径 runtime-verify 未闭合）。
- 最小解锁清单:
  1. F1+design 三处修正一个 commit: 预算表 700→750（补 fail-visible 行的账）、L219 悬空名断言更正、AC3 表述统一; `evidence/section_budget.py` cap 同步 750 并旁注出处; tdd-evidence KD1 口径改 8/8 达标。验收: containment_check && section_budget 双 EXIT=0 无 OVER 行。
  2. F2 二选一: (a) 部署机真实 `/tender-evaluate` 冒烟（核 6 Read 执行 + validate_tender_result + turn 数, 收 F7）落 `evidence/runtime-smoke.md`; (b) 窗口不可达则显式记 `runtime_verify: deferred` + 待验项清单（6 Read 可达 / JSON 合法 / turn 余量 vs AUDIT_MAX_TURNS=30）, tdd-evidence 同步一致。
  3. F3 随 F1 顺手: 删 s3 L10 逐值罗列, containment WHITELIST 落 AC2 预留类别, 复跑仍 123 行全命中; 或如实改 tdd-evidence 表述记 polish。
  4. F4/F5 推迟 polish; F6/F7 已记录无动作。
  5. pass2 增量重核: reviewer 核 F1/F2/F3 关闭证据 + design diff 三处, spec-compliance 仅复核 AC1, evaluator 重判; pass2 头部记明增量理由。
- Sisyphus: 任务全完成 ✓ / 验收过测试 ✗(F1) / 准备进 polish ✗(F2)。
