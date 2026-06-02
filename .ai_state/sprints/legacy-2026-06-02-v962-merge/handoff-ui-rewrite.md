# Codex Handoff — UI 重写计划 + 服务端连接检查

## 任务 A：服务端连接检查

### 当前连接架构

```
Browser → Vite dev server (:5173)
  ├── proxy /audit/* → http://{APP_SERVER_HOST}:{APP_SERVER_PORT}
  └── proxy /health  → http://{APP_SERVER_HOST}:{APP_SERVER_PORT}

生产/Docker → VITE_API_BASE 直接指向后端
```

### 鉴权链路

```
ui/.env.local: VITE_TENANT_TOKEN=<tenant-key>
→ client.ts: Authorization: Bearer ${VITE_TENANT_TOKEN}
→ server/api.py: verify_bearer_token 对比 TENANT_KEYS
```

### 需要检查的潜在问题

请逐项检查并给出结论：

1. **Vite proxy 配置**（`ui/vite.config.ts`）：
   - proxy target 是否优先读取 `VITE_API_PROXY_TARGET`？
   - 如果没有配置任何环境变量，默认值是否为 `http://127.0.0.1:8000`？
   - `0.0.0.0` 是否已自动转换为 `127.0.0.1`？

2. **鉴权边界**（`server/api.py`）：
   - 无 token 请求是否返回 401 而非 422/500？
   - 默认 tenant key 未设置 `ALLOW_INSECURE_DEFAULT_TENANT_KEY=1` 时是否返回 503？
   - CORS 只允许 `localhost:5173`，生产部署时是否需要更改？

3. **Health 端点**：
   - `/health` 是否不需要鉴权即可访问？
   - `ConnectionStatus.tsx` 调用 `/health` 的代码是否绕过了 Bearer token 检查？

4. **类型契约一致性**：
   - `ui/src/types/index.ts` 中 `AuditResult` 的字段是否与 `server/core.py` 的 `audit-result.schema.json` 一致？
   - 如果不一致，列出差异字段

5. **轮询竞态**（`TaskDetail.tsx`）：
   - 组件卸载时 polling interval 是否已正确清理？
   - result fetch 是否在 status 到达 `completed` 时才发生（不重复 fetch）？

输出：连接检查报告，列出每项状态（OK / ISSUE / WARNING）及说明。

---

## 任务 B：UI 重写计划

### 当前 UI 现状

```
ui/src/
├── pages/
│   ├── TaskList.tsx      # 任务列表（stateful，40+ 行 filter/search/pagination）
│   ├── SubmitExpense.tsx # 报销填报（40+ 字段，单页表单，~800 行）
│   └── TaskDetail.tsx    # 任务详情（轮询 + 结果展示，~500 行）
├── components/
│   ├── Layout.tsx         # 导航栏外壳
│   ├── StatusBadge.tsx    # 状态徽标
│   └── ConnectionStatus.tsx # 后端连接横幅
├── api/client.ts          # fetch 封装
├── types/index.ts         # 类型定义
└── lib/
    ├── reimbursementLabels.ts
    └── submissionSummary.ts
```

当前页面的主要问题：
1. `SubmitExpense.tsx` 是 800+ 行单文件表单，难以维护
2. 页面风格是开发者调试工具风格，缺少真实企业审核平台的 UI 质感
3. 任务列表缺少统计总览（待审核数、今日完成等）
4. 审核结果展示缺乏视觉层次（风险评分、证据链、策略引用堆在一起）
5. 整体缺少 loading skeleton、empty state、error boundary 的统一样式

### 重写目标

保持技术栈不变（React 18 + TypeScript + Tailwind CSS v3 + React Router v6）。
**不引入新的 UI 组件库**（维持零运行时 CSS 依赖原则）。

#### 页面重构方向

**1. 仪表板页（新增 `/` 替代纯列表）**
- 顶部 3 个统计卡片：今日提交数 / 待审核 / 通过率
- 下方是精简任务列表（只展示 claim_id、状态、金额概要、提交时间）
- 状态 filter 改为 tabs 样式

**2. 报销填报页（`/submit` 重构为多步表单）**
- 步骤 1：基础信息（报销人、部门、费用类型、总金额）
- 步骤 2：明细与发票（金额拆分、发票信息）
- 步骤 3：附件上传（拖拽上传，分类选择）
- 步骤 4：确认提交（JSON 预览 + 提交）
- 每步有进度条，支持上一步/下一步

**3. 任务详情页（`/tasks/:id` 重构为分区卡片）**
- 顶部：状态横幅（进行中 pulse 动画 / 已完成颜色）
- 卡片 1：裁定结论（大字展示 conclusion，verdict 徽标，risk_score 进度条）
- 卡片 2：风险维度（5 维雷达图替代纯列表）— 用 SVG 原生实现，不依赖 chart 库
- 卡片 3：证据与策略引用（折叠/展开式 accordion）
- 卡片 4：原始提交摘要（折叠，从 localStorage 读）
- 卡片 5：操作（复制 request_id，返回列表）

**4. 组件抽象**
- 新增：`Stepper.tsx`（多步表单进度指示）
- 新增：`StatCard.tsx`（统计卡片）
- 新增：`RiskRadar.tsx`（SVG 原生 5 维风险图）
- 新增：`Accordion.tsx`（折叠/展开区块）
- 新增：`Skeleton.tsx`（统一 loading 骨架）
- 重构：`Layout.tsx`（侧边栏导航，不再是顶部导航）

### 文件拆分要求

`SubmitExpense.tsx` 拆为：
- `pages/SubmitExpense/index.tsx`（步骤状态机）
- `pages/SubmitExpense/Step1BasicInfo.tsx`
- `pages/SubmitExpense/Step2InvoiceDetail.tsx`
- `pages/SubmitExpense/Step3Attachments.tsx`
- `pages/SubmitExpense/Step4Preview.tsx`

### API 契约约束（不得改动）

以下接口调用逻辑保持不变，只改展示层：
- `listTasks()` / `getTask()` / `getTaskResult()` / `submitExpense()` / `getHealth()`
- `SubmitFormData` 类型字段保持兼容（可增加，不删除已有字段）
- `localStorage` key `enterprise-audit:submission-summaries:v1` 保持不变

### 验收标准

1. `cd ui && npm run build` 通过，无 TypeScript 错误
2. 三个页面（TaskList/SubmitExpense/TaskDetail）均可正常渲染
3. SubmitExpense 改为 4 步骤表单，进度条正常运行
4. TaskDetail 审核结果卡片包含 conclusion / risk_score 进度条 / risk_dimensions 展示
5. 无新增外部 npm 依赖（不允许 `npm install` 新包）
6. 所有现有 API 调用保持兼容
7. `ruff check .`（Python）通过（UI 改动不影响后端）

---

## 输出要求

1. **连接检查报告**（Markdown，直接输出结论）
2. **UI 重写实施**：按上述方案直接编写代码，完成后说明每个文件的变更摘要
