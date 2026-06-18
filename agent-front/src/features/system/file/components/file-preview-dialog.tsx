import { useEffect, useState } from 'react'
import { Download } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { fetchBlob } from '../api'
import { canPreview, type SysFile } from '../model'

type Props = {
  file: SysFile | null
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function FilePreviewDialog({ file, open, onOpenChange }: Props) {
  const [objectUrl, setObjectUrl] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    let disposed = false
    let createdUrl: string | null = null

    async function load() {
      if (!file || !open || !canPreview(file.extension)) {
        return
      }
      try {
        setLoading(true)
        const blob = await fetchBlob(file.id, 'preview')
        if (disposed) return
        createdUrl = URL.createObjectURL(blob)
        setObjectUrl(createdUrl)
      } catch {
        toast.error('预览加载失败')
      } finally {
        if (!disposed) setLoading(false)
      }
    }

    load()

    return () => {
      disposed = true
      if (createdUrl) URL.revokeObjectURL(createdUrl)
      setObjectUrl(null)
    }
  }, [file, open])

  async function handleDownload() {
    if (!file) return
    try {
      const blob = await fetchBlob(file.id, 'download')
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = file.originalName
      link.click()
      URL.revokeObjectURL(url)
    } catch {
      toast.error('下载失败')
    }
  }

  const isImage = file
    ? ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'ico'].includes(
        file.extension
      )
    : false
  const isPdf = file?.extension === 'pdf'

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='max-w-3xl'>
        <DialogHeader>
          <DialogTitle className='truncate'>
            {file?.originalName ?? '文件预览'}
          </DialogTitle>
        </DialogHeader>

        <div className='flex min-h-[320px] items-center justify-center overflow-auto rounded border bg-muted/30'>
          {loading ? (
            <span className='text-sm text-muted-foreground'>加载中…</span>
          ) : !file ? null : !canPreview(file.extension) ? (
            <div className='flex flex-col items-center gap-2 p-6 text-sm text-muted-foreground'>
              该类型不支持在线预览
              <Button variant='outline' size='sm' onClick={handleDownload}>
                <Download className='mr-1 size-4' />
                下载查看
              </Button>
            </div>
          ) : objectUrl && isImage ? (
            <img
              src={objectUrl}
              alt={file.originalName}
              className='max-h-[70vh] max-w-full object-contain'
            />
          ) : objectUrl && isPdf ? (
            <iframe
              title={file.originalName}
              src={objectUrl}
              className='h-[70vh] w-full border-0'
            />
          ) : null}
        </div>

        <DialogFooter>
          <Button variant='outline' onClick={handleDownload} disabled={!file}>
            <Download className='mr-1 size-4' />
            下载
          </Button>
          <Button onClick={() => onOpenChange(false)}>关闭</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
