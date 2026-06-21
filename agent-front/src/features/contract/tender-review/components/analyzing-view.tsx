import { Brain, Loader2 } from 'lucide-react'
import { useEffect, useRef } from 'react'
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'

/**
 * 第三步「开始分析」过程界面。
 *
 * 点击「开始分析」后乐观立即跳到此界面（不等文件上传/后端受理完成），展示分析进度，
 * 并预留 SSE 流式输出区——后期接入后端 SSE，实时展示 AI 评标分析过程（逐项扣分/证据定位）。
 */
export function AnalyzingView({
  progress,
  progressText,
  title,
}: {
  progress: number
  progressText?: string
  title?: string
}) {
  const scrollRef = useRef<HTMLDivElement>(null)
  // 思考流式：新进度到达时自动滚到底，始终展示最新分析片段。
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [progressText])

  return (
    <div className='space-y-4'>
      <Card>
        <CardHeader>
          <CardTitle className='flex items-center gap-2'>
            <Loader2 className='size-5 animate-spin text-primary' />
            正在分析{title ? `：${title}` : ''}
          </CardTitle>
        </CardHeader>
        <CardContent className='space-y-5'>
          <div className='space-y-2'>
            <div className='flex justify-between text-sm'>
              <span className='text-muted-foreground'>分析进度</span>
              <span className='font-semibold text-primary'>{progress}%</span>
            </div>
            <div className='h-2 overflow-hidden rounded-full bg-muted'>
              <div
                className='h-full rounded-full bg-primary transition-all'
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>

          {/* SSE 流式输出预留区 —— 后期接入后端 SSE event stream，实时滚动展示分析过程 */}
          <div className='rounded-lg border bg-muted/30'>
            <div className='flex items-center gap-2 border-b px-4 py-2 text-sm font-medium'>
              <Brain className='size-4 text-primary' />
              实时分析输出
            </div>
            <div
              ref={scrollRef}
              className='max-h-80 min-h-32 overflow-auto whitespace-pre-wrap px-4 py-3 font-mono text-xs leading-relaxed text-muted-foreground'
            >
              {progressText?.trim()
                ? progressText
                : '分析进行中，等待 AI 评标实时输出…'}
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
