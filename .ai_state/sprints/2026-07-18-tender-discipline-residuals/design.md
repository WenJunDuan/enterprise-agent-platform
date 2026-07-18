# Design (DRAFT · 先行设计) · D11 tender 判分纪律残留收口包

> **状态: DRAFT, fable5 主 agent 先行设计(用户 2026-07-18 授权「本 sprint 做完后先行设计下个」)。**
> 立项时机: D3+D10(2026-07-18-prompt-single-source)收口后切换为 current sprint → critic 定稿 → impl。
> 实现分派(用户指定 opus 或 codex): 批次 A=opus(安全轮), 批次 B=codex(确定性服务端), 批次 C=条件项。
> path=System, 全批次 worktree 强制(铁律[零写入])。

## 背景(WHY)

2026-06-23 judgment-discipline sprint 的六项账外残留(原始定义=该 sprint design.md「遗留」节,
R8 e2e 实测定位), 因 D2 tender 包归位 `server/tender/` 而解锁——修改落新结构一次到位, D1 评标
回归闸护航。残留清单: R4 #8a(安全) / F04(evidence_chain) / glm 技术参数 / R5(schema) /
R6(config) / R7(前端)。串标围标识别与 S8 不进本包(原范围决议)。

## 批次 A · R4 #8a ocr-page 重识别 wiring 安全硬化(opus, 独立安全轮, P0 面)

**目标**: 把 `.claude/skills/ocr-page`(按页重识别, 含印章/低清页)接进 tender-eval 流, 落 0623
用户决策 2「证据读不清→先重识别再判」——评标 agent 遇底稿页读不清时可调 skill 重识别后再判分,
而非直接 manual_review。

**威胁模型(为什么是独立安全轮)**: 评标 agent 具 Skill/Task 工具面, ocr-page skill 内部走
Bash(OCR 命令行); 投标 PDF 是**攻击者可控输入**(外部投标人上传)——文件名/路径/页码/内容注入
shell 元字符或 `../` 穿越 = 潜在 RCE(security-checklist P0 命令注入)。**未过对抗验证则不接线**
(保留 skill 手动用, 0623 原决议, fail-closed)。

**机制(实施前需探明, 列为 A0 探查任务)**:
- A0: 探 claude-agent-sdk python `can_use_tool` 回调支持面(版本/签名/在 build_options 的接法),
  与 tender worker 现有 allowed_tools 面; 探 ocr-page skill 实际执行的命令形态。
- A1: 白名单闸——`can_use_tool` 回调(或等价机制)限定: 仅允许 ocr-page 规定形态调用; 参数硬校验
  (文件路径必须解析后落在本任务提交目录内、页码必须正整数、拒绝任何 shell 元字符/穿越);
  校验在服务端 Python 层, 不信任 agent 传参。
- A2: 对抗验证(TDD, 红先行)——注入样本集: 文件名含 `;rm`/反引号/`$()`、`../` 穿越、超长参数、
  伪造页锚; 断言全部被拒且进程无副作用。
- A3: 接线——tender-eval skill/命令文档补「读不清页→调 ocr-page→用重识别文本再判」指令;
  重识别文本进上下文时保留【第N页】页锚(evidence-resolution 闸保真红线)。
- **验收**: 对抗测试全绿(任一失败=不接线, 只交付 A1/A2 硬化本体); D1 golden 评标回归不回退;
  正常路径 e2e 一例(低清页重识别后出真分)留部署机窗口(需真扫描标书)。

## 批次 B · 服务端确定性收口(codex, TDD)

- **B1/F04 · evidence_chain 顶层派生**: `server/tender/output.py:enrich_tender_result` 追加——
  顶层 `evidence_chain` 为空时, 从 `scoring[].award_hits/deduction_hits`(带非零分命中优先)派生
  `{source, finding, conclusion}` 条目, **保留页锚**。顺序语义: 派生发生在 enrich(闸后), 派生源
  award_hits 的 quote 本就经 evidence-resolution 闸回查过, 与「evidence_chain=展示元数据非承重」
  既有语义一致, 不引入二次承重。复用 `server/tender/evidence.py` 的 hit 原语(:118-140)。
  测试: 空链派生/非空链不覆盖/无 scoring 安全跳过/页锚保真断言。
- **B2/R5 · schema 与语义对齐**(实施前探查 tender 语义处理器现状, schema-split 后动 tender 侧
  不动 expense): ①`reviewed_by` 错标(实测吐 expense-auditor→应 tender-evaluator, 服务端 normalize
  盖章); ②`manual_review_reason` tender 侧枚举补齐(requires_live_event/external_data/
  cross_bid_comparison 语义是否入枚举, 以 .claude/CLAUDE.md tender 节与 0623 design 为准);
  ③`policy_refs_detail` 入约评估——**若需改共享物理 schema(common/audit-result.json)则升级评估**:
  影响 expense 侧=范围外, 改为 tender 专属物理 schema 文件(分家二期)或 defer, design 定稿时拍。
- **B3/R6 · config 收口**: INFRA-01 超时关系约束(定位 TENDER_TIMEOUT 与 OCR 云等待的实际读取点,
  启动时校验「OCR 等待 ≤ 0.5×TENDER 超时」否则日志警告——只警告不硬拒, 部署机自主); INFRA-02
  cache v2 首跑重 OCR 的部署提示(runbook/README 注记+启动日志一行)。
- **验收**: 全量 pytest 基线不回退+新增全绿; ruff 净; D1 golden 回归不回退。

## 批次 C · 条件项(不阻塞 A/B 收口)

- **C1/glm 技术参数仍 manual**: 模型自身保守(闸只救不造, compound 2026-06-23 learning)。
  处置=prompt 层强化(tender-evaluate additive 必打分指令加压)+ `TENDER_EVAL_MODEL=glm` e2e 验证。
  **前置=本机网关可路由 glm**; 不可达则整项降部署机窗口(与 D8 runbook 同批), 不在本 sprint 死等。
- **C2/R7 · agent-front null guard**(FE-01/02/03: report-view getItemBadge/DetailSection、
  analysis-workbench——闭合 #4 报告 500 潜根因): **agent-front 红区, 需用户显式授权**(可与 D9
  前端部分同批授权)。授权后交 codex(lint+build+前端测试全绿); 未授权则挂账 D9。

## 影响范围

`server/tender/{output.py, worker/options 接缝}` / `server/platform/config.py` /
`.claude/skills/{ocr-page, tender-eval}` 文档面 / tests 新增; C2 授权后 `agent-front/`。
expense 域零改动; 共享闸零改动(B2③ 如需动共享 schema 则按升级评估另拍)。

## 风险与缓解

| 风险 | 缓解 |
|---|---|
| R4 白名单被绕过(未知注入面) | fail-closed: 对抗测试任一失败即不接线; can_use_tool 之外参数再服务端硬校验双层 |
| F04 派生条目撞 evidence-resolution 闸误降级 | 派生放闸后 enrich; 测试含「真伪闸开启时派生不触发降级」断言 |
| B2③ 牵动共享 schema | 触发即停, design 定稿时单独拍(专属物理文件 or defer) |
| glm 网关不可达 | C1 降部署机窗口, 不阻塞收口 |
| D1 golden 回归波动 | 网关抖动重跑一次口径(沿用 D3+D10 验收 2 约定) |

## 验收标准(checklist 权威版)

1. 批次 A: 对抗测试全绿(否则只交硬化本体不接线, 如实记录); wiring 后 D1 golden 回归不回退。
2. 批次 B: 全量 pytest 基线不回退+新增全绿; F04 派生四断言(空链派生/非空不覆盖/无 scoring 跳过/
   页锚保真); B2 语义断言(reviewed_by 盖章/枚举); B3 config 警告单测。
3. ruff 净; 每批次独立 commit 序列; review(reviewer+spec)→evaluator PASS 后 merge。
4. 条件项 C1/C2 状态如实记录(done/降级部署机/待授权), 不计入 Sisyphus 完整性阻塞。

## 分派与顺序

批次 B(codex, 确定性, 先行)∥ 批次 A(opus, 安全轮, 可并行不同 worktree 或串行——**建议串行
B→A** 避免双写者红区叠加); C1/C2 按条件触发。critic 审议于 D3+D10 收口、本 sprint 立项时执行。
