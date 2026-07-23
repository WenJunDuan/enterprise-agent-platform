# design · tender 结论案卷头信息留存与展示 — 2026-07-23-tender-case-header

> 2026-07-23 重建:原档(三轮 critic 定稿版)被 hook 快照回滚事故摧毁,主 agent 从会话上下文重建,含全部 R1-R3 修订。

## 背景

用户实测:评标 agent 分析中已识别**项目名称**与**投标单位名称**,但结论不留存、界面不显示。根因链四点:①命令输出纪律只要标识语义(`claim_id` 优先统一社会信用代码,`tender-evaluate.md:104`;`tender_project_id` 优先招标编号)——去重/分组用,非展示名;②`audit-result.schema.json` extracted_data 自由形,无案卷头节;③`worker.py:180` 仅存 claim_id,不回填;④前端展示名唯一来源=上传手填(`docs.py:128`),未填 fallback bid_id,`model.ts:403` 只消费 bids 手填。

**关键存量**:招标层 `tender-info.schema.json`(手填优先/派生只填空/区1 展示);前端 `displayNameByClaim` 映射链。真实缺口收敛为:①投标单位名全场景无 agent→存储→展示通路;②项目名在散单场景结论不携带。

## 方案

### 选定:方案 A — 结论契约加案卷头节 + 服务端只填空回填 + 前端消费既有映射链

**A1 · 契约**:新增 `.claude/contracts/tender/bidder-info.schema.json`(tender-info 同风格,全 optional,additionalProperties false):`bidder_name`(以投标函/营业执照为准)/`credit_code`/`source_refs[]`(页锚)。结论内嵌:`extracted_data.bidder_info` + `extracted_data.tender_info`(复用现 schema 子集:project_name/tender_no/tenderee)。不改 audit-result 主 schema。

**A2 · 命令**(生产提示词,克制,R1-F5 定位):两处**纯追加**——输出契约节(:101-119)末尾第 8 条 + S2 节(:43-52)一句呼应:钉入 bidder_info(带 source_refs 页锚)与 tender_info(可得时);**识别不到省略,不编造**;claim_id/tender_project_id 语义不变。

**A3 · 服务端**(R2-F6/F7 修订版,**不动跨域共享 TaskStore**):

> R1-F1 勘误:tender_store.py 不存在;真实结构=tender_task_store 薄包装+task_store.py 共享 TaskStore(audit/tender 同 _FIELDS)——加 tender 列污染 audit 域违 schema-split 决策,**放弃 tasks 表加列**;散单前端直读 result payload,bidder_info 随 payload 自然可见。
> R2-F6 勘误:bids 表=`tender_doc_store.py` 的 **`tender_bid_docs`**(:58-70,PK=(project_id,bid_id),已有 bidder_name TEXT),非 tender_project_store(该表 PK=project_id 无 bid 语义)。

1. **results 归档链拍平(主链+R2-F7①补 join key)**:`result_store.py` ResultRecord 加 **bid_id+bidder_name**(比照 project_id 先例:nullable 非 tender 留空);`run_agent_json`(json_bridge.py)**与中转层 `run_command_json`(command_adapter.py,R3 观察1:该文件纪律=显式参数不走 **opts)均加可选具名 kwarg bid_id=None**(audit 零行为变化)→ runner.py:285 透传 → archive_result_payload 拍平。slots-dataclass 坑:_FIELDS/coerce 白名单同步,验收强制 archive→读回往返测试。
2. **路由透出三处+手填 join**:projects.py `GET /projects/{id}/results` 响应、TenderProjectBid/_project_bid_roster 透出两名称:手填((project_id,bid_id) join tender_bid_docs)+ agent 名(results 拍平)——点亮前端 api.ts:35,70 生产死字段,「手填优先」真实可达。
3. **bids 只填空回填**:tender_bid_docs 加 `bidder_name_source` 列(本文件 PRAGMA+ALTER 幂等 idiom :77-92);worker completed 分支挂 `_backfill_bidder_name`(异常不崩),单条原子 SQL 三键 WHERE(对齐 :355-361 跨租户纪律):`UPDATE tender_bid_docs SET bidder_name=?, bidder_name_source='agent_extracted' WHERE project_id=? AND bid_id=? AND tenant=? AND (bidder_name IS NULL OR bidder_name='')`;手填=source NULL,**任何情况不覆盖非空手填**。

**A4 · 前端**(tender-review,红区,R1-F3 写死):api.ts 加结论 bidder_info/tender_info 类型;model.ts 两函数改造——`extractBidderCompanyName`(:1483-1505)首选键改 `bidder_info.bidder_name`(旧猜测键降历史兼容);`resolveBidderDisplayName`(:1468-1474)候选数组改 **[bidderName, summaryBidderName, extractBidderCompanyName, mappedName, claimId, fallback]**(倒正现状 agent 压手填);名称旁标注来源(AI 识别 hover 出 source_refs);散单从 tender_info.project_name 渲染案卷头(缺省隐藏)。

### 字段完整性深研定版(用户点名)

本期钉:投标单位名/信用代码(bidder_info)+ 项目名/招标编号/招标人(tender_info 复用,散单);已钉不动:bid_price。**观察清单**(无消费者不钉,铁律[反过度工程]):拟派项目经理(D11 一致性已消费文本形态)/工期/质保承诺/投标有效期。

### 备选:B 前端正则抽分析全文——弃(非契约面随模型漂移,违背可回溯红线);C 强制表单必填——弃(转嫁用户,散单仍无解,agent 已识别不用是浪费)。

## 影响范围

增:bidder-info.schema.json;改:tender-evaluate.md(纯追加)、result_store.py、json_bridge.py、command_adapter.py、runner.py、projects.py、tender_doc_store.py、worker.py、agent-front tender-review {api,model}.ts+展示组件。

## 风险与缓解

1. 生产提示词回归:纯追加;D1 golden 需网关→部署机窗口,本机契约/单测护航(显式留痕)。
2. 回填覆盖人工:只填空+source 列+三态单测;手填最高优先。
3. agent 编造:识别不到省略+source_refs 可回查+前端标注 AI 来源。
4. 红区:generator+worktree;merge 前主 agent 四证据。
5. 与 X1 并行:X1 已收口,文件面无交集。
6. schema 漂移:bidder_info 单源,前端类型手写对齐(无 codegen 沿现状)。

## 验收标准

1. 后端 `uv run pytest -q` 全绿(基线 955+新增)+ ruff 净。
2. 前端 build/test(bun,基线 146)/lint 全绿,优先级链单测 ≥4。
3. 语义:archive 拍平 bid_id+bidder_name 且**往返读回非空**;三键原子回填三态;手填任何情况不被改写;**手填优先端到端可达**(手填非空时 roster/results 以手填为准,非默认值路径断言);**bid_id=None 退化显式测**(R3 观察2:非 prewarm 直提场景退化到 agent 名不崩);audit `run_agent_json`/`run_command_json` 零行为变化。
4. 前端:列表/分析中心显示单位名+来源标注;散单案卷头;无 bidder_info 回退现状。
5. 命令 diff 仅追加。
6. 观察清单落账不实现。

## 任务分解

T1 契约+命令 → T2 服务端(TDD;红线:task_store 共享层零改动/json_bridge+command_adapter 只加默认 None 可选参数)→ T3 前端 → T4 四证据收口。

## critic 记录

R1 NEEDS_REVISION 五条(P0 tender_store.py 锚点不存在+共享 TaskStore 污染 audit/P0 漏 results 归档链=api.ts:35,70 生产死字段/P1 前端键不匹配+顺序反了/P1 回填 TOCTOU/P2 命令行号)→ R2 NEEDS_REVISION(F6 P0 bids 表误指 tender_project_store→更正 tender_bid_docs;F7 P1 bid_id join key 缺失手填优先空转→采①方案补链)→ **R3 PASS**(历史决策对齐 5/5,2 P2 建议并入:command_adapter 具名透传+bid_id=None 退化测试)。

## 实施记录(2026-07-23,勘误定稿)

- T1(8baef0f 契约+命令)/T2(5fbf482 服务端)/T3(d6bc5cc 前端)全部落在分支 **`worktree-agent-a9ea79174969a5183`**,**未 merge main**(此前"落回 main"系 git 状态错乱期误读:主工作区曾被错误切到 agent 分支,已修复回 main=53fd7ac)。
- 主 agent 在分支态独立验 T1+T2:**981 passed/2 skipped + ruff 净**(基线 955,+26;期间 fitz 缺失系 uv sync 未带 --extra ocr 环境问题,已恢复)。T3 未独立验;**T4 四证据未跑**。
- **模型违约**:T1-T3 实为 sonnet-5 所写(generator.md `model: sonnet` pin 压过 opus 覆盖),违反用户"禁 sonnet";merge 与否待用户拍板(见 route-note 追记)。
- 实施期两次 API 断连;agent worktree 的 Stop hook 曾三次摧毁主仓 .ai_state(截断/回滚/删档),worktree 已拆除(分支保留),档案由主 agent 重建并 commit 固化。
