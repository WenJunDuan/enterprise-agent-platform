/**
 * doc 层 OCR 状态谓词与展示映射（H3 KD2 前端硬门的唯一判据源）。
 *
 * 后端 doc 状态在 `ready | failed` 之外新增两档：
 * - `degraded`：底稿完整，但含本地兜底引擎（Tesseract）识别的降级段；
 * - `partial`：部分文件识别失败，或某文件渲染中途失败只出了部分页。
 *
 * 这两档如果不进前端判据，用户会被直接锁死：轮询终态集不认它们 → 永不停；`isOcrReady`
 * 只认 `ready` → 「开始分析」永久禁用。故终态集 / 可用性 / 状态点 / label 全部收敛到本模块，
 * 避免各消费点各写一份 `=== 'ready'` 再漏一处。
 */
import type { DocsStatusResponse, OcrStatus } from './api'

/** 轮询终止判据：这些状态之后后台不会再改。 */
const TERMINAL_STATUSES: readonly string[] = ['ready', 'degraded', 'partial', 'failed']

/** 底稿可用判据：有内容可评标（质量问题由结论 warning 标注，不阻断流程）。 */
const USABLE_STATUSES: readonly string[] = ['ready', 'degraded', 'partial']

/** 底稿受损判据：可用但质量有损，需要给用户告警提示。 */
const IMPAIRED_STATUSES: readonly string[] = ['degraded', 'partial']

const STATUS_LABELS: Record<string, string> = {
  pending: '等待中',
  running: '识别中',
  ready: '已就绪',
  degraded: '已就绪（降级识别）',
  partial: '部分完成',
  failed: '识别失败',
}

const DOT_CLASSES: Record<string, string> = {
  ready: 'bg-emerald-500',
  // 受损态用琥珀色静态点：绝不能落到"蓝色脉冲"上——那是"还在跑"的语义，会让用户以为要继续等。
  degraded: 'bg-amber-500',
  partial: 'bg-amber-500',
  failed: 'bg-red-500',
}

const IN_PROGRESS_DOT_CLASS = 'bg-blue-400 animate-pulse'

/** 该状态是否已终态（轮询应停止）。 */
export function isOcrTerminal(status: string): boolean {
  return TERMINAL_STATUSES.includes(status)
}

/** 该状态的底稿能否直接用于评标。 */
export function isOcrUsable(status: string): boolean {
  return USABLE_STATUSES.includes(status)
}

/** 该状态是否为"可用但有损"。 */
export function isOcrImpaired(status: string): boolean {
  return IMPAIRED_STATUSES.includes(status)
}

/** 状态的中文 label；未知值原样回显（不吞成空白，便于发现漏接的新枚举）。 */
export function ocrStatusLabel(status: string): string {
  return STATUS_LABELS[status] ?? status
}

/** 状态点的颜色 class；非终态才用蓝色脉冲。 */
export function ocrDotClass(status: string): string {
  return DOT_CLASSES[status] ?? IN_PROGRESS_DOT_CLASS
}

/**
 * 底稿受损时的告警文案（用于「开始分析」旁的提示）；全部完好则返回 null。
 *
 * @param docs - docs-status 轮询结果。
 * @returns 点名受损文档的提示语，或 null。
 */
export function ocrImpairedNotice(docs: DocsStatusResponse | null | undefined): string | null {
  if (!docs) return null
  const impaired: string[] = []
  if (docs.tender_doc && isOcrImpaired(docs.tender_doc.ocr_status)) {
    impaired.push(`招标文件（${ocrStatusLabel(docs.tender_doc.ocr_status)}）`)
  }
  for (const bid of docs.bids) {
    if (isOcrImpaired(bid.ocr_status)) {
      impaired.push(`${bid.bidder_name ?? bid.bid_id}（${ocrStatusLabel(bid.ocr_status)}）`)
    }
  }
  if (impaired.length === 0) return null
  return `以下材料底稿降级或部分缺失：${impaired.join('、')}。分析仍可开始，结论会标注受影响的评分项。`
}

/**
 * criteria 抽取失败时的提示（AC3）；正常或未抽取则返回 null。
 *
 * 后端把**具体缺陷**（中文说明 + 机器码，如「评分标准的 items 评分项为空（items_empty）」）
 * 放在 `criteria_error`。旧后端不返回该字段时回落通用文案——宁可笼统也不静默。
 *
 * 动作口径对齐后端 `criteria_gate.criteria_submission_block`（2026-08-19 收单等就绪）：
 * `criteria_status=failed` 在提交口是 **409 硬拒**，此时"先点开始分析、让评标自行解析"不再成立
 * （旧文案如此说过，照做只会撞一次 409）。唯一出路是重新上传招标文件触发重新解析。
 *
 * @param docs - docs-status 轮询结果。
 * @returns 提示文案，或 null。
 */
export function criteriaProblemNotice(
  docs: DocsStatusResponse | null | undefined
): string | null {
  if (docs?.tender_doc?.criteria_status !== 'failed') return null
  const detail = docs.tender_doc.criteria_error?.trim()
  return `招标文件的评分标准未能自动解析${detail ? `：${detail}` : ''}。此时提交评标会被拒绝：请重新上传招标文件触发重新解析，或改用可检索的电子版招标文件（扫描件缺文字层时解析常失败）。`
}

/**
 * 评分标准仍在解析（`criteria_status` 非终态）时的进度说明。
 *
 * 2026-08-19「收单等就绪」后，提交时 criteria 还在解析**不再被拒**：任务已受理，会在开跑判分前
 * 自己等就绪。分析中页必须把这句说出来——否则用户看到「识别中」会以为自己点早了、要退回重来。
 *
 * @param tenderOcrStatus - 招标文件底稿的 OCR 状态（决定当前卡在哪一步）。
 * @returns 面向用户的中文进度说明。
 */
export function criteriaWaitingHint(tenderOcrStatus: string | undefined): string {
  const stage = isOcrUsable(tenderOcrStatus ?? 'pending')
    ? '正在从招标文件抽取评分项、扣分点与废标条款…'
    : '等待招标文件 OCR 完成后自动抽取评分标准…'
  return `${stage}评标已受理，评分标准就绪后自动开始评分，无需重新提交。`
}

/** 供类型收窄使用：断言字符串是已知 OcrStatus（未知值按非终态处理，不冒充 ready）。 */
export type { OcrStatus }
