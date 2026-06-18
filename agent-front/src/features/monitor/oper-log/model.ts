import { toId } from '@/lib/ids'

export type OperLog = {
  operId: string
  title: string
  businessType: number
  method: string
  requestMethod: string
  operatorType: number
  operName: string
  deptName: string | null
  operUrl: string
  operIp: string
  operLocation: string | null
  operParam: string | null
  jsonResult: string | null
  status: 0 | 1
  errorMsg: string | null
  operTime: string | null
  costTime: number
}

export type OperLogQuery = {
  pageNum: number
  pageSize: number
  title?: string
  operName?: string
  businessType?: number
  status?: number
  beginTime?: string
  endTime?: string
}

export type OperLogPage = {
  pageNum: number
  pageSize: number
  total: number
  pages: number
  records: OperLog[]
}

function getRecord(input: unknown): Record<string, unknown> {
  return (input && typeof input === 'object' ? input : {}) as Record<
    string,
    unknown
  >
}

function toNullableString(value: unknown): string | null {
  if (typeof value !== 'string') return null
  const trimmed = value.trim()
  return trimmed === '' ? null : trimmed
}

function normalizeStatus(value: unknown): 0 | 1 {
  return Number(value) === 1 ? 1 : 0
}

export function normalizeOperLog(input: unknown): OperLog {
  const record = getRecord(input)
  return {
    operId: toId(record.operId ?? record.id),
    title: String(record.title ?? ''),
    businessType: Number(record.businessType ?? 0),
    method: String(record.method ?? ''),
    requestMethod: String(record.requestMethod ?? ''),
    operatorType: Number(record.operatorType ?? 0),
    operName: String(record.operName ?? ''),
    deptName: toNullableString(record.deptName),
    operUrl: String(record.operUrl ?? ''),
    operIp: String(record.operIp ?? ''),
    operLocation: toNullableString(record.operLocation),
    operParam: toNullableString(record.operParam),
    jsonResult: toNullableString(record.jsonResult),
    status: normalizeStatus(record.status),
    errorMsg: toNullableString(record.errorMsg),
    operTime: toNullableString(record.operTime),
    costTime: Number(record.costTime ?? 0),
  }
}

export function formatDateTime(value: string | null) {
  if (!value) return '-'
  return value.replace('T', ' ').slice(0, 19)
}

export function tryFormatJson(value: string | null): string {
  if (!value) return ''
  try {
    return JSON.stringify(JSON.parse(value), null, 2)
  } catch {
    return value
  }
}
