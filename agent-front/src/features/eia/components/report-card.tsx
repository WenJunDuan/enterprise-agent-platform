import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { EIA_CATEGORY_GLYPH } from '../model/mock-data'
import type { EiaReport } from '../types'

/** 单个分类的分析报告卡：结论徽标 + 依据表格 + 摘要 + 下载。 */
export function ReportCard({
  report,
  onDownload,
}: {
  report: EiaReport
  onDownload: () => void
}) {
  return (
    <Card>
      <CardHeader className='flex-row flex-wrap items-center gap-3 space-y-0'>
        <span className='flex size-9 flex-none items-center justify-center rounded-md border-2 border-primary text-lg font-semibold text-primary'>
          {EIA_CATEGORY_GLYPH[report.category]}
        </span>
        <CardTitle className='text-lg'>{report.title}分析报告</CardTitle>
        <Badge variant={report.verdict === '关注' ? 'outline' : 'default'}>
          {report.verdict}
        </Badge>
        <span className='ml-auto text-xs text-muted-foreground tabular-nums'>
          {report.no}
        </span>
      </CardHeader>
      <CardContent className='space-y-4'>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>分析项</TableHead>
              <TableHead>实测 / 依据</TableHead>
              <TableHead>结论</TableHead>
              <TableHead>置信度</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {report.findings.map((finding) => (
              <TableRow key={finding.item}>
                <TableCell>{finding.item}</TableCell>
                <TableCell className='text-muted-foreground tabular-nums'>
                  {finding.basis}
                </TableCell>
                <TableCell>
                  <Badge variant={finding.ok ? 'default' : 'outline'}>
                    {finding.verdict}
                  </Badge>
                </TableCell>
                <TableCell className='text-muted-foreground tabular-nums'>
                  {finding.confidence}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        <p className='max-w-prose text-sm text-muted-foreground'>
          {report.summary}
        </p>
        <Button onClick={onDownload}>下载{report.title}报告 PDF</Button>
      </CardContent>
    </Card>
  )
}
