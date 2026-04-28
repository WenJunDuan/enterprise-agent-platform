# Progress

2026-04-24 17:22 [Feature/impl/Sprint 2] 接管 Claude 变更复核：发现 sprint-2 review 标记 PASS 但后端 pytest 与前端 build 均失败，进入修复流程。
2026-04-24 17:28 [Feature/impl/Sprint 2] 完成 S2-FIX-001：删除过期 JSONLResultStore 测试依赖，store capacity 测试对齐当前 SQLite result store 边界。
2026-04-24 17:28 [Feature/impl/Sprint 2] 完成 S2-FIX-002：新增 ui/src/vite-env.d.ts，前端 TypeScript 可识别 import.meta.env。
2026-04-24 17:29 [Feature/impl/Sprint 2] 完成 S2-FIX-003：收口上传契约为至少 1 个 files 附件，修正 health compact payload 测试与 lint 未使用导入。
2026-04-24 17:29 [Feature/impl/Sprint 2] 完成 S2-FIX-004：验证通过 UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q、ruff check .、cd ui && npm run build，并同步 sprint-2 review。
2026-04-26 00:00 [Feature/review/Sprint 2] 完成 S2-REV-001/S2-REV-002：同步 design 与前端对接文档，补齐 GET /audit/tasks、上传附件必填、VITE_API_BASE/VITE_API_KEY。
2026-04-26 00:00 [Feature/review/Sprint 2] 完成 S2-REV-003：新增 .ai_state/init.sh，review/impl 阶段 get-bearings 可直接执行。
2026-04-26 00:00 [Feature/ship/Sprint 2] 完成 S2-REV-004：stale contract scan、init、pytest、ruff、uv build、ui build、git diff --check 全部通过；Sprint 2 已推进到 ship，等待用户控制 commit/PR。
2026-04-26 00:00 [Feature/ship/Sprint 2] 生成 .ai_state/ship.md，记录安全提交范围、禁止 force-add 的本地产物与建议 commit message；等待显式提交指令。
2026-04-26 00:00 [Feature/ship/Sprint 2] 用户确认提交；已将 project.json 标记为 Sprint 2 完成并推进到 Sprint 3 空阶段，准备创建本地 git commit。
2026-04-26 00:00 [Feature/plan/Sprint 3] 生成真实报销填报与列表增强计划：多区块表单、本地提交摘要、列表/详情增强；等待确认后进入实现。
2026-04-26 00:00 [Feature/impl/Sprint 3] 用户确认开始实现；阶段切换为 impl，按 S3-T1 至 S3-T7 顺序推进。
2026-04-26 00:00 [Feature/impl/Sprint 3] 完成 S3-T1/S3-T2：扩展真实报销 payload 类型，并新增按 request_id 关联的前端本地提交摘要存储。
2026-04-26 00:00 [Feature/impl/Sprint 3] 用户中断 UI 实现并调整契约方向：Python 接收层不应校验业务字段，应只做传输/安全/归档约束，表单语义交给 Claude agent。
2026-04-26 00:00 [Feature/impl/Sprint 3] 完成 S3-T0：`/audit/submit` 上传模式改为通用 intake，删除业务必填字段与附件扩展名白名单，允许 0 个或多个附件。
2026-04-26 00:00 [Feature/impl/Sprint 3] 完成 S3-T3/S3-T4/S3-T5：复杂报销填报、任务列表、任务详情已接入本地提交摘要与新上传契约。
2026-04-26 00:00 [Feature/impl/Sprint 3] 完成 S3-T6：README、design、plan、tasks、前端对接文档同步为 Python 不校验业务字段。
2026-04-26 00:00 [Feature/review/Sprint 3] 完成 S3-T7：聚焦 pytest、全量 pytest、ruff、前端 build 均通过；写入 sprint-3 review。
2026-04-27 00:00 [Quick/impl/Sprint 4] 用户要求继续完善前端用于自测；进入 Sprint 4，范围为健康连接提示、填报自测辅助、结果字段完整展示、摘要清理和联调文档。
2026-04-27 00:00 [Quick/impl/Sprint 4] 完成 S4-T1/S4-T2/S4-T3/S4-T4：新增后端连接状态条、填报页复制/重置/新单号、详情页完整结果字段、列表清空本机摘要。
2026-04-27 00:00 [Quick/review/Sprint 4] 完成 S4-T5：README、前端对接文档、design、session、review、lessons 已同步；ui build、pytest、ruff、diff check 全部通过。
2026-04-27 00:00 [Bugfix/Sprint 4] 调整租户 token 对接边界：UI 改用 `VITE_TENANT_TOKEN` 命名，外部接口调用继续直接发送 `Authorization: Bearer <tenant-token>`，缺失/格式错误 token 统一返回 401。
