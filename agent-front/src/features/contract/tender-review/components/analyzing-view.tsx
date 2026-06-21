import { Brain, FileText, Info, Loader2 } from 'lucide-react'
import { useEffect, useRef } from 'react'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import type { DocsStatusResponse } from '../api'
import type { ProjectFormData } from './create-review-view'

/**
 * 第三步「开始分析」过程界面 — 三区布局（P3 设计）。
 *
 * 区1（左上）基本信息：项目名/编号/控制价/资金类型（来自 projectForm）。
 * 区2（左下）OCR 识别区：招标 criteria / 投标审核要点（来自 docsStatus 或未来评标结论）。
 * 区3（右）投标公司文档：只展示评标流式输出（progressByRid 进度）+ 评标完成后逐项得分。
 *
 * 布局：左（区1+2）|右（区3 流式），自适应宽屏；窄屏上下堆叠。
 */
export function AnalyzingView({
  progress,
  progressText,
  title,
  projectForm,
  docsStatus,
  onExit,
}: {
  progress: number
  progressText?: string
  title?: string
  projectForm?: ProjectFormData | null
  docsStatus?: DocsStatusResponse | null
  onExit?: () => void
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
      {/* 进度条（全宽） */}
      <Card>
        <CardHeader>
          <div className='flex items-center justify-between gap-2'>
            <CardTitle className='flex items-center gap-2'>
              <Loader2 className='size-5 animate-spin text-primary' />
              正在分析{title ? `：${title}` : ''}
            </CardTitle>
            {onExit ? (
              <Button variant='outline' size='sm' onClick={onExit}>
                返回列表
              </Button>
            ) : null}
          </div>
          <p className='mt-2 text-xs text-muted-foreground'>
            评标在后台继续，可随时返回列表查看或停止删除；本页不会因超时退出。
          </p>
        </CardHeader>
        <CardContent>
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
        </CardContent>
      </Card>

      {/* 三区主体：左（区1+2）右（区3） */}
      <div className='grid gap-4 xl:grid-cols-[minmax(300px,2fr)_minmax(400px,3fr)]'>
        {/* ─ 左栏：区1 基本信息 + 区2 OCR 识别区 ─ */}
        <div className='space-y-4'>
          {/* 区1：基本信息 */}
          <Zone1ProjectInfo projectForm={projectForm} />
          {/* 区2：OCR 识别区 */}
          <Zone2OcrOverview docsStatus={docsStatus} />
        </div>

        {/* ─ 右栏：区3 投标公司文档（流式输出） ─ */}
        <Zone3StreamOutput progressText={progressText} scrollRef={scrollRef} />
      </div>
    </div>
  )
}

/**
 * 区1：项目基本信息（项目名/编号/控制价/资金类型）。
 */
function Zone1ProjectInfo({ projectForm }: { projectForm?: ProjectFormData | null }) {
  const fundingLabel: Record<string, string> = {
    state_funded: '国资',
    other: '其他',
    unknown: '未知',
  }
  const rows = [
    { label: '项目名称', value: projectForm?.title },
    { label: '招标编号', value: projectForm?.tender_no },
    { label: '招标人', value: projectForm?.tenderee },
    { label: '评标方法', value: projectForm?.method },
    { label: '控制价', value: projectForm?.control_price },
    {
      label: '资金来源',
      value: projectForm?.funding_type
        ? (fundingLabel[projectForm.funding_type] ?? projectForm.funding_type)
        : undefined,
    },
  ].filter((row) => row.value?.trim())

  return (
    <Card>
      <CardHeader className='pb-3'>
        <CardTitle className='flex items-center gap-2 text-base'>
          <Info className='size-4 text-primary' />
          区1 基本信息
        </CardTitle>
      </CardHeader>
      <CardContent>
        {rows.length > 0 ? (
          <dl className='grid gap-2 text-sm'>
            {rows.map((row) => (
              <div key={row.label} className='grid grid-cols-[6rem_1fr] gap-x-2'>
                <dt className='text-muted-foreground'>{row.label}</dt>
                <dd className='font-medium'>{row.value}</dd>
              </div>
            ))}
          </dl>
        ) : (
          <p className='text-sm text-muted-foreground'>项目信息未填写。</p>
        )}
      </CardContent>
    </Card>
  )
}

/**
 * 区2：OCR 识别区 — 展示招标层已识别的文件列表 / 投标文件概况。
 *
 * OCR 完成后即可展示（不等评标）。criteria 解析结果在评标完成后可在 analysis 界面查看。
 */
function Zone2OcrOverview({ docsStatus }: { docsStatus?: DocsStatusResponse | null }) {
  return (
    <Card>
      <CardHeader className='pb-3'>
        <CardTitle className='flex items-center gap-2 text-base'>
          <FileText className='size-4 text-primary' />
          区2 OCR 识别区
        </CardTitle>
      </CardHeader>
      <CardContent>
        {docsStatus ? (
          <div className='space-y-3 text-sm'>
            {/* 招标文件状态 */}
            <div className='space-y-1'>
              <div className='font-medium text-muted-foreground'>招标文件</div>
              <div className='flex items-center gap-2'>
                <OcrDot status={docsStatus.tender_doc?.ocr_status ?? 'pending'} />
                <span>
                  {docsStatus.tender_doc
                    ? ocrStatusLabel(docsStatus.tender_doc.ocr_status)
                    : '未上传'}
                </span>
              </div>
            </div>
            {/* 投标文件状态 */}
            {docsStatus.bids.length > 0 ? (
              <div className='space-y-1'>
                <div className='font-medium text-muted-foreground'>
                  投标文件（{docsStatus.bids.length} 家）
                </div>
                {docsStatus.bids.map((bid) => (
                  <div key={bid.bid_id} className='flex items-center gap-2'>
                    <OcrDot status={bid.ocr_status} />
                    <span className='truncate'>{bid.bidder_name ?? bid.bid_id}</span>
                    <span className='shrink-0 text-muted-foreground'>
                      {ocrStatusLabel(bid.ocr_status)}
                    </span>
                  </div>
                ))}
              </div>
            ) : null}
            <p className='rounded-lg bg-muted/40 px-3 py-2 text-xs text-muted-foreground'>
              评分标准（criteria）将在评标完成后展示于分析中心。
            </p>
          </div>
        ) : (
          <p className='text-sm text-muted-foreground'>
            OCR 状态加载中，或本次提交使用旧路径（暂无 OCR 层数据）。
          </p>
        )}
      </CardContent>
    </Card>
  )
}

function OcrDot({ status }: { status: string }) {
  const colorClass =
    status === 'ready'
      ? 'bg-emerald-500'
      : status === 'failed'
        ? 'bg-red-500'
        : 'bg-blue-400 animate-pulse'
  return <span className={`size-2 shrink-0 rounded-full ${colorClass}`} />
}

function ocrStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    pending: '等待中',
    running: '识别中',
    ready: '已就绪',
    failed: '识别失败',
  }
  return labels[status] ?? status
}

/**
 * 区3：投标公司文档 — 只展示评标流式输出（progressByRid），不展示原文。
 */
function Zone3StreamOutput({
  progressText,
  scrollRef,
}: {
  progressText?: string
  scrollRef: React.RefObject<HTMLDivElement | null>
}) {
  return (
    <Card className='flex flex-col'>
      <CardHeader className='pb-3'>
        <CardTitle className='flex items-center gap-2 text-base'>
          <Brain className='size-4 text-primary' />
          区3 投标评标实时输出
        </CardTitle>
      </CardHeader>
      <CardContent className='flex-1'>
        {/* 流式输出区：实时展示 AI 评标分析过程，自动滚到最新 */}
        <div className='rounded-lg border bg-muted/30'>
          <div className='flex items-center gap-2 border-b px-4 py-2 text-sm font-medium'>
            <Brain className='size-4 text-primary' />
            实时分析输出
          </div>
          <div
            ref={scrollRef}
            className='max-h-[calc(100vh-420px)] min-h-48 overflow-auto whitespace-pre-wrap px-4 py-3 font-mono text-xs leading-relaxed text-muted-foreground'
          >
            {progressText?.trim()
              ? progressText
              : '分析进行中，等待 AI 评标实时输出…'}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
