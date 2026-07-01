import { CheckCircle2, Clock, MapPin, XCircle } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { ChecklistItem, ChecklistStatus } from '../types'

type StatusMeta = {
  label: string
  Icon: typeof CheckCircle2
  rowClassName: string
  iconClassName: string
  badgeClassName: string
}

// 三态视觉：图标 + **文字标签**双通道，不靠颜色单独传达（守 ui-guidelines a11y P0，色盲友好）。
const statusMeta: Record<ChecklistStatus, StatusMeta> = {
  met: {
    label: '达到',
    Icon: CheckCircle2,
    rowClassName: 'border-l-emerald-500',
    iconClassName: 'text-emerald-600 dark:text-emerald-400',
    badgeClassName:
      'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300',
  },
  unmet: {
    label: '未达到',
    Icon: XCircle,
    rowClassName: 'border-l-red-500',
    iconClassName: 'text-red-600 dark:text-red-400',
    badgeClassName:
      'bg-red-100 text-red-700 dark:bg-red-950/50 dark:text-red-300',
  },
  pending: {
    label: '待核验',
    Icon: Clock,
    rowClassName: 'border-l-amber-400',
    iconClassName: 'text-amber-600 dark:text-amber-400',
    badgeClassName:
      'bg-amber-100 text-amber-700 dark:bg-amber-950/50 dark:text-amber-300',
  },
}

// 组展示顺序：资格审查（最高优先级）→ 否决条款 → 硬性响应；未知组名兜底追加在后。
const groupOrder = ['资格审查', '否决条款', '硬性响应']

const statusOrder: ChecklistStatus[] = ['met', 'unmet', 'pending']

function orderGroups(checklist: ChecklistItem[]) {
  const seen = new Set(checklist.map((item) => item.group))
  const known = groupOrder.filter((group) => seen.has(group))
  const extra = [...seen].filter((group) => !groupOrder.includes(group))
  return [...known, ...extra].map((group) => ({
    group,
    items: checklist.filter((item) => item.group === group),
  }))
}

export function OverviewChecklistView({
  checklist,
  bidderName,
}: {
  checklist: ChecklistItem[]
  bidderName: string
}) {
  if (checklist.length === 0) {
    return (
      <div className='p-6'>
        <div className='rounded-xl border bg-card p-6 text-sm text-muted-foreground'>
          暂无可派生的符合性 checklist；该结果尚未产出资格审查 / 否决 / 硬性响应项，
          请查看「详细分析」。
        </div>
      </div>
    )
  }

  const counts = statusOrder.map((status) => ({
    status,
    meta: statusMeta[status],
    count: checklist.filter((item) => item.status === status).length,
  }))
  const groups = orderGroups(checklist)

  return (
    <div className='space-y-5 bg-muted/20 p-6'>
      <div className='rounded-xl border bg-card p-5 shadow-sm'>
        <div className='text-sm font-semibold'>
          概要分析 · 符合性 checklist
        </div>
        <p className='mt-1 text-xs text-muted-foreground'>
          {bidderName} 对招标要求的达成概览（不含分数）；待核验项需人工结合出处页复核，不作未达到处理。
        </p>
        <div className='mt-4 grid grid-cols-3 gap-2'>
          {counts.map(({ status, meta, count }) => (
            <div key={status} className='rounded-lg bg-muted/50 p-3'>
              <div className='flex items-center gap-1.5 text-xs text-muted-foreground'>
                <meta.Icon className={cn('size-3.5', meta.iconClassName)} />
                {meta.label}
              </div>
              <div className='mt-1 text-xl font-semibold'>{count}</div>
            </div>
          ))}
        </div>
      </div>

      {groups.map(({ group, items }) => (
        <div key={group} className='rounded-xl border bg-card p-5 shadow-sm'>
          <div className='mb-3 flex items-center justify-between gap-2'>
            <div className='text-sm font-semibold'>{group}</div>
            <span className='rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground'>
              {items.length} 项
            </span>
          </div>
          <div className='space-y-2.5'>
            {items.map((item) => (
              <ChecklistRow key={item.id} item={item} />
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

function ChecklistRow({ item }: { item: ChecklistItem }) {
  const meta = statusMeta[item.status]
  const evidence = item.evidence.filter((ev) => ev.source || ev.quote)

  return (
    <div
      className={cn(
        'rounded-lg border border-l-4 bg-background p-3.5',
        meta.rowClassName
      )}
    >
      <div className='flex items-start gap-2.5'>
        <meta.Icon
          className={cn('mt-0.5 size-4 shrink-0', meta.iconClassName)}
          aria-hidden
        />
        <div className='min-w-0 flex-1'>
          <div className='flex flex-wrap items-center gap-2'>
            <span
              className={cn(
                'shrink-0 rounded-full px-2 py-0.5 text-xs font-semibold',
                meta.badgeClassName
              )}
            >
              {meta.label}
            </span>
            <span className='font-medium'>{item.requirement}</span>
          </div>
          <p className='mt-1.5 text-sm leading-6 text-muted-foreground'>
            {item.reason}
          </p>
          {evidence.length > 0 ? (
            <details className='mt-2 text-xs'>
              <summary className='cursor-pointer font-medium text-primary'>
                出处（{evidence.length}）
              </summary>
              <div className='mt-1.5 space-y-1.5'>
                {evidence.map((ev, index) => (
                  <div
                    key={index}
                    className='rounded-md bg-muted/40 px-2.5 py-1.5'
                  >
                    {ev.quote ? (
                      <div className='border-l-2 border-l-amber-300 pl-2 leading-5 text-muted-foreground italic'>
                        「{ev.quote}」
                      </div>
                    ) : null}
                    {ev.source ? (
                      <div className='mt-1 flex items-center gap-1 font-medium text-primary'>
                        <MapPin className='size-3 shrink-0' aria-hidden />
                        {ev.source}
                      </div>
                    ) : null}
                  </div>
                ))}
              </div>
            </details>
          ) : null}
        </div>
      </div>
    </div>
  )
}
