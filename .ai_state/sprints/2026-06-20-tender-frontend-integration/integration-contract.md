# Tender 前端对接契约 — agent-front tender-review ↔ 后端 /tender API

> Sprint 2026-06-20-tender-frontend-integration · CC 出契约，codex 接前端。
> 目标：把 `agent-front/src/features/contract/tender-review/` 的 mock 换成真实 `/tender` API。
> 后端已 ship（tender-data-model goal，344 passed）。前端 `types.ts` 已是数据金标准，**尽量不改 types，新增 api.ts + 改数据来源**。

## 0. 认证 + 基础（仿 `features/audit/api.ts`）
- Base：`VITE_API_BASE`（默认 `/`）。Header：`Authorization: Bearer <tenant-token>`（复用 audit 的 `getActiveTenantToken()` / PIN 机制）。
- 错误响应统一形：`{ detail, error:{code,message,status_code,...} }`。沿用 audit `handleResponse`。
- **建议直接复用 `features/audit/api.ts` 的 token/handleResponse/url 工具**，tender 只加业务函数。

## 1. 后端端点清单（全部 `/tender` 前缀，已实现）

### 招标项目资源
| 方法 | 路径 | 请求 | 响应 |
|---|---|---|---|
| POST | `/tender/projects` | `{tender_no?,title?,tenderee?,method?,control_price?,funding_type?}` | `TenderProjectResponse`（幂等：同 tenant+tender_no 返回现有） |
| GET | `/tender/projects?status&limit&offset` | — | `TenderProjectResponse[]` |
| GET | `/tender/projects/{id}` | — | `TenderProjectDetailResponse`（+bidder_count/bids/recommended_bidder/compare_stale） |
| POST | `/tender/projects/{id}/evaluate` | directory: `{mode:"directory",directory_path}` / upload: multipart `mode=upload`+`form_json`+`files` | `{request_id,status:"accepted",mode,task_status_url}` |
| GET | `/tender/projects/{id}/results` | — | `[{request_id,claim_id,verdict,manual_review_reason,created_at}]` |
| GET | `/tender/projects/{id}/results/{request_id}` | — | 完整 audit-result（criteria/scoring/evidence/policy_refs，删任务后仍可取） |
| POST | `/tender/projects/{id}/compare` | — | `{request_id,status:"accepted",mode:"compare",task_status_url}` |
| GET | `/tender/projects/{id}/compare` | — | `{project_id,result:<compare-payload>,stale,computed_at,input_result_ids}` |

### 评标任务态（轮询用）
| 方法 | 路径 | 响应 |
|---|---|---|
| GET | `/tender/tasks/{request_id}` | `TenderTaskStatusResponse`（status: accepted/running/completed/failed + progress_message + error_detail） |
| GET | `/tender/tasks/{request_id}/result` | 完整 audit-result（completed 才有，否则 409） |
| POST | `/tender/tasks/{request_id}/retry` · DELETE `/tender/tasks/{request_id}` | 重试 / 删除 |

## 2. 类型映射（前端 types.ts ↔ 后端响应）

### TenderProject ↔ project response
| 前端字段 | 后端来源 | 备注 |
|---|---|---|
| `id` | `project_id` | |
| `name` | `title` | |
| `code` | `tender_no` | 招标编号 |
| `method` | `method` | |
| `status` | `status` | **已对齐**：doing/review/done/archived |
| `bidderCount` | detail `bidder_count` | |
| `recommendedBidder` | detail `recommended_bidder` | 仅 compare 非 stale 非 provisional 时非空 |
| `score`/`stage`/`progress`/`riskCount`/`date` | **无直接后端字段** | score=compare 第一名 total_score；progress=已完成投标人/总数；date=created_at；riskCount=各家 manual_review 项数（派生，或前端留默认） |

### ReviewBidder ↔ compare result.bidders[]
| 前端 | 后端 compare `bidders[]` |
|---|---|
| `id`/`name` | `claim_id`（名称需从 project detail bids 或 result payload 补） |
| `total` | `total_score` |
| `rank` | `rank` |
| `tag`/`short` | 前端展示派生 |

### CompareGroup（横比表）↔ compare result
- compare `result.bidders[]` 每家有 `price_score`/`other_score`/`total_score` → 前端按"评分项 × 投标人"转成 `{name, rows:[{name,max,cells:[各家分]}]}`。
- compare `result.recommended`（可 null）+ `provisional` + `warnings[]` → report 页"推荐中标人 / 暂定 / 告警"。

## 3. 前端动作 ↔ 后端调用映射

### create 屏（startReview）— 关键 gap
前端是"1 招标文件 + N 家投标一次提交"，后端是"建 project + 逐家追加 evaluate"。`startReview` 改为：
1. `POST /tender/projects`（title/tender_no 可从招标文件名或留空，funding_type 可加表单项）→ 得 `project_id`。
2. **对每个 uploadBidder**：`POST /tender/projects/{project_id}/evaluate`（multipart upload，**该家投标文件 + 招标文件一起传**——后端单家评标要读招标文件出 criteria）→ 得各 `request_id`。
3. 轮询每个 `GET /tender/tasks/{request_id}` 直到 `completed`/`failed`（替代 mock 进度条；progress = 完成数/总数）。
4. 全 completed 后（≥2 家）：`POST /tender/projects/{id}/compare` → 轮询 `GET /tender/projects/{id}/compare`。
5. 进 analysis/report。

### 其它屏
- **dashboard**：`GET /tender/projects` → `buildDashboardSummary`（前端现有逻辑，喂真实列表）。
- **history**：`GET /tender/projects?status=` 或前端 filter（`filterReviewHistory` 复用）。
- **analysis · detail**：`GET /tender/projects/{id}/results/{request_id}`（单家完整结论：criteria/scoring/evidence）。
- **analysis · compare**：`GET /tender/projects/{id}/compare`（横比表 + 排名）。
- **report**：compare result（推荐/排名/告警）。

## 4. 异步轮询模式
- evaluate/compare 返回 `{request_id, task_status_url}`，不直接给结果。
- 轮询 `GET /tender/tasks/{request_id}`（评标）或 `GET /tender/projects/{id}/compare`（横比）直到 `status=completed`（或 compare 的非 404）。建议 2–3s 间隔，前端用 TanStack Query 的 `refetchInterval`。
- evaluate 完成后取详情走 `/tasks/{request_id}/result` 或 `/projects/{id}/results/{request_id}`。

## 5. 错误 / 边界语义
- `400`：compare 不足 2 家完成 / directory 路径非法。
- `404`：project / task / 结果不存在。
- `409`：删/重试 running 任务；compare 已在进行中（防重）。
- `503`：评标队列满（准入闸）→ 前端提示"稍后重试"。
- compare `stale:true`：追加投标 / 重评后旧横比过期 → 前端提示"投标人有变化，请重新横比"，**不展示陈旧推荐**。
- compare `result.provisional:true` / `recommended:null`：未满足终局推荐条件（非国有资金 / 异常低价 / 有效投标<3）→ report 显示"暂定排名，定标由招标人依法确定"+ `warnings`。

## 6. 边界与不做
- **不改后端**：契约已 ship、稳定。前端缺的派生字段（score/progress/riskCount）在前端算，不要求后端加。
- **不改 types.ts 结构**（金标准）；如确需补字段（如 funding_type 表单），最小新增。
- mock-data.ts 保留作 Storybook/测试 fixture，但页面数据来源切真实 API。
- 验收：`bun run lint` + `bun run test` + `bun run build` 通过；create→评标→横比→report 端到端跑通（连真实后端 `uv run python -m server.cli serve`）。

## 7. 给 codex 的执行提示
- 复用 `features/audit/api.ts` 的认证/错误/url 工具，新建 `features/contract/tender-review/api.ts`。
- 用 TanStack Query（项目已用）做 list/detail/轮询。
- `use-tender-review-page.ts` 的 mock 状态（projects/summary/history）改为 query 数据；`startReview` 改为 §3 的真实多步流程。
- 保持前端域边界（contract/tender-review），不碰其它 feature。
