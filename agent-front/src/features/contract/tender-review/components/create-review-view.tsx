import {
  AlertCircle,
  FileText,
  Loader2,
  Play,
  Plus,
  Trash2,
  UploadCloud,
} from 'lucide-react'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { DocsStatusResponse, TenderProjectCreateRequest } from '../api'
import { ACCEPTED_DOCUMENT_FILE_TYPES } from '../supported-document-formats'
import type { TenderFile, TenderScenario, UploadBidder } from '../types'

/** funding_type 下拉选项 */
const FUNDING_TYPE_OPTIONS: Array<{
  value: 'state_funded' | 'other' | 'unknown'
  label: string
}> = [
  { value: 'state_funded', label: '国资' },
  { value: 'other', label: '其他' },
  { value: 'unknown', label: '未知' },
]

/** A①: 可编辑的项目基本信息 */
export type ProjectFormData = Pick<
  TenderProjectCreateRequest,
  | 'tender_no'
  | 'title'
  | 'tenderee'
  | 'method'
  | 'control_price'
  | 'funding_type'
>

type CreateReviewViewProps = {
  scenario: TenderScenario
  projectForm: ProjectFormData
  tenderFiles: TenderFile[]
  uploadBidders: UploadBidder[]
  progress: number
  isAnalyzing: boolean
  /** A: 任一区上传中（触发后台 OCR）。 */
  isUploading: boolean
  /** A: 招标文件上传中。 */
  uploadingTender: boolean
  /** A: 已自动上传的投标单位 id（锁定其文件区）。 */
  uploadedBidderIds: Set<number>
  /** A: 上传中的投标单位 id。 */
  uploadingBidderIds: Set<number>
  /** P3: 文件已上传并 OCR 就绪，可点"开始分析"。 */
  isOcrReady: boolean
  /** H3 KD2：底稿降级/部分缺失时的告警文案（不阻断开始分析，只告知结论会标注）。 */
  ocrNotice: string | null
  /** A: 招标已上传（uploadProjectId 非 null）→ 投标区解锁。 */
  hasUploaded: boolean
  /** P3: docs-status 轮询结果（显示各文件 OCR 状态）。 */
  docsStatus: DocsStatusResponse | null
  uploadError: boolean
  submitError: string
  canStart: boolean
  onStart: () => void
  onCancel: () => void
  onUpdateProjectForm: (field: keyof ProjectFormData, value: string) => void
  onAddTenderFile: (files: FileList | null) => void
  onRemoveTenderFile: (index: number) => void
  onAddBidder: () => void
  onRemoveBidder: (id: number) => void
  onUpdateBidderName: (id: number, name: string) => void
  onAddBidderFile: (id: number, files: FileList | null) => void
  onRemoveBidderFile: (id: number, fileIndex: number) => void
}

export function CreateReviewView(props: CreateReviewViewProps) {
  // P3: 步骤状态推导
  const currentStep = props.isAnalyzing
    ? 'analyze'
    : props.hasUploaded
      ? 'analyze'
      : 'files'

  return (
    <div className='space-y-4'>
      <StepBar analyzing={props.isAnalyzing} currentStep={currentStep} />
      <ProjectInfoFormCard
        form={props.projectForm}
        onUpdate={props.onUpdateProjectForm}
        disabled={props.isAnalyzing || props.isUploading || props.hasUploaded}
      />
      <UploadFilesCard {...props} />
      {/* R7：移除"OCR 识别中，请稍候…"提示卡——OCR 全在后台跑、不拦路、前台不提示（用户诉求）。
          文件各自的 OCR 进度在「分析中」页区2 仍可见，创建页不再弹阻塞感的状态卡。 */}
      {props.isAnalyzing ? <AnalyzingCard progress={props.progress} /> : null}
      {props.ocrNotice ? (
        <p
          role='status'
          className='rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-800'
        >
          {props.ocrNotice}
        </p>
      ) : null}
      {props.uploadError ? <UploadError /> : null}
      {props.submitError ? <SubmitError message={props.submitError} /> : null}
      <div className='flex justify-end gap-3'>
        <Button type='button' variant='outline' onClick={props.onCancel}>
          取消
        </Button>
        {/* R7：开始分析只看是否选了文件——不被上传/OCR/预热阻塞。点了就进分析中页、后台跑，可离开。 */}
        <Button
          type='button'
          onClick={props.onStart}
          disabled={props.isAnalyzing || !props.canStart}
          aria-label='开始分析'
        >
          {props.isAnalyzing ? (
            <>
              <Play className='size-4' />
              分析中...
            </>
          ) : (
            <>
              <Play className='size-4' />
              {props.scenario === 'bidder_self_check' ? '开始自查' : '开始分析'}
            </>
          )}
        </Button>
      </div>
    </div>
  )
}

const TENDER_STEPS = [
  { id: 'project', label: '项目信息' },
  { id: 'files', label: '上传文件' },
  { id: 'analyze', label: '开始分析' },
] as const

type TenderStepId = (typeof TENDER_STEPS)[number]['id']

/**
 * D①: 顶部步骤条 — 与报销审核 ClickableStepper 统一样式，按钮形式可点击。
 * 招投标创建页是单页表单，currentStep 控制高亮，onStepClick 为可选跳步回调。
 */
function StepBar({
  analyzing,
  currentStep = 'project',
  onStepClick,
}: {
  analyzing: boolean
  currentStep?: TenderStepId
  onStepClick?: (stepId: TenderStepId) => void
}) {
  const activeStep: TenderStepId = analyzing ? 'analyze' : currentStep
  const activeIndex = TENDER_STEPS.findIndex((step) => step.id === activeStep)
  const clickable = Boolean(onStepClick)

  return (
    <div className='grid gap-2 md:grid-cols-3'>
      {TENDER_STEPS.map((step, index) => {
        const active = step.id === activeStep
        const done = index < activeIndex
        // F7/D①: 单页创建表单没有真正的跳步导航 → 无 onStepClick 时渲染为非交互
        // 指示器（保留与报销 ClickableStepper 一致的视觉，但不伪装可点击）。
        const stateClass = active
          ? 'border-primary bg-primary/5 text-primary'
          : done
            ? 'bg-muted/60 text-foreground'
            : 'text-muted-foreground'
        const className = `rounded-md border px-3 py-2 text-left text-sm transition-colors ${stateClass} ${
          clickable ? 'cursor-pointer hover:bg-muted' : 'cursor-default'
        }`
        const inner = (
          <div className='flex items-center gap-2'>
            <span className='inline-flex size-5 items-center justify-center rounded-full border text-xs'>
              {index + 1}
            </span>
            {step.label}
          </div>
        )
        return clickable ? (
          <button
            key={step.id}
            type='button'
            aria-current={active ? 'step' : undefined}
            className={className}
            onClick={() => onStepClick?.(step.id)}
          >
            {inner}
          </button>
        ) : (
          <div
            key={step.id}
            aria-current={active ? 'step' : undefined}
            className={className}
          >
            {inner}
          </div>
        )
      })}
    </div>
  )
}

/**
 * A①: 项目信息表单 — 暴露全部 6 个字段，均为 optional。
 * 允许只填部分，先建后补。
 */
function ProjectInfoFormCard({
  form,
  onUpdate,
  disabled,
}: {
  form: ProjectFormData
  onUpdate: (field: keyof ProjectFormData, value: string) => void
  disabled: boolean
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>项目信息</CardTitle>
        <CardDescription>所有字段均为选填，允许先建后补。</CardDescription>
      </CardHeader>
      <CardContent className='grid gap-4 md:grid-cols-2'>
        <div className='md:col-span-2'>
          <Label
            htmlFor='project-title'
            className='mb-2 block text-sm font-medium'
          >
            项目名称
          </Label>
          <Input
            id='project-title'
            value={form.title ?? ''}
            onChange={(event) => onUpdate('title', event.target.value)}
            placeholder='如：无锡市政管廊施工项目'
            disabled={disabled}
          />
        </div>
        <div>
          <Label
            htmlFor='project-tender-no'
            className='mb-2 block text-sm font-medium'
          >
            招标编号
          </Label>
          <Input
            id='project-tender-no'
            value={form.tender_no ?? ''}
            onChange={(event) => onUpdate('tender_no', event.target.value)}
            placeholder='如：WX-2026-001'
            disabled={disabled}
          />
        </div>
        <div>
          <Label
            htmlFor='project-tenderee'
            className='mb-2 block text-sm font-medium'
          >
            招标人
          </Label>
          <Input
            id='project-tenderee'
            value={form.tenderee ?? ''}
            onChange={(event) => onUpdate('tenderee', event.target.value)}
            placeholder='如：无锡城投集团'
            disabled={disabled}
          />
        </div>
        <div>
          <Label
            htmlFor='project-method'
            className='mb-2 block text-sm font-medium'
          >
            评标方法
          </Label>
          <Input
            id='project-method'
            value={form.method ?? ''}
            onChange={(event) => onUpdate('method', event.target.value)}
            placeholder='如：综合评估法'
            disabled={disabled}
          />
        </div>
        <div>
          <Label
            htmlFor='project-control-price'
            className='mb-2 block text-sm font-medium'
          >
            标底 / 控制价
          </Label>
          <Input
            id='project-control-price'
            value={form.control_price ?? ''}
            onChange={(event) => onUpdate('control_price', event.target.value)}
            placeholder='如：120000000'
            disabled={disabled}
          />
        </div>
        <div>
          <Label
            htmlFor='project-funding-type'
            className='mb-2 block text-sm font-medium'
          >
            资金来源
          </Label>
          <Select
            value={form.funding_type ?? 'unknown'}
            onValueChange={(value) => onUpdate('funding_type', value)}
            disabled={disabled}
          >
            <SelectTrigger id='project-funding-type'>
              <SelectValue placeholder='请选择资金来源' />
            </SelectTrigger>
            <SelectContent>
              {FUNDING_TYPE_OPTIONS.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </CardContent>
    </Card>
  )
}

function UploadFilesCard(props: CreateReviewViewProps) {
  // A 上传即 OCR：招标区选文件即自动上传，传后锁定（要改→取消重来）。投标区在招标上传前禁用
  // （强制招标先传），招标上传后解锁，每家传后单独锁定。
  const tenderLocked =
    props.uploadingTender || props.hasUploaded || props.isAnalyzing
  const isSelfCheck = props.scenario === 'bidder_self_check'
  return (
    <Card>
      <CardHeader className='gap-2 md:flex-row md:items-center md:justify-between'>
        <div>
          <CardTitle>{isSelfCheck ? '自查文件上传' : '文件上传'}</CardTitle>
          <CardDescription>
            {isSelfCheck
              ? '上传投标文件和对应招标文件，输出自查风险、扣分点与修改建议。'
              : '选择文件即自动上传并识别（OCR），无需手动操作。请先上传招标文件，再上传各投标单位文件。'}
          </CardDescription>
        </div>
      </CardHeader>
      <CardContent className='space-y-6'>
        <TenderFilesSection
          files={props.tenderFiles}
          locked={tenderLocked}
          uploading={props.uploadingTender}
          // R7-#1：已上传的招标文件仍可删（删→停 OCR→重传）；仅上传中/分析中禁删。
          removable={!props.uploadingTender && !props.isAnalyzing}
          onAdd={props.onAddTenderFile}
          onRemove={props.onRemoveTenderFile}
        />
        <BidderFilesSection {...props} />
      </CardContent>
    </Card>
  )
}

function TenderFilesSection({
  files,
  locked,
  uploading,
  removable,
  onAdd,
  onRemove,
}: {
  files: TenderFile[]
  locked?: boolean
  uploading?: boolean
  /** R7-#1：删除按钮是否可见（与 locked 解耦——已上传的招标文件仍可删以重传）。 */
  removable?: boolean
  onAdd: (files: FileList | null) => void
  onRemove: (index: number) => void
}) {
  return (
    <section className='space-y-3'>
      <SectionTitle
        color='bg-primary'
        title='招标文件'
        desc='招标公告 · 资格预审 · 评分办法等，选择后自动上传识别（传错可删除重传）'
      />
      {files.map((file, index) => (
        <FileRow
          key={`${file.name}-${index}`}
          file={file}
          tone='blue'
          locked={locked}
          removable={removable}
          onRemove={() => onRemove(index)}
        />
      ))}
      {uploading ? (
        <div className='flex items-center gap-2 rounded-lg border border-dashed bg-muted/20 p-3 text-sm text-muted-foreground'>
          <Loader2 className='size-4 animate-spin' />
          招标文件上传识别中…
        </div>
      ) : !locked ? (
        <label
          className='flex w-full cursor-pointer items-center justify-center gap-2 rounded-lg border border-dashed bg-muted/20 p-3 text-sm font-medium text-primary transition-colors hover:bg-primary/5'
          onDragOver={(event) => event.preventDefault()}
          onDrop={(event) => {
            event.preventDefault()
            onAdd(event.dataTransfer.files)
          }}
        >
          <UploadCloud className='size-4' />
          点击或拖拽上传招标文件
          <input
            multiple
            type='file'
            accept={ACCEPTED_DOCUMENT_FILE_TYPES}
            className='hidden'
            onChange={(event) => {
              onAdd(event.target.files)
              event.currentTarget.value = ''
            }}
          />
        </label>
      ) : null}
    </section>
  )
}

function BidderFilesSection(props: CreateReviewViewProps) {
  // A 招标先传约束：招标未上传(hasUploaded=false)→整个投标区禁用 + 提示。
  const tenderReady = props.hasUploaded
  const sectionLocked = props.isAnalyzing
  const isSelfCheck = props.scenario === 'bidder_self_check'
  return (
    <section className='space-y-3'>
      <div className='flex flex-wrap items-center gap-3'>
        <SectionTitle
          color='bg-violet-500'
          title='投标文件'
          desc='每家投标单位单独管理，选择后自动上传识别'
        />
        <div className='flex-1' />
        {!sectionLocked && !isSelfCheck ? (
          <Button
            type='button'
            size='sm'
            onClick={props.onAddBidder}
            disabled={!tenderReady}
          >
            <Plus className='size-4' />
            添加投标单位
          </Button>
        ) : null}
        {isSelfCheck ? (
          <span className='rounded-md bg-muted px-2 py-1 text-xs text-muted-foreground'>
            单家自查
          </span>
        ) : null}
      </div>

      {!tenderReady ? (
        <div className='rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground'>
          请先上传招标文件，上传完成后即可添加投标单位。
        </div>
      ) : props.uploadBidders.length === 0 ? (
        <div className='rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground'>
          还没有投标单位，点击「添加投标单位」开始添加。
        </div>
      ) : (
        <div className='space-y-3'>
          {props.uploadBidders.map((bidder, index) => (
            <BidderCard
              key={bidder.id}
              bidder={bidder}
              index={index}
              // 每家：上传中/已上传/分析中 → 锁定该家文件区
              locked={
                sectionLocked ||
                props.uploadedBidderIds.has(bidder.id) ||
                props.uploadingBidderIds.has(bidder.id)
              }
              uploading={props.uploadingBidderIds.has(bidder.id)}
              uploaded={props.uploadedBidderIds.has(bidder.id)}
              onUpdateName={(name) => props.onUpdateBidderName(bidder.id, name)}
              onAddFile={(files) => props.onAddBidderFile(bidder.id, files)}
              onRemove={() => props.onRemoveBidder(bidder.id)}
              removable={!isSelfCheck}
              onRemoveFile={(fileIndex) =>
                props.onRemoveBidderFile(bidder.id, fileIndex)
              }
            />
          ))}
        </div>
      )}
    </section>
  )
}

function BidderCard({
  bidder,
  index,
  locked,
  uploading,
  uploaded,
  onUpdateName,
  onAddFile,
  onRemove,
  removable,
  onRemoveFile,
}: {
  bidder: UploadBidder
  index: number
  locked?: boolean
  uploading?: boolean
  uploaded?: boolean
  onUpdateName: (name: string) => void
  onAddFile: (files: FileList | null) => void
  onRemove: () => void
  removable?: boolean
  onRemoveFile: (index: number) => void
}) {
  const tag = '甲乙丙丁戊己庚辛壬癸'[index] ?? String(index + 1)

  return (
    <div className='rounded-xl border bg-muted/20 p-4'>
      <div className='flex items-center gap-3'>
        <span className='flex size-7 shrink-0 items-center justify-center rounded-md bg-primary/10 text-sm font-semibold text-primary'>
          {tag}
        </span>
        <Input
          value={bidder.name}
          onChange={(event) => onUpdateName(event.target.value)}
          placeholder='点击输入投标单位名称...'
          disabled={locked}
          className='border-0 bg-transparent px-1 font-medium shadow-none focus-visible:ring-0'
        />
        <span className='shrink-0 text-xs font-medium text-muted-foreground'>
          {uploaded ? '已上传 · 识别中' : `${bidder.files.length} 个文件`}
        </span>
        {/* 允许删除（含已上传）→ 删该家重选即可改文件（uploading 中不删，防竞态） */}
        {!uploading && removable !== false ? (
          <Button
            type='button'
            variant='ghost'
            size='icon'
            aria-label={`删除投标单位 ${bidder.name || tag}`}
            onClick={onRemove}
          >
            <Trash2 className='size-4' />
          </Button>
        ) : null}
      </div>
      <div className='mt-3 space-y-2'>
        {bidder.files.map((file, fileIndex) => (
          <FileRow
            key={`${bidder.id}-${file.name}-${fileIndex}`}
            file={file}
            tone='violet'
            compact
            locked={locked}
            onRemove={() => onRemoveFile(fileIndex)}
          />
        ))}
        {uploading ? (
          <div className='flex items-center gap-2 rounded-lg border border-dashed bg-background p-2.5 text-sm text-muted-foreground'>
            <Loader2 className='size-4 animate-spin' />
            上传识别中…
          </div>
        ) : !locked ? (
          <label
            className='flex w-full cursor-pointer items-center justify-center gap-2 rounded-lg border border-dashed bg-background p-2.5 text-sm font-medium text-violet-600 transition-colors hover:bg-violet-50'
            onDragOver={(event) => event.preventDefault()}
            onDrop={(event) => {
              event.preventDefault()
              onAddFile(event.dataTransfer.files)
            }}
          >
            <UploadCloud className='size-4' />
            添加该单位的投标文件
            <input
              multiple
              type='file'
              accept={ACCEPTED_DOCUMENT_FILE_TYPES}
              className='hidden'
              onChange={(event) => {
                onAddFile(event.target.files)
                event.currentTarget.value = ''
              }}
            />
          </label>
        ) : null}
      </div>
    </div>
  )
}

function SectionTitle({
  color,
  title,
  desc,
}: {
  color: string
  title: string
  desc: string
}) {
  return (
    <div className='flex flex-wrap items-center gap-2'>
      <span className={`h-4 w-1 rounded-full ${color}`} />
      <span className='text-sm font-semibold'>{title}</span>
      <span className='rounded-md bg-red-100 px-2 py-0.5 text-xs font-semibold text-red-700'>
        必传
      </span>
      <span className='text-xs text-muted-foreground'>{desc}</span>
    </div>
  )
}

function FileRow({
  file,
  tone,
  compact,
  locked,
  removable,
  onRemove,
}: {
  file: TenderFile
  tone: 'blue' | 'violet'
  compact?: boolean
  locked?: boolean
  /** R7-#1：删除按钮可见性，独立于 locked（已上传文件仍可删以重传）。缺省回落 !locked。 */
  removable?: boolean
  onRemove: () => void
}) {
  // 删除按钮可见：显式 removable 优先；未传 removable 时回落旧行为（!locked）。
  const showRemove = removable ?? !locked
  const toneClass =
    tone === 'blue'
      ? 'bg-primary/10 text-primary'
      : 'bg-violet-100 text-violet-700'

  return (
    <div
      className={`flex items-center gap-3 rounded-lg border bg-background ${
        compact ? 'px-3 py-2' : 'px-4 py-3'
      }`}
    >
      <span
        className={`flex size-9 shrink-0 items-center justify-center rounded-lg ${toneClass}`}
      >
        <FileText className='size-4' />
      </span>
      <div className='min-w-0 flex-1'>
        <div className='truncate text-sm font-medium'>{file.name}</div>
        <div className='mt-0.5 text-xs text-muted-foreground'>
          {formatFileSize(file.size)}
        </div>
      </div>
      {!compact ? (
        <span className='rounded-full bg-emerald-100 px-3 py-1 text-xs font-medium text-emerald-700'>
          已选
        </span>
      ) : null}
      {showRemove ? (
        <Button
          type='button'
          variant='ghost'
          size='icon'
          aria-label={`删除文件 ${file.name}`}
          onClick={onRemove}
        >
          <Trash2 className='size-4' />
        </Button>
      ) : null}
    </div>
  )
}

function AnalyzingCard({ progress }: { progress: number }) {
  const stage = getProgressStage(progress)

  return (
    <Alert className='border-primary/20 bg-primary/5'>
      <UploadCloud className='size-4' />
      <AlertDescription className='space-y-3'>
        <div className='flex items-center justify-between gap-4'>
          <span className='font-medium'>正在分析...</span>
          <span className='font-semibold text-primary'>{progress}%</span>
        </div>
        <div className='h-2 overflow-hidden rounded-full bg-muted'>
          <div
            className='h-full rounded-full bg-primary transition-all'
            style={{ width: `${progress}%` }}
          />
        </div>
        <div className='flex items-center gap-2 text-sm text-muted-foreground'>
          <span className='size-1.5 rounded-full bg-emerald-500' />
          {stage}
        </div>
      </AlertDescription>
    </Alert>
  )
}

function UploadError() {
  return (
    <Alert variant='destructive'>
      <AlertCircle className='size-4' />
      <AlertDescription>
        请至少上传 1 个招标文件，并为至少一家投标单位上传文件后再开始分析。
      </AlertDescription>
    </Alert>
  )
}

function SubmitError({ message }: { message: string }) {
  return (
    <Alert variant='destructive'>
      <AlertCircle className='size-4' />
      <AlertDescription>{message}</AlertDescription>
    </Alert>
  )
}

function formatFileSize(bytes: number) {
  if (bytes >= 1048576) return `${(bytes / 1048576).toFixed(1)} MB`
  if (bytes >= 1024) return `${Math.round(bytes / 1024)} KB`
  return `${bytes} B`
}

function getProgressStage(progress: number) {
  if (progress >= 100) return '分析完成，正在跳转...'
  if (progress >= 80) return '生成评分与审核结论...'
  if (progress >= 55) return '比对投标文件、定位响应内容...'
  if (progress >= 30) return '提取招标资格条件与评分要点...'
  return '正在解析文件结构...'
}
