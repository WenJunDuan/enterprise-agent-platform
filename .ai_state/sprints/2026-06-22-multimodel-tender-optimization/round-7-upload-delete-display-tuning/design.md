# R7 设计 — 上传删除 / 区1回传 / 思考区渲染 / 评分误判收紧

> 来源：用户本机 UX 验证反馈（4 个问题）。延续 R6 上传即 OCR + 三区展示。

## 背景

用户实测 R6 前端，提出 4 个问题：

1. **招标文件传错了不能删除**：上传后删除按钮被锁；删除应同时停止后台 OCR 并回传（重置状态可重传）。
2. **区1 基本信息未回传**：区2 招标信息已显示，区1（项目名/招标人/控制价等）空白——用户没手填基本信息直接下一步，区1 应被 OCR 抽取数据覆写。
3. **思考区不等高 + 未渲染 markdown**：区3 实时输出高度未与左栏等高；AI 输出的 markdown 原样显示字符。
4. **评分点误判**：明明不对应（投标未满足）却写 manual_review/待核查，应判不得分/拒绝。

## 方案

### #1 招标文件删除 + 停 OCR（黄区，前后端）

- **后端**：OCR fire-and-forget 任务按 `project_id` 分桶（`_PROJECT_OCR_TASKS: dict[str, set[Task]]`）；`DELETE /projects/{id}` 在级联删除前 `task.cancel()` 该项目所有在跑 OCR → 真正"停止 OCR 服务"，释放信号量名额。DB-gone 守卫已保证停后写入 no-op，无脏数据。
- **前端**：`removeTenderFile` 改 async——若已上传（`uploadProjectId`）→ `deleteTenderProject` 级联清 + 重置全部上传态（uploadProjectId/tenderFiles/uploadedBidderIds/uploadingBidderIds/prewarmBidIds/uploadBidders），可重新上传正确招标文件。UI：招标 FileRow 删除按钮在"非上传中、非分析中"恒显（含已上传态）。

### #2 区1 OCR 覆写（黄区，后端为主）

- **根因**：`tender-info.schema.json` `additionalProperties:false` → 模型多抽一个字段即 `jsonschema.validate` 抛错 → tender_info 整对象被丢 → 区1 空（criteria 走独立 sanity 检查故区2 仍显）。
- **方案**：`_extract_project_doc_info` 对 tender_info 改 **sanitize（保留 6 已知 string 字段、trim、剥未知）** 替代 validate-or-drop。结构合法即留可用字段，杜绝整对象丢失。
- 前端区1"资金来源"补 `tenderInfo.funding_hint` 覆写链（此前仅读手填 funding_type）。

### #3 思考区等高 + markdown（黄区，前端）

- 装 `react-markdown` + `remark-gfm`；新建 `MarkdownView`（自定义 `components` 类映射 h/ul/li/code/strong/p，免引 @tailwindcss/typography，降构建风险）。
- Zone3 布局：grid 默认 `items-stretch`；区3 Card `flex flex-col` → CardContent `flex-1 min-h-0` → 内层 `flex flex-col h-full` → 滚动区 `flex-1 min-h-0 overflow-auto`（去固定 `max-h`），与左栏（区1+区2）等高。

### #4 评分点误判收紧（绿区，prompt）

- 收紧 `tender-evaluate.md` S3「absence-is-not-zero」：**底稿完整可读且确认投标未提供/未满足某客观评分条件 → 判 0 分/扣分 `scored`**（或该项 `rejected`，若属必交硬性项）；**仅** OCR 读不清/无法定位、现场答辩、外部数据、横向比价、rule_gap、data_conflict 才 `manual_review`。保留"读不清≠没提供"的真不可判定边界。
- 需 3 模型 eval 验证生效（prompt 行为改动）。

## 影响范围

- `server/routes/tender.py`（OCR 任务分桶 + delete cancel + tender_info sanitize）
- `agent-front/.../use-tender-review-page.ts`（removeTenderFile async 删除重置）
- `agent-front/.../components/create-review-view.tsx`（招标删除按钮恒显）
- `agent-front/.../components/analyzing-view.tsx`（区1 funding_hint + 区3 等高/markdown）
- 新增 `agent-front/.../components/markdown-view.tsx`
- `agent-front/package.json`（react-markdown/remark-gfm）
- `.claude/commands/tender-evaluate.md`（S3 收紧）

## 风险与缓解

- 删项目 cancel OCR：cancel 抛 CancelledError 由 OCR 协程 try/except 兜住，不冒泡。
- sanitize tender_info：仅保留 string 字段，非 string（数字/对象）跳过，不引脏数据入展示。
- markdown 渲染：自定义 components 限定标签，无 `dangerouslySetInnerHTML`，无 XSS 面。
- #4 prompt 改动：保守收紧，保留全部真不可判定枚举；eval 不达预期可回退。

## 验收标准

- #1：上传招标文件后可删除→OCR 停（log 无后续该项目 OCR 写）→可重传；单测覆盖 delete cancel 调用。
- #2：tender_info 含未知字段时不再整体丢弃（单测）；区1 在 criteria_status=ready 后显项目名/招标人等。
- #3：前端 lint+build 通过；区3 与左栏等高；markdown 标题/列表/粗体正确渲染。
- #4：3 模型 eval 中"投标确认未满足客观项"判 scored 0 而非 manual_review（人工抽检）。
- 全量 `pytest` + `ruff` + 前端 `lint`/`build` 绿。
</content>
</invoke>
