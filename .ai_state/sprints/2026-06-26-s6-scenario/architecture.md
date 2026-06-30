# S6 Scenario Split Phase 1 Architecture

## Three Scenarios

- `expert_assist`: 政务内网专家辅助入口，复用 S5 风险提示与问题清单，报告重点是辅助评审线索、待核验项、扣分/废标风险，不直显分数护栏沿用 S5。
- `bidder_self_check`: 互联网区投标自查入口，上传投标文件与对应招标文件，报告重点是自查风险、扣分点、材料/形式问题和修改建议；报告下载后要求用户显式确认并调用项目级联删除，提示“文件已从服务器销毁”。
- `post_eval_monitor`: 评后监督复核入口，只读读取已完成的 `expert_assist` 项目，无上传、追加、删除、重跑入口；报告重点是已完成项目的复核线索与审计留痕。

## Shared Backend Boundary

- `tender_projects.scenario` 标记项目场景，默认 `expert_assist`，旧表通过幂等 `ALTER TABLE` 补列。
- `POST /tender/projects` 透传并校验场景；`GET /tender/projects?scenario=` 支持按场景过滤。
- 评标、OCR、报告和 S5 advisory 风险逻辑仍共享同一后端内核，phase-1 不复制评分/风险逻辑。

## Security Boundary

- Phase 1 场景隔离仅是 UI 层入口、导航可见性和列表过滤；用户仍可绕过前端路由直接调用 API。
- 真正权限隔离、tenant token 分区、RBAC/resource authz、独立部署强制边界待 RBAC/S8 sprint。
- 投标自查的“下载后销毁”复用现有 `deleteTenderProject` 级联删除路径，是数据生命周期提示与主动销毁，不等同于后端权限隔离。

## Deployment Zones

- 互联网区：默认只暴露 `bidder_self_check` 导航入口，并配合后续独立 tenant/RBAC。
- 政务内网：默认暴露 `expert_assist`，面向专家辅助评审。
- 监督复核区：暴露 `post_eval_monitor`，只读查看已完成专家辅助项目。
- `VITE_ENABLED_SCENARIOS` 控制前端导航可见性；未配置时只开启 `expert_assist`。
