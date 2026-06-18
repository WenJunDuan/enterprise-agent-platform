# 文档地图

## `.ai_state/docs/Enterprise agent vibe guide.md`

- 作用: 端到端实施规范
- 重点:
  - 技术栈与硬性约束
  - 项目目录结构
  - `server/`、hooks、commands、agents、skills 的示例实现

## `.ai_state/docs/enterprise-agent-dev-guide.md`

- 作用: 架构设计与代码样例说明
- 重点:
  - 分层边界与确定性/概率性构件划分
  - `CLAUDE.md`、settings、agents、skills 的推荐写法
  - 服务端三入口和部署方式

## `.ai_state/docs/前端审核服务对接文档.md`

- 作用: 前端/联调用的接口说明（审核异步链路 + OCR 同步识别）
- 重点:
  - 审核: `POST /audit/submit` → 轮询 `GET /audit/tasks/{id}` → `GET /audit/tasks/{id}/result`
  - OCR: `POST /ocr/extract`（纯识别）/ `POST /ocr/fill`（识别+回填）
  - 上传模式与目录模式请求格式 + 错误码

## `.ai_state/sprints/{date}-{slug}/`

- 作用: 各 sprint 的 design / plan / ship / reviews（v9.6.4 迁移后，原 `superpowers/` 已并入此处）
- 重点:
  - `2026-06-17-ocr-http-api/`（OCR 对外 API + 前端 + 四轮 codex review）
  - `2026-03-31-async-audit-submit-serve/`、`2026-04-01-serve-lifespan-and-task-store/` 等历史 sprint

## `.ai_state/compound/{date}-{type}-{slug}.md`

- 作用: 跨 sprint 经验沉淀（learning / trick / decision / explore）
- 重点:
  - `2026-06-17-learning-cross-review-and-soft-timeout.md`（软超时反模式 + 交叉 review 收敛判据）
  - `2026-06-17-learning-classify-fix-exposes-latent-bug.md`（改判据暴露从未跑过的死分支）
