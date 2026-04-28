# Design Snapshot

## 分层

- `.claude/`: agents、skills、hooks、commands、contracts，承载业务工作流与输出契约
- `knowledge/`: 结构化制度和规则资产
- `server/api.py`: 最小业务 HTTP 接口、租户鉴权、健康检查、异步审核提交/状态/结果读取
- `server/core.py`: Claude Agent SDK 桥接、结构化输出约束、会话控制、事件记录
- `server/command_adapter.py`: Python 对 Claude slash command 的统一调用适配层
- `server/cli.py`: 本地 CLI 外壳，负责终端参数解析与终端输出
- `server/app_server.py`: Python 版后台进程管理、日志查看、doctor、maintain
- `server/platform/`: 路径、配置、诊断、维护、底层文件存储工具与源文件预处理
- `server/stores/`: request/session/result/review-delta/runtime/memory 仓储接口；当前 request 日志保留 JSONL，request/session/result/review-delta/memory 查询索引已切到 SQLite
- `tests/`: 测试代码与后续测试用例数据承载位置
- `knowledge/external/`: 当前仓库中保存原始制度文件或外部参考材料的位置
- `logs/`: 唯一的本地运行时、请求、会话、结果、进程状态归档根目录

## 当前设计决策

- 业务规则只留在 `.claude/` 和 `knowledge/`；Python 只负责调用 Claude、执行 JSON 契约、记录审计链路和暴露运行入口。
- 结构化输出通过 Claude Agent SDK `output_format` + JSON Schema 强制约束，不再依赖 prompt 文本声明。
- 审核输出继续保留内部 `approved / rejected / manual_review` 三态，但对外统一映射为 `result/conclusion/explanation` 中文展示字段；其中 `manual_review` 固定显示为“待人工复核”，且必须说明无法自动放行的原因。
- `request_id` 是全链路审计主键；`conversation_id` 表示应用级会话；`claude_session_id` 对应 Claude SDK 的可恢复会话。
- 查询/治理能力已收回 CLI；HTTP 只保留前端业务主链路与健康探针，不再重复暴露 `/requests`、`/results`、`/memories` 等治理面。
- HTTP 错误响应统一保留兼容字段 `detail`，并补充结构化 `error{code,message,status_code,path,correlation_id}`；其中 `correlation_id` 与响应头 `X-Request-ID` 对齐，用于联调与日志追踪。
- Python 不拥有业务能力实现；`init-rules`、`audit` 等能力定义在 `.claude/commands` / `.claude/skills`，CLI 与 serve 只通过统一 adapter 调用这些 Claude 能力。
- serve 层现已提供异步审核提交能力：`POST /audit/submit` 统一接收目录模式与上传模式；上传模式只做传输/安全/归档约束，`form_json` 与普通 multipart 字段不做业务必填校验，附件为 0 个或多个，语义判断交给 Claude agent。`GET /audit/tasks` 提供任务列表，`GET /audit/tasks/{request_id}` 提供状态轮询，`GET /audit/tasks/{request_id}/result` 提供轻量结果读取。
- 前台调试入口是 `python -m server.cli serve`；后台常驻入口是 `uv run app-server start`，两者本质上都启动同一个 Python 服务进程。
- 本地存储当前采用“请求日志/运行日志保留文件，request/session/result/review-delta/memory 查询索引使用 SQLite，结果归档保留 JSON 文件”的混合布局；后续如需升级到 PostgreSQL，优先迁移查询索引层，不改 Claude 业务侧内容。
- 顶层 `data/` 和 `raw_policies/` 不是当前仓库正式目录；测试数据应收敛到 `tests/`，真实制度源材料当前放在 `knowledge/external/`。
- 当前业务建设顺序调整为：`/init-rules` 优先，审后业务记忆沉淀次之，单条审核业务闭环随后；`batch-audit` 不进入当前主线。

## 本地存储布局

- `logs/service/requests/requests-YYYY-MM.jsonl`: serve 请求审计索引
- `logs/service/requests/index.sqlite3`: serve 请求查询索引
- `logs/service/audit-tasks/tasks.json`: 异步审核任务状态
- `logs/sessions/index.sqlite3`: 会话查询索引
- `logs/sessions/events/YYYY/MM/DD/*.jsonl`: Claude 原始事件流
- `logs/results/index.sqlite3`: 结构化结果查询索引
- `logs/results/by-request/YYYY/MM/DD/{request_id}.json`: 结构化结果归档
- `logs/review-deltas/index.sqlite3`: review-delta 查询索引
- `logs/review-deltas/by-request/YYYY/MM/DD/{request_id}.json`: review-delta 归档
- `logs/knowledge/memory-index.sqlite3`: memory 资产查询索引
- `logs/runtime/app-server/`: PID、状态文件、stdout/stderr、维护对象
- `data/submissions/{request_id}/`: 上传模式生成的 case 目录与附件落盘位置

## 约束

- 结果、请求、会话三层都用 `request_id` 串联，保证可恢复、可追溯。
- 请求审计仍保留按月分片 JSONL；request/session/result/review-delta/memory 查询索引已切到 SQLite。
- 原始事件流和结构化结果分离存储：前者保留过程，后者保留最终归档。
- CLI 与 serve 共享同一套 Claude command 调用适配层；差异只体现在终端输出与 HTTP JSON 输出。
- 后续如果接 PostgreSQL，优先迁移 `request/session/result/review-delta/memory` 查询索引层，不改 Claude 业务侧内容。

## 记忆分层

- `logs/` 保存不可变的运行事实：请求审计、会话事件、最终结构化结果、进程状态。
- 审核完成后的“业务记忆沉淀”不应直接混入 Python 逻辑；应由 Claude 侧从已归档结果中提炼为结构化经验资产，再沉淀回 `knowledge/` 体系。
- 下一阶段建议增加独立的案例/经验记忆层，用于沉淀已审核结果中的 `verdict`、`policy_refs`、`evidence_chain`、风险模式和复核结论，并保留 `request_id` / `result_file` 回链。

## 当前清理状态

- 旧 `server/` 外层兼容 wrapper 已删除，当前以 `platform/` 和 `stores/` 为稳定内部边界。
- 旧 `server/logs` 路径已废弃；真实运行数据统一写入项目根 `logs/`。
- 仓储层不再读取 legacy 单文件日志，也不再保留 `output/results/` 兼容实现。
- 文档与命令中仍有少量 `data/claims`、`raw_policies/...` 的历史示例路径，需要在下一阶段统一到当前仓库目录模型。

---

## Sprint 2 — React Frontend Architecture

### WHY

The backend FastAPI audit platform has no user-facing UI. Engineers must call raw HTTP endpoints to submit expense claims and track status. A lightweight React SPA eliminates that friction without changing the backend contract.

### System Boundaries

```
Browser
  │
  ├─ ui/  (Vite dev server :5173)
  │    ├─ Proxy: /audit/* → http://localhost:8000
  │    └─ Proxy: /health  → http://localhost:8000
  │
  └─ server/  (FastAPI :8000)
       └─ CORSMiddleware: allow_origins=[":5173"]
```

### Frontend Stack

| Layer | Choice | Rationale |
|-------|--------|-----------|
| Bundler | Vite 5 | Fast HMR, native ESM, built-in proxy |
| UI lib | React 18 | Concurrent features, large ecosystem |
| Language | TypeScript 5 | Type-safe API contracts |
| Styling | Tailwind CSS v3 | Utility-first, no runtime overhead |
| Routing | React Router v6 | File-like routes, loader-friendly |

### Directory Layout

```
ui/
├── index.html
├── package.json
├── vite.config.ts          # proxy config
├── tsconfig.json
├── tsconfig.node.json
├── tailwind.config.js
├── postcss.config.js
├── .env.local              # VITE_TENANT_TOKEN=... (gitignored)
├── .gitignore
└── src/
    ├── main.tsx            # createRoot entry
    ├── index.css           # @tailwind directives
    ├── App.tsx             # BrowserRouter + Routes
    ├── api/
    │   └── client.ts       # fetch wrapper, Bearer auth injection
    ├── types/
    │   └── index.ts        # AuditTask, AuditResult, etc.
    ├── components/
    │   ├── Layout.tsx      # top nav shell
    │   └── StatusBadge.tsx # color-coded status pill
    └── pages/
        ├── TaskList.tsx    # table, filter, pagination
        ├── SubmitExpense.tsx # upload form
        └── TaskDetail.tsx  # detail + 3s polling + result
```

### Pages & Routes

| Route | Component | Description |
|-------|-----------|-------------|
| `/` | TaskList | Paginated task table with status/search filters, local summary overlay, and fallback-test controls |
| `/submit` | SubmitExpense | Rich reimbursement template → multipart POST /audit/submit |
| `/tasks/:id` | TaskDetail | Status polling + submitted summary + full audit-result display |

### API Integration

- Base URL: `import.meta.env.VITE_API_BASE` (default `/`)
- Auth: `Authorization: Bearer ${VITE_TENANT_TOKEN}` injected by `api/client.ts`; `VITE_API_KEY` is only kept as a legacy local alias.
- `TENANT_KEYS` remains server-side truth; API consumers pass `Authorization: Bearer <tenant-token>` directly and do not use `VITE_*` variables.
- Tenant token stored in `ui/.env.local` for local UI self-test only — never committed (in `.gitignore`)
- Layout renders a `/health` connection status strip so local testers can see backend reachability and API config before submitting.
- Task list uses `GET /audit/tasks?status=&limit=&offset=` and expects a plain `AuditTask[]`.
- Submit form uses multipart `POST /audit/submit`; `form_json` and `files` are both optional as long as the upload contains at least one meaningful form field or file.
- Task detail renders `conclusion` / `explanation` / `reasons` / `policy_refs` / `risk_score` / `risk_dimensions` / `evidence_chain` from the current audit-result schema.

### Polling Strategy

TaskDetail polls `GET /audit/tasks/:id` every 3 seconds when `status ∈ {accepted, running}`.
Poll stops (interval cleared) when `status ∈ {completed, failed}` or component unmounts.
Result is fetched once on transition to `completed`.

### Backend Changes

- Add `CORSMiddleware` after `app = FastAPI(...)` to allow `http://localhost:5173`.
- Add `GET /audit/tasks` as the frontend task-list endpoint; the route is registered before `GET /audit/tasks/{request_id}`.
- Keep `/audit/submit` upload mode business-agnostic: `form_json` is optional but must decode to a JSON object when present; scalar multipart fields are archived under `fields`; `files` is optional and only subject to filename, non-empty content, and size safeguards.
- Preserve the minimal HTTP boundary: no `/requests`, `/results`, `/memories`, `/review-deltas`, `/chat`, `/audit`, or `/init-rules` routes.
