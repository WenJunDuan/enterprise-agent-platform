export type TenderProjectStatus = 'doing' | 'review' | 'done' | 'archived'
export type HistoryTimeRange = 'all' | 'week' | 'month'
export type TenderReviewScreen =
  | 'dashboard'
  | 'create'
  | 'history'
  | 'analysis'
  | 'report'
export type TenderReviewMode = 'detail' | 'compare'
export type ReviewCategory = 'qual' | 'tech' | 'comm'
export type ReviewItemStatus = 'pass' | 'warning' | 'fail'
export type TenderResultVerdict = 'approved' | 'rejected' | 'manual_review' | string
export type TenderScoringStatus =
  | 'scored'
  | 'manual_review'
  | 'rejected'
  | string

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

export type ReviewItem = {
  id: string
  title: string
  desc: string
  loc: number
  aiNote: string
  status?: ReviewItemStatus
  got?: number
  max?: number
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
}

export type TenderScoreIssue = {
  item: string
  max: number
  score: number | null
  status: TenderScoringStatus
  deduction: number | null
  basis: string
}

export type TenderScoreSummary = {
  maxTotal: number
  earnedTotal: number
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
  resultPolicyRefs?: string[]
  scoringItems?: TenderScoringItem[]
  scoreSummary?: TenderScoreSummary
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
