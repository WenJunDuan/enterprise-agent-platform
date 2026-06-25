# Fix Note — Tender Score Summary

## 改动

- `server/common/output_contracts.py`
  - 新增用户可见说明兜底：
    - 清理 `manual_review`、`cross_bid`、`score_mode` 等内部字段名。
    - 删除模型自写的末尾合计段。
    - 按 `extracted_data.scoring` 重新追加“得分小结”。
- `.claude/commands/tender-evaluate.md`
  - 明确最后说明不得出现内部字段名或英文技术词。
  - 要求小结不重复复杂手算，逐项分数以 `scoring[]` 为准。
- `server/stores/tender_doc_store.py`
  - `update_project_doc_criteria()` 写入 criteria 时同步置 `criteria_status='ready'`。
- 测试补充：
  - 用户可见说明清洗与得分小结重算。
  - criteria 回填状态变为 ready。

## 验证

```bash
uv run pytest -q tests/test_tender_criteria_flow.py tests/test_core_pure.py tests/test_tender_doc_store.py tests/test_tender_p3_backend.py tests/test_tender_info_extraction.py
```

结果：

```text
187 passed, 1 warning
```

```bash
uv run ruff check server/common/output_contracts.py server/stores/tender_doc_store.py tests/test_tender_criteria_flow.py tests/test_tender_doc_store.py tests/test_tender_p3_backend.py
```

结果：

```text
All checks passed!
```

