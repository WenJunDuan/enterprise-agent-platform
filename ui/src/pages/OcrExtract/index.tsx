import { useState } from 'react'
import type { FormFillResult, OcrExtractItem } from '../../types'
import { fillOcr } from '../../api/client'
import { FORM_SCHEMA, MOCK_EXTRACT_ITEMS, MOCK_FORM_FILL } from './mockData'
import { nextFileId, type OcrUploadFile, type RecognizePhase } from './shared'
import ResultPanel from './ResultPanel'
import UploadPanel from './UploadPanel'

/**
 * 文档识别 → 表单回填页面。左右分割：左栏上传 + 识别底稿，右栏回填结果。
 *
 * 「开始识别」走真实后端 `POST /ocr/fill`（识别 + 模型映射，需配模型网关）；
 * 「加载示例」用内置 mock 数据，无需后端 / key 即可预览 UI。
 */
export default function OcrExtract() {
  const [files, setFiles] = useState<OcrUploadFile[]>([])
  const [extractItems, setExtractItems] = useState<OcrExtractItem[]>([])
  const [formFill, setFormFill] = useState<FormFillResult | null>(null)
  const [phase, setPhase] = useState<RecognizePhase>('idle')
  const [error, setError] = useState<string | null>(null)

  function addFiles(picked: File[]) {
    setFiles(prev => [
      ...prev,
      ...picked.map(file => ({
        id: nextFileId(),
        name: file.name,
        size: file.size,
        status: 'pending' as const,
        file,
      })),
    ])
  }

  function removeFile(id: string) {
    setFiles(prev => prev.filter(file => file.id !== id))
  }

  async function recognize() {
    if (phase === 'recognizing') return
    const realFiles = files.map(f => f.file).filter((f): f is File => f != null)
    if (realFiles.length === 0) {
      setError('请先选择真实文件（“加载示例”仅用于预览，不会真正识别）')
      setPhase('error')
      return
    }
    setPhase('recognizing')
    setError(null)
    setExtractItems([])
    setFormFill(null)
    setFiles(prev => prev.map(f => ({ ...f, status: 'recognizing' as const })))
    try {
      const resp = await fillOcr(realFiles, FORM_SCHEMA)
      setExtractItems(resp.results)
      setFormFill(resp.fill)
      setFiles(prev => prev.map(f => ({ ...f, status: 'done' as const })))
      setPhase('done')
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      setFiles(prev => prev.map(f => ({ ...f, status: 'error' as const })))
      setPhase('error')
    }
  }

  function loadSample() {
    setError(null)
    setFiles(
      MOCK_EXTRACT_ITEMS.map(item => ({
        id: nextFileId(),
        name: item.path.split('/').pop() ?? item.path,
        size: 0,
        status: 'done' as const,
        route: item.route,
      })),
    )
    setExtractItems(MOCK_EXTRACT_ITEMS)
    setFormFill(MOCK_FORM_FILL)
    setPhase('done')
  }

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-lg font-semibold text-gray-800">文档识别 · 表单回填</h1>
        <p className="mt-1 text-sm text-gray-500">
          上传案件文档，自动识别并回填到目标表单，含合同付款节点抽取。
          <span className="ml-1 rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-500">
            「开始识别」调用后端，「加载示例」为演示数据
          </span>
        </p>
      </header>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* 左右分割：左 40% 上传+底稿 / 右 60% 回填结果；窄屏自动堆叠 */}
      <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-[2fr_3fr]">
        <UploadPanel
          files={files}
          extractItems={extractItems}
          phase={phase}
          onAddFiles={addFiles}
          onRemoveFile={removeFile}
          onRecognize={recognize}
          onLoadSample={loadSample}
        />
        <ResultPanel formFill={formFill} phase={phase} />
      </div>
    </div>
  )
}
