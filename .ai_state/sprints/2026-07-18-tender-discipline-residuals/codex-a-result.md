已完成并提交：

- TA0：SDK `0.2.88` API 与命令形态一致；`bypassPermissions` 下 `PreToolUse` deny 真生效，Bash 无副作用。
- TA1/TA2：完成 `case_root` 透传、realpath 子树校验、页码校验、shell 元字符拒绝、Bash 受控加回。
- TA3：注入、追加攻击、穿越、跨案、symlink、非法页码全部 deny；合法路径 allow。
- TA4：已接线 `tender-eval` 文档，要求低清页先 OCR 重识别并保留 `【第N页】` 页锚。

验证：

- `903 passed`
- `ruff check .` 通过
- 分支：`d11-batch-a`
- Commit：`9dee52a feat(security): gate tender ocr-page Bash calls`
- 未 push、未触碰 main。

`.ai_state` 自动状态文件未纳入本次 commit。