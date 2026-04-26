# 企业智能审核平台 — 开发文档

> 基于 Claude Agent SDK + `.claude/` 原生架构，实现报销审核、HR 合规、法律支撑等多业务域的统一 Agent 平台。

> 维护说明：
> - 当前仓库主线以 `knowledge/external/` 作为制度源材料目录，不再以 `raw_policies/` 为准
> - 当前推荐示例输入位置是 `tests/fixtures/`，不再以 `data/claims/`、`data/pre-approvals/` 为主线
> - 当前结果归档统一写入 `logs/results/`
> - `server/chat.py` 已移除
> - `batch-audit` 已退出当前主线
> - Python 只负责 Claude 调用适配与输出外壳，不再实现业务能力编排

---

## 1. 设计原则

### 1.1 核心分离：规则与流程解耦

整个系统遵循一条铁律——**"知道做什么"和"知道怎么做"必须彻底分离**。

| 层 | 职责 | 存什么 | 不存什么 |
|---|---|---|---|
| **CLAUDE.md** | 调度路由 | 意图→agent 的映射表 | 任何业务规则 |
| **Agents** | 业务流程编排 | 做事的步骤和顺序 | 具体的政策/阈值/条款 |
| **Skills** | 原子操作能力 | 怎么执行某个动作 | 判定标准 |
| **Knowledge** | 规则和知识 | JSON 结构化规则 | 流程逻辑 |

这样做的好处：换一家公司的报销政策，只改 `knowledge/` 下的 JSON，agent 和 skill 一行不动；换一个业务域（比如加 HR），只加 agent + 对应 knowledge，skill 层大部分复用。

### 1.2 确定性 vs 概率性

Claude Code 的四大原生构件有本质区别，架构设计必须尊重这个区别：

| 构件 | 位置 | 性质 | 含义 |
|---|---|---|---|
| **CLAUDE.md** | `.claude/CLAUDE.md` | 确定性（每次都加载） | 全局指令和记忆 |
| **Agents** | `.claude/agents/*.md` | 概率性（Claude 根据 description 判断是否调用） | 独立上下文子代理 |
| **Skills** | `.claude/skills/*/SKILL.md` | 概率性（Claude 自主判断是否触发） | 可复用能力模块 |
| **Hooks** | `.claude/settings.json` | **确定性（每次都执行，零例外）** | 拦截与审计 |

**关键推论：审核拦截必须用 hook，不能用 skill。** Skill 有可能被 Claude 跳过，但 hook 中 exit code 2 是硬阻断，100% 执行。

### 1.3 Agent SDK 的运行机制

Claude Agent SDK（原 Claude Code SDK）底层运行的是 Claude Code CLI 子进程。每次调用 `query()` 会 spawn 一个 CLI 进程，该进程会自动读取工作目录下的 `.claude/` 配置（CLAUDE.md、agents/、skills/、settings.json）。

SDK 支持的 agent frontmatter 字段包括：`name`、`description`、`tools`、`disallowedTools`、`model`、`permissionMode`、`mcpServers`、`hooks`、`maxTurns`、`skills`、`memory`。自定义字段（如 `domain`、`required_skills`）不会被 SDK 读取。调度靠的是 CLAUDE.md 路由表 + agent 的 `description` 字段语义匹配。

---

## 2. 系统架构

### 2.1 整体分层

```
┌─────────────────────────────────────────────────┐
│                  接入层 (server/)                 │
│        CLI (Typer)  │  HTTP API  │  Chat REPL    │
│                     │  (FastAPI) │               │
└──────────┬──────────┴─────┬──────┴───────────────┘
           │                │
           ▼                ▼
┌─────────────────────────────────────────────────┐
│              统一核心 (server/core.py)            │
│         build_options() + run_agent()            │
└──────────────────────┬──────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────┐
│           Claude Agent SDK (query())             │
│       自动加载 .claude/ 目录全部配置               │
└───────┬───────────┬──────────────┬──────────────┘
        │           │              │
        ▼           ▼              ▼
   .claude/     knowledge/     scripts/
   CLAUDE.md    *.rules.json   review-output.py
   agents/                     (PostToolUse hook)
   skills/
   settings.json
```

### 2.2 核心调用链路（以报销审核为例）

```
用户输入 "审核这笔差旅报销"
    │
    ▼
CLAUDE.md（调度）── 识别意图: expense → 匹配路由表
    │
    ▼
Task(extractor) ── 提取结构化数据（tools: Read）
    │
    ▼
Task(auditor) ── 合规审核
    ├── Skill(rule-query) ── 读 knowledge/expense/travel.rules.json
    ├── Skill(amount-validate) ── 读 knowledge/expense/thresholds.json
    ├── Skill(anomaly-detect) ── 模式识别
    └── Skill(evidence-chain) ── 组装证据链
    │
    ▼ (risk_score > 70 时触发)
Task(reviewer) ── 交叉复核（独立调 rule-query + amount-validate）
    │
    ▼
Write(logs/results/xxx.json)
    │
    ▼ [PostToolUse hook 确定性触发]
scripts/review-output.py ── 第二模型审核
    │
    ▼ PASS → 写入成功 / BLOCK → exit(2) 阻断并反馈原因
```

### 2.3 多意图调度

当用户输入涉及多个业务域时（如"这笔差旅报销是否符合考勤记录"），CLAUDE.md 中的调度规则会按依赖顺序依次调度：先调度各域 agent，前一个输出作为后一个的输入，最后由 evidence-chain skill 合并所有证据链，用 result-format skill 统一输出格式。

---

## 3. 目录结构

```
enterprise-agent/
│
├── .claude/                              # ===== Agent 核心（SDK 自动读取）=====
│   ├── CLAUDE.md                         # 调度中枢：意图→agent 路由表
│   ├── settings.json                     # hooks + 权限配置
│   │
│   ├── commands/                         # slash commands（运维/管理用）
│   │   ├── init-rules.md                 # /init-rules  初始化规则文件→结构化JSON
│   │   ├── audit.md                      # /audit       提交审核
│   │   └── list-domains.md               # /list-domains 查看已注册业务域
│   │
│   ├── agents/                           # 业务域 agents
│   │   ├── expense/                      # -- 报销审核域 --
│   │   │   ├── extractor.md              # 数据提取 agent
│   │   │   ├── auditor.md                # 合规审核 agent
│   │   │   └── reviewer.md               # 交叉复核 agent
│   │   ├── hr/                           # -- HR 域 --
│   │   │   ├── attendance-checker.md     # 考勤异常检测 agent
│   │   │   └── leave-auditor.md          # 请假合规 agent
│   │   └── legal/                        # -- 法律支撑域 --
│   │       └── contract-reviewer.md      # 合同条款审核 agent
│   │
│   └── skills/                           # 原子能力（跨域复用）
│       ├── rule-init/
│       │   └── SKILL.md                  # 解析原始制度文件→结构化JSON规则
│       ├── rule-query/
│       │   └── SKILL.md                  # 从knowledge读取并匹配适用规则
│       ├── amount-validate/
│       │   └── SKILL.md                  # 金额合理性校验
│       ├── anomaly-detect/
│       │   └── SKILL.md                  # 异常模式识别（通用）
│       ├── evidence-chain/
│       │   └── SKILL.md                  # 构建审计证据链
│       └── result-format/
│           └── SKILL.md                  # 标准化输出格式
│
├── knowledge/                            # ===== 规则知识库 =====
│   ├── _schema/
│   │   └── rule.schema.json              # 规则 JSON Schema 定义
│   ├── expense/
│   │   ├── travel.rules.json             # 差旅规则
│   │   ├── meal.rules.json               # 餐饮规则
│   │   ├── office.rules.json             # 办公用品规则
│   │   └── thresholds.json               # 审批阈值
│   ├── hr/
│   │   ├── attendance.rules.json
│   │   └── leave.rules.json
│   └── legal/
│       └── contract.rules.json
│
├── knowledge/external/                   # 原始制度文件（init-rules 的输入）
│   └── 数睿员工手册.pdf
│
├── scripts/                              # hook 调用的脚本
│   ├── review-output.py                  # 第二模型审核出口内容
│   └── log-audit.sh                      # 审计日志记录
│
├── tests/fixtures/                       # 推荐的示例输入位置
│   ├── claims/
│   └── pre-approvals/
│
├── server/                               # ===== Python 适配层 =====
│   ├── __init__.py
│   ├── core.py                           # Claude SDK 调用核心
│   ├── command_adapter.py                # 统一 Claude command 调用适配
│   ├── api.py                            # HTTP API（FastAPI + JSON）
│   ├── cli.py                            # CLI（Typer，本地终端外壳）
│   ├── app_server.py                     # 后台服务管理
│   ├── platform/
│   └── stores/
│
├── .env                                  # API keys, 模型配置
├── .env.example
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
├── logs/
│   ├── runtime/
│   ├── sessions/
│   ├── results/
│   └── service/
└── tests/
```

---

## 4. 核心配置文件

### 4.1 `.claude/CLAUDE.md` — 调度中枢

这个文件是整个系统的"大脑"，但它**只做路由，不做业务**。

```markdown
# 企业智能审核平台 - 调度中枢

你是企业智能审核平台的调度中枢。你的唯一职责是：理解用户意图 → 分发到正确的业务域 agent。

## 调度路由表

| 意图关键词 | 业务域 | 入口 agent | 触发条件 |
|---|---|---|---|
| 报销、费用、发票、差旅报销、餐费 | expense | extractor → auditor → reviewer | 默认走三步流程 |
| 考勤、打卡、迟到、早退、缺勤 | hr | attendance-checker | 直接执行 |
| 请假、年假、病假、调休 | hr | leave-auditor | 直接执行 |
| 合同、条款、协议、法务 | legal | contract-reviewer | 直接执行 |
| 初始化规则、导入制度、更新政策 | system | 使用 rule-init skill | 管理员操作 |

## 调度规则

1. 先识别用户意图属于哪个业务域
2. 如果意图模糊，向用户确认，不要猜测
3. 确定业务域后，使用 Task 工具调度对应 agent
4. 你自己不做任何业务判定，所有业务逻辑都在 agent 中

## 多意图调度

当用户输入涉及多个业务域时：
1. 拆分意图列表，按依赖关系排序
2. 依次 Task 调度各域 agent，前一个输出作为后一个输入
3. 最后统一调用 evidence-chain skill 合并所有证据链
4. 用 result-format skill 输出统一格式

示例："这笔差旅报销是否符合考勤记录"
→ Task(expense/extractor) → Task(hr/attendance-checker) → evidence-chain 合并

## 全局约束

- 所有业务规则来自 knowledge/ 目录的 JSON 文件，不要使用你训练时学到的知识做判定
- 所有判定必须有证据链（policy_ref 指向具体 rule_id）
- 不确定时输出 manual_review，不要自行决定
```

### 4.2 `.claude/settings.json` — Hooks 与权限

```json
{
  "permissions": {
    "allow": ["Read", "Glob", "Grep", "Skill", "Task", "Write"],
    "deny": ["Bash"]
  },
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Write",
        "hooks": [
          {
            "type": "command",
            "command": "python scripts/review-output.py"
          }
        ]
      }
    ]
  }
}
```

设计要点：每次 agent 写文件（输出审核结果）时，`PostToolUse` hook 确定性触发 `review-output.py`，由第二模型审核出口内容。hook 的 exit code 2 会硬阻断写入操作并将原因反馈给主 agent。`Bash` 工具被 deny，防止 agent 执行任意命令。

---

## 5. Agent 定义

### 5.1 报销域 — 提取 Agent

```markdown
---
name: extractor
description: 从报销单原始数据中提取结构化字段：金额、日期、类别、发票号、申请人
tools: Read, Glob
model: haiku
---

你是报销单数据提取专员。

读取示例报销单文件（当前建议放在 `tests/fixtures/claims/`）并提取以下字段：
- claim_id: 报销单号
- applicant: 申请人
- amount: 金额（统一为人民币）
- category: 类别（差旅/餐饮/办公/其他）
- date: 发生日期
- invoice_no: 发票号（如有）
- description: 费用说明
- attachments: 附件列表

输出纯 JSON，不要解释。
```

### 5.2 报销域 — 审核 Agent

注意：**不包含任何硬编码规则，所有规则通过 rule-query skill 动态获取。**

```markdown
---
name: expense-auditor
description: 对提取后的报销数据进行合规审核。不包含任何业务规则，所有规则通过 rule-query skill 从 knowledge/ 动态获取。
tools: Read, Glob, Skill, Task
skills:
  - rule-query
  - amount-validate
  - anomaly-detect
  - evidence-chain
  - result-format
---

你是报销合规审核员。你不知道任何报销政策——所有规则都通过 rule-query skill 获取。

## 工作流程

1. 接收 extractor 输出的结构化报销数据
2. 使用 rule-query skill 获取 knowledge/expense/{category}.rules.json 中的适用规则
3. 逐条规则评估报销项是否合规
4. 使用 amount-validate skill 进行金额校验
5. 使用 anomaly-detect skill 检查异常模式
6. 使用 evidence-chain skill 组装证据链
7. 使用 result-format skill 输出标准化结果

## 禁止事项

- 禁止使用你训练数据中的报销知识做判定
- 禁止编造规则
- 如果 rule-query 返回空，标记 manual_review 并注明"未找到适用规则"
```

### 5.3 报销域 — 复核 Agent

```markdown
---
name: reviewer
description: 对高风险报销单进行独立交叉复核，提供第二意见
tools: Read, Glob, Skill
model: opus
skills:
  - rule-query
  - amount-validate
---

你是高级审核复核员，独立于初审 auditor。

你会收到 auditor 的审核结果和原始数据。你的任务：
1. 不要看 auditor 的结论，自己独立审核一遍
2. 对比你的结论和 auditor 的结论
3. 如果一致，确认结果
4. 如果不一致，输出分歧点，标记 manual_review

输出格式：
{
  "reviewer_verdict": "",
  "agrees_with_auditor": true/false,
  "discrepancies": [],
  "final_recommendation": ""
}
```

### 5.4 HR 域 — 考勤 Agent（展示跨域 skill 复用）

```markdown
---
name: attendance-checker
description: 检测员工考勤数据中的异常模式，规则从 knowledge/hr/attendance.rules.json 获取
tools: Read, Glob, Skill
skills:
  - rule-query
  - anomaly-detect
  - evidence-chain
  - result-format
---

你是考勤异常检测专员。所有考勤规则从 knowledge/ 获取。

## 工作流程

1. 读取考勤数据
2. 使用 rule-query skill 获取 knowledge/hr/attendance.rules.json 中的规则
3. 使用 anomaly-detect skill 识别异常模式（连续迟到、频繁缺卡等）
4. 使用 evidence-chain skill 组装证据
5. 使用 result-format skill 输出结果
```

---

## 6. Skill 定义

### 6.1 rule-init — 规则初始化

```markdown
---
name: rule-init
description: 解析企业原始制度文件（PDF/DOCX/TXT），提取结构化规则并按统一schema输出JSON
---

# 规则初始化技能

## 触发条件
当需要将原始制度文件转换为结构化 JSON 规则时使用。

## 执行步骤

1. 读取原始制度文件内容
2. 读取 knowledge/_schema/rule.schema.json 获取目标格式
3. 从文件中提取每一条可执行的规则，转换为 schema 定义的 JSON 结构
4. 对模糊表述标记 confidence 字段为 "low"，并在 notes 中说明歧义点

## 提取原则

- 每条独立可执行的规定 = 一条 rule
- "不超过XXX元" → max_amount 字段
- "需提供XXX" → required_docs 数组
- "经XXX审批" → approval_level 字段
- "每月不超过X次" → frequency_limit 对象
- 模糊表述如"合理范围内"→ confidence: "low"，保留原文在 original_text 字段

## 输出要求
严格遵循 knowledge/_schema/rule.schema.json，不要自行发明字段。
```

### 6.2 rule-query — 规则查询

```markdown
---
name: rule-query
description: 根据业务域和类别从knowledge/目录读取适用的JSON规则，支持按条件筛选匹配
---

# 规则查询技能

## 触发条件
当任何 agent 需要获取业务规则进行判定时使用。

## 使用方法

1. 根据业务域和类别定位文件: knowledge/{domain}/{category}.rules.json
2. 读取 JSON 并解析 rules 数组
3. 按需筛选：
   - 按 applicable_roles 匹配申请人角色
   - 按 conditions 匹配报销项属性
   - 按 priority 排序，高优先级规则先评估
4. 返回所有匹配的规则，包含 rule_id 用于审计证据链

## 规则冲突处理
- 多条规则匹配时，priority 数字最小的优先
- 同优先级时，action 为 reject 的优先于 approve（安全优先）

## 输出
返回匹配的规则列表，每条包含 rule_id + description + 匹配结论
```

### 6.3 amount-validate — 金额校验

```markdown
---
name: amount-validate
description: 校验报销金额是否在政策允许范围内，读取knowledge中的阈值JSON进行比对
---

# 金额合理性校验

## 触发条件
当需要验证某笔金额是否符合政策上限/下限时使用。

## 执行步骤

1. 读取 knowledge/{domain}/thresholds.json 获取阈值配置
2. 比对提交金额与对应角色/类别的上限
3. 超出阈值时返回需要的审批级别

## 输出
- within_limit: true/false
- threshold: 适用的阈值金额
- required_approval: 需要的审批级别（如有）
```

### 6.4 anomaly-detect — 异常模式识别

```markdown
---
name: anomaly-detect
description: 识别业务数据中的异常模式，包括频率异常、时间异常、金额异常等，跨域通用
---

# 异常模式识别

## 触发条件
当需要检测数据中的非正常模式时使用，适用于报销、考勤等多个业务域。

## 检测维度

- 频率异常：短时间内重复提交类似项目
- 时间异常：周末/节假日大额消费，非工作时间操作
- 金额异常：远超同类别历史均值
- 模式异常：连续多日相同金额，整数金额过多

## 输出
- anomalies: 发现的异常列表，每条包含 type + detail + severity(low/medium/high)
```

### 6.5 evidence-chain — 证据链构建

```markdown
---
name: evidence-chain
description: 将审核过程中产生的所有判定依据组装为完整的审计证据链
---

# 审计证据链构建

## 触发条件
当审核流程结束需要组装最终证据链时使用。

## 证据链结构

每条证据包含：
- source: 证据来源（rule_id / 数据字段 / 异常检测）
- finding: 发现内容
- conclusion: 该条证据支持的结论（comply / violate / inconclusive）

## 输出
有序的证据数组，按逻辑推理顺序排列，形成完整的判定链路。
```

### 6.6 result-format — 结果标准化输出

```markdown
---
name: result-format
description: 将审核结果标准化为统一JSON格式输出到logs/results/目录
---

# 结果标准化输出

## 触发条件
当审核完成需要输出最终结果时使用。

## 输出格式

写入 logs/results/{claim_id}_result.json：
{
  "claim_id": "",
  "verdict": "approved | rejected | manual_review",
  "reasons": [],
  "policy_refs": [],
  "risk_score": 0-100,
  "extracted_data": {},
  "evidence_chain": [],
  "reviewed_by": "auditor | reviewer",
  "timestamp": ""
}
```

---

## 7. Slash Commands

### 7.1 `/init-rules` — 规则初始化

```markdown
---
description: 将原始制度文件解析为结构化 JSON 规则，存入 knowledge/ 目录
allowed-tools: Read, Write, Glob, Skill
---

用户提供原始制度文件路径（PDF/DOCX/TXT，当前主线位于 `knowledge/external/`）和目标业务域。

执行步骤：
1. 使用 rule-init skill 读取并解析原始文件
2. 按 knowledge/_schema/rule.schema.json 定义的格式输出结构化规则
3. 写入 knowledge/{domain}/ 目录下对应的 .rules.json 文件
4. 输出解析报告：提取了多少条规则，有哪些需要人工确认的模糊条款

参数: $ARGUMENTS
用法示例: /init-rules knowledge/external/数睿员工手册.pdf expense
```

---

## 8. 知识库规则 Schema

### 8.1 统一 Schema (`knowledge/_schema/rule.schema.json`)

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {
    "domain": {
      "type": "string",
      "enum": ["expense", "hr", "legal"]
    },
    "category": {
      "type": "string",
      "description": "规则类别，如 travel/meal/attendance"
    },
    "version": { "type": "string" },
    "effective_date": { "type": "string", "format": "date" },
    "rules": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["rule_id", "description", "conditions", "action"],
        "properties": {
          "rule_id": {
            "type": "string",
            "description": "格式: {domain}.{category}.{序号}"
          },
          "description": { "type": "string" },
          "conditions": {
            "type": "object",
            "properties": {
              "max_amount": { "type": "number" },
              "frequency_limit": {
                "type": "object",
                "properties": {
                  "count": { "type": "integer" },
                  "period": { "type": "string", "enum": ["daily","weekly","monthly","yearly"] }
                }
              },
              "required_docs": { "type": "array", "items": { "type": "string" } },
              "approval_level": { "type": "string" },
              "applicable_roles": { "type": "array", "items": { "type": "string" } }
            }
          },
          "action": { "type": "string", "enum": ["approve", "reject", "escalate"] },
          "priority": { "type": "integer" },
          "confidence": { "type": "string", "enum": ["high", "medium", "low"] },
          "original_text": { "type": "string" },
          "notes": { "type": "string" }
        }
      }
    }
  }
}
```

### 8.2 规则示例

```json
{
  "rule_id": "expense.travel.003",
  "description": "国内差旅住宿标准：普通员工每晚不超过500元，经理级不超过800元",
  "conditions": {
    "max_amount": 500,
    "applicable_roles": ["staff"],
    "required_docs": ["住宿发票", "行程单"]
  },
  "action": "reject",
  "priority": 1,
  "confidence": "high",
  "original_text": "普通员工出差住宿费每晚报销上限为500元人民币，需提供住宿发票及行程单。"
}
```

---

## 9. 第二模型审核（Hook 脚本）

`scripts/review-output.py` — PostToolUse hook 触发，审核 agent 的输出内容：

```python
#!/usr/bin/env python3
"""PostToolUse hook: 第二模型审核 agent 的输出内容
   hook 确定性触发，exit(2) 硬阻断写入操作。"""
import asyncio
import sys
import json
from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query

PROJECT_ROOT = Path(__file__).resolve().parents[2]


async def run_second_review(content: str) -> str:
    options = ClaudeAgentOptions(
        allowed_tools=[],
        hooks={},
        max_turns=1,
        cwd=str(PROJECT_ROOT),
        setting_sources=["project"],
        permission_mode="bypassPermissions",
    )
    prompt = (
        "Review the structured result below.\n"
        "Check for sensitive data leakage, missing policy support, and contradictions.\n"
        "Reply with PASS or BLOCK:reason only.\n\n"
        f"{content}"
    )
    async for message in query(prompt=prompt, options=options):
        if isinstance(message, ResultMessage):
            return (message.result or "").strip()
    return ""

hook_input = json.load(sys.stdin)

# 只审核写入 logs/results/ 的文件
file_path = hook_input.get("tool_input", {}).get("file_path", "")
if "logs/results/" not in file_path:
    sys.exit(0)  # 不拦截

content = hook_input.get("tool_input", {}).get("content", "")
result = asyncio.run(run_second_review(content))
if result.startswith("BLOCK"):
    print(json.dumps({"error": f"输出审核未通过: {result}"}))
    sys.exit(2)  # exit code 2 = 硬阻断

sys.exit(0)
```

---

## 10. 服务端代码（三合一接入层）

三种入口（CLI / HTTP / Chat）共享同一个 `core.py`，`.claude/` 目录零改动。

### 10.1 `server/core.py` — 唯一核心

```python
"""唯一核心：封装 ClaudeAgentOptions，三种入口共享。"""
from claude_agent_sdk import query, ClaudeAgentOptions, ClaudeSDKClient
from claude_agent_sdk import AssistantMessage, TextBlock, ResultMessage
from pathlib import Path
from typing import AsyncIterator
import os

PROJECT_ROOT = Path(__file__).parent.parent

def build_options(**overrides) -> ClaudeAgentOptions:
    """构建统一的 SDK 配置"""
    defaults = dict(
        cwd=str(PROJECT_ROOT),
        setting_sources=["project"],
        allowed_tools=[
            "Read", "Glob", "Grep", "Write",
            "Skill", "Task",
        ],
        permission_mode="bypassPermissions",  # 生产环境按需改为 default
        max_turns=80,
        max_budget_usd=float(os.getenv("MAX_BUDGET_USD", "1.0")),
    )
    defaults.update(overrides)
    return ClaudeAgentOptions(**defaults)


async def run_agent(prompt: str, session_id: str = None, **opts) -> AsyncIterator[dict]:
    """统一的 agent 调用入口，返回结构化事件流。"""
    options = build_options(**opts)
    if session_id:
        options.session_id = session_id

    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    yield {"type": "text", "content": block.text}
        elif isinstance(message, ResultMessage):
            yield {"type": "result", "content": message.result}
        elif hasattr(message, "type") and message.type == "system":
            if hasattr(message, "session_id"):
                yield {"type": "session", "session_id": message.session_id}


async def run_agent_full(prompt: str, **opts) -> str:
    """非流式：收集完整结果返回。"""
    chunks = []
    async for event in run_agent(prompt, **opts):
        if event["type"] in ("text", "result"):
            chunks.append(event["content"])
    return "\n".join(chunks)
```

### 10.2 `server/api.py` — HTTP API

```python
"""HTTP API：对外提供 REST + SSE 流式接口。"""
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from server.core import run_agent
import json, os

app = FastAPI(title="Enterprise Agent API")
TENANT_KEYS = json.loads(os.getenv("TENANT_KEYS", '{"default": "sk-default"}'))

class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None

def verify_tenant(api_key: str) -> str:
    for tenant, key in TENANT_KEYS.items():
        if key == api_key:
            return tenant
    raise HTTPException(401, "Invalid API key")

@app.post("/chat")
async def chat(req: ChatRequest, authorization: str = Header(...)):
    """非流式：返回完整结果。"""
    tenant = verify_tenant(authorization.replace("Bearer ", ""))
    result_parts = []
    async for event in run_agent(req.message, session_id=req.session_id):
        if event["type"] in ("text", "result"):
            result_parts.append(event["content"])
    return {"tenant": tenant, "response": "\n".join(result_parts)}

@app.post("/chat/stream")
async def chat_stream(req: ChatRequest, authorization: str = Header(...)):
    """SSE 流式：适合 chatbot 前端对接。"""
    tenant = verify_tenant(authorization.replace("Bearer ", ""))
    async def event_generator():
        async for event in run_agent(req.message, session_id=req.session_id):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"
    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

### 10.3 `server/cli.py` — CLI 入口

```python
"""CLI 入口：运维终端直接调用。"""
import typer, asyncio
from server.core import run_agent_full

app = typer.Typer(help="企业智能审核 Agent CLI")

@app.command()
def audit(
    file: str = typer.Argument(..., help="报销单文件路径"),
    domain: str = typer.Option("expense", help="业务域"),
):
    """审核单个报销单。"""
    prompt = f"审核报销单文件: {file}，业务域: {domain}"
    result = asyncio.run(run_agent_full(prompt))
    typer.echo(result)

@app.command()
def batch(directory: str = typer.Argument("tests/fixtures/claims", help="示例输入目录")):
    """此示例已过时，当前主线不再提供 batch-audit。"""
    raise NotImplementedError("batch-audit 已退出当前主线")

@app.command()
def init_rules(
    source: str = typer.Argument(..., help="原始制度文件路径"),
    domain: str = typer.Argument(..., help="目标业务域"),
):
    """初始化规则：解析制度文件为结构化 JSON。"""
    prompt = f"/init-rules {source} {domain}"
    result = asyncio.run(run_agent_full(prompt))
    typer.echo(result)

@app.command()
def chat():
    """交互式对话模式。"""
    from server.chat import interactive_chat
    asyncio.run(interactive_chat())
```

### 10.4 `server/command_adapter.py` — 统一 Claude command 适配

当前主线已经移除 `server/chat.py`。Python 侧保留统一的 Claude command 调用适配层，CLI 与 HTTP 两端共享同一份能力入口。

---

## 11. 部署

### 11.1 环境依赖

```toml
# pyproject.toml
[project]
name = "enterprise-agent"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
    "claude-agent-sdk>=0.1.64",
    "fastapi>=0.115.0",
    "uvicorn>=0.30.0",
    "typer>=0.12.0",
]

[project.scripts]
agent-cli = "server.cli:app"
```

### 11.2 `.env`

```bash
ANTHROPIC_API_KEY=sk-ant-xxx          # 必须，SDK 和审核脚本都依赖
MAX_BUDGET_USD=1.0                     # 单次 agent 调用预算上限
TENANT_KEYS={"tenant_a":"sk-a","tenant_b":"sk-b"}
```

### 11.3 Dockerfile

Claude Agent SDK 依赖 Claude Code CLI，CLI 依赖 Node.js >= 18。基础镜像必须包含 Node.js，否则 SDK 起不来。

```dockerfile
FROM python:3.10-slim

# Claude Agent SDK 依赖 Node.js（Claude Code CLI 运行时需要）
RUN apt-get update && apt-get install -y curl \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir -e .

EXPOSE 8000
CMD ["uvicorn", "server.api:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 11.4 docker-compose.yml

```yaml
version: '3.8'
services:
  agent-server:
    build: .
    ports:
      - "8000:8000"
    env_file:
      - .env
    volumes:
      - ./.claude:/app/.claude            # 热更新 agent 定义
      - ./knowledge:/app/knowledge        # 热更新规则
      - ./output:/app/output              # 持久化结果
      - ./logs:/app/logs                  # 持久化日志
```

### 11.5 三种启动方式

```bash
# CLI 模式（运维）
agent-cli audit tests/fixtures/claims/EXP-001.json
agent-cli init-rules knowledge/external/数睿员工手册.pdf expense

# HTTP API 模式（外部系统对接）
uvicorn server.api:app --host 0.0.0.0 --port 8000

# Docker 启动
docker-compose up -d
```

---

## 12. 部署注意事项与已知限制

### 12.1 并发瓶颈

FastAPI 本身是异步的，但瓶颈不在 FastAPI 而在 Agent SDK。每次 `query()` 调用会 spawn 一个 Claude Code CLI 子进程，该子进程与 Anthropic API 通信、执行多轮 tool loop、读写文件。单个请求可能运行 30 秒到 5 分钟。实际并发上限取决于机器能同时跑多少个 CLI 子进程 × Anthropic API 的 rate limit。单机建议同时不超过 10-20 个 agent session。

### 12.2 不适合 Serverless

Agent SDK 底层是长时间运行的 CLI 子进程，需要读本地文件系统，执行时间可能超过分钟级。Lambda / Vercel 等 Serverless 平台的超时限制、临时存储、冷启动开销与 Agent SDK 的运行模型冲突。应使用 EC2 / ECS / 常驻容器等有状态的长运行实例。

### 12.3 Worker 模型选择

不推荐 Gunicorn 多 worker 模式。多 worker 意味着每个 worker 独立 spawn CLI 子进程，进程数翻倍但 API rate limit 是共享的，容易撞限。推荐单 worker + 异步并发，或 K8s 多 pod 每 pod 单 worker 的方式横向扩展。

### 12.4 场景定位

Agent SDK 的定位是中低频企业内部场景。报销审核这种一天几十到几百笔的场景完全匹配。不需要考虑万级 QPS。

---

## 13. 扩展路径

### 13.1 新增业务域

只需要两步，服务端代码零改动：

1. 在 `.claude/agents/{domain}/` 下添加新的 agent markdown 文件
2. 在 `knowledge/{domain}/` 下添加对应的 rules JSON 文件
3. 在 `CLAUDE.md` 路由表中添加新的意图关键词映射

Skill 层（rule-query, anomaly-detect, evidence-chain 等）跨域复用，无需改动。

### 13.2 租户隔离

当前 `TENANT_KEYS` 做简单 API Key 认证。后续可扩展为：per-tenant 的 `knowledge/` 目录（不同公司用不同报销政策），per-tenant 的 `max_budget_usd` 预算控制，per-tenant 的审计日志隔离。

### 13.3 前端集成

HTTP API 暴露后，可直接对接 Web UI（React + SSE 消费 `/chat/stream`）、钉钉/企微机器人（webhook → `/chat`）、移动 App 等。
