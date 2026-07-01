import {
  AlertTriangle,
  Building2,
  ClipboardList,
  MapPin,
  MinusCircle,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { formatScore } from '../format'
import type {
  ProjectInfo,
  TenderScoreCategory,
  TenderScoreSummary,
  TenderScoringItem,
} from '../types'

type ScoringOverviewPanelProps = {
  projectInfo: ProjectInfo
  bidderName: string
  scoreSummary?: TenderScoreSummary
  scoringItems?: TenderScoringItem[]
  className?: string
}

const EMPTY_SUMMARY: TenderScoreSummary = {
  maxTotal: 0,
  earnedTotal: 0,
  deductedTotal: 0,
  pendingTotal: 0,
  deductedItems: [],
  rejectedItems: [],
  pendingItems: [],
}

// 扣分明细一行：逐条扣分命中(带原文/出处) 或 整项失分/判0 的汇总行。
type LossEntry = {
  key: string
  item: string
  label: string
  reject: boolean
  detail?: string
  quote?: string
  source?: string
}

/** 详细分析左侧「评分总览」：招标项目 + 分数卡 + 类目合计 + 扣分明细(逐条带出处) + 待核验。 */
export function ScoringOverviewPanel({
  projectInfo,
  bidderName,
  scoreSummary,
  scoringItems = [],
  className,
}: ScoringOverviewPanelProps) {
  const s = scoreSummary ?? EMPTY_SUMMARY
  const categories = summarizeByCategory(scoringItems)
  const losses = buildLossEntries(scoringItems)

  return (
    <aside
      className={cn(
        'min-h-0 space-y-4 overflow-y-auto border-b bg-muted/20 p-5 xl:border-r xl:border-b-0',
        className
      )}
    >
      {/* 招标项目 */}
      <div className='rounded-xl border bg-card p-4 shadow-sm'>
        <div className='flex items-center gap-2 text-sm font-semibold'>
          <Building2 className='size-4 text-primary' />
          招标项目
        </div>
        <div className='mt-2 truncate text-sm font-medium' title={projectInfo.name}>
          {projectInfo.name || '—'}
        </div>
        <dl className='mt-2 grid grid-cols-1 gap-1 text-xs text-muted-foreground'>
          <Meta label='招标编号' value={projectInfo.code} />
          <Meta label='评标方法' value={projectInfo.method} />
          <Meta label='控制价' value={projectInfo.controlPrice} />
          <Meta label='当前投标人' value={bidderName} />
        </dl>
      </div>

      {/* 分数卡 */}
      <div className='rounded-xl border bg-card p-4 shadow-sm'>
        <div className='flex items-center gap-2 text-sm font-semibold'>
          <ClipboardList className='size-4 text-primary' />
          评分总览
        </div>
        <div className='mt-3 grid grid-cols-2 gap-2'>
          <Stat label='实际得分' value={formatScore(s.earnedTotal)} tone='primary' big />
          <Stat label='总分' value={formatScore(s.maxTotal)} />
          <Stat label='已扣分' value={formatScore(s.deductedTotal)} tone='red' />
          <Stat label='待核验' value={formatScore(s.pendingTotal)} tone='amber' />
        </div>
        {categories.length > 0 ? (
          <div className='mt-3 space-y-1.5 border-t pt-3'>
            {categories.map((c) => (
              <div
                key={c.category}
                className='flex items-center justify-between text-xs'
              >
                <span className='text-muted-foreground'>{categoryLabel(c.category)}</span>
                <span className='font-medium'>
                  {formatScore(c.earned)} / {formatScore(c.max)}
                </span>
              </div>
            ))}
          </div>
        ) : null}
        {s.pendingTotal > 0 ? (
          <p className='mt-3 text-xs leading-5 text-muted-foreground'>
            待核验分不计入实际得分（价格横比 / 外部数据 / 现场答辩等需人工确认）。
          </p>
        ) : null}
      </div>

      {/* 扣分明细（逐条带出处） */}
      <div className='rounded-xl border bg-card p-4 shadow-sm'>
        <div className='flex items-center gap-2 text-sm font-semibold'>
          <MinusCircle className='size-4 text-red-600' />
          扣分明细
          <span className='ml-auto rounded-full bg-muted px-2 py-0.5 text-xs font-normal text-muted-foreground'>
            {losses.length} 条
          </span>
        </div>
        {losses.length === 0 ? (
          <p className='mt-2 text-sm leading-6 text-muted-foreground'>
            暂无扣分 / 失分项；各评分项均按满分或规则计分。
          </p>
        ) : (
          <div className='mt-3 space-y-2'>
            {losses.map((loss) => (
              <div key={loss.key} className='rounded-lg bg-muted/40 p-2.5 text-xs'>
                <div className='flex items-start justify-between gap-2'>
                  <span className='font-medium text-foreground'>{loss.item}</span>
                  <span className='shrink-0 font-semibold text-red-600 dark:text-red-300'>
                    {loss.reject ? '该项判 0' : loss.label}
                  </span>
                </div>
                {loss.detail ? (
                  <div className='mt-1 leading-5 text-muted-foreground'>{loss.detail}</div>
                ) : null}
                {loss.quote ? (
                  <div className='mt-1 border-l-2 border-l-amber-300 pl-2 leading-5 text-muted-foreground italic'>
                    「{loss.quote}」
                  </div>
                ) : null}
                {loss.source ? (
                  <div className='mt-1 flex items-center gap-1 font-medium text-primary'>
                    <MapPin className='size-3 shrink-0' />
                    {loss.source}
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 待核验清单（若有） */}
      {s.pendingItems.length > 0 ? (
        <div className='rounded-xl border bg-card p-4 shadow-sm'>
          <div className='flex items-center gap-2 text-sm font-semibold'>
            <AlertTriangle className='size-4 text-amber-600' />
            待核验项
            <span className='ml-auto rounded-full bg-muted px-2 py-0.5 text-xs font-normal text-muted-foreground'>
              {s.pendingItems.length} 项
            </span>
          </div>
          <div className='mt-3 space-y-2'>
            {s.pendingItems.map((item, index) => (
              <div key={`${item.item}-${index}`} className='rounded-lg bg-muted/40 p-2.5 text-xs'>
                <div className='flex items-start justify-between gap-2'>
                  <span className='font-medium text-foreground'>{item.item}</span>
                  <span className='shrink-0 font-semibold text-amber-700 dark:text-amber-300'>
                    满分 {formatScore(item.max)} · 待核验
                  </span>
                </div>
                <div className='mt-1 leading-5 text-muted-foreground'>{item.basis || '—'}</div>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </aside>
  )
}

function Meta({ label, value }: { label: string; value?: string }) {
  return (
    <div className='flex items-center justify-between gap-2'>
      <dt className='shrink-0'>{label}</dt>
      <dd className='truncate text-right font-medium text-foreground' title={value || '—'}>
        {value || '—'}
      </dd>
    </div>
  )
}

function Stat({
  label,
  value,
  tone = 'default',
  big = false,
}: {
  label: string
  value: string
  tone?: 'default' | 'primary' | 'red' | 'amber'
  big?: boolean
}) {
  const toneClass =
    tone === 'primary'
      ? 'text-primary'
      : tone === 'red'
        ? 'text-red-600 dark:text-red-300'
        : tone === 'amber'
          ? 'text-amber-700 dark:text-amber-300'
          : 'text-foreground'
  return (
    <div className='rounded-lg bg-muted/50 p-3'>
      <div className='text-xs text-muted-foreground'>{label}</div>
      <div className={cn('mt-1 font-semibold tracking-tight', big ? 'text-2xl' : 'text-xl', toneClass)}>
        {value}
      </div>
    </div>
  )
}

// 从评分项派生扣分明细：优先逐条扣分命中(带原文/出处)，无命中则给整项失分/判0 汇总行。
function buildLossEntries(items: TenderScoringItem[]): LossEntry[] {
  const entries: LossEntry[] = []
  items.forEach((item) => {
    if (item.status === 'rejected') {
      entries.push({
        key: item.id,
        item: item.item,
        label: '该项判 0',
        reject: true,
        detail: item.basis,
      })
      return
    }
    if (item.deductionHits && item.deductionHits.length > 0) {
      item.deductionHits.forEach((hit, index) => {
        entries.push({
          key: `${item.id}-${index}`,
          item: item.item,
          label: hit.points != null ? `-${formatScore(hit.points)} 分` : '扣分',
          reject: false,
          detail: hit.condition,
          quote: hit.quote,
          source: hit.source,
        })
      })
      return
    }
    // 无逐条命中但确有失分(如 pass_fail 得 0 / 客观项未满足) → 汇总一行。
    if (item.status === 'scored' && item.score != null && item.score < item.max) {
      entries.push({
        key: item.id,
        item: item.item,
        label: `-${formatScore(item.max - item.score)} 分`,
        reject: false,
        detail: item.basis,
      })
    }
  })
  return entries
}

function summarizeByCategory(items: TenderScoringItem[]) {
  return (['business', 'technical'] as const)
    .map((category) => {
      const group = items.filter((item) => item.scoreCategory === category)
      return {
        category,
        max: round(group.reduce((sum, item) => sum + item.max, 0)),
        earned: round(
          group.reduce(
            (sum, item) =>
              item.status === 'scored' && item.score != null ? sum + item.score : sum,
            0
          )
        ),
      }
    })
    .filter((group) => group.max > 0)
}

function categoryLabel(category: TenderScoreCategory): string {
  return category === 'business' ? '商务标' : '技术标'
}

function round(n: number): number {
  return Number(n.toFixed(1))
}
