# R1 设计 · 招标信息抽取前移 + 区1/区2 显示

> Sprint: 2026-06-22-multimodel-tender-optimization · Round 1/6
> Path: System（后端 + 契约 + 前端）· 并入 bug B-A/B-B、遗留 ②⑤

## 背景（WHY）

「分析中」页（`analyzing-view.tsx`）三区里：
- **区1 基本信息** 只读用户手填 `projectForm`，默认大片空（B-A）。根因：`tender_projects` 元数据从不由 OCR 回填。
- **区2 OCR 识别区** 只显示状态圆点 + 占位（B-B）。根因：`docs-status` 仅回 `ocr_status`；招标信息（评分项/扣分点/废标/控制价/招标人）只在评标 worker S1 抽、评标后才回填 `tender_project_docs.criteria`、且**无读接口**。
- 用户核心诉求：招投标审核**数据准确 + 扣分项准确**。criteria 是评分命脉，越早抽出来越能复用、越能让用户在分析中就看到「抓到了哪些评分点/扣分点」。

现状（Explore 核实）：上传 → `_run_project_doc_ocr`(`tender.py:612`) 只产 `ocr_text`；criteria 仅 `tender_worker.py:291` 评标后 `_backfill_criteria`（首写赢、无读接口）；`tender_projects` 元数据只来自建项目表单。

## 方案（HOW）

**把「招标信息抽取」从评标 worker 前移到 tender-doc OCR 完成之后**，独立状态跟踪，存库 + 开读接口 + 前端展示。OCR ready 立即解锁「开始分析」（不阻塞），招标信息抽取作为独立后台增强（区2 单独轮询）。

### 备选与取舍
- **A（选定）上传后独立抽取**：tender-doc OCR ready → 后台跑一次聚焦抽取（仅招标文件，无投标、无评分）→ 存 criteria + tender_info。优点：分析中即可见、criteria 项目级单次解析、各家评标复用一致 criteria（治②、对齐 command「同一招标 criteria 须一致」）。代价：上传后多一次 Claude 调用（但**仅 1 次/项目**，并让各家评标 S1 可跳过 → 净省）。
- B 复用评标后回填的 criteria：零新增调用，但只在首家评标后才有、元数据仍空、分析中看不到 → 不满足诉求。否决。

### 后端改动

1. **新命令 `.claude/commands/tender-extract-info.md`**（聚焦单趟抽取，复用 `tender-evaluate.md` S1 定位指令 + criteria.schema）：
   - 输入：服务端注入「招标文件 OCR 底稿」context（已有 `prewarm_and_text` 文本）。
   - 输出**单个 JSON** `{criteria, tender_info}`：
     - `criteria` 对齐 `.claude/contracts/tender/criteria.schema.json`（source_ref/method/total_max/items[score_mode+deductions/bands/awards/formula_spec]/rejection_rules）——把评分项/满分/**扣分点逐条**/废标条款一次抽全。
     - `tender_info` 对齐**新契约** `.claude/contracts/tender/tender-info.schema.json`：`{tender_no?, project_name?, tenderee?, control_price?, method?, funding_hint?}`（全 optional string，缺则省）。
   - 复用 S1 护栏：直读即权威、定位不到 → criteria 降级标注、绝不臆造。不读投标、不评分。
2. **schema 迁移**（`tender_doc_store.py` `_initialize_schema` 幂等 ALTER）：`tender_project_docs` 加
   - `criteria_status TEXT NOT NULL DEFAULT 'pending'`（pending→running→ready|failed，独立于 ocr_status）
   - `tender_info TEXT`（JSON，可空）
   既有 DB 用 `PRAGMA table_info` 探测后 `ALTER TABLE ADD COLUMN`（对齐现有"add missing columns"注释约定）。
3. **store 新函数**：
   - `update_project_doc_criteria_extracted(project_id, tenant, *, criteria_json, tender_info_json, status)` 一次写 criteria+tender_info+criteria_status。
   - 复用现 `update_project_doc_criteria`（评标后回填仍首写赢，与上传抽取不冲突：上传先写则评标 no-op）。
4. **`_run_project_doc_ocr` 链式增强**：OCR ready 写库后，**置 criteria_status=running**，再 `await` 一次 `_extract_project_doc_info`（新协程）：调 `run_command_json("tender-extract-info", case_path, context=ocr底稿, structured=False, effort=低/默认)` → 解析 `{criteria, tender_info}` → `update_project_doc_criteria_extracted(status=ready)`；异常 → criteria_status=failed（**绝不影响 ocr_status=ready / 开始分析**）。
   - tender_info 回填项目表：新 `tender_project_store.update_project_fields_if_empty(project_id, tenant, fields)` —— **只填空字段**（用户手填优先），auto 填 tender_no/tenderee/control_price/method。
5. **新读接口** `GET /tender/projects/{id}/tender-doc`（tenant 作用域）：
   `{ocr_status, ocr_clarity, criteria_status, criteria(obj|null), tender_info(obj|null), tender_files[]}`。
6. **docs-status 增 `criteria_status`**：`tender_doc` 加该字段（前端现有轮询可顺带感知抽取进度，向后兼容）。
7. **评标 S1 复用（治②，轻量）**：`tender_worker._run_evaluation` 若 `get_project_doc` 有非空 criteria → 在 context 注入「已解析评分标准 criteria(JSON)，S1 直接采用、勿重解析」。不动 command 主体，仅加注入段 + 一行指令。降级安全：无 criteria/异常 → 原 S1 流程。

### 契约改动
- 新增 `.claude/contracts/tender/tender-info.schema.json`（小对象，全 optional）。
- criteria 沿用现 schema。抽取命令输出 `{criteria, tender_info}` 仅服务端解析取两键，不新增顶层契约。

### 前端改动（用户本 Sprint 显式纳入 frontend，覆盖 gotchas 的 out-of-scope 默认）
1. `api.ts`：加 `getTenderDocInfo(projectId): TenderDocInfoResponse`；新类型 `TenderCriteria`/`TenderCriteriaItem`/`TenderInfo`/`TenderDocInfoResponse`（镜像 criteria.schema 关键字段）。
2. `use-tender-review-page.ts`：analyzing/analysis 屏时查新接口（`enabled` + criteria_status!=ready 时 `refetchInterval` 2.5s）；透传 `tenderDocInfo` 给 ScreenContent→AnalyzingView。
3. `analyzing-view.tsx`：
   - **区1**：fallback 链 `tenderInfo → projectForm`；criteria_status=running 时空字段显「识别中…」而非消失。
   - **区2**：OCR 状态 + criteria 抽取状态 + 就绪后渲染**招标信息**：`method`/`total_max`、`items[]`（评分项 + 满分 + score_mode 徽章 + 扣分点条数/档次数）、`rejection_rules` 条数。这就是用户要的「招标信息区域」。
4. UI 遵循 `ui-guidelines`：4 态（loading/empty/error/ready）、a11y label、8px 网格。

## 影响范围
- 后端：`server/routes/tender.py`、`server/routes/tender_worker.py`、`server/stores/tender_doc_store.py`、`server/stores/tender_project_store.py`、新 `.claude/commands/tender-extract-info.md`、新 `.claude/contracts/tender/tender-info.schema.json`。
- 前端：`agent-front/src/features/contract/tender-review/{api.ts,use-tender-review-page.ts,components/{analyzing-view,screen-content}.tsx,types.ts}`。
- DB：`tender_project_docs` 加 2 列（幂等迁移，旧库自动 ALTER）。

## 风险与缓解
- **上传后多一次模型调用**（成本/延迟）→ 仅 1 次/项目，独立后台不阻塞「开始分析」；并让评标 S1 复用→净省；3 模型自测对比耗时。
- **抽取质量随模型波动**（qwen/deepseek/opus 差异）→ criteria_status=failed 时区2 显「招标信息识别失败，可重试/以评标结果为准」，不卡死；评标 S1 降级仍能自解析。
- **schema 迁移破坏旧库** → 幂等 ALTER + 既有行 criteria_status 默认 pending（旧项目重新上传才触发抽取，不回溯）。
- **first-writer 冲突**（上传抽取 vs 评标回填）→ 上传先写则评标 `_backfill_criteria` 命中"已存非空"no-op，天然兼容。

## 验收标准
1. `uv run pytest -q` 全绿（新增 store 迁移/新函数、route、worker 注入单测）+ `ruff check .`。
2. 前端 `bun run lint && bun run build` 绿。
3. 接口自测（serve + curl，dogfood case `data/submissions/default/tender/tp-*/case`）：
   - 上传 tender-doc → `docs-status` 短时内 `ocr_status=ready`（不被抽取阻塞）→ `criteria_status` 由 running→ready。
   - `GET .../tender-doc` 返回非空 `criteria.items`（含 deductions/score_mode）+ `tender_info`；`Σitems.max == total_max`（自检）。
   - `tender_projects`（GET project）空元数据被 OCR 值回填、手填字段不被覆盖。
4. **3 模型轮换**（DeepSeek/qwen/opus 各一遍）：记录抽取耗时、criteria 项数、total_max 一致性、扣分点条数到本 design「自测结果」节。
5. 区1 显示 OCR 派生元数据；区2 显示评分项/扣分点/废标（非占位）。视觉美观待用户 mac dev 确认。

## 自测结果（3 模型轮换接口自测，dogfood 华为南通标书）

| 模型 | criteria 耗时 | 状态 | 评分项 | Σmax=total | 废标条款 | score_modes | 备注 |
|---|---|---|---|---|---|---|---|
| qwen3.7-max | 163s | ✅ ready | 14 | ✅ 100=100 | 18 | additive/banded/formula/manual | tender_info+回填全中；非确定性，多跑 modes 略变 |
| deepseek-v4-pro | **142s** | ✅ ready | 14 | ✅ 100=100 | **27** | +deduction | **覆盖最佳**（废标最多+有 deduction），最快 |
| claude-opus-4-8 | 268s | ❌ failed | — | — | — | — | **anyrouter 429/Service Unavailable**（基建非代码）；优雅降级 criteria_status=failed |

**结论**：抽取机制三模型验证通过（2/3 出合格 criteria，OCR 3s 不阻塞开始分析✅，Σmax 自检全过✅，tender_info+项目回填✅）。opus 失败=anyrouter 限流（goal 已记"偶发429"），系统优雅降级（criteria_status=failed→评标自行 S1+区2显"识别失败"），非代码缺陷；重试可恢复。

**关键教训（接口自测抓到、单测漏掉）**：
1. `schema_name=None` 不跳校验反而 `CONTRACTS_DIR/None` 崩 → 单测 mock 了 run_command_json 看不到（codex 也独立指出 P1/P2）。修：apply_schema_semantics 空名 passthrough + structured 守卫。
2. 模型在 enum 上**普遍漂移**（qwen 一次输出三处：method=综合评分法/tag=cross_bid/rounding=内插法）→ 整份 jsonschema all-or-nothing 会因一叶误杀整套 14 项合格 criteria。改为 enum 归一化 + 承重**结构** sanity 检查（有评分项+各项有名+满分为数），容忍叶子瑕疵、挡真垃圾。
3. proxy（all_proxy/SOCKS）会被 httpx 自动吃 → 本地自测 client 须 trust_env=False + curl --noproxy。

## codex + 交叉审查（reviewer+spec-compliance）findings 处置
- codex P1（criteria 注入评标前未校验）→ 已加结构 sanity 检查 + tender_info jsonschema 校验。
- codex P2（schema_name=None 仅限 structured=False）→ run_agent_json 显式守卫 + 测试。
- reviewer F1（running 写失败误覆写 ocr=ready→failed）→ running 写移出共享 try、独立容错。
- reviewer F2（OCR 失败 criteria_status 留 pending→前端无限轮询）→ OCR 失败也置 failed。
- reviewer F3（崩溃后 pending 悬空）→ GET 端 ocr_failed+非终态 推断 failed（+测试）。
- reviewer F4（worker 裸同步 SQLite 读阻塞 loop）→ asyncio.to_thread。
- reviewer F5/F6（冗余 import / import 分组）→ 清理。
- spec-compliance：**PASS**（14 项设计全实现，0 MISSING；D1 校验改结构检查有据、D2 analysis 屏不消费无害）。
