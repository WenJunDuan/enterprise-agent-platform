"""审核业务域：内联审核 runner、JSON 契约、golden-case 评测。

- runner.py   内联目录审核（材料 + 规则预载入一个 prompt，单跳）
- contract.py 审核输出 JSON 契约（schema 加载、归一、校验）
- eval.py     golden-case 回归评测集

对外稳定入口仍是 `server.core` facade；本包是其实现归属。
"""
