import type { ApiResult } from '@/types/api'
import { apiClient } from '@/lib/http'
import { normalizeServerInfo, type ServerInfo } from './model'

function unwrapResult<T>(result: ApiResult<T>) {
  return result.data
}

export async function fetchServerInfo(): Promise<ServerInfo> {
  const response = await apiClient.get<ApiResult<unknown>>('/monitor/server')
  return normalizeServerInfo(unwrapResult(response.data))
}
