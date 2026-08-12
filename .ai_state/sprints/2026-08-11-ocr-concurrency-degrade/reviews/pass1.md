# Review Pass 1 — 2026-08-11-ocr-concurrency-degrade (H3)

审对象：worktree agent-a13794b891d0fcd1e，7 commits（merge-base 4d0a54c，32 文件 +2695/-373）。
reviewer 与 spec-compliance 并行独立完成。证据清点：**6 条 tdd-evidence 八字段全实、新增 60 条
测试逐文件实测对上、行数报数逐项属实**（与 H2 pass1 对照，本次无虚报）。reviewer 实测：ruff 净；
用主仓完整 venv 重跑 worktree 代码 NO_NEW_FAILURES 成立（16 条既有失败逐条同 main + 7 条
worktree 缺 .env），但 evidence 记的"基线 33"是 worktree 残缺 venv 放大出的数字，需更正口径。

## VERDICT 预判：REWORK（P0=0，但 P1×5 中三条有真实并发行为面）

## Findings（reviewer P1×5 / P2×5 / INFO×1；spec-compliance M1+D1/D2 与之交叉印证）

- **F1 [P1]（=spec D1）重试未按剩余预算收口**（engine.py:474-492）：第二次调用仍拿整页 timeout，
  最坏单页 ~180s = 2× 页 deadline，直接违反 KD1"不超页预算"与"最坏不劣于现状"。修法：
  `remaining = deadline - now - backoff` 作为重试 timeout；补"重试 timeout ≤ 剩余预算"断言测试。
- **F2 [P1] 心跳晚于上传信号量排队启动**（doc_pipeline.py:385-390 + :60-70）：排队 >300s 的真在途
  预热被误判 stale → 双跑复活（本 sprint 要杀的病灶）。修法：ticker 移到取信号量之前、首次 touch
  立即执行；补"排队 400s 仍判 in-flight"测试。
- **F3 [P1] KD2 自动重跑无预算约束挂在评标关键路径**（doc_layer.py:237-254）：degraded 文件不进
  缓存必然全量重算 + 信号量无超时排队 + 重跑期间行仍 degraded 会被并发评标重复触发。修法：
  重跑加 `asyncio.wait_for` 显式超时（取剩余 tender 预算一小片），超时放弃走 warning；重跑前置
  行为 running 并起心跳（复用 oracle 天然去重）。
- **F4 [P1] 未知枚举 fail-fast 被读层 blanket catch 吞掉**（doc_layer.py:107-109/155-157）：同一
  ValueError 两种归宿。修法：loader 里把 ValueError 排除出 blanket catch 显式重抛。
- **F5 [P1]（=spec G3）doc_pipeline.py 472→532 越线且 design 未授上界**，tdd-evidence 自授豁免
  不构成授权。修法（reviewer 建议 a 优先）：心跳编排抽到 prewarm_scheduler.py（本就是 OCR 调度
  归属地），doc_pipeline 回落接近基线；否则由主 agent 在 design 补显式豁免。
- **F6 [P2]（=spec M1）degraded warning 不点名文件**；`degraded_files` 字段无生产消费者（只服务
  测试）。修法：落库合并 failed+degraded 名单让 warning 点名，并补一条穿透
  `summarize→update→读回 warning` 真实接缝的测试（spec G1：现测试用手工行构造绕过接缝）。
- **F7 [P2]** AC5 墙钟阈值断言 + 池单例测试序依赖的 flake 面。**F8 [P2]** wait_cap_reached 端到端
  路径无测试。**F9 [P2]** doc_layer/doc_pipeline docstring 引用已不存在符号。**F10 [P2]** 两个
  loader 孪生重复（本 sprint 已付过一次双改成本）。**F11 [INFO]** 闸持有期覆盖退避 sleep（按图
  施工，记录取舍）。
- **spec D2 [P2]**：等待上限公式缺 min 第二项（剩余预算-评标保留量），deadline 从进函数起算不感知
  已耗预算。修法：补公式或 design 记豁免。

## Spec Compliance 摘要

KD 矩阵全覆盖（KD3/KD4/KD6 完全，KD1/KD2/KD5 带上述缺口）；AC1-AC7 测试锚定齐全，构成式
1162+60=1222 核对通过；scope creep=0；EXTRA×6 全合理（doc_layer.py 为 design 外新模块、
case_path 列为 design 遗漏的必要使能，均判合理但需 evaluator 显式表态）；非目标四条未越界。
G2：H1 枚举对齐义务未销账（rebase 后复核留证据）。G4：陈旧注释（并入 F9）。

## 4 处自报偏离评估（reviewer 逐条核）

(a) failed→回落取 AC6：接受，design D3 矛盾文本已由主 agent 回改（design KD2 段 2026-08-12 注）。
(b) summarize_ocr_results 落结构化产物侧：接受，优于原方案。
(c) vlm_client 逐行等价核过无漂移；doc_layer 唯一语义改动即 KD2 判据本身；4ae108a 中间态悬空
引用最终树无残留（ship 时建议 squash 4ae108a+3791a57）。
(d) case_path + run_info_extraction 默认值方向正确，有第二消费者。

## Pass 2 返工清单（发 generator）

必修：F1、F2、F3、F4、F5（优先抽心跳到 prewarm_scheduler）、F6（含穿透接缝测试）、spec D2。
顺手：F8、F9、evidence 基线口径更正（33 → 完整环境 16+7 的构成说明）。
留 polish：F7、F10。
主 agent 已办：design D3 矛盾回改。rebase H2 与 G2 枚举对齐复核在合并阶段做。
