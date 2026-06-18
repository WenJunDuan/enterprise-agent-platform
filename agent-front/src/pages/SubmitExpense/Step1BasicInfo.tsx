import { EXPENSE_TYPES } from '../../lib/reimbursementLabels'
import type { ExpenseType, SubmitFormData } from '../../types'

const CURRENCY_OPTIONS = ['CNY', 'USD', 'EUR', 'HKD', 'JPY']

function fieldClass() {
  return 'w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500'
}

interface Props {
  form: SubmitFormData
  update: <K extends keyof SubmitFormData>(field: K, value: SubmitFormData[K]) => void
}

export default function Step1BasicInfo({ form, update }: Props) {
  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-base font-semibold text-gray-800">基础信息</h2>
        <p className="text-xs text-gray-500 mt-1">填写申请主体、成本归属与费用类型</p>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <label className="block">
          <span className="block text-sm font-medium text-gray-700 mb-1">申请人 <span className="text-red-500">*</span></span>
          <input
            type="text"
            required
            value={form.applicant_name}
            onChange={e => update('applicant_name', e.target.value)}
            className={fieldClass()}
          />
        </label>

        <label className="block">
          <span className="block text-sm font-medium text-gray-700 mb-1">部门</span>
          <input
            type="text"
            value={form.department}
            onChange={e => update('department', e.target.value)}
            className={fieldClass()}
          />
        </label>

        <label className="block">
          <span className="block text-sm font-medium text-gray-700 mb-1">费用类型 <span className="text-red-500">*</span></span>
          <select
            required
            value={form.expense_type}
            onChange={e => update('expense_type', e.target.value as ExpenseType)}
            className={`${fieldClass()} bg-white`}
          >
            {EXPENSE_TYPES.map(t => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        </label>

        <label className="block">
          <span className="block text-sm font-medium text-gray-700 mb-1">报销总额 <span className="text-red-500">*</span></span>
          <input
            type="number"
            required
            value={form.total_amount}
            onChange={e => update('total_amount', e.target.value)}
            className={fieldClass()}
          />
        </label>

        <label className="block">
          <span className="block text-sm font-medium text-gray-700 mb-1">币种</span>
          <select
            value={form.currency}
            onChange={e => update('currency', e.target.value)}
            className={`${fieldClass()} bg-white`}
          >
            {CURRENCY_OPTIONS.map(c => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
        </label>

        <label className="block">
          <span className="block text-sm font-medium text-gray-700 mb-1">申请日期</span>
          <input
            type="date"
            value={form.submission_date}
            onChange={e => update('submission_date', e.target.value)}
            className={fieldClass()}
          />
        </label>

        <label className="block">
          <span className="block text-sm font-medium text-gray-700 mb-1">成本中心</span>
          <input
            type="text"
            value={form.cost_center}
            onChange={e => update('cost_center', e.target.value)}
            className={fieldClass()}
          />
        </label>

        <label className="block">
          <span className="block text-sm font-medium text-gray-700 mb-1">报销主体</span>
          <input
            type="text"
            value={form.legal_entity}
            onChange={e => update('legal_entity', e.target.value)}
            className={fieldClass()}
          />
        </label>

        <label className="block">
          <span className="block text-sm font-medium text-gray-700 mb-1">项目/客户</span>
          <input
            type="text"
            value={form.project_name || form.customer_name}
            onChange={e => update('project_name', e.target.value)}
            className={fieldClass()}
          />
        </label>
      </div>

      <label className="block">
        <span className="block text-sm font-medium text-gray-700 mb-1">报销事由</span>
        <textarea
          value={form.reimbursement_reason}
          onChange={e => update('reimbursement_reason', e.target.value)}
          rows={3}
          className={`${fieldClass()} resize-y`}
        />
      </label>
    </div>
  )
}
