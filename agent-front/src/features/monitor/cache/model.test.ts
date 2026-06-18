import { describe, expect, test } from 'bun:test'
import {
  buildCacheOverview,
  normalizeCacheDetail,
  normalizeCacheStat,
  parseHitRate,
} from './model'

describe('cache model', () => {
  test('normalizeCacheStat should coerce numeric fields and preserve hitRate string', () => {
    const stat = normalizeCacheStat({
      name: 'sys:dict',
      hitCount: '12',
      missCount: 3,
      hitRate: '80.00%',
      size: '6',
    })

    expect(stat.name).toBe('sys:dict')
    expect(stat.hitCount).toBe(12)
    expect(stat.missCount).toBe(3)
    expect(stat.size).toBe(6)
    expect(stat.hitRate).toBe('80.00%')
    expect(parseHitRate(stat.hitRate)).toBe(80)
  })

  test('normalizeCacheDetail should expose optional counters with safe defaults', () => {
    const detail = normalizeCacheDetail({
      name: 'sys:dict',
      hitCount: 12,
      missCount: 3,
      hitRate: '80.00%',
      evictionCount: '4',
      loadCount: 9,
      size: 6,
    })

    expect(detail.evictionCount).toBe(4)
    expect(detail.loadCount).toBe(9)
  })

  test('buildCacheOverview should aggregate totals and average hit rate', () => {
    const overview = buildCacheOverview([
      normalizeCacheStat({
        name: 'user',
        hitCount: 9,
        missCount: 1,
        hitRate: '90.00%',
        size: 3,
      }),
      normalizeCacheStat({
        name: 'dict',
        hitCount: 3,
        missCount: 3,
        hitRate: '50.00%',
        size: 2,
      }),
    ])

    expect(overview.cacheCount).toBe(2)
    expect(overview.totalHits).toBe(12)
    expect(overview.totalMisses).toBe(4)
    expect(overview.totalEntries).toBe(5)
    expect(overview.averageHitRate).toBe(70)
  })
})
