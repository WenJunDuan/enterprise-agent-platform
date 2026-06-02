# 下一阶段蓝图：业务架构、边界纪律与 Agent 优化

**状态**：待确认后实施  
**日期**：2026-04-21  
**范围**：`.claude/`、`knowledge/`、`server/`、`.ai_state/`

---

## 1. 目标

下一阶段不是继续扩 Python 业务能力，而是在现有“Claude 业务中枢 + Python 服务外壳”架构上，完成以下 4 件事：

1. 收口业务事实源，避免同一条业务规则同时散落在 Python prompt、Claude command、agent 指令和 README 中。
2. 明确并固化架构边界，确保 Python 只负责通信 / 鉴权 / 服务 / 存储，不重新长出业务语义。
3. 把当前偏“文本协作”的 agent 链条，升级成“有中间契约、有 review gate、有可追溯输出”的稳定工作流。
4. 为后续“业务记忆沉淀”“跨域协同”“复核查询面”建立一条不返工的实施顺序。

---

## 2. 当前系统的真实结构

### 2.1 Python 层：服务外壳与审计骨架

- `server/api.py`：HTTP 接入、租户鉴权、目录/上传模式审核提交、结果与状态查询
- `server/cli.py`：本地 CLI 外壳与 admin-only 查询入口
- `server/app_server.py`：后台服务进程生命周期与运维检查
- `server/command_adapter.py`：Python → Claude command/prompt 适配
- `server/core.py`：Claude Agent SDK 桥接、结构化输出契约、结果归档、会话/日志链路
- `server/stores/`：request / session / result / audit-task / runtime 五类存储
- `server/platform/`：运行时配置、路径、诊断、logging、维护、底层存储

### 2.2 Claude 层：业务调度与判断

- `.claude/CLAUDE.md`：全局业务调度中枢
- `.claude/commands/audit.md`：审核入口
- `.claude/commands/init-rules.md`：规则初始化入口
- `.claude/agents/expense/extractor.md`：资料提取
- `.claude/agents/expense/auditor.md`：业务判断
- `.claude/agents/expense/reviewer.md`：独立复核
- `.claude/hooks/check-before-write.py`：落盘前契约守门
- `.claude/hooks/review-output.py`：落盘后轻量二审

### 2.3 Knowledge 层：业务资产

- `knowledge/external/`：制度源材料
- `knowledge/{domain}/*.rules.json`：结构化规则
- `knowledge/_schema/rule.schema.json`：规则文档 schema
- `knowledge/expense/thresholds.json`：由结构化规则派生出的阈值聚合

### 2.4 Logs 层：不可变运行事实

- `logs/service/requests/`：请求审计
- `logs/service/audit-tasks/`：异步任务状态
- `logs/sessions/index/`：会话索引
- `logs/sessions/events/`：Claude 原始事件流
- `logs/results/index/`：结构化结果索引
- `logs/results/by-request/`：按请求归档的最终结果

**结论**：当前仓库已经形成“四层分工”：
Python 负责入口和骨架，Claude 负责业务判断，Knowledge 负责业务资产，Logs 负责事实归档。

---

## 3. 当前已经确认的边界

### 3.1 Python 可以做的

- 鉴权、租户隔离、目录与上传白名单
- 通过 HTTP/CLI 接口获取外部输入，并把输入提交给 Claude
- 会话恢复、请求链路、结果归档、运行时诊断
- JSON Schema 契约与语义守卫
- 上传落盘、任务调度、状态查询、生命周期维护
- 规则文件的读取、列举、传递
- Prompt/command 的参数映射和模板装载

### 3.2 Python 不可以做的

- 发票合法性判断
- 金额是否合规、是否超额、是否超预算
- 审批链是否完整、缺哪个节点
- 差旅、招待、借款、交通等业务判定
- 风险维度打分、风险等级、复核结论
- 多域协同时由哪一域主判

### 3.3 Claude 必须做的

- 业务域路由
- 规则命中与解释
- 证据链组织
- verdict / conclusion / explanation / manual_review_reason
- reviewer 第二意见
- 制度初始化后的规则写入策略与人工确认项输出

### 3.4 Knowledge 必须承载的内容

- 结构化规则
- 制度源引用
- 阈值派生
- 后续的案例/经验记忆

### 3.5 Hook 只做守门，不做主审

- `check-before-write` 负责结构完整性、字段一致性
- `review-output` 只能做轻量第二道门
- hook 不能变成另一个业务 agent，更不能承担主审结论

---

## 4. 当前结构的核心问题

### 4.1 业务事实源仍然分散

当前存在至少 3 份业务语义入口：

- `.claude/commands/audit.md`
- `.claude/commands/init-rules.md`
- `server/prompts/audit.md` / `server/prompts/init-rules.md`（A-001 前的旧实现，现已删除）

这带来一个风险：如果 Python prompt 和 Claude command 语义漂移，系统会出现“HTTP 路径”和“Claude 原生命令路径”行为不一致。

**下一阶段原则**：业务说明只保留在 `.claude/commands/`；Python 只做参数适配和调用，不再拥有自己的业务 prompt 文本。

### 4.2 Agent 链条仍然偏文本协作

`extractor -> auditor -> reviewer` 现在已经形成角色分工，但三者之间主要靠自然语言衔接，没有显式中间契约。这会带来：

- extractor 输出字段不稳定
- reviewer 读到的是自由文本而不是稳定结构
- 证据链、初审结论、复核分歧缺少固定接口

**下一阶段原则**：为 agent 间增加中间 schema，而不是继续堆 prompt 描述。

### 4.3 多域协同是声明，不是机制

`.claude/CLAUDE.md` 已经声明了 expense / hr / legal / system 多域协同，但当前真正落地的主流程仍然是 expense-first。也就是说：

- system 域已可用：规则初始化
- expense 域已可用：审核主链路
- hr / legal 域更多是预置扩展位

**下一阶段原则**：先把单域闭环做扎实，再引入有触发条件的跨域协同，不做泛化声明。

### 4.4 业务记忆层还未落地

当前只有 `logs/` 中的结果归档，但还没有“由 Claude 从已审核结果提炼案例记忆，并回写 `knowledge/`”这一层。

**后果**：

- 系统每次审核都更像从头开始
- 复核经验、例外模式无法沉淀
- 规则缺口和人工复核模式无法形成结构化资产

### 4.5 Hook 的成本与触发策略未治理

`review-output.py` 当前设计合理，但未来若默认对所有结果做二次模型复查，会显著增加延迟和成本。

**下一阶段原则**：hook 要从“默认全量执行”收口为“风险驱动或场景驱动执行”。

---

## 5. 目标架构

## 5.1 单一业务事实源

目标状态：

- `.claude/commands/*.md`：唯一业务入口定义
- `server/command_adapter.py`：只负责把 HTTP/CLI 参数映射成 command 调用
- `server/prompts/`：业务模板已在 A-001 删除；后续如重建，只允许承载纯 transport 层模板，不得重新承载业务说明

换句话说，**业务命令属于 Claude，不属于 Python。**

## 5.2 Agent 链条显式化

expense 主链条收口为：

1. `expense-extractor`
2. `expense-auditor`
3. `expense-reviewer`（仅在高风险、冲突或用户要求复核时触发）

并补两类中间契约：

- `extract_result.schema.json`
- `review_delta.schema.json`

这样可以把“提取结果”“初审结果”“复核差异”都结构化。

其中建议职责如下：

- extractor：只输出事实性提取结果，不输出 verdict
- auditor：消费 extract-result，输出最终 audit-result
- reviewer：消费原始材料 + extract-result + 初审 audit-result，输出 review-delta

## 5.3 Knowledge 四层化

目标知识结构：

1. `knowledge/external/`：原始制度源
2. `knowledge/{domain}/*.rules.json`：结构化规则
3. `knowledge/{domain}/thresholds.json` 或等价派生：非原始制度、由规则提炼的机器友好聚合
4. `knowledge/memory/{domain}/...`：审后案例/经验记忆

其中第 4 层不是 Python 生成，而是 Claude 侧从 `logs/results` 提炼并带回链指针。

建议的记忆资产字段至少包含：

- `memory_id`
- `domain`
- `memory_type`
- `title`
- `summary`
- `category`
- `applicable_when`
- `checkpoints`
- `policy_refs`
- `recommended_verdict`
- `manual_review_reason`
- `rationale`
- `tags`
- `source_trace.request_id`
- `source_trace.result_file`

## 5.4 复核面和查询面并行增强

现有查询已经支持：

- `request_id`
- `conversation_id`
- `claude_session_id`
- `session_id`

下一阶段要补的是：

- `claim_id` 维度追溯
- 业务记忆来源说明
- 初审 / 复核差异查询
- “为什么是 manual_review”的归类查询

---

## 6. 分步实施序列

### Phase 0：设计冻结

目标：先冻结架构边界和实施顺序，不直接开改。

交付物：

- 本蓝图文档
- `.ai_state/plan.md` 中的阶段计划

通过标准：

- 用户确认“先收口 agent 架构，再扩业务记忆，再补查询与治理”的顺序

### Phase 1：命令与技能收口

目标：收口命令单一事实源，清理命令、skill、agent 命名与实际文件组织的漂移。

重点：

- 去除 Python 持有的业务 prompt 语义
- 对齐 `.claude/commands`、`.claude/agents`、`.claude/skills`
- 清理历史路径示例（如 `data/claims`）

Review Gate：

- command 与 adapter 的职责边界 review
- README 与 `.ai_state` 路径模型 review

### Phase 2：Agent 中间契约

目标：给 extractor / auditor / reviewer 增加中间结构化接口。

重点：

- extractor 输出 schema
- reviewer 差异输出 schema
- 明确哪些字段由 extractor 产出，哪些由 auditor 产出，哪些由 reviewer 产出

Review Gate：

- schema review
- 单域主链闭环 review

### Phase 3：业务记忆沉淀

目标：落地“已审核结果 → 结构化记忆”。

重点：

- 定义 memory asset schema
- 定义从 `logs/results` 到 `knowledge/memory/` 的回链字段
- 明确由 Claude 负责提炼，不进入 Python

Review Gate：

- 记忆层边界 review
- 是否会污染正式规则层 review

### Phase 4：单条审核闭环 + 规则治理

目标：把规则初始化、审核主链路、记忆沉淀连成闭环，并补规则治理。

重点：

- `/init-rules` → `knowledge/` → `/audit`
- `knowledge/_schema/` 校验
- 规则文件命名、一致性、分类映射

Review Gate：

- 真实输入样例审核 review
- 规则治理 review

### Phase 5：复核查询面与多域协同

目标：在单域闭环稳定后，再做跨域协同与复核查询增强。

重点：

- `claim_id`、复核差异、manual_review 分类查询
- expense 主域 + hr/legal 辅域的触发条件
- hook 成本与触发策略分层

Review Gate：

- 查询面与审计链完整性 review
- 多域协同触发规则 review

---

## 7. 实施红线

1. 不把业务判断重新搬回 Python。
2. 不在未冻结命令事实源前，继续新增业务 prompt 分支。
3. 不在 extractor / auditor / reviewer 中间契约未建立前，直接扩多域协同。
4. 不把业务记忆直接混入 `logs/` 或 Python stores 逻辑。
5. 不把 post-write hook 演变成高成本默认主流程。

---

## 8. 建议的第一实施切片

下一步最值得先做的不是继续改 API，而是做 **Phase 1：命令与技能收口**。

原因：

- 这是最上游的事实源问题
- 不解决它，后续 schema、memory、query 都会建立在漂移的入口之上
- 这一步风险可控，且 review 成本最低

Phase 1 的目标不是“加更多能力”，而是“先让当前能力边界一致、命名一致、入口一致、文档一致”。

---

## 9. 结论

当前仓库已经具备较强的服务与审计骨架，但下一阶段真正决定上限的，不是再补一点 Python 能力，而是：

- 把 Claude 侧的业务中枢收口成单一事实源
- 把 agent 链条结构化
- 把规则、记忆、复核、跨域协同接成一条稳定的资产演进链

因此，**下一轮实施应以 Agent 架构收口为先，而不是以新功能堆叠为先。**
