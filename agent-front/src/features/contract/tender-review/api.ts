import { authHeaders, handleResponse, url } from '@/features/audit/api'
import type { AuditResult, TaskStatus } from '@/features/audit/types'
import type { TenderProjectStatus } from './types'

const DEFAULT_POLL_INTERVAL_MS = 3000
const DEFAULT_POLL_TIMEOUT_MS = 10 * 60 * 1000

export type TenderProjectCreateRequest = {
  tender_no?: string | null
  title?: string | null
  tenderee?: string | null
  method?: string | null
  control_price?: string | null
  funding_type?: 'state_funded' | 'other' | 'unknown' | string | null
}

export type TenderProjectResponse = {
  project_id: string
  tender_no?: string | null
  title?: string | null
  tenderee?: string | null
  method?: string | null
  control_price?: string | null
  funding_type?: string | null
  status: string
  created_at: string
  updated_at: string
}

export type TenderProjectBid = {
  request_id: string
  claim_id?: string | null
  status: TaskStatus | TenderProjectStatus | string
  verdict?: string | null
}

export type TenderProjectDetailResponse = TenderProjectResponse & {
  bidder_count: number
  bids: TenderProjectBid[]
  recommended_bidder?: string | null
  compare_stale?: boolean
}

export type TenderSubmitAcceptedResponse = {
  request_id: string
  status: string
  mode: string
  task_status_url: string
}

export type TenderTaskStatusResponse = {
  request_id: string
  status: TaskStatus
  mode: string
  claim_id?: string | null
  error_detail?: string | null
  progress_message?: string | null
  submitted_at?: string | null
  started_at?: string | null
  finished_at?: string | null
  updated_at: string
}

export type TenderProjectResultSummary = {
  request_id: string
  claim_id?: string | null
  verdict?: string | null
  manual_review_reason?: string | null
  created_at?: string | null
}

export type TenderCompareBidder = {
  claim_id: string
  bid_price?: { amount?: number | null; currency?: string | null } | null
  price_score?: number | null
  other_score?: number | null
  total_score?: number | null
  rank?: number | null
  status: 'scored' | 'manual_review' | 'rejected' | string
  note?: string
}

export type TenderCompareResult = {
  project_id: string
  method?: string | null
  bidders: TenderCompareBidder[]
  recommended: string | null
  provisional: boolean
  warnings: string[]
  explanation?: string
  policy_refs: string[]
  evidence_chain?: Array<{
    source?: string
    finding?: string
    conclusion?: string
  }>
}

export type TenderCompareResponse = {
  project_id: string
  result: TenderCompareResult
  stale: boolean
  computed_at?: string | null
  input_result_ids?: string[] | null
}

export type EvaluateTenderUploadRequest = {
  bidderName?: string
  tenderFiles: File[]
  bidderFiles: File[]
  form?: Record<string, unknown>
}

export type WaitOptions<T> = {
  intervalMs?: number
  timeoutMs?: number
  onUpdate?: (value: T) => void
}

export async function createTenderProject(
  body: TenderProjectCreateRequest
): Promise<TenderProjectResponse> {
  const res = await fetch(url('/tender/projects'), {
    method: 'POST',
    headers: {
      ...authHeaders(),
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  })
  return handleResponse<TenderProjectResponse>(res)
}

export async function listTenderProjects(params?: {
  status?: TenderProjectStatus | string
  limit?: number
  offset?: number
}): Promise<TenderProjectResponse[]> {
  const qs = new URLSearchParams()
  if (params?.status) qs.set('status', params.status)
  if (params?.limit != null) qs.set('limit', String(params.limit))
  if (params?.offset != null) qs.set('offset', String(params.offset))
  const query = qs.toString() ? `?${qs.toString()}` : ''
  const res = await fetch(url(`/tender/projects${query}`), {
    headers: authHeaders(),
  })
  return handleResponse<TenderProjectResponse[]>(res)
}

export async function getTenderProject(
  projectId: string
): Promise<TenderProjectDetailResponse> {
  const res = await fetch(url(`/tender/projects/${encodeURIComponent(projectId)}`), {
    headers: authHeaders(),
  })
  return handleResponse<TenderProjectDetailResponse>(res)
}

export async function evaluateTenderProjectDirectory(
  projectId: string,
  directoryPath: string
): Promise<TenderSubmitAcceptedResponse> {
  const res = await fetch(
    url(`/tender/projects/${encodeURIComponent(projectId)}/evaluate`),
    {
      method: 'POST',
      headers: {
        ...authHeaders(),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        mode: 'directory',
        directory_path: directoryPath,
      }),
    }
  )
  return handleResponse<TenderSubmitAcceptedResponse>(res)
}

export async function evaluateTenderProjectUpload(
  projectId: string,
  request: EvaluateTenderUploadRequest
): Promise<TenderSubmitAcceptedResponse> {
  const body = new FormData()
  const tenderFileNames = request.tenderFiles.map((file) => file.name)
  const bidderFileNames = request.bidderFiles.map((file) => file.name)
  body.append('mode', 'upload')
  body.append(
    'form_json',
    JSON.stringify({
      ...request.form,
      bidder_name: request.bidderName?.trim() || undefined,
      tender_files: tenderFileNames,
      bidder_files: bidderFileNames,
    })
  )
  for (const file of [...request.tenderFiles, ...request.bidderFiles]) {
    body.append('files', file)
  }

  const res = await fetch(
    url(`/tender/projects/${encodeURIComponent(projectId)}/evaluate`),
    {
      method: 'POST',
      headers: authHeaders(),
      body,
    }
  )
  return handleResponse<TenderSubmitAcceptedResponse>(res)
}

export async function listTenderProjectResults(
  projectId: string,
  params?: { limit?: number; offset?: number }
): Promise<TenderProjectResultSummary[]> {
  const qs = new URLSearchParams()
  if (params?.limit != null) qs.set('limit', String(params.limit))
  if (params?.offset != null) qs.set('offset', String(params.offset))
  const query = qs.toString() ? `?${qs.toString()}` : ''
  const res = await fetch(
    url(`/tender/projects/${encodeURIComponent(projectId)}/results${query}`),
    {
      headers: authHeaders(),
    }
  )
  return handleResponse<TenderProjectResultSummary[]>(res)
}

export async function getTenderProjectResult(
  projectId: string,
  requestId: string
): Promise<AuditResult> {
  const res = await fetch(
    url(
      `/tender/projects/${encodeURIComponent(projectId)}/results/${encodeURIComponent(requestId)}`
    ),
    {
      headers: authHeaders(),
    }
  )
  return handleResponse<AuditResult>(res)
}

export async function triggerTenderCompare(
  projectId: string
): Promise<TenderSubmitAcceptedResponse> {
  const res = await fetch(
    url(`/tender/projects/${encodeURIComponent(projectId)}/compare`),
    {
      method: 'POST',
      headers: authHeaders(),
    }
  )
  return handleResponse<TenderSubmitAcceptedResponse>(res)
}

export async function getTenderCompare(
  projectId: string
): Promise<TenderCompareResponse> {
  const res = await fetch(
    url(`/tender/projects/${encodeURIComponent(projectId)}/compare`),
    {
      headers: authHeaders(),
    }
  )
  return handleResponse<TenderCompareResponse>(res)
}

export async function getTenderCompareOrNull(
  projectId: string
): Promise<TenderCompareResponse | null> {
  const res = await fetch(
    url(`/tender/projects/${encodeURIComponent(projectId)}/compare`),
    {
      headers: authHeaders(),
    }
  )
  if (res.status === 404) return null
  return handleResponse<TenderCompareResponse>(res)
}

export async function getTenderTask(
  requestId: string
): Promise<TenderTaskStatusResponse> {
  const res = await fetch(url(`/tender/tasks/${encodeURIComponent(requestId)}`), {
    headers: authHeaders(),
  })
  return handleResponse<TenderTaskStatusResponse>(res)
}

export async function getTenderTaskResult(requestId: string): Promise<AuditResult> {
  const res = await fetch(
    url(`/tender/tasks/${encodeURIComponent(requestId)}/result`),
    {
      headers: authHeaders(),
    }
  )
  return handleResponse<AuditResult>(res)
}

export async function retryTenderTask(
  requestId: string
): Promise<TenderTaskStatusResponse> {
  const res = await fetch(
    url(`/tender/tasks/${encodeURIComponent(requestId)}/retry`),
    {
      method: 'POST',
      headers: authHeaders(),
    }
  )
  return handleResponse<TenderTaskStatusResponse>(res)
}

export async function deleteTenderTask(requestId: string): Promise<void> {
  const res = await fetch(url(`/tender/tasks/${encodeURIComponent(requestId)}`), {
    method: 'DELETE',
    headers: authHeaders(),
  })
  if (!res.ok) await handleResponse(res)
}

export async function waitForTenderTask(
  requestId: string,
  options: WaitOptions<TenderTaskStatusResponse> = {}
): Promise<TenderTaskStatusResponse> {
  const startedAt = Date.now()
  const intervalMs = options.intervalMs ?? DEFAULT_POLL_INTERVAL_MS
  const timeoutMs = options.timeoutMs ?? DEFAULT_POLL_TIMEOUT_MS

  for (;;) {
    const task = await getTenderTask(requestId)
    options.onUpdate?.(task)
    if (task.status === 'completed') return task
    if (task.status === 'failed') {
      throw new Error(task.error_detail || '评标任务失败，请稍后重试。')
    }
    if (Date.now() - startedAt > timeoutMs) {
      throw new Error('评标任务等待超时，请稍后在历史评审中查看结果。')
    }
    await sleep(intervalMs)
  }
}

export async function waitForTenderCompare(
  projectId: string,
  options: WaitOptions<TenderCompareResponse | null> = {}
): Promise<TenderCompareResponse> {
  const startedAt = Date.now()
  const intervalMs = options.intervalMs ?? DEFAULT_POLL_INTERVAL_MS
  const timeoutMs = options.timeoutMs ?? DEFAULT_POLL_TIMEOUT_MS

  for (;;) {
    const compare = await getTenderCompareOrNull(projectId)
    options.onUpdate?.(compare)
    if (compare && !compare.stale) return compare
    if (Date.now() - startedAt > timeoutMs) {
      throw new Error('横比结果等待超时，请稍后在分析中心重新查看。')
    }
    await sleep(intervalMs)
  }
}

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}
