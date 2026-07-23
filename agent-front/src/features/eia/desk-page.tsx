import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Badge } from '@/components/ui/badge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { listEiaCases } from './api'
import { CaseDetailPanel } from './components/case-detail-panel'
import { EIA_CATEGORY_GLYPH } from './model/mock-data'
import type { EiaCase, EiaCaseStatus } from './types'

const STATUS_BADGE_VARIANT: Record<
  EiaCaseStatus,
  'default' | 'secondary' | 'outline'
> = {
  已出具: 'default',
  受理中: 'secondary',
  'AI 分析中': 'outline',
  报告编制: 'outline',
}

export function EiaDeskPage() {
  const casesQuery = useQuery({
    queryKey: ['eia-cases'],
    queryFn: listEiaCases,
  })
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const cases = casesQuery.data ?? []

  // 默认选中第一条案件、联动详情侧栏：派生值而非 effect + setState，用户点选后
  // selectedId 生效，未点选前回落到列表首条。
  const effectiveSelectedId = selectedId ?? cases[0]?.id ?? null
  const selectedCase =
    cases.find((item) => item.id === effectiveSelectedId) ?? null

  function handlePreReview(eiaCase: EiaCase) {
    toast(`${eiaCase.id} 已进入预审，预审意见将同步至案件详情`)
  }

  function handleDownloadReport(eiaCase: EiaCase, categoryTitle: string) {
    toast(`${eiaCase.id} ${categoryTitle}类报告 PDF 已开始下载`)
  }

  return (
    <>
      <Header fixed />
      <Main className='space-y-5'>
        <div>
          <p className='mb-1 text-xs tracking-wide text-primary uppercase'>
            受理工作台
          </p>
          <h1 className='text-2xl font-semibold tracking-tight'>
            检测报告受理列表
          </h1>
        </div>

        {casesQuery.isPending ? (
          <p className='text-sm text-muted-foreground'>加载中…</p>
        ) : casesQuery.isError ? (
          <p className='text-sm text-destructive'>
            案件列表加载失败，请刷新页面重试。
          </p>
        ) : cases.length === 0 ? (
          <p className='text-sm text-muted-foreground'>
            暂无受理案件，等待提交检测报告后同步显示。
          </p>
        ) : (
          <div className='grid gap-4 lg:grid-cols-[1fr_360px] lg:items-start'>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>受理编号</TableHead>
                  <TableHead>项目名称</TableHead>
                  <TableHead>类别</TableHead>
                  <TableHead>状态</TableHead>
                  <TableHead>提交时间</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {cases.map((eiaCase) => (
                  <TableRow
                    key={eiaCase.id}
                    data-state={
                      eiaCase.id === effectiveSelectedId ? 'selected' : undefined
                    }
                    className='cursor-pointer'
                    onClick={() => setSelectedId(eiaCase.id)}
                  >
                    <TableCell className='whitespace-nowrap tabular-nums'>
                      {eiaCase.id}
                    </TableCell>
                    <TableCell>{eiaCase.project}</TableCell>
                    <TableCell className='text-muted-foreground'>
                      {eiaCase.categories
                        .map((category) => EIA_CATEGORY_GLYPH[category])
                        .join(' · ')}
                    </TableCell>
                    <TableCell>
                      <Badge variant={STATUS_BADGE_VARIANT[eiaCase.status]}>
                        {eiaCase.status}
                      </Badge>
                    </TableCell>
                    <TableCell className='text-muted-foreground tabular-nums'>
                      {eiaCase.date}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>

            {selectedCase ? (
              <CaseDetailPanel
                eiaCase={selectedCase}
                onPreReview={handlePreReview}
                onDownloadReport={handleDownloadReport}
              />
            ) : null}
          </div>
        )}
      </Main>
    </>
  )
}
