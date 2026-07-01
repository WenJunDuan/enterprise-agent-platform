import { CheckCircle2, Clock, Trophy, XCircle } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { BidderCard, ChecklistStatus, IssueItem } from '../types'

type BidderCompareCardsProps = {
  cards: BidderCard[]
}

const statusMeta: Record<
  ChecklistStatus,
  { label: string; Icon: typeof CheckCircle2; className: string }
> = {
  met: { label: '达到', Icon: CheckCircle2, className: 'text-emerald-600 dark:text-emerald-400' },
  unmet: { label: '未达到', Icon: XCircle, className: 'text-red-600 dark:text-red-400' },
  pending: { label: '待核验', Icon: Clock, className: 'text-amber-600 dark:text-amber-400' },
}

const statusOrder: ChecklistStatus[] = ['met', 'unmet', 'pending']

function fmt(n: number): string {
  return Number.isInteger(n) ? String(n) : n.toFixed(1)
}

/** 风险对比「每家一卡」：符合性 checklist + 评分总分/实得 + 关键风险，横向并排多家。 */
export function BidderCompareCards({ cards }: BidderCompareCardsProps) {
  if (cards.length === 0) {
    return (
      <div className='rounded-xl border border-dashed bg-card p-4 text-sm text-muted-foreground'>
        暂无投标人评审数据；至少需要一家完成评标后展示综合对比。
      </div>
    )
  }

  return (
    <div className='grid gap-4 md:grid-cols-2 xl:grid-cols-3'>
      {cards.map((card) => (
        <BidderCardView key={card.id} card={card} />
      ))}
    </div>
  )
}

function BidderCardView({ card }: { card: BidderCard }) {
  const counts = statusOrder.map((status) => ({
    status,
    meta: statusMeta[status],
    count: card.checklist.filter((item) => item.status === status).length,
  }))
  // 需关注项：未达到 + 待核验（达到项只计数、不逐条列，保持卡片精简）
  const attention = card.checklist.filter((item) => item.status !== 'met')

  return (
    <div className='flex min-h-0 flex-col overflow-hidden rounded-xl border bg-card shadow-sm'>
      {/* 头部：名 + 排名 + 总分/实得 */}
      <div className='border-b bg-card/80 p-4'>
        <div className='flex items-start justify-between gap-2'>
          <div className='min-w-0'>
            <div className='flex items-center gap-2'>
              <span className='flex size-6 shrink-0 items-center justify-center rounded-md bg-primary/10 text-xs font-semibold text-primary'>
                {card.tag}
              </span>
              <span className='truncate font-semibold' title={card.name}>
                {card.name}
              </span>
            </div>
          </div>
          {card.rank > 0 ? (
            <span className='flex shrink-0 items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground'>
              <Trophy className='size-3' />第 {card.rank} 名
            </span>
          ) : null}
        </div>
        <div className='mt-3 flex items-end gap-2'>
          <span className='text-2xl font-semibold tracking-tight text-primary'>
            {fmt(card.score.earnedTotal)}
          </span>
          <span className='mb-0.5 text-sm text-muted-foreground'>
            / {fmt(card.score.maxTotal)} 分
          </span>
          {card.score.pendingTotal > 0 ? (
            <span className='mb-0.5 ml-auto text-xs text-amber-700 dark:text-amber-300'>
              待核验 {fmt(card.score.pendingTotal)} 分
            </span>
          ) : null}
        </div>
      </div>

      {/* 符合性 checklist 概况 */}
      <div className='border-b p-4'>
        <div className='mb-2 text-xs font-semibold text-muted-foreground'>符合性 checklist</div>
        <div className='grid grid-cols-3 gap-2'>
          {counts.map(({ status, meta, count }) => (
            <div
              key={status}
              className='rounded-lg bg-muted/50 p-2'
              role='group'
              aria-label={`${meta.label} ${count} 项`}
            >
              <div className='flex items-center gap-1 text-xs text-muted-foreground'>
                <meta.Icon className={cn('size-3.5', meta.className)} aria-hidden />
                {meta.label}
              </div>
              <div className='mt-0.5 text-lg font-semibold'>{count}</div>
            </div>
          ))}
        </div>
        {attention.length > 0 ? (
          <div className='mt-3 space-y-1.5'>
            {attention.map((item) => {
              const meta = statusMeta[item.status]
              return (
                <div key={item.id} className='flex items-start gap-2 text-xs'>
                  <meta.Icon
                    className={cn('mt-0.5 size-3.5 shrink-0', meta.className)}
                    aria-hidden
                  />
                  <span className='min-w-0'>
                    <span className='font-medium'>{item.requirement}</span>
                    <span className='ml-1 text-muted-foreground'>· {meta.label}</span>
                  </span>
                </div>
              )
            })}
          </div>
        ) : (
          <p className='mt-3 text-xs text-muted-foreground'>各招标要求均已达到，无待关注项。</p>
        )}
      </div>

      {/* 关键风险 */}
      <div className='min-h-0 flex-1 p-4'>
        <div className='mb-2 text-xs font-semibold text-muted-foreground'>
          关键风险 {card.topIssues.length > 0 ? `（${card.topIssues.length}）` : ''}
        </div>
        {card.topIssues.length === 0 ? (
          <p className='text-xs text-muted-foreground'>暂未发现明显问题。</p>
        ) : (
          <div className='space-y-1.5'>
            {card.topIssues.slice(0, 5).map((issue) => (
              <IssueRow key={issue.id} issue={issue} />
            ))}
            {card.topIssues.length > 5 ? (
              <p className='text-xs text-muted-foreground'>
                另有 {card.topIssues.length - 5} 项，详见该投标人「详细分析」。
              </p>
            ) : null}
          </div>
        )}
      </div>
    </div>
  )
}

function IssueRow({ issue }: { issue: IssueItem }) {
  const isRisk = issue.status === 'risk'
  return (
    <div className='rounded-lg bg-muted/40 p-2 text-xs'>
      <div className='flex items-center gap-1.5'>
        <span
          className={cn(
            'size-1.5 shrink-0 rounded-full',
            isRisk ? 'bg-red-500' : issue.status === 'pending' ? 'bg-amber-400' : 'bg-orange-400'
          )}
        />
        <span className='font-medium text-foreground'>{issue.itemName}</span>
      </div>
      <div className='mt-1 line-clamp-2 leading-5 text-muted-foreground'>{issue.basis}</div>
    </div>
  )
}
