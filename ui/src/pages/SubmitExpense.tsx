import {
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type FormEvent,
  type ReactNode,
} from 'react'
import { useNavigate } from 'react-router-dom'
import { submitExpense } from '../api/client'
import {
  ATTACHMENT_CATEGORIES,
  ATTACHMENT_CATEGORY_LABELS,
  EXPENSE_TYPES,
  SCENARIO_FLAG_LABELS,
  SCENARIO_FLAG_OPTIONS,
  formatAmount,
  formatFileSize,
} from '../lib/reimbursementLabels'
import { createAttachmentSummary, saveSubmissionSummary } from '../lib/submissionSummary'
import type {
  AttachmentCategory,
  AttachmentSummary,
  ExpenseType,
  ScenarioFlag,
  SubmitFormData,
} from '../types'

type SelectedAttachment = {
  id: string
  file: File
  category: AttachmentCategory
}

type TextInputProps = {
  label: string
  value: string
  onChange: (value: string) => void
  required?: boolean
  type?: string
  placeholder?: string
}

type SelectInputProps = {
  label: string
  value: string
  options: string[]
  onChange: (value: string) => void
  required?: boolean
}

type CheckboxInputProps = {
  label: string
  checked: boolean
  onChange: (value: boolean) => void
  description?: string
}

const URGENCY_OPTIONS = ['普通', '紧急付款', '月结截止前', '董事会/审计抽查']
const CURRENCY_OPTIONS = ['CNY', 'USD', 'EUR', 'HKD', 'JPY']
const PAYMENT_METHOD_OPTIONS = ['个人垫付', '公司卡', '对公转账', '预付冲销', '第三方平台支付']
const INVOICE_TYPE_OPTIONS = ['增值税专用发票', '增值税普通发票', '电子发票', '定额发票', '境外票据', '无票说明']
const INVOICE_VALIDATION_OPTIONS = ['已验真', '待验真', '验真失败', '境外票据不可验真']
const TRANSPORTATION_OPTIONS = ['飞机', '高铁/火车', '出租车/网约车', '自驾', '混合交通']
const APPROVAL_STATUS_OPTIONS = ['已事前审批', '事后补批', '审批中', '无审批', '不适用']
const ENTERTAINMENT_PERIOD_OPTIONS = ['早餐', '午餐', '晚餐', '全天会议', '客户活动']

const PRESETS: {
  name: string
  description: string
  data: Partial<SubmitFormData>
}[] = [
  {
    name: '标准差旅',
    description: '行程、住宿、审批和发票齐全',
    data: {
      expense_type: '差旅报销',
      reimbursement_reason: '华东客户现场实施与项目验收',
      department: '企业服务部',
      project_name: 'CRM 二期交付',
      total_amount: '4280.50',
      tax_amount: '242.29',
      net_amount: '4038.21',
      invoice_type: '增值税普通发票',
      invoice_validation_status: '已验真',
      travel_from_city: '上海',
      travel_to_city: '杭州',
      travel_start_date: today(),
      travel_end_date: today(),
      transportation_type: '高铁/火车',
      hotel_nights: '2',
      traveler_count: '1',
      has_pre_trip_approval: true,
      approval_status: '已事前审批',
      scenario_flags: [],
    },
  },
  {
    name: '高风险差旅',
    description: '逾期、住宿超标、金额不一致',
    data: {
      expense_type: '差旅报销',
      reimbursement_reason: '跨月补提差旅住宿和交通费用',
      total_amount: '9860.00',
      tax_amount: '558.49',
      net_amount: '9301.51',
      travel_from_city: '北京',
      travel_to_city: '深圳',
      transportation_type: '飞机',
      hotel_nights: '4',
      traveler_count: '2',
      has_pre_trip_approval: false,
      approval_status: '事后补批',
      invoice_validation_status: '待验真',
      scenario_flags: ['late_submission', 'amount_mismatch', 'over_standard_hotel', 'no_pre_approval'],
    },
  },
  {
    name: '业务招待',
    description: '客户招待、多人参与、人均超标风险',
    data: {
      expense_type: '业务招待',
      reimbursement_reason: '重点客户续约商务沟通',
      customer_name: '上海某制造集团',
      total_amount: '3688.00',
      tax_amount: '208.75',
      net_amount: '3479.25',
      entertainment_target: '客户采购与财务负责人',
      entertainment_company: '上海某制造集团',
      participant_count: '8',
      per_capita_amount: '461.00',
      entertainment_period: '晚餐',
      business_purpose: '沟通年度续约范围、回款计划与上线排期',
      approval_status: '已事前审批',
      scenario_flags: ['over_standard_entertainment'],
    },
  },
  {
    name: '办公采购',
    description: '小额采购、合同/订单缺失',
    data: {
      expense_type: '办公采购',
      reimbursement_reason: '项目驻场临时办公用品采购',
      total_amount: '1280.00',
      tax_amount: '72.45',
      net_amount: '1207.55',
      payment_method: '个人垫付',
      invoice_type: '电子发票',
      invoice_validation_status: '已验真',
      scenario_flags: ['missing_attachment', 'split_reimbursement'],
    },
  },
]

function today(): string {
  return new Date().toISOString().slice(0, 10)
}

function createCaseId(): string {
  const compactDate = today().split('-').join('')
  const suffix = String(Math.floor(Math.random() * 9000) + 1000)
  return `EXP-${compactDate}-${suffix}`
}

function createDefaultForm(): SubmitFormData {
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
    invoice_seller_name: '上海差旅服务有限公司',
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
    notes: '请审核发票、付款凭证与事前审批是否一致。',
  }
}

function fieldClass(): string {
  return 'w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500'
}

function Section({ title, description, children }: { title: string; description: string; children: ReactNode }) {
  return (
    <section className="bg-white rounded-xl border border-gray-200 p-5 space-y-4">
      <div>
        <h2 className="text-base font-semibold text-gray-800">{title}</h2>
        <p className="text-xs text-gray-500 mt-1">{description}</p>
      </div>
      {children}
    </section>
  )
}

function TextInput({ label, value, onChange, required, type = 'text', placeholder }: TextInputProps) {
  return (
    <label className="block">
      <span className="block text-sm font-medium text-gray-700 mb-1">
        {label} {required && <span className="text-red-500">*</span>}
      </span>
      <input
        type={type}
        required={required}
        value={value}
        onChange={event => onChange(event.target.value)}
        placeholder={placeholder}
        className={fieldClass()}
      />
    </label>
  )
}

function SelectInput({ label, value, options, onChange, required }: SelectInputProps) {
  return (
    <label className="block">
      <span className="block text-sm font-medium text-gray-700 mb-1">
        {label} {required && <span className="text-red-500">*</span>}
      </span>
      <select
        required={required}
        value={value}
        onChange={event => onChange(event.target.value)}
        className={`${fieldClass()} bg-white`}
      >
        {options.map(option => (
          <option key={option} value={option}>{option}</option>
        ))}
      </select>
    </label>
  )
}

function CheckboxInput({ label, checked, onChange, description }: CheckboxInputProps) {
  return (
    <label className="flex items-start gap-2 rounded-lg border border-gray-200 p-3 hover:bg-gray-50">
      <input
        type="checkbox"
        checked={checked}
        onChange={event => onChange(event.target.checked)}
        className="mt-0.5 h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
      />
      <span>
        <span className="block text-sm font-medium text-gray-700">{label}</span>
        {description && <span className="block text-xs text-gray-500 mt-0.5">{description}</span>}
      </span>
    </label>
  )
}

function toAttachmentSummary(item: SelectedAttachment): AttachmentSummary {
  return {
    id: item.id,
    name: item.file.name,
    size: item.file.size,
    type: item.file.type || 'unknown',
    category: item.category,
    last_modified: item.file.lastModified,
  }
}

function defaultCategoryForFile(fileName: string): AttachmentCategory {
  const lower = fileName.toLowerCase()
  if (lower.includes('行程') || lower.includes('hotel') || lower.includes('travel')) return 'itinerary'
  if (lower.includes('审批') || lower.includes('approval')) return 'approval'
  if (lower.includes('合同') || lower.includes('order') || lower.includes('contract')) return 'contract'
  if (lower.includes('付款') || lower.includes('payment')) return 'payment_proof'
  if (lower.includes('发票') || lower.includes('invoice')) return 'invoice'
  return 'other'
}

export default function SubmitExpense() {
  const navigate = useNavigate()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [formData, setFormData] = useState<SubmitFormData>(() => createDefaultForm())
  const [attachments, setAttachments] = useState<SelectedAttachment[]>([])
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const attachmentSummaries = useMemo(
    () => attachments.map(toAttachmentSummary),
    [attachments],
  )

  const payloadPreview = useMemo<SubmitFormData>(
    () => ({ ...formData, attachment_summaries: attachmentSummaries }),
    [attachmentSummaries, formData],
  )

  function updateField<K extends keyof SubmitFormData>(field: K, value: SubmitFormData[K]) {
    setFormData(current => ({ ...current, [field]: value }))
    setNotice(null)
  }

  function applyPreset(data: Partial<SubmitFormData>) {
    setFormData(current => ({
      ...current,
      ...data,
      attachment_summaries: attachmentSummaries,
    }))
    setNotice('已套用场景模板，可继续调整字段后提交')
  }

  function resetForm() {
    setFormData(createDefaultForm())
    setAttachments([])
    setError(null)
    setNotice('已重置为默认报销样例')
  }

  function generateNewCaseId() {
    updateField('case_id', createCaseId())
    setNotice('已生成新的报销单号')
  }

  async function copyPayloadPreview() {
    const text = JSON.stringify(payloadPreview, null, 2)
    try {
      await navigator.clipboard.writeText(text)
      setError(null)
      setNotice('已复制当前 form_json，可用于 Postman/curl 联调')
    } catch {
      setNotice(null)
      setError('复制失败：当前浏览器不允许访问剪贴板，请直接从右侧预览框复制')
    }
  }

  function toggleScenario(flag: ScenarioFlag) {
    const next = formData.scenario_flags.includes(flag)
      ? formData.scenario_flags.filter(item => item !== flag)
      : [...formData.scenario_flags, flag]
    updateField('scenario_flags', next)
  }

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const selectedFiles = Array.from(event.target.files ?? [])
    setAttachments(current => [
      ...current,
      ...selectedFiles.map((file, index) => {
        const category = defaultCategoryForFile(file.name)
        const summary = createAttachmentSummary(file, category, current.length + index)
        return { id: summary.id, file, category }
      }),
    ])
    if (selectedFiles.length > 0) {
      setNotice(`已添加 ${selectedFiles.length} 个附件`)
    }
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  function updateAttachmentCategory(id: string, category: AttachmentCategory) {
    setAttachments(current => current.map(item => item.id === id ? { ...item, category } : item))
  }

  function removeAttachment(id: string) {
    setAttachments(current => current.filter(item => item.id !== id))
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setNotice(null)

    const submitPayload: SubmitFormData = {
      ...formData,
      attachment_summaries: attachmentSummaries,
    }

    setSubmitting(true)
    try {
      const response = await submitExpense(submitPayload, attachments.map(item => item.file))
      saveSubmissionSummary({
        request_id: response.request_id,
        submitted_at: new Date().toISOString(),
        form: submitPayload,
        attachments: attachmentSummaries,
      })
      navigate(`/tasks/${response.request_id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : '提交失败，请重试')
    } finally {
      setSubmitting(false)
    }
  }

  const isTravel = formData.expense_type === '差旅报销'
  const isEntertainment = formData.expense_type === '业务招待'

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">真实发票报销填报</h1>
          <p className="text-sm text-gray-500 mt-1">
            这是前端报销模板；后端只归档通用 `form_json` 与附件，不校验任何业务字段。
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={generateNewCaseId}
            className="rounded-md border border-gray-300 bg-white px-3 py-1.5 text-xs text-gray-700 hover:bg-gray-50"
          >
            生成新单号
          </button>
          <button
            type="button"
            onClick={() => void copyPayloadPreview()}
            className="rounded-md border border-blue-200 bg-blue-50 px-3 py-1.5 text-xs text-blue-700 hover:bg-blue-100"
          >
            复制 form_json
          </button>
          <button
            type="button"
            onClick={resetForm}
            className="rounded-md border border-gray-300 bg-white px-3 py-1.5 text-xs text-gray-700 hover:bg-gray-50"
          >
            重置样例
          </button>
        </div>
      </div>

      {notice && (
        <div className="rounded-md border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-700">
          {notice}
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
        <form onSubmit={handleSubmit} className="space-y-5">
          <Section title="场景模板" description="快速切换常见报销复杂情况，也可以继续手动调整字段。">
            <div className="grid gap-3 md:grid-cols-2">
              {PRESETS.map(preset => (
                <button
                  key={preset.name}
                  type="button"
                  onClick={() => applyPreset(preset.data)}
                  className="text-left rounded-lg border border-gray-200 p-3 hover:border-blue-300 hover:bg-blue-50 transition-colors"
                >
                  <span className="block text-sm font-medium text-gray-800">{preset.name}</span>
                  <span className="block text-xs text-gray-500 mt-1">{preset.description}</span>
                </button>
              ))}
            </div>
          </Section>

          <Section title="基础信息" description="确定报销单身份、申请主体、成本归属和费用类型。">
            <div className="grid gap-4 md:grid-cols-3">
              <TextInput label="报销单号" value={formData.case_id} onChange={value => updateField('case_id', value)} />
              <TextInput label="申请人" value={formData.applicant_name} onChange={value => updateField('applicant_name', value)} />
              <TextInput label="员工编号" value={formData.applicant_employee_id} onChange={value => updateField('applicant_employee_id', value)} />
              <TextInput label="部门" value={formData.department} onChange={value => updateField('department', value)} />
              <TextInput label="成本中心" value={formData.cost_center} onChange={value => updateField('cost_center', value)} />
              <TextInput label="报销主体" value={formData.legal_entity} onChange={value => updateField('legal_entity', value)} />
              <TextInput label="项目/订单" value={formData.project_name} onChange={value => updateField('project_name', value)} />
              <TextInput label="客户名称" value={formData.customer_name} onChange={value => updateField('customer_name', value)} />
              <TextInput label="申请日期" type="date" value={formData.submission_date} onChange={value => updateField('submission_date', value)} />
              <SelectInput label="费用类型" value={formData.expense_type} options={EXPENSE_TYPES} onChange={value => updateField('expense_type', value as ExpenseType)} />
              <SelectInput label="币种" value={formData.currency} options={CURRENCY_OPTIONS} onChange={value => updateField('currency', value)} />
              <SelectInput label="紧急程度" value={formData.urgency} options={URGENCY_OPTIONS} onChange={value => updateField('urgency', value)} />
            </div>
            <label className="block">
              <span className="block text-sm font-medium text-gray-700 mb-1">报销事由</span>
              <textarea
                value={formData.reimbursement_reason}
                onChange={event => updateField('reimbursement_reason', event.target.value)}
                rows={3}
                className={`${fieldClass()} resize-y`}
              />
            </label>
          </Section>

          <Section title="金额与预算" description="模拟总额、税额、支付方式、借款冲销和预算余额。">
            <div className="grid gap-4 md:grid-cols-3">
              <TextInput label="报销总额" type="number" value={formData.total_amount} onChange={value => updateField('total_amount', value)} />
              <TextInput label="税额" type="number" value={formData.tax_amount} onChange={value => updateField('tax_amount', value)} />
              <TextInput label="未税金额" type="number" value={formData.net_amount} onChange={value => updateField('net_amount', value)} />
              <SelectInput label="支付方式" value={formData.payment_method} options={PAYMENT_METHOD_OPTIONS} onChange={value => updateField('payment_method', value)} />
              <TextInput label="预算科目" value={formData.budget_subject} onChange={value => updateField('budget_subject', value)} />
              <TextInput label="预算余额" type="number" value={formData.budget_remaining} onChange={value => updateField('budget_remaining', value)} />
              <TextInput label="借款单号" value={formData.cash_advance_id} onChange={value => updateField('cash_advance_id', value)} placeholder="无借款可留空" />
              <TextInput label="借款/预付款金额" type="number" value={formData.cash_advance_amount} onChange={value => updateField('cash_advance_amount', value)} />
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              <CheckboxInput label="公司卡支付" checked={formData.paid_by_company_card} onChange={value => updateField('paid_by_company_card', value)} description="用于模拟公司卡与个人垫付混合场景" />
              <CheckboxInput label="存在借款或预付款冲销" checked={formData.has_cash_advance} onChange={value => updateField('has_cash_advance', value)} description="用于模拟预付冲销、借款未清等情况" />
            </div>
          </Section>

          <Section title="发票信息" description="模拟发票验真、抬头、销售方、税号和金额一致性。">
            <div className="grid gap-4 md:grid-cols-3">
              <SelectInput label="发票类型" value={formData.invoice_type} options={INVOICE_TYPE_OPTIONS} onChange={value => updateField('invoice_type', value)} />
              <TextInput label="发票代码" value={formData.invoice_code} onChange={value => updateField('invoice_code', value)} />
              <TextInput label="发票号码" value={formData.invoice_number} onChange={value => updateField('invoice_number', value)} />
              <TextInput label="开票日期" type="date" value={formData.invoice_issue_date} onChange={value => updateField('invoice_issue_date', value)} />
              <TextInput label="销售方名称" value={formData.invoice_seller_name} onChange={value => updateField('invoice_seller_name', value)} />
              <TextInput label="销售方税号" value={formData.invoice_seller_tax_id} onChange={value => updateField('invoice_seller_tax_id', value)} />
              <TextInput label="购买方抬头" value={formData.invoice_buyer_title} onChange={value => updateField('invoice_buyer_title', value)} />
              <SelectInput label="发票验真状态" value={formData.invoice_validation_status} options={INVOICE_VALIDATION_OPTIONS} onChange={value => updateField('invoice_validation_status', value)} />
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              <CheckboxInput label="发票抬头不符" checked={formData.invoice_title_mismatch} onChange={value => updateField('invoice_title_mismatch', value)} description="勾选后会同时作为异常线索进入表单" />
              <CheckboxInput label="发票金额与报销金额一致" checked={formData.invoice_amount_matches_claim} onChange={value => updateField('invoice_amount_matches_claim', value)} />
            </div>
          </Section>

          {isTravel && (
            <Section title="差旅行程" description="用于模拟差旅申请、交通、住宿、同行人员和事前审批。">
              <div className="grid gap-4 md:grid-cols-3">
                <TextInput label="出发城市" value={formData.travel_from_city} onChange={value => updateField('travel_from_city', value)} />
                <TextInput label="到达城市" value={formData.travel_to_city} onChange={value => updateField('travel_to_city', value)} />
                <SelectInput label="交通方式" value={formData.transportation_type} options={TRANSPORTATION_OPTIONS} onChange={value => updateField('transportation_type', value)} />
                <TextInput label="出差开始日" type="date" value={formData.travel_start_date} onChange={value => updateField('travel_start_date', value)} />
                <TextInput label="出差结束日" type="date" value={formData.travel_end_date} onChange={value => updateField('travel_end_date', value)} />
                <TextInput label="住宿晚数" type="number" value={formData.hotel_nights} onChange={value => updateField('hotel_nights', value)} />
                <TextInput label="同行人数" type="number" value={formData.traveler_count} onChange={value => updateField('traveler_count', value)} />
              </div>
              <CheckboxInput label="已完成事前差旅申请" checked={formData.has_pre_trip_approval} onChange={value => updateField('has_pre_trip_approval', value)} description="取消勾选可模拟无事前审批差旅" />
            </Section>
          )}

          {isEntertainment && (
            <Section title="业务招待" description="用于模拟客户招待对象、人员、人均金额和业务目的。">
              <div className="grid gap-4 md:grid-cols-3">
                <TextInput label="招待对象" value={formData.entertainment_target} onChange={value => updateField('entertainment_target', value)} />
                <TextInput label="客户公司" value={formData.entertainment_company} onChange={value => updateField('entertainment_company', value)} />
                <SelectInput label="招待时段" value={formData.entertainment_period} options={ENTERTAINMENT_PERIOD_OPTIONS} onChange={value => updateField('entertainment_period', value)} />
                <TextInput label="参与人数" type="number" value={formData.participant_count} onChange={value => updateField('participant_count', value)} />
                <TextInput label="人均金额" type="number" value={formData.per_capita_amount} onChange={value => updateField('per_capita_amount', value)} />
              </div>
              <label className="block">
                <span className="block text-sm font-medium text-gray-700 mb-1">业务目的</span>
                <textarea
                  value={formData.business_purpose}
                  onChange={event => updateField('business_purpose', event.target.value)}
                  rows={3}
                  className={`${fieldClass()} resize-y`}
                />
              </label>
            </Section>
          )}

          <Section title="审批与异常场景" description="显式勾选复杂情况，帮助模拟真实发票报销审核边界。">
            <div className="grid gap-4 md:grid-cols-3">
              <TextInput label="审批单号" value={formData.approval_id} onChange={value => updateField('approval_id', value)} />
              <TextInput label="审批人" value={formData.approver_name} onChange={value => updateField('approver_name', value)} />
              <SelectInput label="审批状态" value={formData.approval_status} options={APPROVAL_STATUS_OPTIONS} onChange={value => updateField('approval_status', value)} />
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              {SCENARIO_FLAG_OPTIONS.map(item => {
                const active = formData.scenario_flags.includes(item.value)
                return (
                  <button
                    key={item.value}
                    type="button"
                    onClick={() => toggleScenario(item.value)}
                    className={`rounded-lg border p-3 text-left transition-colors ${
                      active ? 'border-amber-300 bg-amber-50' : 'border-gray-200 hover:bg-gray-50'
                    }`}
                  >
                    <span className="block text-sm font-medium text-gray-800">
                      {active ? '✓ ' : ''}{item.label}
                    </span>
                    <span className="block text-xs text-gray-500 mt-1">{item.description}</span>
                  </button>
                )
              })}
            </div>
            <label className="block">
              <span className="block text-sm font-medium text-gray-700 mb-1">补充说明</span>
              <textarea
                value={formData.notes}
                onChange={event => updateField('notes', event.target.value)}
                rows={3}
                className={`${fieldClass()} resize-y`}
              />
            </label>
          </Section>

          <Section title="附件上传" description="附件可选；每个附件可选择业务分类，分类会进入本地摘要与 form_json。">
            <input
              ref={fileInputRef}
              type="file"
              multiple
              onChange={handleFileChange}
              className="w-full text-sm text-gray-500 file:mr-3 file:py-1.5 file:px-3 file:rounded-md file:border-0 file:text-sm file:font-medium file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100"
            />
            {attachments.length === 0 ? (
              <div className="rounded-lg border border-dashed border-gray-300 p-5 text-center text-sm text-gray-500">
                可上传发票、行程单、付款截图、审批单、合同/订单等材料；也可以只提交表单。
              </div>
            ) : (
              <div className="space-y-2">
                {attachments.map(item => (
                  <div key={item.id} className="grid gap-3 rounded-lg border border-gray-200 p-3 md:grid-cols-[minmax(0,1fr)_180px_auto] md:items-center">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-gray-800">{item.file.name}</p>
                      <p className="text-xs text-gray-500">{formatFileSize(item.file.size)} · {item.file.type || 'unknown'}</p>
                    </div>
                    <select
                      value={item.category}
                      onChange={event => updateAttachmentCategory(item.id, event.target.value as AttachmentCategory)}
                      className={`${fieldClass()} bg-white`}
                    >
                      {ATTACHMENT_CATEGORIES.map(category => (
                        <option key={category.value} value={category.value}>{category.label}</option>
                      ))}
                    </select>
                    <button
                      type="button"
                      onClick={() => removeAttachment(item.id)}
                      className="text-xs text-red-600 hover:underline"
                    >
                      删除
                    </button>
                  </div>
                ))}
              </div>
            )}
          </Section>

          {error && (
            <div className="p-3 bg-red-50 border border-red-200 rounded-md text-sm text-red-700">
              {error}
            </div>
          )}

          <div className="sticky bottom-4 z-10 rounded-xl border border-gray-200 bg-white/95 p-4 shadow-lg backdrop-blur">
            <button
              type="submit"
              disabled={submitting}
              className="w-full bg-blue-600 text-white py-2.5 rounded-md text-sm font-medium hover:bg-blue-700 disabled:opacity-60 transition-colors"
            >
              {submitting ? '提交中…' : '提交给 Claude 审核'}
            </button>
          </div>
        </form>

        <aside className="space-y-4 lg:sticky lg:top-20 lg:self-start">
          <div className="rounded-xl border border-gray-200 bg-white p-5">
            <h2 className="text-base font-semibold text-gray-800">提交摘要</h2>
            <dl className="mt-4 space-y-3 text-sm">
              <div className="flex justify-between gap-4">
                <dt className="text-gray-500">报销单号</dt>
                <dd className="font-mono text-gray-800 text-right">{formData.case_id}</dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-gray-500">申请人</dt>
                <dd className="text-gray-800">{formData.applicant_name}</dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-gray-500">费用类型</dt>
                <dd className="text-gray-800">{formData.expense_type}</dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-gray-500">报销金额</dt>
                <dd className="font-semibold text-gray-900">{formatAmount(formData.total_amount, formData.currency)}</dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-gray-500">附件数量</dt>
                <dd className="text-gray-800">{attachments.length} 个</dd>
              </div>
            </dl>
          </div>

          <div className="rounded-xl border border-gray-200 bg-white p-5">
            <h2 className="text-base font-semibold text-gray-800">异常标签</h2>
            {formData.scenario_flags.length === 0 ? (
              <p className="mt-3 text-sm text-gray-500">未标记异常场景</p>
            ) : (
              <div className="mt-3 flex flex-wrap gap-2">
                {formData.scenario_flags.map(flag => (
                  <span key={flag} className="rounded-full bg-amber-50 px-2.5 py-1 text-xs font-medium text-amber-700">
                    {SCENARIO_FLAG_LABELS[flag]}
                  </span>
                ))}
              </div>
            )}
          </div>

          <div className="rounded-xl border border-gray-200 bg-white p-5">
            <h2 className="text-base font-semibold text-gray-800">附件分类</h2>
            {attachmentSummaries.length === 0 ? (
              <p className="mt-3 text-sm text-gray-500">暂无附件</p>
            ) : (
              <ul className="mt-3 space-y-2">
                {attachmentSummaries.map(item => (
                  <li key={item.id} className="text-sm text-gray-700">
                    <span className="font-medium">{ATTACHMENT_CATEGORY_LABELS[item.category]}</span>
                    <span className="text-gray-400"> · </span>
                    <span className="break-all">{item.name}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="rounded-xl border border-gray-200 bg-white p-5">
            <h2 className="text-base font-semibold text-gray-800">form_json 预览</h2>
            <pre className="mt-3 max-h-[520px] overflow-auto rounded-lg bg-gray-950 p-3 text-xs text-gray-100">
              {JSON.stringify(payloadPreview, null, 2)}
            </pre>
          </div>
        </aside>
      </div>
    </div>
  )
}
