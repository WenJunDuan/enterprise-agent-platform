import type { OcrRoute } from '../../audit/types'

// OCR 页面前端 UI 状态类型与展示工具（非后端契约）。

export type OcrFileStatus = 'pending' | 'recognizing' | 'done' | 'error'

export interface OcrUploadFile {
  id: string
  name: string
  size: number
  status: OcrFileStatus
  route?: OcrRoute
  /** 真实上传的文件对象；「加载示例」的演示项无此字段。 */
  file?: File
}

export type ConfidenceLevel = 'high' | 'medium' | 'low'

/**
 * 置信度分三级，用于右栏字段着色 + 文案。
 *
 * 阈值与 RiskScoreBar 的风险分级同源思路（高/中/低三档）。
 *
 * @param confidence - 0~1 的置信度。
 * @returns 分级标签。
 */
export function confidenceLevel(confidence: number): ConfidenceLevel {
  if (confidence >= 0.85) return 'high'
  if (confidence >= 0.6) return 'medium'
  return 'low'
}

// 置信度配色 + 文字标签：颜色之外保留文字，避免靠颜色单独传达信息（a11y）。
export const CONFIDENCE_STYLE: Record<
  ConfidenceLevel,
  { bg: string; text: string; label: string }
> = {
  high: { bg: 'bg-green-50', text: 'text-green-700', label: '高' },
  medium: { bg: 'bg-amber-50', text: 'text-amber-700', label: '中' },
  low: { bg: 'bg-red-50', text: 'text-red-700', label: '低' },
}

// 识别底稿 route 的中文标签 + 配色。
export const ROUTE_STYLE: Record<
  OcrRoute,
  { label: string; bg: string; text: string }
> = {
  native: { label: '原生直读', bg: 'bg-blue-50', text: 'text-blue-700' },
  ocr: { label: 'OCR 识别', bg: 'bg-purple-50', text: 'text-purple-700' },
  manual: { label: '转人工', bg: 'bg-gray-100', text: 'text-gray-600' },
}

let idCounter = 0

/** 生成稳定的本地文件行 id（仅前端列表渲染用）。 */
export function nextFileId(): string {
  idCounter += 1
  return `ocr-file-${Date.now()}-${idCounter}`
}

/** 把字段值拍平为可渲染字符串；数字加千分位，布尔转中文，数组用顿号连接。 */
export function formatFieldValue(value: unknown): string {
  if (value == null || value === '') return '—'
  if (typeof value === 'number') return value.toLocaleString('zh-CN')
  if (typeof value === 'boolean') return value ? '是' : '否'
  if (Array.isArray(value)) return value.map((v) => String(v)).join('、')
  return String(value)
}
