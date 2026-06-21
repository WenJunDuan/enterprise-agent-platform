# Tender 提示词 dogfood — 用真实标书跑 /tender-evaluate 找出的失效点

> 2026-06-21 · 输入：招标文件 `华为（南通）数字经济协同创新基地技术辅助运营项目.pdf`(79p) + 投标文件 `烛照-标段一v3.pdf`(158p)，均文本层。
> 方法：人工执行 S0–S4，对照真实页码记录提示词会出错的地方，再针对性改 `.claude/commands/tender-evaluate.md`。

## 真实评分结构（已从招标文件提取）

- 评标方法：综合评分法（p5）。评分表**不在《评标办法》章**，而在**第五部分 开标和评标**（p62 起）：商务技术标 70 分 + 报价标 30 分 = 100。
- 商务技术 70（p62-66）：①同类业绩3 ②履约能力(软著)4 ③运营平台24 ④服务团队配置6 ⑤技术方案5.1/5.2/5.3 各5 ⑥应急响应3 ⑦服务质量保障6 ⑧服务增值9。主/客观分列已标。
- 报价 30（p66）：(1)基础服务报价20=基准价法 (2)非驻场单价4 (3)增量服务单价3 (4)营收单价3，(2)(3)(4)依**限价**算。
- **陷阱**：p30「附件一·技术辅助运营考核方案（100 分）」是**中标后季度履约考核 KPI**（招引10/商机30/交付10…），不是评标标准，但同样列分值。

## 失效点（按"会不会在这份真标书上算错"排序）

| # | 失效点 | 真实证据 | 后果 | 已改 |
|---|---|---|---|---|
| G1 | S1 把 p30 考核方案误当评分标准 | p30 考核 KPI vs p62-67 真评分表，都含「分值/得分」 | 整套 criteria 取错 | ✅ S1 加「定位线索 + 排除考核/KPI 表 + Σmax=总分 自检」 |
| G3 | 「否则不得分」对上读不清的扫描附件 → 误判 0 | 业绩合同/软著/资格/毕业证书均「提供扫描件否则不得分」，而 bid p11-59 是扫描盖章件 | 把"读不清"当"没提供"客观判 0，冤判 | ✅ S3 加二分：未提供→0；读不清→null+manual_review |
| G5 | 价格分一律当「需横比」 | (1)基准价法需横比；但(2)(3)(4)靠**限价**(p61表/p66)单家可算 | 白丢 4+3+3=10 可算分给人工 | ✅ formula 项分「基准价类→横比」vs「限价类→scored 单家算」 |
| G4 | 复合评分行硬塞单一 score_mode | 运营平台24=18扣减+6▲加分；服务团队6=驻场3+证书3；服务质量6=2+2+2 | 一项装不下两类规则，分算错 | ✅ S1 加「复合行拆成多条 items，Σmax=原行满分」 |
| G2 | 主观档次项被当客观确定分 | 技术方案5.1-5.3/应急/服务质量为**主观分**（招标表已标主/客观） | 单趟模型幻觉「完整→满分」 | ✅ S3 主观档次给「初评建议+low_confidence」，注明以评委会为准 |
| G7 | S1 只按《评标办法》标题找 | 本标评分表在「第五部分 开标和评标」 | 找不到→rule_gap 误降级 | ✅ 并入 G1：按评分表结构 + 开标/评标/商务技术标/报价标 章节定位 |

## 改动落点

全部在 `.claude/commands/tender-evaluate.md`（5 处外科手术式插入，未重写，未动契约）：
- **S1**：定位线索与排除（G1/G7）、复合行拆 items（G4）、价格分限价 vs 基准价（G5）。
- **S3**：「否则不得分」前置二分（G3）、主观档次低置信纪律（G2）。

均与 `contracts/tender/criteria.schema.json`（score_mode/deductions/bands/awards/formula/tag）兼容；G4 用「拆多条 items」落地（schema 一项仅一种 score_mode，items 数组无 1:1 约束），无需改契约。

## 与 OCR 强化的耦合

G3 是 OCR 域强化（本 sprint design §3 置信度信号 / §4 多模态兜底）在评标侧的落点：底稿带 per-block 置信度后，S3 的「读不清→manual_review」才有客观触发器，而不是靠模型自觉。**建议 G3 提示词改 + OCR 置信度信号一起验收**——两者缺一，扫描盖章附件的评分就不可靠。

## 仍建议（未在本次改，留 backlog）
- 真正端到端验证需在部署侧用模型网关跑一遍这两份文件，比对 S1 取到的 criteria 是否=上表、报价(2)(3)(4)是否给了分而非全 manual。
- criteria.schema 可考虑 v3 加 `sub_items` 让复合行更自然（当前用拆 items 绕过，可用但 criteria 行数与招标行数不再 1:1）。

## AI 端到端实测验证（2026-06-21 · CC 自跑 /tender/projects/{id}/evaluate，deepseek-v4-pro[1M]）

结合 cowork 的 G1-G7 prompt 改 + CC 的【结论产出根因修复】（normalize 剥离未知顶层字段，治 `additionalProperties:false` 把"模型多输出一字段"的完整结论整单拒→重试失败→降级 manual_review/空 criteria）。

**criteria 提取（大成功，对比改前只 2 项"技术"）**：20 项精准——`source_ref="第五部分 开标和评标 p62-67"`（不在《评标办法》章，G1/G7 对）；Σmax=70 商务技术+30 价格=100 自检过；复合行全拆对（运营平台→三平台 18 deduction + ▲加分 6 additive；服务团队→驻场 3+证书 3；服务质量→质量体系 2+承诺 2+培训 2）；score_mode 合理。

**废标判定正确**：disqualification「应答函致中国移动南通分公司，非本招标」→ rejected；解耦工作（rejected 但 scoring 保留逐项，total 13 有扣有得）。

**剩余失效点（第 2 轮修）**：
- **A（absence-is-not-zero，5 项）**：▲加分/资格证书/技术资源/增值方案/月均收费 score=0 却 status=scored——投标对这些项无对应内容/不响应，模型判 0 通过，应 manual_review。CC 的 `scored_zero_suspect` 校验已抓到（5 warning），需 S3 prompt 强化「投标无对应/不响应该项 → manual_review 不判 0」+ 前端 0 分项醒目。
- **G5 未生效**：价格 4 项全 formula→manual_review；限价类（非驻场/增量/营收单价）应 scored 单家算。
- **注意**：本案是废标案例（烛照=中国移动标，不匹配华为南通），大量 manual_review/0 是"投标不响应"的正确表现；**正常评分路径仍需真投华为南通的匹配标验证**。
- ~~小 bug GET tasks HTML~~ → 复核为**误判**：实测 `GET /tender/tasks/{完成任务}` 正常返 JSON；之前的 HTML 是首次评标 `request_id=null`（directory 校验失败）导致轮询空 RID 落 SPA 兜底，非真 bug。SPA 路由（api.py:301）在 API include_router（:265）之后注册，API 优先。

## 第 2 轮修复（CC，dogfood 实测驱动，2026-06-21）

- **A（硬降级，治"实得0却通过"）**：dogfood 重跑证明 **S3 prompt 强化不可靠**（补"无对应→manual_review"后，模型还判 6 个 score=0 scored）。改为**校验层硬降级兜底**（`output_contracts._verify_score_mode_consistency`）：score=0+scored 但无评分依据明细（additive 无 award_hits / banded 无 selected_band）→ 降级 `manual_review(insufficient_evidence)`；**保留** deduction 扣减到 0（有 deduction_hits）、pass_fail（客观未满足，有依据的 0）。前端 `model.ts` 已把 manual_review 归 pendingItems（"待人工"），降级后自动正确显示，无需改前端。
- **G5（S3 配合 cowork 的 S1 tag）**：cowork S1 已把限价类价格标 `tag:scored`，但 S3 把所有 formula 一律 manual_review。改 S3：formula 按 tag 分两路——`requires_cross_bid_comparison`→manual_review；`tag:scored`（限价类）→ 用本家报价+招标限价代入公式单家算 scored。
- **A prompt（S3，与 cowork G3 互补）**：补"投标对评分项无实质对应内容/未响应 → manual_review 不判 0 scored"（区别于 G3 的读不清/材料缺失）。
- 均 450 passed/ruff。codex review + 再 dogfood 验证中。
