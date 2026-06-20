# Tender Phase 2 设计 — 价格横比 / 排名 / 推荐中标人

> Goal 2026-06-20-tender-data-model · Phase 2 · Path: **System** · 设计先行 → codex review → 实施。
> 前置：Phase 1 已审已修（招标项目实体 + 多投标人追加 + 回看，330 passed）。本期补"多家到齐后统一比选"。

## 1. 目标与背景

Phase 1 让同一招标 owns N 家投标评标，但**价格分（`requires_cross_bid_comparison`）各家恒 `manual_review`**（单家无法横比）。Phase 2 补最后一块：**N 家评标完成后，统一算价格分 → 合成各家总分 → 排名 → 推荐中标人**。

前端 `agent-front/.../tender-review/types.ts` 已期待：`ReviewBidder.rank`、`CompareGroup`（横比表 `{name, rows:[{name,max,cells[]}]}`）、`TenderProject.recommendedBidder`。

## 2. 核心决策：横比在 Claude 侧算（不是 Python）

**价格分公式是项目专属、在 criteria 里**（如"最低有效报价/本报价×40"、"均价下浮法"、"标底法"…各标书不同），且"哪些是有效投标""异常低价是否需书面澄清"（`tender_evalmethod_010`）都需判断 → 撞铁律[Python 不判断]。

**结论**：新增 Claude 命令 **`/tender-compare`**，server 只负责①收集该 project 下所有已完成投标人的报价+评分→②调命令→③落库。Python 不解析公式、不判有效性。

- 备选（不取）：Python 直接按公式算价格分。否决理由：公式从 `criteria.scoring_rule` 自然语言提取 + 有效投标认定 + 异常低价澄清都是判断，Python 硬编码脆弱且违铁律。

## 3. 数据流

```
POST /tender/projects/{id}/compare
 │  ① 收集 project 下所有 completed 投标人结论(results.payload):
 │     每家 {claim_id, bid_price{amount,currency}, scoring[](技术/商务已评分项), verdict}
 │     + 该 project 的 criteria 价格项(scoring_rule 公式 + 满分)  ← 取自任一家 payload 的 criteria(同招标 criteria 一致)
 │  ② 组装为 /tender-compare 输入 → 调 run_command_json
 │     Claude: 认定有效投标(废标剔除)→按价格公式算各家价格分→合成总分(可判定项+价格分)→排名→推荐第一
 │  ③ compare 结果落库(project 级) → GET 回看
```

## 4. 设计要点

### 4.1 统一报价字段（前置改动）
`tender-evaluate.md` S2/S4 把"投标报价结构化留 extracted_data"**钉成 `extracted_data.bid_price {amount, currency}`**（现未强制字段名）→ compare 才能可靠收集。

### 4.2 `/tender-compare` 命令（新，.claude）
- 输入（prompt 内联 JSON）：`{criteria_price_item:{item,max,scoring_rule}, bidders:[{claim_id, bid_price, scored_subtotal, verdict}]}`。
- 输出（符合新契约 `contracts/tender/compare-result.schema.json`）：
  ```jsonc
  {
    "project_id": "...",
    "method": "最低评标价法|综合评估法",
    "bidders": [{"claim_id","bid_price","price_score","other_score","total_score","rank","status","note"}],
    "recommended": "claim_id(排名第一)",      // 依 tender_evalmethod_013 国有资金项目排名第一为中标人
    "explanation": "...", "policy_refs": ["tender_evalmethod_004/010/013..."]
  }
  ```
- 护栏：异常低价(明显低于其他/标底)→该家价格分 `manual_review` + note，不强行算（`tender_evalmethod_010` 需书面澄清）；有效投标<3 提示缺乏竞争(`tender_evalmethod_012`)。承重 `policy_refs` 仍只引通则层真实 rule_id。

### 4.3 存储（待 codex 定）
- **方案 A（推荐）**：新表 `tender_compare_results`（project_id PK，payload JSON，created_at）——compare 结果不是单投标人 audit-result，结构不同，独立表干净。GET 直接取。
- 方案 B：复用 `results` 表，特殊 `request_id=compare-{project_id}`、加 `request_mode=compare`——省表但语义混（results 是单投标人结论）。
- 倾向 A。

### 4.4 端点（同步 vs 异步，待 codex 定）
- `POST /tender/projects/{id}/compare`：触发横比。compare 调 Claude 有延迟（聚合 N 家，但比单次评标轻）。
  - **方案 A（推荐）**：异步任务（镜像 evaluate：accepted→running→completed，worker 跑），前端轮询。一致性好。
  - 方案 B：同步（一次请求等结果）。简单但卡请求。
- `GET /tender/projects/{id}/compare`：取最新横比结果。
- 校验：至少 2 家 completed 才能 compare；未完成的家列出提示（可选 `?include_incomplete=false`）。

### 4.5 project 详情联动
`GET /projects/{id}` 详情的 `recommendedBidder`/排名：compare 跑过则从 compare 结果取；没跑过留空（计算不存储原则，Phase 1 已定）。

## 5. 影响范围
- `.claude/commands/tender-compare.md`（新）、`.claude/contracts/tender/compare-result.schema.json`（新）、`tender-evaluate.md`（钉 bid_price 字段）、`server/common/output_contracts.py`（注册 compare schema 校验，可选）。
- `server/stores/tender_compare_store.py`（新，方案 A）或 result_store 扩展（方案 B）。
- `server/routes/tender.py`（compare 端点）+ `tender_worker.py`（compare 异步任务，方案 A）。
- `server/common/command_adapter.py`/`json_bridge.py`（若 compare 走 run_command_json，已支持）。
- 测试 + architecture 档更新。

## 6. 验收
- project 下 ≥2 家 completed → `POST /compare` → 各家价格分+总分+排名+推荐中标人；废标不参与；异常低价 manual_review。
- compare 结果落库 + `GET /compare` 回看；project 详情 recommendedBidder 联动。
- 承重 policy_refs 引通则层真实 rule_id（过真伪闸）；criteria 价格规则走 evidence_chain。
- `uv run pytest -q` 全绿 + ruff + 路由表基线更新。
- System 路径：codex+cc 代码交叉审查 → architecture 档 → ship。

## 7. 待 codex review 的决策点
1. 横比在 Claude 侧（§2）是否认同，还是 Python 算确定公式更简单（铁律权衡）。
2. 存储方案 A（新表）vs B（复用 results）。
3. 端点同步 vs 异步（§4.4）。
4. 总分合成：compare 重算 vs 读各家 scored_subtotal + 补价格分（§4.2 取后者，省 Claude 重读投标）。
5. criteria 价格项来源：取任一家 payload.criteria（同招标 criteria 应一致）vs project 表持久化一份 criteria（去重）。
