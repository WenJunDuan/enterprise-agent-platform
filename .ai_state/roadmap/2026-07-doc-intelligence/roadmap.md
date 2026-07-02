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
| 4 | 立项方式 | 新 program roadmap，吸收旧 S9，S7 剩余作 Wave0，按三波次排序 |

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
