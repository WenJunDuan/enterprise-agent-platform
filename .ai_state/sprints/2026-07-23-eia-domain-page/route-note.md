# route-note · 2026-07-23-eia-domain-page

> 2026-07-23 重建×2:原档两度被 X2 agent worktree 的 Stop hook 反向同步 .ai_state 摧毁(根因已锁定,worktree 已拆除),主 agent 从会话上下文重建并即刻 commit。

## 任务
用户插入需求(2026-07-23):把 `design/`(index.html + support.js,DC 框架静态交互稿「环评智检 · 检测报告受理平台」)迁移进 `agent-front/`,成为平台**第四个业务域能力**,侧边栏排在「智能 OCR」上面。分工:fable5 设计,Opus 实现(用户显式排除 sonnet)。

## 分诊
- **候选路径**:Quick 否(新增域=导航组+2 路由+完整 feature 包,超绿区);**Feature(选定)**:单一前端模块自洽,验收明确,无跨后端改动(后端接线显式出界,见 design.md 方案 C);System/Refactor 否(纯增量)。
- **红区判定**:agent-front 默认 out-of-scope(compound/2026-06-19-decision-agent-front-cc-out-of-scope.md),本次用户显式授权;generator subagent + isolation: worktree 执行。
- **与 D9 关系**:D9 唯剩 runtime-verify 阻塞外部输入,本 sprint 窗口期插入,文件面无交集。
- **roadmap 归属**:非 doc-intelligence 主题,插入项 X1 落账 items.yaml,不占 D 序号。
- **置信度**:高(导航/路由/feature 三层均有 OCR 工作台同构先例)。

## 决策
path=Feature · 红区实现(worktree)· design 先行 + critic ≥1 轮 → opus 实现。

## 事后追记(2026-07-23,透明记录)
实际实现模型=**claude-sonnet-5**(违约用户"禁 sonnet"指令):`~/.claude/agents/generator.md` frontmatter `model: sonnet` pin 压过 Agent 调用的 `model: opus` 覆盖,主 agent 事后 transcript 取证(217 条消息全 sonnet)。质量兜底:主 agent 独立验(146 pass/build/eslint)+ 独立 reviewer 对抗审查(0 P0)+ spec 核查 + 修复 53fd7ac 全部通过。处置待用户拍板(接受 or opus 重做)。
