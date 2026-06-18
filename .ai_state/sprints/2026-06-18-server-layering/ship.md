# Server 分层整理 Ship

> Sprint 2026-06-18 · Path: Refactor · 已执行 A3→A1→A2→A4，每步独立 commit + 全量测试。

## 成果

四处结构债全部消除，server/ 依赖方向严格单向向下，并由 `tests/test_layering.py`
（5 条断言）固化防回归。基线 212 → 216 passed，ruff 全绿。

| 步 | 改动 | commit |
|---|---|---|
| A3 | 抽 `routes/deps.py`，verify_tenant 出 api，删 8 处 lazy import，解 routes↔api 环 | `b7eece9` |
| A1 | 抽 `server/ops/`，diagnostics/maintenance 出 platform，platform 回归纯叶子 | `e8ae42d` |
| A2 | `audit/contract.py` → `common/contract.py`（契约一致性属共享脚手架），解 common→audit | `cd02389` |
| A4 | command_adapter 直连源模块，断 core↔common 环 | `516d17d` |

设计文档 `c1581d3`。

## 最终分层（依赖只向下）

```
app      api · app_server · cli
ops      ops/{diagnostics,maintenance}
routes   routes/{audit,ocr,health} · routes/deps
features audit │ ocr   (兄弟，互不 import)
common   agent_bridge · json_bridge · command_adapter · contract · session_logging
stores   request/result/memory/session/audit_task/...
platform config · paths · logging · storage · sqlite   (纯叶子)
```

`server.core` 保留为对外稳定 facade（外部/测试导入路径不变），但 common 内部一律
直连源模块，不再回环。

## 关键决策与偏调

- **A2 用 relocation 而非设计中的 post_process 回调**：勘察发现 `audit/contract.py`
  实为模型输出契约一致性（schema 加载/归一/语义校验），真正业务判断在 Claude 侧；
  且 `command_adapter`(common) 也服务多域，回调只会把耦合搬到别处。整体下沉 common
  更干净、零签名改动、风险更低。
- **保持按技术分层**（用户定）：新功能域作 audit/ocr 兄弟模块加入；实践中新业务域
  （如 tender）是纯 `.claude/` 配置、复用 common/audit-result 契约，server 侧零改动，
  故 contract 调度器非高频变更点。

## 验收

- [x] 全量 `uv run pytest -q` 216 passed（含 4 条新分层守卫 + 1 routes 守卫）
- [x] ruff 全绿
- [x] `platform/` 不 import 任何上层；`common/` 不 import audit/ocr/routes/ops/api/core；
      audit↔ocr 互不 import；routes 不 import api —— 均由 test_layering 守卫
- [x] `import server.api / server.cli / server.core` 无循环导入

## 遗留（未做，留后续）

- `validate_structured_output_semantics` 仍是 schema-keyed 调度器（含 audit+system 两支），
  未改为注册表。当前新域复用现有 schema、不新增分支，非热点，YAGNI 暂留。
- `server.core` facade 是否彻底删除：内部已不依赖，但外部/测试仍走它；删除留独立 sprint 评估。
