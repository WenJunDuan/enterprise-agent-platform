---
sprint_slug: "2026-07-30-demo-full-doc-ocr"
path: "System"
created: "2026-07-30"
last_updated: "2026-07-30"
---

# Design — 2026-07-30-demo-full-doc-ocr

## 背景 (context)

demo 从完整单体镜像拆成 `agent-front` / `agent-backend` 后，后端保留了现代 Office/PDF 直读，
但丢失本地 PaddleOCR/PaddleX，且没有 LibreOffice/Tesseract。生产诊断还发现三个真实接缝：旧
`.xls` 被错误交给 openpyxl；短/扫描 `.docx` 会把 ZIP 原字节作为图片发给 VLM；模型返回的
`manual + max=null` criteria 会让整份已抽取结果被结构闸误杀。

用户明确要求重新打包，把完整格式读取与 OCR 辅助能力加入双容器并部署到 ARM64 demo。

## 目标 (goals)

- 主要目标：常见文档格式都有确定性读取路径；原生抽空/扫描型文件能转 PDF 后走 OCR。
- 主要目标：恢复旧镜像的 PaddleOCR/PaddleX 依赖能力，但 ARM64 默认仍走现有 LiteLLM 自建 VLM。
- 主要目标：远端 VLM 失败时可用本地 Tesseract 做保守文本兜底。
- 主要目标：修复 `manual + max=null` 使 7 个有效评分项被整份拒绝的问题。
- 部署目标：保持目标机配置、知识库、数据、挂载、网络和固定容器名；前后端使用同一新 tag。

## 非目标 (non-goals)

- 不部署需要 x64 NVIDIA/CUDA 的 PaddleOCR-VL HPS 全栈；demo 是 ARM64 CPU 主机。
- 不执行 Office 宏、不破解密码保护文档、不承诺恶意 Office 解析器的强沙箱。
- 不以 OCR 覆盖高保真原生文本；OCR 只在扫描/抽空/远端失败时升级。
- 不重启 LiteLLM、Milvus、OpenProject 等无关服务。

## 关键决策 (key decisions)

### KD1 · 支持矩阵与路由梯

| 格式 | T0 主路径 | OCR 辅助/回退 |
|---|---|---|
| `.docx` | python-docx；短但有文字也按 native | 含图且文字不足/抽空：LibreOffice→PDF→VLM→Tesseract |
| `.doc` | catdoc/antiword | 抽空：LibreOffice→PDF→VLM→Tesseract |
| `.xlsx/.xlsm` | openpyxl（不执行宏） | 抽空：LibreOffice→PDF→VLM→Tesseract |
| `.xls` | xlrd 读取单元格 | 读取失败/抽空：LibreOffice→PDF→VLM→Tesseract |
| `.xlsb` | pyxlsb 读取单元格 | 读取失败/抽空：LibreOffice→PDF→VLM→Tesseract |
| `.pptx` | python-pptx 读取文本/表格 | 含图且文字不足/抽空：LibreOffice→PDF→VLM→Tesseract |
| `.ppt` | LibreOffice→PDF→PyMuPDF | PDF 无文本层：VLM→Tesseract |
| `.odt/.ods/.odp` | LibreOffice→PDF→PyMuPDF | PDF 无文本层：VLM→Tesseract |
| `.pdf` | PyMuPDF 文本层/表格；混合页保 native | 扫描页或纯扫描：VLM→Tesseract |
| 图片 | 无 native | VLM→Tesseract |
| `.txt/.csv/.md/.json/.tsv` | 文本直读 | 无 |

支持后缀只维护在 `shared/supported-document-formats.json`。后端 `server/ocr/formats.py` 在运行时从
`PROJECT_ROOT/shared` 加载；`scripts/generate_document_formats.py` 只生成前端已提交的
`supported-document-formats.ts`，并提供 `--check` 漂移门禁。两个后端 Containerfile 显式
`COPY shared ./shared`；前端不跨 Vite root 直接 import JSON，避免 tsconfig/build 接缝漂移。
后端分类器与前端 upload `accept` 均从该清单派生，契约测试校验前后端没有额外/缺失后缀。
图片集合固定为 `.png/.jpg/.jpeg/.tif/.tiff/.bmp/.webp`；当前容器没有 HEIC 解码能力，因此删除
UI 中的 `.heic`，同时删除会重新放进 HEIC 的 `image/*` MIME 通配符；不得出现“前端可选、后端落
manual”的伪支持。每个清单内后缀都要经过
`上传校验 → classify → native/convert/OCR → 非空底稿` 契约测试。

openpyxl 官方源码仅列 OOXML 后缀并明确拒绝旧 `.xls`：
https://foss.heptapod.net/openpyxl/openpyxl/-/blob/branch/3.1/openpyxl/reader/excel.py#L75 。
旧 `.xls` 用 xlrd，`.xlsb` 用 pyxlsb，不能只安装 openpyxl 后宣称“支持 Excel”。

### KD2 · 安全 Office→PDF 转换层

新增 `server/ocr/office_convert.py` context manager：

- `TemporaryDirectory` 独占输入/输出/profile，输入复制成固定 basename，避免原路径控制输出。
- 用 `Popen(argv, shell=False, start_new_session=True)` 启动；独立 `UserInstallation` 内预置最高宏安全级别，
  固定最小环境，并使用 `--headless --nologo --nodefault --nolockcheck --norestore`。
- 90 秒超时后对整个进程组先 TERM、限时 `wait`，再 KILL 并 `wait`；任何出口均回收子孙进程和并发槽。
- `BoundedSemaphore(1)`；可由 `OCR_OFFICE_MAX_CONCURRENCY` 调整，避免 6 个文件线程并发拉起 LO。
- 输入后缀必须属于转换清单；仅接受临时目录内普通非 symlink、以 `%PDF-` 开头、未超过
  `OCR_OFFICE_MAX_OUTPUT_BYTES` 的结果，并在进入 OCR 前校验 PDF 页数和每页像素预算。
- 缺命令、超时、非零退出、无输出、输出逃逸均抛 `OcrDependencyError`；上下文退出必清理。

LibreOffice 官方命令行参数资料：
https://help.libreoffice.org/latest/en-US/text/shared/guide/start_parameters.html 。

### KD3 · OCR 顺序与 ARM64 边界

`recognize()` 保持现有选择：`OCR_CLOUD=0` + `OCR_VL_SERVER_URL` +
`OCR_VL_USE_PADDLE_PIPELINE=0` 时走 LiteLLM 后的自建 PaddleOCR-VL。PDF 改为逐页迭代渲染，
VLM 第 N 页失败时只从 N 页开始转 Tesseract，已成功发射的 1..N-1 页不重发；最终页序列必须连续、
每页只发一次，缓存只在整份完成后写最终结果。图片是相同规则的单页特例。

迭代器锁边界固定：打开/读取页数、单页 `get_pixmap/tobytes`、关闭 document 时才持有
`FITZ_LOCK`；每页 PNG bytes 物化后立即释放锁，再 `yield` 给 VLM/Tesseract。网络调用、外部进程和
`on_page` 回调必须发生在锁外。VLM 失败时同一当前页 bytes 直接交 Tesseract，后续页继续从迭代器
逐页取得；不得在持锁的 `with` 内 yield。

Tesseract 是远端 outage 时的可用性降级例外，不是正常能力升级：结果必须标注
`engine=tesseract, degraded=true, clarity=unknown`，缓存指纹/展示状态不得与正常 VLM 结果等价。
定案为所有 `degraded=true` 结果不写持久缓存；outage 恢复后的下一次识别必重新调用 VLM，
不为 fallback 增加易错的 TTL/读取优先级。
仅显式 `OCR_VL_USE_PADDLE_PIPELINE=1` 才调用本地 Paddle layout pipeline。

逐页路径默认受以下可配置上限保护：`OCR_MAX_PDF_PAGES=500`、
`OCR_MAX_PAGE_PIXELS=25000000`、`OCR_MAX_TEMP_BYTES=536870912`、
`OCR_PAGE_TIMEOUT_SEC=90`、`OCR_MAX_TEXT_CHARS_PER_PAGE=200000`。超限或单页失败返回结构化错误；
迭代器在成功、异常和取消路径均立即释放 page/pixmap/临时文件，不把整份 PNG 保留在内存。

镜像恢复并固定已在旧 ARM64 镜像验证过的 `paddlepaddle=3.2.2`、`paddleocr=3.7.0`、
`paddlex=3.7.2`，但不自动启用本地 layout。官方 PaddleOCR-VL 资料：
https://www.paddleocr.ai/latest/en/version3.x/pipeline_usage/PaddleOCR-VL.html 。
Tesseract CLI/语言资料：https://tesseract-ocr.github.io/tessdoc/Command-Line-Usage.html 。

### KD4 · criteria manual/null 保真

- `.claude/contracts/tender/criteria.schema.json`：`max` 允许 number 或 null，但 null 仅由服务端语义闸
  在 `score_mode=manual` 且 tag 非 scored 时接受。
- `criteria_looks_usable`：要求至少一个 `max` 为数值的评分项；manual/null 不再导致整份失败；
  scored/null 仍拒绝。
- `.claude/commands/tender-extract-info.md` 与 `tender-evaluate.md` 同步写明：仅
  `score_mode=manual && tag!=scored` 可输出 null；scored/null 属于无效结果。
- `criteria_looks_usable` 要求至少一个数值评分项才可 ready；manual/null 仍计入项目数，但不参与求和。
- `server/tender/output.py` 的摘要与校验保留 unknown-max 计数；只要存在未知满分，就不得把已知项
  合计冒充整份满分。`compare_worker` 禁止 null/非数值价格项进入横向比较，转人工复核且不排名。
- `api.ts` 使用 `number | null`；`model.ts` 和全部展示组件禁止 `Number(null)`/`|| 0`，单项显示
  “未设分值”，总分显示“待确认”。
- 前端派生摘要统一为 `knownMaxTotal: number`、`unknownMaxCount: number`、`maxTotal: number | null`：
  只有 `unknownMaxCount===0` 时 `maxTotal` 才能是完整数值；否则 `maxTotal=null`。该契约贯通
  `types.ts`、`scoring-overview-panel.tsx`、`scoring-detail-table.tsx`、`report-view.tsx`，禁止这些
  组件各自用 reduce 重新解释 null。

### KD5 · 镜像依赖

后端 Python 层加入/固定：`xlrd`、`pyxlsb`、`python-pptx`、`pdfplumber`、
`paddlepaddle==3.2.2`、`paddleocr[doc-parser]==3.7.0`、`paddlex==3.7.2`。

系统层加入：`antiword`、LibreOffice Writer/Calc/Impress、`tesseract-ocr`、
`tesseract-ocr-chi-sim`、`tesseract-ocr-eng`、`fonts-noto-cjk`、`fonts-liberation`。
构建必须实测 ARM64 包可用，不以 Dockerfile 出现包名代替验收。

### KD6 · 部署与回滚

- 新 tag：`agent-backend:0730b2`、`agent-front:0730b2`。
- 替换前从两个当前运行容器解析实际 image ID，为 0730b1 建时间戳 backup tag，并新鲜导出前后端
  两个旧镜像；保存 image/container inspect、日志、挂载、网络、资源限制和 env key 名清单。
- 旧镜像归档写 SHA-256 后，在独立临时 Docker data-root/一次性验证环境执行可加载验证，证明归档
  对应当前运行 image ID；归档保留到观察期结束，成功后只删除临时 backup tag。
- 禁止 `rsync --delete-excluded`。同步按明确代码根分批执行：`server/`、`shared/` 可在自己的目标
  子目录内 `--delete`；`.claude/` 固定使用 `--delete --exclude=settings.local.json`，并在执行前枚举
  目标端全部 `.claude/*.local.*` 纳入 protect filter；`agent-front/` 以保护 `.env*`、`node_modules`
  的 filter 规则同步；
  根目录只逐文件更新 Dockerfile/pyproject/uv.lock/entrypoint 等构建资产。绝不把项目根作为
  `--delete` 目标，因而目标 `.env*`、compose、knowledge/data/logs、backups、docker-export 不在删除域。
- 正式同步前保存 `rsync --dry-run --itemize-changes`，机器校验上述保护路径无 `*deleting`；
  `.dockerignore` 同步排除 `.git/.ai_state/data/tests/logs/knowledge/backups/docker-export/.env*`、
  `.venv`、`node_modules`、各类缓存/测试/归档，避免目标旧文件进入构建上下文。
- 使用 demo 现有前端 env 构建；后端使用 demo 现有 env，保留三目录挂载和资源限制。
- 新容器健康与格式矩阵通过后新鲜导出两镜像到 `/opt/application/audit-agent/docker-export/`，写
  SHA-256 并做可加载验证；最后删除临时 backup tag。失败则按已记录的 image ID/inspect 恢复
  0730b1 固定容器，旧归档在观察期内持续可恢复。

## 验收标准 (acceptance criteria)

- [ ] AC1：格式分类覆盖表中所有后缀；短文本 DOCX 不再误送原 ZIP，扫描 DOCX 先转 PDF。
- [ ] AC1a：前端两个上传入口与后端分类均派生自同一清单；清单每个后缀都有端到端非空底稿测试；
  `.heic` 与 `image/*` 不再出现在 upload accept；格式生成器 `--check` 与两个 Containerfile COPY 通过。
- [ ] AC2：`.xls` 不调用 openpyxl；`.xls/.xlsb/.pptx` native 单元测试覆盖正文/表格。
- [ ] AC3：Office 转换成功、缺命令、超时、非零退出、无 PDF、magic/逃逸/超限、宏无副作用、
  超时后无残留进程、清理与并发槽释放测试通过。
- [ ] AC4：PDF/图片远端 VLM 中途失败后从失败页续跑 Tesseract；页号连续且无重复、缓存只存最终结果；
  降级诊断可见；默认远端路径不调用本地 Paddle。
- [ ] AC4a：逐页渲染覆盖超页数/超像素/超临时空间/单页超时/单页失败/取消清理，不整份驻留 PNG。
- [ ] AC4b：VLM 第 N 页失败、Tesseract 续跑及 `on_page` 联合回归中，网络/进程/回调执行时
  `FITZ_LOCK.locked()==False`；`degraded=true` 结果不落缓存，远端恢复后重新调用 VLM。
- [ ] AC5：Paddle/PaddleX 在新 ARM64 镜像可导入；LibreOffice/Tesseract/中文字体可实际运行；显式
  本地 Paddle 开关另做启动 smoke，不把“import 成功”等同于 pipeline 可运行。
- [ ] AC6：真实 9 项 criteria（7 numeric + 2 manual/null）从 prompt/schema 到 API/前端往返后 ready；
  scored/null 仍 failed；manual/null 计项目数、不计总分并显示待确认；null 价格项不进入横比。
- [ ] AC7：后端相关测试先红后绿，全量 pytest/ruff；前端 test/build/eslint 全绿。
- [ ] AC8：部署后前后端 HTTP 200，目标 env/挂载/网络/资源/固定名字不漂移，无 OCR/转换启动错误。
- [ ] AC8a：正式 rsync 前 dry-run 证明 `.env*`、compose、knowledge/data/logs、backups、
  docker-export、`.claude/settings.local.json` 及枚举出的 `.claude/*.local.*` 零删除；正式同步后逐项
  存在性/hash 复核仍在。
- [ ] AC9：`.doc/.docx/.xls/.xlsx/.xlsb/.pptx/.pdf/图片` 容器实跑；至少一次扫描件走 OCR 辅助路径。
- [ ] AC10：新旧双镜像导出、SHA-256 与可加载校验通过；临时备份镜像标签已删除；旧镜像归档在
  观察期内仍能映射回部署前 image ID 并恢复。

## 实现要点 (implementation notes)

`classify → pipeline._dispatch_extract` 新增 `route=convert`，以及 native 抽空后的 Office fallback。
转换产物按现有 PDF 分诊重新走 `native_read` / `recognize`，但最终结果保留原文件 path、
`converted_from`、`downstream_route`，缓存键仍以原输入内容为准。

Tesseract 不复用现有整份驻留的 `_render_pdf_pages`，而使用统一逐页 iterator；图片/PDF 每页只在
当前页生命周期内写临时图片后调用 CLI，输出映射回 pages 数组。不得把 Office 原字节直接写入
`image_url`。

## File Structure Plan

```text
shared/supported-document-formats.json                            新增（格式单一真相源）
scripts/generate_document_formats.py                              新增（生成 TS + --check）
server/ocr/formats.py                                             新增（运行时加载 canonical JSON）
server/ocr/office_convert.py                                      新增
server/ocr/classify.py                                            修改
server/ocr/native.py                                              修改
server/ocr/pipeline.py                                            修改
server/ocr/engine.py                                              修改
server/ocr/cache.py                                               修改（路由/降级缓存指纹）
server/tender/doc_pipeline.py                                     修改
server/tender/output.py                                           修改
server/tender/compare_worker.py                                  修改
.claude/contracts/tender/criteria.schema.json                     修改
.claude/commands/tender-extract-info.md                           修改
.claude/commands/tender-evaluate.md                               修改
agent-front/deploy/Containerfile.agent-backend                    修改
Dockerfile                                                        修改
agent-front/src/features/contract/tender-review/api.ts             修改
agent-front/src/features/contract/tender-review/model.ts           修改
agent-front/src/features/contract/tender-review/types.ts           修改
agent-front/src/features/contract/tender-review/supported-document-formats.ts 新增（生成物）
agent-front/src/features/contract/tender-review/components/analyzing-view.tsx 修改
agent-front/src/features/contract/tender-review/components/create-review-view.tsx 修改
agent-front/src/features/contract/tender-review/components/dashboard-view.tsx 修改
agent-front/src/features/contract/tender-review/components/scoring-overview-panel.tsx 修改
agent-front/src/features/contract/tender-review/components/scoring-detail-table.tsx 修改
agent-front/src/features/contract/tender-review/components/report-view.tsx 修改
tests/test_ocr_classify.py                                        修改
tests/test_ocr_native_formats.py                                  新增
tests/test_ocr_office_convert.py                                  新增
tests/test_ocr_pipeline.py                                        修改
tests/test_ocr_engine.py                                          修改
tests/test_tender_info_extraction.py                              修改
tests/test_tender_compare.py                                      修改
tests/test_tender_output.py                                       修改
agent-front/src/features/contract/tender-review/**/*.test.tsx      修改/新增
.ai_state/architecture/system-document-ingestion.md               新增
deploy/TROUBLESHOOTING.md                                         修改
```

## 风险与权衡 (risks & trade-offs)

- LibreOffice、Paddle、字体使镜像明显增大；demo 有约 140GB 可用空间，以能力完整优先。
- LibreOffice 的打印区域可能丢 Excel 非打印内容；因此 Excel 先 native，转换只作抽空/扫描兜底。
- Tesseract 对复杂表格弱于 VLM，只在远端失败时保底并标清晰度 unknown，不冒充高置信。
- 本地 Paddle layout 曾在 ARM64 崩溃；只恢复依赖能力，不改默认开关。
- criteria null 跨后端/前端契约，必须一起改并做求和语义测试。

## 历史决策对齐

- 对齐 `compound/2026-07-02-decision-ocr-routing-ladder.md`：能直读绝不 OCR，只升不降。
- 不推翻 `compound/2026-07-20-decision-ocr-as-standalone-service.md` 的长期独立服务方向；本次是 demo
  现有进程内路径的部署修复，不扩大为新 OCR 服务项目。

---

## Round 1 (initial draft by main agent)

采用“高保真 native → 安全 Office 转 PDF → 自建远端 VLM → Tesseract 兜底”的单向升级梯；
镜像恢复 Paddle/PaddleX 但保持显式开关。criteria 允许受控 manual/null，避免全量误杀。

## Round 1 · Critic Findings

VERDICT: NEEDS_REVISION

- F1 [P0] 格式矩阵未贯通两个前端上传入口，`.heic` 形成伪支持。
- F2 [P0] `max=null` 未贯通 prompt、model、summary、compare 和展示组件。
- F3 [P0] VLM 中途失败后整份 Tesseract 会重复发射已成功页。
- F4 [P1] LibreOffice 超时没有显式清理整个进程组，宏禁用也不可证明。
- F5 [P1] 整份 PDF PNG 驻留存在 OOM，缺少页/像素/时间/临时空间边界。
- F6 [P1] 旧镜像备份未证明对应运行 image ID，删除 tag 后回滚闭环不足。
- F7 [P1] Tesseract 降级与“只升不降”历史决策需声明 outage 例外并显式诊断。
- F8 [P2] 四个故障域应分阶段独立验收；Paddle import 与本地 pipeline 运行必须分开验收。

## Round 2 (revised by main agent)

- 用 `shared/supported-document-formats.json` 贯通前端两个入口、后端分类与矩阵测试，删除 HEIC 伪支持。
- 定义 manual/null 的 prompt→schema→服务端→compare→API→model→展示完整语义和真实 9 项往返。
- 保留页级流式：VLM 第 N 页失败只从 N 页降级，页只发一次，最终完成后才写缓存。
- LibreOffice 改为显式 Popen 进程组生命周期、最高宏安全 profile、输入输出验证与并发槽清理。
- 改为有硬上限的逐页渲染；Tesseract 标记 outage/degraded，不与正常 VLM 等价缓存或展示。
- 部署前新鲜导出当前运行 image ID 对应的双旧镜像并做 SHA/可加载验证；成功后删 backup tag，
  但旧归档保留观察期。新镜像也做同等导出验证。
- 实现按四个可独立验收阶段提交：格式/OCR、criteria 契约、镜像依赖、部署与文档。

## Round 2 · Critic Findings

VERDICT: NEEDS_REVISION

- R2-F1 [P0] `--delete-excluded` 会删除被保护的目标机配置、知识库和归档。
- R2-F2 [P0] criteria 前端类型与三个评分/报告组件仍未进入明确修改面。
- R2-F3 [P0] 逐页 generator 若在 `with FITZ_LOCK` 内 yield，会把网络/OCR/回调串进锁内。
- R2-F4 [P1] fallback 后仍写 VLM cache key，会让远端恢复后继续复用降级结果。
- R2-F5 [P1] canonical JSON 到前端生成物及后端镜像 COPY 的构建接缝没有定案。

## Round 3 (revised by main agent)

- 取消危险的 `--delete-excluded`；只对明确代码子目录受控 `--delete`，根目录构建文件逐个同步；
  dry-run 与正式后校验共同证明目标配置/数据/知识库/归档不在删除域。
- 前端评分摘要采用 `knownMaxTotal + unknownMaxCount + nullable maxTotal`，把 types、overview、detail、
  report 及测试列入修改面，杜绝局部 reduce 折零。
- 每页只在 PyMuPDF 操作期持锁，物化单页 bytes 后锁外 yield、调用 VLM/Tesseract 和触发回调。
- `degraded=true` 结果不落持久缓存，outage 恢复后必重试 VLM。
- canonical JSON 由 Python 运行时读取；脚本只生成提交的 TS 常量并以 `--check` 防漂移；后端
  Containerfile 显式 COPY shared，accept 不含 `.heic` 或 `image/*`。

## Round 3 · Critic Findings

VERDICT: NEEDS_REVISION

- R3-F1 [P0] `.claude/ --delete` 若未保护 `settings.local.json`，仍会删除目标机本地配置/秘密。

## Round 4 (revised by main agent)

- `.claude/` 同步固定保护 `settings.local.json`；执行前枚举所有目标端 `.claude/*.local.*` 并生成
  protect filter。dry-run 的零删除断言与同步后 hash 复核同时覆盖这些文件。

## Round 4 · Critic Findings

VERDICT: PASS

- R3-F1 CLOSED：目标端全部 `.claude/*.local.*` 在同步前枚举，进入 protect filter；dry-run 无删除，
  正式同步后逐文件 hash 复核。Round 1–3 其余 findings 维持 CLOSED，可进入实现阶段。
