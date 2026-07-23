import { useEffect, useMemo, useReducer, useRef, useState } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { Sparkles } from 'lucide-react'
import { toast } from 'sonner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
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
import { submitEiaBatch } from './api'
import { CategoryUploadCard } from './components/category-upload-card'
import { ReportCard } from './components/report-card'
import { ReportSidePanel } from './components/report-side-panel'
import { StreamConsole } from './components/stream-console'
import { formatFileSize } from './format'
import {
  EIA_CATEGORIES,
  EIA_CATEGORY_FINDINGS,
  EIA_CATEGORY_GLYPH,
  EIA_CATEGORY_STREAM_LINES,
  MOCK_EIA_SAMPLE_FILES,
} from './model/mock-data'
import {
  buildStreamScript,
  buildTrackRows,
  computeProgressPercent,
  isStreamDone,
  visibleLines,
} from './model/stream-script'
import {
  createInitialEiaWizardState,
  eiaWizardReducer,
  getActiveCategories,
  getTotalFileCount,
  isStep1Blocked,
} from './model/wizard-state'
import type { EiaCategory, EiaReport } from './types'

// 流式推进节奏：每 45ms 前进 5 个字符，仿静态稿 streamSpeed=1 的默认速度。
const STREAM_TICK_MS = 45
const STREAM_CHARS_PER_TICK = 5

const STEP_DEFS = [
  { step: 1, title: '分类上传材料', sub: '水 · 土 · 气 · 声，均为选填' },
  { step: 2, title: '确认提交', sub: '核对各类材料清单' },
  { step: 3, title: 'AI 分析出报告', sub: '实时过程 · 按类别逐份下载' },
] as const

let fileIdCounter = 0
/** 生成稳定的本地文件行 id（仅前端列表渲染用，仿 ocr/workbench/shared.ts nextFileId）。 */
function nextFileId(): string {
  fileIdCounter += 1
  return `eia-file-${Date.now()}-${fileIdCounter}`
}

function buildReports(
  activeCategories: EiaCategory[],
  batchNo: string
): EiaReport[] {
  return activeCategories.map((category, index) => {
    const findings = EIA_CATEGORY_FINDINGS[category]
    return {
      category,
      title: `${EIA_CATEGORY_GLYPH[category]}类`,
      no: `${batchNo}-${String(index + 1).padStart(2, '0')}`,
      verdict: findings.verdict,
      findings: findings.rows,
      summary: findings.summary,
    }
  })
}

export function EiaSubmitPage() {
  const navigate = useNavigate()
  const [state, dispatch] = useReducer(
    eiaWizardReducer,
    undefined,
    createInitialEiaWizardState
  )
  const [batchNo, setBatchNo] = useState('')

  // 受理编号经 api.ts 的 mock 接缝下发（真实后端接线后改由响应带回），页面层不再自己造号。
  useEffect(() => {
    void submitEiaBatch([]).then((result) => setBatchNo(result.batchNo))
  }, [])

  const activeCategories = getActiveCategories(state.files)
  const totalFiles = getTotalFileCount(state.files)
  const step1Blocked = isStep1Blocked(state.files)
  const activeCategoriesKey = activeCategories.join(',')

  const script = useMemo(
    () =>
      buildStreamScript(activeCategories, EIA_CATEGORY_STREAM_LINES, totalFiles),
    // activeCategories 每次 render 都是新数组；用固定顺序拼接的 key 做依赖，脚本只在
    // 激活类别集合或材料总数真正变化时重建，analyzing 阶段的 chars tick 不会触发重建。
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [activeCategoriesKey, totalFiles]
  )

  // setInterval 靠 ref 读最新 chars 避免闭包过期（reducer 不掌握 totalChars，clamp 逻辑
  // 留在页面层），定时器归口 useEffect cleanup（约束 7）。
  const charsRef = useRef(state.chars)
  useEffect(() => {
    charsRef.current = state.chars
  }, [state.chars])

  useEffect(() => {
    if (!state.analyzing) return
    const timer = setInterval(() => {
      const next = Math.min(
        script.totalChars,
        charsRef.current + STREAM_CHARS_PER_TICK
      )
      dispatch({ type: 'advance_chars', chars: next })
      if (next >= script.totalChars) clearInterval(timer)
    }, STREAM_TICK_MS)
    return () => clearInterval(timer)
  }, [state.analyzing, script.totalChars])

  function addFiles(category: EiaCategory, fileList: FileList | null) {
    if (!fileList || fileList.length === 0) return
    dispatch({
      type: 'add_files',
      category,
      files: Array.from(fileList).map((file) => ({
        id: nextFileId(),
        name: file.name,
        size: file.size,
        file,
      })),
    })
  }

  function removeFile(category: EiaCategory, id: string) {
    dispatch({ type: 'remove_file', category, id })
  }

  function loadSample() {
    dispatch({ type: 'load_sample', files: MOCK_EIA_SAMPLE_FILES })
  }

  function resetWizard() {
    dispatch({ type: 'reset_wizard' })
    void submitEiaBatch([]).then((result) => setBatchNo(result.batchNo))
  }

  function downloadReport(report: EiaReport) {
    toast(`${report.title}分析报告 PDF 已开始下载`)
  }

  function downloadAll() {
    toast('全部分析报告已打包，开始下载 ZIP')
  }

  const reports = buildReports(activeCategories, batchNo)
  const trackRows = buildTrackRows(script, state.chars)
  const progressPercent = computeProgressPercent(script, state.chars)
  const streamDone = state.analyzing && isStreamDone(script, state.chars)
  const lines = visibleLines(script, state.chars)

  return (
    <>
      <Header fixed />
      <Main className='space-y-5'>
        <div className='flex flex-wrap items-end justify-between gap-4 border-b pb-4'>
          <div>
            <p className='mb-1 text-xs tracking-wide text-primary uppercase'>
              环评检测 · AI 分析出具
            </p>
            <h1 className='text-2xl font-semibold tracking-tight'>
              提交环评检测材料
            </h1>
            <p className='mt-1 max-w-prose text-sm text-muted-foreground'>
              按水、土、气、声分类上传检测材料——每类可上传一到多个文件，也可留空。
              系统按已上传类别逐项进行 AI 分析，并分别出具分析报告。
            </p>
          </div>
          <div className='flex gap-2'>
            <Badge variant='outline'>材料 {totalFiles}</Badge>
            <Badge variant='outline'>类别 {activeCategories.length}</Badge>
            <Badge variant='outline'>受理编号 {batchNo}</Badge>
          </div>
        </div>

        <div className='grid grid-cols-3 overflow-hidden rounded-md border'>
          {STEP_DEFS.map((def) => (
            <div
              key={def.step}
              className={`flex items-center gap-3 border-r p-3 last:border-r-0 ${
                def.step === state.step
                  ? 'bg-primary text-primary-foreground'
                  : def.step < state.step
                    ? 'bg-primary/10'
                    : ''
              }`}
            >
              <span className='font-mono text-lg'>
                {String(def.step).padStart(2, '0')}
              </span>
              <span className='flex flex-col'>
                <span className='text-sm font-semibold'>{def.title}</span>
                <span className='text-xs opacity-70'>{def.sub}</span>
              </span>
            </div>
          ))}
        </div>

        {state.step === 1 ? (
          <>
            <div className='flex justify-end'>
              <Button variant='outline' onClick={loadSample}>
                <Sparkles className='size-4' />
                加载示例
              </Button>
            </div>
            <div className='grid gap-4 md:grid-cols-2'>
              {EIA_CATEGORIES.map((def) => (
                <CategoryUploadCard
                  key={def.key}
                  def={def}
                  files={state.files[def.key]}
                  onAddFiles={(fileList) => addFiles(def.key, fileList)}
                  onRemoveFile={(id) => removeFile(def.key, id)}
                />
              ))}
            </div>
            <div className='flex items-center justify-end gap-3 border-t pt-4'>
              <span className='text-xs text-muted-foreground'>
                {step1Blocked
                  ? '请至少在任意一个类别中上传一份材料'
                  : `已选 ${activeCategories
                      .map((category) => EIA_CATEGORY_GLYPH[category])
                      .join('、')} 共 ${totalFiles} 份，可进入确认`}
              </span>
              <Button
                disabled={step1Blocked}
                onClick={() => dispatch({ type: 'to_step2' })}
              >
                下一步 · 确认提交
              </Button>
            </div>
          </>
        ) : null}

        {state.step === 2 ? (
          <Card className='max-w-3xl'>
            <CardContent className='space-y-4'>
              <h2 className='text-lg font-semibold'>核对材料清单</h2>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>类别</TableHead>
                    <TableHead>文件</TableHead>
                    <TableHead>大小</TableHead>
                    <TableHead>状态</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {activeCategories.flatMap((category) =>
                    state.files[category].map((file) => (
                      <TableRow key={file.id}>
                        <TableCell className='whitespace-nowrap'>
                          {EIA_CATEGORY_GLYPH[category]}
                        </TableCell>
                        <TableCell>{file.name}</TableCell>
                        <TableCell className='text-muted-foreground tabular-nums'>
                          {formatFileSize(file.size)}
                        </TableCell>
                        <TableCell>
                          <Badge variant='outline'>待分析</Badge>
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
              <p className='text-sm text-muted-foreground'>
                本次将对{' '}
                {activeCategories
                  .map((category) => EIA_CATEGORY_GLYPH[category])
                  .join('、')}{' '}
                共 {totalFiles} 份材料进行 AI 分析，按类别分别出具分析报告，通常
                1–2 分钟内完成。
              </p>
              <div className='flex justify-end gap-3'>
                <Button
                  variant='ghost'
                  onClick={() => dispatch({ type: 'back_step1' })}
                >
                  返回修改
                </Button>
                <Button onClick={() => dispatch({ type: 'start_analysis' })}>
                  确认提交，开始 AI 分析
                </Button>
              </div>
            </CardContent>
          </Card>
        ) : null}

        {state.step === 3 && state.analyzing ? (
          <StreamConsole
            progressPercent={progressPercent}
            trackRows={trackRows}
            lines={lines}
            streamDone={streamDone}
            reportCount={reports.length}
            onViewReports={() => dispatch({ type: 'view_reports' })}
          />
        ) : null}

        {state.step === 3 && state.reportReady ? (
          <div className='grid gap-4 lg:grid-cols-[1fr_320px] lg:items-start'>
            <div className='flex flex-col gap-4'>
              {reports.map((report) => (
                <ReportCard
                  key={report.category}
                  report={report}
                  onDownload={() => downloadReport(report)}
                />
              ))}
            </div>
            <ReportSidePanel
              reports={reports}
              batchNo={batchNo}
              onDownloadOne={downloadReport}
              onDownloadAll={downloadAll}
              onReplay={() => dispatch({ type: 'replay_analysis' })}
              onGoDesk={() => void navigate({ to: '/eia/desk' })}
              onReset={resetWizard}
            />
          </div>
        ) : null}
      </Main>
    </>
  )
}
