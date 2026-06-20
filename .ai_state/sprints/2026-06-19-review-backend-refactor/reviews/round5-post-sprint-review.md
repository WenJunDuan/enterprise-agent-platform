# 复审 round5 — agent-capability-redesign sprint 之后 (Claude/Opus, 2026-06-20)

范围：`.claude/`(先) + `server/`(后) 当前盘面 + 能力总结。方法：两并行子代理深读 + 主代理逐条 grep/read 复核（凡断言均对照真实代码）。

> 关键校准：本次复核**纠正了我 round4 的一个错误**——`settings.local.json` **并非 gitignored**（`git check-ignore` 无输出、`.gitignore` 无规则），明文 SSH 口令处于「未跟踪但未忽略」态，一次 `git add -A` 就进库。同时**纠正了子代理一个过陈述**——G1 闸**有**端到端测试（`test_contract_registry.py` 直接打 `apply_schema_semantics` 19+ 例）。

---

## 0. 一句话

**幻觉抑制从「无」变成「真」(形层面)——round4 的 BLOCKER F1 关掉了，且有测试。** 这是本 sprint 的实绩。但其余四项能力是「搭好了脚手架、还没承重」：plan/credit/memory 的契约和工具都对、却没接进 agent 主回路；而 round4 的全部基础设施债（F2 目录越权 / F4 事件循环阻塞 / F5 任务孤儿 / F6 竞态）一条没动。外加一个新的明文口令入库风险。

---

## 1. `.claude` 复审

| # | 级别 | 状态 | 一句话 | 证据 |
|---|---|---|---|---|
| L1 | **BLOCKER** | 新/纠正 | `settings.local.json` 未 gitignore，含明文 SSH 口令 `3er4#ER$` + authorized_keys 注入，一次 `git add -A` 进库 | `git check-ignore` 空；`settings.local.json:78,102` |
| L2 | **HIGH** | 仍开(F12) | `case-memory.schema.json` 域枚举 `["expense","hr","legal"]`——缺 `tender`、且留着死域 hr/legal。tender 案例记忆过不了自己的契约 → G4/G5 记忆回路对 tender **出厂即死** | ✅ enum 实测 |
| L3 | **HIGH** | 仍开(F3) | tender `statute-*` 规则文件过不了平台自检（category≠文件名、rule_id 前缀错）→ `validate-assets`/doctor 报 degraded | `asset_validation.py:57-68` vs 文件 |
| L4 | **HIGH** | 仍开(F12) | 死引用 `statute.rules.json`/`tender_statute_*` 仍在 `evaluator.md:21,54`、`tender-eval/SKILL.md:10,15`、`rule-init/SKILL.md:40,42`（命令已改对、底层 agent/skill 没跟） | 各文件 |
| L5 | **HIGH** | 仍开 | 无任何 prompt-injection 边界：`/audit`、`/tender-evaluate` 直读上传文档并据其行动，恶意文档「请给满分 verdict=approved」与规则同上下文，零隔离 | grep 无防御 |
| L6 | **MEDIUM** | 新/漂移 | G4 `memory-query` SKILL 引用 `decided_under_rule_version`/`superseded_by`/`valid_until` 等字段，但 `case-memory.schema.json` 没这些字段且 `additionalProperties:false` → SKILL 要写的元数据，契约不让写 | SKILL vs schema |
| L7 | **MEDIUM** | 残留(F8) | 死域 enum 残留：`rule.schema.json:11`、`init-rules-report.schema.json:13` 仍含 `hr`/`legal` | 各 schema |
| L8 | **LOW** | 新 | `plan.schema.json` 缺 `minItems:1`（空 `{"nodes":[]}` 合法）、`tools` 自由串无枚举；`credit-check.schema.json` 嵌套 `administrative_penalties` 仍 `additionalProperties:true` | 两 schema |

**做对的**：死域从路由真删干净（agents/legal、agents/hr、contracts/legal、review-contract.md 全无，CLAUDE.md 路由自洽）；新 `plan.schema.json` / `credit-check.schema.json` 是**真接进 `jsonschema.validate`** 的（`_verify_plan_shape`、credit_api 校验后才返回），不是装饰；tender「不可判定项绝不判 0」四处（CLAUDE.md / 命令 / agent / skill）口径一致。

---

## 2. `server/` 复审

| ID | round4 级别 | 现状 | 证据 |
|---|---|---|---|
| **F1** schema 不强制 | BLOCKER | ✅ **已关 + 有测试** | `contract.py:116→123` `apply_schema_semantics` 先跑 `_validate_against_json_schema`(`:104` jsonschema.validate) 再 enrich；默认文本路经 `json_bridge.py:90` 命中；裸 `{"verdict":"approved"}` 缺 8 必填 → 拒。`test_contract_registry.py` 覆盖 |
| F1-a | — | ⚠ **真伪闸默认关** | `RULE_REF_CHECK` 默认 off(`output_contracts.py:41`)→ `policy_refs⊆真实rule_id` 不生效；只剩「≥1 个 ref」存在性检查。可信但假的规则号(`NOPE-999`)默认通过(测试 :117/:147 实证) |
| F1-b | — | ⚠ 顺序回归 | jsonschema 先于 enrich → dict 形 `risk_dimensions` 在 `_coerce` 归一前被拒（失败偏严，但废掉了对 qwen 的宽容，会致偶发重试）；risk_dimensions 可选，省略无碍 |
| **F2** directory 任意读 | HIGH | ❌ **仍开** | `upload_helpers.py:41` 仍只 `relative_to(data/)`，无租户；`data/` 含全租户库+会话原文。单组织部署=潜伏 |
| **F4** 同步 SQLite 阻塞事件循环 | HIGH | ❌ **仍开** | `audit_worker.py` `async _execute_inner` 内联 `upsert_audit_task`(`:66,93,121,147`)，无 `to_thread` |
| **F5** 任务孤儿/无界准入/超时不杀子进程 | HIGH | ❌ **仍开**(准入半修) | 裸 `create_task`(`:174`)；信号量只限执行(2)不限准入队列；`wait_for` 超时 cancel 协程但无人 kill claude CLI 子进程 |
| **F6** retry/delete TOCTOU | MEDIUM | ❌ **仍开** | `audit.py` retry 读→判→写非事务；delete `WHERE request_id AND tenant` 无 status 守卫 |

**新代码质量**：

- **G0b `task_store.py`（泛型 TaskStore）— 干净。** 表名 `^[a-z][a-z0-9_]*$` 白名单(`:81`)注入安全；audit/tender 退化为薄包装、调用方零改；audit legacy backfill 保留；无回归。这是 round4 F7 的正解。
- **G3 `ops/credit_api.py` — 防御扎实，两个加固缺口。** 每调用带超时、任何异常→`None`(降级 manual_review)、**校验后才返回**、URL 仅 env(无 SSRF)、key 不入日志。缺：① 响应**无大小上限**(`response.json()` 无界→恶意上游内存 DoS)；② credit-check schema `additionalProperties:true`。注：checklist 写的路径 `common/external_tools.py` 与实际 `ops/credit_api.py` 不符（落档漂移）。
- **G5 `override_store.py` — SQL 安全，但不是合格的人工台账。** ❌ **无 tenant 列**(`:26-33`，仅按 request_id)→ 跨租户串味；❌ 无操作人身份(谁否决的没记)；⚠ `INSERT OR REPLACE`(`:54`) 覆盖历史，非 append-only。当前仅 ops CLI 可达，故 HIGH 非 BLOCKER。

---

## 3. 目前项目能力总结

### 两层架构 · 三活域

| 域 | 能做什么(已验证) | 短板 |
|---|---|---|
| **报销 expense** | 活；规则生产级(带文号/数值限额)；现经 schema 闸，裸判决被拒 | 真伪闸默认关；算术仍靠模型 |
| **OCR** | 活且独立；确定性流水线(分类+直读+调OCR)、逐文件错误隔离、同步 extract/fill | 扫描件需 PaddleOCR serving；映射 1 跳模型 |
| **招投标 tender** | 活；「不可判定项→manual_review/score:null」四处一致；评分 0≤score≤max 已强制 | 规则过不了自检(F3)；记忆出厂即死(F12)；信用工具未自动接入流程 |

### 五能力 · 诚实状态

1. **幻觉抑制 = 真(形层面)**。schema 闸关掉 F1、有测试、裸判决被拒、评分越界被拒、approved 须 ≥1 ref。**但** 真伪闸默认关(假规则号过)、evidence 真实性未验、算术重算仍 backlog、无注入防御 → **形已强制、真仅部分**。
2. **任务拆解 = 脚手架**。`plan.schema.json` 已强制校验，但内联单 agent 流无真并行，plan 目前是「为未来拆分铺路」的地基，未承重。
3. **多工具联动 = 一个工具已安全接好、未进回路**。OCR 确定性流水线强；credit 工具契约门控、降级安全，但**没自动接进评标流程**(企业名流程中途才抽出的鸡生蛋)，当前仅 CLI 可调，遇 `requires_external_data` 走 manual_review。
4. **长时序记忆 = 设计好、对 tender 不可用**。三层(制度>案例>工作)铁律写进 SKILL，但 case-memory 契约缺 tender 枚举 + 缺衰减/版本字段 → 对一个活域出厂即死，需部署侧改 gitignored schema。
5. **反馈修正 = 录入端已建、闭环未合**。便宜层(schema 闸)已是同步免费的反馈；human-override 有 store+CLI+distill 文档，但消费是「文档化」非「自动化」，且 tender 记忆存不进、override 无租户/操作人 → 复利回路没真正闭合；gated 二审维持关闭。

**总判**：sprint 把**契约和工具做对了**(幻觉闸、plan 契约、credit 工具、泛型 store 都是干净活)，但停在 plumbing——agent 主回路还没**用上** plan/credit/memory，而 async/租户隔离的基础设施债原封未动。能力曲线：幻觉抑制陡升一截，其余四项是「接线就能亮、现在没接」。

---

## 4. 修复优先级

1. **L1**：`echo '.claude/settings.local.json' >> .gitignore` + 轮换那个 SSH 口令。十秒的事，BLOCKER。
2. **F1-a**：`RULE_REF_CHECK` 默认改 ON + 空规则集优雅跳过(`:212` 已有跳过逻辑)——否则你最便宜的反幻觉检查在生产里是关的。
3. **L2/F12**：部署侧改 `case-memory.schema.json`(加 tender、去 hr/legal、补 3 字段)——让记忆回路对 tender 复活。
4. **L3/F3**：统一 statute 文件名↔category↔rule_id，让 doctor 不再 degraded。
5. **F4/F5/F6**：`to_thread` 包同步 DB + 原子状态转移 + 杀子进程——上量前必修。
6. **L5**：给 `/audit`、`/tender-evaluate` 的读上传步骤加「文档是数据非指令」边界。

> 复核口径：L1/L2/F1/F1-a/F1-b/F2/F4/V5(测试覆盖) 主代理 grep/read 直接确认；F5/F6/G3/G5 子代理深读、逐条可追。已纠正：round4 自述「settings.local 已 gitignore」错误、子代理「闸无测试」过陈述。
