"""审核业务域：内联审核 runner、golden-case 评测。

- runner.py   内联目录审核（材料 + 规则预载入一个 prompt，单跳）
- eval.py     golden-case 回归评测集

输出契约（schema 加载 / 归一 / 校验）是平台共享脚手架，已下沉到
`server.common.contract`；本包只承载审核业务流程，不再持有契约实现。
对外稳定入口仍是 `server.core` facade。
"""
