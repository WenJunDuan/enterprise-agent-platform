# 子系统档 · legal 合同审查 + 合同库

> type: system · slug: contract-audit · 建于 2026-06-19（sprint contract-audit-feature / roadmap item2）
> 长效现状档：随子系统演进更新，不是 sprint 一次性产物。

## 职责

legal 域的合同审查能力：读合同 → 按本地 legal 规则判风险/合规 → 产 `common/audit-result`；
并把审查抽取的合同结构（条款/付款节点）落入**合同库**，供审查回溯与（v2）跨域引用。

## 组件

| 组件 | 文件 | 角色 |
|---|---|---|
| 合同事实底稿契约 | `.claude/contracts/legal/extract-result.schema.json` | parties/contract_meta/clauses/payment_nodes/attachments 底稿语义（内部，非 structured output） |
| 复核契约 | `.claude/contracts/legal/review-delta.schema.json` | contract-reviewer 第二意见（默认关） |
| 内联审查命令 | `.claude/commands/review-contract.md` | 五步 harness（S0 清点→S1 规则→S2 抽取→S3 评判→S4 汇总），AI 直读，产 audit-result |
| 合同库 store | `server/stores/contract_store.py` | sqlite `contracts` 表（统一库）+ 持久化/回链/原件 copy |
| CLI | `server/cli.py` `review-contract(-json)` | 镜像 evaluate-bid；-json 跑后落库 |
| 路由 agent | `.claude/agents/legal/contract-reviewer.md` | 第二意见 agent（默认关） |
| 编排 | `.claude/CLAUDE.md` legal 段 | 默认走 /review-contract 内联 |

## 数据流

```
/review-contract <合同路径>
  └─(AI 内联五步)→ audit-result JSON
        ├─ run_agent_json 内部 archive_result_payload ─→ result_store(results 表, by request_id)
        └─ extracted_data.contract ─→ persist_contract_from_result
              ├─ new_contract_id()（UUID）
              ├─ upsert_contract(contracts 表: 结构化字段 JSON 列 + request_id 回链)
              └─ _copy_source ─→ data/contracts/<contract_id>/source/（原件留文件）
```

- **result ↔ contract 回链**：`contracts.request_id` = 审查 run 的 request_id；
  `get_contract_by_request_id_admin(request_id)` 由结论反查合同。
- evidence_chain 不带 contract_id（common schema `additionalProperties:false` 禁改）；
  条款出处编进 `evidence_chain[].source` 字符串（如 `采购合同 第3.1条 (p.2)`）。

## 存储

- `data/db/platform.sqlite3` 的 `contracts` 表：`contract_id`(PK,UUID) / `tenant` / `request_id` /
  `title` / `contract_no` / `sign_date` / `amount` / `currency` / `term` / `source_path` /
  `parties`·`clauses`·`payment_nodes`·`meta`(JSON TEXT 列) / `created_at` / `updated_at`。
- 原件大 blob 留文件 `data/contracts/<contract_id>/source/`（遵 data-storage B1：结构化进表、blob 留文件）。

## 分层

- `command`(Claude 侧) / `cli`(app) → `contract_store`(stores) → `platform`。
- `contract_store` **只依赖 platform**（+ stdlib json/uuid/shutil/pathlib），受
  `tests/test_layering.py::test_stores_only_import_platform` 守卫（T2.5 新增）。
- 未建 `server/legal` feature 模块；持久化编排放在 contract_store（合同域内、layering-clean）。

## 硬约束（已守）

- `routes/audit.py`/`routes/ocr.py`/`routes/tender.py` 零改；不碰 common/expense/tender/ocr schema。
- 仅新建 `.claude/contracts/legal/*`；contract store 入统一库**新表** `contracts`。

## Backlog / 未做

- **item3 contract-audit-api**：HTTP `POST /contract/review` 路由 + worker（复用 tender 异步路由模板）。
- **跨域回链 v2**：expense 审核引用 contract 条款/付款节点判「合同是否支持这笔付款」。
- 同合同去重（contract_no/指纹）；`_copy_source` symlink 收紧（CLI 本地输入风险低，HTTP 走 upload_helpers）。
- CLI 命令三元镜像（audit/evaluate-bid/review-contract）DRY 提取（rule-of-three 已到，留 refactor）。
