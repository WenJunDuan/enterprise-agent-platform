# .claude 域驱动上下文装配 — Design

> Sprint 2026-06-21 · Path: System/Refactor · brainstorm 后用户选「域驱动自动装配」方向。

## 背景（问题）

`.claude/` 现状盘点（量化）：
- **skills/commands/agents/contracts 已域分离 + 按需加载**——每个 `SKILL.md` 的 `description: Use when…`
  就是按需触发器（已分 common / expense-audit / multi-ocr / system / tender-eval）。**不是问题源。**
- **真正的上下文挤占在两处**：
  1. **CLAUDE.md**（77 行）把 expense/tender/system 的操作细节常驻进来——它是"业务调度中枢"，是
     CLI/编排路由 agent 的系统提示。
  2. **tender 内联流未瘦身**：`/tender-evaluate` 走 `setting_sources=["project"]` → **载入全本 CLAUDE.md**
     （含无关的 expense/system 细节）+ 命令自身 74 行。**跑 tender 时背着报销/系统域全文**。
- **audit 已经是目标形态**：`AUDIT_LEAN_CONTEXT=true`（默认）→ `setting_sources=[]`（**不载 CLAUDE.md**）
  + 服务端自带 prompt（`runner.AUDIT_INSTRUCTIONS` + 材料 + 规则）。这就是"域驱动装配"的雏形，只是：
  ① 只 audit 做了；② 指令写死在 Python（`runner.py`），不在 .claude 提示层；③ 没抽象成可复用装配器。

**两条执行路径必须分清**：
- **内联执行路径**（生产；server worker 直接调域流程，audit/tender/ocr）→ 应**全部 lean + 服务端域装配**，不载 CLAUDE.md。
- **CLI/编排路由路径**（人对项目总入口说话）→ CLAUDE.md 路由，应**瘦成最小路由器**。

## 方案：域驱动确定性上下文装配

核心：每个业务域注册一个 **DomainProfile**，服务端按域**确定性装配** lean prompt；CLAUDE.md 退化成最小路由。

### 1. DomainProfile 注册表（server 侧，`server/common/domain_profile.py`）
```python
DomainProfile(
    domain="expense",
    instructions=".claude/domains/expense/instructions.md",  # 提示层,prompt 工程师可改
    rules_dir="knowledge/expense",
    result_contract="common/audit-result.schema.json",
    skills=["expense-audit", "common-*"],                    # 文档性,实际仍按需触发
)
```
- 域指令从 **`.claude/domains/{domain}/instructions.md`** 读（提示归位提示层，不再写死 Python）。
- audit 现有 `AUDIT_INSTRUCTIONS`(runner.py) → 迁到 `.claude/domains/expense/instructions.md`。
- tender 现有 `/tender-evaluate.md` 五步 → 迁到 `.claude/domains/tender/instructions.md`。

### 2. 通用装配器
`assemble_domain_prompt(profile, case_dir, *, ocr_block=None) -> str`：
指令 + 材料(case) + 规则(rules_dir) +（OCR 底稿）→ 一个自洽 lean prompt。
- 泛化 audit 的 `build_inline_audit_prompt`（它现在是 expense 专版）。
- 所有内联 worker（audit_worker / tender_worker）改用它，统一 `setting_sources=[]`。

### 3. tender 对齐 audit（lean）
tender_worker 不再走 `/tender-evaluate` + `["project"]`；改为 `assemble_domain_prompt(tender_profile, dir, ocr_block=…)`
+ lean → 自动隔离跨域细节。OCR sprint 刚做的 `ocr_preprocess_block` 底稿作为装配器的一个输入。

### 4. CLAUDE.md → 最小路由器
只留：域表 + 路由原则 + 每域一行入口指针（"expense → /audit 或 expense-audit skill"）。操作细节全在
`.claude/domains/{domain}/instructions.md`（装配器读）。共享护栏（保守原则/多域协同）压到 ≤5 行或下沉 common skill。

## 影响范围
- **新增**：`server/common/domain_profile.py`（注册表 + 装配器）、`.claude/domains/{expense,tender,…}/instructions.md`。
- **改**：`server/audit/runner.py`（指令外移 + 用装配器）、`server/routes/tender_worker.py`（lean + 装配器）、
  `.claude/CLAUDE.md`（瘦身）、`.claude/commands/tender-evaluate.md`（细节外移或废弃）。
- **不破坏**：skills/contracts/agents 的按需加载机制不变。

## 风险与缓解
- **生产 agent 行为变化（最大风险）**：每个域改完必须**真实端到端回归**（audit/tender 跑通、结论不退化）。分域分阶段、各自验证。
- 指令从 Python/command 外移到 `.claude/domains/` → 加载路径变了；装配器须稳定读到（路径校验 + 缺失降级 manual_review）。
- CLI 路由路径仍依赖 CLAUDE.md → 瘦身别瘦掉路由能力（保留域识别 + 入口指针）。
- tender 改 lean 丢了 `["project"]` 带的长超时/降噪 → 比照 audit 放进 env（`agent_bridge` 已有此兜底模式）。

## 验收标准
- tender 评标时 prompt **不含** expense/system 细节（可验：关键词缺席）。
- audit/tender 都经统一 `assemble_domain_prompt` + lean；域指令都在 `.claude/domains/`。
- CLAUDE.md ≤ ~30 行纯路由；**新增域只需加一个 DomainProfile + 一个 instructions.md，不改 CLAUDE.md 主体**。
- 真实 audit + tender 端到端回归通过，结论不退化（与重构前同输入同结论）。

## 落地顺序
- **P1** 抽 `assemble_domain_prompt` + DomainProfile（先**原样包住 audit 现状，零行为变化**，纯重构 + 单测）。
- **P2** audit 指令外移到 `.claude/domains/expense/instructions.md`（装配器读），回归 audit。
- **P3** tender 改 lean + 用装配器 + 指令外移到 `.claude/domains/tender/instructions.md`，回归 tender（**关掉跨域挤占**）。
- **P4** CLAUDE.md 瘦成路由器；共享护栏处理。
- **P5** ocr/system 域纳入同模式（如适用）。

## 关联
- 模式来源：`server/audit/runner.py` + `AUDIT_LEAN_CONTEXT`（audit 已 lean）。
- 上游刚落地：OCR sprint P4 的 `ocr_preprocess_block` 注入 = 装配器的一个输入（ocr_block）。
- doc-style/coding-standards：指令外移须保留出处可追溯；装配器纯函数易测。

## 评审修订（critic R1：APPROVE-WITH-CHANGES）

- **F1 [P0] tender lean 的落点必须明确**：`tender_worker` **放弃 `run_command_json`**，改为直接
  `run_agent_json(assemble_domain_prompt(tender_profile, dir, ocr_block=…), setting_sources=[], …)`。
  理由：命令路径(`run_command_json`)走 `build_options` 默认 `setting_sources=["project"]` → 注入 CLAUDE.md，
  与 lean 目的冲突；只在调用处加参数易遗漏。完全类比 audit runner，不复用 command_adapter。
- **F3 [P1] `/tender-evaluate.md` 处置（拍板）**：server inline 为主路径；`tender-evaluate.md` **标 deprecated 保留**
  作 CLI fallback（接受旧行为），不强行删（CLI 用户偶发直调仍可用）。指令权威源 = `.claude/domains/tender/instructions.md`；
  deprecated 命令头部加一行指回它，避免两份同步负担（命令仅留薄壳）。
- **F4 [P1] system 域显式排除本 sprint**：`system-rule-init`/`memory-distill` 走 skill（非内联 worker），
  **不纳入 DomainProfile**；多域协同 OCR→expense 已由 `ocr_block` 覆盖。ocr/system 纳入留 backlog。
- **F2 [P1] P2 验证用字节级比对**：指令外移后 `assert assemble_domain_prompt(case) == 旧 build_inline_audit_prompt(case)`
  字节一致（防换行/BOM 偏移——历史"audit schema 闸误杀"即模型对开头字节敏感），再回归 audit 端到端。
- **F5 [P2] 值级回归（落 classify 教训）**：P3 用**已验证真实 case**（示例云平台 tender / 张三 audit），重构前后
  `verdict`/`claim_id`/`scoring[*].score` **值级一致**，不止"端到端通过"（改装配器=改分流，防首次激活下游死分支）。
- **F6 [P2] DomainProfile.skills 字段**：文档性、默认 `[]`、当前**无运行时效果**（注释标明，防误用）；或 P1 先不加，待真实消费者。
- **优先级校正**：CLAUDE.md 瘦身（P4）是**最低优先级工程卫生**（非性能/上下文挤占——生产全走 inline worker，
  CLAUDE.md 只在 CC 对话时生效；真实价值=降低误路由）。**核心是 P1-P3（tender lean）**，P4 收尾即可。
