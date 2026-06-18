import type { ApiResult } from '@/types/api'
import { apiClient } from '@/lib/http'
import {
  normalizeLoginLog,
  type LoginLogPage,
  type LoginLogQuery,
} from './model'

function unwrapResult<T>(result: ApiResult<T>) {
  return result.data
}

export async function fetchLoginLogPage(
  query: LoginLogQuery
): Promise<LoginLogPage> {
  const response = await apiClient.get<ApiResult<Record<string, unknown>>>(
    '/monitor/login/log/list',
    {
      params: {
        pageNum: query.pageNum,
        pageSize: query.pageSize,
        username: query.username?.trim() || undefined,
        ipaddr: query.ipaddr?.trim() || undefined,
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
    records: records.map(normalizeLoginLog),
  }
}

export async function deleteLoginLogs(infoIds: string[]): Promise<void> {
  if (infoIds.length === 0) return
  await apiClient.delete<ApiResult<null>>(
    `/monitor/login/log/${infoIds.join(',')}`
  )
}

export async function cleanLoginLog(): Promise<void> {
  await apiClient.delete<ApiResult<null>>('/monitor/login/log/clean')
}
