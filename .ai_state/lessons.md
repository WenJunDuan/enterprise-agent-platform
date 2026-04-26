# Lessons

- `.claude/` 只保留业务内容；开发过程、运行方式、服务契约和演进记录统一放在 `.ai_state`。
- 结构化 JSON 约束要落在 Claude Agent SDK `output_format` 和 schema 上，而不是依赖提示词 wording。
- 对服务层的目录迁移和兼容裁剪要一次性做完：删目录、删引用、删 fallback、删缓存最好在同一轮完成。
- `server/logs` 是历史残留；真实运行目录应统一使用项目根 `logs/`，避免后续存储边界混乱。
- 一旦决定不再兼容旧路径，就应同步移除 `LEGACY_*` 常量和旧单文件读取逻辑，避免为未来 PostgreSQL 迁移制造噪音。
- 本地持久化要先把 `request_id / conversation_id / claude_session_id` 这条链路设计完整，再考虑替换底层为数据库。
- 如果业务域继续扩展，`.claude/skills` 继续按“业务域 / 通用能力 / 系统能力”分组，比一级平铺更容易维护。
- 顶层 `data/` 与 `raw_policies/` 如果不再保留，就要同步修正文档、CLI 默认参数、slash command 用法和验收示例；否则计划会被历史目录误导。
- 当前仓库的真实素材组织应以 `tests/` 承载测试数据、`knowledge/` 承载结构化规则、`knowledge/external/` 承载制度源材料为准。
- `batch-audit` 已不再是当前阶段主线能力，规划和文档不应继续围绕它展开。
- “规则初始化”和“审后记忆沉淀”都属于 Claude 侧业务建设，不应回流成 Python 业务判断；Python 继续只做调用、归档和查询。
- FastAPI 回归测试里，httpx `TestClient` 在 `files=` 为空或缺失时不保证发 `multipart/form-data`，可能退化成 `application/x-www-form-urlencoded`；零附件场景要**手写 multipart body + 显式设置 `Content-Type; boundary=...`**，否则端点会分发到错误的 content-type 分支。
- 通过 `from server.platform.paths import SUBMISSION_ROOT_DIR` 引入到 `server.api` 后，测试里 monkeypatch 必须作用于 `server.api.SUBMISSION_ROOT_DIR`（被引入的目标模块），而不是源模块 `server.platform.paths`；否则运行时仍读到旧绑定。
- tenant isolation 不能只靠 API 入口校验；一旦 store 查询函数把 `tenant=None` 当默认值，内部任何漏传都会退化成“读全量数据”，因此需要显式区分 tenant-scoped API 和 admin-only 维护路径。
- HTTP `X-Request-ID` 更适合作为 correlation id，而业务返回体里的 `request_id` 继续承担请求归档主键；如果把两者混成一个概念，会同时破坏文件命名约束和跨系统链路追踪的清晰度。
- **Python 只做通信 / 鉴权 / 服务，不碰任何业务概念**。2026-04-20 在 audit 域曾试图把 Python 拆成"数据搬运层 + Claude 判断层"（`server/audit/` 下的 contracts / intake / extractor / rules_loader / amount_extract / approval_signatures / orchestrator，外加 `/audit/fast` 端点），即使"只做搬运"也是越线——Python 根本不该知道"发票 / 规则 / 金额 / 签字节点"等业务词汇。已全部撤销。下次涉及类似"降低 Claude 调用次数 / 优化审核耗时"的诉求时，只能在 prompt 工程、schema 约束、`max_turns` 上做文章，不能把业务语义下沉到 Python。
- 同一条业务入口不应同时存在于 Python prompt 模板和 `.claude/commands/` 两处。2026-04-21 在 A-001 中移除了 `server/prompts/` 下的 `audit` / `init-rules` 业务模板，原因不是“模板机制不好”，而是它会让 HTTP/CLI 路径和 Claude 原生命令路径产生双重事实源。以后 Python adapter 只负责参数序列化和 slash command 调用，不再维护自己的业务说明文本。
- 收口事实源时，不能只删除 Python 侧业务 prompt，还要把其中仍然生效的结构化约束完整补回 Claude command。否则看起来职责更清晰，实际上会削弱 Claude 端满足 schema/validator 的提示强度，造成 `manual_review_reason` 等字段更容易漏填。
- `distill-memory` 这类“审后知识沉淀”能力更适合保留在 Claude command / CLI 工作流里，不适合作为对外 HTTP API 暴露。原因是它不是稳定的外部业务接口，而是内部知识治理动作；放进 API surface 会把管理面和业务面混在一起。
- 如果主流程已经统一走 `claude-agent-sdk`，二审 hook 也应尽量统一到同一 SDK，避免主流程和 hook 分别依赖不同的客户端栈。多套 SDK 并存短期未必出错，但长期会带来版本节奏、认证方式、错误模型和调试路径不一致的问题。
- 发布前做 API 返回集优化时，优先选“增量兼容”而不是“一刀切重包”。这次把 HTTP 错误统一补成 `detail + error{...}`，而不是直接移除 `detail`，可以在不打断现有前端的前提下完成契约升级。
- 查询型列表接口如果暂时拿不到可靠 total count，就不要伪造 `total`；统一返回 `returned + filters` 更诚实，也能避免前端误把当前页条数当成全量统计。
- 质量门要跑全仓而不是只跑 `server/ tests`。这次发布前整理暴露出 `.ai_state/docs/audit-skills/audit_check.py` 的历史 lint 问题，说明文档侧辅助脚本同样会影响真实发布 gate。
- README 这类入口文档的首要目标不是“信息尽可能全”，而是“高频问题 30 秒内能找到答案”。这次把端口、两套 CLI、常用 API 和启动方式提前后，可读性明显比长篇顺叙教程更好。
- 公共探针接口与本地运维诊断命令都要克制数量。最终收口成 `health + doctor` 比 `health + ready + inspect + doctor` 更清晰：外部只看一个探针，内部只保留一个重型诊断入口。
- 如果 CLI 已经承担本地追溯、治理和排障职责，就不要再在 HTTP API 上重复暴露同一批查询面。更清晰的边界是：HTTP 只留业务主链路，CLI 留查询/治理/调试。
- 如果目标是“最小业务 HTTP 面”，就要避免半收半放。真正稳定的边界是：HTTP 只留前端必需的异步业务链路，命令型能力如 `chat/audit/init-rules` 也统一收回 CLI。

## [2026-04-26 Sprint 2] 前端接入必须把文档契约和真实 API 同步验证
- **Pattern**: 前端新增列表页时，后端需要显式锁定 `GET /audit/tasks` 路由顺序和返回 shape，避免被 `GET /audit/tasks/{request_id}` 吞掉；对应测试在 `tests/test_api.py` 和 `tests/test_query_surfaces.py`。
- **Pitfall**: `.ai_state/reviews/sprint-2.md` 曾出现 local PASS 早于真实 gate 的情况；以后进入 review 前必须实际跑 `pytest`、`ruff`、前端 build，并把失败先写回 review。
- **Constraint**: Vite 环境变量必须有 `ui/src/vite-env.d.ts:1` 的 `vite/client` 类型声明；否则 `ui/src/api/client.ts` 的 `import.meta.env.VITE_API_BASE` / `VITE_API_KEY` 无法通过 `tsc`。
- **Constraint**: review/impl 阶段的 session-start 会尝试执行 `.ai_state/init.sh`；项目必须保留一个无副作用、可重复运行的 init 脚本（`.ai_state/init.sh:1`）。

## [2026-04-26 Sprint 3] 上传入口只做通用 intake
- **Pattern**: 通用表单入口应把 `form_json` 解析、普通 multipart 字段归档和附件落盘拆开处理，`server/api.py:315` 解析可选 JSON，`server/api.py:302` 收集普通字段，`server/api.py:380` 写入统一 `audit-request.json`。
- **Pitfall**: 前端模板字段很容易被文档和测试误固化成 Python 必填契约；`tests/test_audit_submit_attachments.py:77` 应覆盖无附件仍可提交，`tests/test_api.py:55` 应覆盖无 `form_json` 的附件提交。
- **Constraint**: UI 对接层必须用通用 payload 和可选附件，`ui/src/api/client.ts:46` 接收 `unknown` formData 和默认空 `File[]`，`ui/src/pages/SubmitExpense.tsx:373` 不再因 0 附件阻断提交。
