# Root Cause

`server/ocr/classify.py` only treated `.docx` as Word. Legacy `.doc` was not routed to
`native`, so `server/ocr/pipeline.py` returned a manual result and rendered only the
placeholder header into `tender_project_docs.ocr_text`.

That made the downstream `.claude/commands/tender-extract-info.md` JSON-only contract
work with almost no source context. The `JSONContractError` was therefore a secondary
symptom, not the root parser/model failure.

## Code Evidence

- `server/ocr/classify.py`: `WORD_EXT` contained only `.docx`.
- `server/ocr/native.py`: `native_read()` dispatched `.docx`, Excel, PDF, and text,
  but had no legacy Word reader.
- `server/routes/tender.py`: project document OCR writes `ocr_text` first, then injects
  that text into `tender-extract-info`; empty/manual OCR therefore directly poisons
  criteria extraction.

## Fix Strategy

Route `.doc` as `word/native/legacy_word`, then read it with platform-native text
extractors before any OCR fallback:

1. macOS `textutil`
2. Linux `catdoc`
3. `antiword`
4. UTF-16LE embedded text fallback

The Docker OCR image installs `catdoc` so Linux production does not rely on the noisy
Python fallback.
