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

- 作用: 前端/联调用的异步审核接口说明
- 重点:
  - `POST /audit/submit`
  - `GET /audit/tasks/{request_id}`
  - `GET /audit/tasks/{request_id}/result`
  - 上传模式与目录模式请求格式

## `.ai_state/superpowers/specs/`

- 作用: 当前项目的设计规格文档
- 重点:
  - `2026-03-31-async-audit-submit-serve-design.md`
  - `2026-03-31-audit-result-chinese-display-design.md`

## `.ai_state/superpowers/plans/`

- 作用: 已确认的实现计划与后续硬化计划
- 重点:
  - `2026-03-31-async-audit-submit-serve-plan.md`
  - `2026-03-31-audit-serve-hardening-plan.md`
  - `2026-04-01-serve-lifespan-and-task-store-plan.md`
