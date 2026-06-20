# Codex 交付契约 — tender 评标 + 报销审核 前端 UI 改造

> 来源：用户 2026-06-20 端到端测试后的改进反馈。
> 分工：**CC 出契约 + 盯联调；codex 负责前端实现**。
> 关键结论：**本批几乎零后端改动** —— 项目字段、追加评标的 API 早已就绪，全部是前端工作。

---

## 0. 已就绪的后端 API（codex 直接调，无需改后端）

| 用途 | 端点 | 备注 |
|---|---|---|
| 建项目（**已支持全字段**） | `POST /tender/projects` | body 接受 `{tender_no, title, tenderee, method, control_price, funding_type}` 全 optional → **A①** |
| 追加一家投标评标 | `POST /tender/projects/{project_id}/evaluate` | multipart `mode=upload` + `files`/`file` → **B⑥** |
| 项目列表 | `GET /tender/projects?status&limit&offset` | |
| 项目详情+名册 | `GET /tender/projects/{id}` | 返回 `bids[]`、`bidder_count`、`recommended_bidder`、`compare_stale` |
| 结果回看 | `GET /tender/projects/{id}/results` · `/results/{request_id}` | 删任务后已完成结论仍可回看 |
| 重新审核 | `POST /tender/tasks/{request_id}/retry` | 保留原 project 链接（codex P1.1） |
| 删除任务 | `DELETE /tender/tasks/{request_id}` | running 中拒删（409） |
| 价格横比 | `GET /tender/projects/{id}/compare` | **未就绪/<2 家时返回 404，前端须静默** → E② |

鉴权：`Authorization` 头；本地 `ALLOW_INSECURE_DEFAULT_TENANT_KEY=true` 时可免 key。

项目字段语义（`server/routes/tender.py` 的 `TenderProjectCreateRequest`）：
`tender_no` 招标编号 · `title` 项目名 · `tenderee` 招标人 · `method` 评标方法 ·
`control_price` 标底/控制价 · `funding_type` ∈ `state_funded|other|unknown`（compare 推荐终局护栏用）。

---

## A. 项目创建表单（features/contract/tender-review/）

**A① - 创建项目时允许输入项目信息**
- 现状：创建只生成空壳，`tenderee/control_price/funding_type` 等全 null。
- 目标：创建表单暴露上述 6 个字段输入项，全部 optional，允许只填部分、**先建后补**。提交时塞进 `POST /tender/projects` body。
- `funding_type` 用下拉（国资/其他/未知 → `state_funded|other|unknown`）。
- 验收：建项目后 `GET /tender/projects/{id}` 能看到所填值非 null。
- 备注：详情页「补全编辑已建项目」留 backlog，本次只要创建时能填。

---

## B. tender 列表（项目/任务列表）

- **B①** 列表行加**复选框**（多选）。
- **B②** 行内**移除**「重新审核」「删除」按钮。
- **B③** 「创建评审」按钮移到列表**下方、居右**。
- **B④** 「重新审核」按钮紧跟「创建评审」之后（同一居右操作区）。
- **B⑤** 「删除」「重新审核」改为**对复选框选中行的批量操作**：
  - 删除 → 对每个选中 `DELETE /tender/tasks/{request_id}`。
  - 重新审核 → 对每个选中 `POST /tender/tasks/{request_id}/retry`。
- **B⑥** 加「追加公司审核」入口（同一招标项目追加一家投标人）：
  调 `POST /tender/projects/{id}/evaluate` 上传该投标人文件。**后端已支持，仅缺前端入口按钮 + 上传交互。**
- 验收：行有复选框、无行内重审/删除按钮；创建评审+重新审核居右于列表下方；勾选后可批量删/重审；「追加公司审核」能追加并在名册出现新投标人。

---

## C. 报销审核页（features/audit/）

- **C①** 新建审核（`audit-submit-page.tsx`）：**去掉左侧**「基础信息/发票与场景/附件/预览提交」冗余点击列表（已有上一步/下一步）。改为**顶部步骤条可点击切换** —— 页面已有 `<Tabs value={step} onValueChange={...}>`，把它做成可见步骤指示器 + 可点击跳步，移除左侧重复块。
- **C②** 任务详情页：移除「复制 id」「返回列表」；把「重新审核」挪到详情页；**移除「删除任务」**（删除保留在列表页批量操作）。
- **C③** 任务详情 + 审核界面：**移除「提交摘要」区块**。
- **C④** 任务详情底部任务 id：**完整显示**（不截断），其后加一个小「复制」icon 按钮（点击复制完整 id）。
- 验收：新建审核无左侧冗余块、顶部步骤可点；详情页无复制id/返回列表/删除任务、有重新审核；详情+审核无提交摘要；详情底部 id 完整 + 复制 icon 可用。

---

## D. tender 审核步骤样式

- **D①** 招投标审核步骤指示器改成与**报销审核一致的「可点击」样式**（与 C① 统一交互/视觉）。
- 验收：tender 审核步骤条样式与 audit 一致且可点击跳步。

---

## E. 杂项

- **E②** 前端对 `GET /tender/projects/{id}/compare` 的 **404 静默处理**（视为"横比未就绪"，不在控制台报错、不弹错误）。仅 ≥2 家已完成且用户主动触发时才显示横比入口/结果。
  - 验收：单投标人/未评完场景控制台无 compare 404 报错。

---

## 不在本次范围（backlog）
- 项目信息「详情页补全编辑」（本次只做创建时可填）。
- 追加公司审核做成向导式多步体验（超出"加按钮+上传"的部分）。
- **E① 模型超时 / `[1m]` 变体** 属后端 infra，CC 侧另议，不在 codex 范围。

## 验证命令
```bash
npm --prefix agent-front run lint
npm --prefix agent-front run build
# 端到端（后端已在跑 9999；前端 dev proxy 已指 127.0.0.1:9999）
npm --prefix agent-front run dev
```
