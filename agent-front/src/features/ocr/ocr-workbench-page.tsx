import { useEffect, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { FileSearch, FileUp, Loader2, Play, Sparkles, X } from 'lucide-react'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
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
import { getOcrJob, submitOcrJob } from '@/features/audit/api'
import type {
  FormFillResult,
  OcrExtractItem,
  OcrJobUnit,
} from '@/features/audit/types'
import {
  deriveOcrJobPhase,
  groupUnitsByFile,
  ocrJobRefetchInterval,
  unitDisplayText,
  unitErrorText,
  type OcrJobFileGroup,
  type OcrJobPhase,
} from './workbench/job-model'
import { MOCK_EXTRACT_ITEMS, MOCK_FORM_FILL } from './workbench/mock-data'
import {
  CONFIDENCE_STYLE,
  ROUTE_STYLE,
  confidenceLevel,
  formatFieldValue,
  nextFileId,
  type OcrUploadFile,
} from './workbench/shared'

const IN_PROGRESS_PHASES = new Set<OcrJobPhase>([
  'submitting',
  'queued',
  'running',
])

function isBusyPhase(phase: OcrJobPhase): boolean {
  return IN_PROGRESS_PHASES.has(phase)
}

function UploadCard({
  files,
  phase,
  onAddFiles,
  onRemoveFile,
  onRecognize,
  onLoadSample,
}: {
  files: OcrUploadFile[]
  phase: OcrJobPhase
  onAddFiles: (files: FileList | null) => void
  onRemoveFile: (id: string) => void
  onRecognize: () => void
  onLoadSample: () => void
}) {
  const busy = isBusyPhase(phase)
  return (
    <Card>
      <CardHeader>
        <CardTitle>文档上传</CardTitle>
        <CardDescription>
          上传合同、PDF、Excel 或图片后按页渐进识别。
        </CardDescription>
      </CardHeader>
      <CardContent className='space-y-4'>
        <label className='flex min-h-40 cursor-pointer flex-col items-center justify-center gap-3 rounded-lg border border-dashed bg-muted/20 p-6 text-center'>
          <FileUp className='size-8 text-muted-foreground' />
          <span className='font-medium'>选择待识别文件</span>
          <span className='text-sm text-muted-foreground'>
            选择文件后开始识别。
          </span>
          <input
            multiple
            type='file'
            className='hidden'
            onChange={(event) => onAddFiles(event.target.files)}
          />
        </label>

        <div className='flex items-center justify-between gap-3'>
          <Button disabled={busy} onClick={onRecognize}>
            <Play className='size-4' />
            {busy ? '识别中' : '开始识别'}
          </Button>
          <Button variant='outline' onClick={onLoadSample} disabled={busy}>
            <Sparkles className='size-4' />
            加载示例
          </Button>
        </div>

        <div className='space-y-2'>
          {files.length === 0 ? (
            <div className='rounded-md border p-4 text-sm text-muted-foreground'>
              暂无文件。
            </div>
          ) : (
            files.map((file) => (
              <div
                key={file.id}
                className='flex items-center justify-between gap-3 rounded-md border p-3'
              >
                <div className='min-w-0'>
                  <div className='truncate font-medium'>{file.name}</div>
                  <div className='text-xs text-muted-foreground'>
                    {file.status}
                  </div>
                </div>
                <Button
                  variant='ghost'
                  size='icon'
                  aria-label='移除文件'
                  onClick={() => onRemoveFile(file.id)}
                >
                  <X className='size-4' />
                </Button>
              </div>
            ))
          )}
        </div>
      </CardContent>
    </Card>
  )
}

/** 「加载示例」演示专用：复用同步 /ocr/fill 响应形态渲染（保留原有整文件识别底稿展示）。 */
function MockExtractPanel({ items }: { items: OcrExtractItem[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>识别底稿（示例）</CardTitle>
        <CardDescription>
          按文件展示直读、OCR、转人工或错误状态。
        </CardDescription>
      </CardHeader>
      <CardContent className='space-y-3'>
        {items.map((item, index) => {
          const route = item.route ? ROUTE_STYLE[item.route] : null
          return (
            <div
              key={`${item.path}-${index}`}
              className='space-y-3 rounded-md border p-4'
            >
              <div className='flex flex-wrap items-center justify-between gap-2'>
                <div className='min-w-0'>
                  <div className='truncate font-medium'>{item.path}</div>
                  <div className='text-xs text-muted-foreground'>
                    {item.kind}
                  </div>
                </div>
                {route ? (
                  <Badge className={`${route.bg} ${route.text}`}>
                    {route.label}
                  </Badge>
                ) : null}
              </div>
              {item.error ? (
                <Alert variant='destructive'>
                  <AlertDescription>{item.error}</AlertDescription>
                </Alert>
              ) : null}
              {item.note ? (
                <p className='text-sm text-muted-foreground'>{item.note}</p>
              ) : null}
              {item.blocks?.length ? (
                <pre className='max-h-48 overflow-auto rounded-md bg-muted/40 p-3 text-xs'>
                  {item.blocks.join('\n\n')}
                </pre>
              ) : null}
              {item.tables?.length ? (
                <div className='text-sm text-muted-foreground'>
                  {item.tables.length} 个表格已识别
                </div>
              ) : null}
              {item.pages?.length ? (
                <div className='text-sm text-muted-foreground'>
                  {item.pages.length} 页 OCR Markdown
                </div>
              ) : null}
            </div>
          )
        })}
      </CardContent>
    </Card>
  )
}

function JobUnitBlock({ unit }: { unit: OcrJobUnit }) {
  const payload = unit.payload ?? {}
  const errorText = unitErrorText(payload)
  const content = unitDisplayText(payload)
  const label = unit.page != null ? `第 ${unit.page} 页` : '整份文件'
  return (
    <div className='space-y-2'>
      <div className='flex items-center gap-2 text-xs text-muted-foreground'>
        <span>{label}</span>
        {unit.status === 'error' ? (
          <Badge variant='destructive'>识别失败</Badge>
        ) : null}
        {unit.from_cache ? <Badge variant='outline'>命中缓存</Badge> : null}
      </div>
      {errorText ? (
        <Alert variant='destructive'>
          <AlertDescription>{errorText}</AlertDescription>
        </Alert>
      ) : content ? (
        <pre className='max-h-48 overflow-auto rounded-md bg-muted/40 p-3 text-xs'>
          {content}
        </pre>
      ) : (
        <p className='text-sm text-muted-foreground'>暂无可展示文本。</p>
      )}
    </div>
  )
}

function JobFileGroupCard({ group }: { group: OcrJobFileGroup }) {
  return (
    <div className='space-y-3 rounded-md border p-4'>
      <div className='truncate font-medium'>{group.file}</div>
      {group.units.map((unit, index) => (
        <JobUnitBlock
          key={`${group.file}-${unit.page ?? 'file'}-${index}`}
          unit={unit}
        />
      ))}
    </div>
  )
}

/** 页级流式识别底稿：来一个 unit 就渲一个（partial），不等全部完成；四态显式处理（ui-guidelines）。 */
function JobResultsPanel({
  phase,
  progress,
  errorDetail,
  fileGroups,
  onRetry,
}: {
  phase: OcrJobPhase
  progress: { done: number; total: number } | null
  errorDetail: string | null
  fileGroups: OcrJobFileGroup[]
  onRetry: () => void
}) {
  const loading = isBusyPhase(phase)
  const loadingLabel =
    phase === 'submitting'
      ? '提交中…'
      : phase === 'queued'
        ? '排队中…'
        : '识别中…'

  return (
    <Card>
      <CardHeader>
        <CardTitle>识别底稿</CardTitle>
        <CardDescription>
          按文件 / 页渐进展示识别结果，页锚原样保真，不等全部完成再显示。
        </CardDescription>
      </CardHeader>
      <CardContent className='space-y-3'>
        {loading ? (
          <div
            role='status'
            className='flex items-center gap-2 text-sm text-muted-foreground'
          >
            <Loader2 className='size-4 animate-spin' aria-hidden='true' />
            <span>
              {loadingLabel}
              {progress ? `（已完成 ${progress.done}/${progress.total}）` : ''}
            </span>
          </div>
        ) : null}

        {phase === 'failed' ? (
          <Alert variant='destructive'>
            <FileSearch className='size-4' />
            <AlertTitle>识别失败</AlertTitle>
            <AlertDescription className='space-y-2'>
              <p>{errorDetail ?? '任务未找到或已失效，请重新识别。'}</p>
              <Button size='sm' variant='outline' onClick={onRetry}>
                重试
              </Button>
            </AlertDescription>
          </Alert>
        ) : null}

        {fileGroups.length === 0 ? (
          phase === 'completed' ? (
            <div className='rounded-md border p-4 text-sm text-muted-foreground'>
              未识别到内容，请检查上传文件是否有效。
            </div>
          ) : phase === 'idle' ? (
            <div className='rounded-md border p-4 text-sm text-muted-foreground'>
              暂无识别结果。
            </div>
          ) : null
        ) : (
          fileGroups.map((group) => (
            <JobFileGroupCard key={group.file} group={group} />
          ))
        )}
      </CardContent>
    </Card>
  )
}

function FillPanel({
  fill,
  isMock,
}: {
  fill: FormFillResult | null
  isMock: boolean
}) {
  if (!fill) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>回填结果</CardTitle>
          <CardDescription>
            {isMock
              ? '识别后展示字段置信度和付款节点子表。'
              : '当前页面为纯识别渐进渲染，/ocr/jobs 暂不做表单回填。'}
          </CardDescription>
        </CardHeader>
        <CardContent className='rounded-md border p-4 text-sm text-muted-foreground'>
          暂无回填结果。
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader className='gap-3 md:flex-row md:items-start md:justify-between'>
        <div>
          <CardTitle>回填结果</CardTitle>
          <CardDescription>
            {fill.form_id
              ? `表单 ID：${fill.form_id}`
              : '根据文档内容自适应抽取'}
          </CardDescription>
        </div>
        {fill.needs_review ? (
          <Badge variant='secondary'>需复核</Badge>
        ) : (
          <Badge variant='outline'>可用</Badge>
        )}
      </CardHeader>
      <CardContent className='space-y-5'>
        {fill.low_confidence?.length ? (
          <Alert>
            <AlertTitle>低置信字段</AlertTitle>
            <AlertDescription>
              {fill.low_confidence.join('、')}
            </AlertDescription>
          </Alert>
        ) : null}

        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>字段</TableHead>
              <TableHead>值</TableHead>
              <TableHead>置信度</TableHead>
              <TableHead>来源</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {fill.fields.map((field) => {
              const style = CONFIDENCE_STYLE[confidenceLevel(field.confidence)]
              return (
                <TableRow key={field.key}>
                  <TableCell className='font-medium'>{field.key}</TableCell>
                  <TableCell>{formatFieldValue(field.value)}</TableCell>
                  <TableCell>
                    <Badge className={`${style.bg} ${style.text}`}>
                      {style.label} {(field.confidence * 100).toFixed(0)}%
                    </Badge>
                  </TableCell>
                  <TableCell className='text-muted-foreground'>
                    {field.source || '-'}
                  </TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>

        {fill.sub_tables.map((table) => (
          <div key={table.key} className='space-y-2'>
            <div className='font-medium'>{table.key}</div>
            <Table>
              <TableHeader>
                <TableRow>
                  {(table.columns ?? Object.keys(table.rows[0] ?? {})).map(
                    (column) => (
                      <TableHead key={column}>{column}</TableHead>
                    )
                  )}
                </TableRow>
              </TableHeader>
              <TableBody>
                {table.rows.map((row, index) => (
                  <TableRow key={index}>
                    {(table.columns ?? Object.keys(row)).map((column) => (
                      <TableCell key={column}>
                        {formatFieldValue(row[column])}
                      </TableCell>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        ))}

        {fill.evidence?.length ? (
          <div className='space-y-2'>
            <div className='font-medium'>证据</div>
            {fill.evidence.map((item, index) => (
              <div key={index} className='rounded-md border p-3 text-sm'>
                <div className='font-medium'>{item.source}</div>
                <div className='text-muted-foreground'>{item.finding}</div>
              </div>
            ))}
          </div>
        ) : null}
      </CardContent>
    </Card>
  )
}

export function OcrWorkbenchPage() {
  const [files, setFiles] = useState<OcrUploadFile[]>([])
  const [jobId, setJobId] = useState<string | null>(null)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [mockItems, setMockItems] = useState<OcrExtractItem[]>([])
  const [mockFill, setMockFill] = useState<FormFillResult | null>(null)

  const submitMutation = useMutation({ mutationFn: submitOcrJob })

  const jobQuery = useQuery({
    queryKey: ['ocr-job', jobId],
    // 未知/跨租户 request_id → 404；轮询函数吞掉错误归一为 null，交 deriveOcrJobPhase/
    // ocrJobRefetchInterval 当终态处理（继承 tender-review activeEvalQuery 先例）。
    queryFn: () => getOcrJob(jobId as string).catch(() => null),
    enabled: Boolean(jobId),
    refetchInterval: (query) => ocrJobRefetchInterval(query.state.data),
  })

  const phase = deriveOcrJobPhase({
    isSubmitting: submitMutation.isPending,
    jobId,
    jobData: jobQuery.data,
  })
  const fileGroups = groupUnitsByFile(jobQuery.data?.results ?? [])

  // 轮询状态 → 文件行状态同步（外部数据驱动 UI 展示，非用户交互触发，理由同
  // use-tender-review-page.ts activeEvalQuery 的响应 effect）。
  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    if (phase === 'completed') {
      setFiles((current) =>
        current.map((file) => ({ ...file, status: 'done' }))
      )
    } else if (phase === 'failed') {
      setFiles((current) =>
        current.map((file) => ({ ...file, status: 'error' }))
      )
    }
  }, [phase])
  /* eslint-enable react-hooks/set-state-in-effect */

  function addFiles(fileList: FileList | null) {
    if (!fileList) return
    setFiles((current) => [
      ...current,
      ...Array.from(fileList).map((file) => ({
        id: nextFileId(),
        name: file.name,
        size: file.size,
        status: 'pending' as const,
        file,
      })),
    ])
  }

  function removeFile(id: string) {
    setFiles((current) => current.filter((file) => file.id !== id))
  }

  async function recognize() {
    const realFiles = files
      .map((file) => file.file)
      .filter((file): file is File => Boolean(file))
    if (realFiles.length === 0) {
      setSubmitError('请先选择真实文件，或使用“加载示例”预览。')
      return
    }

    setSubmitError(null)
    setMockItems([])
    setMockFill(null)
    setJobId(null)
    setFiles((current) =>
      current.map((file) => ({ ...file, status: 'recognizing' }))
    )

    try {
      const accepted = await submitMutation.mutateAsync(realFiles)
      setJobId(accepted.request_id)
    } catch (recognizeError) {
      setSubmitError(
        recognizeError instanceof Error
          ? recognizeError.message
          : '识别提交失败'
      )
      setFiles((current) =>
        current.map((file) => ({ ...file, status: 'error' }))
      )
    }
  }

  function loadSample() {
    setSubmitError(null)
    setJobId(null)
    setMockItems(MOCK_EXTRACT_ITEMS)
    setMockFill(MOCK_FORM_FILL)
    setFiles(
      MOCK_EXTRACT_ITEMS.map((item) => ({
        id: nextFileId(),
        name: item.path.split('/').pop() || item.path,
        size: 0,
        status: 'done' as const,
        route: item.route,
      }))
    )
  }

  const isMock = mockItems.length > 0

  return (
    <>
      <Header fixed />
      <Main className='space-y-5'>
        <div>
          <h1 className='text-2xl font-semibold tracking-tight'>OCR 识别</h1>
          <p className='text-sm text-muted-foreground'>
            上传材料后按页渐进生成识别底稿。
          </p>
        </div>

        {submitError ? (
          <Alert variant='destructive'>
            <FileSearch className='size-4' />
            <AlertTitle>提交失败</AlertTitle>
            <AlertDescription>{submitError}</AlertDescription>
          </Alert>
        ) : null}

        <div className='grid gap-4 xl:grid-cols-[420px_1fr]'>
          <div className='space-y-4'>
            <UploadCard
              files={files}
              phase={phase}
              onAddFiles={addFiles}
              onRemoveFile={removeFile}
              onRecognize={() => void recognize()}
              onLoadSample={loadSample}
            />
            {isMock ? (
              <MockExtractPanel items={mockItems} />
            ) : (
              <JobResultsPanel
                phase={phase}
                progress={jobQuery.data?.progress ?? null}
                errorDetail={jobQuery.data?.error_detail ?? null}
                fileGroups={fileGroups}
                onRetry={() => void recognize()}
              />
            )}
          </div>
          <FillPanel fill={mockFill} isMock={isMock} />
        </div>
      </Main>
    </>
  )
}
