# R5 设计 · 数据存储（compare 横比 + delete 清理 + criteria 复用）

> Sprint 2026-06-22 · Round 5/6 · Path: System（前端 + 后端）· 并入遗留②③④

## 背景（WHY）
goal #3「数据存储」+ 遗留②③④：三层数据正确性、横比首次生成、删项目磁盘清理。

## 方案（HOW）

### 遗留③ compare 首次横比 refetchInterval 停（✅ 前端）
- 根因：`compareQuery.refetchInterval` 在 `compare==null`(404,首次未生成) 时返回 false → 停轮询 →
  triggerTenderCompare 异步生成的首个横比永不出现停在空（codex r5 P1-5）。
- 修：null 时继续轮询（3000）直到横比生成；非 stale 才停。query 仅 ≥2 投标 + 分析/报告屏 enabled，
  离屏 react-query 自动停，无无界轮询。`use-tender-review-page.ts:193`。

### 遗留④ delete 磁盘 OCR 产物目录清理（✅ 后端）
- 根因：删项目级联只清各评标 task 的 `case_path`，但 P3「上传即 OCR」的 tender-doc/bids 预热目录
  无对应评标 task → 不在 case_paths、残留磁盘（codex P2 P1-5）。
- 修：新 `remove_project_submission_dir(tenant, project_id)`——删整个 `<tenant>/tender/<project_id>/`
  目录树兜底所有子目录；tenant/project_id 逐段安全校验 + confine submissions root 防穿越；异常静默吞
  不让删失败。delete 端点 case 清理后追调。`upload_helpers.py` + `tender.py:540`。

### 遗留② criteria 项目级回填复用（部分，R1 已落代码）
- R1 已实现：上传即抽 criteria 存招标层（首写赢）+ 评标 worker 注入已存 criteria 跳 S1 重解析。
- 待：端到端验证「首家写入 → 后续家读已存复用」（需多家同项目评标，留实测）。

## 影响范围
- 前端：use-tender-review-page.ts（compareQuery）。
- 后端：server/routes/upload_helpers.py（新 remove_project_submission_dir）、server/routes/tender.py（delete 端点）。

## 验收标准
1. compare：≥2 投标完成后首次横比自动出现（不停在空）。
2. delete：删项目后整个 `<tenant>/tender/<project_id>/` 目录（含孤儿上传目录）清空；穿越 project_id 安全。
3. tests + 前端 build 绿。

## 进度
- 遗留③ ✅ + 遗留④ ✅（608 passed + ruff + 前端 build；2 新单测：删项目目录树 + 穿越安全）。
- 遗留② 端到端复用验证：_pending（需多家同项目评标实测）_。
- 三层数据正确性：R1 上传层 + 评标读层单家（第6轮）已实测；compare 层本轮修。
