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

## 生效范围说明 / 落点（2026-06-19 最终）

用户拍板：**只留本 `.ai_state` 决策档，不追求"自动注入"**。约束靠「索引先行」兜底——
`_index.md` 的 `pointers.latest_decisions` 已指向本档，CC 每个新会话起手读 `_index.md` 时带到。

⚠️ **不可放的落点（已踩坑）**：`.claude/CLAUDE.md` 是产品业务内容（业务调度中枢 prompt），
**会被加载进生产审核 agent 的系统提示**，绝不能往里写 CC 开发/工作约束（会污染产品行为）。
曾误写一段「工作范围(CC scope)」被用户回退。`.ai_state/_index.md` 本会话也未被 SessionStart
自动注入，故不依赖任何自动注入渠道，统一以本决策档为准。

## 关联

- ui→agent-front 改名 + 引用修复：commit `bbf40ac`。
- `.agents/ .codex/ AGENTS.md`（Athena CX 平台镜像）：用户 2026-06-19 拍板**不入库**，已加入 `.gitignore`
  （三条均原本 untracked，无需 `git rm --cached`）。
