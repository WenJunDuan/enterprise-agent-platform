import {
  Download as DownloadIcon,
  Eye,
  FileIcon,
  Trash2,
} from 'lucide-react'
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
import {
  BIZ_TYPE_OPTIONS,
  canPreview,
  formatFileSize,
  type SysFile,
} from '../model'

function formatDateTime(value: string | null) {
  if (!value) return '-'
  return value.replace('T', ' ').slice(0, 19)
}

function bizTypeLabel(value: string | null) {
  if (!value) return '-'
  return BIZ_TYPE_OPTIONS.find((opt) => opt.value === value)?.label ?? value
}

type Props = {
  records: SysFile[]
  selectedIds: Set<string>
  isLoading: boolean
  allowSelection: boolean
  canDelete: boolean
  canDownload: boolean
  onToggleSelectAll: (checked: boolean) => void
  onToggleSelect: (id: string) => void
  onPreview: (file: SysFile) => void
  onDownload: (file: SysFile) => void
  onDelete: (file: SysFile) => void
}

export function FileTable({
  records,
  selectedIds,
  isLoading,
  allowSelection,
  canDelete,
  canDownload,
  onToggleSelectAll,
  onToggleSelect,
  onPreview,
  onDownload,
  onDelete,
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
                  aria-label='全选当前页文件'
                  className='translate-y-[2px]'
                />
              </TableHead>
            ) : null}
            <TableHead>文件名</TableHead>
            <TableHead className='w-24'>类型</TableHead>
            <TableHead className='w-28'>大小</TableHead>
            <TableHead className='w-32'>业务类型</TableHead>
            <TableHead className='w-44'>上传时间</TableHead>
            <TableHead className='w-40 text-right'>操作</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {isLoading ? (
            <TableRow>
              <TableCell colSpan={allowSelection ? 7 : 6} className='text-center text-sm'>
                加载中...
              </TableCell>
            </TableRow>
          ) : records.length === 0 ? (
            <TableRow>
              <TableCell
                colSpan={allowSelection ? 7 : 6}
                className='text-center text-sm text-muted-foreground'
              >
                暂无数据
              </TableCell>
            </TableRow>
          ) : (
            records.map((file) => (
              <TableRow key={file.id}>
                {allowSelection ? (
                  <TableCell>
                    <Checkbox
                      checked={selectedIds.has(file.id)}
                      onCheckedChange={() => onToggleSelect(file.id)}
                      aria-label='选择当前文件'
                      className='translate-y-[2px]'
                    />
                  </TableCell>
                ) : null}
                <TableCell>
                  <div className='flex items-center gap-2'>
                    <FileIcon className='size-4 text-muted-foreground' />
                    <span
                      className='max-w-80 truncate'
                      title={file.originalName}
                    >
                      {file.originalName}
                    </span>
                  </div>
                </TableCell>
                <TableCell>
                  <Badge variant='outline' className='uppercase'>
                    {file.extension || '-'}
                  </Badge>
                </TableCell>
                <TableCell>{formatFileSize(file.size)}</TableCell>
                <TableCell>{bizTypeLabel(file.bizType)}</TableCell>
                <TableCell>{formatDateTime(file.uploadTime)}</TableCell>
                <TableCell className='text-right'>
                  <div className='flex justify-end gap-1'>
                    {canPreview(file.extension) ? (
                      <Button
                        size='sm'
                        variant='ghost'
                        onClick={() => onPreview(file)}
                      >
                        <Eye className='size-4' />
                      </Button>
                    ) : null}
                    {canDownload ? (
                      <Button
                        size='sm'
                        variant='ghost'
                        onClick={() => onDownload(file)}
                      >
                        <DownloadIcon className='size-4' />
                      </Button>
                    ) : null}
                    {canDelete ? (
                      <Button
                        size='sm'
                        variant='ghost'
                        onClick={() => onDelete(file)}
                      >
                        <Trash2 className='size-4 text-destructive' />
                      </Button>
                    ) : null}
                  </div>
                </TableCell>
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>
    </div>
  )
}
