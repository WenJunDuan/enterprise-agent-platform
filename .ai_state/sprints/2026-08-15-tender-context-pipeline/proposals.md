# 白名单外发现与待立项（2026-08-19 批次）

> 来源：提交闸改造（`b7f66cf`）、Phase A（`5ef7d18`）及四刀批次
> （`1df7407`/`de54b4b`/`ea1e5e7`/`d9286d8`）的 generator 交付报告。
> 纪律：只记不顺手改。按优先级排。

## ~~P1 · agency 生产可见性缺口~~（已修，`de54b4b`）

复制式汇集：评标前把双侧 corpus 复制进 `<eval case>/corpus/{tender,bid}/`，跨投标人
隔离五条专测（含真路径闸 deny）。残留一角：**legacy/inline 路径**（无 project_id/bid_id
或无 doc 行）不汇集，此时补证指引"底稿已落在 X/"对空目录是虚假承诺——要治需动已冻结的
`corpus_materialize.agency_context_block` 或加抑制开关，记此备查（生产 doc-layer 不受影响）。

## P1 · 补证工具调用数无服务端信号（Step 5 报告出数的前置）

工具调用只落 session 事件 JSONL（`session_logging` 的 `event=tool_call`），任务表与
结论体都没有计数字段。度量刀已把读取口径钉死为任务记录 `tool_call_count`、缺席显 `n/a`
（防把"没接信号"读成"没调用"）。要让 Step 5 的"补证调用数"列出数字，服务端须把
tool_call 计数写进任务记录——小刀，落点 `worker.py`/`tasks.py`，Step 5 开跑前做。

## P1 · v2.1 阈值口径冲突待用户裁决：40K「字」还是「字节」

v2.1 三节写「连续两轮 >40K **字**触发 P0.6 复议」，五节列名是「结论**字节数**」。
实测 0818b3 结论 27,716 字 / 53,310 字节——**按字节已越线、按字数没越，结论相反**。
度量刀现处理：指标列给字节、明细给字数、脚注声明"判 P0.6 以字数为准"。最终口径需用户定。

## P1 · vision-page 部署前置：必须先配 `VISION_PAGE_URL/MODEL`

现役 `OCR_VL_SERVER_URL` 是 aistudio 异步 job API 而非 chat/completions，vision-page
不能复用；不配单独端点则三个像素点冒烟必全挂（exit 5）。env.example 已补说明。
另：`2026-08-14-l2-model-routing` 落地后 VISION_PAGE_* 应并入模型注册表而非长期自带 env。

## P2 · A3/B3 归因张力（Step 5 结果复议项）

case-2/3 的"团队人员"成员表页实测**可直读文本**（第 71/42 页），但 v2.1 二节把证书类
三项整体归列B（像素）。度量刀按"登记不改判"照表落 pixel 并在 yaml 内注明张力。
若 Step 5 后判定应改列A，改的是 v2.1 二节那张表，不是 expected。

## P1 · criteria 抽取无心跳，>300s 被误判僵尸

抽取阶段（`doc_pipeline.extract_project_doc_info`）不刷新 `updated_at`，而
`OCR_PREWARM_STALE_SEC=300s`、`TENDER_EXTRACT_TIMEOUT_SEC=1200s`——慢抽取（>~5min）会被
既有口径判"僵尸"。收单语义下表现从"提交即拒"变成"任务失败"，用户感受更晚。根治 = 抽取
阶段加 `touch_project_doc_*` 同款心跳。既有口径本次原样沿用未借机改。

## P2 · Dockerfile 加装 qpdf（1 行，1-2 MB）

`WITH_OCR=1` 的 apt 层没有 qpdf。现行为：记 `qpdf_unavailable_skipping_pdf_precheck`
warning 后按旧行为继续（损坏 PDF 原样进 OCR）。要让 A.1 的损坏修复真正生效（参照教训：
损坏文件页数报 5 实为 400），apt 列表加 `qpdf`。打 0818b4 时顺手带上即可。

## P2 · 回归命令可去掉 `--ignore=tests/test_tender_prewarm_oracle.py`

该文件此前是**真挂死**（doc_layer 那档 criteria 等待空转到 1800s），不是慢。收编后
25 用例 0.35s 全绿，主 checkout 已验证（全量 1,868P 含它）。各处文档里的回归命令
（handoff 环境备忘等）可更新。

## P2 · 行数债（08-19 晚更新）

`server/tender/worker.py` 510 行（+37）；`eval/regression.py` **1,134 行**（度量刀 +312，
其中出处注释约 90 行属载荷；函数级全部压在 40 行内，文件级下刀线=报告渲染拆 `eval/report.py`
+ YAML 子集解析器分家）；`server/common/agent_bridge.py` 690、`server/ocr/pipeline.py` 884、
`run_tender_evaluation` 259 行（均既有债+小增量，如实记）。

## P3 · 口径备忘（不动，读数时要知道）

- 提示词预算 39,963/40,000，剩 37 B——下次加句必先删等量重复（ratchet 设计意图）
- corpus manifest 的 blank 判定复用 `MAX_BLANK_CHARS=20`：正文 <20 字符的短页记 blank
- corpus 是 case 目录内派生物，靠"OCR 前 clear_corpus"防自我复制；要常驻的正解是
  `server/ocr/pipeline.py` 的 `_OCR_EXCLUDED_*` 加目录排除（未改）
- 测试夹具两处 `criteria_status` 补 ready 是修"生产不可能状态"，断言未动
