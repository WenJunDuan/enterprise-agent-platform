import { useMemo, useState, type FormEvent } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { Check, FileUp, Send, X } from 'lucide-react'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  CardTitle,
  CardDescription,
} from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { SelectDropdown } from '@/components/select-dropdown'
import { submitExpense } from './api'
import {
  ATTACHMENT_CATEGORIES,
  EXPENSE_TYPES,
  SCENARIO_FLAG_OPTIONS,
  formatFileSize,
} from './lib/reimbursement-labels'
import { saveSubmissionSummary } from './lib/submission-summary'
import { createDefaultForm, toAttachmentSummaries } from './submit/shared'
import type { SelectedAttachment } from './submit/types'
import type { ScenarioFlag, SubmitFormData } from './types'

const steps = [
  { id: 'basic', label: '基础信息' },
  { id: 'invoice', label: '发票与场景' },
  { id: 'attachments', label: '附件' },
  { id: 'preview', label: '预览提交' },
] as const

type StepId = (typeof steps)[number]['id']
type TextField = keyof SubmitFormData

const basicFields: { key: TextField; label: string; placeholder?: string }[] = [
  { key: 'case_id', label: '报销单号' },
  { key: 'applicant_name', label: '申请人' },
  { key: 'applicant_employee_id', label: '员工编号' },
  { key: 'department', label: '部门' },
  { key: 'cost_center', label: '成本中心' },
  { key: 'legal_entity', label: '报销主体' },
  { key: 'project_name', label: '项目名称' },
  { key: 'customer_name', label: '客户名称' },
  { key: 'submission_date', label: '提交日期' },
  { key: 'total_amount', label: '总金额' },
  { key: 'currency', label: '币种' },
  { key: 'urgency', label: '紧急程度' },
]

const invoiceFields: { key: TextField; label: string }[] = [
  { key: 'tax_amount', label: '税额' },
  { key: 'net_amount', label: '不含税金额' },
  { key: 'payment_method', label: '付款方式' },
  { key: 'budget_subject', label: '预算科目' },
  { key: 'budget_remaining', label: '预算余额' },
  { key: 'invoice_type', label: '发票类型' },
  { key: 'invoice_code', label: '发票代码' },
  { key: 'invoice_number', label: '发票号码' },
  { key: 'invoice_issue_date', label: '开票日期' },
  { key: 'invoice_seller_name', label: '销售方名称' },
  { key: 'invoice_seller_tax_id', label: '销售方税号' },
  { key: 'invoice_buyer_title', label: '购买方抬头' },
  { key: 'invoice_validation_status', label: '验真状态' },
  { key: 'travel_from_city', label: '出发城市' },
  { key: 'travel_to_city', label: '到达城市' },
  { key: 'travel_start_date', label: '出差开始' },
  { key: 'travel_end_date', label: '出差结束' },
  { key: 'transportation_type', label: '交通方式' },
  { key: 'hotel_nights', label: '住宿晚数' },
  { key: 'traveler_count', label: '出行人数' },
  { key: 'approval_id', label: '审批单号' },
  { key: 'approver_name', label: '审批人' },
  { key: 'approval_status', label: '审批状态' },
]

function InputField({
  label,
  value,
  onChange,
}: {
  label: string
  value: string
  onChange: (value: string) => void
}) {
  return (
    <label className='grid gap-2'>
      <span className='text-sm font-medium'>{label}</span>
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className='h-9 rounded-md border bg-background px-3 text-sm outline-none transition-colors focus:border-ring focus:ring-[3px] focus:ring-ring/20'
      />
    </label>
  )
}

/**
 * C①: Clickable top stepper — replaces the old non-clickable Stepper + hidden Tabs in footer.
 * Clicking a step directly navigates to that step.
 */
function ClickableStepper({
  current,
  onStepClick,
}: {
  current: StepId
  onStepClick: (stepId: StepId) => void
}) {
  const currentIndex = steps.findIndex((step) => step.id === current)
  return (
    <div className='grid gap-2 md:grid-cols-4'>
      {steps.map((step, index) => {
        const active = step.id === current
        const done = index < currentIndex
        return (
          <button
            key={step.id}
            type='button'
            aria-current={active ? 'step' : undefined}
            className={`rounded-md border px-3 py-2 text-left text-sm transition-colors ${
              active
                ? 'border-primary bg-primary/5 text-primary'
                : done
                  ? 'cursor-pointer bg-muted/60 hover:bg-muted'
                  : 'cursor-pointer text-muted-foreground hover:bg-muted/40'
            }`}
            onClick={() => onStepClick(step.id)}
          >
            <div className='flex items-center gap-2'>
              <span className='inline-flex size-5 items-center justify-center rounded-full border text-xs'>
                {done ? <Check className='size-3' /> : index + 1}
              </span>
              {step.label}
            </div>
          </button>
        )
      })}
    </div>
  )
}

export function AuditSubmitPage() {
  const navigate = useNavigate()
  const [step, setStep] = useState<StepId>('basic')
  const [form, setForm] = useState<SubmitFormData>(() => createDefaultForm())
  const [attachments, setAttachments] = useState<SelectedAttachment[]>([])
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const stepIndex = steps.findIndex((item) => item.id === step)
  const attachmentSummaries = useMemo(() => toAttachmentSummaries(attachments), [attachments])

  function updateText(field: keyof SubmitFormData, value: string) {
    setForm((current) => ({ ...current, [field]: value }) as SubmitFormData)
  }

  function updateBoolean(field: keyof SubmitFormData, value: boolean) {
    setForm((current) => ({ ...current, [field]: value }) as SubmitFormData)
  }

  function toggleScenario(flag: ScenarioFlag) {
    setForm((current) => {
      const next = current.scenario_flags.includes(flag)
        ? current.scenario_flags.filter((item) => item !== flag)
        : [...current.scenario_flags, flag]
      return { ...current, scenario_flags: next }
    })
  }

  function addFiles(files: FileList | null) {
    if (!files) return
    const nextFiles = Array.from(files).map((file, index) => ({
      id: `${file.name}-${file.size}-${file.lastModified}-${index}-${Date.now()}`,
      file,
      category: 'invoice' as const,
    }))
    setAttachments((current) => [...current, ...nextFiles])
  }

  function updateAttachmentCategory(id: string, category: SelectedAttachment['category']) {
    setAttachments((current) =>
      current.map((item) => (item.id === id ? { ...item, category } : item))
    )
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (stepIndex < steps.length - 1) {
      setStep(steps[stepIndex + 1].id)
      return
    }

    setSubmitting(true)
    setError(null)
    try {
      const payload = { ...form, attachment_summaries: attachmentSummaries }
      const response = await submitExpense(payload, attachments.map((item) => item.file))
      saveSubmissionSummary({
        request_id: response.request_id,
        submitted_at: new Date().toISOString(),
        form: payload,
        attachments: attachmentSummaries,
      })
      await navigate({
        to: '/audit/tasks/$taskId',
        params: { taskId: response.request_id },
      })
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : '提交失败')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <>
      <Header fixed />
      <Main className='space-y-5'>
        <div>
          <h1 className='text-2xl font-semibold tracking-tight'>新建报销审核</h1>
          <p className='text-sm text-muted-foreground'>
            按步骤整理报销信息与附件，提交后进入审核流程。
          </p>
        </div>

        {/* C①: 顶部步骤条可点击跳步，无左侧冗余步骤列表 */}
        <ClickableStepper current={step} onStepClick={setStep} />

        {error ? (
          <Alert variant='destructive'>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        ) : null}

        <form onSubmit={handleSubmit}>
          <Card>
            <CardHeader>
              <CardTitle>{steps[stepIndex].label}</CardTitle>
              <CardDescription>按页面提示补充必要信息。</CardDescription>
            </CardHeader>
            <CardContent className='space-y-5'>
              {step === 'basic' ? (
                <>
                  <div className='grid gap-4 md:grid-cols-3'>
                    {basicFields.map((field) => (
                      <InputField
                        key={field.key}
                        label={field.label}
                        value={String(form[field.key] ?? '')}
                        onChange={(value) => updateText(field.key, value)}
                      />
                    ))}
                    <label className='grid gap-2'>
                      <span className='text-sm font-medium'>费用类型</span>
                      <SelectDropdown
                        value={form.expense_type}
                        onValueChange={(value) => updateText('expense_type', value)}
                        items={EXPENSE_TYPES.map((type) => ({
                          label: type,
                          value: type,
                        }))}
                        isControlled
                        withFormControl={false}
                        className='h-9'
                      />
                    </label>
                  </div>
                  <label className='grid gap-2'>
                    <span className='text-sm font-medium'>报销事由</span>
                    <Textarea
                      value={form.reimbursement_reason}
                      onChange={(event) => updateText('reimbursement_reason', event.target.value)}
                    />
                  </label>
                </>
              ) : null}

              {step === 'invoice' ? (
                <>
                  <div className='grid gap-4 md:grid-cols-3'>
                    {invoiceFields.map((field) => (
                      <InputField
                        key={field.key}
                        label={field.label}
                        value={String(form[field.key] ?? '')}
                        onChange={(value) => updateText(field.key, value)}
                      />
                    ))}
                  </div>
                  <div className='grid gap-3 rounded-md border p-4 md:grid-cols-3'>
                    <Label className='flex items-center gap-2'>
                      <Checkbox
                        checked={form.has_pre_trip_approval}
                        onCheckedChange={(checked) => updateBoolean('has_pre_trip_approval', checked === true)}
                      />
                      已事前审批
                    </Label>
                    <Label className='flex items-center gap-2'>
                      <Checkbox
                        checked={form.invoice_title_mismatch}
                        onCheckedChange={(checked) => updateBoolean('invoice_title_mismatch', checked === true)}
                      />
                      发票抬头不符
                    </Label>
                    <Label className='flex items-center gap-2'>
                      <Checkbox
                        checked={form.invoice_amount_matches_claim}
                        onCheckedChange={(checked) => updateBoolean('invoice_amount_matches_claim', checked === true)}
                      />
                      发票金额匹配
                    </Label>
                  </div>
                  <div className='grid gap-3 md:grid-cols-2'>
                    {SCENARIO_FLAG_OPTIONS.map((option) => (
                      <Label key={option.value} className='flex items-start gap-3 rounded-md border p-3'>
                        <Checkbox
                          checked={form.scenario_flags.includes(option.value)}
                          onCheckedChange={() => toggleScenario(option.value)}
                        />
                        <span>
                          <span className='block text-sm font-medium'>{option.label}</span>
                          <span className='text-xs text-muted-foreground'>{option.description}</span>
                        </span>
                      </Label>
                    ))}
                  </div>
                </>
              ) : null}

              {step === 'attachments' ? (
                <div className='space-y-4'>
                  <label className='flex min-h-36 cursor-pointer flex-col items-center justify-center gap-3 rounded-lg border border-dashed bg-muted/20 p-6 text-center'>
                    <FileUp className='size-8 text-muted-foreground' />
                    <span className='font-medium'>选择或拖入附件</span>
                    <span className='text-sm text-muted-foreground'>
                      支持发票、审批单、合同、行程单等材料。
                    </span>
                    <input multiple type='file' className='hidden' onChange={(event) => addFiles(event.target.files)} />
                  </label>
                  <div className='space-y-2'>
                    {attachments.length === 0 ? (
                      <div className='rounded-md border p-4 text-sm text-muted-foreground'>暂无附件。</div>
                    ) : (
                      attachments.map((item) => (
                        <div key={item.id} className='flex flex-col gap-3 rounded-md border p-3 md:flex-row md:items-center md:justify-between'>
                          <div>
                            <div className='font-medium'>{item.file.name}</div>
                            <div className='text-xs text-muted-foreground'>{formatFileSize(item.file.size)}</div>
                          </div>
                          <div className='flex items-center gap-2'>
                            <SelectDropdown
                              value={item.category}
                              onValueChange={(value) =>
                                updateAttachmentCategory(
                                  item.id,
                                  value as SelectedAttachment['category']
                                )
                              }
                              items={ATTACHMENT_CATEGORIES}
                              isControlled
                              withFormControl={false}
                              className='h-9 w-32'
                            />
                            <Button
                              type='button'
                              variant='ghost'
                              size='icon'
                              aria-label='移除附件'
                              onClick={() =>
                                setAttachments((current) => current.filter((entry) => entry.id !== item.id))
                              }
                            >
                              <X className='size-4' />
                            </Button>
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              ) : null}

              {step === 'preview' ? (
                <div className='space-y-3 rounded-md border p-4'>
                  <div>
                    <div className='text-sm text-muted-foreground'>报销单</div>
                    <div className='text-lg font-semibold'>{form.case_id}</div>
                  </div>
                  <div className='grid gap-3 text-sm md:grid-cols-2'>
                    <div>申请人：{form.applicant_name}</div>
                    <div>部门：{form.department}</div>
                    <div>费用类型：{form.expense_type}</div>
                    <div>金额：{form.currency} {form.total_amount}</div>
                    <div>附件：{attachments.length} 个</div>
                    <div>异常标签：{form.scenario_flags.length} 个</div>
                  </div>
                </div>
              ) : null}
            </CardContent>
            <CardFooter className='justify-between border-t pt-5'>
              <Button
                type='button'
                variant='outline'
                disabled={stepIndex === 0 || submitting}
                onClick={() => setStep(steps[stepIndex - 1].id)}
              >
                上一步
              </Button>
              <Button disabled={submitting} type='submit'>
                {stepIndex === steps.length - 1 ? (
                  <>
                    <Send className='size-4' />
                    {submitting ? '提交中' : '提交审核'}
                  </>
                ) : (
                  '下一步'
                )}
              </Button>
            </CardFooter>
          </Card>
        </form>
      </Main>
    </>
  )
}
