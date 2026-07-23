import { FileUp, X } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { formatFileSize } from '../format'
import type { EiaCategoryDef, EiaUploadFile } from '../types'

/**
 * 提交向导第一步的单个分类上传卡（水/土/气/声）。每类可多选、可留空，
 * 上传区用 `<label>` 包裹 `<input type=file>`（a11y P0：可达 label）。
 */
export function CategoryUploadCard({
  def,
  files,
  onAddFiles,
  onRemoveFile,
}: {
  def: EiaCategoryDef
  files: EiaUploadFile[]
  onAddFiles: (fileList: FileList | null) => void
  onRemoveFile: (id: string) => void
}) {
  return (
    <Card>
      <CardHeader>
        <div className='flex items-center gap-3'>
          <span className='flex size-9 flex-none items-center justify-center rounded-md border-2 border-primary text-lg font-semibold text-primary'>
            {def.glyph}
          </span>
          <div className='min-w-0 flex-1'>
            <CardTitle>{def.title}</CardTitle>
            <CardDescription>{def.hint}</CardDescription>
          </div>
          <Badge variant={files.length > 0 ? 'default' : 'outline'}>
            {files.length > 0 ? `${files.length} 个文件` : '未上传'}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className='space-y-3'>
        <label className='flex cursor-pointer items-center gap-3 rounded-md border border-dashed bg-muted/20 p-4 text-sm'>
          <FileUp className='size-4 text-muted-foreground' aria-hidden='true' />
          <span>
            点击上传，可多选
            <span className='ml-1 text-muted-foreground'>
              (选填，PDF / 图片 ≤ 50MB)
            </span>
          </span>
          <input
            multiple
            type='file'
            className='hidden'
            onChange={(event) => onAddFiles(event.target.files)}
          />
        </label>

        {files.length === 0 ? (
          <p className='text-sm text-muted-foreground'>暂未上传该类别材料。</p>
        ) : (
          <ul className='space-y-2'>
            {files.map((file) => (
              <li
                key={file.id}
                className='flex items-center gap-3 rounded-md border p-2 text-sm'
              >
                <span className='min-w-0 flex-1 truncate'>{file.name}</span>
                <span className='flex-none text-xs text-muted-foreground tabular-nums'>
                  {formatFileSize(file.size)}
                </span>
                <button
                  type='button'
                  aria-label={`移除 ${file.name}`}
                  className='flex-none rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground'
                  onClick={() => onRemoveFile(file.id)}
                >
                  <X className='size-3.5' />
                </button>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}
