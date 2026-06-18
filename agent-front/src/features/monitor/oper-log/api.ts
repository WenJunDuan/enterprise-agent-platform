import type { ApiResult } from '@/types/api'
import { apiClient } from '@/lib/http'
import {
  normalizeOperLog,
  type OperLog,
  type OperLogPage,
  type OperLogQuery,
} from './model'

function unwrapResult<T>(result: ApiResult<T>) {
  return result.data
}

export async function fetchOperLogPage(
  query: OperLogQuery
): Promise<OperLogPage> {
  const response = await apiClient.get<ApiResult<Record<string, unknown>>>(
    '/monitor/operlog/list',
    {
      params: {
        pageNum: query.pageNum,
        pageSize: query.pageSize,
        title: query.title?.trim() || undefined,
        operName: query.operName?.trim() || undefined,
        businessType: query.businessType,
        status: query.status,
        beginTime: query.beginTime || undefined,
        endTime: query.endTime || undefined,
      },
    }
  )

  const page = unwrapResult(response.data)
  const records = Array.isArray(page.records) ? page.records : []
  return {
    pageNum: Number(page.pageNum ?? 1),
    pageSize: Number(page.pageSize ?? 10),
    total: Number(page.total ?? 0),
    pages: Number(page.pages ?? 0),
    records: records.map(normalizeOperLog),
  }
}

export async function fetchOperLogDetail(operId: string): Promise<OperLog> {
  const response = await apiClient.get<ApiResult<unknown>>(
    `/monitor/operlog/${operId}`
  )
  return normalizeOperLog(unwrapResult(response.data))
}

export async function deleteOperLogs(operIds: string[]): Promise<void> {
  if (operIds.length === 0) return
  await apiClient.delete<ApiResult<null>>(
    `/monitor/operlog/${operIds.join(',')}`
  )
}

export async function cleanOperLog(): Promise<void> {
  await apiClient.delete<ApiResult<null>>('/monitor/operlog/clean')
}
