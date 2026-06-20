# Tender Phase 2 设计 — 价格横比 / 排名 / 推荐中标人（终版）

> Goal 2026-06-20-tender-data-model · Phase 2 · Path: **System** · 设计先行 → codex review(**APPROVE-WITH-CHANGES**) → 本终版可实施。
> 前置：Phase 1 已审已修（招标项目实体 + 多投标人追加 + 回看，330 passed）。本期补"多家到齐后统一比选"。
> 评审：`reviews/codex-phase2-design-review.md`（6 findings 全纳入，见 §8）。

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

## 4. 设计要点（终版，含 codex 6 findings）

### 4.1 统一报价字段（前置，**已做**）
`tender-evaluate.md` S2 + 单投标人段把投标报价**钉成 `extracted_data.bid_price {amount, currency}`**（已提交）→ compare 可靠收集。

### 4.2 `/tender-compare` 命令（新，.claude）
- 输入（prompt 内联 JSON）：
  ```jsonc
  {
    "project_id": "...", "method": "...", "funding_type": "state_funded|other|unknown",
    "control_price": "标底(可空)", "criteria_price_item": {"item","max","scoring_rule"},
    "bidders": [{"claim_id","bid_price":{amount,currency},"scoring":[{item,max,score,status}],"verdict"}]
  }
  ```
  → **传各家 `scoring[]`，由 Claude 自算 `other_score`**（不读不存在的 `scored_subtotal`，codex P1.3）。
- 输出（新契约 `contracts/tender/compare-result.schema.json`）：
  ```jsonc
  {
    "project_id": "...", "method": "...",
    "bidders": [{"claim_id","bid_price","price_score","other_score","total_score",
                 "rank","status":"scored|manual_review|rejected","note"}],
    "recommended": "claim_id 或 null",       // codex P1.5：非无条件排名第一
    "provisional": true,                      // 仅暂定排名(未满足终局条件)时 true
    "warnings": ["异常低价待澄清","有效投标<3 缺乏竞争"…],
    "explanation": "...", "policy_refs": ["tender_evalmethod_004/010/012/013…"]
  }
  ```
- **推荐终局性护栏（codex P1.5）**：`recommended` 可为 `null`。仅当①方法为综合评估法/最低评标价法算出明确排名第一 ②无异常低价待澄清(`tender_evalmethod_010`) ③有效投标≥3(`tender_evalmethod_012`) ④`funding_type=state_funded`(`tender_evalmethod_013` 才强制排名第一为中标) 时给终局 `recommended`；否则 `recommended=null` + `provisional=true` + `warnings`。废标(rejected)不参与排名；异常低价该家 `price_score` 走 `manual_review`。
- 承重 `policy_refs` 只引通则层真实 rule_id；价格规则/命中走 `evidence_chain`（同 Phase 1，过真伪闸）。

### 4.3 存储（方案 A 新表，杜绝污染 codex P1.1）
- 新表 **`tender_compare_results`**（`project_id` PK / tenant / payload JSON / `input_result_ids`(排序 request_id 列表) / `criteria_hash` / `computed_at`）。
- **compare 不写 `results` 表**（codex P1.1）：给 `run_agent_json` 加 `archive_to_results: bool=True` 显式参数，compare 调用传 **False**（结果由 compare runner 自存 `tender_compare_results`），避免 `_project_bid_roster`/`/projects/{id}/results` 出现 compare 伪投标人。

### 4.4 异步任务分表（codex P1.2）
- compare 异步，但**新建 `tender_compare_tasks` 表**（绑泛型 TaskStore，表名隔离）——**不复用 `tender_tasks`**，否则 compare task 挂同 group_id 会被 `_project_bid_roster` 当在途 bid。roster 只查 `tender_tasks`，天然不碰 compare。
- `POST /tender/projects/{id}/compare`：建 compare task（accepted→running→completed），worker 收集→校验→调 `/tender-compare`→存。
- `GET /tender/projects/{id}/compare`：取最新 compare 结果（含 `stale` 标记，见 4.6）。
- 校验：≥2 家 `completed` 才 compare；不足则 400 提示。

### 4.5 criteria 一致性校验（codex P1.4）
compare 收集各家 `payload.criteria`，算 **`criteria_hash`**（规范化 JSON 后 hash）。全一致 → 取该 criteria 进 compare 输入；不一致 → compare 结果 `manual_review` + warning「各投标人 criteria 不一致，需人工核对评分标准」，**不任取一份**。

### 4.6 输入签名 + stale（codex P2.6）
`tender_compare_results` 存 `input_result_ids`(参与的 completed request_id 排序列表) + `criteria_hash` + `computed_at`。`GET /compare` 与 `GET /projects/{id}`：重算当前 completed result set 的签名，与存储不匹配（追加了新投标/重评）→ 标 **`stale=true`**，提示需重跑 compare，**不展示陈旧 recommended**。

### 4.7 project 详情联动
`GET /projects/{id}` 的 `recommendedBidder`/排名：compare 跑过**且非 stale 且 recommended≠null** 才展示；否则留空（计算不存储，Phase 1 原则）。project 表加 nullable `funding_type` 列（compare 输入用，前端建项目时可选传）。

## 5. 影响范围
- 新：`.claude/commands/tender-compare.md`、`.claude/contracts/tender/compare-result.schema.json`、`server/stores/tender_compare_store.py`（compare 结果 + 签名/stale）、`server/stores/tender_compare_task_store.py`（绑 TaskStore "tender_compare_tasks"）、`server/routes/tender_compare_worker.py`（收集→校验→调命令→存）。
- 改：`server/common/json_bridge.py`（`archive_to_results` 参数）、`server/common/command_adapter.py`（透传）、`server/routes/tender.py`（compare 2 端点 + detail stale 联动）、`server/stores/tender_project_store.py`（加 funding_type 列）、`.claude/commands/tender-evaluate.md`（bid_price 已钉)。
- 测试 + architecture 档（System ≥5 文件）。

## 6. 验收
- project ≥2 家 completed → `POST /compare`(异步) → 各家价格分+other_score+总分+排名；废标不参与；异常低价 manual_review；funding≠state 或有效投标<3 → `recommended=null`+provisional+warnings。
- compare 不污染 `results`/bid roster（codex P1.1/P1.2 回归）；compare task 不进名册。
- criteria 不一致 → compare manual_review（codex P1.4）；追加投标后旧 compare 标 stale（codex P2.6）。
- 承重 policy_refs 引通则层真实 rule_id（过真伪闸）。
- `uv run pytest -q` 全绿 + ruff + 路由表基线更新 + System 交叉审查(codex+cc) → architecture 档 → ship。

## 7. §7 决策（codex 确认，已定）
1. 横比 Claude 侧（Python 只收集/校验/调度/持久化）。
2. 存储新表 A + compare 不写 results（archive_to_results=False）。
3. 异步 + compare task 分表 `tender_compare_tasks`。
4. 总分不重读投标：传 scoring[]/bid_price/criteria，Claude 合成 other_score+total。
5. criteria hash 校验一致后再 compare，不任取一家。

## 8. codex 6 findings 纳入对照
P1.1 results 污染→archive_to_results=False(§4.3) · P1.2 task 复用→新表 tender_compare_tasks(§4.4) · P1.3 scored_subtotal→传 scoring[] 让 Claude 算(§4.2) · P1.4 criteria 任取→hash 校验(§4.5) · P1.5 推荐终局→recommended 可 null+provisional+warnings(§4.2) · P2.6 stale→input 签名(§4.6)。
