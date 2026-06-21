import type { AuditResult } from '@/features/audit/types'
import type {
  TenderCompareResponse,
  TenderProjectDetailResponse,
  TenderProjectResponse,
  TenderProjectResultSummary,
} from './api'
import type {
  CompareGroup,
  DashboardSummary,
  DocumentParagraph,
  HistoryFilters,
  ProjectInfo,
  ReviewBidder,
  ReviewCategory,
  ReviewCategoryData,
  ReviewItem,
  TenderScoreIssue,
  TenderScoreSummary,
  TenderScoringItem,
  TenderProject,
  TenderProjectStatus,
  TenderReviewMockData,
} from './types'

const DAY_MS = 24 * 60 * 60 * 1000
const WEEK_DAYS = 7
const MONTH_DAYS = 30
const DEFAULT_METHOD = '综合评估法'
const EMPTY_PROJECT_TITLE = '新建招投标项目'
const BIDDER_TAGS = '甲乙丙丁戊己庚辛壬癸'

type UnknownRecord = Record<string, unknown>

type BuildTenderReviewDataInput = {
  projects?: TenderProjectResponse[]
  project?: TenderProjectResponse | TenderProjectDetailResponse | null
  resultSummaries?: TenderProjectResultSummary[]
  selectedResult?: AuditResult | null
  compare?: TenderCompareResponse | null
}

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
  data: Pick<TenderReviewMockData, 'projects'> | TenderProject[]
): DashboardSummary {
  const projects = Array.isArray(data) ? data : data.projects
  const activeProjects = projects.filter(isActiveProject)
  const reviewCount = projects.filter(
    (project) => project.status === 'review'
  ).length
  const completedCount = projects.filter(isHistoryProject).length

  return {
    activeProjects,
    activeCount: activeProjects.length,
    reviewCount,
    completedCount,
    totalCount: projects.length,
    stats: [
      {
        label: '分析中',
        count: projects.filter((project) => project.status === 'doing').length,
        tone: 'blue',
      },
      { label: '待复核', count: reviewCount, tone: 'amber' },
      { label: '已完成', count: completedCount, tone: 'green' },
      { label: '全部项目', count: projects.length, tone: 'muted' },
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

export function mapTenderProject(
  project: TenderProjectResponse | TenderProjectDetailResponse,
  compare?: TenderCompareResponse | null,
  resultSummaries: TenderProjectResultSummary[] = []
): TenderProject {
  const detail = isTenderProjectDetail(project) ? project : null
  const baseStatus = normalizeProjectStatus(project.status)
  const bidderCount = Math.max(detail?.bidder_count ?? 0, resultSummaries.length)
  const completedCount = Math.max(
    detail?.bids.filter((bid) => bid.status === 'completed').length ?? 0,
    resultSummaries.length
  )
  const status = deriveProjectStatus(baseStatus, completedCount, bidderCount)
  const progress = getProjectProgress(status, completedCount, bidderCount)
  const topScore = getTopCompareScore(compare)
  const compareStale = Boolean(detail?.compare_stale || compare?.stale)

  return {
    id: project.project_id,
    name: project.title?.trim() || project.tender_no?.trim() || EMPTY_PROJECT_TITLE,
    code: project.tender_no?.trim() || project.project_id,
    method: project.method?.trim() || compare?.result.method || DEFAULT_METHOD,
    bidderCount,
    score: topScore == null || compareStale ? '-' : formatScore(topScore),
    date: formatDate(project.created_at),
    status,
    stage: getProjectStage(status, completedCount, bidderCount, compareStale),
    progress,
    riskCount: getRiskCount(detail, resultSummaries),
    recommendedBidder: getRecommendedBidder(detail, compare, status, compareStale),
  }
}

export function mapTenderProjects(
  projects: TenderProjectResponse[],
  details: TenderProjectDetailResponse[] = [],
  compares: TenderCompareResponse[] = []
) {
  const detailById = new Map(details.map((detail) => [detail.project_id, detail]))
  const compareById = new Map(compares.map((compare) => [compare.project_id, compare]))
  return projects.map((project) =>
    mapTenderProject(
      detailById.get(project.project_id) ?? project,
      compareById.get(project.project_id) ?? null
    )
  )
}

export function buildTenderReviewData({
  projects = [],
  project,
  resultSummaries = [],
  selectedResult,
  compare,
}: BuildTenderReviewDataInput): TenderReviewMockData {
  const mappedProjects = projects.map((item) => mapTenderProject(item))
  const activeProject = project ?? projects[0] ?? null
  const projectData = activeProject
    ? mapTenderProject(activeProject, compare, resultSummaries)
    : null
  const reviewBidders = buildReviewBidders(
    activeProject,
    resultSummaries,
    selectedResult,
    compare
  )
  const scoringItems = buildScoringItems(selectedResult)

  return {
    projects: projectData
      ? [projectData, ...mappedProjects.filter((item) => item.id !== projectData.id)]
      : mappedProjects,
    projectInfo: buildProjectInfo(activeProject, compare),
    tenderFiles: [],
    uploadBidders: [],
    reviewBidders,
    categories: buildCategories(selectedResult),
    paragraphs: buildParagraphs(selectedResult),
    compareGroups: buildCompareGroups(compare),
    resultVerdict: selectedResult?.verdict,
    resultExplanation: selectedResult?.explanation || selectedResult?.summary || '',
    resultReasons: normalizeDisplayList(selectedResult?.reasons),
    resultPolicyRefs: normalizeDisplayList(selectedResult?.policy_refs),
    scoringItems,
    scoreSummary: buildScoreSummary(scoringItems),
    compareNotice: buildCompareNotice(activeProject, compare),
  }
}

function isTenderProjectDetail(
  project: TenderProjectResponse | TenderProjectDetailResponse
): project is TenderProjectDetailResponse {
  return 'bidder_count' in project && Array.isArray(project.bids)
}

function normalizeProjectStatus(status: string): TenderProjectStatus {
  if (
    status === 'doing' ||
    status === 'review' ||
    status === 'done' ||
    status === 'archived'
  ) {
    return status
  }
  if (status === 'completed') return 'done'
  if (status === 'failed') return 'review'
  return 'doing'
}

function deriveProjectStatus(
  status: TenderProjectStatus,
  completedCount: number,
  bidderCount: number
): TenderProjectStatus {
  if (status === 'archived') return status
  if (bidderCount > 0 && completedCount >= bidderCount) return 'done'
  return status
}

function getProjectProgress(
  status: TenderProjectStatus,
  completedCount: number,
  bidderCount: number
) {
  if (status === 'done' || status === 'archived' || status === 'review') return 100
  if (bidderCount > 0) return Math.round((completedCount / bidderCount) * 100)
  return 0
}

function getProjectStage(
  status: TenderProjectStatus,
  completedCount: number,
  bidderCount: number,
  compareStale: boolean
) {
  if (compareStale) return '投标人有变化 · 待重新横比'
  if (status === 'done') return '已完成'
  if (status === 'archived') return '已归档'
  if (status === 'review') return '评分完成 · 待复核'
  if (bidderCount > 0) return `${completedCount}/${bidderCount} 家评标完成`
  return '评标任务进行中'
}

function getRiskCount(
  detail: TenderProjectDetailResponse | null,
  resultSummaries: TenderProjectResultSummary[]
) {
  const bidRisks =
    detail?.bids.filter((bid) => bid.verdict === 'manual_review').length ?? 0
  const summaryRisks = resultSummaries.filter(
    (summary) =>
      summary.verdict === 'manual_review' || Boolean(summary.manual_review_reason)
  ).length
  return Math.max(bidRisks, summaryRisks)
}

function getRecommendedBidder(
  detail: TenderProjectDetailResponse | null,
  compare: TenderCompareResponse | null | undefined,
  status: TenderProjectStatus,
  compareStale: boolean
) {
  if (compareStale) return '待重新横比'
  if (detail?.recommended_bidder) return detail.recommended_bidder
  if (compare?.result.provisional === false && compare.result.recommended) {
    return compare.result.recommended
  }
  if (compare?.result.provisional) return '暂定排名'
  if (status === 'doing') return '分析中'
  return '暂未推荐'
}

function getTopCompareScore(compare?: TenderCompareResponse | null) {
  if (!compare?.result.bidders.length) return null
  const ranked = [...compare.result.bidders].sort(
    (left, right) => (left.rank ?? Number.MAX_SAFE_INTEGER) - (right.rank ?? Number.MAX_SAFE_INTEGER)
  )
  return toNumber(ranked[0]?.total_score)
}

function buildProjectInfo(
  project?: TenderProjectResponse | TenderProjectDetailResponse | null,
  compare?: TenderCompareResponse | null
): ProjectInfo {
  const date = compare?.computed_at || project?.updated_at || project?.created_at || ''
  const id = project?.project_id || 'new'
  return {
    name: project?.title?.trim() || project?.tender_no?.trim() || EMPTY_PROJECT_TITLE,
    code: project?.tender_no?.trim() || (project ? project.project_id : '-'),
    method: project?.method?.trim() || compare?.result.method || DEFAULT_METHOD,
    controlPrice: project?.control_price?.trim() || '-',
    reviewDate: formatChineseDate(date),
    reportNo: `TR-${formatDate(date).replaceAll('-', '')}-${id.slice(0, 8)}`,
  }
}

function buildReviewBidders(
  project: TenderProjectResponse | TenderProjectDetailResponse | null,
  resultSummaries: TenderProjectResultSummary[],
  selectedResult?: AuditResult | null,
  compare?: TenderCompareResponse | null
): ReviewBidder[] {
  if (compare?.result.bidders.length) {
    return [...compare.result.bidders]
      .sort(
        (left, right) =>
          (left.rank ?? Number.MAX_SAFE_INTEGER) - (right.rank ?? Number.MAX_SAFE_INTEGER)
      )
      .map((bidder, index) => ({
        id: bidder.claim_id,
        tag: getBidderTag(index),
        name: bidder.claim_id,
        short: shortenBidderName(bidder.claim_id),
        total: toNumber(bidder.total_score) ?? 0,
        rank: bidder.rank ?? index + 1,
      }))
  }

  const detailBids = isTenderProjectDetailOrNull(project) ? project.bids : []
  const summaries = resultSummaries.length
    ? resultSummaries
    : detailBids.map((bid) => ({
        request_id: bid.request_id,
        claim_id: bid.claim_id,
        verdict: bid.verdict,
      }))

  if (summaries.length) {
    return summaries.map((summary, index) => {
      const name =
        summary.claim_id ||
        (selectedResult?.claim_id && index === 0 ? selectedResult.claim_id : '') ||
        `投标人 ${index + 1}`
      return {
        id: name,
        tag: getBidderTag(index),
        name,
        short: shortenBidderName(name),
        total: index === 0 ? getResultTotalScore(selectedResult) : 0,
        rank: index + 1,
      }
    })
  }

  if (selectedResult?.claim_id) {
    return [
      {
        id: selectedResult.claim_id,
        tag: getBidderTag(0),
        name: selectedResult.claim_id,
        short: shortenBidderName(selectedResult.claim_id),
        total: getResultTotalScore(selectedResult),
        rank: 1,
      },
    ]
  }

  return []
}

function isTenderProjectDetailOrNull(
  project: TenderProjectResponse | TenderProjectDetailResponse | null | undefined
): project is TenderProjectDetailResponse {
  return Boolean(project && isTenderProjectDetail(project))
}

function buildCategories(result?: AuditResult | null): ReviewCategoryData[] {
  const scoring = buildScoringItems(result)
  if (!scoring.length) {
    return [
      {
        key: 'qual',
        label: '审核结果',
        items: [
          {
            id: 'result-summary',
            title: getVerdictLabel(result?.verdict),
            desc: result?.summary || result?.explanation || '暂无评审明细。',
            loc: 0,
            aiNote: result?.explanation || '等待评标结果生成后展示评分项明细。',
            status: getVerdictStatus(result?.verdict),
          },
        ],
      },
    ]
  }

  const groups = new Map<ReviewCategory, ReviewItem[]>()
  scoring.forEach((item, index) => {
    const title = item.item || `评分项 ${index + 1}`
    const criteria = findCriteriaItem(result, title)
    const category = item.category
    const groupItems = groups.get(category) ?? []
    groupItems.push({
      id: item.id || `score-${index}`,
      title,
      desc:
        toText(criteria?.scoring_rule) ||
        toText(criteria?.source_ref) ||
        '按招标文件评分标准判定。',
      loc: index,
      aiNote: item.basis || result?.explanation || '该评分项已完成判定。',
      status: getScoringStatus(item.status, item.score),
      got: item.score ?? undefined,
      max: item.max,
    })
    groups.set(category, groupItems)
  })

  return (['qual', 'tech', 'comm'] as const)
    .filter((key) => groups.has(key))
    .map((key) => ({
      key,
      label: getCategoryLabel(key),
      items: groups.get(key) ?? [],
    }))
}

function buildParagraphs(result?: AuditResult | null): DocumentParagraph[] {
  const evidence = result?.evidence_chain ?? []
  if (evidence.length) {
    return evidence.map((item, index) => ({
      loc: index,
      label: item.source || `证据 ${index + 1}`,
      text: [item.finding, item.conclusion].filter(Boolean).join('；'),
    }))
  }
  if (result?.explanation) {
    return [
      {
        loc: 0,
        label: '结论说明',
        text: result.explanation,
      },
    ]
  }
  return []
}

function buildCompareGroups(compare?: TenderCompareResponse | null): CompareGroup[] {
  const bidders = compare?.result.bidders ?? []
  if (!bidders.length) return []

  const rows = [
    buildCompareRow('价格分', bidders.map((bidder) => bidder.price_score)),
    buildCompareRow('其他评审分', bidders.map((bidder) => bidder.other_score)),
  ].filter((row): row is CompareGroup['rows'][number] => row != null)

  return rows.length
    ? [
        {
          name: '横向评分',
          rows,
        },
      ]
    : []
}

function buildCompareRow(name: string, values: Array<number | null | undefined>) {
  if (!values.some((value) => value != null)) return null
  const cells = values.map((value) => roundScore(toNumber(value) ?? 0))
  return {
    name,
    max: Math.max(...cells, 1),
    cells,
  }
}

function buildCompareNotice(
  project?: TenderProjectResponse | TenderProjectDetailResponse | null,
  compare?: TenderCompareResponse | null
) {
  const stale = Boolean(
    (isTenderProjectDetailOrNull(project) && project.compare_stale) || compare?.stale
  )
  const result = compare?.result
  return {
    stale,
    provisional: Boolean(result?.provisional),
    recommended: result?.recommended ?? null,
    warnings: result?.warnings ?? [],
    explanation:
      result?.explanation ||
      (stale ? '投标人有变化，请重新横比后再展示推荐结论。' : ''),
  }
}

function getScoringItems(result?: AuditResult | null): UnknownRecord[] {
  const scoring = result?.extracted_data?.scoring
  return Array.isArray(scoring) ? scoring.filter(isRecord) : []
}

function buildScoringItems(result?: AuditResult | null): TenderScoringItem[] {
  return getScoringItems(result).map((item, index) => {
    const title = toText(item.item) || `评分项 ${index + 1}`
    const max = toNumber(item.max) ?? 0
    const score = toNumber(item.score)
    const status = toText(item.status) || (score == null ? 'manual_review' : 'scored')
    return {
      id: `score-${index}`,
      item: title,
      max,
      score,
      status,
      basis: toText(item.basis) || result?.explanation || '暂无判定依据。',
      category: inferCategory(title),
    }
  })
}

function buildScoreSummary(items: TenderScoringItem[]): TenderScoreSummary {
  const maxTotal = roundScore(items.reduce((sum, item) => sum + item.max, 0))
  const earnedTotal = roundScore(
    items.reduce(
      (sum, item) =>
        item.status === 'scored' && item.score != null ? sum + item.score : sum,
      0
    )
  )
  const deductedItems: TenderScoreIssue[] = []
  const rejectedItems: TenderScoreIssue[] = []
  const pendingItems: TenderScoreIssue[] = []

  items.forEach((item) => {
    const issue = toScoreIssue(item)
    if (item.status === 'manual_review' || item.score == null) {
      pendingItems.push({ ...issue, deduction: null })
    } else if (item.status === 'rejected') {
      rejectedItems.push(issue)
    } else if (item.status === 'scored' && item.score < item.max) {
      deductedItems.push(issue)
    }
  })

  return {
    maxTotal,
    earnedTotal,
    deductedItems,
    rejectedItems,
    pendingItems,
  }
}

function toScoreIssue(item: TenderScoringItem): TenderScoreIssue {
  const deduction =
    item.score == null ? null : roundScore(Math.max(0, item.max - item.score))
  return {
    item: item.item,
    max: item.max,
    score: item.score,
    status: item.status,
    deduction,
    basis: item.basis,
  }
}

function findCriteriaItem(result: AuditResult | null | undefined, title: string) {
  const criteria = result?.extracted_data?.criteria
  const items = Array.isArray(criteria)
    ? criteria
    : isRecord(criteria) && Array.isArray(criteria.items)
      ? criteria.items
      : []
  return items.filter(isRecord).find((item) => toText(item.item) === title)
}

function getResultTotalScore(result?: AuditResult | null) {
  return roundScore(
    getScoringItems(result).reduce((sum, item) => sum + (toNumber(item.score) ?? 0), 0)
  )
}

function inferCategory(title: string): ReviewCategory {
  if (title.includes('资格') || title.includes('资质')) return 'qual'
  if (
    title.includes('报价') ||
    title.includes('价格') ||
    title.includes('商务') ||
    title.includes('财务') ||
    title.includes('信誉') ||
    title.includes('业绩')
  ) {
    return 'comm'
  }
  return 'tech'
}

function getCategoryLabel(category: ReviewCategory) {
  if (category === 'qual') return '资格审查'
  if (category === 'tech') return '技术评分'
  return '商务·信誉'
}

function getScoringStatus(status: string, score: number | null): ReviewItem['status'] {
  if (status === 'manual_review') return 'warning'
  if (status === 'rejected' || status === 'failed') return 'fail'
  if (score == null) return 'warning'
  return 'pass'
}

function getVerdictStatus(verdict?: string): ReviewItem['status'] {
  if (verdict === 'approved') return 'pass'
  if (verdict === 'rejected') return 'fail'
  return 'warning'
}

function getVerdictLabel(verdict?: string) {
  if (verdict === 'approved') return '审核通过'
  if (verdict === 'rejected') return '不通过'
  if (verdict === 'manual_review') return '待人工复核'
  return '等待评审结果'
}

function getBidderTag(index: number) {
  return BIDDER_TAGS[index] ?? String(index + 1)
}

function shortenBidderName(name: string) {
  return name
    .replace(/有限公司$/u, '')
    .replace(/股份$/u, '')
    .slice(0, 6)
}

function formatDate(value?: string | null) {
  const raw = value?.trim()
  if (!raw) return '-'
  return raw.slice(0, 10)
}

function formatChineseDate(value?: string | null) {
  const date = formatDate(value)
  if (date === '-') return '-'
  const [year, month, day] = date.split('-')
  return `${year} 年 ${Number(month)} 月 ${Number(day)} 日`
}

function formatScore(score: number) {
  return Number.isInteger(score) ? String(score) : score.toFixed(1)
}

function roundScore(score: number) {
  return Number(score.toFixed(1))
}

function toNumber(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : null
  }
  return null
}

function toText(value: unknown) {
  return typeof value === 'string' ? value.trim() : ''
}

function normalizeDisplayList(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return value.map(toDisplayText).filter(Boolean)
}

function toDisplayText(value: unknown): string {
  if (typeof value === 'string') return value.trim()
  if (isRecord(value)) {
    const desc = String(
      value.description ?? value.message ?? value.reason ?? value.code ?? ''
    ).trim()
    const severity = String(value.severity ?? '').trim()
    if (severity && desc) return `[${severity}] ${desc}`
    if (desc) return desc
    return JSON.stringify(value)
  }
  return value == null ? '' : String(value)
}

function isRecord(value: unknown): value is UnknownRecord {
  return Boolean(value && typeof value === 'object' && !Array.isArray(value))
}
