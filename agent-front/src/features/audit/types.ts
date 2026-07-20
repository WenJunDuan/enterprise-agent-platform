export type TaskStatus = 'accepted' | 'running' | 'completed' | 'failed'

export interface AuditTask {
  request_id: string
  status: TaskStatus
  mode: string
  claim_id: string | null
  error_detail: string | null
  progress_message: string | null
  submitted_at: string | null
  started_at: string | null
  finished_at: string | null
  updated_at: string
}

export type Verdict = 'approved' | 'rejected' | 'manual_review'

/**
 * 契约里 reasons / policy_refs 是字符串数组，但旧存档结果或网关模型
 * 可能返回 {code, description, severity} 形态的对象。前端类型放宽为联合，
 * 渲染时统一经 toText() 拍平，避免直接把对象塞进 JSX 触发 React #31。
 */
export interface ReasonDetail {
  code?: string
  description?: string
  severity?: string
  message?: string
  reason?: string
  [key: string]: unknown
}

export interface AuditResult {
  claim_id?: string
  verdict?: Verdict
  result?: boolean
  conclusion?: '合规' | '不合规' | '待人工复核' | string
  explanation?: string
  reasons?: (string | ReasonDetail)[]
  risk_score?: number
  summary?: string
  policy_refs?: (string | ReasonDetail)[]
  extracted_data?: Record<string, unknown>
  evidence_chain?: EvidenceItem[]
  // 契约是 RiskDimension[]，但旧数据/模型可能给成 {name: score} 映射；渲染前经 normalizeRiskDimensions 兜底。
  risk_dimensions?: RiskDimension[] | Record<string, number>

  reviewed_by?: string
  timestamp?: string
  manual_review_reason?: string
  [key: string]: unknown
}

export interface EvidenceItem {
  source?: string
  finding?: string
  conclusion?: string
  [key: string]: unknown
}

export interface RiskDimension {
  name: 'invoice' | 'amount' | 'approval' | 'budget' | 'anomaly' | string
  score: number
}

export interface SubmitFormData {
  case_id: string
  applicant_name: string
  applicant_employee_id: string
  department: string
  cost_center: string
  legal_entity: string
  project_name: string
  customer_name: string
  submission_date: string
  expense_type: ExpenseType
  currency: string
  urgency: string
  reimbursement_reason: string
  total_amount: string
  tax_amount: string
  net_amount: string
  payment_method: string
  paid_by_company_card: boolean
  has_cash_advance: boolean
  cash_advance_id: string
  cash_advance_amount: string
  budget_subject: string
  budget_remaining: string
  invoice_type: string
  invoice_code: string
  invoice_number: string
  invoice_issue_date: string
  invoice_seller_name: string
  invoice_seller_tax_id: string
  invoice_buyer_title: string
  invoice_validation_status: string
  invoice_title_mismatch: boolean
  invoice_amount_matches_claim: boolean
  travel_from_city: string
  travel_to_city: string
  travel_start_date: string
  travel_end_date: string
  transportation_type: string
  hotel_nights: string
  traveler_count: string
  has_pre_trip_approval: boolean
  entertainment_target: string
  entertainment_company: string
  participant_count: string
  per_capita_amount: string
  entertainment_period: string
  business_purpose: string
  approval_id: string
  approver_name: string
  approval_status: string
  scenario_flags: ScenarioFlag[]
  attachment_summaries: AttachmentSummary[]
  notes: string
}

export interface SubmitAcceptedResponse {
  request_id: string
  status: string
  mode: string
  task_status_url: string
}

export interface HealthResponse {
  status: string
  app_server?: {
    ok?: boolean
    running?: boolean
    [key: string]: unknown
  }
  failing_checks?: string[]
  advisories?: string[]
  [key: string]: unknown
}

export type ExpenseType =
  | '差旅报销'
  | '业务招待'
  | '办公采购'
  | '交通通讯'
  | '培训会议'
  | '其他费用'

export type AttachmentCategory =
  | 'invoice'
  | 'itinerary'
  | 'payment_proof'
  | 'approval'
  | 'contract'
  | 'other'

export type ScenarioFlag =
  | 'duplicate_invoice'
  | 'missing_attachment'
  | 'amount_mismatch'
  | 'late_submission'
  | 'over_budget'
  | 'over_standard_hotel'
  | 'over_standard_entertainment'
  | 'title_mismatch'
  | 'no_pre_approval'
  | 'split_reimbursement'

export interface AttachmentSummary {
  id: string
  name: string
  size: number
  type: string
  category: AttachmentCategory
  last_modified: number
}

export interface SubmissionSummary {
  request_id: string
  submitted_at: string
  form: SubmitFormData
  attachments: AttachmentSummary[]
}

// ── OCR 文档识别 → 表单回填 ──────────────────────────────────────────────
// 类型对齐 .claude/contracts/ocr/*.schema.json。后端 OCR HTTP 路由尚未实现，
// 当前 OCR 页面使用 mock 数据；契约稳定，类型可直接复用到真实调用。

export type OcrItemKind =
  | 'excel'
  | 'word'
  | 'text'
  | 'pdf_text'
  | 'ocr'
  | 'seal'
  | 'manual'
  | 'error'
export type OcrRoute = 'native' | 'ocr' | 'manual'

/** 识别底稿单文件产物，对应 ocr/extract-result.schema.json。 */
export interface OcrExtractItem {
  path: string
  kind: OcrItemKind
  route?: OcrRoute
  blocks?: string[]
  tables?: { name?: string; rows: string[][] }[]
  pages?: { markdown?: string; [k: string]: unknown }[]
  seals?: OcrSeal[]
  error?: string
  note?: string
  [key: string]: unknown
}

export interface OcrSeal {
  bbox?: number[]
  shape?: string
  text?: string
  color?: string
  confidence?: number
}

export type FormComponent =
  | 'single_line'
  | 'multi_line'
  | 'select'
  | 'number'
  | 'date'
  | 'sub_table'

/** 回填到目标表单的单个字段，对应 ocr/form-fill.schema.json 的 fields[]。 */
export interface FormFillField {
  key: string
  component: FormComponent
  value: unknown
  confidence: number
  source?: string
}

/** 付款节点等子表，对应 form-fill 契约的 sub_tables[]。 */
export interface FormFillSubTable {
  key: string
  columns?: string[]
  rows: Record<string, unknown>[]
}

/** 表单回填结果，对应 .claude/contracts/ocr/form-fill.schema.json。 */
export interface FormFillResult {
  request_id?: string
  form_id?: string
  fields: FormFillField[]
  sub_tables: FormFillSubTable[]
  low_confidence?: string[]
  needs_review: boolean
  evidence?: { source: string; finding: string }[]
}

/** POST /ocr/extract 的同步响应：每文件识别底稿 + 组装文本。 */
export interface OcrExtractResponse {
  request_id: string
  results: OcrExtractItem[]
  block: string
}

/** POST /ocr/fill 的同步响应：识别底稿（左栏）+ 表单回填（右栏）一次返回。 */
export interface OcrFillResponse {
  request_id: string
  results: OcrExtractItem[]
  block: string
  fill: FormFillResult
}

// ── OCR 页级流式任务（POST/GET /ocr/jobs，D9 streaming-ocr T4）───────────
//
// 与同步 /ocr/extract、/ocr/fill 不同：提交立即 202 返回 request_id，识别在
// 后台跑，客户端轮询 GET /ocr/jobs/{request_id} 拿渐进产出的 units（页级或
// 文件级），不必等整份识别完成。当前不做表单回填（仅纯识别）。

export type OcrJobStatusValue = 'queued' | 'running' | 'completed' | 'failed'

/** 单个识别单元：page=null 表文件级产物（excel/word/整份失败等），否则为具体页号（1-based）。 */
export interface OcrJobUnit {
  file: string
  page: number | null
  status: string
  payload: Record<string, unknown>
  from_cache: boolean
}

export interface OcrJobProgress {
  done: number
  total: number
}

/** POST /ocr/jobs 的 202 响应。 */
export interface OcrJobAcceptedResponse {
  request_id: string
  status: string
  task_status_url: string
}

/** GET /ocr/jobs/{request_id} 的轮询响应：进度 + 已产出的 partial units。 */
export interface OcrJobStatusResponse {
  request_id: string
  status: OcrJobStatusValue
  progress: OcrJobProgress | null
  results: OcrJobUnit[]
  error_detail: string | null
}
