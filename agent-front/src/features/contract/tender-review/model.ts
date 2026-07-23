import type { AuditResult } from '@/features/audit/types'
import type {
  TenderCompareResponse,
  TenderProjectDetailResponse,
  TenderProjectResponse,
  TenderProjectResultSummary,
} from './api'
import type {
  BidderCard,
  ChecklistItem,
  CompareGroup,
  DashboardSummary,
  DocumentParagraph,
  HistoryFilters,
  IssueCategory,
  IssueItem,
  ProjectInfo,
  ReviewBidder,
  ReviewCategory,
  ReviewCategoryData,
  ReviewItem,
  ScoreHit,
  TenderCompareScoreRow,
  TenderEligibilityCheck,
  TenderPolicyRef,
  TenderPriceCompareDetail,
  TenderScoreCategory,
  TenderScoreEvidence,
  TenderScoreIssue,
  TenderScoreSummary,
  TenderScoringItem,
  TenderProject,
  TenderProjectStatus,
  TenderReviewDimension,
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
  resultDetails?: AuditResult[]
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
  const bidderCount = Math.max(
    detail?.bidder_count ?? 0,
    resultSummaries.length
  )
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
    name:
      project.title?.trim() || project.tender_no?.trim() || EMPTY_PROJECT_TITLE,
    code: project.tender_no?.trim() || project.project_id,
    method: project.method?.trim() || compare?.result.method || DEFAULT_METHOD,
    bidderCount,
    score: topScore == null || compareStale ? '-' : formatScore(topScore),
    date: formatDate(project.created_at),
    status,
    stage: getProjectStage(status, completedCount, bidderCount, compareStale),
    progress,
    riskCount: getRiskCount(detail, resultSummaries),
    recommendedBidder: getRecommendedBidder(
      detail,
      compare,
      status,
      compareStale
    ),
  }
}

export function mapTenderProjects(
  projects: TenderProjectResponse[],
  details: TenderProjectDetailResponse[] = [],
  compares: TenderCompareResponse[] = []
) {
  const detailById = new Map(
    details.map((detail) => [detail.project_id, detail])
  )
  const compareById = new Map(
    compares.map((compare) => [compare.project_id, compare])
  )
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
  resultDetails = [],
  compare,
}: BuildTenderReviewDataInput): TenderReviewMockData {
  const mappedProjects = projects.map((item) => mapTenderProject(item))
  const activeProject = project ?? projects[0] ?? null
  const projectData = activeProject
    ? mapTenderProject(activeProject, compare, resultSummaries)
    : null
  const scoringResults = normalizeResultDetails(resultDetails, selectedResult)
  const reviewBidders = buildReviewBidders(
    activeProject,
    resultSummaries,
    selectedResult,
    compare,
    scoringResults
  )
  const scoringItems = buildScoringItems(selectedResult)
  const issueList = buildIssueList(selectedResult)
  const overviewChecklist = buildOverviewChecklist(selectedResult)
  const bidderCards = buildBidderCards(reviewBidders, scoringResults)

  return {
    projects: projectData
      ? [
          projectData,
          ...mappedProjects.filter((item) => item.id !== projectData.id),
        ]
      : mappedProjects,
    projectInfo: buildProjectInfo(activeProject, compare, selectedResult),
    tenderFiles: [],
    uploadBidders: [],
    reviewBidders,
    categories: buildCategories(selectedResult),
    paragraphs: buildParagraphs(selectedResult, scoringItems),
    compareGroups: buildCompareGroups(compare),
    resultVerdict: selectedResult?.verdict,
    resultExplanation:
      selectedResult?.explanation || selectedResult?.summary || '',
    resultReasons: normalizeDisplayList(selectedResult?.reasons),
    resultPolicyRefs: normalizePolicyRefs(selectedResult),
    resultEligibilityChecks: buildEligibilityChecks(selectedResult),
    overviewChecklist,
    bidderCards,
    scoringItems,
    scoreSummary: buildScoreSummary(scoringItems),
    issueList,
    compareScoreRows: buildCompareScoreRows(scoringResults, reviewBidders),
    comparePriceDetail: buildComparePriceDetail(compare, reviewBidders),
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
  if (status === 'done' || status === 'archived' || status === 'review')
    return 100
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
      summary.verdict === 'manual_review' ||
      Boolean(summary.manual_review_reason)
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
    (left, right) =>
      (left.rank ?? Number.MAX_SAFE_INTEGER) -
      (right.rank ?? Number.MAX_SAFE_INTEGER)
  )
  return toNumber(ranked[0]?.total_score)
}

/**
 * X2：散单案卷头（无 project 实体，如 legacy `/tender/evaluate` 直提场景）——
 * 从结论 `extracted_data.tender_info` 取项目名 + 招标编号渲染标题；无 project 且
 * 无 tender_info 时维持原占位（缺省隐藏，不额外展示）。有 project 时区1既有展示不动。
 */
function buildCaseHeaderFromTenderInfo(result?: AuditResult | null) {
  const extracted = result?.extracted_data
  const tenderInfo = isRecord(extracted) && isRecord(extracted.tender_info)
    ? extracted.tender_info
    : null
  return {
    name: toText(tenderInfo?.project_name) || '',
    code: toText(tenderInfo?.tender_no) || '',
  }
}

function buildProjectInfo(
  project?: TenderProjectResponse | TenderProjectDetailResponse | null,
  compare?: TenderCompareResponse | null,
  selectedResult?: AuditResult | null
): ProjectInfo {
  const date =
    compare?.computed_at || project?.updated_at || project?.created_at || ''
  const id = project?.project_id || 'new'
  const caseHeader = project ? null : buildCaseHeaderFromTenderInfo(selectedResult)
  return {
    name:
      project?.title?.trim() ||
      project?.tender_no?.trim() ||
      caseHeader?.name ||
      EMPTY_PROJECT_TITLE,
    code:
      project?.tender_no?.trim() ||
      (project ? project.project_id : caseHeader?.code || '-'),
    method: project?.method?.trim() || compare?.result.method || DEFAULT_METHOD,
    controlPrice: project?.control_price?.trim() || '-',
    reviewDate: formatChineseDate(date),
    reportNo: `TR-${formatDate(date).replaceAll('-', '')}-${id.slice(0, 8)}`,
  }
}

/**
 * X2：按 claim_id 建两条独立展示名索引，供 resolveBidderDisplayName 的优先级链消费。
 *
 * - handNameByClaim：手填名，来自 roster（``project.bids[].bidder_name``，后端已按
 *   手填优先 join ``tender_bid_docs`` 解析——手填非空即用手填，无手填回退 agent 名）。
 * - summaryNameByClaim：results 链新透出的 agent 识别名（``resultSummaries[].bidder_name``，
 *   ``extracted_data.bidder_info.bidder_name`` 拍平值，不含手填 join）。
 *
 * 两条索引口径不同、来源独立，三处调用点（compare / summaries / selectedResult 单投标人）
 * 统一从这两个 Map 取值，避免此前"summaries 合并塌缩成单一 bidder_name 字段"导致的语义混淆。
 */
function buildBidderNameIndexes(
  project: TenderProjectResponse | TenderProjectDetailResponse | null,
  resultSummaries: TenderProjectResultSummary[]
) {
  const detailBids = isTenderProjectDetailOrNull(project) ? project.bids : []
  const handNameByClaim = new Map<string, string>()
  detailBids.forEach((bid) => {
    const name = toText(bid.bidder_name)
    if (bid.claim_id && name) handNameByClaim.set(bid.claim_id, name)
  })
  const summaryNameByClaim = new Map<string, string>()
  resultSummaries.forEach((summary) => {
    const name = toText(summary.bidder_name)
    if (summary.claim_id && name) summaryNameByClaim.set(summary.claim_id, name)
  })
  return { detailBids, handNameByClaim, summaryNameByClaim }
}

function buildReviewBidders(
  project: TenderProjectResponse | TenderProjectDetailResponse | null,
  resultSummaries: TenderProjectResultSummary[],
  selectedResult?: AuditResult | null,
  compare?: TenderCompareResponse | null,
  resultDetails: AuditResult[] = []
): ReviewBidder[] {
  const displayNameByClaim = buildBidderDisplayNameMap(resultDetails)
  const { detailBids, handNameByClaim, summaryNameByClaim } = buildBidderNameIndexes(
    project,
    resultSummaries
  )

  if (compare?.result.bidders.length) {
    const bidders = [...compare.result.bidders]
      .sort(
        (left, right) =>
          (left.rank ?? Number.MAX_SAFE_INTEGER) -
          (right.rank ?? Number.MAX_SAFE_INTEGER)
      )
      .map((bidder, index) => {
        const { name, source, sourceRefs } = resolveBidderDisplayName({
          claimId: bidder.claim_id,
          bidderName: handNameByClaim.get(bidder.claim_id),
          summaryBidderName: summaryNameByClaim.get(bidder.claim_id),
          result: resultDetails.find(
            (result) => toText(result.claim_id) === bidder.claim_id
          ),
          mappedName: displayNameByClaim.get(bidder.claim_id),
          fallback: `投标人 ${index + 1}`,
        })
        return {
          id: bidder.claim_id,
          tag: getBidderTag(index),
          name,
          short: shortenBidderName(name),
          total: toNumber(bidder.total_score) ?? 0,
          rank: bidder.rank ?? index + 1,
          nameSource: source,
          nameSourceRefs: sourceRefs,
        }
      })
    return rankReviewBiddersByScore(bidders)
  }

  const summaries = resultSummaries.length
    ? resultSummaries
    : detailBids.map((bid) => ({
        request_id: bid.request_id,
        claim_id: bid.claim_id,
        bidder_name: bid.bidder_name,
        verdict: bid.verdict,
      }))

  if (summaries.length) {
    const bidders = summaries.map((summary, index) => {
      const result =
        findResultForSummary(summary, resultDetails) ??
        findResultForSummary(summary, selectedResult ? [selectedResult] : [])
      const claimId =
        summary.claim_id ||
        (selectedResult?.claim_id && index === 0 ? selectedResult.claim_id : '')
      const { name, source, sourceRefs } = resolveBidderDisplayName({
        claimId,
        bidderName: claimId ? handNameByClaim.get(claimId) : undefined,
        summaryBidderName: claimId ? summaryNameByClaim.get(claimId) : undefined,
        result,
        mappedName: summary.claim_id
          ? displayNameByClaim.get(summary.claim_id)
          : undefined,
        fallback: `投标人 ${index + 1}`,
      })
      const id = summary.claim_id || summary.request_id || name
      return {
        id,
        tag: getBidderTag(index),
        name,
        short: shortenBidderName(name),
        total: getResultTotalScore(result),
        rank: index + 1,
        nameSource: source,
        nameSourceRefs: sourceRefs,
      }
    })
    return rankReviewBiddersByScore(bidders)
  }

  if (selectedResult?.claim_id) {
    const { name, source, sourceRefs } = resolveBidderDisplayName({
      claimId: selectedResult.claim_id,
      bidderName: handNameByClaim.get(selectedResult.claim_id),
      summaryBidderName: summaryNameByClaim.get(selectedResult.claim_id),
      result: selectedResult,
      fallback: '投标人 1',
    })
    return [
      {
        id: selectedResult.claim_id,
        tag: getBidderTag(0),
        name,
        short: shortenBidderName(name),
        total: getResultTotalScore(selectedResult),
        rank: 1,
        nameSource: source,
        nameSourceRefs: sourceRefs,
      },
    ]
  }

  return []
}

function rankReviewBiddersByScore(bidders: ReviewBidder[]): ReviewBidder[] {
  return bidders
    .map((bidder, index) => ({ bidder, index }))
    .sort((left, right) => {
      const scoreDelta = right.bidder.total - left.bidder.total
      if (Math.abs(scoreDelta) > 0.000001) return scoreDelta
      const rankDelta = left.bidder.rank - right.bidder.rank
      if (rankDelta !== 0) return rankDelta
      return left.index - right.index
    })
    .map(({ bidder }, index) => ({
      ...bidder,
      tag: getBidderTag(index),
      rank: index + 1,
    }))
}

function findResultForSummary(
  summary: TenderProjectResultSummary,
  results: AuditResult[]
) {
  return results.find(
    (result) =>
      (summary.request_id &&
        (toText(result.request_id) === summary.request_id ||
          toText(result.task_id) === summary.request_id)) ||
      (summary.claim_id && toText(result.claim_id) === summary.claim_id)
  )
}

function isTenderProjectDetailOrNull(
  project:
    | TenderProjectResponse
    | TenderProjectDetailResponse
    | null
    | undefined
): project is TenderProjectDetailResponse {
  return Boolean(project && isTenderProjectDetail(project))
}

function buildCategories(result?: AuditResult | null): ReviewCategoryData[] {
  const scoring = buildScoringItems(result)
  const eligibilityItems = buildEligibilityReviewItems(result, 0)
  if (!scoring.length) {
    if (eligibilityItems.length) {
      return [
        {
          key: 'qual',
          label: getCategoryLabel('qual'),
          items: eligibilityItems,
        },
      ]
    }
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

  // R2：原始 scoring 项（与 buildScoringItems 1:1 同序）→ 取逐条扣分/加分明细 + score_mode + 原因。
  const rawScoring = getScoringItems(result)
  const groups = new Map<ReviewCategory, ReviewItem[]>()
  if (eligibilityItems.length) {
    // 资格审查是与技术标/商务标并列的独立审查类目（不计入评分总分），
    // 归到 'qual' 单独成一栏（含自己的小标题），不要混进技术标。
    groups.set('qual', eligibilityItems)
  }
  scoring.forEach((item, index) => {
    const title = item.item || `评分项 ${index + 1}`
    const criteria = findCriteriaItem(result, title)
    const category = item.category
    const raw = rawScoring[index]
    const groupItems = groups.get(category) ?? []
    groupItems.push({
      id: item.id || `score-${index}`,
      title,
      desc:
        toText(criteria?.scoring_rule) ||
        toText(criteria?.source_ref) ||
        '按招标文件评分标准判定。',
      loc: index + eligibilityItems.length,
      aiNote: item.basis || result?.explanation || '该评分项已完成判定。',
      status: getScoringStatus(item.status, item.score),
      got: item.score ?? undefined,
      max: item.max,
      // R2 上下文定位与显示：逐条扣分/加分命中带原文 quote + 出处页。
      deductionHits: parseScoreHits(raw?.deduction_hits),
      awardHits: parseScoreHits(raw?.award_hits),
      scoreMode: toText(raw?.score_mode) || undefined,
      manualReviewReason: toText(raw?.manual_review_reason) || undefined,
    })
    groups.set(category, groupItems)
  })

  // 资格审查恒首位；其余类目按招标文件评分项出现顺序动态展开——
  // criteria 有几类显示几类，缺的不显示，多于三类也全显示（D6：类目即标书实际要素）。
  const orderedKeys: ReviewCategory[] = []
  if (groups.has('qual')) orderedKeys.push('qual')
  scoring.forEach((item) => {
    if (item.category !== 'qual' && !orderedKeys.includes(item.category)) {
      orderedKeys.push(item.category)
    }
  })
  return orderedKeys.map((key) => ({
    key,
    label: getCategoryLabel(key),
    items: groups.get(key) ?? [],
  }))
}

function buildParagraphs(
  result?: AuditResult | null,
  scoringItems: TenderScoringItem[] = buildScoringItems(result)
): DocumentParagraph[] {
  const eligibility = buildEligibilityChecks(result)
  const eligibilityParagraphs = eligibility.map((item, index) => ({
    loc: index,
    label: item.evidence[0]?.source || `${item.check} · 资格审查`,
    text: buildEligibilityParagraphText(item),
  }))
  if (scoringItems.length) {
    return [
      ...eligibilityParagraphs,
      ...scoringItems.map((item, index) => ({
        loc: index + eligibilityParagraphs.length,
        label: item.evidence[0]?.source || `${item.item} · 判定依据`,
        text: buildScoringParagraphText(item),
      })),
    ]
  }
  if (eligibilityParagraphs.length) return eligibilityParagraphs

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

function buildScoringParagraphText(item: TenderScoringItem) {
  const evidenceText = item.evidence
    .map((evidence) =>
      [
        evidence.condition,
        evidence.quote ? `原文：${evidence.quote}` : '',
        evidence.finding,
        evidence.conclusion,
        evidence.source ? `出处：${evidence.source}` : '',
      ]
        .filter(Boolean)
        .join('；')
    )
    .filter(Boolean)
    .join('\n')
  return evidenceText || item.basis || '暂无该评分项的证据明细。'
}

function buildEligibilityParagraphText(item: TenderEligibilityCheck) {
  const evidenceText = item.evidence
    .map((evidence) =>
      [
        evidence.quote ? `原文：${evidence.quote}` : '',
        evidence.finding,
        evidence.conclusion,
        evidence.source ? `出处：${evidence.source}` : '',
      ]
        .filter(Boolean)
        .join('；')
    )
    .filter(Boolean)
    .join('\n')
  return evidenceText || item.basis || '暂无该资格审查项的证据明细。'
}

function buildCompareGroups(
  compare?: TenderCompareResponse | null
): CompareGroup[] {
  const bidders = compare?.result.bidders ?? []
  if (!bidders.length) return []

  const rows = [
    buildCompareRow(
      '价格分',
      bidders.map((bidder) => bidder.price_score)
    ),
    buildCompareRow(
      '其他评审分',
      bidders.map((bidder) => bidder.other_score)
    ),
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

function buildCompareRow(
  name: string,
  values: Array<number | null | undefined>
) {
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
    (isTenderProjectDetailOrNull(project) && project.compare_stale) ||
    compare?.stale
  )
  const result = compare?.result
  return {
    stale,
    provisional: Boolean(result?.provisional),
    recommended: result?.recommended ?? null,
    warnings: result?.warnings ?? [],
    explanation:
      result?.explanation ||
      (stale ? '投标人有变化，请重新横比后再展示横比结果。' : ''),
  }
}

function buildComparePriceDetail(
  compare: TenderCompareResponse | null | undefined,
  bidders: ReviewBidder[]
): TenderPriceCompareDetail | undefined {
  if (!compare) return undefined
  const compareBidders = compare.result.bidders
  if (!compareBidders.length || bidders.length < 2) return undefined
  const bidderByClaim = new Map(
    compareBidders.map((bidder) => [bidder.claim_id, bidder])
  )
  const cells: TenderPriceCompareDetail['cells'] = []
  bidders.forEach((bidder, index) => {
    const raw = bidderByClaim.get(bidder.id) ?? compareBidders[index]
    if (!raw) return
    cells.push({
      bidderId: bidder.id,
      bidderName: bidder.name,
      bidPrice: formatBidPrice(raw.bid_price),
      score: toNumber(raw.price_score),
      status: raw.status,
      note: raw.note || undefined,
    })
  })

  if (!cells.length) return undefined
  return {
    formula: buildPriceFormulaText(compare),
    evidence: buildComparePriceEvidence(compare),
    cells,
  }
}

function buildPriceFormulaText(compare: TenderCompareResponse) {
  const evidenceText = buildComparePriceEvidence(compare)
    .map((item) => [item.finding, item.conclusion].filter(Boolean).join('；'))
    .find(Boolean)
  return (
    evidenceText ||
    compare.result.explanation ||
    '价格分由横比结果按招标文件价格公式统一计算；前端仅展示 compare 侧返回结果。'
  )
}

function buildComparePriceEvidence(compare: TenderCompareResponse): TenderScoreEvidence[] {
  const evidence = compare.result.evidence_chain ?? []
  return evidence
    .filter((item) =>
      `${item.source ?? ''} ${item.finding ?? ''} ${item.conclusion ?? ''}`.match(
        /价格|报价|评标价|基准价|公式/u
      )
    )
    .map((item) => ({
      source: item.source?.trim(),
      finding: item.finding?.trim(),
      conclusion: item.conclusion?.trim(),
    }))
    .filter(
      (item) => item.source || item.finding || item.conclusion
    )
}

function getScoringItems(result?: AuditResult | null): UnknownRecord[] {
  const scoring = result?.extracted_data?.scoring
  return Array.isArray(scoring) ? scoring.filter(isRecord) : []
}

function getEligibilityCheckRecords(
  result?: AuditResult | null
): UnknownRecord[] {
  const checks = result?.extracted_data?.eligibility_checks
  return Array.isArray(checks) ? checks.filter(isRecord) : []
}

function buildEligibilityChecks(
  result?: AuditResult | null
): TenderEligibilityCheck[] {
  return getEligibilityCheckRecords(result).map((item, index) => {
    const check = toText(item.check) || `资格审查 ${index + 1}`
    const evidence = buildEligibilityEvidence(item)
    return {
      id: toText(item.rule_id) || toText(item.id) || `eligibility-${index}`,
      check,
      status: toText(item.status) || 'manual',
      basis:
        toText(item.basis) ||
        result?.explanation ||
        '按招标文件资格审查要求核验。',
      evidence,
    }
  })
}

function buildEligibilityReviewItems(
  result?: AuditResult | null,
  startLoc = 0
): ReviewItem[] {
  return buildEligibilityChecks(result).map((item, index) => ({
    id: item.id || `eligibility-${index}`,
    title: `资格审查：${item.check}`,
    desc: '投标文件进入详细评分前的资格审查项；不计入评分总分。',
    loc: startLoc + index,
    aiNote: item.basis,
    status: getEligibilityStatus(item.status),
  }))
}

export function buildIssueList(result?: AuditResult | null): IssueItem[] {
  const issues: IssueItem[] = []
  const pushIssue = (issue: Omit<IssueItem, 'id'>) => {
    issues.push({
      ...issue,
      id: `issue-${issues.length}`,
    })
  }

  getDisqualificationHitRecords(result).forEach((hit, index) => {
    const evidence = getIssueEvidence(hit)
    const text = collectIssueText(hit)
    const pending = isUnconfirmedDisqualification(hit) || isPendingSignal(text)
    pushIssue({
      category: pending ? 'pending_verification' : 'disqualification_risk',
      status: pending ? 'pending' : 'risk',
      title: pending ? '否决风险待核验' : '废标风险',
      itemName:
        toText(hit.item) ||
        toText(hit.condition) ||
        toText(hit.check) ||
        toText(hit.finding) ||
        toText(hit.rule_id) ||
        `否决条款 ${index + 1}`,
      basis:
        toText(hit.finding) ||
        toText(hit.basis) ||
        toText(hit.reason) ||
        '命中招标文件否决性条款。',
      quote: evidence.quote,
      source: evidence.source,
    })
  })

  getEligibilityCheckRecords(result).forEach((item, index) => {
    const status = toText(item.status)
    const text = collectIssueText(item)
    const pending =
      status === 'manual' ||
      status === 'manual_review' ||
      status === 'pending' ||
      isPendingSignal(text)
    const failed =
      status === 'fail' || status === 'failed' || status === 'rejected'
    if (!pending && !failed) return

    const evidence = getIssueEvidence(item)
    pushIssue({
      category: pending ? 'pending_verification' : 'eligibility_mismatch',
      status: pending ? 'pending' : 'risk',
      title: pending ? '资格项待核验' : '资格不符',
      itemName: toText(item.check) || `资格审查 ${index + 1}`,
      basis:
        toText(item.basis) ||
        toText(item.finding) ||
        (pending
          ? '该资格项需要人工核验。'
          : '该资格项未满足招标文件要求。'),
      quote: evidence.quote,
      source: evidence.source,
    })
  })

  getScoringItems(result).forEach((item, index) => {
    const title = toText(item.item) || `评分项 ${index + 1}`
    const max = toNumber(item.max) ?? 0
    const score = toNumber(item.score)
    const status = toText(item.status)
    const basis =
      toText(item.basis) ||
      toText(item.manual_review_reason) ||
      '按招标文件评分标准判定。'
    const text = collectIssueText(item, [title, basis])
    const pending =
      status === 'manual_review' ||
      score == null ||
      isPendingSignal(text)
    const rejected = status === 'rejected' || status === 'failed'
    const deductionHits = parseScoreHits(item.deduction_hits) ?? []

    if (pending) {
      const evidence = getIssueEvidence(item)
      pushIssue({
        category: 'pending_verification',
        status: 'pending',
        title: '待核验清单',
        itemName: title,
        basis,
        quote: evidence.quote,
        source: evidence.source,
      })
      return
    }

    if (deductionHits.length > 0) {
      deductionHits.forEach((hit) => {
        const hitText = [title, basis, hit.condition, hit.quote, hit.source]
          .filter(Boolean)
          .join(' ')
        const category = classifyIssueCategory(hitText)
        pushIssue({
          category,
          status: category === 'score_deduction' ? 'warning' : 'risk',
          title: getIssueTitle(category),
          itemName: title,
          basis: hit.condition || basis,
          quote: hit.quote,
          source: hit.source,
          points: hit.points,
        })
      })
      return
    }

    if (rejected || (score != null && max > 0 && score < max)) {
      const evidence = getIssueEvidence(item)
      const category = classifyIssueCategory(text)
      pushIssue({
        category,
        status: category === 'score_deduction' ? 'warning' : 'risk',
        title: getIssueTitle(category),
        itemName: title,
        basis,
        quote: evidence.quote,
        source: evidence.source,
        points: score == null ? null : roundScore(Math.max(0, max - score)),
      })
    }
  })

  return issues
}

// S10 概要分析：只识别真正二元的评分项——pass_fail 硬性响应，或 status=rejected 的硬否决/必交材料缺失。
const BINARY_SCORE_MODES = new Set(['pass_fail'])
// "程度"评分项（档次/扣减/加分/公式）——概要 checklist 一律排除（即便被标 rejected），留给「详细分析」。
const DEGREE_SCORE_MODES = new Set(['banded', 'deduction', 'additive', 'formula'])

/** 把一条记录的出处（文件+页+quote）收成 checklist 用的 evidence 数组；与 issueList 共用同一提取口径。 */
function checklistEvidence(record: UnknownRecord): TenderScoreEvidence[] {
  const { source, quote } = getIssueEvidence(record)
  if (!source && !quote) return []
  return [{ source, quote }]
}

// 概要"不展示评分"须防到文本层：模型的 basis 常含"扣5分/得10分/0分/得分为0/总分80/(5/10)/
// 排名第N"等，直接塞进 reason 会在标称无分数的概要页泄漏分值。这里覆盖"数字在前(N分)"与
// "数字在后(得分为N)"两序，抹掉分值表述，只留定性理由（守不可违反原则 #1，不展示评分）。
function stripScoreMentions(text: string): string {
  return text
    // (5/10)、（5 / 10 分）等占比/得分括注
    .replace(/[（(]\s*\d+(?:\.\d+)?\s*[/／]\s*\d+(?:\.\d+)?\s*分?\s*[)）]/gu, '')
    // 分数关键词 + (为/是/等于/:) + 数字（数字在后）：得分为0 / 总分80 / 分值：5
    .replace(
      /(?:满分|总分|得分|分值|评分|计分|积分|分数)\s*(?:为|是|达|等于|计|=|：|:)?\s*\d+(?:\.\d+)?\s*分?/gu,
      ''
    )
    // 数字 + 分（数字在前）：得5分 / 扣10分 / 0分（"分母/分子/分项"等非分值不误伤）
    .replace(/(?:得|扣|加|计|共|减|判|给|获|再|拿)?\s*\d+(?:\.\d+)?\s*分(?![母子项数值制])/gu, '')
    // 排名第 N / 第 N 名
    .replace(/排名\s*第?\s*\d+|第\s*\d+\s*名/gu, '')
    .replace(/\s{2,}/gu, ' ')
    // 清理抹除后遗留的孤立/首尾标点（如"投标函未签字，。"→"投标函未签字"）
    .replace(/[，,、；;]\s*(?=[，,、；;。])/gu, '')
    .replace(/^[，,、；;。/／\s]+|[，,、；;、/／\s]+$/gu, '')
    .trim()
}

/** 概要理由：抹掉分数表述后若为空，退回定性兜底（不留空行）。 */
function checklistReason(text: string, fallback: string): string {
  const cleaned = stripScoreMentions(text)
  return cleaned || fallback
}

/**
 * 概要分析 checklist：把每条招标要求判成 met/unmet/pending（符合性导向），
 * 与 buildIssueList（问题导向）互补且**共享同一套源 getter + pending 谓词**，
 * 保证两视图口径一致（issueList 里 pending 的项，此处必 pending，绝不 ✗）。
 *
 * 只纳入二元达成项：资格审查 / 否决命中 / pass_fail 硬性响应 / rejected 必交材料。
 * 档次/扣减/加分/公式等"程度"项一律排除（塞进二元 checklist 是范畴错误，仍在「详细分析」展示）。
 * 概要不含任何分数——ChecklistItem 类型层面即不带 score/points/max。
 */
export function buildOverviewChecklist(
  result?: AuditResult | null
): ChecklistItem[] {
  const items: ChecklistItem[] = []
  const push = (row: Omit<ChecklistItem, 'id'>) => {
    items.push({ ...row, id: `checklist-${items.length}` })
  }

  // 1) 资格审查：pass→met，fail/failed/rejected→unmet，manual/pending/读不清→pending。
  getEligibilityCheckRecords(result).forEach((item, index) => {
    const status = toText(item.status)
    const text = collectIssueText(item)
    const pending =
      status === 'manual' ||
      status === 'manual_review' ||
      status === 'pending' ||
      isPendingSignal(text)
    const unmet =
      !pending &&
      (status === 'fail' || status === 'failed' || status === 'rejected')
    // 仅明确 pass 记 met；status 缺失 / 未知 / 枚举漂移一律降 pending，绝不当"达到"（守 R2b + 不可判定不判 0）。
    const met = !pending && (status === 'pass' || status === 'passed')
    push({
      group: '资格审查',
      requirement: toText(item.check) || `资格审查 ${index + 1}`,
      status: pending ? 'pending' : unmet ? 'unmet' : met ? 'met' : 'pending',
      reason: checklistReason(
        toText(item.basis) || toText(item.finding),
        '按招标文件资格审查要求核验。'
      ),
      evidence: checklistEvidence(item),
    })
  })

  // 2) 否决条款：命中即"未达到"；confirmed:false 疑似 / 读不清 → pending（绝不打叉，守 R2b）。
  //    只拿到"命中"记录、没有全量条款清单，故不合成 met 行。
  getDisqualificationHitRecords(result).forEach((hit, index) => {
    const text = collectIssueText(hit)
    const pending = isUnconfirmedDisqualification(hit) || isPendingSignal(text)
    push({
      group: '否决条款',
      requirement:
        toText(hit.item) ||
        toText(hit.condition) ||
        toText(hit.check) ||
        toText(hit.finding) ||
        toText(hit.rule_id) ||
        `否决条款 ${index + 1}`,
      status: pending ? 'pending' : 'unmet',
      reason: checklistReason(
        toText(hit.finding) || toText(hit.basis) || toText(hit.reason),
        '命中招标文件否决性条款。'
      ),
      evidence: checklistEvidence(hit),
    })
  })

  // 3) 硬性响应/必交材料：只纳入 pass_fail 或 status=rejected 的二元项，程度项排除。
  //    score≥max→met，rejected/失败/score<max→unmet，manual_review/score==null/读不清→pending。
  getScoringItems(result).forEach((item, index) => {
    const title = toText(item.item) || `硬性响应 ${index + 1}`
    // score_mode 与 buildScoringItems 同口径：raw 缺省时回退 criteria，避免漏填 mode 绕过程度项排除。
    const scoreMode =
      toText(item.score_mode) || toText(findCriteriaItem(result, title)?.score_mode)
    const status = toText(item.status)
    const isRejected = status === 'rejected' || status === 'failed'
    // 只收 pass_fail，或"非程度项"的 rejected（必交材料缺失/硬否决）；程度项即便 rejected 也排除。
    const isBinary =
      BINARY_SCORE_MODES.has(scoreMode) ||
      (isRejected && !DEGREE_SCORE_MODES.has(scoreMode))
    if (!isBinary) return

    const max = toNumber(item.max) ?? 0
    const score = toNumber(item.score)
    const rawBasis = toText(item.basis) || toText(item.manual_review_reason)
    const text = collectIssueText(item, [title, rawBasis])
    // manual / manual_review / 读不清信号 → 待核验（守 R2b）。score==null 仅在非 rejected 时算待核验：
    // rejected(必交材料缺失/硬否决)是确定的未达到,不能因缺 score 字段被误判成待核验(codex r2 P1)。
    const pending =
      status === 'manual' ||
      status === 'manual_review' ||
      isPendingSignal(text) ||
      (score == null && !isRejected)
    // pass_fail 满足=满分；max 缺失(=0)时退而据 score>0 判达标，避免漏填 max 把达标项误判未达到。
    const met =
      !pending &&
      !isRejected &&
      score != null &&
      (max > 0 ? score >= max : score > 0)
    push({
      group: '硬性响应',
      requirement: title,
      status: pending ? 'pending' : met ? 'met' : 'unmet',
      reason: checklistReason(rawBasis, '按招标文件硬性响应要求判定。'),
      evidence: checklistEvidence(item),
    })
  })

  return items
}

export function getAdvisoryLabel(issueList: IssueItem[]) {
  if (issueList.some((issue) => issue.category === 'disqualification_risk')) {
    return '存在废标风险'
  }
  if (issueList.length > 0) return '较多待确认项'
  return '暂未发现明显问题'
}

function getDisqualificationHitRecords(
  result?: AuditResult | null
): UnknownRecord[] {
  const hits = result?.extracted_data?.disqualification_hits
  if (!Array.isArray(hits)) return []
  return hits.filter(isRecord).filter(hasMeaningfulIssueRecord)
}

function hasMeaningfulIssueRecord(record: UnknownRecord) {
  const text = collectIssueText(record)
  if (!text) return false
  return !/^(无|暂无|没有|none|n\/a|null)$/iu.test(text)
}

function isUnconfirmedDisqualification(hit: UnknownRecord) {
  if (!Object.prototype.hasOwnProperty.call(hit, 'confirmed')) return false
  return hit.confirmed !== true
}

function classifyIssueCategory(text: string): IssueCategory {
  if (isPendingSignal(text)) return 'pending_verification'
  if (/投标函|签字|盖章|签章|印章|密封|装订|格式|骑缝章/u.test(text)) {
    return 'formality_issue'
  }
  if (/未提供|未提交|未附|缺失|遗漏|材料不全|证明材料不全/u.test(text)) {
    return 'missing_material'
  }
  if (/偏离|正偏离|负偏离|参数|技术响应|响应偏差/u.test(text)) {
    return 'parameter_deviation'
  }
  return 'score_deduction'
}

function getIssueTitle(category: IssueCategory) {
  const titles: Record<IssueCategory, string> = {
    disqualification_risk: '废标风险',
    eligibility_mismatch: '资格不符',
    score_deduction: '扣分点',
    formality_issue: '形式问题',
    missing_material: '材料缺失',
    parameter_deviation: '参数正负偏离',
    pending_verification: '待核验清单',
  }
  return titles[category]
}

function isPendingSignal(text: string) {
  return /疑似|待核验|需核验|待人工|人工核验|需复核|未核实|无法确认|不能确认|证据不足|读不清|看不清|不清晰|不可读|无法识别|未能识别|未还原|未清晰还原|模糊|低置信|出处未核实|insufficient_evidence|data_conflict|unclear|unreadable|unresolved|manual_review|low_clarity/iu.test(
    text
  )
}

function getIssueEvidence(record: UnknownRecord) {
  const evidence = isRecord(record.evidence) ? record.evidence : null
  return {
    quote:
      toText(evidence?.quote) ||
      toText(record.quote) ||
      toText(record.source_text) ||
      undefined,
    source:
      toText(evidence?.source) ||
      toText(record.source) ||
      toText(record.source_ref) ||
      undefined,
  }
}

function collectIssueText(record: UnknownRecord, extra: string[] = []) {
  const parts = [
    ...extra,
    toText(record.rule_id),
    toText(record.id),
    toText(record.item),
    toText(record.check),
    toText(record.title),
    toText(record.condition),
    toText(record.finding),
    toText(record.basis),
    toText(record.reason),
    toText(record.message),
    toText(record.manual_review_reason),
    toText(record.status),
  ]
  const evidence = isRecord(record.evidence) ? record.evidence : null
  if (evidence) {
    parts.push(
      toText(evidence.quote),
      toText(evidence.source),
      toText(evidence.finding),
      toText(evidence.conclusion)
    )
  }
  const selectedBand = isRecord(record.selected_band) ? record.selected_band : null
  if (selectedBand) {
    parts.push(toText(selectedBand.level), toText(selectedBand.reason))
  }
  return parts.filter(Boolean).join(' ')
}

function buildEligibilityEvidence(raw: UnknownRecord): TenderScoreEvidence[] {
  const evidence: TenderScoreEvidence[] = []
  const addEvidence = (item: TenderScoreEvidence) => {
    const normalized = {
      source: item.source?.trim(),
      quote: item.quote?.trim(),
      finding: item.finding?.trim(),
      conclusion: item.conclusion?.trim(),
      condition: item.condition?.trim(),
      points: item.points ?? null,
    }
    if (
      !normalized.source &&
      !normalized.quote &&
      !normalized.finding &&
      !normalized.conclusion &&
      !normalized.condition
    ) {
      return
    }
    evidence.push(normalized)
  }

  const directEvidence = isRecord(raw.evidence) ? raw.evidence : null
  if (directEvidence) {
    addEvidence({
      source: toText(directEvidence.source),
      quote: toText(directEvidence.quote),
      finding: toText(directEvidence.finding),
      conclusion: toText(directEvidence.conclusion),
    })
  }
  addEvidence({
    finding: toText(raw.basis),
    conclusion: eligibilityStatusLabel(toText(raw.status)),
  })
  return evidence
}

/**
 * R2: parse scoring[].deduction_hits / award_hits into displayable ScoreHit[].
 *
 * Raw hit shape (tender-evaluate command): {condition, points_each, deducted|awarded,
 * evidence:{source, quote}}. Tolerant of missing/odd fields (best-effort display).
 */
function parseScoreHits(raw: unknown): ScoreHit[] | undefined {
  if (!Array.isArray(raw)) return undefined
  const hits = raw.filter(isRecord).map((hit) => {
    const evidence = isRecord(hit.evidence) ? hit.evidence : undefined
    return {
      condition: toText(hit.condition) || '—',
      points:
        toNumber(hit.deducted) ??
        toNumber(hit.awarded) ??
        toNumber(hit.points_each),
      quote: toText(evidence?.quote) || toText(hit.quote) || undefined,
      source: toText(evidence?.source) || toText(hit.source) || undefined,
    }
  })
  return hits.length > 0 ? hits : undefined
}

function buildScoringItems(result?: AuditResult | null): TenderScoringItem[] {
  return getScoringItems(result).map((item, index) => {
    const title = toText(item.item) || `评分项 ${index + 1}`
    const criteria = findCriteriaItem(result, title)
    const max = toNumber(item.max) ?? 0
    const score = toNumber(item.score)
    const status =
      toText(item.status) || (score == null ? 'manual_review' : 'scored')
    const scoreCategory = inferScoreCategory(
      title,
      toText(item.category) || toText(criteria?.category)
    )
    const reviewDimension = deriveReviewDimension(item, criteria)
    return {
      id: `score-${index}`,
      item: title,
      max,
      score,
      status,
      basis: toText(item.basis) || result?.explanation || '暂无判定依据。',
      // 类目优先用招标文件标注的实际类目原名（criteria/scoring.category），动态分栏；
      // 旧数据无 category 时回退关键词推断的 tech/comm，保证不崩。
      category:
        normalizeDocCategory(toText(item.category) || toText(criteria?.category)) ||
        inferReviewCategory(title, scoreCategory),
      scoreCategory,
      reviewDimension,
      scoreMode:
        toText(item.score_mode) || toText(criteria?.score_mode) || undefined,
      // 逐条扣分命中(条件 + 触发原文 quote + 出处页)——供详细分析「扣分明细」显示可追溯依据。
      deductionHits: parseScoreHits(item.deduction_hits),
      evidence: buildScoringEvidence(item, result, title),
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
    // rejected 优先于 score==null：必交材料缺失判 0 可能不带 score 字段，应归失分项(该项判0)而非待核验。
    if (item.status === 'rejected') {
      rejectedItems.push(issue)
    } else if (item.status === 'manual_review' || item.score == null) {
      pendingItems.push({ ...issue, deduction: null })
    } else if (item.status === 'scored' && item.score < item.max) {
      deductedItems.push(issue)
    }
  })
  const deductedTotal = roundScore(
    [...deductedItems, ...rejectedItems].reduce(
      (sum, item) => sum + getIssueLostScore(item),
      0
    )
  )
  const pendingTotal = roundScore(
    pendingItems.reduce((sum, item) => sum + item.max, 0)
  )

  return {
    maxTotal,
    earnedTotal,
    deductedTotal,
    pendingTotal,
    deductedItems,
    rejectedItems,
    pendingItems,
  }
}

/**
 * 风险对比"每家一卡"：为每个投标人派生 符合性 checklist + 评分总览 + 关键风险。
 * 按 claim_id 匹配 resultDetails 里各家完整结果;无匹配则给空卡(不崩)。复用 S10/S5 既有派生,不另造口径。
 */
export function buildBidderCards(
  reviewBidders: ReviewBidder[],
  resultDetails: AuditResult[] = []
): BidderCard[] {
  return reviewBidders.map((bidder) => {
    // bidder.id 可能是 claim_id / request_id / task_id（buildReviewBidders 的兜底口径），
    // 与 normalizeResultDetails 同款多键匹配，避免 request_id-only 结果匹配不上出空卡（codex P1-1）。
    const result =
      resultDetails.find(
        (item) =>
          toText(item.claim_id) === bidder.id ||
          toText(item.request_id) === bidder.id ||
          toText(item.task_id) === bidder.id
      ) ?? null
    return {
      ...bidder,
      score: buildScoreSummary(buildScoringItems(result)),
      checklist: buildOverviewChecklist(result),
      topIssues: buildIssueList(result),
    }
  })
}

function toScoreIssue(item: TenderScoringItem): TenderScoreIssue {
  const deduction = getItemDeduction(item)
  return {
    item: item.item,
    max: item.max,
    score: item.score,
    status: item.status,
    deduction,
    basis: item.basis,
    scoreCategory: item.scoreCategory,
    reviewDimension: item.reviewDimension,
  }
}

function getItemDeduction(item: TenderScoringItem): number | null {
  if (item.status === 'rejected' && item.score == null) return item.max
  if (item.score == null) return null
  return roundScore(Math.max(0, item.max - item.score))
}

function getIssueLostScore(item: TenderScoreIssue): number {
  if (item.deduction != null) return item.deduction
  if (item.status === 'rejected') return item.max
  return 0
}

function findCriteriaItem(
  result: AuditResult | null | undefined,
  title: string
) {
  const criteria = result?.extracted_data?.criteria
  const items = Array.isArray(criteria)
    ? criteria
    : isRecord(criteria) && Array.isArray(criteria.items)
      ? criteria.items
      : []
  return items.filter(isRecord).find((item) => toText(item.item) === title)
}

function normalizeResultDetails(
  resultDetails: AuditResult[],
  selectedResult?: AuditResult | null
) {
  const results = [...resultDetails, selectedResult].filter(
    (item): item is AuditResult => Boolean(item)
  )
  const byKey = new Map<string, AuditResult>()
  results.forEach((result, index) => {
    const key =
      toText(result.claim_id) ||
      toText(result.request_id) ||
      toText(result.task_id) ||
      `result-${index}`
    if (!byKey.has(key)) byKey.set(key, result)
  })
  return [...byKey.values()]
}

function buildBidderDisplayNameMap(results: AuditResult[]) {
  const map = new Map<string, string>()
  results.forEach((result) => {
    const claimId = toText(result.claim_id)
    if (!claimId || map.has(claimId)) return
    const name = extractBidderCompanyName(result)
    if (name) map.set(claimId, name)
  })
  return map
}

type ResolvedBidderName = {
  name: string
  /** 来源标注：manual=用户手填、agent=AI 识别、unknown=兜底（claim_id/占位，不展示标注）。 */
  source: 'manual' | 'agent' | 'unknown'
  /** AI 识别名的出处页锚（仅 source=agent 且能定位到 bidder_info 时有值）。 */
  sourceRefs?: string[]
}

/**
 * 展示名优先级链（X2：手填优先于 agent 猜测，倒正此前 agent 名压手填名的现状）。
 *
 * 顺序：手填（roster/summary 的 bidder_name，来自用户上传表单或文档层）→ results 链
 * 新透出的 agent 识别名（summaryBidderName）→ 结论 extracted_data 派生名
 * （extractBidderCompanyName，首选 bidder_info.bidder_name）→ 历史 claim 映射名
 * （mappedName）→ claimId → fallback。返回值带来源标注，供界面区分"手填/AI 识别"。
 */
function resolveBidderDisplayName({
  claimId,
  bidderName,
  summaryBidderName,
  result,
  mappedName,
  fallback,
}: {
  claimId?: string | null
  bidderName?: string | null
  summaryBidderName?: string | null
  result?: AuditResult | null
  mappedName?: string
  fallback: string
}): ResolvedBidderName {
  const candidates: Array<{
    value?: string | null
    source: ResolvedBidderName['source']
  }> = [
    { value: bidderName, source: 'manual' },
    { value: summaryBidderName, source: 'agent' },
    { value: extractBidderCompanyName(result), source: 'agent' },
    { value: mappedName, source: 'agent' },
    { value: claimId, source: 'unknown' },
  ]
  for (const candidate of candidates) {
    const text = toText(candidate.value)
    if (text && !looksLikeCreditCode(text)) {
      return {
        name: text,
        source: candidate.source,
        sourceRefs:
          candidate.source === 'agent' ? extractBidderSourceRefs(result) : undefined,
      }
    }
  }
  return { name: fallback, source: 'unknown' }
}

function extractBidderCompanyName(result?: AuditResult | null) {
  const extracted = result?.extracted_data
  if (!isRecord(extracted)) return ''

  const bidderInfo = isRecord(extracted.bidder_info) ? extracted.bidder_info : null
  // 历史兼容次选：旧数据/其它猜测键（本字段引入前留存的结论仍需正确展示名称）。
  const bidder = isRecord(extracted.bidder) ? extracted.bidder : null
  const directCandidates = [
    bidderInfo?.bidder_name,
    bidder?.name,
    bidder?.company_name,
    bidder?.bidder_name,
    bidder?.enterprise_name,
    extracted.bidder_name,
    extracted.company_name,
    extracted.enterprise_name,
    extracted.supplier_name,
    extracted.vendor_name,
  ]

  return (
    directCandidates
      .map((candidate) => toText(candidate))
      .find((candidate) => candidate && !looksLikeCreditCode(candidate)) || ''
  )
}

/** AI 识别名的出处页锚（`extracted_data.bidder_info.source_refs`），供 hover 展示，识别不到则空。 */
function extractBidderSourceRefs(result?: AuditResult | null): string[] | undefined {
  const extracted = result?.extracted_data
  if (!isRecord(extracted)) return undefined
  const bidderInfo = isRecord(extracted.bidder_info) ? extracted.bidder_info : null
  const refs = bidderInfo?.source_refs
  if (!Array.isArray(refs)) return undefined
  const texts = refs.map((ref) => toText(ref)).filter((ref): ref is string => Boolean(ref))
  return texts.length > 0 ? texts : undefined
}

function looksLikeCreditCode(value: string) {
  const normalized = value.replace(/\s+/g, '').toUpperCase()
  return /^[0-9A-Z]{18}$/u.test(normalized) || /^\d{15,18}$/u.test(normalized)
}

function buildCompareScoreRows(
  results: AuditResult[],
  bidders: ReviewBidder[]
): TenderCompareScoreRow[] {
  if (bidders.length < 2 || results.length === 0) return []

  const resultByClaim = new Map(
    results
      .map((result) => [toText(result.claim_id), result] as const)
      .filter(([claimId]) => claimId)
  )
  const orderedResults = bidders.map(
    (bidder, index) =>
      resultByClaim.get(bidder.id) ??
      resultByClaim.get(bidder.name) ??
      results[index] ??
      null
  )
  const itemOrder: string[] = []
  const itemsByResult = orderedResults.map((result) => {
    const items = result ? buildScoringItems(result) : []
    const map = new Map<string, TenderScoringItem>()
    items.forEach((item) => {
      if (!itemOrder.includes(item.item)) itemOrder.push(item.item)
      map.set(item.item, item)
    })
    return map
  })

  return itemOrder
    .map((itemName, rowIndex) => {
      const firstItem = itemsByResult
        .map((items) => items.get(itemName))
        .find((item): item is TenderScoringItem => Boolean(item))
      const max = firstItem?.max ?? 0
      const scoreCategory =
        firstItem?.scoreCategory ?? inferScoreCategory(itemName, '')
      const reviewDimension =
        firstItem?.reviewDimension ??
        deriveReviewDimension({ item: itemName }, null)

      return {
        id: `compare-score-${rowIndex}`,
        item: itemName,
        max,
        scoreCategory,
        reviewDimension,
        cells: bidders.map((bidder, bidderIndex) => {
          const item = itemsByResult[bidderIndex]?.get(itemName)
          const score = item?.score ?? null
          return {
            bidderId: bidder.id,
            bidderName: bidder.name,
            max: item?.max ?? max,
            score,
            status: item?.status ?? 'manual_review',
            deduction:
              score == null
                ? null
                : roundScore(Math.max(0, (item?.max ?? max) - score)),
            basis: item?.basis ?? '该投标人暂无该评分项明细。',
            evidence: item?.evidence ?? [],
          }
        }),
      }
    })
    .filter((row) =>
      row.cells.some((cell) => cell.score != null || cell.basis.trim())
    )
}

function buildScoringEvidence(
  raw: UnknownRecord,
  result: AuditResult | null | undefined,
  itemTitle: string
): TenderScoreEvidence[] {
  const evidence: TenderScoreEvidence[] = []
  const addEvidence = (item: TenderScoreEvidence) => {
    const normalized = {
      source: item.source?.trim(),
      quote: item.quote?.trim(),
      finding: item.finding?.trim(),
      conclusion: item.conclusion?.trim(),
      condition: item.condition?.trim(),
      points: item.points ?? null,
    }
    if (
      !normalized.source &&
      !normalized.quote &&
      !normalized.finding &&
      !normalized.conclusion &&
      !normalized.condition
    ) {
      return
    }
    const key = JSON.stringify(normalized)
    if (!evidence.some((existing) => JSON.stringify(existing) === key)) {
      evidence.push(normalized)
    }
  }

  for (const hit of [
    ...(parseScoreHits(raw.deduction_hits) ?? []),
    ...(parseScoreHits(raw.award_hits) ?? []),
  ]) {
    addEvidence({
      source: hit.source,
      quote: hit.quote,
      condition: hit.condition,
      points: hit.points,
    })
  }

  const selectedBand = isRecord(raw.selected_band) ? raw.selected_band : null
  if (selectedBand) {
    addEvidence({
      condition: toText(selectedBand.level),
      finding: toText(selectedBand.reason),
      points: toNumber(selectedBand.points),
    })
  }

  const directEvidence = isRecord(raw.evidence) ? raw.evidence : null
  if (directEvidence) {
    addEvidence({
      source: toText(directEvidence.source),
      quote: toText(directEvidence.quote),
      finding: toText(directEvidence.finding),
      conclusion: toText(directEvidence.conclusion),
    })
  }

  if (evidence.length > 0) return evidence

  const chain = result?.evidence_chain ?? []
  const relevant = chain.filter((item) =>
    `${item.source ?? ''} ${item.finding ?? ''} ${item.conclusion ?? ''}`.includes(
      itemTitle
    )
  )
  const fallback = relevant.length ? relevant : chain.slice(0, 2)
  fallback.forEach((item) =>
    addEvidence({
      source: item.source,
      finding: item.finding,
      conclusion: item.conclusion,
    })
  )
  return evidence
}

function getResultTotalScore(result?: AuditResult | null) {
  return roundScore(
    getScoringItems(result).reduce(
      (sum, item) => sum + (toNumber(item.score) ?? 0),
      0
    )
  )
}

export function deriveReviewDimension(
  scoringItem: UnknownRecord,
  criteriaItem?: UnknownRecord | null
): TenderReviewDimension {
  const tag = normalizeDimensionSignal(
    toText(scoringItem.tag) || toText(criteriaItem?.tag)
  )
  const scoreMode = normalizeDimensionSignal(
    toText(scoringItem.score_mode) || toText(criteriaItem?.score_mode)
  )
  if (tag === 'requires_cross_bid_comparison' || scoreMode === 'formula') {
    return 'price'
  }

  const evaluatorType = normalizeDimensionSignal(
    toText(scoringItem.evaluator_type) || toText(criteriaItem?.evaluator_type)
  )
  if (evaluatorType === 'subjective' || evaluatorType === 'mixed') {
    return 'technical_subjective'
  }

  if (!scoreMode && !evaluatorType && isLegacyPriceItemName(scoringItem, criteriaItem)) {
    return 'price'
  }

  return 'business_objective'
}

function normalizeDimensionSignal(value: string) {
  return value.trim().toLowerCase()
}

function isLegacyPriceItemName(
  scoringItem: UnknownRecord,
  criteriaItem?: UnknownRecord | null
) {
  const name = `${toText(scoringItem.item)} ${toText(criteriaItem?.item)}`
  return /价格|报价|投标报价|最高限价/u.test(name)
}

function inferReviewCategory(
  title: string,
  scoreCategory: TenderScoreCategory
): ReviewCategory {
  if (scoreCategory === 'technical') return 'tech'
  if (title.includes('资格审查') || title.includes('符合性审查')) return 'qual'
  return 'comm'
}

function inferScoreCategory(
  title: string,
  rawCategory?: string
): TenderScoreCategory {
  const category = rawCategory?.trim() ?? ''
  if (
    category.includes('技术') ||
    category.toLowerCase().includes('technical')
  ) {
    return 'technical'
  }
  if (
    category.includes('商务') ||
    category.includes('报价') ||
    category.includes('价格') ||
    category.toLowerCase().includes('business') ||
    category.toLowerCase().includes('commercial')
  ) {
    return 'business'
  }
  const normalized = title
  if (
    normalized.includes('技术') ||
    normalized.includes('方案') ||
    normalized.includes('参数') ||
    normalized.includes('实施') ||
    normalized.includes('培训') ||
    normalized.includes('售后') ||
    normalized.includes('服务') ||
    normalized.includes('质量') ||
    normalized.includes('进度') ||
    normalized.toLowerCase().includes('technical')
  ) {
    return 'technical'
  }
  if (
    normalized.includes('报价') ||
    normalized.includes('价格') ||
    normalized.includes('商务') ||
    normalized.includes('财务') ||
    normalized.includes('信誉') ||
    normalized.includes('信用') ||
    normalized.includes('业绩') ||
    normalized.includes('企业') ||
    normalized.includes('资质') ||
    normalized.includes('资格') ||
    normalized.includes('负责人') ||
    normalized.includes('项目经理') ||
    normalized.toLowerCase().includes('business') ||
    normalized.toLowerCase().includes('commercial')
  ) {
    return 'business'
  }
  return 'technical'
}

function getCategoryLabel(category: ReviewCategory) {
  if (category === 'qual') return '资格审查'
  if (category === 'tech') return '技术标'
  if (category === 'comm') return '商务标'
  // 动态类目：招标文件标注的类目原名直接作小标题。
  return category
}

const _ELIGIBILITY_CATEGORY = /资格(性|预)?审查|资格评审|符合性审查|响应性(审查|评审)/

/**
 * 归一招标文件标注的类目名：资格审查类合并到固定 'qual' 列（避免与
 * eligibility_checks 列重复），其余返回去空白后的原名（空串→落回推断兜底）。
 */
function normalizeDocCategory(raw: string): ReviewCategory | '' {
  const value = raw.trim()
  if (!value) return ''
  if (_ELIGIBILITY_CATEGORY.test(value)) return 'qual'
  return value
}

function getScoringStatus(
  status: string,
  score: number | null
): ReviewItem['status'] {
  if (status === 'manual_review') return 'warning'
  if (status === 'rejected' || status === 'failed') return 'fail'
  if (score == null) return 'warning'
  return 'pass'
}

function getEligibilityStatus(status: string): ReviewItem['status'] {
  if (status === 'pass' || status === 'passed') return 'pass'
  if (status === 'fail' || status === 'failed' || status === 'rejected')
    return 'fail'
  return 'warning'
}

function eligibilityStatusLabel(status: string) {
  if (status === 'pass' || status === 'passed') return '资格审查通过'
  if (status === 'fail' || status === 'failed' || status === 'rejected') {
    return '资格审查不通过'
  }
  return '资格审查需人工核验'
}

function getVerdictStatus(verdict?: string): ReviewItem['status'] {
  if (verdict === 'approved') return 'pass'
  if (verdict === 'rejected') return 'fail'
  return 'warning'
}

function getVerdictLabel(verdict?: string) {
  if (verdict === 'approved') return '审核通过'
  if (verdict === 'rejected') return '不通过'
  if (verdict === 'manual_review') return '需复核'
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

function formatBidPrice(value: { amount?: number | null; currency?: string | null } | null | undefined) {
  const amount = toNumber(value?.amount)
  if (amount == null) return '待补充'
  const currency = value?.currency?.trim() || '元'
  return `${amount.toLocaleString('zh-CN')} ${currency}`
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

function normalizePolicyRefs(result?: AuditResult | null): TenderPolicyRef[] {
  const refs = Array.isArray(result?.policy_refs_detail)
    ? result?.policy_refs_detail
    : result?.policy_refs
  if (!Array.isArray(refs)) return []
  return refs
    .map((ref) => {
      if (typeof ref === 'string') {
        const id = ref.trim()
        return id ? { id } : null
      }
      if (!isRecord(ref)) return null
      const id =
        toText(ref.rule_id) ||
        toText(ref.id) ||
        toText(ref.code) ||
        toText(ref.name)
      const name = toText(ref.name)
      const sourceText =
        toText(ref.source_text) ||
        toText(ref.sourceText) ||
        toText(ref.description) ||
        toText(ref.message)
      if (!id && !name && !sourceText) return null
      return {
        id: id || name || sourceText.slice(0, 24),
        name: name || undefined,
        sourceText: sourceText || undefined,
      }
    })
    .filter((ref): ref is TenderPolicyRef => Boolean(ref))
}

function toDisplayText(value: unknown): string {
  if (typeof value === 'string') return value.trim()
  if (isRecord(value)) {
    const desc = String(
      value.description ??
        value.message ??
        value.reason ??
        value.name ??
        value.source_text ??
        value.rule_id ??
        value.code ??
        ''
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
