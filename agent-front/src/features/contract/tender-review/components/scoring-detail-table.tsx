import { ChevronDown, FileText, MapPin } from 'lucide-react'
import { cn } from '@/lib/utils'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import type {
  ReviewBidder,
  TenderCompareScoreRow,
  TenderReviewDimension,
  TenderScoreCategory,
  TenderScoreEvidence,
  TenderScoringItem,
} from '../types'
import { resolvePendingReasonLabel } from '../model'

type ScoringDetailTableProps = {
  items: TenderScoringItem[]
  title?: string
  variant?: 'full' | 'compact'
  emptyText?: string
  className?: string
}

type CompareScoringDetailTableProps = {
  rows: TenderCompareScoreRow[]
  bidders: ReviewBidder[]
  selectedRowId?: string
  onRowClick: (row: TenderCompareScoreRow) => void
}

type CompareScoreDetailSheetProps = {
  row: TenderCompareScoreRow | null
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function ScoringDetailTable({
  items,
  title = '评标项目明细',
  variant = 'full',
  emptyText = '暂无评标项目明细。',
  className,
}: ScoringDetailTableProps) {
  const groups = groupScoringItems(items)

  if (items.length === 0) {
    return (
      <div
        className={cn(
          'rounded-lg border border-dashed p-4 text-sm text-muted-foreground',
          className
        )}
      >
        {emptyText}
      </div>
    )
  }

  return (
    <div className={cn('space-y-3', className)}>
      {title ? <div className='text-sm font-semibold'>{title}</div> : null}
      {groups.map((group) => (
        <details
          key={group.category}
          open
          className='group overflow-hidden rounded-lg border bg-card'
        >
          <summary className='flex cursor-pointer list-none items-center justify-between gap-3 bg-muted/40 px-3 py-2 text-sm font-semibold'>
            <span>
              {getScoreCategoryLabel(group.category)}
              <span className='ml-2 text-xs font-normal text-muted-foreground'>
                {group.items.length} 项
              </span>
            </span>
            <ChevronDown className='size-4 text-muted-foreground transition-transform group-open:rotate-180' />
          </summary>
          {variant === 'compact' ? (
            <CompactScoringRows items={group.items} />
          ) : (
            <FullScoringRows items={group.items} />
          )}
        </details>
      ))}
    </div>
  )
}

function CompactScoringRows({ items }: { items: TenderScoringItem[] }) {
  return (
    <div className='overflow-x-auto'>
      <div className='min-w-[620px]'>
        <div className='grid h-10 grid-cols-[minmax(140px,1.2fr)_56px_56px_68px_minmax(220px,1.6fr)] items-center border-b px-3 text-xs font-semibold text-muted-foreground'>
          <div>评标项目</div>
          <div className='text-center'>结果</div>
          <div className='text-center'>满分</div>
          <div className='text-center'>处理</div>
          <div>依据</div>
        </div>
        {items.map((item, index) => (
          <div
            key={item.id}
            className={cn(
              'grid h-[72px] grid-cols-[minmax(140px,1.2fr)_56px_56px_68px_minmax(220px,1.6fr)] items-center px-3 text-xs',
              index % 2 ? 'bg-muted/20' : ''
            )}
          >
            <div className='line-clamp-2 pr-2 font-medium text-foreground'>
              {item.item}
            </div>
            <div className='text-center font-semibold'>
              {getStatusLabel(item.status)}
            </div>
            <div className='text-center text-muted-foreground'>
              {formatMax(item.max)}
            </div>
            <div className='text-center text-muted-foreground'>
              {resolvePendingReasonLabel(item)}
            </div>
            <div className='line-clamp-2 leading-5 text-muted-foreground'>
              {item.basis || '—'}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function FullScoringRows({ items }: { items: TenderScoringItem[] }) {
  return (
    <div className='overflow-x-auto'>
      <div className='min-w-[760px]'>
        <div className='grid grid-cols-[minmax(180px,1.2fr)_80px_90px_100px_minmax(260px,1.5fr)] border-b px-3 py-2 text-xs font-semibold text-muted-foreground'>
          <div>评标项目</div>
          <div className='text-center'>满分</div>
          <div className='text-center'>状态</div>
          <div className='text-center'>关注点</div>
          <div>判定依据</div>
        </div>
        {items.map((item, index) => (
          <div
            key={item.id}
            className={cn(
              'grid grid-cols-[minmax(180px,1.2fr)_80px_90px_100px_minmax(260px,1.5fr)] px-3 py-3 text-sm',
              index % 2 ? 'bg-muted/20' : ''
            )}
          >
            <div className='font-medium text-foreground'>{item.item}</div>
            <div className='text-center text-muted-foreground'>
              {formatMax(item.max)}
            </div>
            <div className='text-center font-semibold'>
              {getStatusLabel(item.status)}
            </div>
            <div className='text-center text-muted-foreground'>
              {/* KD5：待定原因显式化（枚举→中文文案），存量无字段仍回退"待核验"。 */}
              {resolvePendingReasonLabel(item)}
            </div>
            <div className='leading-6 text-muted-foreground'>
              {item.basis || '—'}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

export function CompareScoringDetailTable({
  rows,
  bidders,
  selectedRowId,
  onRowClick,
}: CompareScoringDetailTableProps) {
  const groups = groupCompareRows(rows)
  const gridStyle = {
    gridTemplateColumns: `minmax(220px,1.4fr) 80px repeat(${Math.max(
      bidders.length,
      1
    )}, minmax(128px,1fr))`,
  }
  const minWidth = 320 + Math.max(bidders.length, 1) * 150

  if (rows.length === 0) {
    return (
      <div className='rounded-xl border border-dashed bg-card p-4 text-sm text-muted-foreground'>
        暂无可对比的分项评分明细。
      </div>
    )
  }

  return (
    <div className='space-y-3'>
      <div>
        <div className='text-sm font-semibold'>评标项目明细</div>
        <div className='mt-1 text-xs text-muted-foreground'>
          点击任一评分项查看各投标人的依据与证据。
        </div>
      </div>
      {groups.map((group) => (
        <details
          key={group.dimension}
          open
          className='group overflow-hidden rounded-xl border bg-card shadow-sm'
        >
          <summary className='flex cursor-pointer list-none items-center justify-between gap-3 bg-muted/40 px-4 py-3 text-sm font-semibold'>
            <span>{getReviewDimensionLabel(group.dimension)}</span>
            <ChevronDown className='size-4 text-muted-foreground transition-transform group-open:rotate-180' />
          </summary>
          <div className='overflow-x-auto'>
            <div style={{ minWidth }}>
              <div
                className='grid border-b px-4 py-2 text-xs font-semibold text-muted-foreground'
                style={gridStyle}
              >
                <div>评分项</div>
                <div className='text-center'>满分</div>
                {bidders.map((bidder) => (
                  <div key={bidder.id} className='text-center'>
                    {bidder.short}
                  </div>
                ))}
              </div>
              {group.rows.map((row, index) => (
                <button
                  key={row.id}
                  type='button'
                  className={cn(
                    'grid w-full border-b px-4 py-3 text-left text-sm last:border-b-0 hover:bg-muted/30',
                    index % 2 ? 'bg-muted/10' : '',
                    selectedRowId === row.id && 'bg-primary/5'
                  )}
                  style={gridStyle}
                  onClick={() => onRowClick(row)}
                >
                  <div className='font-medium text-foreground'>
                    {row.item}
                    {row.reviewDimension === 'technical_subjective' ? (
                      <div className='mt-1 text-xs font-normal text-amber-700'>
                        初评建议，最终以评标委员会评分为准
                      </div>
                    ) : null}
                  </div>
                  <div className='text-center text-muted-foreground'>
                    {formatMax(row.max)}
                  </div>
                  {row.cells.map((cell) => (
                    <div
                      key={`${row.id}-${cell.bidderId}`}
                      className='text-center'
                    >
                      <div className='font-semibold'>
                        {getStatusLabel(cell.status)}
                      </div>
                      <div className='text-xs text-muted-foreground'>
                        {cell.score == null ? '待核验' : '已记录'}
                      </div>
                    </div>
                  ))}
                </button>
              ))}
            </div>
          </div>
        </details>
      ))}
    </div>
  )
}

export function CompareScoreDetailSheet({
  row,
  open,
  onOpenChange,
}: CompareScoreDetailSheetProps) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className='w-full overflow-y-auto sm:max-w-xl'>
        <SheetHeader className='border-b'>
          <SheetTitle>{row?.item ?? '评标项目明细'}</SheetTitle>
          <SheetDescription>
            {row
              ? `${getReviewDimensionLabel(row.reviewDimension)} · ${row.max == null ? '未设分值' : `满分 ${formatScore(row.max)}`}`
              : ''}
          </SheetDescription>
        </SheetHeader>
        <div className='space-y-4 px-4 pb-6'>
          {row?.reviewDimension === 'technical_subjective' ? (
            <div className='rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs leading-5 text-amber-800 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-300'>
              初评建议，最终以评标委员会评分为准。此处仅按各家事实依据对照展示。
            </div>
          ) : null}
          {row?.cells.map((cell) => (
            <div key={cell.bidderId} className='rounded-lg border p-4'>
              <div className='flex items-start justify-between gap-3'>
                <div className='min-w-0'>
                  <div className='font-semibold'>{cell.bidderName}</div>
                  <div className='mt-1 text-xs text-muted-foreground'>
                    {getReviewDimensionLabel(row.reviewDimension)} ·
                    {getStatusLabel(cell.status)}
                  </div>
                </div>
                <span className='rounded-md bg-muted px-2 py-1 text-xs font-semibold text-muted-foreground'>
                  {getStatusLabel(cell.status)}
                </span>
              </div>
              <div className='mt-3 rounded-md bg-muted/40 p-3 text-sm leading-6 text-muted-foreground'>
                {cell.basis || '—'}
              </div>
              <EvidenceList evidence={cell.evidence} />
            </div>
          ))}
          {row?.reviewDimension === 'technical_subjective' ? (
            <div className='rounded-lg border bg-muted/40 p-3 text-sm leading-6 text-muted-foreground'>
              事实对照：{buildSubjectiveDifference(row)}
            </div>
          ) : null}
        </div>
      </SheetContent>
    </Sheet>
  )
}

function EvidenceList({ evidence }: { evidence: TenderScoreEvidence[] }) {
  if (evidence.length === 0) {
    return (
      <div className='mt-3 rounded-md border border-dashed p-3 text-xs text-muted-foreground'>
        暂无单项证据。
      </div>
    )
  }

  return (
    <div className='mt-3 space-y-2'>
      {evidence.map((item, index) => (
        <div
          key={index}
          className='rounded-md bg-muted/30 p-3 text-xs leading-5'
        >
          {item.condition ? (
            <div className='font-semibold text-foreground'>
              {item.condition}
            </div>
          ) : null}
          {item.quote ? (
            <div className='mt-1 border-l-2 border-l-amber-300 pl-2 text-muted-foreground italic'>
              「{item.quote}」
            </div>
          ) : null}
          {item.finding || item.conclusion ? (
            <div className='mt-1 flex gap-1 text-muted-foreground'>
              <FileText className='mt-0.5 size-3 shrink-0' />
              <span>
                {[item.finding, item.conclusion].filter(Boolean).join('；')}
              </span>
            </div>
          ) : null}
          {item.source ? (
            <div className='mt-1 flex items-center gap-1 font-medium text-primary'>
              <MapPin className='size-3 shrink-0' />
              {item.source}
            </div>
          ) : null}
        </div>
      ))}
    </div>
  )
}

function groupScoringItems(items: TenderScoringItem[]) {
  return groupByScoreCategory(items, (item) => item.scoreCategory)
}

function groupCompareRows(rows: TenderCompareScoreRow[]) {
  return groupByReviewDimension(rows, (row) => row.reviewDimension).map(
    (group) => ({
      dimension: group.dimension,
      rows: group.items,
    })
  )
}

function groupByScoreCategory<T>(
  items: T[],
  pickCategory: (item: T) => TenderScoreCategory
) {
  return (['business', 'technical'] as const)
    .map((category) => ({
      category,
      items: items.filter((item) => pickCategory(item) === category),
    }))
    .filter((group) => group.items.length > 0)
}

function getScoreCategoryLabel(category: TenderScoreCategory) {
  return category === 'business' ? '商务标' : '技术标'
}

function groupByReviewDimension<T>(
  items: T[],
  pickDimension: (item: T) => TenderReviewDimension
) {
  return (['price', 'business_objective', 'technical_subjective'] as const)
    .map((dimension) => ({
      dimension,
      items: items.filter((item) => pickDimension(item) === dimension),
    }))
    .filter((group) => group.items.length > 0)
}

function getReviewDimensionLabel(dimension: TenderReviewDimension) {
  if (dimension === 'price') return '价格分'
  if (dimension === 'technical_subjective') return '技术主观分'
  return '商务客观分'
}

function buildSubjectiveDifference(row: TenderCompareScoreRow) {
  const cells = row.cells.filter((cell) => cell.basis.trim())
  if (cells.length === 0) return '暂无可展示的事实依据。'
  return cells
    .map((cell) => `${cell.bidderName}：${cell.basis || '—'}`)
    .join('；')
}

function getStatusLabel(status: string) {
  if (status === 'scored') return '已记录'
  if (status === 'rejected' || status === 'failed') return '存在问题'
  if (status === 'manual_review' || status.includes('待')) return '—'
  return status || '—'
}

function formatScore(score: number) {
  return Number.isInteger(score) ? String(score) : score.toFixed(1)
}

function formatMax(max: number | null) {
  return max == null ? '未设分值' : formatScore(max)
}
