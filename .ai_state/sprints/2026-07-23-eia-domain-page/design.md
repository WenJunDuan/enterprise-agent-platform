# design · 环评智检域(第四业务域)前端迁移 — 2026-07-23-eia-domain-page

> 2026-07-23 重建×2(hook 摧毁事故,见 route-note)。含两轮 critic 全部修订。

## 背景

`design/` 下有完整静态交互稿(`index.html` 544 行 + `support.js` 1841 行,DC 模板框架):**环评智检 · 报告受理平台**。功能形态:①提交向导三步(水/土/气/声四类检测材料分类上传,每类可多文件可留空、至少一类非空 → 确认清单 → AI 流式分析:分轨进度+终端风格逐字符流 → 按类别出具分析报告:结论/置信度/依据标准+下载);②受理工作台(案件列表+详情侧栏:时间线/分类报告/预审)。用户要求迁入 `agent-front/` 成第四业务域,侧边栏排「智能 OCR」上方。DC 框架与本项目栈(React 19+TanStack+shadcn+Tailwind)不兼容,必须重写迁移。

## 方案

### 选定:方案 A — React 习语重写 + mock-first 数据层

按 OCR 工作台先例(`features/ocr/`:纯函数模型层+mock-data+useReducer+shadcn)重写:

**A1 · 导航注册**:`registry.ts` `MENU_GROUP_ORDER` = ['智能招投标审核','智能报销审核','智能环评检测','智能 OCR'];新组两入口(提交检测报告 `/eia` + 受理工作台 `/eia/desk`);`STATIC_BREADCRUMBS` 增两条;menu-visibility 按组名泛化零改动;`registry.test.ts` 三组断言同步更新为四组(排序测试即回归锁)。

**A2 · 路由壳**:`routes/_authenticated/eia.tsx` + `eia/index.tsx` + `eia/desk.tsx` 薄壳仿 `ocr.tsx`;routeTree.gen.ts 插件再生。

**A3 · feature 包** `src/features/eia/`:submit-page/desk-page + api.ts + types.ts + model/{wizard-state(useReducer 仿 mode-state),stream-script(纯函数引擎:chars→可见行/分轨/进度,定时器只在组件层),mock-data} + components/{category-upload-card,stream-console,report-card,**report-side-panel**(报告清单+打包下载+受理信息+回看/转工作台/再提交,critic R1-F2),case-detail-panel}。

- **向导初始文件态为空**(R1-F3):静态稿预置演示文件仅由「加载示例」注入(对齐 ocr `files: []` 惯例)。
- **toast 一律复用 sonner**(R1-F4):不迁移 toastMsg/toastTimer,页面层零 toast 计时器。
- 视觉:弃 `_ds` 样式,design tokens + shadcn,终端面板 `bg-foreground text-background`;a11y P0:`<label>` 包 `<input type=file>`;文件对象持真实 File。

**A4 · mock-first 接缝**:api.ts `submitEiaBatch(files)→{batchNo}` / `listEiaCases()`,mock 供数;本 sprint 不建后端;将来接线复用 D9 `/ocr/jobs` 任务化+轮询,types.ts 单一契约源。

### 备选:B 静态稿 iframe 直挂——弃(双技术栈/无法接 auth 导航/成本延后加倍);C 同期建后端真分析域——弃(环评标准比对=独立 program 规模;静态稿演示态,EIA-GPT 等均虚构)。**方案 C 是最大可推翻决策,用户要真分析需升级重议。**

## 影响范围

改:registry.ts/registry.test.ts;增:3 路由壳 + features/eia/**(~12 文件);自动:routeTree.gen.ts;不动:server/**、features/ocr/**、.claude/CLAUDE.md。

## 风险与缓解

1. registry.test 锁三组顺序 → T1 同步改断言。
2. mock 契约漂移 → types.ts 单源 + api.ts 单接缝。
3. agent-front 红区 → 用户显式授权;generator(model=opus,用户指定禁 sonnet)+ worktree;merge 前主 agent 独立验(build+bun test+eslint)。
4. 定时器泄漏 → 流式推进归 useEffect cleanup;toast 走 sonner。
5. 与 D9 互扰 → 文件面无交集,D9 回传收口优先。
6. **红区粒度取舍留痕(R1-F6)**:单 worktree 顺序 T1-T4+末次终验,轻于 D9 逐任务先例——理由:纯增量前端/无跨进程副作用/单写者;终验三证据 fail-closed 不减。
7. **页面组件层无自动化测试留痕(R1-F5)**:覆盖止于 model 纯函数层+registry(与 OCR 先例同纪律);回归防护=model 测试+registry 顺序锁。

## 验收标准

1. build 通过;`npm --prefix agent-front run test`(**bun test 唯一跑道,禁引 vitest**,R1-F1)全绿(基线 121+新增:registry 四组/breadcrumb ≥3、wizard-state ≥4 含 step1Blocked/toStep2/backStep1、stream-script ≥5);eslint 净。
2. 第四组「智能环评检测」位于「智能 OCR」上方,两入口,可见性自动支持。
3. `/eia`:**首屏四类均空**→上传卡(全空禁用下一步)→确认→流式→报告卡(sonner toast)+侧栏**四收尾动作**(打包下载/回看重放/转工作台/再提交清空回步 1)。
4. `/eia/desk`:选中高亮→侧栏联动。
5. 双主题无硬编码色值;上传 input 可达 label。
6. design/ 原稿保留;无 worktree 残留。

## 任务分解:T1 导航+路由壳 → T2 域模型层(TDD bun test)→ T3 提交向导页 → T4 工作台+收口。

## critic 记录

R1 NEEDS_REVISION 六条(F1 P0 vitest→bun test/F2 侧栏动作/F3 初始态/F4 sonner/F5+F6 留痕)→ 全应答 → R2 复核 F2-F6 RESOLVED+F1 残留一处(风险#3 漏改)→ 已修,免 round3,定稿。

## 实施与收口记录(2026-07-23)

- impl:worktree T1-T4(一次 API 断连断点续跑),merge main **2d8d822**;主 agent 独立验 146 pass/build/eslint。
- review pass1(reviews/pass1.md):reviewer 0P0/1P1/2P2 + spec M1 → 修 **53fd7ac** → VERDICT **PASS**。
- **模型违约追记**:实现全程 claude-sonnet-5(generator.md pin 压过覆盖),违反"禁 sonnet";已过全套独立门禁,处置待用户拍板。
