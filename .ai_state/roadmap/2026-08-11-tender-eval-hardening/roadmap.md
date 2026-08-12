# Tender 评审加固 Program — 2026-08-11

## 立项背景

2026-08-10 用户实跑双标段评标暴露三类问题，2026-08-11 四路评审（3 症状根因 + 1 架构）定位全部根因：

1. **页码映射错**：Office→PDF 转换页无人知情（`converted_from` 仅 pipeline.py:486 一处写入零处读取）、
   context 截断锚点错挂（context_slim.py:87-98 按字符硬切）、find_tables 表格尾段无锚归末页
   （native.py:277-294 丢页号）、回查闸对 page_mismatch 只计数不纠正（evidence.py:96-99）。
2. **有价格但横比不出**：横比全系统唯一触发点是前端 fire-and-forget（use-tender-review-page.ts:532
   `.catch(() => {})`）；compare 失败态无路由暴露；`_find_price_item` 首个 cross-bid 项 max 非法即
   return None（compare_worker.py:129-151）；criteria 一致性判据 = N 份模型转录副本 hash 字节等价。
3. **双标并发第二标大量缺结果**：LibreOffice 全进程 BoundedSemaphore(1) + FITZ_LOCK + asyncio 默认
   executor 三层全局队列 → 袋2 预热 360s 超时 → inline 回落双份 OCR 正反馈；逐页 VLM 无客户端并发闸；
   单页失败整文件永久降级 Tesseract 且低质底稿以 ready 永久落库（doc_pipeline.py:425-435）。

架构评审结论：**只动三处结构**（criteria 权威、page-provenance 契约、executor/状态粒度），
FITZ/LO per-task 精修与 engine.py 大拆**不做**——并入已拍板的 OCR 独立服务迁移
（compound/2026-07-20-decision-ocr-as-standalone-service.md），进程内返修是白修。

评审证据：本 program 立项依据的完整 findings 见 2026-08-11 会话四路子代理评审结论
（页锚 F1-F7 / 横比 F1-F9 / 并发 F1-F10 / 架构病根 1-6），承重条目已由主 agent 逐条抽查代码坐实。

## 决策记录

- **执行模型**：design 由 Fable 5 完成（本档），impl 由 generator subagent `model=opus` 执行
  （用户 2026-08-11 拍板"opus5 开发实现，fable5 设计"）。
- **分区**：三个 slice 均跨 server/tender + server/ocr，且**三 slice 均含前端**（H3 的前端硬门
  四点为 critic R1-F1 拉入），按 铁律[零写入] 走红区：generator subagent + `isolation: worktree` 强制。
- **agent-front 豁免声明**（critic R2-N1）：compound/2026-06-19-decision-agent-front-cc-out-of-scope
  约定仅用户明确要求时才动前端。本 program 前端改动（H1: api/model/types/use-tender-review-page/
  compare 组件；H2: model/report-view 展示；H3: 状态硬门四点+OcrDot/文案）已于 2026-08-11 向用户
  完整披露（含"前端四点拉进修改面"），用户拍板"直接叫opus5开始"即为本 program 范围内的前端授权，
  据此豁免；超出上述清单的前端改动仍需另行授权。
- **顺序与合并序**（Round1-F7 修订）：开发可三线并行（各自 worktree），**合并序固定
  H1 → H2 → H3 串行**。理由：H1/H2 共改 audit-result.schema.json、tender-evaluate.md、前端
  model.ts（pending_reason vs page_kind 两组契约变更），H2/H3 共改 engine.py/pipeline.py。
  **H1/H3 另共改 use-tender-review-page.ts、api.ts**（H1 改 compare 轮询/状态机，H3 改终态集/
  canStart，critic R2-N2 补入）。H2 rebase H1 后、H3 rebase H2 后，各做一次**共享契约合并复核**
  （上述共享文件逐一 diff 核对多组变更共存、schema 校验器与前端类型双绿），复核项进各 sprint
  checklist。H3 对 H1 的 doc 状态枚举依赖在合并前对齐命名即可。
- **单位换算**：bid_price 万元/元不做自动换算（错一个数量级后果不可接受），只做数值校验 +
  不一致告警转人工（H1 KD4）。
- **不做清单**（反过度工程 + 架构评审拍板）：FITZ/LO per-task 资源隔离、engine.py（887 行基线）
  拆分、doc-structure schema 全量重构、EngineRegistry 化——全部并入 OCR 独立服务迁移。

## 波次

- wave 0：H1（横比修复，用户最痛 + 定 pending_reason/schema 基底；doc 状态枚举 owner 是
  H3 KD2，H1 只消费其命名，critic R2-P2a 校正）
- wave 1：H2（页锚溯源）、H3（并发与降级治理）——开发可并行，**合并严格 H2 先 H3 后**（见决策记录）

## 评议记录

- Round 1（2026-08-11，critic 三设计合审）：VERDICT NEEDS_REVISION，F1(P0 前端硬门)/F2/F3/F4/
  F5/F6/F7 + 3 P2。全部采纳，修订落三份 design 的 Round 2 节与本档合并序。各 design 内
  Round 1/2 记录为准。
- Round 2（2026-08-11，critic 收口复核）：R1 七条逐一核实 CLOSED；新增 N1/N2（P1，均为文档/
  流程收口无技术返工）+ P2 a-d，已全部修订落盘（本档豁免声明/共享清单/波次 owner + H3 P2b/c +
  H1 P2d）。**用户拍板"设计review不要反复了，直接开始"→ 不再跑 Round 3**，critic 自评
  "Round 3 预期可 PASS"如实记录于此。H1 已派 generator(model=opus, worktree) 实施。
