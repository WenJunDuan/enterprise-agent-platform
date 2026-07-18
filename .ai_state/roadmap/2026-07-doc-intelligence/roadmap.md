# 文档智能 Program · 2026-07-doc-intelligence

> 来源：2026-07-02 全仓架构评估（会话交付）+ 用户愿景确认。
> 愿景原话：「OCR Agent + 多模型路由 + 文档理解 + 实时流式 OCR + 结构化 RAG 系统效果」。

## 背景（WHY）

1. **需求侧证据**：S7 压测结论（`logs/s7-model-compare/REPORT.md`）——底稿 32 万 token 远超 128K
   窗口，"压成本/提稳的杠杆在精简底稿非换模型"。换模型只能缓解，结构化底稿才是解。
2. **供给侧现状**（2026-07-02 评估核实）：
   - OCR 只有容器级 L1 分诊（native vs OCR），OCR 分支内单引擎 PaddleOCR-VL，seal 产线备案未编排；
   - 页级理解有（VL 输出 Markdown+JSON），**文档级结构化没有**（无章节树/目录/实体）；
   - 底稿全量灌 prompt，`ocr-page` skill 是手动检索雏形；
   - 批处理无流式（平台 SSE 进度流机制已有，可复用）。
3. **结构债前置**（同评估）：tender 域无 feature 包（约 3250 行散在 routes/+common/，22 文件超
   300 行红线）；三域三套 prompt 投递机制（expense=Python 常量、tender=slash command、
   ocr=core 门面 legacy），判断纪律双源漂移风险已踩过一次（2026-06-12 audit.md 改了生产不生效）。

**核心洞察**：用户的 OCR 愿景与"底稿瘦身"是同一件事的供需两侧；旧 roadmap S9（KB 脚手架）与
结构化 RAG 是同一存储/检索层——合并立项，不建两套。

## 决策记录（2026-07-02 用户拍板）

| # | 分叉 | 决策 |
|---|---|---|
| 1 | OCR Agent 化程度 | **混合**：Python 管道骨架 + LLM 决策点（低置信度/异常自检/引擎升级重试），不做全 agent 驱动 |
| 2 | RAG 检索地基 | **结构化检索先行**：章节树+页锚+SQLite FTS/BM25，零新依赖；向量（自托管 embedding）作二期增强 |
| 3 | 流式深度 | **页级部分结果流**：边识别边推每页完成事件+内容；识别-评标流水线重叠作流式二期 |
| 4 | 立项方式 | 新 program roadmap，吸收旧 S9，S7 剩余作 Wave0，按四波次排序 |

## 波次结构

```
Wave 0 地基+安全网 ─ D1 eval_tender 正式化(回归闸,S7剩余迁入)
                    D2 tender feature 包重构(纯移动零行为,红区 worktree)
                    D3 prompt 单源统一 + .claude 瘦身
Wave 1 质量层     ─ D4 L2 多模型路由+模型池(含印章/手写 POC,五级决策梯已定稿)
                    D5 OCR 决策点 agent 化(混合)
                    D10 expense 审核链路可靠性包(热路径直连 spike+附件预嵌+runbook)
                    D11 tender 判分纪律残留收口包(R4安全硬化/F04/glm/R5-R7)
Wave 2 结构层★    ─ D6 文档级结构化(章节树/页锚/实体)
                    D7 结构化 RAG 入库+检索(并入旧 S9)
                    D8 底稿瘦身落地+S7 harness 复测
Wave 3 体验层     ─ D9 页级流式 OCR
```

排序理由：D1 是所有后续改动的质量回归闸，必须最先；D2/D3 把地基理干净再动工
（OCR 主线会大改 `server/ocr/` 与 tender 消费侧，D5 的 prompt 管理依赖 D3 的机制决策）；
Wave2 是收益最大的主线（成本/一致性双收）；流式是体验增强，殿后。
**Wave1 即"三域优化 Sprint 包"**（2026-07-02 用户定）：OCR=D4/D5、expense=D10、tender=D11，
三域账外债自此全部在册——D10 吸收 2026-06-12 quality backlog 剩余（③④⑤残），
D11 收口 2026-06-23 judgment-discipline 六项残留；执行时按 PACE 惯例每 item 各开 sprint。

## 执行序重排（2026-07-18，D3 spike 出数后，fable5 主 agent 排定）

**重排依据**（证据：`sprints/2026-07-18-prompt-single-source/{route-note.md, spike/results.jsonl}`）：

1. D3 spike 完场：三模式时延中位差 <6% → **延迟不再是 command 统一的约束**；两源 prompt 漂移已实测
   兑换成生产可靠性差（内联 4/6 attempt 漏 explanation vs command 侧 1/7）→ D3 从「卫生债」升级为
   「可靠性项」；B1（agent 自行取证）1/3 verdict 漂移淘汰，command 统一必须 B2（context 注入）形态。
2. 其中最痛的 prompt-闸矛盾已单独修复（`07f1dc8`，2026-07-18 merge `60d860c`），D3 拍板压力降低，
   但**剩余唯一决策变量 = D10① 直连 spike 数据**（直连 vs command 二选一，roadmap 原定同场拍板）。
3. D11 的依赖（D1/D2）已全部 done，与 D3/D10 零耦合 → 提升为等待窗口的并行项。
4. D4 仍卡部署机前置（V4Pro 基线标定 → 一致性阈值硬门锁定），部署机窗口的活集中打包。

**新执行序**（E# 为建议顺位；「窗口并行」= 等用户拍板/部署机期间可起）：

| 顺位 | 项 | 场地 | 说明 |
|---|---|---|---|
| E1 | **D10① 直连 spike** | 本机 | anthropic SDK 直打网关测时延/可靠性，补齐 D3/D10 拍板的最后一块数据；小工装，落同 sprint spike/ |
| E2 | **D3+D10 同场拍板 → D3 实施** | 用户拍 → 本机 | 方向 a=command 单源(B2) / b=Python 单源；实施含 .claude 瘦身，方向定后可外包（codex/generator） |
| E2' | D10 剩余（②附件预嵌 ③耗时指标+runbook） | 本机 | 形态随 E2 拍板定 |
| E3 | **D11 tender 残留收口** | 本机·窗口并行 | R4 安全硬化独立轮（红区）；F04 纯服务端低风险可先行；R7 前端与 D9 同批授权 |
| E4 | chore：dependabot 14 漏洞（6 high） | 本机·窗口并行 | 走 deps-check，可外包 codex |
| — | 部署机窗口（用户）：D8 runbook 四指标→达标改默认 1；V4Pro 基线→一致性阈值锁硬门（=D4 前置） | 部署机 | 两件同窗口做完 |
| E5 | D4 L2 多模型路由 | 本机 | 部署机前置解锁后 |
| E6 | D5 决策点 agent 化 | 本机 | 依赖 D3+D4 |
| E7 | D9 页级流式 | 本机+前端红区 | 依赖 D4 + agent-front 授权 |

## 护栏（每 sprint 铁律级）

- **页锚全链路保真**：任何切片/检索/结构化产物必须保留【第N页】锚点，否则
  evidence-resolution 闸（出处回查）失效——这是 RAG 切片设计的硬约束。
- **eval 回归闸先行**：D4 起任何识别/底稿形态改动，必须复跑 golden case 证明评标质量不回退。
- 招标文件 criteria 唯一权威 / 不可判定不判 0（继承 tender 纪律）。
- Refactor 零行为变更（D2）；pytest 全绿；agent-front 红区 worktree+明确授权（D9 前端部分）。
- 部署双形态兼容：模型池须同时覆盖内网自托管（qwen/paddle 经 litellm）与云网关（deepseek）。

## 与旧 roadmap（2026-06-tender-program）的关系

- **S7** → 截断防护+双模型压测已完成；eval 脚手架正式化等剩余项迁入 **D1**（见旧 items.yaml done_note）。
- **S9** → 未单独实施，并入 **D7**（KB+检索+外部数据适配脚手架）。
- **S8**（数据安全）→ 保持用户推迟决策，拍板后可插入任意波次之后，不阻塞本 program。

## Backlog（不进波次，机会主义捎带或二期）

- 向量检索增强（bge-m3 自托管+离线打包）——触发条件：结构化检索命中率不足或需历史案例语义检索。
- 识别-评标流水线重叠（流式二期，状态机复杂度高）。
- `config.py`(491)/`cli.py`(527) 拆分、core 门面退役（`ocr/runner.py` 私有名 import，D4 动 ocr 时捎带）、
  session store `list_conversation_summaries` 三处重复（2026-06-12 已知债）。
- 手写签名真伪验证（YOLO+孪生网络，非 OCR 域，见 multi-ocr references/engines.md）。
