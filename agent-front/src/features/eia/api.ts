import { MOCK_EIA_CASES } from './model/mock-data'
import type { EiaCase } from './types'

// 数据层接缝(design.md A4)：本 sprint 不建后端(方案 C 已弃)，三个函数均为 mock 实现，
// 但函数签名即未来接线的契约起点——真实后端接入时复用 D9 `/ocr/jobs` 任务化 + 轮询先例
// (提交 → 202 + request_id → 单元事件轮询)，submit-page.tsx / desk-page.tsx 的交互层
// 不必改动，只换这里的实现。

export interface SubmitEiaBatchResult {
  batchNo: string
}

/** 受理编号：mock 实现本地生成；真实后端接线后改由响应下发。 */
function createBatchNo(): string {
  const now = new Date()
  const year = now.getFullYear()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  const sequence = String(Math.floor(Math.random() * 900) + 100)
  return `HP-${year}${month}${day}-${sequence}`
}

/**
 * 提交本批检测材料，开始 AI 分析。mock 实现立即返回受理编号；真实分析在此 sprint
 * 由 stream-script.ts 本地驱动，不经过这里的返回值。
 */
export async function submitEiaBatch(
  _files: File[]
): Promise<SubmitEiaBatchResult> {
  return { batchNo: createBatchNo() }
}

/** 受理工作台案件列表。 */
export async function listEiaCases(): Promise<EiaCase[]> {
  return MOCK_EIA_CASES
}
