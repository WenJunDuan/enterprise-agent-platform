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
  expense_type: string
}

export interface SubmitAcceptedResponse {
  request_id: string
  status: string
  mode: string
  task_status_url: string
}
