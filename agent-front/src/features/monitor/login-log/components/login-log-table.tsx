import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { formatDateTime, type LoginLog } from '../model'

type Props = {
  records: LoginLog[]
  selectedIds: Set<string>
  isLoading: boolean
  allowSelection: boolean
  onToggleSelectAll: (checked: boolean) => void
  onToggleSelect: (id: string) => void
}

export function LoginLogTable({
  records,
  selectedIds,
  isLoading,
  allowSelection,
  onToggleSelectAll,
  onToggleSelect,
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
                  aria-label='全选当前页登录日志'
                  className='translate-y-[2px]'
                />
              </TableHead>
            ) : null}
            <TableHead className='w-32'>账号</TableHead>
            <TableHead className='w-36'>IP</TableHead>
            <TableHead className='w-40'>地点</TableHead>
            <TableHead className='w-28'>浏览器</TableHead>
            <TableHead className='w-28'>系统</TableHead>
            <TableHead className='w-20'>状态</TableHead>
            <TableHead>消息</TableHead>
            <TableHead className='w-44'>登录时间</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {isLoading ? (
            <TableRow>
              <TableCell colSpan={allowSelection ? 9 : 8} className='text-center text-sm'>
                加载中...
              </TableCell>
            </TableRow>
          ) : records.length === 0 ? (
            <TableRow>
              <TableCell
                colSpan={allowSelection ? 9 : 8}
                className='text-center text-sm text-muted-foreground'
              >
                暂无数据
              </TableCell>
            </TableRow>
          ) : (
            records.map((log) => (
              <TableRow key={log.infoId}>
                {allowSelection ? (
                  <TableCell>
                    <Checkbox
                      checked={selectedIds.has(log.infoId)}
                      onCheckedChange={() => onToggleSelect(log.infoId)}
                      aria-label='选择当前登录日志'
                      className='translate-y-[2px]'
                    />
                  </TableCell>
                ) : null}
                <TableCell>{log.username || '-'}</TableCell>
                <TableCell className='font-mono text-xs'>
                  {log.ipaddr || '-'}
                </TableCell>
                <TableCell>{log.loginLocation || '-'}</TableCell>
                <TableCell>{log.browser || '-'}</TableCell>
                <TableCell>{log.os || '-'}</TableCell>
                <TableCell>
                  <Badge
                    variant={log.status === 0 ? 'default' : 'destructive'}
                  >
                    {log.status === 0 ? '成功' : '失败'}
                  </Badge>
                </TableCell>
                <TableCell>
                  <span
                    className='block max-w-60 truncate'
                    title={log.msg ?? ''}
                  >
                    {log.msg || '-'}
                  </span>
                </TableCell>
                <TableCell>{formatDateTime(log.loginTime)}</TableCell>
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>
    </div>
  )
}
