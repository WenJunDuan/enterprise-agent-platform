# 白名单外发现与待立项（2026-08-19 批次）

> 来源：提交闸改造（commit `b7f66cf`）与 Phase A（commit `5ef7d18`）两个 generator
> 的交付报告。纪律：只记不顺手改。按优先级排。

## P1 · agency 生产可见性缺口（下一刀优先）

A.1 语料落盘挂在 `doc_pipeline`（招标/投标**上传目录**），而评标会话的 `case_root` 是
**评标提交目录**——两个不同路径。`TENDER_AGENCY=1` 在生产 doc-layer 路径下，模型 grep 的
`<case>/corpus/` 很可能是空的。补齐要把 doc 层 `case_path`（`tender_doc_store` 有）透到
评标侧，落点 `doc_layer.py` / `doc_context.py` / `worker.py`——当时被并行 worktree 禁触，
**现已解禁**。另一半：证据层开启时 `ocr_block` 是按项片段非整份底稿，corpus 须另读 store。
**不修则 agency 开关在生产等于空转，Step 5 对照实验前必须修。**

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

## P2 · 行数债

`server/tender/worker.py` 510 行（+37，既有违规）；`eval/regression.py` 822 行
（gate sprint proposals P1#2 已记，下刀线=YAML 子集解析器分家）。

## P3 · 口径备忘（不动，读数时要知道）

- 提示词预算 39,963/40,000，剩 37 B——下次加句必先删等量重复（ratchet 设计意图）
- corpus manifest 的 blank 判定复用 `MAX_BLANK_CHARS=20`：正文 <20 字符的短页记 blank
- corpus 是 case 目录内派生物，靠"OCR 前 clear_corpus"防自我复制；要常驻的正解是
  `server/ocr/pipeline.py` 的 `_OCR_EXCLUDED_*` 加目录排除（未改）
- 测试夹具两处 `criteria_status` 补 ready 是修"生产不可能状态"，断言未动
