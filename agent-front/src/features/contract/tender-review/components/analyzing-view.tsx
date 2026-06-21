import { Brain, FileText, Info, Loader2 } from 'lucide-react'
import { useEffect, useRef } from 'react'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import type {
  CriteriaStatus,
  DocsStatusResponse,
  TenderCriteria,
  TenderDocInfoResponse,
  TenderInfo,
} from '../api'
import type { ProjectFormData } from './create-review-view'
import { MarkdownView } from './markdown-view'

/**
 * 第三步「开始分析」过程界面 — 三区布局（P3 设计 + R1 招标信息）。
 *
 * 区1（左上）基本信息：项目名/编号/控制价/招标人/评标办法。优先 OCR 抽取的 tenderInfo，
 *   缺则回落用户手填 projectForm（R1：治"基本信息显示不全"）。
 * 区2（左下）招标信息：OCR 状态 + 评分标准 criteria（评分项/满分/扣分点/废标条款，
 *   来自 tender-doc 抽取，criteria_status=ready 后展示）（R1：治"应是招标信息区域"）。
 * 区3（右）投标评标实时输出：评标流式输出（progressByRid 进度）。
 *
 * 布局：左（区1+2）|右（区3 流式），自适应宽屏；窄屏上下堆叠。
 */
export function AnalyzingView({
  progress,
  progressText,
  title,
  projectForm,
  docsStatus,
  tenderDocInfo,
  onExit,
}: {
  progress: number
  progressText?: string
  title?: string
  projectForm?: ProjectFormData | null
  docsStatus?: DocsStatusResponse | null
  tenderDocInfo?: TenderDocInfoResponse | null
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
        {/* ─ 左栏：区1 基本信息 + 区2 招标信息 ─ */}
        <div className='space-y-4'>
          {/* 区1：基本信息（OCR 抽取优先，回落手填表单）+ 投标公司名 */}
          <Zone1ProjectInfo
            projectForm={projectForm}
            tenderInfo={tenderDocInfo?.tender_info ?? null}
            criteriaStatus={tenderDocInfo?.criteria_status}
            bidders={docsStatus?.bids ?? []}
          />
          {/* 区2：招标信息（OCR 状态 + 评分标准 criteria） */}
          <Zone2TenderInfo docsStatus={docsStatus} tenderDocInfo={tenderDocInfo} />
        </div>

        {/* ─ 右栏：区3 投标公司文档（流式输出） ─ */}
        <Zone3StreamOutput progressText={progressText} scrollRef={scrollRef} />
      </div>
    </div>
  )
}

/**
 * 区1：项目基本信息。R1：OCR 抽取的 tenderInfo 优先，缺则回落用户手填 projectForm。
 *
 * 治"基本信息显示不全"：以前只读手填表单（默认大片空）；现在招标编号/招标人/控制价/评标办法
 * 在 OCR 抽取就绪后自动填充。criteria_status=running 且字段仍空时显"识别中…"而非消失。
 */
function Zone1ProjectInfo({
  projectForm,
  tenderInfo,
  criteriaStatus,
  bidders,
}: {
  projectForm?: ProjectFormData | null
  tenderInfo?: TenderInfo | null
  criteriaStatus?: CriteriaStatus
  bidders?: DocsStatusResponse['bids']
}) {
  const fundingLabel: Record<string, string> = {
    state_funded: '国资',
    other: '其他',
    unknown: '未知',
  }
  // fallback 链：OCR 抽取值 → 用户手填值。
  const pick = (extracted?: string | null, form?: string | null) =>
    extracted?.trim() || form?.trim() || ''
  // 资金来源：优先 OCR 抽取的 funding_hint（如「财政资金」），回落用户手填的 funding_type 枚举（R7-#2）。
  const fundingValue =
    tenderInfo?.funding_hint?.trim() ||
    (projectForm?.funding_type
      ? (fundingLabel[projectForm.funding_type] ?? projectForm.funding_type)
      : '')
  const extracting = criteriaStatus === 'pending' || criteriaStatus === 'running'

  const rows = [
    {
      label: '项目名称',
      value: pick(tenderInfo?.project_name, projectForm?.title),
    },
    { label: '招标编号', value: pick(tenderInfo?.tender_no, projectForm?.tender_no) },
    { label: '招标人', value: pick(tenderInfo?.tenderee, projectForm?.tenderee) },
    { label: '评标办法', value: pick(tenderInfo?.method, projectForm?.method) },
    {
      label: '控制价',
      value: pick(tenderInfo?.control_price, projectForm?.control_price),
    },
    { label: '资金来源', value: fundingValue },
  ]
  const hasAny = rows.some((row) => row.value)

  return (
    <Card>
      <CardHeader className='pb-3'>
        <CardTitle className='flex items-center gap-2 text-base'>
          <Info className='size-4 text-primary' />
          区1 基本信息
        </CardTitle>
      </CardHeader>
      <CardContent className='space-y-3'>
        {hasAny || extracting ? (
          <dl className='grid gap-2 text-sm'>
            {rows.map((row) => (
              <div key={row.label} className='grid grid-cols-[6rem_1fr] gap-x-2'>
                <dt className='text-muted-foreground'>{row.label}</dt>
                <dd className={row.value ? 'font-medium' : 'text-muted-foreground'}>
                  {row.value || (extracting ? '识别中…' : '—')}
                </dd>
              </div>
            ))}
          </dl>
        ) : (
          <p className='text-sm text-muted-foreground'>项目信息未填写。</p>
        )}
        {/* R6-R3：投标公司名称 */}
        {bidders && bidders.length > 0 ? (
          <div className='border-t pt-3'>
            <div className='mb-1.5 text-xs font-medium text-muted-foreground'>
              投标单位（{bidders.length} 家）
            </div>
            <div className='flex flex-col gap-1'>
              {bidders.map((bid) => (
                <div key={bid.bid_id} className='flex items-center gap-2 text-sm'>
                  <span className='size-1.5 shrink-0 rounded-full bg-violet-500' />
                  <span className='truncate font-medium'>
                    {bid.bidder_name?.trim() || bid.bid_id}
                  </span>
                </div>
              ))}
            </div>
          </div>
        ) : null}
      </CardContent>
    </Card>
  )
}

const scoreModeLabel: Record<string, string> = {
  deduction: '扣减',
  banded: '档次',
  additive: '加分',
  formula: '公式',
  pass_fail: '通过否',
  manual: '人工',
}

/**
 * 区2：招标信息 — OCR 状态 + 评分标准 criteria（评分项/满分/扣分点/废标条款）。
 *
 * R1：治"应是招标信息区域"。OCR 就绪后后台抽取 criteria；criteria_status=ready 即展示评分标准，
 * 让用户在评标前就看到"抓到了哪些评分点/扣分点"。failed → 提示以评标结果为准，不卡死。
 */
function Zone2TenderInfo({
  docsStatus,
  tenderDocInfo,
}: {
  docsStatus?: DocsStatusResponse | null
  tenderDocInfo?: TenderDocInfoResponse | null
}) {
  const criteriaStatus = tenderDocInfo?.criteria_status ?? 'pending'
  const criteria = tenderDocInfo?.criteria ?? null

  return (
    <Card>
      <CardHeader className='pb-3'>
        <CardTitle className='flex items-center gap-2 text-base'>
          <FileText className='size-4 text-primary' />
          区2 招标信息
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className='space-y-3 text-sm'>
          {/* OCR 状态行（招标 + 各投标家） */}
          {docsStatus ? (
            <div className='space-y-2'>
              <div className='flex items-center gap-2'>
                <OcrDot status={docsStatus.tender_doc?.ocr_status ?? 'pending'} />
                <span className='font-medium text-muted-foreground'>招标文件</span>
                <span className='shrink-0'>
                  {docsStatus.tender_doc
                    ? ocrStatusLabel(docsStatus.tender_doc.ocr_status)
                    : '未上传'}
                </span>
              </div>
              {docsStatus.bids.length > 0 ? (
                <div className='flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground'>
                  <span>投标 {docsStatus.bids.length} 家：</span>
                  {docsStatus.bids.map((bid) => (
                    <span key={bid.bid_id} className='flex items-center gap-1'>
                      <OcrDot status={bid.ocr_status} />
                      <span className='max-w-32 truncate'>
                        {bid.bidder_name ?? bid.bid_id}
                      </span>
                    </span>
                  ))}
                </div>
              ) : null}
            </div>
          ) : (
            <p className='text-muted-foreground'>OCR 状态加载中…</p>
          )}

          {/* 评分标准 criteria（招标信息核心） */}
          <div className='border-t pt-3'>
            <div className='mb-2 flex items-center justify-between'>
              <span className='font-medium text-muted-foreground'>评分标准</span>
              <CriteriaStatusBadge status={criteriaStatus} />
            </div>
            {criteriaStatus === 'ready' && criteria ? (
              <CriteriaSummary criteria={criteria} />
            ) : criteriaStatus === 'failed' ? (
              <p className='rounded-lg bg-muted/40 px-3 py-2 text-xs text-muted-foreground'>
                招标信息自动识别失败，将以评标过程的解析结果为准。
              </p>
            ) : (
              <p className='rounded-lg bg-muted/40 px-3 py-2 text-xs text-muted-foreground'>
                {docsStatus?.tender_doc?.ocr_status === 'ready'
                  ? '正在从招标文件抽取评分项、扣分点与废标条款…'
                  : '等待招标文件 OCR 完成后自动抽取评分标准…'}
              </p>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

/** criteria 抽取状态徽章。 */
function CriteriaStatusBadge({ status }: { status: CriteriaStatus }) {
  const map: Record<CriteriaStatus, { label: string; cls: string }> = {
    pending: { label: '等待中', cls: 'bg-muted text-muted-foreground' },
    running: { label: '识别中', cls: 'bg-blue-100 text-blue-700' },
    ready: { label: '已识别', cls: 'bg-emerald-100 text-emerald-700' },
    failed: { label: '识别失败', cls: 'bg-red-100 text-red-700' },
  }
  const { label, cls } = map[status] ?? map.pending
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${cls}`}>
      {label}
    </span>
  )
}

/** 评分标准摘要：方法/满分 + 评分项列表（评分项·满分·方式·扣分点数）+ 废标条款数。 */
function CriteriaSummary({ criteria }: { criteria: TenderCriteria }) {
  const items = criteria.items ?? []
  const rejectionCount = criteria.rejection_rules?.length ?? 0
  // 自检：各项 max 之和 vs 声明满分，对不上时提示（抓漏/抓错评分项的早期信号）。
  const sumMax = items.reduce((acc, it) => acc + (Number(it.max) || 0), 0)
  const totalMax = criteria.total_max
  const sumMismatch =
    typeof totalMax === 'number' && Math.abs(sumMax - totalMax) > 0.5

  return (
    <div className='space-y-2'>
      <div className='flex flex-wrap items-center gap-x-3 gap-y-1 text-xs'>
        {criteria.method ? (
          <span className='rounded bg-primary/10 px-2 py-0.5 font-medium text-primary'>
            {criteria.method}
          </span>
        ) : null}
        <span className='text-muted-foreground'>
          满分 <b className='text-foreground'>{totalMax ?? sumMax}</b> · 评分项{' '}
          <b className='text-foreground'>{items.length}</b>
          {rejectionCount > 0 ? (
            <>
              {' '}
              · 废标条款 <b className='text-foreground'>{rejectionCount}</b>
            </>
          ) : null}
        </span>
      </div>
      {sumMismatch ? (
        <p className='text-xs text-amber-600'>
          ⚠ 各项满分合计 {sumMax} 与声明满分 {totalMax} 不一致，可能漏抓或抓错评分项。
        </p>
      ) : null}
      <ul className='max-h-64 space-y-1 overflow-y-auto'>
        {items.map((item, index) => {
          const deductionCount = item.deductions?.length ?? 0
          const bandCount = item.bands?.length ?? 0
          const awardCount = item.awards?.length ?? 0
          const detailBits = [
            deductionCount > 0 ? `${deductionCount} 扣分点` : '',
            bandCount > 0 ? `${bandCount} 档` : '',
            awardCount > 0 ? `${awardCount} 加分点` : '',
          ].filter(Boolean)
          return (
            <li
              key={`${item.item}-${index}`}
              className='flex items-start justify-between gap-2 rounded-lg bg-muted/40 px-2.5 py-1.5'
            >
              <span className='min-w-0 flex-1'>
                <span className='block truncate font-medium'>{item.item}</span>
                {detailBits.length > 0 ? (
                  <span className='text-xs text-muted-foreground'>
                    {detailBits.join(' · ')}
                  </span>
                ) : null}
                {/* R6-R4：扣减分数项目明细（每条扣分情形 + 扣分值） */}
                {deductionCount > 0 ? (
                  <span className='mt-1 block space-y-0.5'>
                    {item.deductions!.slice(0, 4).map((ded, dedIndex) => (
                      <span
                        key={dedIndex}
                        className='block text-xs leading-4 text-muted-foreground'
                      >
                        <b className='text-red-600'>
                          −{ded.points != null ? ded.points : '?'}
                        </b>{' '}
                        {ded.condition || '扣分情形'}
                      </span>
                    ))}
                    {deductionCount > 4 ? (
                      <span className='block text-xs text-muted-foreground'>
                        …另 {deductionCount - 4} 条扣分项
                      </span>
                    ) : null}
                  </span>
                ) : null}
              </span>
              <span className='flex shrink-0 items-center gap-1.5'>
                {item.score_mode ? (
                  <span className='rounded bg-background px-1.5 py-0.5 text-xs text-muted-foreground'>
                    {scoreModeLabel[item.score_mode] ?? item.score_mode}
                  </span>
                ) : null}
                <span className='text-sm font-semibold'>{item.max}</span>
              </span>
            </li>
          )
        })}
      </ul>
    </div>
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
      {/* R7-#3：flex 链撑满 → 区3 与左栏（区1+区2）等高（grid 默认 items-stretch）。 */}
      <CardContent className='flex min-h-0 flex-1 flex-col'>
        {/* 流式输出区：实时展示 AI 评标分析过程，自动滚到最新 */}
        <div className='flex h-full flex-col rounded-lg border bg-muted/30'>
          <div className='flex shrink-0 items-center gap-2 border-b px-4 py-2 text-sm font-medium'>
            <Brain className='size-4 text-primary' />
            实时分析输出
          </div>
          {/* R7-#3：min-h-0 + flex-1 让滚动区随卡片伸缩（去固定 max-h）；markdown 渲染 AI 输出。 */}
          <div ref={scrollRef} className='min-h-48 flex-1 overflow-auto px-4 py-3'>
            {progressText?.trim() ? (
              <MarkdownView>{progressText}</MarkdownView>
            ) : (
              <p className='text-xs text-muted-foreground'>
                分析进行中，等待 AI 评标实时输出…
              </p>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
