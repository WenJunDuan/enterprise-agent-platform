import type { AuditResult, RiskDimension, TaskStatus } from './types'

export const taskStatusLabels: Record<TaskStatus, string> = {
  accepted: '已接收',
  running: '审核中',
  completed: '已完成',
  failed: '失败',
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return '-'
  return new Date(iso).toLocaleString('zh-CN')
}

export function truncateId(value: string, length = 18): string {
  return value.length > length ? `${value.slice(0, length)}...` : value
}

export function toDisplayText(item: unknown): string {
  if (typeof item === 'string') return item
  if (item && typeof item === 'object') {
    const data = item as Record<string, unknown>
    const desc = String(data.description ?? data.message ?? data.reason ?? '').trim()
    const severity = String(data.severity ?? '').trim()
    if (severity && desc) return `[${severity}] ${desc}`
    if (desc) return desc
    return JSON.stringify(item)
  }
  return String(item)
}

export function normalizeRiskDimensions(raw: AuditResult['risk_dimensions']) {
  let entries: [string, unknown][] = []
  if (Array.isArray(raw)) {
    entries = raw
      .filter((item): item is RiskDimension => Boolean(item?.name))
      .map((item) => [item.name, item.score])
  } else if (raw && typeof raw === 'object') {
    entries = Object.entries(raw)
  }

  return entries
    .map(([name, score]) => {
      let numeric = Number(score)
      if (!Number.isFinite(numeric)) numeric = 0
      if (numeric > 10) numeric = Math.round(numeric / 10)
      return {
        name,
        score: Math.max(0, Math.min(10, numeric)),
      }
    })
    .filter((item) => item.name)
}

export function verdictLabel(verdict: AuditResult['verdict']) {
  if (verdict === 'approved') return '通过'
  if (verdict === 'rejected') return '拒绝'
  if (verdict === 'manual_review') return '待人工复核'
  return '未出结论'
}
