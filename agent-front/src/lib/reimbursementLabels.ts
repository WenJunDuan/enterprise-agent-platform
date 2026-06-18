import type { AttachmentCategory, ExpenseType, ScenarioFlag } from '../types'

export const EXPENSE_TYPES: ExpenseType[] = [
  '差旅报销',
  '业务招待',
  '办公采购',
  '交通通讯',
  '培训会议',
  '其他费用',
]

export const ATTACHMENT_CATEGORIES: { value: AttachmentCategory; label: string }[] = [
  { value: 'invoice', label: '发票/票据' },
  { value: 'itinerary', label: '行程/住宿单' },
  { value: 'payment_proof', label: '付款凭证' },
  { value: 'approval', label: '事前审批' },
  { value: 'contract', label: '合同/订单' },
  { value: 'other', label: '其他材料' },
]

export const SCENARIO_FLAG_OPTIONS: {
  value: ScenarioFlag
  label: string
  description: string
}[] = [
  { value: 'duplicate_invoice', label: '疑似重复发票', description: '同一发票号或金额日期组合可能重复报销' },
  { value: 'missing_attachment', label: '附件不完整', description: '缺少发票、行程单、审批单或付款凭证' },
  { value: 'amount_mismatch', label: '金额不一致', description: '报销金额、发票金额或付款凭证金额不一致' },
  { value: 'late_submission', label: '跨期/逾期报销', description: '发票日期距提交日过久或跨财务期间' },
  { value: 'over_budget', label: '预算超额', description: '预算余额不足或超过项目/部门预算' },
  { value: 'over_standard_hotel', label: '住宿超标', description: '住宿单价、天数或城市标准存在异常' },
  { value: 'over_standard_entertainment', label: '招待超标', description: '人均金额、人数或招待频次可能超标准' },
  { value: 'title_mismatch', label: '发票抬头不符', description: '发票购买方名称与报销主体不一致' },
  { value: 'no_pre_approval', label: '无事前审批', description: '差旅、招待或大额采购缺少事前审批' },
  { value: 'split_reimbursement', label: '疑似拆单', description: '多笔相近金额或同一供应商拆分提交' },
]

export const ATTACHMENT_CATEGORY_LABELS = Object.fromEntries(
  ATTACHMENT_CATEGORIES.map(item => [item.value, item.label]),
) as Record<AttachmentCategory, string>

export const SCENARIO_FLAG_LABELS = Object.fromEntries(
  SCENARIO_FLAG_OPTIONS.map(item => [item.value, item.label]),
) as Record<ScenarioFlag, string>

export function formatFileSize(size: number): string {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

export function formatAmount(amount: string, currency = 'CNY'): string {
  const parsed = Number(amount)
  if (!Number.isFinite(parsed)) return amount || '—'
  return `${currency} ${parsed.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}
