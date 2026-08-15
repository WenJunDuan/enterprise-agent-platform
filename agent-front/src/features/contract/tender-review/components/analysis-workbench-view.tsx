import { useEffect, useRef } from 'react'
import { Brain, FileText, MapPin, Printer } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import type {
  ProjectInfo,
  ReviewCategory,
  ReviewItem,
  ReviewBidder,
  ScoreHit,
  TenderReviewMockData,
  TenderReviewMode,
} from '../types'
import type { TenderCompareStatus } from '../api'
import { formatScore } from '../format'
import { OverviewChecklistView } from './overview-checklist-view'
import { ScoringOverviewPanel } from './scoring-overview-panel'
import { BidderCompareCards } from './bidder-compare-cards'

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
  /** KD2：横比生命周期 + 重新横比入口（失败/过期时用户可自助重跑）。 */
  compareRetrying?: boolean
  onRetryCompare?: () => void
}

const viewLabels: Record<TenderReviewMode, string> = {
  overview: '概要分析',
  detail: '辅助评审',
  compare: '投标横评',
}

const emptyProjectInfo: ProjectInfo = {
  name: '—',
  code: '—',
  method: '—',
  controlPrice: '—',
  reviewDate: '—',
  reportNo: '—',
}

export function AnalysisWorkbenchView(props: AnalysisWorkbenchViewProps) {
  const viewLabel = viewLabels[props.mode] ?? '辅助评审'
  const projectInfo = props.data.projectInfo ?? emptyProjectInfo

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
              {projectInfo.name ?? '—'}
            </h2>
          </div>
          <div className='flex shrink-0 items-center gap-2'>
            <div className='flex rounded-lg bg-muted p-1'>
              <ModeButton
                active={props.mode === 'overview'}
                onClick={() => props.onMode('overview')}
              >
                概要分析
              </ModeButton>
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
                投标横评
              </ModeButton>
            </div>
            <Button size='sm' onClick={() => props.onReport()}>
              <Printer className='size-4' />
              查看报告
            </Button>
          </div>
        </div>
        {props.mode !== 'compare' ? <BidderTabs {...props} /> : null}
      </div>

      {props.mode === 'overview' ? (
        <OverviewChecklistView
          checklist={props.data.overviewChecklist ?? []}
          bidderName={selectedBidderName(props)}
        />
      ) : props.mode === 'detail' ? (
        <DetailWorkbench {...props} />
      ) : (
        <CompareWorkbench
          data={props.data}
          retrying={props.compareRetrying}
          onRetry={props.onRetryCompare}
        />
      )}
    </div>
  )
}

/** 概要/详细共用：取当前选中投标人名（无则兜底首个 / 占位）。 */
function selectedBidderName(props: AnalysisWorkbenchViewProps): string {
  const bidders = props.data.reviewBidders ?? []
  const bidder =
    bidders.find(
      (item) => item.id === props.selectedBidderId
    ) ?? bidders[0]
  return bidder?.name ?? '当前投标人'
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
  const bidders = data.reviewBidders ?? []

  return (
    <div className='mt-3 flex gap-2 overflow-x-auto'>
      {bidders.map((bidder) => {
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
              {bidder.tag ?? '—'}
            </span>
            {bidder.short ?? '—'}
            <BidderNameSourceBadge
              source={bidder.nameSource}
              sourceRefs={bidder.nameSourceRefs}
            />
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

/**
 * X2：投标单位名称旁的来源标注——手填（用户上传时填写）/ AI 识别（agent 从投标文件识别）。
 * AI 识别时 hover 展示出处页锚（`source_refs`），便于人工回查；来源不明（unknown，兜底
 * claim_id/占位名）时不展示标注，避免误导。
 */
function BidderNameSourceBadge({
  source,
  sourceRefs,
}: {
  source?: 'manual' | 'agent' | 'unknown'
  sourceRefs?: string[]
}) {
  if (source !== 'manual' && source !== 'agent') return null
  const label = source === 'manual' ? '手填' : 'AI 识别'
  const title =
    source === 'agent' && sourceRefs?.length
      ? `出处：${sourceRefs.join('；')}`
      : undefined
  return (
    <span
      className='rounded bg-muted px-1 py-0.5 text-[10px] font-normal text-muted-foreground'
      title={title}
    >
      {label}
    </span>
  )
}

function DetailWorkbench(props: AnalysisWorkbenchViewProps) {
  const reviewBidders = props.data.reviewBidders ?? []
  const categories = props.data.categories ?? []
  const paragraphs = props.data.paragraphs ?? []
  const scoringItems = props.data.scoringItems ?? []
  const projectInfo = props.data.projectInfo ?? emptyProjectInfo
  const selectedBidder =
    reviewBidders.find(
      (bidder) => bidder.id === props.selectedBidderId
    ) ??
    reviewBidders[0] ??
    emptyBidder
  const activeCategory =
    categories.find((category) => category.key === props.category) ??
    categories[0] ?? {
      key: props.category,
      label: '暂无分类',
      items: [],
    }
  const activeItems = activeCategory.items ?? []
  const activeItem = activeItems.find(
    (item) => item.id === props.activeItemId
  )
  const activeLocValue = activeItem?.loc
  const activeLoc = isFiniteNumber(activeLocValue) ? activeLocValue : -1
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
      <ScoringOverviewPanel
        projectInfo={projectInfo}
        bidderName={selectedBidder.name}
        scoreSummary={props.data.scoreSummary}
        scoringItems={scoringItems}
      />

      <section className='flex min-h-0 min-w-0 flex-col border-b xl:border-r xl:border-b-0'>
        <div className='flex shrink-0 gap-1 overflow-x-auto px-5 pt-4'>
          {categories.map((category) => {
            const items = category.items ?? []
            return (
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
                {category.label ?? '—'}
                <span className='rounded-full bg-muted px-2 py-0.5 text-xs'>
                  {items.length}
                </span>
              </button>
            )
          })}
        </div>
        <div className='min-h-0 flex-1 space-y-3 overflow-y-auto p-5'>
          {activeItems.length > 0 ? (
            activeItems.map((item, index) => (
              <ReviewItemCard
                key={item.id}
                item={item}
                index={index + 1}
                active={item.id === props.activeItemId}
                onClick={() => props.onActiveItem(item.id)}
              />
            ))
          ) : (
            <div className='rounded-lg border border-dashed p-4 text-sm text-muted-foreground'>
              暂无详细分析数据。
            </div>
          )}
        </div>
      </section>

      <section className='flex min-h-0 min-w-0 flex-col bg-muted/20'>
        <div className='shrink-0 border-b px-5 py-4'>
          <div className='flex items-center gap-2 text-sm font-semibold'>
            <FileText className='size-4 text-violet-600' />
            证据与底稿
          </div>
        </div>
        <div className='min-h-0 flex-1 space-y-3 overflow-y-auto p-5'>
          {paragraphs.length > 0 ? (
            paragraphs.map((paragraph, index) => {
              const paragraphLoc = isFiniteNumber(paragraph.loc)
                ? paragraph.loc
                : undefined
              const active = paragraphLoc != null && paragraphLoc === activeLoc
              return (
                <div
                  key={paragraphLoc ?? `paragraph-${index}`}
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
                      active
                        ? 'text-amber-700 dark:text-amber-300'
                        : 'text-muted-foreground'
                    )}
                  >
                    {paragraph.label ?? '—'}
                  </div>
                  <div className='leading-6 text-muted-foreground'>
                    {paragraph.text ?? '—'}
                  </div>
                </div>
              )
            })
          ) : (
            <div className='rounded-lg border border-dashed p-4 text-sm text-muted-foreground'>
              暂无证据与底稿。
            </div>
          )}
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
  const deductionHits = item.deductionHits ?? []
  const awardHits = item.awardHits ?? []
  const maxScore = isFiniteNumber(item.max) ? item.max : null
  const gotScore = isFiniteNumber(item.got) ? item.got : null
  const displayLoc = isFiniteNumber(item.loc) ? item.loc + 1 : '—'

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
          <span className='font-medium'>{item.title ?? '—'}</span>
          <span className='flex shrink-0 items-center gap-2'>
            {maxScore != null ? (
              <span className='text-xs font-semibold whitespace-nowrap'>
                <b className='text-primary'>
                  {gotScore == null ? '—' : formatScore(gotScore)}
                </b>
                <span className='text-muted-foreground'>
                  {' '}/ {formatScore(maxScore)} 分
                </span>
              </span>
            ) : null}
            <span
              className={cn(
                'rounded-full px-3 py-1 text-xs font-semibold',
                badge.className
              )}
            >
              {badge.label}
            </span>
          </span>
        </span>
        <span className='mt-1 block text-sm leading-6 text-muted-foreground'>
          {item.desc ?? '—'}
        </span>
        {item.manualReviewReason ? (
          <span className='mt-2 inline-flex w-fit items-center gap-1 rounded bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-700 dark:bg-amber-950/40 dark:text-amber-300'>
            {manualReviewReasonLabel(item.manualReviewReason)}
          </span>
        ) : null}
        {/* R2 扣分明细：逐条命中（扣分 + 原文 quote + 出处页），治"扣分项准确 + 上下文定位与显示" */}
        {deductionHits.length ? (
          <span className='mt-2 block space-y-1.5'>
            <span className='block text-xs font-semibold text-muted-foreground'>
              问题依据（{deductionHits.length} 条）
            </span>
            {deductionHits.map((hit, hitIndex) => (
              <ScoreHitRow key={hitIndex} hit={hit} sign='deduct' />
            ))}
          </span>
        ) : null}
        {awardHits.length ? (
          <span className='mt-2 block space-y-1.5'>
            <span className='block text-xs font-semibold text-muted-foreground'>
              响应依据（{awardHits.length} 条）
            </span>
            {awardHits.map((hit, hitIndex) => (
              <ScoreHitRow key={hitIndex} hit={hit} sign='award' />
            ))}
          </span>
        ) : null}
        <span className='mt-2 flex gap-2 rounded-lg bg-primary/5 p-2 text-xs leading-5 text-primary'>
          <Brain className='mt-0.5 size-3 shrink-0' />
          <span>
            <b>审核依据：</b>
            {item.aiNote ?? '—'}
          </span>
        </span>
        <span className='mt-2 flex items-center gap-1 text-xs font-medium text-primary'>
          <MapPin className='size-3' />
          定位原文 · {displayLoc}
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
        <span className='text-foreground'>{hit.condition ?? '—'}</span>
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

function CompareWorkbench({
  data,
  retrying,
  onRetry,
}: {
  data: TenderReviewMockData
  retrying?: boolean
  onRetry?: () => void
}) {
  const reviewBidders = data.reviewBidders ?? []
  const cards = data.bidderCards ?? []
  const projectInfo = data.projectInfo ?? emptyProjectInfo
  return (
    <div className='space-y-4 bg-muted/20 p-6'>
      <div className='text-sm text-muted-foreground'>
        {reviewBidders.length} 家投标方 · {projectInfo.method ?? '—'} · 综合对比
      </div>
      <CompareStatusBanner
        notice={data.compareNotice}
        retrying={retrying}
        onRetry={onRetry}
      />
      <BidderCompareCards cards={cards} />
    </div>
  )
}

const compareStatusText: Record<TenderCompareStatus, string> = {
  none: '',
  pending: '横比已排队，稍候自动刷新。',
  running: '横比计算中，稍候自动刷新。',
  failed: '横比未成功。',
  ready: '横比已完成。',
}

/** 横比生命周期条：状态可见 + 失败可解释 + 一键重跑（ui-guidelines 三原则）。 */
function CompareStatusBanner({
  notice,
  retrying,
  onRetry,
}: {
  notice: TenderReviewMockData['compareNotice']
  retrying?: boolean
  onRetry?: () => void
}) {
  if (!notice) return null
  const failed = notice.status === 'failed'
  const busy = notice.status === 'pending' || notice.status === 'running'
  const canRetry = Boolean(onRetry) && (failed || notice.stale)
  if (notice.status === 'ready' && !notice.stale) return null
  return (
    <div
      className={cn(
        'flex flex-wrap items-center gap-3 rounded-lg border px-4 py-3 text-sm',
        failed
          ? 'border-red-300 bg-red-50 text-red-800 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200'
          : 'border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-200'
      )}
      role='status'
    >
      <span>
        {notice.stale && !failed
          ? '投标人有变化，当前横比结果已过期。'
          : compareStatusText[notice.status]}
      </span>
      {failed && notice.errorDetail ? (
        <span className='text-xs opacity-80'>原因：{notice.errorDetail}</span>
      ) : null}
      {busy ? <span className='text-xs opacity-80'>正在计算…</span> : null}
      {canRetry ? (
        <button
          type='button'
          className='ml-auto rounded-md border border-current px-3 py-1 text-xs font-medium disabled:opacity-60'
          onClick={onRetry}
          disabled={retrying}
          aria-label='重新横比'
        >
          {retrying ? '正在重新横比…' : '重新横比'}
        </button>
      ) : null}
    </div>
  )
}

const emptyBidder: ReviewBidder = {
  id: '-',
  tag: '-',
  name: '暂无投标人',
  short: '暂无',
  total: 0,
  rank: 0,
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}
