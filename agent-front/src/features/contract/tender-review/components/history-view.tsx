import { Archive, Search } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import type {
  HistoryTimeRange,
  TenderProject,
} from '../types'
import { StatusBadge } from './status-badge'

const timeFilters: Array<{ value: HistoryTimeRange; label: string }> = [
  { value: 'all', label: '全部时间' },
  { value: 'week', label: '近 7 天' },
  { value: 'month', label: '近 30 天' },
]

type HistoryViewProps = {
  query: string
  timeRange: HistoryTimeRange
  history: TenderProject[]
  onQuery: (value: string) => void
  onTimeRange: (value: HistoryTimeRange) => void
  onAnalysis: () => void
  onReport: () => void
}

const historyGrid =
  'grid-cols-[2.2fr_1fr_0.7fr_0.8fr_1fr_0.85fr_minmax(170px,1.4fr)]'

export function HistoryView(props: HistoryViewProps) {
  return (
    <div className='space-y-4'>
      <HistoryFilters {...props} />
      <HistoryTable
        history={props.history}
        onAnalysis={props.onAnalysis}
        onReport={props.onReport}
      />
    </div>
  )
}

function HistoryFilters(props: HistoryViewProps) {
  return (
    <div className='flex flex-col gap-3 xl:flex-row xl:items-center'>
      <SearchInput query={props.query} onQuery={props.onQuery} />
      <div className='flex-1' />
      <FilterButtons
        items={timeFilters}
        value={props.timeRange}
        onChange={props.onTimeRange}
      />
    </div>
  )
}

function SearchInput({
  query,
  onQuery,
}: {
  query: string
  onQuery: (value: string) => void
}) {
  return (
    <div className='relative w-full xl:max-w-sm'>
      <Search className='absolute top-2.5 left-3 size-4 text-muted-foreground' />
      <Input
        className='pl-9'
        value={query}
        onChange={(event) => onQuery(event.target.value)}
        placeholder='搜索项目名称或招标编号...'
      />
    </div>
  )
}

function FilterButtons<T extends string>({
  items,
  value,
  onChange,
}: {
  items: Array<{ value: T; label: string }>
  value: T
  onChange: (value: T) => void
}) {
  return (
    <div className='flex flex-wrap gap-2'>
      {items.map((item) => (
        <Button
          key={item.value}
          type='button'
          size='sm'
          variant={value === item.value ? 'default' : 'outline'}
          onClick={() => onChange(item.value)}
        >
          {item.label}
        </Button>
      ))}
    </div>
  )
}

function HistoryTable({
  history,
  onAnalysis,
  onReport,
}: {
  history: TenderProject[]
  onAnalysis: () => void
  onReport: () => void
}) {
  return (
    <Card className='overflow-hidden'>
      <CardContent className='p-0'>
        {history.length === 0 ? (
          <EmptyHistory />
        ) : (
          <div className='overflow-x-auto'>
            <div className='min-w-[1000px]'>
              <HistoryHeader />
              {history.map((item) => (
                <HistoryRow
                  key={item.id}
                  item={item}
                  onAnalysis={onAnalysis}
                  onReport={onReport}
                />
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function HistoryHeader() {
  return (
    <div
      className={`grid ${historyGrid} bg-muted/40 text-xs font-semibold text-muted-foreground`}
    >
      <div className='px-5 py-3 text-center'>项目名称 / 编号</div>
      <div className='px-3 py-3 text-center'>评标办法</div>
      <div className='px-3 py-3 text-center'>投标方</div>
      <div className='px-3 py-3 text-center'>中标得分</div>
      <div className='px-3 py-3 text-center'>完成日期</div>
      <div className='px-3 py-3 text-center'>状态</div>
      <div className='px-4 py-3 text-center'>操作</div>
    </div>
  )
}

function HistoryRow({
  item,
  onAnalysis,
  onReport,
}: {
  item: TenderProject
  onAnalysis: () => void
  onReport: () => void
}) {
  return (
    <div
      className={`grid ${historyGrid} items-center border-t text-sm transition-colors hover:bg-muted/30`}
    >
      <button type='button' className='min-w-0 px-5 py-4 text-left' onClick={onAnalysis}>
        <div className='truncate font-medium'>{item.name}</div>
        <div className='mt-1 truncate text-xs text-muted-foreground'>
          {item.code}
        </div>
      </button>
      <div className='truncate px-3 py-4 text-center text-muted-foreground'>
        {item.method}
      </div>
      <div className='px-3 py-4 text-center'>{item.bidderCount}</div>
      <div className='px-3 py-4 text-center font-semibold'>{item.score}</div>
      <div className='px-3 py-4 text-center text-muted-foreground'>
        {item.date}
      </div>
      <div className='px-3 py-4 text-center'>
        <StatusBadge status={item.status} />
      </div>
      <div className='flex justify-center gap-2 px-4 py-3'>
        <HistoryAction label='分析中心' onClick={onAnalysis} />
        <HistoryAction label='审核报告' primary onClick={onReport} />
      </div>
    </div>
  )
}

function HistoryAction({
  label,
  primary,
  onClick,
}: {
  label: string
  primary?: boolean
  onClick: () => void
}) {
  return (
    <Button
      type='button'
      size='sm'
      variant={primary ? 'default' : 'outline'}
      className='whitespace-nowrap'
      onClick={onClick}
    >
      {label}
    </Button>
  )
}

function EmptyHistory() {
  return (
    <div className='rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground'>
      <Archive className='mx-auto mb-2 size-8' />
      没有符合条件的历史评审。
    </div>
  )
}
