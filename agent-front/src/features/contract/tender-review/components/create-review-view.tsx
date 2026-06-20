import {
  AlertCircle,
  FileText,
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
import type { ProjectInfo, TenderFile, UploadBidder } from '../types'

const ACCEPTED_REVIEW_FILE_TYPES = [
  '.pdf',
  '.doc',
  '.docx',
  '.xls',
  '.xlsx',
  '.ppt',
  '.pptx',
  '.txt',
  '.jpg',
  '.jpeg',
  '.png',
  '.webp',
  '.heic',
  'image/*',
  'application/pdf',
].join(',')

type CreateReviewViewProps = {
  projectInfo: ProjectInfo
  tenderFiles: TenderFile[]
  uploadBidders: UploadBidder[]
  progress: number
  isAnalyzing: boolean
  uploadError: boolean
  submitError: string
  canStart: boolean
  onStart: () => void
  onCancel: () => void
  onAddTenderFile: (files: FileList | null) => void
  onRemoveTenderFile: (index: number) => void
  onAddBidder: () => void
  onRemoveBidder: (id: number) => void
  onUpdateBidderName: (id: number, name: string) => void
  onAddBidderFile: (id: number, files: FileList | null) => void
  onRemoveBidderFile: (id: number, fileIndex: number) => void
}

export function CreateReviewView(props: CreateReviewViewProps) {
  return (
    <div className='space-y-4'>
      <StepBar analyzing={props.isAnalyzing} />
      <ProjectInfoCard projectInfo={props.projectInfo} />
      <UploadFilesCard {...props} />
      {props.isAnalyzing ? <AnalyzingCard progress={props.progress} /> : null}
      {props.uploadError ? <UploadError /> : null}
      {props.submitError ? <SubmitError message={props.submitError} /> : null}
      <div className='flex justify-end gap-3'>
        <Button type='button' variant='outline' onClick={props.onCancel}>
          取消
        </Button>
        <Button
          type='button'
          onClick={props.onStart}
          disabled={props.isAnalyzing}
          className={!props.canStart ? 'opacity-70' : undefined}
        >
          <Play className='size-4' />
          {props.isAnalyzing ? '分析中...' : '开始分析'}
        </Button>
      </div>
    </div>
  )
}

function StepBar({ analyzing }: { analyzing: boolean }) {
  const steps = [
    { label: '项目信息', active: true },
    { label: '上传文件', active: true },
    { label: '开始分析', active: analyzing },
  ]

  return (
    <div className='flex justify-center'>
      <div className='flex w-full max-w-4xl flex-wrap items-center justify-center gap-4 rounded-lg border bg-muted/20 px-6 py-3'>
        {steps.map((step, index) => (
          <div key={step.label} className='flex items-center gap-3'>
            <span
              className={`flex size-8 items-center justify-center rounded-full border text-sm font-semibold ${
                step.active
                  ? 'border-primary bg-primary text-primary-foreground'
                  : 'border-primary bg-background text-primary'
              }`}
            >
              {index + 1}
            </span>
            <span className='text-sm font-medium'>{step.label}</span>
            {index < steps.length - 1 ? (
              <span className='h-px w-16 bg-border md:w-24' />
            ) : null}
          </div>
        ))}
      </div>
    </div>
  )
}

function ProjectInfoCard({ projectInfo }: { projectInfo: ProjectInfo }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>项目信息</CardTitle>
      </CardHeader>
      <CardContent className='grid gap-4 md:grid-cols-2'>
        <ReadonlyField
          className='md:col-span-2'
          label='项目名称'
          value={projectInfo.name}
        />
        <ReadonlyField label='招标编号' value={projectInfo.code} />
        <ReadonlyField label='评标办法' value={projectInfo.method} />
      </CardContent>
    </Card>
  )
}

function UploadFilesCard(props: CreateReviewViewProps) {
  return (
    <Card>
      <CardHeader className='gap-2 md:flex-row md:items-center md:justify-between'>
        <div>
          <CardTitle>文件上传</CardTitle>
          <CardDescription>
            支持 PDF、图片、Word、Excel、PPT 等文档，单文件不超过 200MB。
          </CardDescription>
        </div>
      </CardHeader>
      <CardContent className='space-y-6'>
        <TenderFilesSection
          files={props.tenderFiles}
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
  onAdd,
  onRemove,
}: {
  files: TenderFile[]
  onAdd: (files: FileList | null) => void
  onRemove: (index: number) => void
}) {
  return (
    <section className='space-y-3'>
      <SectionTitle
        color='bg-primary'
        title='招标文件'
        desc='招标公告 · 资格预审 · 评分办法等，支持多个文件'
      />
      {files.map((file, index) => (
        <FileRow
          key={`${file.name}-${index}`}
          file={file}
          tone='blue'
          onRemove={() => onRemove(index)}
        />
      ))}
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
          accept={ACCEPTED_REVIEW_FILE_TYPES}
          className='hidden'
          onChange={(event) => {
            onAdd(event.target.files)
            event.currentTarget.value = ''
          }}
        />
      </label>
    </section>
  )
}

function BidderFilesSection(props: CreateReviewViewProps) {
  return (
    <section className='space-y-3'>
      <div className='flex flex-wrap items-center gap-3'>
        <SectionTitle
          color='bg-violet-500'
          title='投标文件'
          desc='每家投标单位单独管理，每家可上传多个文件'
        />
        <div className='flex-1' />
        <Button type='button' size='sm' onClick={props.onAddBidder}>
          <Plus className='size-4' />
          添加投标单位
        </Button>
      </div>

      {props.uploadBidders.length === 0 ? (
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
              onUpdateName={(name) => props.onUpdateBidderName(bidder.id, name)}
              onAddFile={(files) => props.onAddBidderFile(bidder.id, files)}
              onRemove={() => props.onRemoveBidder(bidder.id)}
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
  onUpdateName,
  onAddFile,
  onRemove,
  onRemoveFile,
}: {
  bidder: UploadBidder
  index: number
  onUpdateName: (name: string) => void
  onAddFile: (files: FileList | null) => void
  onRemove: () => void
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
          className='border-0 bg-transparent px-1 font-medium shadow-none focus-visible:ring-0'
        />
        <span className='shrink-0 text-xs font-medium text-muted-foreground'>
          {bidder.files.length} 个文件
        </span>
        <Button
          type='button'
          variant='ghost'
          size='icon'
          aria-label={`删除投标单位 ${bidder.name || tag}`}
          onClick={onRemove}
        >
          <Trash2 className='size-4' />
        </Button>
      </div>
      <div className='mt-3 space-y-2'>
        {bidder.files.map((file, fileIndex) => (
          <FileRow
            key={`${bidder.id}-${file.name}-${fileIndex}`}
            file={file}
            tone='violet'
            compact
            onRemove={() => onRemoveFile(fileIndex)}
          />
        ))}
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
            accept={ACCEPTED_REVIEW_FILE_TYPES}
            className='hidden'
            onChange={(event) => {
              onAddFile(event.target.files)
              event.currentTarget.value = ''
            }}
          />
        </label>
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

function ReadonlyField({
  label,
  value,
  className,
}: {
  label: string
  value: string
  className?: string
}) {
  return (
    <div className={className}>
      <div className='mb-2 text-sm font-medium text-muted-foreground'>
        {label}
      </div>
      <div className='rounded-lg border bg-muted/30 px-3 py-2 text-sm'>
        {value}
      </div>
    </div>
  )
}

function FileRow({
  file,
  tone,
  compact,
  onRemove,
}: {
  file: TenderFile
  tone: 'blue' | 'violet'
  compact?: boolean
  onRemove: () => void
}) {
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
      <span className={`flex size-9 shrink-0 items-center justify-center rounded-lg ${toneClass}`}>
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
          已上传
        </span>
      ) : null}
      <Button
        type='button'
        variant='ghost'
        size='icon'
        aria-label={`删除文件 ${file.name}`}
        onClick={onRemove}
      >
        <Trash2 className='size-4' />
      </Button>
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
