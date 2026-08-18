import type { AttachmentSummary, SubmitFormData } from '../types'
import type { SelectedAttachment } from './types'

export function toAttachmentSummaries(attachments: SelectedAttachment[]): AttachmentSummary[] {
  return attachments.map(item => ({
    id: item.id,
    name: item.file.name,
    size: item.file.size,
    type: item.file.type || 'unknown',
    category: item.category,
    last_modified: item.file.lastModified,
  }))
}

export function today(): string {
  return new Date().toISOString().slice(0, 10)
}

export function createCaseId(): string {
  const compactDate = today().split('-').join('')
  const suffix = String(Math.floor(Math.random() * 9000) + 1000)
  return `EXP-${compactDate}-${suffix}`
}

export function createDefaultForm(): SubmitFormData {
  return {
    case_id: createCaseId(),
    applicant_name: '张三',
    applicant_employee_id: 'E10245',
    department: '企业服务部',
    cost_center: 'CC-OPS-001',
    legal_entity: '示例科技有限公司',
    project_name: '客户交付项目',
    customer_name: '华东重点客户',
    submission_date: today(),
    expense_type: '差旅报销',
    currency: 'CNY',
    urgency: '普通',
    reimbursement_reason: '客户现场沟通、项目实施与业务招待',
    total_amount: '4280.50',
    tax_amount: '242.29',
    net_amount: '4038.21',
    payment_method: '个人垫付',
    paid_by_company_card: false,
    has_cash_advance: false,
    cash_advance_id: '',
    cash_advance_amount: '',
    budget_subject: '销售交付费用',
    budget_remaining: '12000.00',
    invoice_type: '增值税普通发票',
    invoice_code: '031002300111',
    invoice_number: '24567890',
    invoice_issue_date: today(),
    invoice_seller_name: '示例差旅服务有限公司',
    invoice_seller_tax_id: '91310000MA1K000000',
    invoice_buyer_title: '示例科技有限公司',
    invoice_validation_status: '已验真',
    invoice_title_mismatch: false,
    invoice_amount_matches_claim: true,
    travel_from_city: '上海',
    travel_to_city: '杭州',
    travel_start_date: today(),
    travel_end_date: today(),
    transportation_type: '高铁/火车',
    hotel_nights: '2',
    traveler_count: '1',
    has_pre_trip_approval: true,
    entertainment_target: '',
    entertainment_company: '',
    participant_count: '',
    per_capita_amount: '',
    entertainment_period: '晚餐',
    business_purpose: '',
    approval_id: 'APR-2026-0426-001',
    approver_name: '李经理',
    approval_status: '已事前审批',
    scenario_flags: [],
    attachment_summaries: [],
    notes: '',
  }
}
