import { Award, Brain, FileText, MapPin, Printer } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import type {
  ReviewCategory,
  ReviewItem,
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

const scoreBlocks = [
  { label: '商务标', got: 48, max: 50, color: 'bg-blue-500' },
  { label: '技术标', got: 36.5, max: 40, color: 'bg-violet-500' },
  { label: '信誉业绩', got: 10, max: 10, color: 'bg-emerald-500' },
]

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
                历史评审
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
            <Button size='sm' onClick={props.onReport}>
              <Printer className='size-4' />
              生成报告
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
    ) ?? props.data.reviewBidders[0]
  const activeCategory =
    props.data.categories.find((category) => category.key === props.category) ??
    props.data.categories[0]
  const activeItem = activeCategory.items.find(
    (item) => item.id === props.activeItemId
  )
  const activeLoc = activeItem?.loc ?? -1

  return (
    <div className='grid min-h-[620px] xl:grid-cols-[288px_minmax(0,1.2fr)_minmax(340px,1fr)]'>
      <aside className='border-b bg-muted/20 p-5 xl:border-r xl:border-b-0'>
        <div className='rounded-xl border bg-card p-5 text-center shadow-sm'>
          <div className='text-xs font-medium text-muted-foreground'>综合得分</div>
          <div className='mt-1 text-5xl font-semibold tracking-tight text-primary'>
            {selectedBidder.total}
          </div>
          <div className='text-xs text-muted-foreground'>/ 100 分</div>
          <Badge className='mt-3 bg-emerald-100 text-emerald-700 hover:bg-emerald-100'>
            <Award className='size-3' />
            排名第 {selectedBidder.rank} / {props.data.reviewBidders.length}
          </Badge>
        </div>

        <div className='mt-5 space-y-4'>
          <div className='text-xs font-semibold text-muted-foreground'>分项得分</div>
          {scoreBlocks.map((block) => (
            <div key={block.label}>
              <div className='mb-1 flex justify-between text-sm'>
                <span className='font-medium'>{block.label}</span>
                <span className='text-muted-foreground'>
                  <b className='text-foreground'>{block.got}</b> / {block.max}
                </span>
              </div>
              <div className='h-2 overflow-hidden rounded-full bg-muted'>
                <div
                  className={cn('h-full rounded-full', block.color)}
                  style={{ width: `${(block.got / block.max) * 100}%` }}
                />
              </div>
            </div>
          ))}
        </div>

        <div className='mt-5 rounded-xl border bg-card p-4'>
          <div className='mb-2 flex items-center gap-2 text-sm font-semibold'>
            <Brain className='size-4 text-primary' />
            审核小结
          </div>
          <p className='text-sm leading-6 text-muted-foreground'>
            资格审查 <b className='text-foreground'>6 项通过、1 项待核查</b>
            ；技术与商务得分均居首位。建议核实「近三年无重大安全事故」承诺函原件后，推荐为第一中标候选人。
          </p>
        </div>
      </aside>

      <section className='min-w-0 border-b xl:border-r xl:border-b-0'>
        <div className='flex gap-1 overflow-x-auto px-5 pt-4'>
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
        <div className='space-y-3 p-5'>
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

      <section className='min-w-0 bg-muted/20'>
        <div className='border-b px-5 py-4'>
          <div className='flex items-center gap-2 text-sm font-semibold'>
            <FileText className='size-4 text-violet-600' />
            投标文件原文
          </div>
          <div className='mt-1 text-xs text-muted-foreground'>
            中建华东建设集团_投标文件.pdf · 点击左侧要点自动定位
          </div>
        </div>
        <div className='max-h-[560px] space-y-3 overflow-y-auto p-5'>
          {props.data.paragraphs.map((paragraph) => {
            const active = paragraph.loc === activeLoc
            return (
              <div
                key={paragraph.loc}
                className={cn(
                  'rounded-lg border-l-4 bg-card p-4 text-sm shadow-sm',
                  active
                    ? 'border-l-amber-500 bg-amber-50'
                    : 'border-l-transparent'
                )}
              >
                <div
                  className={cn(
                    'mb-1 text-xs font-bold',
                    active ? 'text-amber-700' : 'text-muted-foreground'
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

function getItemBadge(item: ReviewItem) {
  if (item.status === 'warning') {
    return {
      label: '待核查',
      className: 'bg-amber-100 text-amber-700',
    }
  }
  if (item.status === 'fail') {
    return {
      label: '不通过',
      className: 'bg-red-100 text-red-700',
    }
  }
  if (item.status === 'pass') {
    return {
      label: '通过',
      className: 'bg-emerald-100 text-emerald-700',
    }
  }

  return {
    label: `${item.got} / ${item.max} 分`,
    className: 'bg-blue-100 text-blue-700',
  }
}

function CompareWorkbench({ data }: { data: TenderReviewMockData }) {
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
                winner && 'border-emerald-200 shadow-emerald-100'
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
                      : 'bg-muted text-muted-foreground hover:bg-muted'
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
                    winner && 'text-emerald-700'
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
    </div>
  )
}

function CompareTable({ data }: { data: TenderReviewMockData }) {
  const rows = data.compareGroups.flatMap((group) =>
    group.rows.map((row) => ({ ...row, group: group.name }))
  )

  return (
    <div className='overflow-x-auto rounded-xl border bg-card shadow-sm'>
      <div className='min-w-[980px]'>
        <div className='grid grid-cols-[1.6fr_repeat(4,1fr)] border-b bg-muted/40 text-xs font-semibold text-muted-foreground'>
          <div className='px-5 py-3'>评审项 / 分值</div>
          {data.reviewBidders.map((bidder) => (
            <div key={bidder.id} className='px-3 py-3 text-center'>
              {bidder.short}
            </div>
          ))}
        </div>
        {rows.map((row) => {
          const max = Math.max(...row.cells)
          return (
            <div
              key={`${row.group}-${row.name}`}
              className='grid grid-cols-[1.6fr_repeat(4,1fr)] border-b last:border-b-0'
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
                      value === max && 'font-semibold text-emerald-700'
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
                      style={{ width: `${(value / row.max) * 100}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          )
        })}
        <div className='grid grid-cols-[1.6fr_repeat(4,1fr)] bg-blue-50 font-semibold'>
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
