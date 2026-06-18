import { useRef, type ChangeEvent } from 'react'
import { ATTACHMENT_CATEGORIES, ATTACHMENT_CATEGORY_LABELS, formatFileSize } from '../../lib/reimbursementLabels'
import { createAttachmentSummary } from '../../lib/submissionSummary'
import type { AttachmentCategory } from '../../types'

export type SelectedAttachment = {
  id: string
  file: File
  category: AttachmentCategory
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

function fieldClass() {
  return 'w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500'
}

interface Props {
  attachments: SelectedAttachment[]
  setAttachments: (updater: (prev: SelectedAttachment[]) => SelectedAttachment[]) => void
  setNotice: (msg: string) => void
}

export default function Step3Attachments({ attachments, setAttachments, setNotice }: Props) {
  const fileInputRef = useRef<HTMLInputElement>(null)

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

  function updateCategory(id: string, category: AttachmentCategory) {
    setAttachments(current => current.map(item => item.id === id ? { ...item, category } : item))
  }

  function remove(id: string) {
    setAttachments(current => current.filter(item => item.id !== id))
  }

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-base font-semibold text-gray-800">附件上传</h2>
        <p className="text-xs text-gray-500 mt-1">可上传发票、行程单、付款凭证、审批单等材料；也可只提交表单</p>
      </div>

      <input
        ref={fileInputRef}
        type="file"
        multiple
        onChange={handleFileChange}
        className="w-full text-sm text-gray-500 file:mr-3 file:py-1.5 file:px-3 file:rounded-md file:border-0 file:text-sm file:font-medium file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100"
      />

      {attachments.length === 0 ? (
        <div className="rounded-lg border border-dashed border-gray-300 p-8 text-center text-sm text-gray-500">
          暂无附件，可上传发票、行程单、付款截图、审批单、合同/订单等材料
        </div>
      ) : (
        <div className="space-y-2">
          {attachments.map(item => (
            <div
              key={item.id}
              className="grid gap-3 rounded-lg border border-gray-200 p-3 md:grid-cols-[minmax(0,1fr)_180px_auto] md:items-center"
            >
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-gray-800">{item.file.name}</p>
                <p className="text-xs text-gray-500">
                  {formatFileSize(item.file.size)} · {item.file.type || 'unknown'}
                </p>
              </div>
              <select
                value={item.category}
                onChange={e => updateCategory(item.id, e.target.value as AttachmentCategory)}
                className={`${fieldClass()} bg-white`}
              >
                {ATTACHMENT_CATEGORIES.map(cat => (
                  <option key={cat.value} value={cat.value}>{cat.label}</option>
                ))}
              </select>
              <button
                type="button"
                onClick={() => remove(item.id)}
                className="text-xs text-red-600 hover:underline"
              >
                删除
              </button>
            </div>
          ))}
        </div>
      )}

      {attachments.length > 0 && (
        <div className="rounded-lg border border-gray-100 bg-gray-50 p-3">
          <p className="text-xs font-medium text-gray-500 mb-2">附件分类汇总</p>
          <ul className="space-y-1">
            {attachments.map(item => (
              <li key={item.id} className="text-xs text-gray-600">
                <span className="font-medium">{ATTACHMENT_CATEGORY_LABELS[item.category]}</span>
                <span className="text-gray-400"> · </span>
                <span className="break-all">{item.file.name}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
