# Fix Note

## Changes

- `server/ocr/classify.py`: added `.doc` as legacy Word and routed it to
  `route=native`, `handler=legacy_word`.
- `server/ocr/native.py`: added `read_legacy_word()` and wired `.doc` through
  `native_read()`.
- `Dockerfile`: installs `catdoc` when `WITH_OCR=1`.
- Tests added for `.doc` classification and UTF-16LE fallback extraction.

## Local Data Cleanup

Backed up SQLite before clearing stale tender/OCR state:

- Backup: `logs/platform.sqlite3.bak-before-legacy-doc-ocr-20260625T131308`
- Cleared tables: `tender_projects`, `tender_tasks`, `tender_project_docs`,
  `tender_bid_docs`, `tender_compare_tasks`, `tender_compare_results`
- Cleared paths: `data/submissions/default/tender/*`, `data/ocr-cache/*`

Post-cleanup counts:

```text
tender_projects          0
tender_tasks             0
tender_project_docs      0
tender_bid_docs          0
tender_compare_tasks     0
tender_compare_results   0
default/tender entries   0
ocr-cache files          0
```

## Verification

Real sample after cache cleanup:

```text
word native legacy_word 38995 True True
### 文件: 招标人ZJ网院直播间建设项目公开招标文件.doc (kind=word, route=native)
block_len=39058
manual_placeholder=False
```

Commands:

```bash
uv run pytest -q tests/test_ocr_classify.py tests/test_ocr_pipeline.py::test_read_legacy_word_utf16_fallback_extracts_text tests/test_ocr_pipeline_mixed_pdf.py
uv run pytest -q tests/test_ocr_pipeline.py
uv run pytest -q tests/test_tender_upload_routes.py tests/test_ocr_classify.py tests/test_ocr_pipeline.py
uv run ruff check server/ocr/native.py server/ocr/classify.py tests/test_ocr_classify.py tests/test_ocr_pipeline.py
```

Results:

```text
26 passed
48 passed, 5 warnings
73 passed, 6 warnings
All checks passed
```
