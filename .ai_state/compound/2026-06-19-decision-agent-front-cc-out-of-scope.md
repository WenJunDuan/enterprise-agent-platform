# Decision · 前端 agent-front 保持追踪，但 CC 视其为 out-of-scope

> doc_type: decision · 2026-06-19

## 决定

`agent-front/`（原 `ui/`，2026-06-18 改名）**保持在本仓 git 追踪内**——不可移出，
否则会出问题（构建 / 部署 / 同源托管依赖它在仓内）。

但它作为**独立演进的前端工程**单独维护，CC（Claude Code）工作时**默认把它当作
out-of-scope 区域**：

- 重构 / 搜索 / 审查 / 批量改动**默认排除** `agent-front/` 下内容。
- 改后端（server / .claude / knowledge）时**不联动**去改前端。
- 仅当用户**明确要求**动前端时才读取 / 修改 `agent-front/`。

## Why

前后端职责分离、前端独立迭代；但前端产物与路径仍被后端 / Docker 依赖，所以必须留在
仓内追踪，只是不希望 CC 在做后端工作时把注意力 / 改动扩散到前端。

## 背景修正

- 曾误以为"忽略 = 移出追踪"，做过 `git rm --cached agent-front` + `.gitignore`（commit
  `106b55d`），**已回退**。agent-front 必须保持 tracked。
- 正确语义：git 照常追踪；"忽略"只针对 **CC 的工作范围**，不是 git。

## 生效范围说明

本 compound doc 是决策留痕。若要让**每个 CC 会话自动遵守**该范围约束，需把约束写进
SessionStart 会注入的入口（`.claude/CLAUDE.md` 或 `.ai_state/_index.md` 的 project.gotchas）。
当前仅记于此档，待用户确认是否上提到常驻入口。

## 关联

- ui→agent-front 改名 + 引用修复：commit `bbf40ac`。
- `.agents/ .codex/ AGENTS.md` 是 Athena CX 平台镜像（非本任务产物），是否追踪待用户定。
