---
sprint_slug: "2026-06-19-contract-tender-review-mock"
path: "System"
created: "2026-06-19"
last_updated: "2026-06-19"
status: "reworked_after_user_correction"
---

# Design — 2026-06-19-contract-tender-review-mock

## 背景

用户提供 `/Users/mi_manchi/Desktop/招投标审核Agent.dc.html` 与
`/Users/mi_manchi/Desktop/support.js`。上一版误把原型里的隐藏内页都产品化，并保留
`合同审查清单` 旧入口。用户纠正后，当前设计以最新口径为准：

- 发票审核组名改为 `智能报销审核`，入口改为 `报销审核`。
- OCR 识别组名改为 `智能 OCR`，入口仍为 `OCR 识别`。
- 合同审查组名改为 `智能招投标审核`。
- 移除 `合同审查清单` 入口和旧空白页。
- 原型入口只落 `工作台` 与 `历史评审`；`工作台` 在新框架中改名为 `项目管理`。

上一版把所有原型页面都做成左侧入口的方案作废。当前保留两个左侧入口，
但允许 `创建评审`、`分析中心`、`评分对比`、`审核报告` 作为按钮进入的内部
mock 流程。

## 目标

- 侧边栏显示 `智能招投标审核 > 项目管理` 与 `历史评审` 两个入口。
- `/contracts` 老链接不再显示旧空白页，直接重定向到 `/contracts/tender-review`。
- `/contracts/tender-review` 是项目管理工作台；`/contracts/tender-review/history`
  是历史评审。
- `创建评审` 从项目管理工作台进入 mock 创建流程，不作为左侧菜单入口。
- 历史评审列表只暴露 `分析中心` 与 `审核报告` 两个操作按钮；`评分对比`
  仅保留在分析中心内部，不作为历史评审列表动作。
- 使用本地 mock 数据，统计、进度和历史筛选集中在 feature 的 data/model 层。
- OCR 业务行为不变，但上传卡片动作区按用户要求左右分开；报销审核只改命名、
  可见文案和统一控件，不接新接口。

## 非目标

- 不接真实后端接口。
- 不引入 Design Canvas runtime `support.js`。
- 不保留原型隐藏内页作为左侧菜单入口。
- 不实现真实后端上传、真实 PDF 导出或真实评分详情接口。创建评审的文件入口
  可以选择真实本地文件，并暂存在前端 mock 状态中。

## 关键决策

- `TenderReviewScreen` 允许 `dashboard | create | history | analysis |
  report`，但侧边栏只暴露 `dashboard/history` 对应的两个业务入口。
- `dashboard` 显示为 `项目管理`，承载统计和项目列表；按用户要求移除日期统计块、上传引导块和审核引擎块，并使用统一查询、状态筛选、分页控件。
- `create` 显示 mock 项目信息、文件状态和 `开始分析` 进度流程；创建页宽度与工作台/历史列表使用同一主容器，步骤条居中加宽，招标/投标文件入口通过真实文件选择添加文件。
- `history` 通过独立路由展示历史评审搜索、时间筛选与表格；不展示状态筛选，
  历史记录统一为 `已完成`，表头居中，列表行只保留 `分析中心`、`审核报告` 操作。
- `/contracts/` index route 使用 TanStack Router `redirect` 跳到 `/contracts/tender-review`。
- `/contracts/tender-review` 父路由只渲染 `Outlet`；首页放在 index route，避免历史页被父页面遮挡。
- `src/features/contract/contract-review-page.tsx` 删除，避免旧空白页继续存在。

## 官方依据

- TanStack Router file-based routing: https://tanstack.com/router/latest/docs/framework/react/routing/file-based-routing
- TanStack Router redirects: https://tanstack.com/router/latest/docs/framework/react/guide/redirects
- React `useState`: https://react.dev/reference/react/useState
- Tailwind responsive design: https://tailwindcss.com/docs/responsive-design

## 验收标准

- [x] AC1: 导航组 `智能报销审核` 只包含入口 `报销审核`。
- [x] AC2: 导航组 `智能招投标审核` 包含 `项目管理` 与 `历史评审` 两个入口。
- [x] AC3: `合同审查清单` 入口和旧空白页已移除。
- [x] AC4: `/contracts` 重定向到 `/contracts/tender-review`。
- [x] AC5: `/contracts/tender-review` 面包屑为 `智能招投标审核 > 项目管理`。
- [x] AC6: `/contracts/tender-review` 与 `/contracts/tender-review/history` 渲染不同页面。
- [x] AC7: `创建评审` 按钮可进入 mock 创建流程，`开始分析` 会启动进度并进入分析中心。
- [x] AC8: 历史评审支持搜索和时间筛选；状态统一为 `已完成`，不再展示 `已完成` / `已归档` 状态筛选。
- [x] AC9: mock 数据集中在 `mock-data.ts`，筛选统计集中在 `model.ts`。
- [x] AC10: `bun run test`、`bun run lint`、`bun run build` 通过。
- [x] AC11: Edge/Playwright 视觉和动作验收通过；两个左侧菜单入口、历史页表格、创建评审流程、分析/对比/报告按钮链路均正常。
- [x] AC12: 创建评审页面宽度与工作台/历史列表页面保持一致。
- [x] AC13: 原生 `<select>` 已替换为共享 Select 组件，且项目管理/报销审核使用共享分页。
- [x] AC14: 历史评审列表只保留 `分析中心` 和 `审核报告` 两个按钮，表头居中。
- [x] AC15: `项目管理` 统计卡片压低，查询输入框加宽；`OCR 识别` 开始识别/加载示例左右分开。

## File Structure Plan

```text
src/
├── app/navigation/registry.ts                         (修改：新组名、新入口、breadcrumb)
├── app/navigation/registry.test.ts                    (新增/修改：导航与 breadcrumb 断言)
├── features/audit/
│   ├── audit-tasks-page.tsx                           (修改：报销审核可见文案)
│   └── audit-submit-page.tsx                          (修改：新建报销审核可见文案)
├── features/contract/
│   └── tender-review/
│       ├── index.tsx                                  (薄页面容器)
│       ├── use-tender-review-page.ts                  (dashboard/create/history/analysis/report 状态)
│       ├── mock-data.ts                               (原型工作台/历史 mock)
│       ├── model.ts                                   (统计与历史筛选)
│       ├── model.test.ts                              (TDD 覆盖)
│       ├── types.ts                                   (业务类型)
│       └── components/
│           ├── create-review-view.tsx
│           ├── dashboard-view.tsx
│           ├── history-view.tsx
│           ├── analysis-workbench-view.tsx
│           ├── metric-card.tsx
│           ├── page-heading.tsx
│           ├── report-view.tsx
│           ├── screen-content.tsx
│           └── status-badge.tsx
├── features/contract/contract-review-page.tsx         (删除：旧空白页)
└── routes/_authenticated/contracts/
    ├── index.tsx                                      (修改：redirect)
    ├── tender-review.tsx                              (父路由 Outlet)
    └── tender-review/
        ├── index.tsx                                  (项目管理)
        └── history.tsx                                (历史评审)
```

## 风险与权衡

- `/contracts` 仍作为技术路由存在是为了兼容老链接；它没有菜单入口，也不渲染旧页面。
- Edge/Playwright 视觉验收发现并修复了创建页运行时 500；`创建评审`、文件增删、投标单位增删、`开始分析`、`评分对比`、`生成报告`、`返回对比` 和历史页操作按钮均已实际点击验证。
- 真实接口替换时只替换 `mock-data.ts` 和 `model.ts` 周边，不改 `/audit/*` 或 `/ocr`。
