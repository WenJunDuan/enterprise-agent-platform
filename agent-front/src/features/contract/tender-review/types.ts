import type { TenderCompareStatus } from './api'

export type TenderProjectStatus = 'doing' | 'review' | 'done' | 'archived'
export type TenderScenario =
  | 'bidder_self_check'
  | 'expert_assist'
  | 'post_eval_monitor'
/** Per-file OCR processing status in the two-step upload flow (P3). */
export type OcrFileStatus = 'uploading' | 'running' | 'ready' | 'failed'
export type HistoryTimeRange = 'all' | 'week' | 'month'
export type TenderReviewScreen =
  | 'dashboard'
  | 'create'
  | 'analyzing'
  | 'history'
  | 'analysis'
  | 'report'
export type TenderReviewMode = 'overview' | 'detail' | 'compare'
// 'qual'=资格审查（固定类目，来自 eligibility_checks）。其余为招标文件评标办法的
// 实际类目原名（动态字符串，criteria.items[].category）；'tech'/'comm' 仅作旧数据
// （无 category）的推断兜底键。(string & {}) 保留字面量补全又允许任意标书类目名。
export type ReviewCategory = 'qual' | 'tech' | 'comm' | (string & {})
export type ReviewItemStatus = 'pass' | 'warning' | 'fail'
export type TenderResultVerdict =
  | 'approved'
  | 'rejected'
  | 'manual_review'
  | string
export type TenderScoringStatus =
  | 'scored'
  | 'manual_review'
  | 'rejected'
  | string
export type TenderEligibilityStatus = 'pass' | 'fail' | 'manual' | string
export type TenderScoreCategory = 'business' | 'technical'
export type TenderReviewDimension =
  | 'price'
  | 'business_objective'
  | 'technical_subjective'
export type IssueCategory =
  | 'disqualification_risk'
  | 'eligibility_mismatch'
  | 'score_deduction'
  | 'formality_issue'
  | 'missing_material'
  | 'parameter_deviation'
  | 'pending_verification'
export type IssueStatus = 'risk' | 'warning' | 'pending'

// S10 概要分析 checklist：符合性三态（达到 / 未达到 / 待核验）。
// pending 专收 confirmed:false 疑似 / manual 资格 / 读不清项——绝不当作 unmet（守 R2b + 不可判定不判 0）。
export type ChecklistStatus = 'met' | 'unmet' | 'pending'

export type TenderProject = {
  id: string
  name: string
  code: string
  method: string
  bidderCount: number
  score: string
  date: string
  status: TenderProjectStatus
  stage: string
  progress: number
  riskCount: number
  recommendedBidder: string
}

export type TenderFile = {
  name: string
  size: number
  file?: File
}

export type UploadBidder = {
  id: number
  name: string
  files: TenderFile[]
}

export type ReviewBidder = {
  id: string
  tag: string
  name: string
  short: string
  total: number | null
  rank: number | null
  /** X2：展示名来源——手填（manual）/ AI 识别（agent）/ 无法判断来源（unknown，不展示标注）。 */
  nameSource?: 'manual' | 'agent' | 'unknown'
  /** X2：AI 识别名的出处页锚（`extracted_data.bidder_info.source_refs`），source=agent 时 hover 展示。 */
  nameSourceRefs?: string[]
}

/** 单条扣分/加分命中（R2：逐条展示"哪条命中/扣几分/原文/出处页"）。 */
export type ScoreHit = {
  condition: string
  points: number | null
  quote?: string
  source?: string
}

export type ReviewItem = {
  id: string
  title: string
  desc: string
  loc: number
  aiNote: string
  status?: ReviewItemStatus
  got?: number
  max?: number | null
  /** R2 扣分明细：deduction-mode 项逐条扣分命中（含原文 quote + 出处页）。 */
  deductionHits?: ScoreHit[]
  /** R2 加分明细：additive-mode 项逐条加分命中。 */
  awardHits?: ScoreHit[]
  /** R2：评分方式（deduction/banded/additive/formula/pass_fail/manual）。 */
  scoreMode?: string
  /** R2：manual_review 项的原因（insufficient_evidence/data_conflict 等）。 */
  manualReviewReason?: string
}

export type ReviewCategoryData = {
  key: ReviewCategory
  label: string
  items: ReviewItem[]
}

/** score=null 的待定原因（KD5，与 audit-result.schema.json 的枚举同源）。 */
export type TenderPendingReason =
  | 'cross_bid'
  | 'external_data'
  | 'live_event'
  | 'evidence_unresolved'
  | 'manual_mode'
  | 'non_responsive'

export type TenderScoringItem = {
  id: string
  item: string
  max: number | null
  score: number | null
  status: TenderScoringStatus
  /** score=null 时的待定原因；存量结果没有该字段，展示层回退"待核验"。 */
  pendingReason?: TenderPendingReason
  basis: string
  category: ReviewCategory
  scoreCategory: TenderScoreCategory
  reviewDimension: TenderReviewDimension
  scoreMode?: string
  /** 逐条扣分命中（条件 + 触发原文 quote + 出处页），供扣分明细展示可追溯依据。 */
  deductionHits?: ScoreHit[]
  evidence: TenderScoreEvidence[]
}

export type TenderScoreEvidence = {
  source?: string
  quote?: string
  finding?: string
  conclusion?: string
  condition?: string
  points?: number | null
  /** 页号所属坐标系：converted = Office→PDF 转换稿页号，原文档页号不可用（H2 page-provenance） */
  page_kind?: 'original' | 'converted'
}

export type IssueItem = {
  id: string
  category: IssueCategory
  status: IssueStatus
  title: string
  itemName: string
  basis: string
  quote?: string
  source?: string
  points?: number | null
}

export type TenderEligibilityCheck = {
  id: string
  check: string
  status: TenderEligibilityStatus
  basis: string
  evidence: TenderScoreEvidence[]
}

// S10 概要分析：一条招标要求的符合性判定。**刻意不含 score/points/max**——概要只做二元/三态，
// 编译期即杜绝分数泄漏；程度评分项不进本表（仍在「详细分析」）。
export type ChecklistItem = {
  id: string
  group: string
  requirement: string
  status: ChecklistStatus
  reason: string
  evidence: TenderScoreEvidence[]
}

export type TenderScoreIssue = {
  item: string
  max: number | null
  score: number | null
  status: TenderScoringStatus
  deduction: number | null
  basis: string
  scoreCategory: TenderScoreCategory
  reviewDimension: TenderReviewDimension
}

export type TenderCompareScoreCell = {
  bidderId: string
  bidderName: string
  max: number | null
  score: number | null
  status: TenderScoringStatus
  deduction: number | null
  basis: string
  evidence: TenderScoreEvidence[]
}

export type TenderCompareScoreRow = {
  id: string
  item: string
  max: number | null
  scoreCategory: TenderScoreCategory
  reviewDimension: TenderReviewDimension
  cells: TenderCompareScoreCell[]
}

export type TenderPriceCompareCell = {
  bidderId: string
  bidderName: string
  bidPrice: string
  score: number | null
  status: TenderScoringStatus
  note?: string
}

export type TenderPriceCompareDetail = {
  formula: string
  evidence: TenderScoreEvidence[]
  cells: TenderPriceCompareCell[]
}

export type TenderPolicyRef = {
  id: string
  name?: string
  sourceText?: string
}

export type TenderScoreCategorySummary = {
  category: TenderScoreCategory
  knownMaxTotal: number
  unknownMaxCount: number
  maxTotal: number | null
  score: number
}

export type TenderScoreSummary = {
  knownMaxTotal: number
  unknownMaxCount: number
  maxTotal: number | null
  earnedTotal: number
  deductedTotal: number
  pendingTotal: number
  deductedItems: TenderScoreIssue[]
  rejectedItems: TenderScoreIssue[]
  pendingItems: TenderScoreIssue[]
  categorySummaries: TenderScoreCategorySummary[]
}

// 风险对比"每家一卡"综合视图：一个投标人的符合性 checklist + 评分总览 + 关键风险。
export type BidderCard = {
  id: string
  tag: string
  name: string
  short: string
  total: number | null
  rank: number | null
  score: TenderScoreSummary
  checklist: ChecklistItem[]
  topIssues: IssueItem[]
}

export type DocumentParagraph = {
  loc: number
  label: string
  text: string
}

export type CompareGroup = {
  name: string
  rows: Array<{
    name: string
    max: number
    cells: Array<number | null>
  }>
}

export type ProjectInfo = {
  name: string
  code: string
  method: string
  controlPrice: string
  reviewDate: string
  reportNo: string
}

export type TenderReviewMockData = {
  projects: TenderProject[]
  projectInfo: ProjectInfo
  tenderFiles: TenderFile[]
  uploadBidders: UploadBidder[]
  reviewBidders: ReviewBidder[]
  categories: ReviewCategoryData[]
  paragraphs: DocumentParagraph[]
  compareGroups: CompareGroup[]
  resultVerdict?: TenderResultVerdict
  resultExplanation?: string
  resultReasons?: string[]
  resultPolicyRefs?: TenderPolicyRef[]
  resultEligibilityChecks?: TenderEligibilityCheck[]
  overviewChecklist?: ChecklistItem[]
  issueList?: IssueItem[]
  bidderCards?: BidderCard[]
  scoringItems?: TenderScoringItem[]
  scoreSummary?: TenderScoreSummary
  compareScoreRows?: TenderCompareScoreRow[]
  comparePriceDetail?: TenderPriceCompareDetail
  compareNotice?: {
    /** 横比生命周期（KD2）：none/pending/running/failed/ready。 */
    status: TenderCompareStatus
    /** failed 时的脱敏原因，供"错误可解释"提示。 */
    errorDetail?: string
    stale: boolean
    provisional: boolean
    recommended: string | null
    warnings: string[]
    explanation: string
  }
}

export type DashboardSummary = {
  activeProjects: TenderProject[]
  stats: Array<{
    label: string
    count: number
    tone: 'blue' | 'amber' | 'green' | 'muted'
  }>
  activeCount: number
  reviewCount: number
  completedCount: number
  totalCount: number
}

export type HistoryFilters = {
  query: string
  timeRange: HistoryTimeRange
  now: string
}
