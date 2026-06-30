import { useEffect, useRef } from 'react'
import { AlertTriangle, Brain, CheckCircle2, FileText, MapPin, Printer } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { getAdvisoryLabel } from '../model'
import type {
  IssueCategory,
  IssueItem,
  ReviewCategory,
  ReviewItem,
  ReviewBidder,
  ScoreHit,
  TenderReviewMockData,
  TenderReviewMode,
} from '../types'

type AnalysisWorkbenchViewProps = {
  data: TenderReviewMockData
  mode: TenderReviewMode
  category: ReviewCategory
  selectedBidderId: string
  activeItemId: string
  onMode: (mode: TenderReviewMode) => void
  onCategory: (category: ReviewCategory) => void
  onBidder: (bidderId: string) => void
  onActiveItem: (itemId: string) => void
  onHistory: () => void
  onReport: () => void
}

export function AnalysisWorkbenchView(props: AnalysisWorkbenchViewProps) {
  const viewLabel = props.mode === 'compare' ? '风险对比' : '辅助评审'

  return (
    <div className='overflow-hidden rounded-xl border bg-background'>
      <div className='border-b bg-card/80 px-6 py-4 backdrop-blur'>
        <div className='flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between'>
          <div className='min-w-0'>
            <div className='flex items-center gap-2 text-xs font-medium text-muted-foreground'>
              <button
                type='button'
                className='hover:text-primary'
                onClick={props.onHistory}
              >
                评审列表
              </button>
              <span>›</span>
              <span className='text-foreground'>{viewLabel}</span>
            </div>
            <h2 className='mt-1 truncate text-xl font-semibold'>
              {props.data.projectInfo.name}
            </h2>
          </div>
          <div className='flex shrink-0 items-center gap-2'>
            <div className='flex rounded-lg bg-muted p-1'>
              <ModeButton
                active={props.mode === 'detail'}
                onClick={() => props.onMode('detail')}
              >
                详细分析
              </ModeButton>
              <ModeButton
                active={props.mode === 'compare'}
                onClick={() => props.onMode('compare')}
              >
                风险对比
              </ModeButton>
            </div>
            <Button size='sm' onClick={() => props.onReport()}>
              <Printer className='size-4' />
              查看报告
            </Button>
          </div>
        </div>
        {props.mode === 'detail' ? <BidderTabs {...props} /> : null}
      </div>

      {props.mode === 'detail' ? (
        <DetailWorkbench {...props} />
      ) : (
        <CompareWorkbench data={props.data} />
      )}
    </div>
  )
}

function ModeButton({
  active,
  onClick,
  children,
}: {
  active: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      type='button'
      className={cn(
        'rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
        active ? 'bg-background shadow-sm' : 'text-muted-foreground'
      )}
      onClick={onClick}
    >
      {children}
    </button>
  )
}

function BidderTabs({
  data,
  selectedBidderId,
  onBidder,
}: AnalysisWorkbenchViewProps) {
  return (
    <div className='mt-3 flex gap-2 overflow-x-auto'>
      {data.reviewBidders.map((bidder) => {
        const active = bidder.id === selectedBidderId
        return (
          <button
            key={bidder.id}
            type='button'
            className={cn(
              'flex shrink-0 items-center gap-2 rounded-lg border px-3 py-1.5 text-sm font-medium',
              active
                ? 'border-border bg-background text-foreground'
                : 'border-transparent text-muted-foreground hover:bg-muted'
            )}
            onClick={() => onBidder(bidder.id)}
          >
            <span
              className={cn(
                'flex size-5 items-center justify-center rounded text-xs',
                active
                  ? 'bg-primary/10 text-primary'
                  : 'bg-muted text-muted-foreground'
              )}
            >
              {bidder.tag}
            </span>
            {bidder.short}
            <span
              className={cn(
                'text-xs font-semibold text-muted-foreground',
                active && 'text-primary'
              )}
            >
              {active ? '当前查看' : '切换查看'}
            </span>
          </button>
        )
      })}
    </div>
  )
}

function DetailWorkbench(props: AnalysisWorkbenchViewProps) {
  const selectedBidder =
    props.data.reviewBidders.find(
      (bidder) => bidder.id === props.selectedBidderId
    ) ??
    props.data.reviewBidders[0] ??
    emptyBidder
  const activeCategory =
    props.data.categories.find((category) => category.key === props.category) ??
    props.data.categories[0]
  const activeItem = activeCategory.items.find(
    (item) => item.id === props.activeItemId
  )
  const activeLoc = activeItem?.loc ?? -1
  const issueList = props.data.issueList ?? []
  const activeEvidenceRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (activeLoc < 0) return
    activeEvidenceRef.current?.scrollIntoView({
      behavior: 'smooth',
      block: 'center',
    })
  }, [activeLoc])

  return (
    <div className='grid min-h-[620px] xl:h-[calc(100vh-220px)] xl:min-h-[620px] xl:grid-cols-[288px_minmax(0,1.2fr)_minmax(340px,1fr)]'>
      <aside className='min-h-0 overflow-y-auto border-b bg-muted/20 p-5 xl:border-r xl:border-b-0'>
        <div className='rounded-xl border bg-card p-5 shadow-sm'>
          <div className='flex items-center gap-2 text-sm font-semibold'>
            <AlertTriangle className='size-4 text-amber-600' />
            风险提示
          </div>
          <div className='mt-3 text-2xl font-semibold tracking-tight text-foreground'>
            {getAdvisoryLabel(issueList)}
          </div>
          <div className='mt-3 grid grid-cols-2 gap-2 text-xs'>
            {getIssueCategoryCounts(issueList).map((item) => (
              <div key={item.category} className='rounded-lg bg-muted/50 p-2'>
                <div className='text-muted-foreground'>{item.label}</div>
                <div className='mt-1 font-semibold'>{item.count} 项</div>
              </div>
            ))}
          </div>
        </div>

        <IssueListPanel issues={issueList} className='mt-5' />

        <div className='mt-5 rounded-xl border bg-card p-4'>
          <div className='mb-2 flex items-center gap-2 text-sm font-semibold'>
            <Brain className='size-4 text-primary' />
            辅助小结
          </div>
          <p className='text-sm leading-6 text-muted-foreground'>
            {getAdvisorySummary(issueList, selectedBidder.name)}
          </p>
        </div>
      </aside>

      <section className='flex min-h-0 min-w-0 flex-col border-b xl:border-r xl:border-b-0'>
        <div className='flex shrink-0 gap-1 overflow-x-auto px-5 pt-4'>
          {props.data.categories.map((category) => (
            <button
              key={category.key}
              type='button'
              className={cn(
                'flex shrink-0 items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium',
                category.key === props.category
                  ? 'bg-primary/10 text-primary'
                  : 'text-muted-foreground hover:bg-muted'
              )}
              onClick={() => props.onCategory(category.key)}
            >
              {category.label}
              <span className='rounded-full bg-muted px-2 py-0.5 text-xs'>
                {category.items.length}
              </span>
            </button>
          ))}
        </div>
        <div className='min-h-0 flex-1 space-y-3 overflow-y-auto p-5'>
          {activeCategory.items.map((item, index) => (
            <ReviewItemCard
              key={item.id}
              item={item}
              index={index + 1}
              active={item.id === props.activeItemId}
              onClick={() => props.onActiveItem(item.id)}
            />
          ))}
        </div>
      </section>

      <section className='flex min-h-0 min-w-0 flex-col bg-muted/20'>
        <div className='shrink-0 border-b px-5 py-4'>
          <div className='flex items-center gap-2 text-sm font-semibold'>
            <FileText className='size-4 text-violet-600' />
            证据与底稿
          </div>
          <div className='mt-1 text-xs text-muted-foreground'>
            {selectedBidder.name} · 点击左侧要点自动定位依据
          </div>
        </div>
        <div className='min-h-0 flex-1 space-y-3 overflow-y-auto p-5'>
          {props.data.paragraphs.map((paragraph) => {
            const active = paragraph.loc === activeLoc
            return (
              <div
                key={paragraph.loc}
                ref={active ? activeEvidenceRef : undefined}
                className={cn(
                'rounded-lg border-l-4 bg-card p-4 text-sm shadow-sm',
                active
                    ? 'border-l-amber-500 bg-amber-50 dark:bg-amber-950/30'
                    : 'border-l-transparent'
                )}
              >
                <div
                  className={cn(
                    'mb-1 text-xs font-bold',
                    active ? 'text-amber-700 dark:text-amber-300' : 'text-muted-foreground'
                  )}
                >
                  {paragraph.label}
                </div>
                <div className='leading-6 text-muted-foreground'>
                  {paragraph.text}
                </div>
              </div>
            )
          })}
        </div>
      </section>
    </div>
  )
}

function ReviewItemCard({
  item,
  index,
  active,
  onClick,
}: {
  item: ReviewItem
  index: number
  active: boolean
  onClick: () => void
}) {
  const badge = getItemBadge(item)

  return (
    <button
      type='button'
      className={cn(
        'flex w-full gap-3 rounded-xl border p-4 text-left transition-colors',
        active ? 'border-primary/40 bg-primary/5 shadow-sm' : 'bg-card hover:bg-muted/30'
      )}
      onClick={onClick}
    >
      <span
        className={cn(
        'flex size-7 shrink-0 items-center justify-center rounded-lg text-xs font-semibold',
          active ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground'
        )}
      >
        {index}
      </span>
      <span className='min-w-0 flex-1'>
        <span className='flex items-start justify-between gap-3'>
          <span className='font-medium'>{item.title}</span>
          <span
            className={cn(
              'shrink-0 rounded-full px-3 py-1 text-xs font-semibold',
              badge.className
            )}
          >
            {badge.label}
          </span>
        </span>
        <span className='mt-1 block text-sm leading-6 text-muted-foreground'>
          {item.desc}
        </span>
        {item.manualReviewReason ? (
          <span className='mt-2 inline-flex w-fit items-center gap-1 rounded bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-700 dark:bg-amber-950/40 dark:text-amber-300'>
            {manualReviewReasonLabel(item.manualReviewReason)}
          </span>
        ) : null}
        {/* R2 扣分明细：逐条命中（扣分 + 原文 quote + 出处页），治"扣分项准确 + 上下文定位与显示" */}
        {item.deductionHits?.length ? (
          <span className='mt-2 block space-y-1.5'>
            <span className='block text-xs font-semibold text-muted-foreground'>
              问题依据（{item.deductionHits.length} 条）
            </span>
            {item.deductionHits.map((hit, hitIndex) => (
              <ScoreHitRow key={hitIndex} hit={hit} sign='deduct' />
            ))}
          </span>
        ) : null}
        {item.awardHits?.length ? (
          <span className='mt-2 block space-y-1.5'>
            <span className='block text-xs font-semibold text-muted-foreground'>
              响应依据（{item.awardHits.length} 条）
            </span>
            {item.awardHits.map((hit, hitIndex) => (
              <ScoreHitRow key={hitIndex} hit={hit} sign='award' />
            ))}
          </span>
        ) : null}
        <span className='mt-2 flex gap-2 rounded-lg bg-primary/5 p-2 text-xs leading-5 text-primary'>
          <Brain className='mt-0.5 size-3 shrink-0' />
          <span>
            <b>审核依据：</b>
            {item.aiNote}
          </span>
        </span>
        <span className='mt-2 flex items-center gap-1 text-xs font-medium text-primary'>
          <MapPin className='size-3' />
          定位原文 · {item.loc + 1}
        </span>
      </span>
    </button>
  )
}

/** R2：单条命中明细行 — 命中条件 + 投标原文 quote + 出处页（上下文定位）。 */
function ScoreHitRow({ hit, sign }: { hit: ScoreHit; sign: 'deduct' | 'award' }) {
  return (
    <span className='block rounded-lg bg-muted/40 px-2.5 py-1.5 text-xs'>
      <span className='flex items-start gap-2'>
        <b
          className={cn(
            'shrink-0',
            sign === 'deduct'
              ? 'text-red-600 dark:text-red-300'
              : 'text-emerald-600 dark:text-emerald-300'
          )}
        >
          {sign === 'deduct' ? '问题' : '依据'}
        </b>
        <span className='text-foreground'>{hit.condition}</span>
      </span>
      {hit.quote ? (
        <span className='mt-1 block border-l-2 border-l-amber-300 pl-2 leading-5 text-muted-foreground italic'>
          「{hit.quote}」
        </span>
      ) : null}
      {hit.source ? (
        <span className='mt-1 flex items-center gap-1 font-medium text-primary'>
          <MapPin className='size-3 shrink-0' />
          {hit.source}
        </span>
      ) : null}
    </span>
  )
}

const manualReviewReasonLabels: Record<string, string> = {
  insufficient_evidence: '证据不足',
  data_conflict: '数据冲突',
  rule_gap: '规则缺口',
  missing_approval: '缺审批',
  budget_exceeded: '超预算',
  invoice_invalid: '发票无效',
  pre_approval_mismatch: '预审不符',
}

function manualReviewReasonLabel(reason: string): string {
  return manualReviewReasonLabels[reason] ?? reason
}

function getItemBadge(item: ReviewItem) {
  if (item.status === 'warning') {
    return {
      label: '待核查',
      className: 'bg-amber-100 text-amber-700 dark:bg-amber-950/50 dark:text-amber-300',
    }
  }
  if (item.status === 'fail') {
    return {
      label: '存在问题',
      className: 'bg-red-100 text-red-700 dark:bg-red-950/50 dark:text-red-300',
    }
  }
  if (item.status === 'pass') {
    return {
      label: '已覆盖',
      className: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300',
    }
  }

  return {
    label: '已记录',
    className: 'bg-blue-100 text-blue-700 dark:bg-blue-950/50 dark:text-blue-300',
  }
}

function CompareWorkbench({ data }: { data: TenderReviewMockData }) {
  const hasMultipleBidders = data.reviewBidders.length >= 2

  return (
    <div className='space-y-5 bg-muted/20 p-6'>
      <div className='text-sm text-muted-foreground'>
        {data.reviewBidders.length} 家投标方 · {data.projectInfo.method} ·
        当前仅展示辅助评审问题口径，结论性评分数据留作内部监督场景。
      </div>
      <div className='grid gap-4 md:grid-cols-2 xl:grid-cols-4'>
        {data.reviewBidders.map((bidder) => (
            <div
              key={bidder.id}
              className='relative overflow-hidden rounded-xl border bg-card p-4 shadow-sm'
            >
              <div className='absolute inset-x-0 top-0 h-1 bg-primary/50' />
              <div className='flex items-center justify-between'>
                <Badge className='bg-muted text-muted-foreground hover:bg-muted'>
                  辅助评审
                </Badge>
                <span className='flex size-6 items-center justify-center rounded-md bg-muted text-xs font-semibold'>
                  {bidder.tag}
                </span>
              </div>
              <div className='mt-3 line-clamp-2 min-h-10 text-sm font-semibold'>
                {bidder.name}
              </div>
              <div className='mt-3 flex items-center gap-2 text-xs text-muted-foreground'>
                <CheckCircle2 className='size-3.5 text-primary' />
                分值与排序已隐藏
              </div>
            </div>
        ))}
      </div>
      <CompareTable data={data} />
      <IssueListPanel issues={data.issueList ?? []} />
      {hasMultipleBidders ? (
        <div className='rounded-xl border border-dashed bg-card p-4 text-sm text-muted-foreground'>
          分项评分明细已转为问题清单口径；需要监督复核时再查看内部评分数据。
        </div>
      ) : (
        <div className='rounded-xl border border-dashed bg-card p-4 text-sm text-muted-foreground'>
          需至少 2 家投标人后展示横向评分；单家项目不会生成横比结果。
        </div>
      )}
    </div>
  )
}

function CompareTable({ data }: { data: TenderReviewMockData }) {
  const rows = data.compareGroups.flatMap((group) =>
    group.rows.map((row) => ({ ...row, group: group.name }))
  )
  if (rows.length === 0) {
    return (
      <div className='rounded-xl border border-dashed bg-card p-4 text-sm text-muted-foreground'>
        暂无横向评审要素。
      </div>
    )
  }

  const bidderCount = Math.max(data.reviewBidders.length, 1)
  const gridStyle = {
    gridTemplateColumns: `minmax(260px,1.6fr) repeat(${bidderCount}, minmax(140px,1fr))`,
  }
  const minWidth = 260 + bidderCount * 160

  return (
    <div className='overflow-x-auto rounded-xl border bg-card shadow-sm'>
      <div style={{ minWidth }}>
        <div
          className='grid border-b bg-muted/40 text-xs font-semibold text-muted-foreground'
          style={gridStyle}
        >
          <div className='px-5 py-3'>评审项</div>
          {data.reviewBidders.map((bidder) => (
            <div key={bidder.id} className='px-3 py-3 text-center'>
              {bidder.short}
            </div>
          ))}
        </div>
        {rows.map((row) => (
            <div
              key={`${row.group}-${row.name}`}
              className='grid border-b last:border-b-0'
              style={gridStyle}
            >
              <div className='px-5 py-3'>
                <div className='text-sm font-medium'>{row.name}</div>
                <div className='text-xs text-muted-foreground'>
                  {row.group} · 分值已隐藏
                </div>
              </div>
              {row.cells.map((_value, index) => (
                <div
                  key={`${row.name}-${data.reviewBidders[index]?.id}`}
                  className='flex items-center justify-center px-3 py-3'
                >
                  <span className='rounded-full bg-muted px-2.5 py-1 text-xs font-medium text-muted-foreground'>
                    需结合问题清单复核
                  </span>
                </div>
              ))}
            </div>
        ))}
      </div>
    </div>
  )
}

function IssueListPanel({
  issues,
  className,
}: {
  issues: IssueItem[]
  className?: string
}) {
  if (issues.length === 0) {
    return (
      <div className={cn('rounded-xl border bg-card p-4', className)}>
        <div className='flex items-center gap-2 text-sm font-semibold'>
          <CheckCircle2 className='size-4 text-emerald-600' />
          问题清单
        </div>
        <p className='mt-2 text-sm leading-6 text-muted-foreground'>
          暂未发现明显问题；仍建议专家结合原文进行必要复核。
        </p>
      </div>
    )
  }

  const groups = issueCategoryOrder
    .map((category) => ({
      category,
      meta: issueCategoryMeta[category],
      items: issues.filter((issue) => issue.category === category),
    }))
    .filter((group) => group.items.length > 0)

  return (
    <div className={cn('rounded-xl border bg-card p-4', className)}>
      <div className='flex items-center gap-2 text-sm font-semibold'>
        <AlertTriangle className='size-4 text-amber-600' />
        问题清单
      </div>
      <div className='mt-3 space-y-4'>
        {groups.map((group) => (
          <div key={group.category}>
            <div className='mb-2 flex items-center justify-between gap-2'>
              <div className='text-xs font-semibold text-muted-foreground'>
                {group.meta.label}
              </div>
              <span className='rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground'>
                {group.items.length} 项
              </span>
            </div>
            <div className='space-y-2'>
              {group.items.map((issue) => (
                <div key={issue.id} className='rounded-lg bg-muted/40 p-3 text-xs'>
                  <div className='flex flex-wrap items-center gap-2'>
                    <Badge className={group.meta.badgeClassName}>
                      {group.meta.label}
                    </Badge>
                    <span className='font-semibold text-foreground'>
                      {issue.itemName}
                    </span>
                  </div>
                  <div className='mt-2 leading-5 text-muted-foreground'>
                    {issue.basis}
                  </div>
                  {issue.quote ? (
                    <div className='mt-2 border-l-2 border-l-amber-300 pl-2 leading-5 text-muted-foreground italic'>
                      「{issue.quote}」
                    </div>
                  ) : null}
                  {issue.source ? (
                    <div className='mt-2 flex items-center gap-1 font-medium text-primary'>
                      <MapPin className='size-3 shrink-0' />
                      {issue.source}
                    </div>
                  ) : null}
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

const issueCategoryOrder: IssueCategory[] = [
  'disqualification_risk',
  'eligibility_mismatch',
  'score_deduction',
  'formality_issue',
  'missing_material',
  'parameter_deviation',
  'pending_verification',
]

const issueCategoryMeta: Record<
  IssueCategory,
  { label: string; badgeClassName: string }
> = {
  disqualification_risk: {
    label: '废标风险',
    badgeClassName: 'bg-red-100 text-red-700 dark:bg-red-950/50 dark:text-red-300',
  },
  eligibility_mismatch: {
    label: '资格不符',
    badgeClassName: 'bg-red-100 text-red-700 dark:bg-red-950/50 dark:text-red-300',
  },
  score_deduction: {
    label: '扣分点',
    badgeClassName:
      'bg-orange-100 text-orange-700 dark:bg-orange-950/50 dark:text-orange-300',
  },
  formality_issue: {
    label: '形式问题',
    badgeClassName:
      'bg-yellow-100 text-yellow-700 dark:bg-yellow-950/50 dark:text-yellow-300',
  },
  missing_material: {
    label: '材料缺失',
    badgeClassName: 'bg-amber-100 text-amber-700 dark:bg-amber-950/50 dark:text-amber-300',
  },
  parameter_deviation: {
    label: '参数正负偏离',
    badgeClassName: 'bg-blue-100 text-blue-700 dark:bg-blue-950/50 dark:text-blue-300',
  },
  pending_verification: {
    label: '待核验清单',
    badgeClassName: 'bg-muted text-muted-foreground',
  },
}

function getIssueCategoryCounts(issues: IssueItem[]) {
  return issueCategoryOrder.map((category) => ({
    category,
    label: issueCategoryMeta[category].label,
    count: issues.filter((issue) => issue.category === category).length,
  }))
}

function getAdvisorySummary(issues: IssueItem[], bidderName: string) {
  if (issues.length === 0) {
    return `${bidderName} 暂未发现明显问题；专家仍可结合原文进行抽查复核。`
  }
  const riskCount = issues.filter((issue) => issue.status === 'risk').length
  const pendingCount = issues.filter((issue) => issue.status === 'pending').length
  return `${bidderName} 当前形成 ${issues.length} 项需关注内容，其中 ${riskCount} 项高风险、${pendingCount} 项待核验；请以问题清单和出处页为复核入口。`
}

const emptyBidder: ReviewBidder = {
  id: '-',
  tag: '-',
  name: '暂无投标人',
  short: '暂无',
  total: 0,
  rank: 0,
}
