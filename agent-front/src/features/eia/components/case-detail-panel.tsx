import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { EIA_CATEGORY_GLYPH } from '../model/mock-data'
import type { EiaCase, EiaCaseStatus } from '../types'

const CASE_STAGE_ORDER: readonly EiaCaseStatus[] = [
  '受理中',
  'AI 分析中',
  '报告编制',
  '已出具',
]

/** 各类别报告在当前案件状态下是否已可下载：已出具则全部就绪；报告编制阶段先出第一份。 */
function isCategoryReportReady(
  status: EiaCaseStatus,
  categoryIndex: number
): boolean {
  if (status === '已出具') return true
  if (status === '报告编制') return categoryIndex === 0
  return false
}

/** 受理工作台右侧案件详情：状态时间线 + 分类报告清单 + 预审动作。 */
export function CaseDetailPanel({
  eiaCase,
  onPreReview,
  onDownloadReport,
}: {
  eiaCase: EiaCase
  onPreReview: (eiaCase: EiaCase) => void
  onDownloadReport: (eiaCase: EiaCase, categoryTitle: string) => void
}) {
  const reachedIndex = CASE_STAGE_ORDER.indexOf(eiaCase.status)

  return (
    <Card>
      <CardHeader>
        <CardTitle className='text-xs tracking-wide text-muted-foreground uppercase'>
          案件详情
        </CardTitle>
        <p className='text-lg font-semibold'>{eiaCase.project}</p>
        <p className='text-xs text-muted-foreground'>
          {eiaCase.id} ·{' '}
          {eiaCase.categories
            .map((category) => EIA_CATEGORY_GLYPH[category])
            .join(' · ')}{' '}
          · 委托方 {eiaCase.org}
        </p>
      </CardHeader>
      <CardContent className='space-y-4'>
        <div className='border-t'>
          {CASE_STAGE_ORDER.map((stage, index) => {
            const reached = index <= reachedIndex
            return (
              <div
                key={stage}
                className={`flex items-center gap-3 border-b py-2.5 last:border-b-0 ${
                  reached ? '' : 'opacity-50'
                }`}
              >
                <span
                  className={`size-2.5 flex-none rounded-full ${
                    reached ? 'bg-primary' : 'bg-muted-foreground/30'
                  }`}
                  aria-hidden='true'
                />
                <div className='flex flex-col'>
                  <span className='text-sm font-medium'>{stage}</span>
                  <span className='text-xs text-muted-foreground'>
                    {reached ? '已完成' : '待进行'}
                  </span>
                </div>
              </div>
            )
          })}
        </div>

        <div>
          <p className='mb-1 text-xs tracking-wide text-muted-foreground uppercase'>
            分类报告
          </p>
          {eiaCase.categories.map((category, index) => {
            const ready = isCategoryReportReady(eiaCase.status, index)
            const title = EIA_CATEGORY_GLYPH[category]
            return (
              <div
                key={category}
                className='flex items-center gap-2 border-b py-2 text-sm last:border-b-0'
              >
                <span className='flex-1'>{title}类分析报告</span>
                {ready ? (
                  <Button
                    variant='secondary'
                    size='sm'
                    onClick={() => onDownloadReport(eiaCase, title)}
                  >
                    下载
                  </Button>
                ) : (
                  <Badge variant='outline'>编制中</Badge>
                )}
              </div>
            )
          })}
        </div>

        <Button className='w-full' onClick={() => onPreReview(eiaCase)}>
          预审
        </Button>
      </CardContent>
    </Card>
  )
}
