import { SCENARIO_FLAG_LABELS, SCENARIO_FLAG_OPTIONS, formatAmount } from '../../lib/reimbursementLabels'
import type { ScenarioFlag, SubmitFormData } from '../../types'
import type { SelectedAttachment } from './Step3Attachments'

interface Props {
  form: SubmitFormData
  attachments: SelectedAttachment[]
  submitting: boolean
  update: <K extends keyof SubmitFormData>(field: K, value: SubmitFormData[K]) => void
}

export default function Step4Preview({ form, attachments, submitting, update }: Props) {
  function toggleScenario(flag: ScenarioFlag) {
    const next = form.scenario_flags.includes(flag)
      ? form.scenario_flags.filter(item => item !== flag)
      : [...form.scenario_flags, flag]
    update('scenario_flags', next)
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-base font-semibold text-gray-800">预览与提交</h2>
        <p className="text-xs text-gray-500 mt-1">确认信息无误后，勾选异常场景并提交</p>
      </div>

      {/* Summary */}
      <div className="rounded-xl border border-gray-200 bg-gray-50 p-5 space-y-3">
        <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm sm:grid-cols-3">
          <div>
            <dt className="text-xs text-gray-400">报销单号</dt>
            <dd className="font-mono text-gray-800">{form.case_id}</dd>
          </div>
          <div>
            <dt className="text-xs text-gray-400">申请人</dt>
            <dd className="text-gray-800">{form.applicant_name}</dd>
          </div>
          <div>
            <dt className="text-xs text-gray-400">费用类型</dt>
            <dd className="text-gray-800">{form.expense_type}</dd>
          </div>
          <div>
            <dt className="text-xs text-gray-400">报销金额</dt>
            <dd className="font-semibold text-gray-900">{formatAmount(form.total_amount, form.currency)}</dd>
          </div>
          <div>
            <dt className="text-xs text-gray-400">附件数量</dt>
            <dd className="text-gray-800">{attachments.length} 个</dd>
          </div>
          <div>
            <dt className="text-xs text-gray-400">申请日期</dt>
            <dd className="text-gray-800">{form.submission_date}</dd>
          </div>
        </dl>
      </div>

      {/* Scenario flags */}
      <div>
        <p className="text-sm font-medium text-gray-700 mb-3">异常场景标记（可选）</p>
        <div className="grid gap-3 md:grid-cols-2">
          {SCENARIO_FLAG_OPTIONS.map(item => {
            const active = form.scenario_flags.includes(item.value)
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
        {form.scenario_flags.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2">
            {form.scenario_flags.map(flag => (
              <span key={flag} className="rounded-full bg-amber-50 px-2.5 py-1 text-xs font-medium text-amber-700">
                {SCENARIO_FLAG_LABELS[flag]}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Submit button */}
      <button
        type="submit"
        disabled={submitting}
        className="w-full bg-blue-600 text-white py-3 rounded-lg text-sm font-semibold hover:bg-blue-700 disabled:opacity-60 transition-colors"
      >
        {submitting ? '提交中…' : '提交给 Agent 审核'}
      </button>
    </div>
  )
}
