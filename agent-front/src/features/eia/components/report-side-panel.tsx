import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import type { EiaReport } from '../types'

/**
 * 报告态右侧栏：报告清单(逐份下载 + 打包下载全部) + 受理信息(回看分析过程 /
 * 转入受理工作台 / 再提交一份)。四个收尾动作齐全(design.md 验收标准 3)。
 */
export function ReportSidePanel({
  reports,
  batchNo,
  onDownloadOne,
  onDownloadAll,
  onReplay,
  onGoDesk,
  onReset,
}: {
  reports: EiaReport[]
  batchNo: string
  onDownloadOne: (report: EiaReport) => void
  onDownloadAll: () => void
  onReplay: () => void
  onGoDesk: () => void
  onReset: () => void
}) {
  return (
    <div className='flex flex-col gap-3'>
      <Card>
        <CardHeader>
          <CardTitle className='text-xs tracking-wide text-muted-foreground uppercase'>
            报告清单
          </CardTitle>
        </CardHeader>
        <CardContent className='space-y-1'>
          {reports.map((report) => (
            <div
              key={report.category}
              className='flex items-center gap-2 border-b py-2 text-sm last:border-b-0'
            >
              <span className='flex-1'>{report.title}分析报告</span>
              <Button
                variant='secondary'
                size='sm'
                onClick={() => onDownloadOne(report)}
              >
                下载
              </Button>
            </div>
          ))}
          <Button variant='ghost' className='w-full' onClick={onDownloadAll}>
            打包下载全部
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className='text-xs tracking-wide text-muted-foreground uppercase'>
            受理信息
          </CardTitle>
        </CardHeader>
        <CardContent className='space-y-3'>
          <p className='text-sm text-muted-foreground'>受理编号 {batchNo}</p>
          <div className='flex flex-col gap-2'>
            <Button variant='secondary' className='w-full' onClick={onReplay}>
              回看分析过程
            </Button>
            <Button variant='secondary' className='w-full' onClick={onGoDesk}>
              转入受理工作台
            </Button>
            <Button variant='ghost' className='w-full' onClick={onReset}>
              再提交一份
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
