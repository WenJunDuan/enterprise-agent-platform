import { useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { submitExpense } from '../api/client'

const EXPENSE_TYPES = ['差旅', '招待', '办公', '其他']

export default function SubmitExpense() {
  const navigate = useNavigate()
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [caseId, setCaseId] = useState('')
  const [applicantName, setApplicantName] = useState('')
  const [expenseType, setExpenseType] = useState(EXPENSE_TYPES[0])
  const [files, setFiles] = useState<File[]>([])
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    setFiles(Array.from(e.target.files ?? []))
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)

    if (files.length === 0) {
      setError('请至少上传一个文件')
      return
    }

    setSubmitting(true)
    try {
      const res = await submitExpense(
        { case_id: caseId, applicant_name: applicantName, expense_type: expenseType },
        files,
      )
      navigate(`/tasks/${res.request_id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : '提交失败，请重试')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="max-w-xl">
      <h1 className="text-xl font-semibold text-gray-800 mb-6">新建报销申请</h1>

      <form onSubmit={handleSubmit} className="bg-white rounded-lg border border-gray-200 p-6 space-y-5">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            案例编号 <span className="text-red-500">*</span>
          </label>
          <input
            type="text"
            required
            value={caseId}
            onChange={e => setCaseId(e.target.value)}
            placeholder="请输入案例编号"
            className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            申请人姓名 <span className="text-red-500">*</span>
          </label>
          <input
            type="text"
            required
            value={applicantName}
            onChange={e => setApplicantName(e.target.value)}
            placeholder="请输入申请人姓名"
            className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            费用类型 <span className="text-red-500">*</span>
          </label>
          <select
            value={expenseType}
            onChange={e => setExpenseType(e.target.value)}
            className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            {EXPENSE_TYPES.map(t => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            附件 <span className="text-red-500">*</span>
          </label>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept=".pdf,.png,.jpg,.jpeg"
            onChange={handleFileChange}
            className="w-full text-sm text-gray-500 file:mr-3 file:py-1.5 file:px-3 file:rounded-md file:border-0 file:text-sm file:font-medium file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100"
          />
          {files.length > 0 && (
            <ul className="mt-2 space-y-1">
              {files.map(f => (
                <li key={f.name} className="text-xs text-gray-500 flex items-center gap-1">
                  <span className="text-green-500">✓</span> {f.name}
                </li>
              ))}
            </ul>
          )}
        </div>

        {error && (
          <div className="p-3 bg-red-50 border border-red-200 rounded-md text-sm text-red-700">
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={submitting}
          className="w-full bg-blue-600 text-white py-2 rounded-md text-sm font-medium hover:bg-blue-700 disabled:opacity-60 transition-colors"
        >
          {submitting ? '提交中…' : '提交申请'}
        </button>
      </form>
    </div>
  )
}
