import { cloneLocalSystemMenuRouters } from './local-system-routers'

export async function fetchMenuRouters() {
  return cloneLocalSystemMenuRouters()
}

export function navigationQueryOptions() {
  return {
    queryKey: ['navigation', 'routers'] as const,
    queryFn: fetchMenuRouters,
    staleTime: 5 * 60 * 1000,
  }
}
