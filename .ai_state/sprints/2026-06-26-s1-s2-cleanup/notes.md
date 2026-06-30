# S1 + S2' Cleanup Notes

## 改动

- S1: 在 `server/platform/sqlite_store.py` 新增公开 `utc_now()`，并让 `tender_project_store.py`、`tender_doc_store.py`、`tender_compare_store.py` 复用它；删除三处私有 `_utc_now()`。
- S2': 新增 `.claude/skills/tender-eval/references/s1-locate-criteria.md` 作为 S1 定位线索与排除的单一权威；四个 `.claude` 入口改为引用该文件，保留 S3 评分权威与不臆造护栏。
- 注释 triage: 仅整理 `server/common/output_contracts.py`、`server/common/evidence_resolution.py` 的历史版本号式注释，未改判定逻辑或输出字符串。

## 验证

- `uv run pytest -q` -> `727 passed, 8 warnings in 3.57s`
- `uv run ruff check .` -> `All checks passed!`
- 相关子集：`uv run pytest -q tests/test_tender_doc_store.py tests/test_tender_compare.py tests/test_tender_info_extraction.py tests/test_tender_upload_routes.py` -> `73 passed, 1 warning in 0.75s`

## 取舍

- `tender_task_store` 并入与 `_initialize_schema` 合并按路线图留 backlog，本轮未做。
- 新 worktree 首次 `uv run pytest -q` 缺 OCR extra 依赖 `fitz`；执行 `uv sync --extra ocr` 后，最终门禁命令按要求原样通过。
- `evidence_resolution` 的低置信用户可见 note 中保留既有 `(R3)` 字符串，避免注释整理引入行为/输出变更。
