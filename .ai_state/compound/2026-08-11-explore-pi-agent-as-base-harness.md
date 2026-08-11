# explore · 底座换 pi agent 的可行性评估（2026-08-11）

## 问题

用户问：把当前底座 claude-agent-sdk (Python) 换成 pi agent 可行吗？与现状对比。

## 指认

pi = earendil-works/pi（原 badlogic/pi-mono），Mario Zechner 的 MIT TypeScript coding agent，
v0.84.1，86.7k star，OpenClaw 底座。**不是** Inflection 的 Pi(pi.ai)，也不是同作者的 vLLM 部署
CLI badlogic/pi。事实清单与全部一手出处见本日会话调研（官方 repo/pi.dev/npm registry 核对）。

## 关键事实（决策承重项）

| 维度 | pi | 现状 claude-agent-sdk |
|---|---|---|
| 内网自建模型(qwen/DeepSeek) | **原生**：models.json 自定义 baseUrl，4 种 API 方言，官方支持 vLLM/proxy | 经 LiteLLM anthropic-format 兼容层；官方**不支持非 Claude 模型**，issue #677(SDK 捆绑二进制忽略 ANTHROPIC_BASE_URL)有 workaround |
| Python 服务内嵌 | **无 Python SDK**；唯一路径 RPC 子进程(stdin/stdout JSONL)；TS SDK 仅 Node 进程内 | Python SDK 进程内原生（agent_bridge.py 现行） |
| subagent/Task | **无内置**（官方 by-design 缺失），extension 自建或社区 fork | 内置（本产品 expense/tender 多 agent 依赖） |
| 最终输出 JSON schema 强制 | 无（strict schema 只在 tool 参数层；可用 submit_result 自定义工具模拟） | 内置 output_format（contracts/audit-result 依赖） |
| 权限/沙箱 | **官方明示无内置权限系统**，建议容器化自管 | 内置权限 + hooks（ocr-page hook 钉 bash 到 case_root 依赖） |
| MCP | 官方 "No MCP"（extension 可自建） | 内置（quantum-data 等依赖） |
| skills/CLAUDE.md | **兼容 Agent Skills 标准，自动加载 CLAUDE.md/AGENTS.md**——.claude/skills 可低成本迁移 | 原生 |
| hooks | extensions = TypeScript 重写 | Python 回调 |
| 成熟度/风险 | MIT、极活跃；0.x 月级快速漂移、badlogic 一人主导(巴士系数)、repo 已迁过一次组织 | 官方维护；绑 Anthropic 生态 |

## 结论

**技术可行，当下不划算，缓议。**

1. **换底座解决不了任何当前实跑问题**：页锚/横比/并发三症状根因全在 server/ocr + server/tender
   Python 层（见 2026-08-11-tender-eval-hardening roadmap），与 agent 底座无关。
2. 买到的：内网模型接入原生化（甩掉 anthropic-format 兼容层）、MIT 全可控、skills 资产可迁移。
3. 付出的：自建四大件（subagent、结构化输出强制、权限护栏、MCP 桥）+ 产品 hooks TS 化 +
   Python↔RPC 进程桥（在并发已是痛点的服务里再加一层进程管理）+ 跟随 0.x 上游漂移
   （coding-standards"自研 vs 依赖"判据里被一笔带过的正是这类长期跟漂成本）。
4. 本产品的会话是**审核/评标任务不是 coding 任务**（Read/Skill/Task/结构化输出，不用 Edit 精确
   diff）——"非 Claude 模型在 Claude harness 下退化"的最大坑（edit format）对本产品面小；
   现有 LiteLLM 路径的真实退化程度应先实测再谈换底座。

## 若要推进的最小验证路径

1. 先修 H1-H3（与底座无关）。
2. 实测现路径：内网 qwen/DeepSeek 经 LiteLLM anthropic-format 跑 tender-evaluate golden 集，
   用 eval 回归闸（D1 产物）量化质量差距——有数据再决策。
3. 差距不可接受时做 1-2 天 PoC：pi RPC 模式 + models.json 接内网模型 + 复用现 .claude/skills
   跑同一 golden 集对比。PoC 范围钉死在"评标会话 runner"单点，不动平台其余部分。
4. 时机上与 OCR 独立服务迁移（compound/2026-07-20 决策）合并评估——两者都是服务边界重划，
   分开做两次手术不如一次定型。
