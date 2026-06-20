# 全栈后端审查 — round4 (Claude/Opus, 2026-06-19)

范围：`server/`(~9.8k LOC Python)、`.claude/`(编排层/agents/skills/hooks/contracts)、`knowledge/`(规则)。排除 `audit-front`。
方法：4 个并行子代理深读 + 主代理逐条 grep/read 复核（凡标 ✅VERIFIED 的均已对照真实代码确认）。

---

## 0. 一句话结论

**这套系统的全部价值在于"可追溯、有制度依据的判断"，而默认运行路径根本不校验模型输出是否满足这一点。** 物理隔离守卫、常数时间比 token、verdict 单一真源、规则提取质量——这些都做得对；但信任边界（schema 校验）和数据边界（租户隔离）这两道门是开着的。修这两个，再谈其它。

架构校准（按你的澄清）：
- **2 层技术架构**：① Claude Agent SDK 驱动的 agent（`.claude/` + `knowledge/`，承载业务语义）；② Python 调 SDK 对外的 API 网关（`server/`，鉴权/归档/异步/进程）。
- **3 个真实业务域**：报销审核(expense)、OCR、招投标(tender)。
- **2 个未成功域**：legal/合同(contract) 与 HR——见 F8，这不是"保留待用"，是**已沉没成本的死代码**。

---

## 1. 发现清单（按严重度，已复核去重）

| # | 级别 | 层 | 一句话 | 证据 |
|---|---|---|---|---|
| F1 | **BLOCKER** | SDK桥/契约 | 默认路径(`AUDIT_STRUCTURED_OUTPUT=0`)不做 JSON Schema 校验，只查 verdict/explanation；`policy_refs`/`evidence_chain`/`risk_score`/必填字段全不验。伪造审批、虚构规则号、缺字段均静默通过并归档 | ✅ `server/common/` 无 `jsonschema`；`output_contracts.py:135-162`；`config.py:350` |
| F2 | **BLOCKER（多租户）/ HIGH（单组织）** | API网关 | `mode=directory` 只校验"在 `data/` 下"，不校验租户归属。`data/` 内含全部租户上传 + `data/db/platform.sqlite3` + `data/sessions/events`(全部会话原文)。任意已认证调用方可令 agent 读取并外泄 | ✅ `upload_helpers.py:32-46`；`paths.py:42-44` |
| F3 | **HIGH** | knowledge | tender 两个 statute 规则文件**通不过平台自己的资产校验器**：`category`≠文件名、`rule_id` 前缀不匹配 → `validate-assets` 报 degraded。三大真实域之一带病出厂 | ✅ `asset_validation.py:57-68` vs `statute-evalmethod.rules.json`(category=evalmethod, rule_id=tender_evalmethod_001) |
| F4 | **HIGH** | API网关 | 同步 SQLite 调用直接跑在 asyncio 事件循环上（worker 内 `upsert_*_task` 未 `to_thread`），单库 `busy_timeout=30s`。写争用时会阻塞整个事件循环。当前规模(2并发/单进程)潜伏，架构上是错的 | ✅ `audit_worker.py:66,93,121,147` + `create_task:174` |
| F5 | **HIGH** | API网关 | 裸 `asyncio.create_task` 不留引用(待定任务可被 GC、信号量前异常静默丢失)；准入无上限(任务在 accepted 无限堆积→内存 DoS)；超时只 cancel 协程，不保证杀掉 claude CLI 子进程→孤儿进程绕过信号量 | ✅ `audit_worker.py:174,48,84` |
| F6 | **HIGH** | API网关 | retry/delete 的 TOCTOU：读→判 status→写 跨 3 个独立连接、无原子守卫。两个并发 retry 同时过 409，各自起一个后台审核→双重执行/双重成本 | `routes/audit.py:194-221,238-244` |
| F7 | **MEDIUM** | 全层 | audit/tender/contract 在 store/route/worker 三层 ~95% 复制粘贴，~600 行。docstring 直接写"镜像 audit_worker"——抽象在哭着要出生。且其一(contract)是死域 | ✅ `diff` 规范化后仅表名/docstring 不同 |
| F8 | **MEDIUM** | 编排+网关 | legal/contract 与 HR 是未成功域却仍接入 CLAUDE.md 路由；contract 更已注册**活路由**(`api.py:269`)+808 行 Python 管道+schema，但 `knowledge/legal` 不存在→所有判断只能 `rule_gap`。HR 仅剩孤儿 agent 提示词。零价值，纯增路由歧义与攻击面 | ✅ `knowledge/legal`、`knowledge/hr` 均不存在 |
| F9 | **MEDIUM** | 契约 | enrich/validate 顺序错：validate 先跑，把 dict 形态/0-100 量纲的 `risk_dimensions` 删掉，专门修这些形态的 enrich 协程永远跑不到。且 `_scale_risk_dimension_score` 接受布尔(`float(True)=1.0`)，而其姊妹函数明确防了 bool | `contract.py:94-97`；`output_contracts.py:53-65,112-132` |
| F10 | **MEDIUM** | API网关 | 上传大小限制在 `await upload.read()` 全量读入内存**之后**才查；无文件数上限、无聚合上限。5GiB 分片会先被缓冲再撞 10MiB 限 → 内存/磁盘 DoS | `upload_helpers.py:141-143,69-74` |
| F11 | **LOW** | 编排 | `.claude/settings.local.json` 内有明文 SSH 口令 `3er4#ER$` + authorized_keys 注入命令。**已 gitignore**(非公开泄露)，但仍是工作文件里的真实凭据，且说明 agent 被手喂了服务器口令 | ✅ `settings.local.json:78,102,111`；`git ls-files` 未跟踪 |
| F12 | **LOW** | 编排/文档 | 死引用：`statute.rules.json`(单文件已不存在)仍被 evaluator.md / tender-eval SKILL / rule-init SKILL / tender/README 引用(README 还谎称 statute "尚未生成")；`priority` 字段在 schema 中不存在(`additionalProperties:false` 会拒)；`case-memory.schema.json` 域枚举缺 `tender`→tender 记忆无法校验 | 见各文件 |

---

## 2. 三条必须先修的（详述 + 代码 + 修法）

### F1 — 信任边界是开的（BLOCKER）

`AUDIT_STRUCTURED_OUTPUT` 默认 `False`（`config.py:350`），因为网关模型(qwen)不做原生 function calling。于是**默认走文本模式**，校验只有手写的 `_validate_audit_result`（`output_contracts.py:135-162`）：

```python
verdict = structured_output.get("verdict")
if verdict not in AUDIT_DECISION_DERIVATION: raise ...
if not str(structured_output.get("explanation") or "").strip(): raise ...
if verdict == "manual_review": # 查 reason ∈ 7 枚举
_cleanse_risk_dimensions(structured_output)
```

而 schema 声明 `required: [claim_id, verdict, explanation, reasons, policy_refs, risk_score, extracted_data, evidence_chain, reviewed_by, timestamp]` + `additionalProperties:false`。`server/common/` 里**没有任何 `jsonschema.validate`**（✅grep 确认，全仓只有 `ocr/runner.py` 用了）。

后果：模型返回 `{"verdict":"approved","explanation":"符合差旅政策"}`——无 policy_refs、无 evidence_chain、无 risk_score——照样通过、归档、经 `/audit/tasks/{id}/result` 当权威结果返回。`policy_refs:["TRAVEL-RULE-999"]`(不存在的规则)也通过，因为**没有任何代码把模型自报的 policy_refs 回查真实 rule_id**。CLAUDE.md:107 承诺的"所有结论都必须能回溯到 policy_refs/evidence_chain"在代码里不存在。

**修**：
1. `apply_schema_semantics` 里在 `_extract_json_object` 后、语义校验前，对 text 与 structured 两条路都跑 `jsonschema.validate(parsed, load_output_schema(name))`，校验失败抛 `JSONContractError`（`runner.py:134` 已有重试环会接住）。
2. 把命中的 rule_id 集合传进校验器，断言 `policy_refs ⊆ 已注入规则集`；`verdict=approved` 时尤其要硬性回查。这是最便宜的高价值加固，现在完全缺失。

### F2 — 数据边界是开的（多租户 BLOCKER / 单组织 HIGH）

`validate_directory_case_path`（`upload_helpers.py:32-46`）唯一约束是 `resolved.relative_to(data/)`。但 `data/` 是所有租户共享的：`SUBMISSION_ROOT_DIR=data/submissions`、`data/db/platform.sqlite3`(全租户库)、`data/sessions/events`(全部会话原文)都在其下。任意已认证租户 POST `{"mode":"directory","directory_path":"data/sessions/events"}` 到 `/audit/submit`(或 `/ocr/extract`、`/tender/evaluate`、`/contract/review`)，即可让 agent 读取并把内容回吐。

注意校准：keyed 查询(task/result)的租户隔离**是好的**——`get_audit_task(request_id, tenant=tenant)` 全部带 `WHERE tenant=?`，`request_id` 是 uuid4 不可枚举，token 比对是 `secrets.compare_digest` 常数时间。破在 directory 这一个口子，且与"猜 uuid"无关——`data/sessions`、`data/db` 无需猜。

**修**：directory 模式本质是任意本地文件读原语，不该暴露给租户。要么(a)对外只留 `upload` 模式（写进服务端选定的新目录），要么(b)把每租户限制在 `data/submissions/<tenant>/...` 子树并校验归属。无论如何，audit/OCR runner 都不该能走进 `data/db`、`data/sessions`、`data/contracts`。

### F3 — tender 规则带病出厂（HIGH）

`asset_validation.py:60-68`：`expected_category = 文件名去掉 .rules.json`；`expected_prefix = f"{domain}_{category}_"`。

| 文件 | 文件名推导 category | 文件内 category | 文件内 rule_id | 结果 |
|---|---|---|---|---|
| `statute-evalmethod.rules.json` | `statute-evalmethod` | `evalmethod` | `tender_evalmethod_001` | category 不匹配 + 前缀应为 `tender_statute-evalmethod_` 不匹配 |
| `statute-regulation.rules.json` | `statute-regulation` | `regulation` | `tender_regulation_001` | 同上 |

`validate-assets` 对 tender 域报 `degraded`。规则内容本身是好的（实质、带 `requires_live_event` 等标签），坏的是 plumbing 元数据。**修**：要么文件改名为 `evalmethod.rules.json`/`regulation.rules.json`，要么改 category+rule_id。三者(文件名/category/rule_id)不能都对。

---

## 3. 做得对的地方（不灌水，是真的好）

- **SQL 注入：干净。** 所有 f-string SQL 只插值硬编码的列名/表名，值全走 `?` 占位符。`# noqa: S608` 标注正确。我专门找洞，没有。
- **鉴权原语正确**：`secrets.compare_digest` 常数时间(`deps.py:66`)；不安全默认 key 是**强制 503 拒绝**而非仅告警(`deps.py:47-55`，有测试)。
- **离线守卫**(`config.py:66-82`)：base_url 为空/指向 anthropic.com 直接拒审并强关遥测——针对内网威胁模型，这是真正想清楚了的设计。
- **verdict 单一真源**：服务端从 verdict 派生 result/conclusion，提示词禁止模型自报后两者——防三字段不一致，对。
- **机制/策略分离**：`register_schema_processor` 注册表 + 处理器，无中心 if/elif，开放扩展。
- **"不可判定项绝不判 0"**：把"缺失≠零分"的范畴错误写进规则标签而非仅口号——成熟洞察。
- **expense 规则是生产级**：有 `source_text` 原文引用、数值 limit+单位、可溯源到文号。
- **二次复核成本治理**：正确识别了 ROI 问题并移除 hook，CLAUDE.md 诚实记录(✅与 settings.json 对照属实)。这是博弈/熵增视角下的好决策。
- 原子文件写(temp+os.replace+fsync)、OCR 逐文件错误隔离、路径逃逸守卫、运行时快照脱敏——基本功扎实。

---

## 4. 修复优先级

1. **F1**（信任边界）+ policy_refs 回查——平台立身之本，最便宜的高价值修复。
2. **F2**（数据边界）——若真要多租户，是 BLOCKER。
3. **F3 / F12 / F9 / F10**——出厂带病、死引用、校验逻辑互搏、上传 DoS。
4. **F4/F5/F6**（异步正确性）——上规模前必修；当前单进程低并发可排后。
5. **F7 + F8**——把三层 ~600 行复制粘贴收敛成一个泛型 `TaskPipeline(table, runner, labels)`，**顺手删掉 contract/HR 死域**（先减熵再抽象，否则你在为死代码做抽象）。

---

## 5. 附：重复度量化（F7）

规范化域名后 `diff`：
- **task store**：`tender_task_store.py`(185) vs `contract_task_store.py`(186) 仅 docstring + 表名(`*_tasks` vs `*_review_tasks`)不同，~96% 同。dataclass/`_coerce_record`/`upsert`/`delete`/`get`/`list`/`recover_stale`/`_coerce_timestamp` 逐字相同。
- **worker**：三个 `_execute_inner` 结构逐字同（同 started_at/logging_context/running-upsert/wait_for/三个 except 各写 ~17 键 dict），仅 store 函数名/超时常量/runner 调用/中文文案不同。~80%/文件。
- **route**：tender.py/contract.py ~72% 是 audit.py 的机械克隆。
- 跨三层保守估 **600+ 行复制粘贴**，应收敛为 1 份实现 + 3 个 ~10 行配置声明。在一处修 bug 必须记得修三处——这正是会烂的特例化重复。

---
*复核口径：F1/F2/F3/F4/F7/F11 已主代理 grep/read 直接确认；F5/F6/F9/F10/F12 来自子代理深读、逻辑可追。F11 已纠正子代理"已提交入库"的过陈述——实际 gitignore，仅本地。*
