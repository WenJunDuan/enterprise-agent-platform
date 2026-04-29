# Codex Handoff — T-001: 路径模型统一清理

## 目标

清理项目中已过时的 `data/case*` 路径示例引用，统一为当前仓库实际目录模型
（测试数据在 `tests/fixtures/`，真实制度源材料在 `knowledge/external/`）。

## 背景

`data/` 目录是历史压测目录，不是当前仓库的正式测试数据组织方式。
当前真实目录示例应引用 `tests/fixtures/expense/travel-missing-preapproval/`。

## 当前发现的残留引用

### 文件 1: `README.md`（10 处）

| 行号 | 内容 |
|---|---|
| 171 | `uv run python -m server.cli audit data/case1` |
| 172 | `uv run python -m server.cli audit-json data/case1` |
| 309 | `"directory_path":"data/case1"` |
| 534 | `uv run python -m server.cli audit-json data/case1` |
| 543 | `"directory_path":"data/case2"` |
| 550 | `- data/case2 到 data/case9：相对合法样例` |
| 551 | `- data/case10 到 data/case13：缺件或缺文件` |
| 552 | `- data/case14 到 data/case17：脏数据或越界` |
| 553 | `- data/case18 到 data/case21：重复、冲突、脏文本、伪文件` |
| 555 | `详细场景见 data/scenario-index.json。` |

### 文件 2: `.claude/commands/audit.md`（2 处）

| 行号 | 内容 |
|---|---|
| 41 | `用法: /audit data/case1` |
| 42 | `目录示例: /audit data/case1` |

## 修改要求

### README.md

1. 命令示例（L171, L172, L534）：将 `data/case1` 改为 `tests/fixtures/expense/travel-missing-preapproval`
2. JSON payload 示例（L309, L543）：将 `"directory_path":"data/case1"` / `data/case2` 改为 `tests/fixtures/expense/travel-missing-preapproval`
3. 压测样例章节（L550-L555）：删除或替换整个"压测样例"子章节说明
   - 当前仓库不再有 data/case2~case21，也不再主推 batch 能力
   - 应改为说明：测试用 fixture 数据在 `tests/fixtures/`，真实报销材料放 `knowledge/external/` 或由用户自建目录

### `.claude/commands/audit.md`

1. L41-L42：将 `data/case1` 改为 `tests/fixtures/expense/travel-missing-preapproval`

## 约束

- 不改动 `server/` 代码
- 不修改 `data/` 目录（目录可能已在 .gitignore 或用户机器上存在）
- 只改文档/命令定义中的路径示例

## 验收标准

- `grep -r "data/case" README.md .claude/commands/` 返回零结果
- `grep -r "raw_policies" README.md .claude/commands/` 返回零结果
- `grep -r "batch-audit\|batch_audit" README.md server/ .claude/` 返回零结果
- 修改后的 README.md 可读性不低于当前版本
- `uv run ruff check .` 通过（纯文档修改，不影响 Python）
