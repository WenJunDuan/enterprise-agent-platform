import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { submitExpense } from '../../api/client'
import Stepper from '../../components/Stepper'
import { saveSubmissionSummary } from '../../lib/submissionSummary'
import type { SubmitFormData } from '../../types'
import Step1BasicInfo from './Step1BasicInfo'
import Step2InvoiceDetail from './Step2InvoiceDetail'
import Step3Attachments, { type SelectedAttachment } from './Step3Attachments'
import Step4Preview from './Step4Preview'
import { createDefaultForm, toAttachmentSummaries } from './shared'

const STEPS = ['基础信息', '发票/行程', '附件上传', '预览提交']

export default function SubmitExpense() {
  const navigate = useNavigate()
  const [step, setStep] = useState(0)
  const [form, setForm] = useState<SubmitFormData>(() => createDefaultForm())
  const [attachments, setAttachments] = useState<SelectedAttachment[]>([])
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  function update<K extends keyof SubmitFormData>(field: K, value: SubmitFormData[K]) {
    setForm(current => ({ ...current, [field]: value }))
    setNotice(null)
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (step < STEPS.length - 1) {
      setStep(s => s + 1)
      return
    }
    // Final submit
    setError(null)
    setNotice(null)
    const attachmentSummaries = toAttachmentSummaries(attachments)
    const submitPayload: SubmitFormData = { ...form, attachment_summaries: attachmentSummaries }
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

  const isLastStep = step === STEPS.length - 1

  return (
    <div className="space-y-6 max-w-3xl mx-auto">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-semibold text-gray-900">新建报销申请</h1>
        <p className="text-sm text-gray-500 mt-1">
          分步填写报销信息，提交后由 Agent 自动审核
        </p>
      </div>

      {/* Stepper */}
      <Stepper steps={STEPS} currentStep={step} />

      {notice && (
        <div className="rounded-md border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-700">
          {notice}
        </div>
      )}

      {error && (
        <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Step content */}
      <form onSubmit={handleSubmit} className="rounded-xl border border-gray-200 bg-white p-6 space-y-6">
        {step === 0 && <Step1BasicInfo form={form} update={update} />}
        {step === 1 && <Step2InvoiceDetail form={form} update={update} />}
        {step === 2 && (
          <Step3Attachments
            attachments={attachments}
            setAttachments={setAttachments}
            setNotice={setNotice}
          />
        )}
        {step === 3 && (
          <Step4Preview
            form={form}
            attachments={attachments}
            submitting={submitting}
            update={update}
          />
        )}

        {/* Navigation buttons */}
        <div className="flex items-center justify-between pt-4 border-t border-gray-100">
          <button
            type="button"
            onClick={() => setStep(s => Math.max(0, s - 1))}
            disabled={step === 0}
            className="rounded-md border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            上一步
          </button>

          {!isLastStep && (
            <button
              type="submit"
              className="rounded-md bg-blue-600 px-5 py-2 text-sm font-medium text-white hover:bg-blue-700 transition-colors"
            >
              下一步
            </button>
          )}
        </div>
      </form>
    </div>
  )
}
