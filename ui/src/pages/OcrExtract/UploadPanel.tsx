import { useRef, type ChangeEvent } from 'react'
import { formatFileSize } from '../../lib/reimbursementLabels'
import type { OcrExtractItem } from '../../types'
import { ROUTE_STYLE, type OcrFileStatus, type OcrUploadFile, type RecognizePhase } from './shared'

const FILE_STATUS: Record<OcrFileStatus, { label: string; cls: string }> = {
  pending: { label: '待识别', cls: 'bg-gray-100 text-gray-600' },
  recognizing: { label: '识别中', cls: 'bg-blue-50 text-blue-700' },
  done: { label: '已识别', cls: 'bg-green-50 text-green-700' },
  error: { label: '失败', cls: 'bg-red-50 text-red-700' },
}

interface Props {
  files: OcrUploadFile[]
  extractItems: OcrExtractItem[]
  phase: RecognizePhase
  onAddFiles: (files: File[]) => void
  onRemoveFile: (id: string) => void
  onRecognize: () => void
  onLoadSample: () => void
}

/** 单文件识别底稿卡片：文件名 + route 标签 + 底稿正文 / 表格 / 占位。 */
function ExtractItemCard({ item }: { item: OcrExtractItem }) {
  const name = item.path.split('/').pop() ?? item.path
  const routeStyle = item.route ? ROUTE_STYLE[item.route] : null
  return (
    <div className="space-y-2 rounded-lg border border-gray-200 p-3">
      <div className="flex items-center justify-between gap-2">
        <p className="truncate text-sm font-medium text-gray-800" title={name}>
          {name}
        </p>
        {routeStyle && (
          <span className={`shrink-0 rounded px-2 py-0.5 text-xs font-medium ${routeStyle.bg} ${routeStyle.text}`}>
            {routeStyle.label}
          </span>
        )}
      </div>
      {item.error ? (
        <p className="text-xs text-red-600">识别失败：{item.error}</p>
      ) : (
        <>
          {item.note && (
            <p className="rounded border border-dashed border-gray-300 bg-gray-50 px-3 py-2 text-xs text-gray-500">
              {item.note}
            </p>
          )}
          {item.pages?.map((page, i) => (
            <pre
              key={`page-${i}`}
              className="whitespace-pre-wrap break-words font-sans text-xs leading-relaxed text-gray-600"
            >
              {page.markdown ?? ''}
            </pre>
          ))}
          {item.blocks?.map((block, i) => (
            <pre
              key={i}
              className="whitespace-pre-wrap break-words font-sans text-xs leading-relaxed text-gray-600"
            >
              {block}
            </pre>
          ))}
          {item.tables?.map((table, i) => (
            <div key={i} className="overflow-x-auto">
              {table.name && <p className="mb-1 text-xs font-medium text-gray-500">{table.name}</p>}
              <table className="w-full border-collapse text-xs">
                <tbody>
                  {table.rows.map((row, ri) => (
                    <tr key={ri} className={ri === 0 ? 'bg-gray-50 font-medium text-gray-700' : 'text-gray-600'}>
                      {row.map((cell, ci) => (
                        <td key={ci} className="border border-gray-200 px-2 py-1">
                          {cell}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
        </>
      )}
    </div>
  )
}

/** OCR 页面左栏：① 文档上传与文件列表；② 确定性识别底稿。 */
export default function UploadPanel({
  files,
  extractItems,
  phase,
  onAddFiles,
  onRemoveFile,
  onRecognize,
  onLoadSample,
}: Props) {
  const inputRef = useRef<HTMLInputElement>(null)

  function handlePick(event: ChangeEvent<HTMLInputElement>) {
    const picked = Array.from(event.target.files ?? [])
    if (picked.length) onAddFiles(picked)
    if (inputRef.current) inputRef.current.value = ''
  }

  const recognizing = phase === 'recognizing'

  return (
    <section className="space-y-5 rounded-xl border border-gray-200 bg-white p-5">
      {/* ① 上传区 */}
      <div className="space-y-3">
        <div>
          <h2 className="text-base font-semibold text-gray-800">上传文档</h2>
          <p className="mt-1 text-xs text-gray-500">支持 PDF / 图片 / Word / Excel / 文本；可一次上传多份</p>
        </div>
        <label className="sr-only" htmlFor="ocr-file-input">
          选择待识别文档
        </label>
        <input
          id="ocr-file-input"
          ref={inputRef}
          type="file"
          multiple
          onChange={handlePick}
          className="w-full text-sm text-gray-500 file:mr-3 file:rounded-md file:border-0 file:bg-blue-50 file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-blue-700 hover:file:bg-blue-100"
        />

        {files.length === 0 ? (
          <div className="rounded-lg border border-dashed border-gray-300 p-6 text-center text-sm text-gray-500">
            还没有文档，选择文件后点击「开始识别」，或直接「加载示例」查看效果
          </div>
        ) : (
          <ul className="space-y-2">
            {files.map(file => {
              const status = FILE_STATUS[file.status]
              return (
                <li
                  key={file.id}
                  className="flex items-center justify-between gap-3 rounded-lg border border-gray-200 p-2.5"
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-gray-800" title={file.name}>
                      {file.name}
                    </p>
                    {file.size > 0 && <p className="text-xs text-gray-500">{formatFileSize(file.size)}</p>}
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <span className={`rounded px-2 py-0.5 text-xs font-medium ${status.cls}`}>{status.label}</span>
                    <button
                      type="button"
                      onClick={() => onRemoveFile(file.id)}
                      className="text-xs text-red-600 hover:underline"
                      aria-label={`移除 ${file.name}`}
                    >
                      删除
                    </button>
                  </div>
                </li>
              )
            })}
          </ul>
        )}

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onRecognize}
            disabled={recognizing || files.length === 0}
            className="inline-flex items-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {recognizing && (
              <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
              </svg>
            )}
            {recognizing ? '识别中…' : '开始识别'}
          </button>
          <button
            type="button"
            onClick={onLoadSample}
            disabled={recognizing}
            className="rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-50 disabled:opacity-50"
          >
            加载示例
          </button>
        </div>
      </div>

      {/* ② 识别底稿 */}
      <div className="space-y-3 border-t border-gray-100 pt-4">
        <h3 className="text-sm font-semibold text-gray-700">识别底稿</h3>
        {recognizing ? (
          <div className="space-y-2">
            <div className="h-20 animate-pulse rounded-lg bg-gray-100" />
            <div className="h-16 animate-pulse rounded-lg bg-gray-100" />
          </div>
        ) : extractItems.length === 0 ? (
          <p className="rounded-lg border border-dashed border-gray-300 p-5 text-center text-xs text-gray-400">
            确定性识别产物（原生直读 / OCR）将显示在这里
          </p>
        ) : (
          <div className="space-y-3">
            {extractItems.map(item => (
              <ExtractItemCard key={item.path} item={item} />
            ))}
          </div>
        )}
      </div>
    </section>
  )
}
