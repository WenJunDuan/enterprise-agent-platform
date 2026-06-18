import type {
  AuditTask,
  AuditResult,
  HealthResponse,
  OcrExtractResponse,
  OcrFillResponse,
  SubmitAcceptedResponse,
} from './types'

const RAW_BASE = (import.meta.env.VITE_API_BASE as string | undefined) || '/'
const RAW_TENANT_PIN_KEYS =
  (import.meta.env.VITE_TENANT_PIN_KEYS as string | undefined) || ''
const BASE = RAW_BASE
const TENANT_TOKEN_STORAGE_KEY = 'enterprise-audit:tenant-token:v1'

function normalizeTenantToken(token: string) {
  const trimmed = token.trim()
  return trimmed.startsWith('Bearer ')
    ? trimmed.slice('Bearer '.length).trim()
    : trimmed
}

export function getConfiguredTenantPinKeys() {
  const raw = RAW_TENANT_PIN_KEYS.trim()
  if (!raw) return {}

  try {
    const parsed = JSON.parse(raw) as unknown
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      return {}
    }

    return Object.fromEntries(
      Object.entries(parsed)
        .map(([pin, token]) => [
          pin.trim(),
          normalizeTenantToken(typeof token === 'string' ? token : ''),
        ])
        .filter(([pin, token]) => pin && token)
    )
  } catch {
    return {}
  }
}

export function getConfiguredTenantPinLength() {
  const pins = Object.keys(getConfiguredTenantPinKeys())
  return pins[0]?.length || 6
}

export function resolveTenantTokenByPin(pin: string) {
  return getConfiguredTenantPinKeys()[pin.trim()] || ''
}

export function getStoredTenantToken() {
  if (typeof window === 'undefined') return ''
  return normalizeTenantToken(
    window.localStorage.getItem(TENANT_TOKEN_STORAGE_KEY) || ''
  )
}

export function getActiveTenantToken() {
  return getStoredTenantToken()
}

export function persistTenantToken(token: string) {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(
    TENANT_TOKEN_STORAGE_KEY,
    normalizeTenantToken(token)
  )
}

export function clearTenantToken() {
  if (typeof window === 'undefined') return
  window.localStorage.removeItem(TENANT_TOKEN_STORAGE_KEY)
}

function getTenantTokenSource() {
  if (getStoredTenantToken()) return '本地登录会话'
  if (Object.keys(getConfiguredTenantPinKeys()).length > 0) {
    return 'VITE_TENANT_PIN_KEYS'
  }
  return '未配置'
}

export function getApiRuntimeConfig() {
  const tenantToken = getActiveTenantToken()
  return {
    base: BASE,
    displayBase: BASE === '/' ? '当前服务' : BASE,
    hasTenantToken: Boolean(tenantToken),
    tenantTokenSource: getTenantTokenSource(),
  }
}

function authHeaders(token = getActiveTenantToken()): HeadersInit {
  if (!token) {
    throw new Error('登录状态已失效，请重新输入 PIN。')
  }
  return { Authorization: `Bearer ${normalizeTenantToken(token)}` }
}

function isGatewayError(status: number) {
  return status === 502 || status === 503 || status === 504
}

function getGatewayErrorMessage() {
  return '服务暂不可用，请稍后重试。'
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let message = '请求失败，请稍后重试。'
    const contentType = res.headers.get('content-type') || ''
    if (contentType.includes('application/json')) {
      const body = await res.json()
      if (body?.error?.message) message = body.error.message
      else if (typeof body?.detail === 'string') message = body.detail
    } else {
      const text = await res.text()
      if (text.includes('Unable to connect') || text.includes('ECONNREFUSED')) {
        message = getGatewayErrorMessage()
      }
    }
    if (isGatewayError(res.status)) {
      message = getGatewayErrorMessage()
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
      return { status: res.status === 200 ? 'ok' : 'degraded' }
    }
  }
  return handleResponse<HealthResponse>(res)
}

export async function submitExpense(
  formData: unknown,
  files: File[] = []
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
// 上传文档后同步返回结构化识别底稿（results + block）。

/** 同步纯识别：上传文档 → 结构化识别底稿（每文件 results + 组装 block）。 */
export async function extractOcr(
  files: File[],
  runSeal = false
): Promise<OcrExtractResponse> {
  const body = new FormData()
  for (const file of files) body.append('files', file)
  const res = await fetch(
    url(`/ocr/extract${runSeal ? '?run_seal=true' : ''}`),
    {
      method: 'POST',
      headers: authHeaders(),
      body,
    }
  )
  return handleResponse<OcrExtractResponse>(res)
}

/** 同步识别 + 表单回填：上传文档 + 目标表单 schema → 底稿 + 回填结果（POST /ocr/fill）。 */
export async function fillOcr(
  files: File[],
  formSchema: unknown,
  runSeal = false
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
