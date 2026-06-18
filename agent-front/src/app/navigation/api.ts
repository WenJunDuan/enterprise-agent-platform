import { apiClient } from '@/lib/http'
import type { ApiResult } from '@/types/api'
import type { BackendMenuRouter } from './types'

function unwrapResult<T>(result: ApiResult<T>) {
  return result.data
}

export async function fetchMenuRouters() {
  const response =
    await apiClient.get<ApiResult<BackendMenuRouter[]>>('/system/menu/getRouters')

  return unwrapResult(response.data)
}

export function navigationQueryOptions() {
  return {
    queryKey: ['navigation', 'routers'] as const,
    queryFn: fetchMenuRouters,
    staleTime: 5 * 60 * 1000,
  }
}
