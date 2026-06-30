# Tender 域代码审计（2026-06-26，只读）

> 目的：为「整理招投标审核域」提供事实底稿。**只读盘点，未改任何代码。**
> 范围：`.claude/{commands,agents,skills,contracts}/tender*` + `server/{routes,stores,common,ocr}` 的 tender 面。

## 体量速览

| 文件 | 行数 | 备注 |
|---|---|---|
| `server/routes/tender.py` | 1370 | god-file，含 ~440 行 ops 逻辑 |
| `server/common/output_contracts.py` | 930 | 共享 expense+tender，tender 专属 ~400+ 行 |
| `server/common/evidence_resolution.py` | 642 | 共享 infra（OCR/boq + output_contracts），非 tender 专属 |
| `server/routes/tender_worker.py` | 538 | 评标 worker |
| `server/stores/tender_*` | 367+325+166+40 | 4 个 store（doc/project/compare/task） |

## 排序发现

### F1 🔴 `tender.py` god-file：ops 业务逻辑困在 routes 层
- **证据**：683–1091 行有 **364 行** OCR/criteria 抽取 ops 逻辑；顶部 97–177 还有 OCR task 编排（`_track_upload_ocr_task`/`_cancel_project_ocr_tasks`）。合计 ~440 行**非路由**逻辑：
  `_is_ocr_text_valid` / `_criteria_looks_usable` / `_normalize_criteria_enums` / `_sanitize_tender_info` / `_extract_project_doc_info` / `_run_project_doc_ocr` / `_run_bid_doc_ocr` / `_start_*_ocr_task`。
- **违反**：自家决策 `app→routes→ops→features→core→common→stores→platform`（[ops-below-routes](../../compound/2026-06-19-decision-ops-below-routes-layering.md)）。
- **修复**：下沉到 `server/ops/tender_doc_pipeline.py`（criteria/OCR 抽取）+ `server/ops/tender_ocr_tasks.py`（task 编排）。路由只留 HTTP 编排。
- **风险**：低（纯移动；`tests/test_layering.py` 有守卫；零行为变更）。**收益**：1370 → ~880；管线可独立单测。**工作量**：中。

### F2 🟠 `output_contracts.py`：tender 专属逻辑混在共享 common
- **证据**：tender-only ~400+ 行混在 expense 也走的文件里——`_verify_score_mode_consistency`（575–767，**192 行**）、`_finalize_user_explanation` 链（107–378）、`_has_*_disqualification`/`_has_failed_eligibility`、`_strip_unknown_policy_refs`。
- D0 已用 `_is_tender_explanation_output` 运行时隔离，但**结构上仍同住**——正是 D0 那类跨域污染的温床。
- **修复**：抽 `server/common/tender_output.py`（或 `features/tender/output.py`），`normalize_audit_result` 按 domain 分派。
- **风险**：中（共享入口，须保 expense 路径零变更 + 回归测试）。**收益**：共享 common 瘦身，根治 D0 类风险。**工作量**：中。

### F3 🟠 store 样板重复（项目级 DRY，非仅 tender）
- **证据**：`_initialize_schema` × 10 文件、`connect_sqlite` × 11、`new_*_id` × 4、`_utc_now` × 3。tender 4 store 各自重复；`tender_task_store` 仅 40 行（`TaskStore` 的 1 函数包装 `list_tender_tasks_by_project`）。
- **修复**：抽 `server/stores/_base.py`（schema init + utc_now + id 工厂）；`tender_task_store` 并入 `task_store` 或 project 查询。
- **风险**：中（动 10+ store 初始化）。**收益**：去样板。**注**：跨域、面广，可独立于 tender 单独排期。**工作量**：中–大。

### F4 🟡 `.claude` 提示词重复：S1 两处维护
- `tender-extract-info.md` 标称"完全复用 tender-evaluate S1"，实为**复制**——S1 定位逻辑两处维护、易漂移。
- **修复**：抽共享 S1 片段（skill reference / include 单一权威）。**风险**：低。

### F5 🟡 27 处 兜底/遗留/workaround 注释 — 集中 triage
- 4 个主文件累计 27 处。部分合理（并发闸/超时/线程不可取消的说明），部分可能是可消除的临时补丁（"遗留①②③④"）。逐条复核，能消的消、该留的补成正式注释。

## 审计澄清（✅ 非问题 / 勿误删）

- **review-delta / tender-reviewer 是 dormant-by-design，不是死代码**：`review_delta_store` 只有读 + `archive_*` 写函数、当前无 live 调用方，但 [CLAUDE.md](../../../.claude/CLAUDE.md) 明确文档了 `SECOND_REVIEW_ENABLED=true` + 重注册 hook 的**重启路径**。**保留，勿删**（删了会断重启通道）。expense-reviewer 同源。
- **5 个 tender schema 均有引用**（criteria 6 / extract-result 9 / compare-result 2 / tender-info 2 / review-delta 3），无 orphan schema。
- **`evidence_resolution.py`** 是 OCR/boq + output_contracts 共享 infra，非 tender 专属——不纳入本轮 tender cleanup。

## 建议路线（分批，每批独立可 ship）

| 批次 | 内容 | ROI/风险 |
|---|---|---|
| **A（推荐先做）** | F1 `tender.py` 拆分（routes/ops 分层） | 最高 ROI / 最低风险（有守卫、零行为变更） |
| B | F2 `output_contracts` tender 抽离 | 高（根治跨域污染），中风险 |
| C | F4 + F5（.claude S1 去重 + 注释 triage） | 轻量 |
| D（可选/跨域） | F3 store DRY 基座 | 面广，可独立排期 |

## 本轮明确不做

- review-delta 清理（dormant-by-design）。
- `evidence_resolution` 重构（共享 infra，非 tender）。
- 任何**行为/判分逻辑变更**——本轮纯结构整理 + 文档/注释，保业务输出不变（每批以 `uv run pytest -q` 全绿 + 关键路径回归守住）。
