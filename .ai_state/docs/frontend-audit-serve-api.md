# 前端对接文档：异步审核接口

## 1. 目标

前端通过一个统一提交接口发起审核任务：

- 测试阶段：提交服务端已有目录路径
- 正式阶段：上传 `form_json + files[]`

服务端立即返回 `request_id`，前端通过轮询查询任务状态，任务完成后再读取最终审核结果。

---

## 2. 鉴权

所有请求都需要携带：

```http
Authorization: Bearer sk-default
```

如果后续接入多租户，替换成对应租户的 API key 即可。

---

## 3. 接口总览

本轮前端主要使用 3 个接口：

1. `POST /audit/submit`
2. `GET /audit/tasks/{request_id}`
3. `GET /results/{request_id}`

---

## 4. 提交审核

### 4.1 测试阶段：目录路径提交

请求：

```http
POST /audit/submit
Content-Type: application/json
Authorization: Bearer sk-default
```

请求体：

```json
{
  "mode": "directory",
  "directory_path": "data/case1"
}
```

返回：

```json
{
  "request_id": "faf62e3a-fa35-4d47-acd6-93b74190fe46",
  "status": "accepted",
  "mode": "directory",
  "task_status_url": "/audit/tasks/faf62e3a-fa35-4d47-acd6-93b74190fe46",
  "result_url": "/results/faf62e3a-fa35-4d47-acd6-93b74190fe46"
}
```

语义：

- `accepted` 只表示任务已创建
- 不代表审核已完成

### 4.2 正式阶段：上传表单 + 附件

请求：

```http
POST /audit/submit
Content-Type: multipart/form-data
Authorization: Bearer sk-default
```

表单字段：

- `mode=upload`
- `form_json=<json string>`
- `files[]`

`form_json` 示例：

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

行为：

- 服务端会创建 `data/submissions/{request_id}/`
- 自动生成 `audit-request.json`
- 附件原文件一起落盘

返回与目录模式一致：

```json
{
  "request_id": "uuid",
  "status": "accepted",
  "mode": "upload",
  "task_status_url": "/audit/tasks/uuid",
  "result_url": "/results/uuid"
}
```

---

## 5. 查询任务状态

请求：

```http
GET /audit/tasks/{request_id}
Authorization: Bearer sk-default
```

返回示例：

```json
{
  "request_id": "faf62e3a-fa35-4d47-acd6-93b74190fe46",
  "status": "running",
  "mode": "directory",
  "case_path": "data/case1",
  "claim_id": null,
  "result_file": null,
  "error_detail": null,
  "updated_at": "2026-03-31T09:27:31.691389+00:00"
}
```

状态枚举：

- `accepted`
- `running`
- `completed`
- `failed`

建议前端处理：

- `accepted` / `running`：继续轮询
- `completed`：跳转读取结果详情
- `failed`：展示 `error_detail`

---

## 6. 获取最终审核结果

请求：

```http
GET /results/{request_id}
Authorization: Bearer sk-default
```

返回结构：

```json
{
  "record": {
    "request_id": "...",
    "claim_id": "case1",
    "verdict": "manual_review",
    "result_file": "results/by-request/2026/03/31/....json"
  },
  "payload": {
    "request_id": "...",
    "response": {
      "claim_id": "case1",
      "verdict": "manual_review",
      "result": false,
      "conclusion": "待人工复核",
      "explanation": "根据……规定，……",
      "reasons": [],
      "policy_refs": [],
      "risk_score": 65,
      "extracted_data": {},
      "evidence_chain": [],
      "reviewed_by": "...",
      "timestamp": "..."
    }
  }
}
```

前端通常取：

```ts
const audit = result.payload.response;
```

---

## 7. 前端重点字段

### 7.1 页面摘要区

直接展示：

- `audit.result`
- `audit.conclusion`
- `audit.explanation`

说明：

- `result=true` 表示系统确认合规
- `result=false` 可能是不合规，也可能是待人工复核
- 具体展示以 `conclusion` 为准

### 7.2 页面详情区

展示：

- `audit.extracted_data`
- `audit.reasons`
- `audit.policy_refs`
- `audit.evidence_chain`
- `audit.risk_score`
- `audit.verdict`

建议：

- `extracted_data` 用于表格或 key-value 展示
- `reasons` 用于问题列表
- `policy_refs` 用于规则编号展示
- `evidence_chain` 用于证据链明细展开

---

## 8. 推荐前端调用流程

### 8.1 目录模式

1. 调用 `POST /audit/submit`
2. 拿到 `request_id`
3. 每 2 秒轮询 `GET /audit/tasks/{request_id}`
4. 当 `status === "completed"` 时，调用 `GET /results/{request_id}`
5. 读取 `payload.response`

### 8.2 上传模式

1. 用户填写表单
2. 前端组装 `form_json`
3. 用户上传一个或多个文件
4. 调用 `POST /audit/submit`（multipart）
5. 后续轮询流程与目录模式相同

---

## 9. TypeScript 类型建议

```ts
export type AuditTaskStatus = "accepted" | "running" | "completed" | "failed";

export interface AuditSubmitResponse {
  request_id: string;
  status: "accepted";
  mode: "directory" | "upload";
  task_status_url: string;
  result_url: string;
}

export interface AuditTaskResponse {
  request_id: string;
  status: AuditTaskStatus;
  mode: "directory" | "upload";
  case_path: string;
  claim_id: string | null;
  result_file: string | null;
  error_detail: string | null;
  updated_at: string;
}

export interface AuditResultPayload {
  claim_id: string;
  verdict: "approved" | "rejected" | "manual_review";
  result: boolean;
  conclusion: "合规" | "不合规" | "待人工复核";
  explanation: string;
  reasons: string[];
  policy_refs: string[];
  risk_score: number;
  extracted_data: Record<string, unknown>;
  evidence_chain: Array<{
    source: string;
    finding: string;
    conclusion: string;
  }>;
  reviewed_by: string;
  timestamp: string;
}

export interface ResultDetailResponse {
  record: Record<string, unknown>;
  payload: {
    request_id: string;
    response: AuditResultPayload;
  };
}
```

---

## 10. fetch 示例

### 10.1 目录模式提交

```ts
const res = await fetch("/audit/submit", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    Authorization: "Bearer sk-default",
  },
  body: JSON.stringify({
    mode: "directory",
    directory_path: "data/case1",
  }),
});

const submitPayload = await res.json();
```

### 10.2 轮询状态

```ts
async function pollAuditTask(requestId: string) {
  while (true) {
    const res = await fetch(`/audit/tasks/${requestId}`, {
      headers: {
        Authorization: "Bearer sk-default",
      },
    });

    const task = await res.json();

    if (task.status === "completed" || task.status === "failed") {
      return task;
    }

    await new Promise((resolve) => setTimeout(resolve, 2000));
  }
}
```

### 10.3 获取结果

```ts
const resultRes = await fetch(`/results/${requestId}`, {
  headers: {
    Authorization: "Bearer sk-default",
  },
});

const resultDetail = await resultRes.json();
const audit = resultDetail.payload.response;
```

### 10.4 上传模式提交

```ts
const fd = new FormData();
fd.append("mode", "upload");
fd.append(
  "form_json",
  JSON.stringify({
    case_id: "case1",
    applicant_name: "张三",
    expense_type: "业务招待",
  })
);

for (const file of files) {
  fd.append("files", file);
}

const res = await fetch("/audit/submit", {
  method: "POST",
  headers: {
    Authorization: "Bearer sk-default",
  },
  body: fd,
});

const submitPayload = await res.json();
```

---

## 11. 手工联调命令

### 11.1 目录模式

```bash
curl -X POST http://127.0.0.1:8000/audit/submit \
  -H "Authorization: Bearer sk-default" \
  -H "Content-Type: application/json" \
  -d '{"mode":"directory","directory_path":"data/case1"}'
```

### 11.2 查状态

```bash
curl -H "Authorization: Bearer sk-default" \
  http://127.0.0.1:8000/audit/tasks/<request_id>
```

### 11.3 查结果

```bash
curl -H "Authorization: Bearer sk-default" \
  http://127.0.0.1:8000/results/<request_id>
```

---

## 12. 当前限制

1. 当前后台任务是进程内 `asyncio.create_task`，服务重启后，正在执行的任务不会自动恢复。
2. 当前已经适合单机联调和前端接入阶段，但还不是持久任务队列方案。
3. 上传文件名虽然会做基础清洗，但后续如果上线，还需要更完整的文件大小、类型和安全校验。
