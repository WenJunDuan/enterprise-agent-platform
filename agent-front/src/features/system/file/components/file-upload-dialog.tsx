import { useRef, useState } from 'react'
import type { AxiosError } from 'axios'
import { Upload } from 'lucide-react'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { uploadFile } from '../api'
import { BIZ_TYPE_OPTIONS } from '../model'

const MAX_MB = 100

type Props = {
  open: boolean
  onOpenChange: (open: boolean) => void
  onUploaded: () => void
  defaultBizType?: string
  defaultBizId?: string
}

export function FileUploadDialog({
  open,
  onOpenChange,
  onUploaded,
  defaultBizType = 'other',
  defaultBizId,
}: Props) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [bizType, setBizType] = useState<string>(defaultBizType)
  const [bizId, setBizId] = useState<string>(defaultBizId ?? '')
  const [dragOver, setDragOver] = useState(false)
  const [progress, setProgress] = useState(0)
  const [uploading, setUploading] = useState(false)

  function resetState() {
    setFile(null)
    setProgress(0)
    setUploading(false)
    setBizType(defaultBizType)
    setBizId(defaultBizId ?? '')
    if (inputRef.current) inputRef.current.value = ''
  }

  function handleSelect(selected: File | null) {
    if (!selected) return
    if (selected.size > MAX_MB * 1024 * 1024) {
      toast.error(`文件超出 ${MAX_MB}MB 限制`)
      return
    }
    setFile(selected)
  }

  async function handleUpload() {
    if (!file) {
      toast.error('请选择文件')
      return
    }
    try {
      setUploading(true)
      await uploadFile({
        file,
        bizType,
        bizId: bizId.trim() || undefined,
        onProgress: setProgress,
      })
      toast.success('上传成功')
      resetState()
      onOpenChange(false)
      onUploaded()
    } catch (err) {
      const message =
        (err as AxiosError<{ msg?: string }>)?.response?.data?.msg ??
        '上传失败'
      toast.error(message)
    } finally {
      setUploading(false)
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) resetState()
        onOpenChange(next)
      }}
    >
      <DialogContent className='sm:max-w-lg'>
        <DialogHeader>
          <DialogTitle>上传文件</DialogTitle>
        </DialogHeader>

        <div
          className={cn(
            'flex flex-col items-center justify-center gap-2 rounded-md border-2 border-dashed p-6 text-center',
            dragOver ? 'border-primary bg-primary/5' : 'border-muted'
          )}
          onDragOver={(e) => {
            e.preventDefault()
            setDragOver(true)
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => {
            e.preventDefault()
            setDragOver(false)
            if (uploading) return
            handleSelect(e.dataTransfer.files?.[0] ?? null)
          }}
          onClick={() => inputRef.current?.click()}
          role='button'
        >
          <Upload className='size-8 text-muted-foreground' />
          {file ? (
            <span className='text-sm font-medium'>{file.name}</span>
          ) : (
            <span className='text-sm text-muted-foreground'>
              点击选择或拖拽文件到此处
            </span>
          )}
          <span className='text-xs text-muted-foreground'>
            最大 {MAX_MB}MB · 禁止 exe/bat/sh 等危险类型
          </span>
          <input
            ref={inputRef}
            type='file'
            className='hidden'
            onChange={(e) => handleSelect(e.target.files?.[0] ?? null)}
          />
        </div>

        <div className='grid grid-cols-2 gap-3'>
          <div className='flex flex-col gap-1.5'>
            <Label htmlFor='bizType'>业务类型</Label>
            <select
              id='bizType'
              className='h-9 rounded-md border bg-background px-3 text-sm'
              value={bizType}
              onChange={(e) => setBizType(e.target.value)}
            >
              {BIZ_TYPE_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          <div className='flex flex-col gap-1.5'>
            <Label htmlFor='bizId'>业务 ID (可选)</Label>
            <Input
              id='bizId'
              value={bizId}
              onChange={(e) => setBizId(e.target.value)}
              placeholder='关联业务对象 ID'
            />
          </div>
        </div>

        {uploading ? (
          <div className='flex items-center gap-2'>
            <div className='h-2 flex-1 overflow-hidden rounded-full bg-muted'>
              <div
                className='h-full bg-primary transition-all'
                style={{ width: `${progress}%` }}
              />
            </div>
            <span className='w-10 text-right text-xs text-muted-foreground'>
              {progress}%
            </span>
          </div>
        ) : null}

        <DialogFooter>
          <Button
            variant='outline'
            onClick={() => onOpenChange(false)}
            disabled={uploading}
          >
            取消
          </Button>
          <Button onClick={handleUpload} disabled={uploading || !file}>
            {uploading ? '上传中…' : '上传'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
