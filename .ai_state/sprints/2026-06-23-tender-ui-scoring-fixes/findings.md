# ZJ dogfood 诊断 + UI/评分问题拆分（2026-06-23）

> 触发：用户给 8 条实测问题 + 用 `knowledge/external/招标人ZJ/`（招标 .doc 534KB + XH投标 .PDF 43MB，单投标人）做测试。
> 分工（用户定）：**前端→codex；后端 server + `.claude`→本会话(CC)**。
> ①招标人侧合规 MVP（v2）= **用户明确永久不做，从 backlog 永久剔除**。

## 环境坑（dogfood 必踩，已绕过；与部署相关）

1. **上传默认 10MiB**（`config.py:305` `max_upload_file_bytes`）挡住 43MB 投标 → 已改默认 256MiB（#8b）。注意 `materialize_upload_submission` 用 `await upload.read()` 整文件进内存，200M+ 长期应改流式。
2. **`ANTHROPIC_BASE_URL` 被 Claude Code 会话继承成 `api.anthropic.com`** → 离线护栏（`config.offline_guard_error`，护栏读 ANTHROPIC_BASE_URL 优先于 MODEL_BASE_URL）拦截**所有模型调用**。仅"从 CC 会话起服务"才有此坑；正常部署无。起服务须 `env -u ANTHROPIC_BASE_URL -u ANTHROPIC_API_KEY -u ANTHROPIC_AUTH_TOKEN -u ANTHROPIC_MODEL`。
3. `.doc` 管道不支持（`classify.py:16 WORD_EXT={".docx"}`）；`.doc→.docx`(textutil) 丢表格（107k→40k，0 表格）→ 改用 `.doc→.txt`（textutil，107k 全量，`.txt` native 支持）。**招标 .txt 无页锚点**，故招标侧 page 引用天然对不上（但 #3 主要在投标侧）。

## 三模型评标结果（ZJXH，项目 TENDER-NO-ZJ，政府采购=state_funded）

| 模型 | verdict | scored/manual | evidence resolved/checked | 耗时 |
|---|---|---|---|---|
| qwen3.7-max | manual_review | 8/1 | 23/32 (72%) | ~210s |
| deepseek-v4-pro[1M] | manual_review | 7/2 | 8/24 (33%) | ~250s |
| glm-5.2 | manual_review | 7/2 | 12/16 (75%) | ~290s |

**逐项一致性**：企业实力6/6·业绩9/9·负责人3/3·售后4/4 **三模型全一致**（客观/additive 稳）；**技术参数指标(25分)：qwen 打 21，deepseek+glm 却 punt 成 manual**（过保守，#2/#7 的 ④ 靶子——应核投标参数表逐项打分，不该 punt）；banded 主观项(总体方案/实施/培训)正常波动；价格分全 manual（低价优先需≥2家，正确）。**zero=0 无误判0**（不判0 原则守住）。verdict 全 manual_review **仅因价格分**。

**#3 根因修正**：投标全文 native 仅 **147k（<200k 未被 native 截断）**；底稿 200158 = native + find_tables 表格 + 云OCR(扫描页) **合并**撞 200k 限。提 `OCR_MAX_FILE_BLOCK_CHARS` 让完整渲染底稿过；但部分 unresolved 也来自模型**引 printed 页/范围/转述**（非底稿 `【第N页】` 逐字）= ④ 引证纪律。两者都要治。deepseek 回查率最低(33%)。

## 8 问题拆分 + 实测确权

| # | 用户反馈 | 实测真相 | 归属 |
|---|---|---|---|
| 1/2 | 分项得分不显示、全待核查 | 后端 8 项打了真实分(数据在结果)；前端没渲染 `scoring[]`；"待核查"是 verdict 总标签 | **codex** |
| 3 | 证据/定位对不上 | **真问题**。根因=**bid 底稿撞 200k 截断**（43MB/399页 native 文本>200k，截断到 200158 字符）→ evidence_resolution 回查残缺底稿 → unresolved/page_mismatch。R1 闸本身正常 | **CC**（截断+④引证纪律）|
| 4 | 生成报告 500（历史正常） | 报告屏后端端点全 200（compare 单家 404 正常），服务端无 500。报告=前端 `buildTenderReviewData` 纯构建。当前 build 复现不出 | **需前端复现拿 correlation_id**（多半 codex）|
| 5 | 评分对比无分项 | 前端 compare 视图加分项表+点击右侧弹出 | **codex** |
| 6 | 法定依据裸 id | 确认 `policy_refs:["tender_evalmethod_001",...]`；规则 json 有 `description`+`source_text` | **CC**（enrich→规则文本）|
| 7 | 废标项明细改名/分类聚合表/隐藏待人工 | 前端表格重构；内容侧（不过度 manual、依据去"待人工"前缀）连 ④ | **codex(布局)+CC(④内容)** |
| 8a | OCR 能力移给 Claude（skills+py） | 与 #3 截断同源：大投标底稿截断 → 让 Claude 按需读/OCR 具体页 | **CC**（新 skill）|
| 8b | 上传≥200M | 已改 256MiB | **CC ✅** |

## #3 红线（用户已确认）
可判定项纠回真实分（修过保守）；**真·缺外部输入项（价格横比/外部信用/现场答辩）不编假分**，依据写"需横比/需外部数据"。

## 修复计划（CC 侧）
- **#3 截断**（最高价值，连 #8a）：① 快赢=提 `OCR_MAX_FILE_BLOCK_CHARS`（投标底稿覆盖全文，1M 上下文模型可吃）；② 正解=#8a OCR-as-skill，Claude 按需读页，不预截。**待用户定方向**。
- **#6** enrich：`policy_refs`→`{rule_id, 规则名, source_text}`（读 `knowledge/tender/*.rules.json`，TDD）。
- **④** `tender-evaluate.md`：逼逐字引底稿 `【第N页】` 锚点原文（非printed页/范围/转述）；按红线纠保守。
- **#8a** OCR skill：`.claude/skills/` + py 包装 `server.ocr`，Claude 可 invoke。
- codex handoff：#1/#5/#7 + #4 复现指引（含每字段数据来源/形状）。

## 关键路径/锚点
- 项目 `tp-1de490325fe54594` bid `bd-860e703c9cf04d46`（OCR 已入库 SQLite，换模型复用免重 OCR）。
- 跑法：`logs/tmp/run_eval.sh <model>` + `logs/tmp/pick_model.py <域名>`（非破坏 export 切模型）。
- 服务起法：`env -u ANTHROPIC_* MODEL_BASE_URL/TOKEN/NAME=... nohup uv run python -m server.cli serve`。
- 跑法脚本：`logs/tmp/run_eval.sh`（首评）/ `rerun_bid.sh`（提上限后重传重评）/ `pick_model.py`（切模型）。

## 进展（2026-06-23 修复轮，commit d26d90d + OCR skill）

| 项 | 归属 | 状态 |
|---|---|---|
| #8b 上传 256MiB | CC | ✅ commit d26d90d |
| #3 底稿上限 600k | CC | ✅ 实测回查 71%→92%、unresolved 8→1（commit d26d90d）|
| #6 policy_refs_detail enrich | CC | ✅ +3 测试，684 绿（commit d26d90d）|
| ④ 禁 additive punt + 页码取底稿锚点 | CC | ✅ commit d26d90d（治技术参数 punt + page_mismatch）|
| 前端 #1/#5/#7/#4 | codex | ✅ 已交 codex-handoff.md |
| #8a OCR-as-skill | CC | 🟡 **能力件成**：`.claude/skills/ocr-page/{ocr.py,SKILL.md}` 已建+自测（投标第7页 OCR 通过）。**接进评标 agent 待做**：需 `can_use_tool` 回调把 Bash 限死只跑 `ocr.py`（评标 agent 处理可能含注入的投标 PDF + bypassPermissions，裸 Bash=RCE 风险），须对抗性验证。#3 已被提上限解决，#8a 降为架构改进，wiring 不紧急。|

**下一步（CC）**：#8a wiring（受限 Bash 回调 + 引 SKILL 进 tender-evaluate.md S2/S3 + 对抗验证 + 全 e2e 重跑 3 模型确认 ④/#6 生效）。

## fixed 重测（3 模型，带 #6/④ + 完整 600k 底稿，2026-06-23）

| 模型 | scored/manual | 技术参数(25) | 价格分(30) | bid_price | #6 |
|---|---|---|---|---|---|
| qwen | 5/4 | manual | manual | 1,316,033.66 | ✅ |
| deepseek | 7/2 | manual | manual | 1,316,033.66 | ✅ |
| glm | 8/1 | **scored** | manual | 1,316,033.66 | ✅ |

**验证结论**：
- **#6 ✅ e2e 通过**——`policy_refs_detail` 三模型全显示法定原文（评标办法 001/003/004 规则名）。
- **④ ✅ 按预期**——非"恶化"：模型不再无证据瞎打分，而是诚实 manual（v2 旧码给技术参数 21/25 是错的，证书读不到却给分）。qwen_fixed manual 项 basis 明写「证书扫描件 OCR 未能还原」。
- **价格分** 三模型一致 manual（低价优先需≥2家横比，正确）；**bid_price 三模型完全一致 1,316,033.66**（价格抽取稳）。
- **真瓶颈 = OCR 扫描证书页盲区**：投标 400 页中 **59 页（资质/业绩/职称/社保/检测报告全是扫描件）native 路由没走云 OCR→底稿空→技术参数/企业实力/负责人评分缺据**。qwen/deepseek 严谨→manual，glm 宽松→给分（不稳）。**这是评标拿不到全自动真分的唯一卡点。**

## 当前 Sprint 剩余（2026-06-23-tender-ui-scoring-fixes）

**CC 已完成并 push**（commit d26d90d/e4ff16b，origin 同步，684 绿）：#8b ✅ · #3 ✅(验证) · #6 ✅(e2e 验证) · ④ ✅(e2e 验证) · #8a OCR-skill 能力件 ✅(自测) · 3 模型 fixed dogfood ✅。

**CC 剩余**：
1. 🔴 **逐页 OCR 路由**（最高价值，ZJ出真分的关键）：plan 经 workflow 产出中 → 待用户确认后实施（detect 空页→渲图→云 OCR→merge；代价 ~59 页云识别变慢，需 env 开关/灰度）。
2. 🟡 **#8a OCR-skill wiring**（接进评标 agent，安全敏感需 can_use_tool 限死 Bash + 对抗验证）；逐页 OCR 路由落地后其价值降低（证书已进底稿），可降级/合并。

**codex 侧（非 CC）**：前端 #1/#5/#7（渲染 scoring/分项表/分类聚合）+ #4（报告 500 复现），已交 codex-handoff.md。

**永久剔除**：①招标人侧合规 MVP（用户定永久不做）。
