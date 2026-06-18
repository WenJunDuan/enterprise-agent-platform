import { Eye } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { getBusinessTypeMeta } from '../data/business-type'
import { formatDateTime, type OperLog } from '../model'

type Props = {
  records: OperLog[]
  selectedIds: Set<string>
  isLoading: boolean
  allowSelection: boolean
  canShowDetail: boolean
  onToggleSelectAll: (checked: boolean) => void
  onToggleSelect: (id: string) => void
  onShowDetail: (id: string) => void
}

export function OperLogTable({
  records,
  selectedIds,
  isLoading,
  allowSelection,
  canShowDetail,
  onToggleSelectAll,
  onToggleSelect,
  onShowDetail,
}: Props) {
  const allSelected =
    records.length > 0 && selectedIds.size === records.length
  const someSelected = selectedIds.size > 0 && selectedIds.size < records.length

  return (
    <div className='rounded-md border'>
      <Table>
        <TableHeader>
          <TableRow>
            {allowSelection ? (
              <TableHead className='w-10'>
                <Checkbox
                  checked={allSelected || (someSelected && 'indeterminate')}
                  onCheckedChange={(value) => onToggleSelectAll(Boolean(value))}
                  aria-label='全选当前页操作日志'
                  className='translate-y-[2px]'
                />
              </TableHead>
            ) : null}
            <TableHead>模块</TableHead>
            <TableHead className='w-24'>业务类型</TableHead>
            <TableHead className='w-28'>操作人</TableHead>
            <TableHead className='w-20'>方式</TableHead>
            <TableHead>URL</TableHead>
            <TableHead className='w-32'>IP</TableHead>
            <TableHead className='w-20'>状态</TableHead>
            <TableHead className='w-20'>耗时</TableHead>
            <TableHead className='w-44'>时间</TableHead>
            <TableHead className='w-16 text-right'>操作</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {isLoading ? (
            <TableRow>
              <TableCell colSpan={allowSelection ? 11 : 10} className='text-center text-sm'>
                加载中...
              </TableCell>
            </TableRow>
          ) : records.length === 0 ? (
            <TableRow>
              <TableCell
                colSpan={allowSelection ? 11 : 10}
                className='text-center text-sm text-muted-foreground'
              >
                暂无数据
              </TableCell>
            </TableRow>
          ) : (
            records.map((log) => {
              const meta = getBusinessTypeMeta(log.businessType)
              return (
                <TableRow key={log.operId}>
                  {allowSelection ? (
                    <TableCell>
                      <Checkbox
                        checked={selectedIds.has(log.operId)}
                        onCheckedChange={() => onToggleSelect(log.operId)}
                        aria-label='选择当前操作日志'
                        className='translate-y-[2px]'
                      />
                    </TableCell>
                  ) : null}
                  <TableCell>
                    <span className='max-w-40 truncate' title={log.title}>
                      {log.title || '-'}
                    </span>
                  </TableCell>
                  <TableCell>
                    <Badge variant={meta.variant}>{meta.label}</Badge>
                  </TableCell>
                  <TableCell>{log.operName || '-'}</TableCell>
                  <TableCell>{log.requestMethod || '-'}</TableCell>
                  <TableCell>
                    <span
                      className='block max-w-60 truncate font-mono text-xs'
                      title={log.operUrl}
                    >
                      {log.operUrl || '-'}
                    </span>
                  </TableCell>
                  <TableCell className='font-mono text-xs'>
                    {log.operIp || '-'}
                  </TableCell>
                  <TableCell>
                    <Badge
                      variant={log.status === 0 ? 'default' : 'destructive'}
                    >
                      {log.status === 0 ? '正常' : '异常'}
                    </Badge>
                  </TableCell>
                  <TableCell>{log.costTime}ms</TableCell>
                  <TableCell>{formatDateTime(log.operTime)}</TableCell>
                  <TableCell className='text-right'>
                    {canShowDetail ? (
                      <Button
                        size='sm'
                        variant='ghost'
                        onClick={() => onShowDetail(log.operId)}
                      >
                        <Eye className='size-4' />
                      </Button>
                    ) : null}
                  </TableCell>
                </TableRow>
              )
            })
          )}
        </TableBody>
      </Table>
    </div>
  )
}
