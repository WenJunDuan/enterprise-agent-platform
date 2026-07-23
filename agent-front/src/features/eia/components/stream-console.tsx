import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import type {
  StreamTone,
  StreamTrackRow,
  VisibleStreamLine,
} from '../model/stream-script'

// tone → 终端行配色。终端容器用 bg-foreground/text-background 反色语义（design.md A3：
// 不引入静态稿硬编码色值，深浅主题都靠 tokens 自动成立）；ok/warn 沿用项目既有的语义色号
// 惯例（如 CONFIDENCE_STYLE），不是裸 hex。
const LINE_TONE_CLASS: Record<StreamTone, string> = {
  head: 'text-background/55',
  cat: 'text-background',
  data: 'pl-4 text-background/75',
  ok: 'text-emerald-400',
  warn: 'text-amber-400',
}

function TrackRow({ row }: { row: StreamTrackRow }) {
  const dotClass =
    row.status === '等待' ? 'bg-muted-foreground/30' : 'bg-primary'
  return (
    <div className='flex items-center gap-2 border-b px-4 py-2.5 text-sm last:border-b-0'>
      <span
        className={`size-2 flex-none rounded-full ${dotClass}`}
        aria-hidden='true'
      />
      <span className='flex-1'>{row.label}</span>
      <span className='text-xs text-muted-foreground'>{row.status}</span>
    </div>
  )
}

/**
 * 提交向导第三步「AI 分析」进行中态：左侧分轨进度 + 右侧终端风格逐字符流。
 * 定时推进由父组件 useEffect 驱动，本组件只吃已计算好的可见行/进度/分轨状态。
 */
export function StreamConsole({
  progressPercent,
  trackRows,
  lines,
  streamDone,
  reportCount,
  onViewReports,
}: {
  progressPercent: number
  trackRows: StreamTrackRow[]
  lines: VisibleStreamLine[]
  streamDone: boolean
  reportCount: number
  onViewReports: () => void
}) {
  return (
    <div className='grid gap-4 lg:grid-cols-[300px_1fr] lg:items-start'>
      <Card>
        <CardHeader className='flex-row items-baseline justify-between space-y-0'>
          <CardTitle className='text-xs tracking-wide text-muted-foreground uppercase'>
            分析进度
          </CardTitle>
          <span className='font-mono text-xl text-primary tabular-nums'>
            {progressPercent}%
          </span>
        </CardHeader>
        <div className='h-1.5 bg-muted'>
          <div
            className='h-1.5 bg-primary transition-[width] duration-200'
            style={{ width: `${progressPercent}%` }}
          />
        </div>
        <CardContent className='p-0'>
          {trackRows.map((row) => (
            <TrackRow key={row.label} row={row} />
          ))}
        </CardContent>
      </Card>

      <Card className='flex min-h-[420px] flex-col overflow-hidden bg-foreground text-background'>
        <CardHeader className='flex-row items-center gap-2 space-y-0 border-b border-background/20 py-3'>
          <span
            className='size-2 flex-none animate-pulse rounded-full bg-primary'
            aria-hidden='true'
          />
          <CardTitle className='text-xs tracking-wide text-background/80 uppercase'>
            AI 分析引擎 · 实时输出
          </CardTitle>
        </CardHeader>
        <CardContent
          role='status'
          aria-live='polite'
          className='flex-1 space-y-1.5 py-4 font-mono text-sm leading-relaxed'
        >
          {lines.map((line, index) => (
            <div
              key={index}
              className={`whitespace-pre-wrap ${LINE_TONE_CLASS[line.tone]}`}
            >
              {line.text}
              {line.cursor ? (
                <span className='ml-0.5 inline-block h-3.5 w-2 animate-pulse bg-primary align-middle' />
              ) : null}
            </div>
          ))}
        </CardContent>
        {streamDone ? (
          <div className='flex items-center gap-4 border-t border-background/20 px-4 py-3'>
            <span className='text-sm text-background/70'>
              分析完成，已生成 {reportCount} 份分类报告
            </span>
            <Button className='ml-auto' onClick={onViewReports}>
              查看分析报告 →
            </Button>
          </div>
        ) : null}
      </Card>
    </div>
  )
}
