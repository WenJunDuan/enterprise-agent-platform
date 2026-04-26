import type { AuditTask, AuditResult, SubmitFormData, SubmitAcceptedResponse } from '../types'

const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? '/'
const API_KEY = (import.meta.env.VITE_API_KEY as string | undefined) ?? ''

function authHeaders(): HeadersInit {
  return { Authorization: `Bearer ${API_KEY}` }
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let message = `HTTP ${res.status}`
    try {
      const body = await res.json()
      if (body?.error?.message) message = body.error.message
      else if (typeof body?.detail === 'string') message = body.detail
    } catch {
      // ignore parse errors
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

export async function submitExpense(
  formData: SubmitFormData,
  files: File[],
): Promise<SubmitAcceptedResponse> {
  const body = new FormData()
  body.append('mode', 'upload')
  body.append('form_json', JSON.stringify(formData))
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
