# 架构摘要

本文用于帮助研发和架构协作者快速判断：当前仓库已经具备哪些能力、整体分层是什么、下一步还缺什么。更完整的背景与长设计说明见 [enterprise-agent-dev-guide.md](enterprise-agent-dev-guide.md)。

## 当前状态

当前仓库已经不是纯骨架阶段，而是“最小可运行链路 + Claude 调度审核原型 + 规则初始化骨架”阶段：

- 已有可运行的本地 HTTP 服务：`server/api.py`
- 已有统一 env 配置入口：`server/config.py`
- 已有统一执行层：`server/core.py`
- 已有通用模型上游客户端：`server/model_client.py`
- 已有业务运行记忆写入器：`server/memory_writer.py`
- 已有统一日志配置：`server/logging_config.py`
- 已有 CLI `audit` / `init` 入口：`server/cli.py`、`server/rule_init.py`
- 已有 `.claude/` 费控最小审核编排：项目级 `CLAUDE.md` 调度、`/audit` 命令、`expense-router`、领域 auditor、workflow 与技能骨架
- 已有 `knowledge/memory/` 业务运行记忆目录，用于沉淀案例、判断、人工确认和例外处理

还没有进入“真实业务闭环可审核”的阶段，原因是可复用规则、真实单据输入、结构化提取、链路日志追踪和生产级审核留痕还未补齐。

## 系统目标

项目目标是搭建一个统一的企业智能审核平台，在同一套 Agent 基础设施上承载费控闭环、HR 合规、法务支撑等业务域。新增业务域时，优先通过扩展规则、知识和 agent 定义完成接入，而不是反复重写底层模型调用、日志、审计和入口层。

## 当前优先业务

当前优先落地的是费控闭环，而不是孤立的“报销单审核”。首期闭环包括：

- 事前审批：出差申请、招待申请、预算与审批层级校验
- 事中票据：发票解析、抬头/税号/日期/金额一致性校验
- 事后报销：报销单与事前申请交叉匹配，再叠加制度合规与预算占用判断

详细业务拆分见 [expense-control-design.md](expense-control-design.md)。

## 当前实际分层

### 1. 入口层

- `server/api.py`：提供 `/health` 和 `/chat`，用于最小联通验证
- `server/cli.py`：提供本地管理命令，当前已支持 `init` 和 `audit`
- `server/core.py`：统一执行包络，封装 Claude Agent SDK 的共享调用逻辑

这层已经有 CLI 版结构化审核入口，但 HTTP `/audit` 仍未开放，当前仍以本地联调为主。

### 2. 规则初始化层

- `server/rule_init.py`：负责扫描 `knowledge/external/`、读取业务运行记忆、生成 schema、规则占位文件、初始化报告和清单

当前能力是“初始化骨架 + 文本制度低置信度抽取 + OCR/向量化前置确认”，还不是正式制度解析引擎。

### 3. 模型接入层

- `server/config.py`：统一从 `.env` / 环境变量读取运行配置
- `server/model_client.py`：通过 OpenAI 兼容接口访问上游模型网关

这层已经可用，但目前主要服务于通用 `/chat`，还没有和业务审核流程深度绑定。
这层已经可用，并已被 CLI `audit` 复用来驱动 `.claude/` 审核编排。

### 4. 可观测性层

- `server/logging_config.py`
- `logs/service.log`

目前已经支持 `DEBUG / INFO / WARNING / ERROR`，能覆盖本地启动、调用和异常排查。

### 5. 知识层

- `knowledge/external/`：外部制度原文输入
- `knowledge/memory/`：业务运行记忆，按 `YYYY/MM/YYYY-MM-DD.md` 组织
- `knowledge/_schema/`：规则 schema
- `knowledge/expense/`：费控域规则初始化产物
- `server/memory_writer.py`：负责把可复用业务判断追加到每日 memory 文件

这层的目录已经明确，但“真实可复用规则”还不够。

### 6. 协作留档层

- `.ai_state/docs/`：架构、路线、业务设计
- `.ai_state/`：当前设计、计划、状态、质量和知识留档

这层已经建立，但文档要持续跟实现同步，不能停留在设计态。

## 核心原则

- 规则与流程解耦：规则尽量沉淀在 `knowledge/`，流程尽量沉淀在 agent / server 编排层
- 确定性与概率性分离：确定性校验、日志和阻断逻辑不依赖模型“碰运气”
- 单一主链路收敛：CLI、HTTP、后续 Chat/批处理尽量收敛到同一套核心审核链
- 审计可追溯：每个结论最终都要能回溯到规则、原始字段和证据链

## 当前已具备能力

- 本地通过 HTTP 调用模型，验证联通性
- 本地通过 CLI 执行 `/init`，生成规则 schema、规则占位文件、初始化报告
- 本地通过 CLI `audit` 触发 Claude Agent SDK，并执行 `.claude` 费控审核链
- 针对文本类制度文件进行低置信度规则抽取
- 针对 PDF / DOCX / 图片类制度文件，在接入 OCR/向量化前给出明确确认提示
- 通过 `knowledge/memory/` 沉淀并复用业务运行中的可复用判断
- 通过 `.env` / 环境变量集中读取模型、日志和 memory 配置

## 当前主要缺口

### P0：离“可审核闭环”还差的核心项

- 虽然已有 CLI `audit` 主链路，但还缺面向真实“仅文件输入”场景的结构化提取与附件编目能力
- 缺少真实可复用的 `knowledge/expense/*.rules.json` 样例规则，目前更多是初始化骨架
- 缺少更贴近真实单据上传场景的联调样例；当前主要依赖 `tests/fixtures/audit_inputs/` 中的 mock 数据
- 缺少生产级请求日志、链路追踪和审计留痕；当前结果输出仍偏本地联调形态

### P1：影响后续扩展效率的项

- `.claude/agents`、`.claude/workflows` 和 `.claude/skills` 已有费控最小链路，但只覆盖 `expense` 域，skills 还偏薄
- OCR / 向量化制度解析方案还未确认，也未接入
- 缺少围绕真实报销样例的端到端集成测试

### P2：后续工程化项

- 缺少更细的运行脚本、部署手册和运维说明
- 缺少多业务域扩展策略的实际代码验证

## 下一步建议顺序

1. 先补齐 `knowledge/expense/` 的真实样例规则，以及更贴近企业场景的文件清单/附件样例
2. 再补强 `expense-extractor` 与日志链路，让“只有文件、没有完整表单”的审核输入能跑通
3. 然后继续细化业务 agents/skills/workflow，让审核链路从“可调用”变成“稳定可复用”
4. 最后确认 OCR / 向量化是否接入，并补足对应的测试、运行说明和审计留痕
