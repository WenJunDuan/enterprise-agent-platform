import { useEffect, useRef, useState } from 'react'
import { Award, Brain, FileText, MapPin, Printer } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  CompareScoreDetailSheet,
  CompareScoringDetailTable,
  ScoringDetailTable,
} from './scoring-detail-table'
import type {
  ReviewCategory,
  ReviewItem,
  ReviewBidder,
  ScoreHit,
  TenderCompareScoreRow,
  TenderReviewMockData,
  TenderReviewMode,
  TenderScoreIssue,
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
  const viewLabel = props.mode === 'compare' ? '评分对比' : '分析中心'

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
                评分对比
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
            <span className={cn('text-xs font-semibold', active && 'text-primary')}>
              {bidder.total}
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
  const reviewStats = getReviewStats(props.data.categories, selectedBidder)
  const scoreSummary = props.data.scoreSummary ?? emptyScoreSummary
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
        <div className='rounded-xl border bg-card p-5 text-center shadow-sm'>
          <div className='text-xs font-medium text-muted-foreground'>评分汇总</div>
          <div className='mt-1 text-5xl font-semibold tracking-tight text-primary'>
            {formatScoreValue(scoreSummary.earnedTotal)}
          </div>
          <div className='text-xs text-muted-foreground'>
            / {formatScoreValue(scoreSummary.maxTotal)} 分
          </div>
          <div className='mt-3 grid grid-cols-2 gap-2 text-left text-xs'>
            <ScoreSummaryMiniCard
              label='扣分/未得分'
              score={scoreSummary.deductedTotal}
              items={[
                ...scoreSummary.deductedItems,
                ...scoreSummary.rejectedItems,
              ]}
            />
            <ScoreSummaryMiniCard
              label='未计分项'
              score={scoreSummary.pendingTotal}
              items={scoreSummary.pendingItems}
            />
          </div>
          {props.data.resultVerdict !== 'rejected' ? (
            <Badge className='mt-3 bg-emerald-100 text-emerald-700 hover:bg-emerald-100 dark:bg-emerald-950/50 dark:text-emerald-300'>
              <Award className='size-3' />
              排名第 {selectedBidder.rank} / {props.data.reviewBidders.length}
            </Badge>
          ) : (
            <Badge className='mt-3 bg-red-100 text-red-700 hover:bg-red-100 dark:bg-red-950/50 dark:text-red-300'>
              整标废标
            </Badge>
          )}
        </div>

        <div className='mt-5 space-y-4'>
          <ScoringDetailTable
            title='分项得分'
            items={props.data.scoringItems ?? []}
            variant='compact'
            emptyText='暂无分项得分。'
          />
        </div>

        <div className='mt-5 rounded-xl border bg-card p-4'>
          <div className='mb-2 flex items-center gap-2 text-sm font-semibold'>
            <Brain className='size-4 text-primary' />
            审核小结
          </div>
          <p className='text-sm leading-6 text-muted-foreground'>
            {reviewStats.summary}
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
        {typeof item.max === 'number' ? (
          <span className='mt-3 grid grid-cols-3 gap-2 rounded-lg bg-muted/40 p-2 text-xs'>
            <span>
              <span className='block text-muted-foreground'>满分</span>
              <b>{formatScoreValue(item.max)}</b>
            </span>
            <span>
              <span className='block text-muted-foreground'>实得</span>
              <b>{item.got == null ? '—' : formatScoreValue(item.got)}</b>
            </span>
            <span>
              <span className='block text-muted-foreground'>扣分</span>
              <b>{getDeductionLabel(item)}</b>
            </span>
          </span>
        ) : null}
        {item.manualReviewReason ? (
          <span className='mt-2 inline-flex w-fit items-center gap-1 rounded bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-700 dark:bg-amber-950/40 dark:text-amber-300'>
            {manualReviewReasonLabel(item.manualReviewReason)}
          </span>
        ) : null}
        {/* R2 扣分明细：逐条命中（扣分 + 原文 quote + 出处页），治"扣分项准确 + 上下文定位与显示" */}
        {item.deductionHits?.length ? (
          <span className='mt-2 block space-y-1.5'>
            <span className='block text-xs font-semibold text-muted-foreground'>
              扣分明细（{item.deductionHits.length} 条）
            </span>
            {item.deductionHits.map((hit, hitIndex) => (
              <ScoreHitRow key={hitIndex} hit={hit} sign='deduct' />
            ))}
          </span>
        ) : null}
        {item.awardHits?.length ? (
          <span className='mt-2 block space-y-1.5'>
            <span className='block text-xs font-semibold text-muted-foreground'>
              加分明细（{item.awardHits.length} 条）
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

/** R2：单条扣分/加分明细行 — 扣/加分值 + 命中条件 + 投标原文 quote + 出处页（上下文定位）。 */
function ScoreHitRow({ hit, sign }: { hit: ScoreHit; sign: 'deduct' | 'award' }) {
  const ptsLabel =
    hit.points == null
      ? ''
      : `${sign === 'deduct' ? '−' : '+'}${formatScoreValue(hit.points)} 分`
  return (
    <span className='block rounded-lg bg-muted/40 px-2.5 py-1.5 text-xs'>
      <span className='flex items-start gap-2'>
        {ptsLabel ? (
          <b
            className={cn(
              'shrink-0',
              sign === 'deduct'
                ? 'text-red-600 dark:text-red-300'
                : 'text-emerald-600 dark:text-emerald-300'
            )}
          >
            {ptsLabel}
          </b>
        ) : null}
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
      label: '不通过',
      className: 'bg-red-100 text-red-700 dark:bg-red-950/50 dark:text-red-300',
    }
  }
  if (item.status === 'pass') {
    return {
      label: '通过',
      className: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300',
    }
  }

  return {
    label: `${item.got} / ${item.max} 分`,
    className: 'bg-blue-100 text-blue-700 dark:bg-blue-950/50 dark:text-blue-300',
  }
}

function CompareWorkbench({ data }: { data: TenderReviewMockData }) {
  const [selectedScoreRow, setSelectedScoreRow] =
    useState<TenderCompareScoreRow | null>(null)
  const hasMultipleBidders = data.reviewBidders.length >= 2

  return (
    <div className='space-y-5 bg-muted/20 p-6'>
      <div className='text-sm text-muted-foreground'>
        {data.reviewBidders.length} 家投标方 · {data.projectInfo.method}（满分
        100）· 各评审项最高分以绿色高亮。
      </div>
      <div className='grid gap-4 md:grid-cols-2 xl:grid-cols-4'>
        {data.reviewBidders.map((bidder) => {
          const winner = bidder.rank === 1
          return (
            <div
              key={bidder.id}
              className={cn(
                'relative overflow-hidden rounded-xl border bg-card p-4 shadow-sm',
                winner &&
                  'border-emerald-200 shadow-emerald-100 dark:border-emerald-900 dark:shadow-none'
              )}
            >
              <div
                className={cn(
                  'absolute inset-x-0 top-0 h-1',
                  winner ? 'bg-emerald-500' : 'bg-muted-foreground/30'
                )}
              />
              <div className='flex items-center justify-between'>
                <Badge
                  className={cn(
                    winner
                      ? 'bg-emerald-100 text-emerald-700 hover:bg-emerald-100'
                      : 'bg-muted text-muted-foreground hover:bg-muted',
                    winner && 'dark:bg-emerald-950/50 dark:text-emerald-300'
                  )}
                >
                  第 {bidder.rank} 名
                </Badge>
                <span className='flex size-6 items-center justify-center rounded-md bg-muted text-xs font-semibold'>
                  {bidder.tag}
                </span>
              </div>
              <div className='mt-3 line-clamp-2 min-h-10 text-sm font-semibold'>
                {bidder.name}
              </div>
      <div className='mt-2 flex items-baseline gap-1'>
                <span
                  className={cn(
                    'text-3xl font-semibold tracking-tight',
                    winner && 'text-emerald-700 dark:text-emerald-300'
                  )}
                >
                  {bidder.total}
                </span>
                <span className='text-xs text-muted-foreground'>分</span>
              </div>
            </div>
          )
        })}
      </div>
      <CompareTable data={data} />
      {hasMultipleBidders ? (
        <>
          <CompareScoringDetailTable
            rows={data.compareScoreRows ?? []}
            bidders={data.reviewBidders}
            selectedRowId={selectedScoreRow?.id}
            onRowClick={setSelectedScoreRow}
          />
          <CompareScoreDetailSheet
            row={selectedScoreRow}
            open={Boolean(selectedScoreRow)}
            onOpenChange={(open) => {
              if (!open) setSelectedScoreRow(null)
            }}
          />
        </>
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
          <div className='px-5 py-3'>评审项 / 分值</div>
          {data.reviewBidders.map((bidder) => (
            <div key={bidder.id} className='px-3 py-3 text-center'>
              {bidder.short}
            </div>
          ))}
        </div>
        {rows.map((row) => {
          const max = Math.max(...row.cells, 0)
          return (
            <div
              key={`${row.group}-${row.name}`}
              className='grid border-b last:border-b-0'
              style={gridStyle}
            >
              <div className='px-5 py-3'>
                <div className='text-sm font-medium'>{row.name}</div>
                <div className='text-xs text-muted-foreground'>
                  {row.group} · 满分 {row.max}
                </div>
              </div>
              {row.cells.map((value, index) => (
                <div
                  key={`${row.name}-${data.reviewBidders[index]?.id}`}
                  className='flex flex-col items-center justify-center gap-1 px-3 py-3'
                >
                  <span
                    className={cn(
                      'text-sm font-medium',
                      value === max &&
                        'font-semibold text-emerald-700 dark:text-emerald-300'
                    )}
                  >
                    {value}
                  </span>
                  <div className='h-1.5 w-full overflow-hidden rounded-full bg-muted'>
                    <div
                      className={cn(
                        'h-full rounded-full',
                        value === max ? 'bg-emerald-500' : 'bg-muted-foreground/40'
                      )}
                      style={{
                        width: `${row.max > 0 ? (value / row.max) * 100 : 0}%`,
                      }}
                    />
                  </div>
                </div>
              ))}
            </div>
          )
        })}
        <div className='grid bg-primary/10 font-semibold' style={gridStyle}>
          <div className='px-5 py-4'>综合总分</div>
          {data.reviewBidders.map((bidder) => (
            <div key={bidder.id} className='px-3 py-4 text-center text-primary'>
              {bidder.total}
            </div>
          ))}
        </div>
      </div>
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

const emptyScoreSummary = {
  maxTotal: 0,
  earnedTotal: 0,
  deductedTotal: 0,
  pendingTotal: 0,
  deductedItems: [],
  rejectedItems: [],
  pendingItems: [],
}

function ScoreSummaryMiniCard({
  label,
  score,
  items,
}: {
  label: string
  score: number
  items: TenderScoreIssue[]
}) {
  return (
    <div className='min-w-0 rounded-lg bg-muted/50 p-2'>
      <div className='text-muted-foreground'>{label}</div>
      <div className='mt-1 font-semibold'>
        {formatScoreValue(score)} 分 · {items.length} 项
      </div>
      {items.length > 0 ? (
        <div className='mt-1 line-clamp-2 leading-4 text-muted-foreground'>
          {items.map((item) => item.item).join('、')}
        </div>
      ) : (
        <div className='mt-1 text-muted-foreground'>无</div>
      )}
    </div>
  )
}

function getDeductionLabel(item: ReviewItem) {
  if (item.got == null || item.max == null) return '—'
  return formatScoreValue(Math.max(0, item.max - item.got))
}

function formatScoreValue(score: number) {
  return Number.isInteger(score) ? String(score) : score.toFixed(1)
}

function getReviewStats(
  categories: TenderReviewMockData['categories'],
  selectedBidder: ReviewBidder
) {
  const items = categories.flatMap((category) => category.items)
  const passCount = items.filter((item) => item.status === 'pass').length
  const warningCount = items.filter((item) => item.status === 'warning').length
  const failCount = items.filter((item) => item.status === 'fail').length
  const totalCount = items.length
  return {
    summary:
      totalCount > 0
        ? `${selectedBidder.name} 共完成 ${totalCount} 项审核：${passCount} 项通过、${warningCount} 项待核查、${failCount} 项不通过。`
        : `${selectedBidder.name} 暂无可展示的评分明细。`,
  }
}
