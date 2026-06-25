export type TenderProjectStatus = 'doing' | 'review' | 'done' | 'archived'
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
export type TenderReviewMode = 'detail' | 'compare'
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
  total: number
  rank: number
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
  max?: number
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

export type TenderScoringItem = {
  id: string
  item: string
  max: number
  score: number | null
  status: TenderScoringStatus
  basis: string
  category: ReviewCategory
  scoreCategory: TenderScoreCategory
  reviewDimension: TenderReviewDimension
  scoreMode?: string
  evidence: TenderScoreEvidence[]
}

export type TenderScoreEvidence = {
  source?: string
  quote?: string
  finding?: string
  conclusion?: string
  condition?: string
  points?: number | null
}

export type TenderEligibilityCheck = {
  id: string
  check: string
  status: TenderEligibilityStatus
  basis: string
  evidence: TenderScoreEvidence[]
}

export type TenderScoreIssue = {
  item: string
  max: number
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
  max: number
  score: number | null
  status: TenderScoringStatus
  deduction: number | null
  basis: string
  evidence: TenderScoreEvidence[]
}

export type TenderCompareScoreRow = {
  id: string
  item: string
  max: number
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

export type TenderScoreSummary = {
  maxTotal: number
  earnedTotal: number
  deductedTotal: number
  pendingTotal: number
  deductedItems: TenderScoreIssue[]
  rejectedItems: TenderScoreIssue[]
  pendingItems: TenderScoreIssue[]
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
    cells: number[]
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
  scoringItems?: TenderScoringItem[]
  scoreSummary?: TenderScoreSummary
  compareScoreRows?: TenderCompareScoreRow[]
  comparePriceDetail?: TenderPriceCompareDetail
  compareNotice?: {
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
