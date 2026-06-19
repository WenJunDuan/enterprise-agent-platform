import { describe, expect, test } from 'bun:test'
import { tenderReviewMockData } from './mock-data'
import { buildDashboardSummary, filterReviewHistory } from './model'
import type { TenderReviewMockData } from './types'

describe('contract tender review model', () => {
  test('buildDashboardSummary aggregates prototype workbench counts', () => {
    const summary = buildDashboardSummary(tenderReviewMockData)

    expect(summary.totalCount).toBe(tenderReviewMockData.projects.length)
    expect(summary.activeCount).toBe(3)
    expect(summary.reviewCount).toBe(1)
    expect(summary.completedCount).toBe(3)
    expect(summary.stats.map((stat) => [stat.label, stat.count])).toEqual([
      ['分析中', 2],
      ['待复核', 1],
      ['已完成', 3],
      ['全部项目', 6],
    ])
    expect(summary.activeProjects.map((project) => project.code)).toEqual([
      'BJ-2026-ZB-018',
      'BJ-2026-ZB-014',
      'BJ-2026-ZB-011',
    ])
  })

  test('buildDashboardSummary handles empty project data', () => {
    const emptyData: TenderReviewMockData = {
      ...tenderReviewMockData,
      projects: [],
    }

    const summary = buildDashboardSummary(emptyData)

    expect(summary.totalCount).toBe(0)
    expect(summary.activeProjects).toEqual([])
    expect(summary.stats.map((stat) => stat.count)).toEqual([0, 0, 0, 0])
  })

  test('filterReviewHistory only returns completed projects', () => {
    const allHistory = filterReviewHistory(tenderReviewMockData.projects, {
      query: '',
      timeRange: 'all',
      now: '2026-06-19',
    })

    expect(allHistory.map((item) => item.status)).toEqual([
      'done',
      'done',
      'done',
    ])
  })

  test('filterReviewHistory applies search and time range filters', () => {
    const searchResult = filterReviewHistory(tenderReviewMockData.projects, {
      query: '轨道交通',
      timeRange: 'all',
      now: '2026-06-19',
    })
    const completedThisMonth = filterReviewHistory(
      tenderReviewMockData.projects,
      {
        query: '',
        timeRange: 'month',
        now: '2026-06-19',
      }
    )
    const weekItems = filterReviewHistory(tenderReviewMockData.projects, {
      query: '',
      timeRange: 'week',
      now: '2026-06-19',
    })

    expect(searchResult.map((item) => item.code)).toEqual(['BJ-2026-ZB-009'])
    expect(completedThisMonth.map((item) => item.code)).toEqual([
      'BJ-2026-ZB-009',
      'BJ-2026-ZB-006',
    ])
    expect(weekItems).toEqual([])
  })
})
