import type {
  OcrJobStatusResponse,
  OcrJobStatusValue,
  OcrJobUnit,
} from '@/features/audit/types'

// D9 streaming-ocr T4：页级流式 OCR 前端渲染的纯逻辑（轮询节奏 / 分组 / payload 取文本），
// 抽出与 react-query hook 解耦，理由同 tender-review/model.ts —— 可脱离 DOM 直接单测。

/** 轮询间隔，继承 tender-review 轮询先例（use-tender-review-page.ts 固定 2500ms）。 */
export const OCR_JOB_POLL_INTERVAL_MS = 2500

const TERMINAL_STATUSES: readonly OcrJobStatusValue[] = ['completed', 'failed']

export function isTerminalJobStatus(status: OcrJobStatusValue): boolean {
  return TERMINAL_STATUSES.includes(status)
}

/**
 * react-query `refetchInterval` 回调的纯决策部分：终态（completed/failed）或任务丢失
 * （data===null，如 404 / 跨租户不可见）都停止轮询；否则固定间隔轮询直到终态。
 *
 * @param data - 最近一次成功轮询的响应；`undefined` 表示尚未拿到第一次响应，`null` 表示
 *   查询函数捕获到查找失败（未知 request_id）。
 */
export function ocrJobRefetchInterval(
  data: OcrJobStatusResponse | null | undefined
): number | false {
  if (data === undefined) return OCR_JOB_POLL_INTERVAL_MS
  if (data === null) return false
  return isTerminalJobStatus(data.status) ? false : OCR_JOB_POLL_INTERVAL_MS
}

export type OcrJobPhase = 'idle' | 'submitting' | OcrJobStatusValue // 'queued' | 'running' | 'completed' | 'failed'

/** 综合提交态 + 轮询态推出 UI 四态（loading/partial/success/error）落到的具体阶段。 */
export function deriveOcrJobPhase(params: {
  isSubmitting: boolean
  jobId: string | null
  jobData: OcrJobStatusResponse | null | undefined
}): OcrJobPhase {
  const { isSubmitting, jobId, jobData } = params
  if (isSubmitting) return 'submitting'
  if (!jobId) return 'idle'
  if (jobData === null) return 'failed' // 404 / 任务丢失，按终态处理，不无限轮询
  if (jobData === undefined) return 'queued' // 已提交，首次轮询结果未回
  return jobData.status
}

export interface OcrJobFileGroup {
  file: string
  units: OcrJobUnit[]
}

/**
 * 按文件分组 units，保留首次出现的文件顺序（渐进渲染：来一个 unit 就能渲一个，不等全部
 * 完成）；组内按页号升序排列，文件级单元（page=null）排在最前。
 */
export function groupUnitsByFile(units: OcrJobUnit[]): OcrJobFileGroup[] {
  const order: string[] = []
  const byFile = new Map<string, OcrJobUnit[]>()
  for (const unit of units) {
    if (!byFile.has(unit.file)) {
      byFile.set(unit.file, [])
      order.push(unit.file)
    }
    byFile.get(unit.file)?.push(unit)
  }
  return order.map((file) => ({
    file,
    units: [...(byFile.get(file) ?? [])].sort(
      (a, b) => (a.page ?? -1) - (b.page ?? -1)
    ),
  }))
}

/**
 * 从 payload 里取可展示文本。page=null guard: 服务端 payload 形态因识别路由而异（native
 * pdf 页给 `text`，OCR 引擎页给 `markdown`，文件级 native 结果给 `blocks[]`），未命中任一
 * 已知字段时返回空串——不臆造内容。页锚【第N页】保真：这里只取原文，不额外拼接/改写页号。
 */
export function unitDisplayText(payload: Record<string, unknown>): string {
  if (typeof payload.text === 'string') return payload.text
  if (typeof payload.markdown === 'string') return payload.markdown
  if (Array.isArray(payload.blocks)) {
    return payload.blocks.map((block) => String(block)).join('\n\n')
  }
  return ''
}

/** payload.error 是否为可展示的字符串错误消息；防御边界：服务端形态不保证，非字符串按无错误处理。 */
export function unitErrorText(payload: Record<string, unknown>): string | null {
  return typeof payload.error === 'string' ? payload.error : null
}
