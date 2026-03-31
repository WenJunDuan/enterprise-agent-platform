# Async Audit Submit Serve Design

## Goal

为前端提供一套可直接对接的异步审核服务：

- 测试阶段：前端提交目录路径
- 正式阶段：前端上传 `form_json + files[]`
- 服务端立即返回 `request_id`
- 后台异步执行审核
- 前端轮询任务状态
- 审核完成后通过结果接口读取完整结构化结果与中文审核意见

## Scope

本轮只做 serve 端异步审核提交链路，不改动具体制度规则内容。

涉及内容：

- 新增异步提交接口
- 新增任务状态查询接口
- 增加上传落盘与 case 目录组织
- 复用现有审核能力完成后台执行
- 让前端统一使用 `request_id` 查询结果

不涉及：

- 前端页面本身实现
- 对 OCR、规则库、审核规则内容做业务扩写
- 对第三方对象存储、消息队列、数据库做基础设施升级

## Current State

当前 serve 层已经具备以下能力：

- `POST /audit`：同步提交单个文件或目录路径，返回结构化审核结果
- `GET /results/{request_id}`：按请求读取归档结果
- `GET /requests/{request_id}`：读取请求审计记录
- 本地结果归档位于 `logs/results/by-request/YYYY/MM/DD/{request_id}.json`

当前缺口：

1. 前端没有“提交即返回 request_id、后台继续审核”的异步入口。
2. 测试阶段目录路径提交和正式阶段文件上传还不是同一个服务模型。
3. 服务端缺少独立的审核任务状态存储，前端无法轮询 `accepted/running/completed/failed`。
4. 上传模式还没有统一的 case 落盘目录。

## Design

### 1. 单一异步提交端点

新增统一端点：

- `POST /audit/submit`

它同时支持两种提交模式：

#### 1.1 测试模式：目录路径

请求类型：`application/json`

```json
{
  "mode": "directory",
  "directory_path": "data/case1"
}
```

适用场景：

- 本地测试
- 前端联调阶段
- 已经存在于服务端文件系统上的测试案例

#### 1.2 正式模式：文件上传

请求类型：`multipart/form-data`

字段：

- `mode=upload`
- `form_json=<json string>`
- `files[]`

其中 `form_json` 对应前端真实表单，例如：

```json
{
  "case_id": "case1",
  "applicant_name": "张三",
  "department": "销售部",
  "expense_type": "业务招待",
  "expense_category": "餐饮招待",
  "biz_date": "2026-03-26",
  "participants_total": 5,
  "internal_participants": 4,
  "client_count": 1,
  "description": "中午与客户用餐，申请报销业务招待费。",
  "business_purpose": "客户商务接待与业务沟通",
  "currency": "CNY",
  "notes": ""
}
```

### 2. 提交响应

`POST /audit/submit` 不等待审核完成，立即返回：

```json
{
  "request_id": "uuid",
  "status": "accepted",
  "mode": "directory | upload",
  "task_status_url": "/audit/tasks/{request_id}",
  "result_url": "/results/{request_id}"
}
```

语义：

- `accepted` 只表示任务已被服务端接收
- 不表示 Claude 审核已经完成

### 3. 任务状态接口

新增：

- `GET /audit/tasks/{request_id}`

返回结构：

```json
{
  "request_id": "uuid",
  "status": "accepted | running | completed | failed",
  "mode": "directory | upload",
  "claim_id": "optional",
  "result_file": "optional",
  "error_detail": "optional",
  "updated_at": "2026-03-31T09:30:00+08:00"
}
```

状态定义：

- `accepted`：任务已创建，尚未开始执行
- `running`：正在调用 Claude 审核
- `completed`：审核已完成，结果已归档
- `failed`：审核失败，可查看 `error_detail`

### 4. 统一 case 模型

无论目录模式还是上传模式，后台最终都把输入转成“一个 case 路径”交给审核能力。

#### 4.1 目录模式

- 不复制原目录
- 直接记录 `directory_path`
- 后台任务把该目录作为 case 根目录传给审核流程

#### 4.2 上传模式

服务端创建：

- `data/submissions/{request_id}/`

目录内容：

- `audit-request.json`
- 上传的附件原文件

其中 `audit-request.json` 的结构与当前 [audit-request.json](/Users/mac/workspace/enterprise-agent-platform/data/case1/audit-request.json) 一致，至少包含：

```json
{
  "form": { ... },
  "attachments": [
    {
      "type": "invoice",
      "name": "xxx.pdf",
      "path": "data/submissions/{request_id}/xxx.pdf"
    }
  ]
}
```

这样目录模式和上传模式在审核阶段都会收敛为“一个目录路径”。

### 5. 后台执行模型

`POST /audit/submit` 只负责：

1. 鉴权
2. 校验输入
3. 生成 `request_id`
4. 初始化任务状态为 `accepted`
5. 启动后台异步任务
6. 立即返回提交响应

后台任务负责：

1. 将状态更新为 `running`
2. 解析输入模式：
   - `directory` → 使用原目录
   - `upload` → 使用新建 submission 目录
3. 调用现有审核能力
4. 审核成功后：
   - 由现有结构化结果归档逻辑写入 `logs/results/by-request/...`
   - 更新任务状态为 `completed`
   - 记录 `result_file`、`claim_id`
5. 审核失败后：
   - 更新任务状态为 `failed`
   - 记录 `error_detail`

### 6. 与现有结果接口的关系

任务状态接口只返回任务维度的轻量信息。

完整结果仍通过现有：

- `GET /results/{request_id}`

读取。

这样职责分离：

- `/audit/tasks/{request_id}`：查进度
- `/results/{request_id}`：查完整结果

### 7. 返回给前端的核心结果字段

最终前端页面需要消费的审核结果保持两层：

#### 7.1 审核意见字段

- `result`
- `conclusion`
- `explanation`

#### 7.2 结构化字段

- `extracted_data`
- `reasons`
- `policy_refs`
- `evidence_chain`
- `risk_score`
- `verdict`

前端推荐流程：

1. 提交后拿到 `request_id`
2. 轮询任务状态
3. `completed` 后取 `/results/{request_id}`
4. 页面摘要展示：
   - `result`
   - `conclusion`
   - `explanation`
5. 页面详情展示：
   - `extracted_data`
   - `reasons`
   - `policy_refs`
   - `evidence_chain`

### 8. 错误处理

#### 8.1 提交阶段错误

`POST /audit/submit` 直接返回 4xx/5xx：

- 缺少 `mode`
- `directory_path` 不存在
- `form_json` 非法
- 未上传任何文件
- 鉴权失败

#### 8.2 执行阶段错误

后台任务失败时：

- `POST /audit/submit` 已经成功返回
- 任务状态转为 `failed`
- `error_detail` 记录原因

#### 8.3 结果阶段错误

如果任务是 `completed` 但 `/results/{request_id}` 无记录，应视为服务端一致性错误，需要在任务状态中保留错误信息并标记失败。

## API Summary

### POST /audit/submit

用途：

- 创建异步审核任务

输入：

- `application/json` + `mode=directory`
- `multipart/form-data` + `mode=upload`

输出：

```json
{
  "request_id": "uuid",
  "status": "accepted",
  "mode": "directory",
  "task_status_url": "/audit/tasks/uuid",
  "result_url": "/results/uuid"
}
```

### GET /audit/tasks/{request_id}

用途：

- 查询任务状态

输出：

```json
{
  "request_id": "uuid",
  "status": "running",
  "mode": "directory",
  "claim_id": null,
  "result_file": null,
  "error_detail": null,
  "updated_at": "2026-03-31T09:30:00+08:00"
}
```

### GET /results/{request_id}

用途：

- 查询完整审核结果

输出：

- 复用现有结果详情接口

## Testing Strategy

### 1. 目录模式

- 使用 `data/case1`
- `POST /audit/submit` 提交目录路径
- 轮询 `GET /audit/tasks/{request_id}`
- 最后读取 `GET /results/{request_id}`

### 2. 上传模式

- 通过测试客户端上传一个 `form_json` 和一个 PDF
- 验证：
  - 服务端生成 submission 目录
  - 生成 `audit-request.json`
  - 附件落盘
  - 后台任务可进入 `running/completed`

### 3. 回归验证

- 不破坏现有 `POST /audit`
- 不破坏现有 `GET /results/{request_id}`
- 不破坏现有 request/session/result 存储

## Risks

1. 当前项目还没有独立任务状态仓储，需要新增最小任务状态存储，否则只能复用 request audit，语义不够清晰。
2. 后台异步任务若直接用进程内 `asyncio.create_task`，服务重启后任务状态不会自动恢复；本轮可以接受，但要明确这是单机轻量实现。
3. 上传模式要处理文件名冲突与路径安全，不能直接信任前端文件名。
4. Claude 审核时长不可控，前端轮询策略需要设置合理间隔和超时。
