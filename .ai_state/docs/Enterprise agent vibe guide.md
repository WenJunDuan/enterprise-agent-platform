# 企业智能审核平台 — Vibe Coding 实施方案

> 本文档是完整的实施规范。AI 编码助手应按照本文档从 Step 0 开始逐步执行，每步验证通过后再进入下一步。

---

## 0. 技术栈与约束

### 0.1 技术选型

| 组件         | 选型                                   | 版本要求         |
| ------------ | -------------------------------------- | ---------------- |
| Agent 运行时 | Claude Agent SDK（Python）             | >= 0.1.48        |
| Python       | uv 管理                                | >= 3.12          |
| Node.js      | 系统安装（Agent SDK CLI 运行时依赖）   | >= 18            |
| HTTP API     | FastAPI + Uvicorn                      | FastAPI >= 0.115 |
| CLI          | Typer                                  | >= 0.12          |
| 第二模型审核 | Anthropic Python SDK（仅 hook 脚本用） | >= 0.52          |
| 容器化       | Docker + docker-compose                | -                |

### 0.2 绝对禁止

以下规则在整个项目中不可违反：

1. **Python 中禁止出现任何业务术语**：报销、发票、差旅、招待、考勤、审核、合规、规则、政策、阈值——这些概念只允许出现在 `.claude/` 的 markdown 文件和 `knowledge/` 的 JSON 文件中
2. **Python 中禁止出现业务分支**：不允许写 `if category == "travel"` 这种逻辑，业务路由由 CLAUDE.md 负责
3. **Python 只做三件事**：接请求/吐响应（HTTP/CLI/Chat 壳）、记日志（SDK 消息原样存储）、第二模型审核（hook 脚本，单次 API 调用）
4. **Agent 和 Skill 中禁止硬编码规则**：所有判定标准从 `knowledge/` 的 JSON 文件读取
5. **确定性保障用 hooks，不用工作流引擎**：hooks 是 Claude 原生机制，exit code 2 硬阻断，100% 触发

### 0.3 架构分层原则

| 层          | 目录              | 职责                     | 谁维护   |
| ----------- | ----------------- | ------------------------ | -------- |
| Claude 生态 | `.claude/`        | 调度、流程、能力、拦截   | 开发者   |
| 业务规则    | `knowledge/`      | 政策条款、阈值、审批标准 | 业务人员 |
| 接入壳      | `server/`         | HTTP/CLI/Chat + 日志     | 开发者   |
| 业务数据    | `data/` `output/` | 输入报销单、输出审核结果 | 系统自动 |

### 0.4 确定性 vs 概率性

| 构件      | 性质                                       | 含义     |
| --------- | ------------------------------------------ | -------- |
| CLAUDE.md | 确定性（每次加载）                         | 全局指令 |
| Agents    | 概率性（Claude 根据 description 判断调用） | 子代理   |
| Skills    | 概率性（Claude 自主判断触发）              | 能力模块 |
| Hooks     | **确定性（每次执行，零例外）**             | 拦截审计 |

关键推论：审核拦截、完整性检查必须用 hook。

### 0.5 Agent SDK 运行机制

调用 `query()` 时，SDK spawn Claude Code CLI 子进程（Node.js），通过 stdin/stdout JSON-lines 通信。CLI 自动读取 `{cwd}/.claude/` 目录的全部配置。Python 代码从不直接调 Anthropic API（hook 脚本除外）。

必须在 options 中设置 `setting_sources=["project"]`，否则 SDK 不读 `.claude/` 目录。

---

## 1. 目录结构

```
enterprise-agent/
│
├── .claude/                              # ===== Claude 生态 =====
│   ├── CLAUDE.md                         # 调度中枢（纯路由，不含业务规则）
│   ├── settings.json                     # hooks 配置 + 权限
│   │
│   ├── commands/                         # slash commands（运维用）
│   │   ├── init-rules.md                 # /init-rules 原始制度→结构化JSON
│   │   ├── audit.md                      # /audit 提交审核
│   │   └── batch-audit.md                # /batch-audit 批量审核
│   │
│   ├── agents/                           # 业务域 agents
│   │   ├── expense/
│   │   │   ├── extractor.md              # 数据提取
│   │   │   ├── auditor.md                # 合规审核（核心）
│   │   │   └── reviewer.md               # 交叉复核
│   │   ├── hr/
│   │   │   ├── attendance-checker.md
│   │   │   └── leave-auditor.md
│   │   └── legal/
│   │       └── contract-reviewer.md
│   │
│   ├── skills/                           # 原子能力（跨域复用）
│   │   ├── rule-init/SKILL.md            # 解析原始制度→JSON
│   │   ├── rule-query/SKILL.md           # 读取匹配规则
│   │   ├── invoice-parse/SKILL.md        # 发票解析校验
│   │   ├── pre-approval-match/SKILL.md   # 事前↔事后匹配
│   │   ├── travel-compliance/SKILL.md    # 出差全链路合规
│   │   ├── entertainment-compliance/SKILL.md  # 招待合规
│   │   ├── budget-check/SKILL.md         # 预算额度校验
│   │   ├── amount-validate/SKILL.md      # 金额合理性
│   │   ├── anomaly-detect/SKILL.md       # 异常模式识别
│   │   ├── evidence-chain/SKILL.md       # 证据链构建
│   │   └── result-format/SKILL.md        # 标准化输出
│   │
│   └── hooks/                            # hook 脚本
│       ├── review-output.py              # PostToolUse：第二模型审核
│       └── check-before-write.py         # PreToolUse：写入前完整性检查
│
├── knowledge/                            # ===== 业务规则 =====
│   ├── _schema/
│   │   └── rule.schema.json              # 统一规则 schema
│   ├── expense/
│   │   ├── travel.rules.json
│   │   ├── meal.rules.json
│   │   ├── entertainment.rules.json
│   │   ├── invoice.rules.json
│   │   ├── office.rules.json
│   │   ├── thresholds.json
│   │   └── budget-limits.json
│   ├── hr/
│   │   ├── attendance.rules.json
│   │   └── leave.rules.json
│   └── legal/
│       └── contract.rules.json
│
├── data/                                 # ===== 业务数据输入 =====
│   ├── claims/                           # 报销单
│   ├── invoices/                         # 发票
│   └── pre-approvals/                    # 事前申请单
│
├── output/results/                       # ===== 审核结果输出 =====
│
├── logs/sessions/                        # ===== 会话日志(JSONL) =====
│
├── server/                               # ===== 接入壳 =====
│   ├── __init__.py
│   ├── core.py                           # SDK 调用 + 日志（唯一核心）
│   ├── api.py                            # HTTP API（FastAPI + SSE）
│   ├── cli.py                            # CLI（Typer）
│   └── chat.py                           # 交互式 Chat REPL
│
├── .env
├── .env.example
├── .gitignore
├── pyproject.toml
├── Dockerfile
└── docker-compose.yml
```

---

## 2. 分步实施

### Step 1：项目初始化

```bash
mkdir enterprise-agent && cd enterprise-agent

uv init --no-readme
uv python pin 3.12

uv add claude-agent-sdk anthropic fastapi uvicorn typer
uv add --dev pytest ruff

# 验证
uv run python -c "from claude_agent_sdk import query; print('SDK OK')"
node --version  # 必须 >= 18
```

创建目录骨架：

```bash
mkdir -p .claude/{commands,agents/expense,agents/hr,agents/legal,skills/{rule-init,rule-query,invoice-parse,pre-approval-match,travel-compliance,entertainment-compliance,budget-check,amount-validate,anomaly-detect,evidence-chain,result-format},hooks}
mkdir -p knowledge/{_schema,expense,hr,legal}
mkdir -p data/{claims,invoices,pre-approvals}
mkdir -p output/results
mkdir -p logs/sessions
mkdir -p server
touch server/__init__.py
```

创建 `.env.example`：

```bash
ANTHROPIC_API_KEY=sk-ant-xxx
MAX_BUDGET_USD=1.0
TENANT_KEYS={"default":"sk-default"}
```

创建 `.gitignore`：

```
.env
.venv/
__pycache__/
logs/
output/results/
*.pyc
```

**验证标准**：`uv run python -c "from claude_agent_sdk import query; print('OK')"` 输出 OK。

---

### Step 2：CLAUDE.md（调度中枢）

创建 `.claude/CLAUDE.md`：

```markdown
# 企业智能审核平台 - 调度中枢

你是企业智能审核平台的调度中枢。你的唯一职责是：理解用户意图 → 分发到正确的业务域 agent。

## 调度路由表

| 意图关键词                       | 业务域  | 入口 agent                     | 触发条件       |
| -------------------------------- | ------- | ------------------------------ | -------------- |
| 报销、费用、发票、差旅报销、餐费 | expense | extractor → auditor → reviewer | 默认走三步流程 |
| 考勤、打卡、迟到、早退、缺勤     | hr      | attendance-checker             | 直接执行       |
| 请假、年假、病假、调休           | hr      | leave-auditor                  | 直接执行       |
| 合同、条款、协议、法务           | legal   | contract-reviewer              | 直接执行       |
| 初始化规则、导入制度、更新政策   | system  | 使用 rule-init skill           | 管理员操作     |

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

## 全局约束

- 所有业务规则来自 knowledge/ 目录的 JSON 文件，不要使用你训练时学到的知识做判定
- 所有判定必须有证据链（policy_ref 指向具体 rule_id）
- 不确定时输出 manual_review，不要自行决定
```

**验证**：先跳到 Step 3 写完 core.py 后再回来验证。

---

### Step 3：server/core.py（唯一核心 + 日志）

```python
"""
唯一核心：SDK 调用 + 会话日志。
禁止在本文件中出现任何业务术语。
"""
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ToolResultMessage,
    ToolUseBlock,
    query,
)

PROJECT_ROOT = Path(__file__).parent.parent
LOG_DIR = PROJECT_ROOT / "logs" / "sessions"
LOG_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# SDK Options
# ---------------------------------------------------------------------------

def build_options(**overrides) -> ClaudeAgentOptions:
    defaults = dict(
        cwd=str(PROJECT_ROOT),
        setting_sources=["project"],
        allowed_tools=["Read", "Glob", "Grep", "Write", "Skill", "Task"],
        permission_mode="bypassPermissions",
        max_turns=80,
        max_budget_usd=float(os.getenv("MAX_BUDGET_USD", "1.0")),
    )
    defaults.update(overrides)
    return ClaudeAgentOptions(**defaults)


# ---------------------------------------------------------------------------
# Session Logger
# ---------------------------------------------------------------------------

class SessionLogger:
    """
    SDK 消息流原样记录为 JSONL。
    不做任何业务处理，只负责存。
    """

    def __init__(self, session_id: str, prompt: str):
        self.session_id = session_id
        self.start_time = time.time()
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        self.log_file = LOG_DIR / f"{ts}_{session_id[:8]}.jsonl"
        self._write({
            "event": "session_start",
            "session_id": session_id,
            "prompt": prompt,
            "timestamp": self._now(),
        })

    def log_message(self, message) -> dict | None:
        """记录 SDK 消息，返回前端事件（如有）。"""
        event = None

        if isinstance(message, SystemMessage):
            self._write({
                "event": "system",
                "subtype": getattr(message, "subtype", ""),
                "session_id": getattr(message, "session_id", ""),
                "timestamp": self._now(),
            })

        elif isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    event = {"type": "text", "content": block.text}
                    self._write({
                        "event": "assistant_text",
                        "content": block.text,
                        "timestamp": self._now(),
                    })
                elif isinstance(block, ToolUseBlock):
                    self._write({
                        "event": "tool_call",
                        "tool": block.name,
                        "input": str(block.input)[:500],
                        "timestamp": self._now(),
                    })

        elif isinstance(message, ToolResultMessage):
            self._write({
                "event": "tool_result",
                "content": str(getattr(message, "content", ""))[:500],
                "timestamp": self._now(),
            })

        elif isinstance(message, ResultMessage):
            elapsed = time.time() - self.start_time
            event = {
                "type": "result",
                "content": message.result or "",
                "cost": getattr(message, "total_cost_usd", 0),
            }
            self._write({
                "event": "session_end",
                "subtype": getattr(message, "subtype", ""),
                "cost_usd": getattr(message, "total_cost_usd", 0),
                "duration_sec": round(elapsed, 2),
                "timestamp": self._now(),
            })

        return event

    def _write(self, record: dict):
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Agent Entry Points
# ---------------------------------------------------------------------------

async def run_agent(
    prompt: str,
    session_id: str | None = None,
    **opts,
) -> AsyncIterator[dict]:
    """统一入口：SDK 跑业务，Python 只记日志和转发。"""
    sid = session_id or str(uuid.uuid4())
    logger = SessionLogger(sid, prompt)
    options = build_options(**opts)

    if session_id:
        options.session_id = session_id

    async for message in query(prompt=prompt, options=options):
        event = logger.log_message(message)
        if event:
            yield event


async def run_agent_full(prompt: str, **opts) -> str:
    """非流式：收集完整结果。"""
    chunks = []
    async for event in run_agent(prompt, **opts):
        if event["type"] in ("text", "result"):
            chunks.append(event["content"])
    return "\n".join(filter(None, chunks))
```

---

### Step 4：server/cli.py

```python
"""CLI 入口。禁止业务术语。"""
import asyncio
import json

import typer

from server.core import run_agent, run_agent_full

app = typer.Typer(help="Enterprise Agent CLI")


@app.command()
def ask(prompt: str = typer.Argument(..., help="提问内容")):
    """单次提问。"""
    result = asyncio.run(run_agent_full(prompt))
    typer.echo(result)


@app.command()
def audit(file: str = typer.Argument(..., help="待审核文件路径")):
    """审核单个文件。"""
    result = asyncio.run(run_agent_full(f"审核文件: {file}"))
    typer.echo(result)


@app.command()
def init_rules(
    source: str = typer.Argument(..., help="原始制度文件路径"),
    domain: str = typer.Argument(..., help="目标业务域"),
):
    """解析制度文件为结构化 JSON 规则。"""
    result = asyncio.run(run_agent_full(f"/init-rules {source} {domain}"))
    typer.echo(result)


@app.command()
def chat():
    """交互式对话。"""
    from server.chat import interactive_chat

    asyncio.run(interactive_chat())


if __name__ == "__main__":
    app()
```

---

### Step 5：server/chat.py

```python
"""交互式 Chat REPL。禁止业务术语。"""
import uuid

from server.core import run_agent


async def interactive_chat():
    session_id = str(uuid.uuid4())
    print(f"Agent 交互模式 (session: {session_id[:8]}...)")
    print("输入 /quit 退出\n")

    while True:
        try:
            user_input = input("你> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if user_input in ("/quit", "/exit", ""):
            break

        async for event in run_agent(user_input, session_id=session_id):
            if event["type"] == "text":
                print(f"Agent> {event['content']}")
            elif event["type"] == "result":
                print(f"[完成] {event['content']}")
        print()
```

---

### Step 6：server/api.py

```python
"""HTTP API。禁止业务术语。"""
import json
import os

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from server.core import run_agent

app = FastAPI(title="Enterprise Agent API", version="0.1.0")

TENANT_KEYS: dict = json.loads(
    os.getenv("TENANT_KEYS", '{"default": "sk-default"}')
)


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class ChatResponse(BaseModel):
    tenant: str
    response: str
    cost: float


def _verify_tenant(api_key: str) -> str:
    key = api_key.replace("Bearer ", "")
    for tenant, k in TENANT_KEYS.items():
        if k == key:
            return tenant
    raise HTTPException(401, "Invalid API key")


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, authorization: str = Header(...)):
    """非流式 JSON 响应。"""
    tenant = _verify_tenant(authorization)
    parts: list[str] = []
    cost = 0.0
    async for event in run_agent(req.message, session_id=req.session_id):
        if event["type"] == "text":
            parts.append(event["content"])
        elif event["type"] == "result":
            cost = event.get("cost", 0)
    return ChatResponse(tenant=tenant, response="\n".join(parts), cost=cost)


@app.post("/chat/stream")
async def chat_stream(req: ChatRequest, authorization: str = Header(...)):
    """SSE 流式响应。"""
    _verify_tenant(authorization)

    async def generate():
        async for event in run_agent(req.message, session_id=req.session_id):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.get("/health")
async def health():
    return {"status": "ok"}
```

**Step 2-6 验证**：

```bash
export ANTHROPIC_API_KEY=sk-ant-xxx

# 验证 CLI + CLAUDE.md 加载
uv run python -m server.cli ask "你是谁？你能做什么？简短回答。"
# 期望输出提到"企业智能审核平台"和"调度中枢"

# 验证 Chat 模式
uv run python -m server.cli chat

# 验证 HTTP API
uv run uvicorn server.api:app --host 127.0.0.1 --port 8000 &
curl -X POST http://127.0.0.1:8000/chat \
  -H "Authorization: Bearer sk-default" \
  -H "Content-Type: application/json" \
  -d '{"message":"你是什么系统？"}'
# 期望返回 JSON 包含"调度中枢"

# 验证日志生成
ls logs/sessions/
# 应该有 .jsonl 文件
```

---

### Step 7：knowledge/ 规则 JSON

#### 7.1 统一 Schema `knowledge/_schema/rule.schema.json`

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["domain", "category", "version", "rules"],
  "properties": {
    "domain": { "type": "string", "enum": ["expense", "hr", "legal"] },
    "category": { "type": "string" },
    "version": { "type": "string" },
    "effective_date": { "type": "string", "format": "date" },
    "rules": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["rule_id", "description", "conditions", "action"],
        "properties": {
          "rule_id": { "type": "string" },
          "description": { "type": "string" },
          "conditions": {
            "type": "object",
            "properties": {
              "max_amount": { "type": "number" },
              "frequency_limit": {
                "type": "object",
                "properties": {
                  "count": { "type": "integer" },
                  "period": {
                    "type": "string",
                    "enum": ["daily", "weekly", "monthly", "yearly"]
                  }
                }
              },
              "required_docs": {
                "type": "array",
                "items": { "type": "string" }
              },
              "approval_level": { "type": "string" },
              "applicable_roles": {
                "type": "array",
                "items": { "type": "string" }
              }
            }
          },
          "action": {
            "type": "string",
            "enum": ["approve", "reject", "escalate"]
          },
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

#### 7.2 差旅规则 `knowledge/expense/travel.rules.json`

```json
{
  "domain": "expense",
  "category": "travel",
  "version": "2024-v3",
  "effective_date": "2024-01-01",
  "rules": [
    {
      "rule_id": "expense.travel.001",
      "description": "出差须事前提交出差申请并获审批，事后补申请不予受理",
      "conditions": { "required_docs": ["出差申请单"] },
      "action": "reject",
      "priority": 1,
      "confidence": "high",
      "original_text": "员工出差须事前填写出差申请单，经部门负责人审批后方可出行。未经事前审批的出差费用不予报销。"
    },
    {
      "rule_id": "expense.travel.002",
      "description": "交通方式标准：普通员工火车/高铁二等座，经理级可高铁一等座，总监及以上可商务舱",
      "conditions": {
        "applicable_roles": ["staff"],
        "required_docs": ["交通票据"]
      },
      "action": "reject",
      "priority": 1,
      "confidence": "high",
      "original_text": "普通员工出差乘坐火车硬卧或高铁二等座；部门经理可乘坐高铁一等座；总监及以上可乘坐飞机经济舱或商务舱。"
    },
    {
      "rule_id": "expense.travel.003",
      "description": "住宿标准：普通员工每晚不超过500元，经理级不超过800元，总监及以上不超过1200元",
      "conditions": {
        "max_amount": 500,
        "applicable_roles": ["staff"],
        "required_docs": ["住宿发票", "行程单"]
      },
      "action": "reject",
      "priority": 1,
      "confidence": "high",
      "original_text": "普通员工出差住宿费每晚报销上限为500元人民币，需提供住宿发票及行程单。"
    },
    {
      "rule_id": "expense.travel.004",
      "description": "出差补贴：一线城市每天150元，二线城市每天100元，其他城市每天80元",
      "conditions": {
        "max_amount": 150,
        "frequency_limit": { "count": 1, "period": "daily" }
      },
      "action": "reject",
      "priority": 2,
      "confidence": "high",
      "original_text": "出差期间按目的地城市等级发放餐饮补贴，一线城市150元/天，二线城市100元/天，其他城市80元/天。"
    },
    {
      "rule_id": "expense.travel.005",
      "description": "同城出差不允许报销住宿费",
      "conditions": {},
      "action": "reject",
      "priority": 1,
      "confidence": "high",
      "original_text": "在工作所在城市内的公务活动不得报销住宿费用。"
    }
  ]
}
```

#### 7.3 招待费规则 `knowledge/expense/entertainment.rules.json`

```json
{
  "domain": "expense",
  "category": "entertainment",
  "version": "2024-v2",
  "effective_date": "2024-06-01",
  "rules": [
    {
      "rule_id": "expense.entertainment.001",
      "description": "业务招待须事前提交招待申请并获部门负责人审批",
      "conditions": {
        "required_docs": ["招待申请单", "消费明细", "参与人员名单"]
      },
      "action": "reject",
      "priority": 1,
      "confidence": "high",
      "original_text": "业务招待须事前填写《招待申请单》，经部门负责人审批后方可执行。"
    },
    {
      "rule_id": "expense.entertainment.002",
      "description": "招待标准：普通客户人均不超过200元，重要客户人均不超过500元",
      "conditions": {
        "max_amount": 200,
        "applicable_roles": ["normal_client"],
        "frequency_limit": { "count": 3, "period": "monthly" }
      },
      "action": "reject",
      "priority": 1,
      "confidence": "high",
      "original_text": "普通客户招待标准为人均200元以内，每月同一客户招待不超过3次。"
    },
    {
      "rule_id": "expense.entertainment.003",
      "description": "公司陪餐人员与客户人数比例不得超过1:1",
      "conditions": { "max_company_ratio": 1.0 },
      "action": "reject",
      "priority": 2,
      "confidence": "high",
      "original_text": "招待用餐时，公司参与人员人数不得超过受邀客户人数。"
    },
    {
      "rule_id": "expense.entertainment.004",
      "description": "禁止在高档会所、KTV、高尔夫球场等场所进行业务招待",
      "conditions": {
        "venue_blacklist": ["KTV", "高尔夫", "会所", "夜总会", "足浴"]
      },
      "action": "reject",
      "priority": 1,
      "confidence": "high",
      "original_text": "严禁在高消费娱乐场所进行业务招待活动。"
    },
    {
      "rule_id": "expense.entertainment.005",
      "description": "酒水费用不得超过餐费总额的30%",
      "conditions": { "max_alcohol_ratio": 0.3 },
      "action": "escalate",
      "priority": 2,
      "confidence": "medium",
      "original_text": "招待用餐中酒水消费应控制在合理范围内。",
      "notes": "原文'合理范围'较模糊，参照行业惯例设定30%，confidence标记medium"
    }
  ]
}
```

#### 7.4 发票规则 `knowledge/expense/invoice.rules.json`

```json
{
  "domain": "expense",
  "category": "invoice",
  "version": "2024-v1",
  "effective_date": "2024-01-01",
  "rules": [
    {
      "rule_id": "expense.invoice.001",
      "description": "发票抬头必须为公司注册全称",
      "conditions": { "buyer_name": "本公司注册全称" },
      "action": "reject",
      "priority": 1,
      "confidence": "high",
      "original_text": "报销发票抬头须与公司工商注册名称完全一致。"
    },
    {
      "rule_id": "expense.invoice.002",
      "description": "发票开具日期距报销提交日不得超过90天",
      "conditions": { "max_age_days": 90 },
      "action": "reject",
      "priority": 1,
      "confidence": "high",
      "original_text": "发票开具日期距报销申请提交日超过90天的不予报销。"
    },
    {
      "rule_id": "expense.invoice.003",
      "description": "不接受手写发票和收据（定额发票除外）",
      "conditions": { "disallowed_types": ["手写发票", "白条", "收据"] },
      "action": "reject",
      "priority": 1,
      "confidence": "high",
      "original_text": "报销凭证须为正规税务发票，手写发票及白条不予受理（定额发票除外）。"
    }
  ]
}
```

#### 7.5 审批阈值 `knowledge/expense/thresholds.json`

```json
{
  "approval_levels": {
    "auto_approve": { "max_amount": 500, "description": "500元以下自动审批" },
    "manager": { "max_amount": 5000, "description": "5000元以下部门经理审批" },
    "director": { "max_amount": 20000, "description": "20000元以下总监审批" },
    "cfo": { "max_amount": 999999, "description": "20000元以上CFO审批" }
  },
  "deviation_tolerance": {
    "amount_pct": 10,
    "description": "事后报销金额超出事前申请10%以内可接受，超出需说明原因"
  },
  "high_risk_threshold": {
    "amount": 5000,
    "description": "超过5000元触发交叉复核"
  }
}
```

**验证**：

```bash
uv run python -m server.cli ask "查一下差旅住宿标准是多少"
# 期望 Claude 读取 knowledge/expense/travel.rules.json 并回答"普通员工每晚500元"
```

---

### Step 8：Skills

每个 skill 是 `.claude/skills/{name}/SKILL.md` 文件。

#### 8.1 rule-query

```markdown
---
name: rule-query
description: 根据业务域和类别从knowledge/目录读取适用的JSON规则，支持按条件筛选匹配
---

# 规则查询

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

#### 8.2 rule-init

```markdown
---
name: rule-init
description: 解析企业原始制度文件（PDF/DOCX/TXT），提取结构化规则并按统一schema输出JSON
---

# 规则初始化

## 触发条件

当需要将原始制度文件转换为结构化 JSON 规则时使用。

## 执行步骤

1. 读取原始制度文件内容
2. 读取 knowledge/\_schema/rule.schema.json 获取目标格式
3. 从文件中提取每一条可执行的规则，转换为 schema 定义的 JSON 结构
4. 对模糊表述标记 confidence: "low"，并在 notes 中说明歧义点

## 提取原则

- 每条独立可执行的规定 = 一条 rule
- "不超过XXX元" → max_amount 字段
- "需提供XXX" → required_docs 数组
- "经XXX审批" → approval_level 字段
- "每月不超过X次" → frequency_limit 对象
- 模糊表述如"合理范围内" → confidence: "low"，保留原文在 original_text

## 输出

严格遵循 knowledge/\_schema/rule.schema.json，不要自行发明字段。
```

#### 8.3 invoice-parse

```markdown
---
name: invoice-parse
description: 解析上传的发票或收据，提取结构化字段并校验发票基本合规性（抬头、税号、日期、金额）
---

# 发票解析与校验

## 触发条件

当收到发票文件需要提取结构化数据并做基础校验时使用。

## 执行步骤

1. 读取 data/invoices/ 下的发票文件
2. 提取字段：invoice_no, invoice_type, seller, buyer, buyer_tax_no, amount, tax, total, date, items
3. 读取 knowledge/expense/invoice.rules.json 获取校验规则
4. 基础校验：抬头匹配、税号正确、开票日期有效期内、发票类型允许、金额算术一致

## 输出

{
"invoice_no": "",
"parsed_data": {},
"validations": [
{"check": "buyer_match", "pass": true/false, "detail": ""}
],
"overall_valid": true/false
}

## 注意

本 skill 不判定费用是否合规（那是 auditor 的事），只负责发票形式校验。
```

#### 8.4 pre-approval-match

```markdown
---
name: pre-approval-match
description: 将事后报销单与事前审批单（出差/招待申请）进行交叉匹配，检测偏差并判定是否在允许范围内
---

# 事前审批↔事后报销匹配

## 触发条件

当报销单关联了事前审批单号时使用。

## 执行步骤

1. 从报销单提取 pre_approval_id
2. 读取 data/pre-approvals/{pre_approval_id}.json
3. 读取 knowledge/expense/thresholds.json 获取偏差容忍范围
4. 逐维度比对：金额、日期、目的地、同行人、费用类目
5. 判定：无偏差→pass，偏差在范围内→pass_with_note，超出→deviation

## 输出

{
"pre_approval_id": "",
"match_result": "full_match | partial_match | mismatch | no_approval",
"deviations": [],
"requires_explanation": true/false
}
```

#### 8.5 travel-compliance

```markdown
---
name: travel-compliance
description: 综合校验出差报销全流程合规性：事前申请→行程→住宿→交通→补贴的完整链路
---

# 出差合规校验

## 触发条件

当报销类别为差旅且需要全链路合规判定时使用。

## 执行步骤

1. 读取 knowledge/expense/travel.rules.json
2. 校验维度：
   - 事前申请（调用 pre-approval-match skill）
   - 行程合规（天数/目的地与申请一致）
   - 住宿标准（按职级匹配上限，同城不允许住宿）
   - 交通标准（按职级匹配交通方式）
   - 出差补贴（天数/城市等级标准）

## 输出

{
"checks": [
{"category": "pre_approval", "pass": true/false, "detail": ""},
{"category": "itinerary", "pass": true/false, "detail": ""},
{"category": "lodging", "pass": true/false, "detail": ""},
{"category": "transport", "pass": true/false, "detail": ""},
{"category": "allowance", "pass": true/false, "detail": ""}
],
"overall": "compliant | non_compliant | needs_review"
}
```

#### 8.6 entertainment-compliance

```markdown
---
name: entertainment-compliance
description: 校验招待费报销合规性：事前审批、招待标准、陪餐比例、频次限制、场所黑名单
---

# 招待费合规校验

## 触发条件

当报销类别为业务招待时使用。

## 执行步骤

1. 读取 knowledge/expense/entertainment.rules.json
2. 校验维度：
   - 事前审批（调用 pre-approval-match skill）
   - 人均标准（按客户级别区分）
   - 酒水占比（不超过30%）
   - 场所黑名单（KTV、会所等）
   - 陪餐比例（公司人员≤客户人数）
   - 月度频次（同一客户≤3次）
   - 附件完整性（申请单+明细+人员名单）

## 输出

{
"checks": [
{"category": "pre_approval", "pass": true/false, "detail": ""},
{"category": "standard", "pass": true/false, "detail": ""},
{"category": "ratio_frequency", "pass": true/false, "detail": ""},
{"category": "attachments", "pass": true/false, "detail": ""}
],
"overall": "compliant | non_compliant | needs_review"
}
```

#### 8.7 budget-check

```markdown
---
name: budget-check
description: 校验本次费用是否超出部门/项目/个人预算额度
---

# 预算额度校验

## 触发条件

当需要判断费用是否超预算时使用。

## 执行步骤

1. 读取 knowledge/expense/budget-limits.json
2. 确定预算维度（部门/项目/个人）
3. 计算已使用预算（读取 output/results/ 中已审批记录）
4. 计算本次金额占剩余预算比例

## 输出

{
"budget_scope": "department | project | personal",
"total_budget": 0,
"used_budget": 0,
"this_claim": 0,
"remaining_after": 0,
"over_budget": false
}
```

#### 8.8 amount-validate

```markdown
---
name: amount-validate
description: 校验报销金额是否在政策允许范围内，读取knowledge中的阈值JSON比对
---

# 金额合理性校验

## 执行步骤

1. 读取 knowledge/{domain}/thresholds.json
2. 比对提交金额与角色/类别上限
3. 超出阈值时返回需要的审批级别

## 输出

{ "within_limit": true/false, "threshold": 0, "required_approval": "" }
```

#### 8.9 anomaly-detect

```markdown
---
name: anomaly-detect
description: 识别业务数据中的异常模式：频率异常、时间异常、金额异常，跨域通用
---

# 异常模式识别

## 检测维度

- 频率异常：短时间内重复提交类似项目
- 时间异常：周末/节假日大额消费
- 金额异常：远超同类别历史均值
- 模式异常：连续多日相同金额

## 输出

{ "anomalies": [{"type": "", "detail": "", "severity": "low|medium|high"}] }
```

#### 8.10 evidence-chain

```markdown
---
name: evidence-chain
description: 将审核过程中所有判定依据组装为完整审计证据链
---

# 证据链构建

## 证据结构

每条：source(rule_id/数据字段/异常检测) + finding + conclusion(comply/violate/inconclusive)

## 输出

有序证据数组，按逻辑推理顺序排列。
```

#### 8.11 result-format

```markdown
---
name: result-format
description: 将审核结果标准化为统一JSON格式输出到output/results/
---

# 标准化输出

## 输出格式

写入 output/results/{claim_id}\_result.json：
{
"claim_id": "",
"verdict": "approved | rejected | manual_review",
"reasons": [],
"policy_refs": [],
"risk_score": 0-100,
"extracted_data": {},
"evidence_chain": [],
"timestamp": ""
}
```

**验证**：

```bash
uv run python -m server.cli ask "你有哪些 skills？列出来"
# 期望列出上述所有 skill 名称
```

---

### Step 9：Agents

#### 9.1 expense/extractor.md

```markdown
---
name: extractor
description: 从报销单原始数据中提取结构化字段：金额、日期、类别、发票号、申请人
tools: Read, Glob
model: haiku
---

你是报销单数据提取专员。

读取 data/claims/ 下的报销单文件，提取字段：

- claim_id, applicant, amount, category, date, invoice_no, description, attachments, pre_approval_id

输出纯 JSON，不要解释。
```

#### 9.2 expense/auditor.md

```markdown
---
name: expense-auditor
description: 费控综合审核agent。根据报销类别调度不同skill组合完成全流程合规判定。不含任何业务规则。
tools: Read, Glob, Skill, Task
skills:
  - rule-query
  - invoice-parse
  - pre-approval-match
  - travel-compliance
  - entertainment-compliance
  - budget-check
  - amount-validate
  - anomaly-detect
  - evidence-chain
  - result-format
---

你是费控综合审核员。你不知道任何报销政策——所有规则通过 skill 从 knowledge/ 动态获取。

## 审核流程（按报销类别分支）

### 通用步骤（所有类别都执行）

1. 使用 invoice-parse skill 校验所有发票的形式合规性
2. 使用 budget-check skill 校验预算额度
3. 使用 anomaly-detect skill 检查异常模式

### 差旅报销

4. 使用 pre-approval-match skill 比对出差申请
5. 使用 travel-compliance skill 做全链路合规校验
6. 使用 amount-validate skill 逐项金额校验

### 招待报销

4. 使用 pre-approval-match skill 比对招待申请
5. 使用 entertainment-compliance skill 做招待合规校验

### 普通报销（办公用品、交通等）

4. 使用 rule-query skill 获取对应类别规则
5. 使用 amount-validate skill 金额校验

### 汇总

6. 使用 evidence-chain skill 组装完整证据链
7. 使用 result-format skill 输出标准化结果写入 output/results/

## 判定逻辑

- 所有 skill 返回 pass → approved
- 任一 skill 返回 fail → rejected
- 存在 deviation/needs_review/missing_approval → manual_review

## 禁止事项

- 禁止用训练知识判定
- 禁止编造规则
- 无事前申请时标记 manual_review，不要自行放行
```

#### 9.3 expense/reviewer.md

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

1. 不看 auditor 结论，自己独立审核一遍
2. 对比你的结论和 auditor 的结论
3. 一致则确认，不一致则输出分歧点并标记 manual_review

输出：
{
"reviewer_verdict": "",
"agrees_with_auditor": true/false,
"discrepancies": [],
"final_recommendation": ""
}
```

---

### Step 10：Hooks

#### 10.1 `.claude/settings.json`

```json
{
  "permissions": {
    "allow": ["Read", "Glob", "Grep", "Skill", "Task", "Write"],
    "deny": ["Bash"]
  },
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Write",
        "hooks": [
          {
            "type": "command",
            "command": "python .claude/hooks/check-before-write.py"
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Write",
        "hooks": [
          {
            "type": "command",
            "command": "python .claude/hooks/review-output.py"
          }
        ]
      }
    ]
  }
}
```

#### 10.2 `.claude/hooks/check-before-write.py`

```python
#!/usr/bin/env python3
"""
PreToolUse hook：写入审核结果前检查完整性。
确保 Claude 没有跳过关键步骤。
exit(0) = 放行, exit(2) = 阻断并反馈原因。
"""
import json
import sys

hook_input = json.load(sys.stdin)

file_path = hook_input.get("tool_input", {}).get("file_path", "")
if "output/results/" not in file_path:
    sys.exit(0)

content = hook_input.get("tool_input", {}).get("content", "")
try:
    result = json.loads(content)
except (json.JSONDecodeError, TypeError):
    print(json.dumps({"error": "输出不是有效 JSON，请用 result-format skill 格式化"}))
    sys.exit(2)

required_fields = ["claim_id", "verdict", "reasons", "policy_refs", "evidence_chain"]
missing = [f for f in required_fields if f not in result or not result[f]]

if missing:
    print(json.dumps({
        "error": f"审核结果缺少必要字段: {', '.join(missing)}。请确保已执行所有审核步骤并使用 evidence-chain + result-format skill。"
    }))
    sys.exit(2)

if result.get("verdict") == "approved" and not result.get("policy_refs"):
    print(json.dumps({
        "error": "判定为 approved 但没有引用任何政策条款(policy_refs 为空)。请使用 rule-query skill 获取适用规则。"
    }))
    sys.exit(2)

sys.exit(0)
```

#### 10.3 `.claude/hooks/review-output.py`

```python
#!/usr/bin/env python3
"""
PostToolUse hook：第二模型审核 agent 的输出内容。
exit(0) = 放行, exit(2) = 阻断。
"""
import json
import sys

from anthropic import Anthropic

hook_input = json.load(sys.stdin)

file_path = hook_input.get("tool_input", {}).get("file_path", "")
if "output/results/" not in file_path:
    sys.exit(0)

content = hook_input.get("tool_input", {}).get("content", "")

client = Anthropic()
response = client.messages.create(
    model="claude-haiku-4-5-20251001",
    max_tokens=500,
    messages=[{
        "role": "user",
        "content": f"""审核以下输出的质量：
1. 是否包含敏感个人信息泄露（身份证号、银行卡号等）
2. 判定理由是否引用了政策条款
3. 是否存在逻辑矛盾

输出内容：
{content}

只回答 PASS 或 BLOCK:原因"""
    }],
)

result = response.content[0].text.strip()
if result.startswith("BLOCK"):
    print(json.dumps({"error": f"输出审核未通过: {result}"}))
    sys.exit(2)

sys.exit(0)
```

---

### Step 11：Slash Commands

#### 11.1 `.claude/commands/init-rules.md`

```markdown
---
description: 将原始制度文件解析为结构化 JSON 规则
allowed-tools: Read, Write, Glob, Skill
---

用户提供原始制度文件路径和目标业务域。
使用 rule-init skill 解析，按 knowledge/\_schema/rule.schema.json 输出，写入 knowledge/{domain}/。
输出解析报告：提取规则数量、需人工确认的模糊条款。

参数: $ARGUMENTS
用法: /init-rules raw_policies/差旅管理办法.pdf expense
```

#### 11.2 `.claude/commands/audit.md`

```markdown
---
description: 审核单个报销单
allowed-tools: Read, Write, Glob, Skill, Task
---

读取指定报销单文件，调度 extractor → auditor 流程，高风险自动触发 reviewer。
结果写入 output/results/。

参数: $ARGUMENTS
用法: /audit data/claims/EXP-2024-0312.json
```

---

### Step 12：测试数据

#### 12.1 `data/pre-approvals/PA-2024-0157.json`

```json
{
  "approval_id": "PA-2024-0157",
  "type": "travel",
  "applicant": {
    "id": "EMP-0042",
    "name": "张三",
    "department": "销售部",
    "role": "staff"
  },
  "status": "approved",
  "approved_by": "李四",
  "approved_at": "2024-10-15T09:30:00",
  "details": {
    "purpose": "拜访深圳客户ABC科技",
    "destination": "深圳",
    "planned_dates": ["2024-10-20", "2024-10-21", "2024-10-22"],
    "planned_participants": ["张三"],
    "approved_categories": ["交通", "住宿", "市内交通", "餐补"],
    "approved_amount": 5000,
    "budget_source": "销售部Q4差旅预算"
  }
}
```

#### 12.2 `data/claims/EXP-2024-0312.json`

```json
{
  "claim_id": "EXP-2024-0312",
  "pre_approval_id": "PA-2024-0157",
  "applicant_id": "EMP-0042",
  "submit_date": "2024-10-25",
  "category": "travel",
  "items": [
    {
      "type": "交通",
      "description": "北京→深圳 高铁二等座",
      "amount": 950,
      "date": "2024-10-20",
      "invoice_ref": "INV-001"
    },
    {
      "type": "住宿",
      "description": "深圳XX酒店 2晚",
      "amount": 1160,
      "date": "2024-10-20",
      "invoice_ref": "INV-002"
    },
    {
      "type": "住宿",
      "description": "深圳XX酒店 额外1晚（客户临时加会）",
      "amount": 580,
      "date": "2024-10-22",
      "invoice_ref": "INV-003"
    },
    {
      "type": "市内交通",
      "description": "出租车/地铁",
      "amount": 320,
      "date": "2024-10-20",
      "invoice_ref": "INV-004"
    },
    {
      "type": "餐补",
      "description": "3天出差餐补",
      "amount": 300,
      "date": "2024-10-22"
    }
  ],
  "total_amount": 3310,
  "attachments": ["INV-001", "INV-002", "INV-003", "INV-004"]
}
```

---

### Step 13：端到端验证

```bash
# 1. 审核测试报销单
uv run python -m server.cli audit data/claims/EXP-2024-0312.json

# 期望行为：
# - Claude 调度 extractor 提取数据
# - 调度 auditor 审核
# - auditor 调 invoice-parse / pre-approval-match / travel-compliance
# - pre-approval-match 发现住宿多1晚（偏差）
# - 金额3310 < 5000，不触发 reviewer
# - 最终判定 manual_review，理由：行程天数偏差
# - PreToolUse hook 检查结果完整性
# - PostToolUse hook 用 Haiku 审核输出
# - 结果写入 output/results/EXP-2024-0312_result.json

# 2. 检查结果文件
cat output/results/EXP-2024-0312_result.json

# 3. 检查日志
cat logs/sessions/*.jsonl | head -20

# 4. 测试 HTTP API
uv run uvicorn server.api:app --port 8000 &
curl -X POST http://127.0.0.1:8000/chat \
  -H "Authorization: Bearer sk-default" \
  -H "Content-Type: application/json" \
  -d '{"message":"审核报销单 data/claims/EXP-2024-0312.json"}'
```

---

## 3. 部署

### 3.1 Dockerfile

```dockerfile
FROM python:3.12-slim

# Agent SDK CLI 依赖 Node.js
RUN apt-get update && apt-get install -y curl \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .
EXPOSE 8000
CMD ["uv", "run", "uvicorn", "server.api:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 3.2 docker-compose.yml

```yaml
version: "3.8"
services:
  agent-server:
    build: .
    ports:
      - "8000:8000"
    env_file:
      - .env
    volumes:
      - ./.claude:/app/.claude
      - ./knowledge:/app/knowledge
      - ./output:/app/output
      - ./logs:/app/logs
```

### 3.3 三种启动方式

```bash
# CLI
uv run python -m server.cli audit data/claims/EXP-001.json
uv run python -m server.cli chat
uv run python -m server.cli init-rules raw_policies/差旅制度.pdf expense

# HTTP API
uv run uvicorn server.api:app --host 0.0.0.0 --port 8000

# Docker
docker-compose up -d
```

---

## 4. 部署约束

| 约束              | 说明                                                            |
| ----------------- | --------------------------------------------------------------- |
| 不兼容 Serverless | SDK 底层 spawn CLI 子进程，需长运行实例                         |
| 并发上限          | 取决于 CLI 子进程数 × API rate limit，单机建议 ≤ 20 并发        |
| Worker 模型       | 单 worker + async，不用 Gunicorn 多 worker（避免撞 rate limit） |
| 扩展方式          | K8s 多 pod 每 pod 单 worker                                     |

---

## 5. 扩展路径

### 新增业务域

1. `.claude/agents/{domain}/` 下添加 agent markdown
2. `knowledge/{domain}/` 下添加 rules JSON
3. `CLAUDE.md` 路由表添加意图映射
4. skills 跨域复用，无需改动

### 新增规则

编辑 `knowledge/` 下对应的 JSON 文件。Python 代码和 .claude/ 配置无需任何改动。

### 新增 skill

在 `.claude/skills/{name}/SKILL.md` 创建文件，在需要的 agent 的 `skills:` frontmatter 中引用。
