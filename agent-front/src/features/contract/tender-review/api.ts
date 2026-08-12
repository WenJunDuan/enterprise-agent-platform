import { authHeaders, handleResponse, url } from '@/features/audit/api'
import type {
  AuditResult,
  ReasonDetail,
  TaskStatus,
} from '@/features/audit/types'
import type { TenderProjectStatus, TenderScenario } from './types'

const DEFAULT_POLL_INTERVAL_MS = 3000
const DEFAULT_POLL_TIMEOUT_MS = 10 * 60 * 1000

export type TenderProjectCreateRequest = {
  scenario?: TenderScenario
  tender_no?: string | null
  title?: string | null
  tenderee?: string | null
  method?: string | null
  control_price?: string | null
  funding_type?: 'state_funded' | 'other' | 'unknown' | null
}

export type TenderProjectResponse = {
  project_id: string
  scenario: TenderScenario
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
  bidder_name?: string | null
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
  bidder_name?: string | null
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
  policy_refs: (string | ReasonDetail)[]
  evidence_chain?: Array<{
    source?: string
    finding?: string
    conclusion?: string
    /** 页号所属坐标系：converted = Office→PDF 转换稿页号，原文档页号不可用 */
    page_kind?: 'original' | 'converted'
  }>
}

/** 横比生命周期（KD2）：GET 恒 200，用 status 表达，不再靠 404 猜"还没算"。 */
export type TenderCompareStatus =
  | 'none'
  | 'pending'
  | 'running'
  | 'failed'
  | 'ready'

export type TenderCompareResponse = {
  project_id: string
  status: TenderCompareStatus
  /** failed 时的脱敏原因（服务端已去 stack trace / 路径）。 */
  error_detail?: string | null
  /** 尚未算出结果时为 null（status=none/pending/failed）。 */
  result: TenderCompareResult | null
  stale: boolean
  computed_at?: string | null
  input_result_ids?: string[] | null
}

export type EvaluateTenderUploadRequest = {
  bidderName?: string
  tenderFiles: File[]
  bidderFiles: File[]
  form?: Record<string, unknown>
  /** R6-R2：预热 bid_id（上传即 OCR 时 uploadBid 返回）→ 评标复用预热 OCR，免重 OCR。 */
  bidId?: string
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
  scenario?: TenderScenario
  limit?: number
  offset?: number
}): Promise<TenderProjectResponse[]> {
  const qs = new URLSearchParams()
  if (params?.status) qs.set('status', params.status)
  if (params?.scenario) qs.set('scenario', params.scenario)
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
  const res = await fetch(
    url(`/tender/projects/${encodeURIComponent(projectId)}`),
    {
      headers: authHeaders(),
    }
  )
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
      bid_id: request.bidId || undefined, // R6-R2：评标复用预热 OCR
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

export async function getTenderTask(
  requestId: string
): Promise<TenderTaskStatusResponse> {
  const res = await fetch(
    url(`/tender/tasks/${encodeURIComponent(requestId)}`),
    {
      headers: authHeaders(),
    }
  )
  return handleResponse<TenderTaskStatusResponse>(res)
}

export async function getTenderTaskResult(
  requestId: string
): Promise<AuditResult> {
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
  const res = await fetch(
    url(`/tender/tasks/${encodeURIComponent(requestId)}`),
    {
      method: 'DELETE',
      headers: authHeaders(),
    }
  )
  if (!res.ok) await handleResponse(res)
}

/**
 * 删除整个招标项目（级联删投标任务 / 结论 / 横比）。
 *
 * 后端 DELETE /tender/projects/{id}：空项目也能删干净，有运行中任务时回 409。
 */
export async function deleteTenderProject(projectId: string): Promise<void> {
  const res = await fetch(
    url(`/tender/projects/${encodeURIComponent(projectId)}`),
    {
      method: 'DELETE',
      headers: authHeaders(),
    }
  )
  if (!res.ok) await handleResponse(res)
}

// ── P3 OCR 预热 API ────────────────────────────────────────────────────────────

/**
 * OCR status values from the backend.
 *
 * H3 KD2 新增两档：`degraded`（底稿完整但含本地兜底引擎的降级段）、`partial`（部分文件失败或
 * 缺页）。两者都是**终态且底稿可用**——判据统一走 `./ocr-status`，不要在消费点各写 `=== 'ready'`。
 */
export type OcrStatus =
  | 'pending'
  | 'running'
  | 'ready'
  | 'degraded'
  | 'partial'
  | 'failed'

export type DocsStatusTenderDoc = {
  ocr_status: OcrStatus
  /** R1: criteria 抽取状态（与 ocr_status 独立轮询）。旧后端可能不返回。 */
  criteria_status?: CriteriaStatus
}

export type DocsStatusBid = {
  bid_id: string
  bidder_name: string | null
  ocr_status: OcrStatus
}

export type DocsStatusResponse = {
  tender_doc: DocsStatusTenderDoc | null
  bids: DocsStatusBid[]
}

/**
 * Upload tender (招标) document files and trigger background OCR.
 *
 * @param projectId - Tender project identifier.
 * @param files - Tender document files to upload.
 * @returns Immediate response with ocr_status=running.
 */
export async function uploadTenderDoc(
  projectId: string,
  files: File[]
): Promise<{ project_id: string; ocr_status: OcrStatus }> {
  const body = new FormData()
  for (const file of files) {
    body.append('files', file)
  }
  const res = await fetch(
    url(`/tender/projects/${encodeURIComponent(projectId)}/tender-doc`),
    {
      method: 'POST',
      headers: authHeaders(),
      body,
    }
  )
  return handleResponse<{ project_id: string; ocr_status: OcrStatus }>(res)
}

/**
 * Upload a single bidder's (投标) document files and trigger background OCR.
 *
 * @param projectId - Tender project identifier.
 * @param bidderName - Display name of the bidder.
 * @param files - Bid document files to upload.
 * @returns Immediate response with bid_id and ocr_status=running.
 */
export async function uploadBid(
  projectId: string,
  bidderName: string | undefined,
  files: File[]
): Promise<{ bid_id: string; ocr_status: OcrStatus }> {
  const body = new FormData()
  if (bidderName?.trim()) body.append('bidder_name', bidderName.trim())
  for (const file of files) {
    body.append('files', file)
  }
  const res = await fetch(
    url(`/tender/projects/${encodeURIComponent(projectId)}/bids`),
    {
      method: 'POST',
      headers: authHeaders(),
      body,
    }
  )
  return handleResponse<{ bid_id: string; ocr_status: OcrStatus }>(res)
}

// ── R1 招标信息抽取（criteria + tender_info）─────────────────────────────────────

/** criteria 抽取状态（与 OCR 状态独立）。 */
export type CriteriaStatus = 'pending' | 'running' | 'ready' | 'failed'

/** 单个评分项（镜像 .claude/contracts/tender/criteria.schema.json 的 items[]，仅取 UI 所需字段）。 */
export type TenderCriteriaItem = {
  item: string
  max: number | null
  scoring_rule?: string
  source_ref?: string
  tag?: string
  score_mode?:
    | 'deduction'
    | 'banded'
    | 'additive'
    | 'formula'
    | 'pass_fail'
    | 'manual'
  evaluator_type?: 'objective' | 'subjective' | 'mixed'
  deductions?: Array<{ condition?: string; points?: number }>
  bands?: Array<{ level?: string; points?: number }>
  awards?: Array<{ condition?: string; points?: number }>
}

/** 项目评分标准（招标文件评标办法直读解析）。 */
export type TenderCriteria = {
  source_ref?: string
  method?: string
  total_max?: number
  items: TenderCriteriaItem[]
  rejection_rules?: Array<{ condition?: string; source_ref?: string }>
}

/** 招标基本信息（OCR 抽取，全 optional）。 */
export type TenderInfo = {
  tender_no?: string | null
  project_name?: string | null
  tenderee?: string | null
  control_price?: string | null
  method?: string | null
  funding_hint?: string | null
}

/**
 * X2：投标单位案卷头信息（结论 `extracted_data.bidder_info`，对齐
 * `.claude/contracts/tender/bidder-info.schema.json`，全字段 optional）。
 */
export type TenderBidderInfo = {
  bidder_name?: string | null
  credit_code?: string | null
  source_refs?: string[] | null
}

/** GET /tender/projects/{id}/tender-doc 响应。 */
export type TenderDocInfoResponse = {
  ocr_status: OcrStatus
  ocr_clarity: string | null
  criteria_status: CriteriaStatus
  criteria: TenderCriteria | null
  tender_info: TenderInfo | null
  tender_files: string[]
}

/**
 * Read the tender (招标) document layer info: OCR status + extracted criteria + tender_info.
 *
 * @param projectId - Tender project identifier.
 * @returns OCR/criteria status plus extracted 招标信息 (null until criteria_status=ready).
 */
export async function getTenderDocInfo(
  projectId: string
): Promise<TenderDocInfoResponse> {
  const res = await fetch(
    url(`/tender/projects/${encodeURIComponent(projectId)}/tender-doc`),
    {
      headers: authHeaders(),
    }
  )
  return handleResponse<TenderDocInfoResponse>(res)
}

/**
 * Poll OCR readiness for all docs under a tender project (P3 two-step upload).
 *
 * @param projectId - Tender project identifier.
 * @returns Current OCR status for tender doc and each bid doc.
 */
export async function getDocsStatus(
  projectId: string
): Promise<DocsStatusResponse> {
  const res = await fetch(
    url(`/tender/projects/${encodeURIComponent(projectId)}/docs-status`),
    {
      headers: authHeaders(),
    }
  )
  return handleResponse<DocsStatusResponse>(res)
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
  options: WaitOptions<TenderCompareResponse> = {}
): Promise<TenderCompareResponse> {
  const startedAt = Date.now()
  const intervalMs = options.intervalMs ?? DEFAULT_POLL_INTERVAL_MS
  const timeoutMs = options.timeoutMs ?? DEFAULT_POLL_TIMEOUT_MS

  for (;;) {
    const compare = await getTenderCompare(projectId)
    options.onUpdate?.(compare)
    if (compare.status === 'failed') {
      throw new Error(compare.error_detail || '横比计算失败，请重新横比。')
    }
    if (compare.status === 'ready' && !compare.stale) return compare
    if (Date.now() - startedAt > timeoutMs) {
      throw new Error('横比结果等待超时，请稍后在分析中心重新查看。')
    }
    await sleep(intervalMs)
  }
}

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}
