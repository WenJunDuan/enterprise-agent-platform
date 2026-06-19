import type {
  DashboardSummary,
  HistoryFilters,
  TenderProject,
  TenderReviewMockData,
} from './types'

const DAY_MS = 24 * 60 * 60 * 1000
const WEEK_DAYS = 7
const MONTH_DAYS = 30

function isActiveProject(project: TenderProject) {
  return project.status === 'doing' || project.status === 'review'
}

function isHistoryProject(project: TenderProject) {
  return project.status === 'done'
}

function getRangeDays(timeRange: HistoryFilters['timeRange']) {
  if (timeRange === 'week') return WEEK_DAYS
  if (timeRange === 'month') return MONTH_DAYS
  return null
}

function isWithinRange(date: string, filters: HistoryFilters) {
  const rangeDays = getRangeDays(filters.timeRange)
  if (!rangeDays) return true

  const nowTime = new Date(filters.now).getTime()
  const itemTime = new Date(date).getTime()
  const diffDays = Math.floor((nowTime - itemTime) / DAY_MS)

  return diffDays >= 0 && diffDays < rangeDays
}

export function buildDashboardSummary(
  data: TenderReviewMockData
): DashboardSummary {
  const activeProjects = data.projects.filter(isActiveProject)
  const reviewCount = data.projects.filter(
    (project) => project.status === 'review'
  ).length
  const completedCount = data.projects.filter(isHistoryProject).length

  return {
    activeProjects,
    activeCount: activeProjects.length,
    reviewCount,
    completedCount,
    totalCount: data.projects.length,
    stats: [
      {
        label: '分析中',
        count: data.projects.filter((project) => project.status === 'doing')
          .length,
        tone: 'blue',
      },
      { label: '待复核', count: reviewCount, tone: 'amber' },
      { label: '已完成', count: completedCount, tone: 'green' },
      { label: '全部项目', count: data.projects.length, tone: 'muted' },
    ],
  }
}

export function filterReviewHistory(
  projects: TenderProject[],
  filters: HistoryFilters
) {
  const query = filters.query.trim().toLowerCase()

  return projects.filter((project) => {
    if (!isHistoryProject(project)) return false

    const matchesQuery = query
      ? `${project.name} ${project.code} ${project.method} ${project.recommendedBidder}`
          .toLowerCase()
          .includes(query)
      : true
    return matchesQuery && isWithinRange(project.date, filters)
  })
}
