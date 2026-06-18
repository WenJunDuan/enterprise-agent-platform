export type CacheStat = {
  name: string
  hitCount: number
  missCount: number
  hitRate: string
  size: number
}

export type CacheDetail = CacheStat & {
  evictionCount: number
  loadCount: number
  error?: string | null
}

export type CacheOverview = {
  cacheCount: number
  totalEntries: number
  totalHits: number
  totalMisses: number
  averageHitRate: number
}

function getRecord(input: unknown): Record<string, unknown> {
  return (input && typeof input === 'object' ? input : {}) as Record<
    string,
    unknown
  >
}

function toNumber(value: unknown) {
  const num = Number(value)
  return Number.isFinite(num) ? num : 0
}

function toStringValue(value: unknown) {
  return typeof value === 'string' ? value : ''
}

export function parseHitRate(value: string) {
  const numeric = Number.parseFloat(value.replace('%', ''))
  return Number.isFinite(numeric) ? numeric : 0
}

export function normalizeCacheStat(input: unknown): CacheStat {
  const record = getRecord(input)

  return {
    name: toStringValue(record.name),
    hitCount: toNumber(record.hitCount),
    missCount: toNumber(record.missCount),
    hitRate: toStringValue(record.hitRate),
    size: toNumber(record.size),
  }
}

export function normalizeCacheDetail(input: unknown): CacheDetail {
  const record = getRecord(input)
  const base = normalizeCacheStat(record)

  return {
    ...base,
    evictionCount: toNumber(record.evictionCount),
    loadCount: toNumber(record.loadCount),
    error: typeof record.error === 'string' ? record.error : null,
  }
}

export function buildCacheOverview(stats: CacheStat[]): CacheOverview {
  const totalHitRate = stats.reduce((sum, stat) => sum + parseHitRate(stat.hitRate), 0)

  return {
    cacheCount: stats.length,
    totalEntries: stats.reduce((sum, stat) => sum + stat.size, 0),
    totalHits: stats.reduce((sum, stat) => sum + stat.hitCount, 0),
    totalMisses: stats.reduce((sum, stat) => sum + stat.missCount, 0),
    averageHitRate: stats.length > 0 ? Number((totalHitRate / stats.length).toFixed(2)) : 0,
  }
}
