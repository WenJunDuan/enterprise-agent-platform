import type { AttachmentSummary, SubmissionSummary } from '../types'

const STORAGE_KEY = 'enterprise-audit:submission-summaries:v1'
const MAX_SUMMARIES = 80

type SummaryMap = Record<string, SubmissionSummary>

function canUseStorage(): boolean {
  return typeof window !== 'undefined' && typeof window.localStorage !== 'undefined'
}

export function readSubmissionSummaries(): SummaryMap {
  if (!canUseStorage()) return {}
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return {}
    const parsed = JSON.parse(raw)
    return parsed && typeof parsed === 'object' ? parsed as SummaryMap : {}
  } catch {
    return {}
  }
}

export function getSubmissionSummary(requestId: string): SubmissionSummary | null {
  return readSubmissionSummaries()[requestId] ?? null
}

export function saveSubmissionSummary(summary: SubmissionSummary): void {
  if (!canUseStorage()) return
  const current = readSubmissionSummaries()
  current[summary.request_id] = summary
  const entries = Object.entries(current)
    .sort(([, a], [, b]) => Date.parse(b.submitted_at) - Date.parse(a.submitted_at))
    .slice(0, MAX_SUMMARIES)
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(Object.fromEntries(entries)))
}

export function createAttachmentSummary(
  file: File,
  category: AttachmentSummary['category'],
  index: number,
): AttachmentSummary {
  return {
    id: `${file.name}-${file.size}-${file.lastModified}-${index}`,
    name: file.name,
    size: file.size,
    type: file.type || 'unknown',
    category,
    last_modified: file.lastModified,
  }
}
