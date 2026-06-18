import type {
  AuditTask,
  AuditResult,
  HealthResponse,
  OcrExtractResponse,
  OcrFillResponse,
  SubmitAcceptedResponse,
} from '../types'

const RAW_BASE = (import.meta.env.VITE_API_BASE as string | undefined) || '/'
const RAW_TENANT_TOKEN = (import.meta.env.VITE_TENANT_TOKEN as string | undefined) || ''
const RAW_LEGACY_API_KEY = (import.meta.env.VITE_API_KEY as string | undefined) || ''
const TENANT_TOKEN = (RAW_TENANT_TOKEN || RAW_LEGACY_API_KEY).trim()
const TENANT_TOKEN_SOURCE = RAW_TENANT_TOKEN
  ? 'VITE_TENANT_TOKEN'
  : RAW_LEGACY_API_KEY
    ? 'VITE_API_KEY（兼容旧名）'
    : '未配置'
const BASE = RAW_BASE

export function getApiRuntimeConfig() {
  return {
    base: BASE,
    displayBase: BASE === '/' ? 'Vite 代理 /' : BASE,
    hasTenantToken: Boolean(TENANT_TOKEN),
    tenantTokenSource: TENANT_TOKEN_SOURCE,
  }
}

function authHeaders(): HeadersInit {
  if (!TENANT_TOKEN) {
    throw new Error('缺少租户 token：请在 agent-front/.env.local 配置 VITE_TENANT_TOKEN')
  }
  const token = TENANT_TOKEN.startsWith('Bearer ') ? TENANT_TOKEN.slice('Bearer '.length).trim() : TENANT_TOKEN
  return { Authorization: `Bearer ${token}` }
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let message = `HTTP ${res.status}`
    const contentType = res.headers.get('content-type') || ''
    if (contentType.includes('application/json')) {
      const body = await res.json()
      if (body?.error?.message) message = body.error.message
      else if (typeof body?.detail === 'string') message = body.detail
    } else {
      const text = await res.text()
      if (text.includes('Unable to connect') || text.includes('ECONNREFUSED')) {
        message = `后端未启动或 Vite 代理目标不可达（HTTP ${res.status}）`
      }
    }
    throw new Error(message)
  }
  return res.json() as Promise<T>
}

function url(path: string): string {
  const base = BASE.endsWith('/') ? BASE.slice(0, -1) : BASE
  return `${base}${path}`
}

export async function listTasks(params?: {
  status?: string
  limit?: number
  offset?: number
}): Promise<AuditTask[]> {
  const qs = new URLSearchParams()
  if (params?.status) qs.set('status', params.status)
  if (params?.limit != null) qs.set('limit', String(params.limit))
  if (params?.offset != null) qs.set('offset', String(params.offset))
  const query = qs.toString() ? `?${qs.toString()}` : ''
  const res = await fetch(url(`/audit/tasks${query}`), {
    headers: authHeaders(),
  })
  return handleResponse<AuditTask[]>(res)
}

export async function getHealth(): Promise<HealthResponse> {
  const res = await fetch(url('/health'))
  if (res.status === 200 || res.status === 503) {
    try {
      return (await res.json()) as HealthResponse
    } catch {
      // 可达但响应非 JSON（如 /health 未被反代显式代理、回退到 SPA index.html）：
      // 后端原点已经应答，视为可达，避免误报“离线”。
      return { status: res.status === 200 ? 'ok' : 'degraded' }
    }
  }
  return handleResponse<HealthResponse>(res)
}

export async function submitExpense(
  formData: unknown,
  files: File[] = [],
): Promise<SubmitAcceptedResponse> {
  const body = new FormData()
  body.append('mode', 'upload')
  if (formData != null) {
    body.append('form_json', JSON.stringify(formData))
  }
  for (const file of files) {
    body.append('files', file)
  }
  const res = await fetch(url('/audit/submit'), {
    method: 'POST',
    headers: authHeaders(),
    body,
  })
  return handleResponse<SubmitAcceptedResponse>(res)
}

export async function getTask(id: string): Promise<AuditTask> {
  const res = await fetch(url(`/audit/tasks/${id}`), {
    headers: authHeaders(),
  })
  return handleResponse<AuditTask>(res)
}

export async function getTaskResult(id: string): Promise<AuditResult> {
  const res = await fetch(url(`/audit/tasks/${id}/result`), {
    headers: authHeaders(),
  })
  return handleResponse<AuditResult>(res)
}

export async function retryTask(id: string): Promise<AuditTask> {
  const res = await fetch(url(`/audit/tasks/${encodeURIComponent(id)}/retry`), {
    method: 'POST',
    headers: authHeaders(),
  })
  return handleResponse<AuditTask>(res)
}

export async function deleteTask(id: string): Promise<void> {
  const res = await fetch(url(`/audit/tasks/${encodeURIComponent(id)}`), {
    method: 'DELETE',
    headers: authHeaders(),
  })
  if (!res.ok) await handleResponse(res)
}

// ── OCR 纯识别（POST /ocr/extract，同步）────────────────────────────────
//
// 后端已实现「纯识别」端点：上传文档 → 同步返回结构化识别底稿（results + block）。
// 注：此端点只做确定性识别，**不含表单回填（form-fill）**；OCR 页面右栏的回填结果
// 目前仍是演示数据，需另接回填端点（后端暂未实现）。

/** 同步纯识别：上传文档 → 结构化识别底稿（每文件 results + 组装 block）。 */
export async function extractOcr(files: File[], runSeal = false): Promise<OcrExtractResponse> {
  const body = new FormData()
  for (const file of files) body.append('files', file)
  const res = await fetch(url(`/ocr/extract${runSeal ? '?run_seal=true' : ''}`), {
    method: 'POST',
    headers: authHeaders(),
    body,
  })
  return handleResponse<OcrExtractResponse>(res)
}

/** 同步识别 + 表单回填：上传文档 + 目标表单 schema → 底稿 + 回填结果（POST /ocr/fill）。 */
export async function fillOcr(
  files: File[],
  formSchema: unknown,
  runSeal = false,
): Promise<OcrFillResponse> {
  const body = new FormData()
  body.append('form_schema', JSON.stringify(formSchema))
  for (const file of files) body.append('files', file)
  const res = await fetch(url(`/ocr/fill${runSeal ? '?run_seal=true' : ''}`), {
    method: 'POST',
    headers: authHeaders(),
    body,
  })
  return handleResponse<OcrFillResponse>(res)
}
