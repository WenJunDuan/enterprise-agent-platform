# Tender 评标 Harness — 执行计划（Claude Code 接手）

> 自包含执行清单。设计见同目录 design.md。**先读 design.md 的"已知坑"再动手。**
> 项目约定：`uv run pytest -q` / `uv run ruff check .`；line-length=100；py312。
> 分层：app→ops→routes→features(audit|ocr)→common→stores→platform；feature 互不 import。

## 现状（已完成，勿重复）

- 域 `tender` 已注册；agents/契约/skill/规则/`/evaluate-bid` 命令均就位且校验通过。
- 入口现状：`/evaluate-bid` 命令可经 `run_command_full("evaluate-bid", 目录)` 跑（CLI/命令）。
- **本 sprint 要做的是"路由 + CLI + 端到端验证 + 测试"，把命令接到 HTTP，并在真材料上跑通。**

## 任务（按序）

### T1 · CLI 子命令 `evaluate-bid`
- 文件：`server/cli.py`
- 做法：镜像现有 `audit` 命令，加 `@app.command("evaluate-bid")`，调 `run_command_full("evaluate-bid", path, conversation_id=...)`；同时加 `evaluate-bid-json`（如 audit-json）走 `run_command_json(..., schema_name="common/audit-result.schema.json")`。
- 验收：`uv run python -m server.cli evaluate-bid --help` 可见；ruff 过。

### T2 · HTTP 路由 `/tender/evaluate`（异步任务，镜像 /audit/submit）
- 文件：`server/routes/tender.py`（新）、在 `server/api.py` `include_router(prefix="/tender")`。
- 端点：`POST /tender/evaluate`（directory + multipart 双模式，`verify_tenant` 走 `server.routes.deps`）；`GET /tender/tasks/{request_id}`；`GET /tender/tasks/{request_id}/result`。
- 任务存储：**优先复用** `server/stores/audit_task_store.py`（`mode="tender"`/`source_mode` 区分）；若字段不够再新建 `tender_task_store.py`（**严格镜像** audit_task_store：dataclass + `_initialize_schema()` import 时建表 + `INSERT OR REPLACE` 合并 upsert + `connect_sqlite(immediate=True)`）。
- 后台执行：`server/routes/tender_worker.py`（新，镜像 `audit_worker.py`）：信号量 + 超时 + 调 `run_command_json("evaluate-bid", case_path, schema_name="common/audit-result.schema.json")` → 写 results 表。
- **分层**：route/worker 属上层，可调 `server.common.command_adapter`、`server.stores.*`、`server.platform.*`；**不要**新建会被 feature 守卫拦的 `server/tender` 模块。
- 验收：`uv run pytest -q` 新增 `tests/test_tender_routes.py`（镜像 `test_ocr_routes`/`test_routes_smoke`）绿；`test_routes_do_not_import_app_module` 不退化。

### T2.5 · 关掉 item0 延后的 ops/routes 层序决策（整合项，roadmap 前移）
- 背景：item0 复核把「`ops` 相对 `routes` 层序 + 补守卫」延后到「Phase 1 第一次碰 `routes/`」。tender 路由是后重构第一个新路由 → 在此一并定（来源 `sprints/2026-06-19-review-backend-refactor/reviews/summary.md` 延后段 + 門禁#5，R2-F1/F3/F4）。
- 决策：定 `ops` 相对 `routes` 的层序（`health` 路由合法地需要 `diagnostics`(ops)）；定稿写入本 sprint `design.md` 一行附注。
- 修：3 处上向 import 改直连源模块 —— `server/routes/health.py:12`、`server/ops/diagnostics.py:9`、`server/routes/audit.py:17`。
- 补：`tests/test_layering.py` 增 ops/stores 守卫（现实测 4 条、ops/stores 零守卫）。
- 验收：`uv run pytest -q` 的 `test_layering` 全过且新增守卫生效；无新增上向 import。
- 注：tender 与 contract-api 共享的基座决策，**只在此做一次**，contract-api(Phase 2b)直接受益。

### T3 · 测试与回归
- 新增：`tests/test_tender_routes.py`（提交→202/accepted、查任务、查结果路径；directory 模式用 fixture）。
- 结构校验：把"`/evaluate-bid` 引用的契约/规则文件存在、`manual_review_reason` 枚举与契约一致"做成一个轻量测试（可参考本 session 的校验脚本）。
- 验收：全量 `uv run pytest -q` 绿；`uv run ruff check .` 全过；`test_layering` 全过。

### T4 · 端到端（需用户提供真招标文件 + 投标文件）
- 步骤：把真招标文件 PDF 放 `knowledge/external/` → `/init-rules <招标文件> tender` 生成 `knowledge/tender/{招标编号}.rules.json`（**覆盖** r2024007 样例，confidence 升到 high）→ 放投标文件到一个目录 → `/evaluate-bid <目录>`（或 `POST /tender/evaluate`）。
- 验收（DoD）：产出符合 `common/audit-result`；不可判定项（答辩/信用/价格）为 `manual_review`/`score:null`、**非 0**；业绩 PM≠拟派 PM 命中 `data_conflict` 且 evidence_chain 同引两处出处；`policy_refs` 为命中的 `rule_id`。
- 可选：把该案做成 golden fixture（`tests/eval_fixtures/`，参考 `golden_manifest.json` + `server/audit/eval.py`）。

## Definition of Done（整体）

- [ ] `uv run pytest -q` 绿（含新增 tender 路由测试 + 分层守卫）
- [ ] ops/routes 层序决策定稿 + 修 3 处上向 import + 补 ops/stores 守卫（T2.5，item0 延后项关闭）
- [ ] `uv run ruff check .` 全过
- [ ] `/tender/evaluate` 提交→轮询→取结果 跑通（TestClient）
- [ ] `/evaluate-bid` 在一份真标上端到端产出 audit-result，且 manual_review 不判 0、一致性 data_conflict 成立
- [ ] 不新增违反分层的 import；不复活 meta.json/by-request 文件树

## Backlog（本 sprint 不做，记着）

- 余下 statute：招标投标法顶层 → `statute-bidlaw`；实施条例 ch4(评标否决/定标 49-56)；政府采购法 + 87号令 → `govproc-law` / `govproc-87`（政采综合评分法，与工程那套分开建）。
- 多投标人 S5：价格横比/排序/有效投标数，把 `requires_cross_bid_comparison` 项落定。
- 程序合规 v2：资格审查/一票否决/串标围标自动识别。
- 小修：`rule-init/SKILL.md` 第5步 rule_id 点号→下划线；`audit-result.risk_dimensions.name` 加 tender 维度（价格/资格/业绩/一致性）。
