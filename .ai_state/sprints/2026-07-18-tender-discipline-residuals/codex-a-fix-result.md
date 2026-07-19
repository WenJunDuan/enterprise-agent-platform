已完成并提交，未 push。

- Test A：`hook_calls=1`，`marker_created=False`；证明 `bypassPermissions` 下 deny 生效。
- Test B：`hook_calls=1`，`marker_created=False`；生产 `ocr-page` hook 拒绝非 OCR Bash。
- 无网关环境：A/B 均正确 `skip`。
- `903 passed, 2 skipped`；`uv run ruff check .` 通过。
- 围栏逻辑未改动，仅新增测试与 `runner.py` 注释。

Commit：`f0424e1` `test(security): prove ocr-page hook denies Bash under bypass`