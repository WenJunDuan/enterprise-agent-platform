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

export interface AuditResult {
  claim_id?: string
  verdict?: Verdict
  risk_score?: number
  summary?: string
  policy_refs?: string[]
  evidence_chain?: Record<string, unknown>[]
  manual_review_reason?: string
  [key: string]: unknown
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
