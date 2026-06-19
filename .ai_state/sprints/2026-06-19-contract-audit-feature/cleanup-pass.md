# Polish Pass · contract-audit-feature (System path 强制)

> 范围：本 sprint 新增/改动代码（contract_store / cli review-contract / legal schema / review-contract 命令）。
> 规则：coding-standards / doc-style / security-checklist。

## 扫描结果

| # | 项 | 等级 | 处置 |
|---|---|---|---|
| 1 | `cli.review_contract_json` docstring 中英混排（"to the库"） | P2 | **已修**：规范为纯英文 "...persist the contract to the local store." |
| 2 | 公开 API docstring | P1 | 通过：`persist_contract_from_result` 有完整 Args/Returns；store 函数有摘要；CLI 命令有 docstring |
| 3 | 安全：`_copy_source` 目标路径 | P0 | 通过：dest = `CONTRACTS_DATA_DIR/<uuid>/source`，UUID 隔离无穿越；source 为用户主动提交的合同（CLI 本地输入） |
| 4 | 安全：密钥/注入 | P0 | 通过：无硬编码密钥；无 SQL 拼接（全 parameterized）；无 shell |
| 5 | 类型/异常 | P1 | 通过：`_loads` 容坏 JSON 降级；persist 无合同结构静默跳过（返回 None） |
| 6 | DRY：CLI 命令三元镜像（audit / evaluate-bid / review-contract 的 text+json 对） | P1 | **记 backlog**：rule-of-three 已到，可提取命令工厂；但触及 audit/evaluate-bid CLI，留独立 refactor（非本 sprint，已记 architecture backlog） |
| 7 | 安全：`_copy_source` 跟随 symlink（copytree 默认） | P2 | **记 backlog**：CLI 本地输入风险低；HTTP 路由(2b)走 upload_helpers 已有 symlink 防护 |

## 裁决

- P0 全通过；P2 #1 已修；P1 #6 与 P2 #7 记入 `architecture/system-contract-audit.md` backlog，非阻塞。
- 验收：`uv run pytest -q` 全绿 + `ruff` 全过 + `test_layering` 6 守卫不退化。

## 架构档

- 更新 `architecture/system-contract-audit.md`（新建子系统档）+ `architecture/ARCHITECTURE.md`（总入口，含全局分层 + 存储）。
