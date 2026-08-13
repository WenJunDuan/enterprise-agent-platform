import { useMemo, useRef, useState } from 'react'
import {
  type ColumnDef,
  type ColumnFiltersState,
  flexRender,
  type OnChangeFn,
  type PaginationState,
  type Row,
  type RowSelectionState,
  useTable,
  type ColumnVisibilityState,
} from '@tanstack/react-table'
import {
  CircleAlert,
  Clock3,
  FileSearch,
  Plus,
  RotateCcw,
  Trash2,
  UploadCloud,
} from 'lucide-react'
import { toast } from 'sonner'
import { appTableFeatures, type AppTableFeatures } from '@/lib/table-features'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { DataTablePagination, DataTableToolbar } from '@/components/data-table'
import { ACCEPTED_DOCUMENT_FILE_TYPES } from '../supported-document-formats'
import type { DashboardSummary, TenderProject } from '../types'
import { StatusBadge } from './status-badge'

const statToneClass = {
  blue: 'bg-blue-500',
  amber: 'bg-amber-500',
  green: 'bg-emerald-500',
  muted: 'bg-muted-foreground',
} satisfies Record<DashboardSummary['stats'][number]['tone'], string>

const progressToneClass = {
  doing: 'bg-blue-500',
  review: 'bg-amber-500',
  done: 'bg-emerald-500',
  archived: 'bg-muted-foreground',
} satisfies Record<TenderProject['status'], string>

const projectStatusOptions = [
  { value: 'doing', label: '分析中' },
  { value: 'review', label: '待复核' },
  { value: 'done', label: '已完成' },
  { value: 'archived', label: '已归档' },
]

export function DashboardView({
  summary,
  projects,
  onOpenProject,
  onCreateReview,
  readOnly = false,
  emptyMessage,
  notice,
  onBatchDelete,
  onBatchRetry,
  onAppendBidder,
}: {
  summary: DashboardSummary
  projects: TenderProject[]
  onOpenProject: (projectId: string) => void
  readOnly?: boolean
  emptyMessage?: string
  notice?: string
  /** B③: 创建评审 按钮 callback */
  onCreateReview: () => void
  /** B⑤: batch delete selected project task ids */
  onBatchDelete: (projectIds: string[]) => Promise<void>
  /** B⑤: batch retry selected project task ids */
  onBatchRetry: (projectIds: string[]) => Promise<void>
  /** B⑥: append a new bidder to an existing project */
  onAppendBidder: (
    projectId: string,
    bidderName: string | undefined,
    tenderFiles: File[],
    bidderFiles: File[]
  ) => Promise<void>
}) {
  return (
    <div className='space-y-4'>
      <DashboardMetrics summary={summary} />
      <ProjectTable
        projects={projects}
        readOnly={readOnly}
        emptyMessage={emptyMessage}
        notice={notice}
        onOpenProject={onOpenProject}
        onCreateReview={onCreateReview}
        onBatchDelete={onBatchDelete}
        onBatchRetry={onBatchRetry}
        onAppendBidder={onAppendBidder}
      />
    </div>
  )
}

function DashboardMetrics({ summary }: { summary: DashboardSummary }) {
  return (
    <div className='grid gap-3 sm:grid-cols-2 xl:grid-cols-4'>
      {summary.stats.map((stat) => (
        <Card key={stat.label}>
          <CardContent className='px-4 py-3'>
            <div className='flex items-center gap-2 text-sm font-medium text-muted-foreground'>
              <span
                className={cn('size-2 rounded-full', statToneClass[stat.tone])}
              />
              {stat.label}
            </div>
            <div className='mt-1 text-xl font-semibold'>{stat.count}</div>
          </CardContent>
        </Card>
      ))}
    </div>
  )
}

function ProjectTable({
  projects,
  onOpenProject,
  onCreateReview,
  readOnly,
  emptyMessage,
  notice,
  onBatchDelete,
  onBatchRetry,
  onAppendBidder,
}: {
  projects: TenderProject[]
  onOpenProject: (projectId: string) => void
  onCreateReview: () => void
  readOnly: boolean
  emptyMessage?: string
  notice?: string
  onBatchDelete: (projectIds: string[]) => Promise<void>
  onBatchRetry: (projectIds: string[]) => Promise<void>
  onAppendBidder: (
    projectId: string,
    bidderName: string | undefined,
    tenderFiles: File[],
    bidderFiles: File[]
  ) => Promise<void>
}) {
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({})
  const [isBatchAction, setIsBatchAction] = useState(false)

  const columns = useMemo<ColumnDef<AppTableFeatures, TenderProject>[]>(
    () => [
      // B①: checkbox column for multi-selection
      {
        id: 'select',
        header: ({ table }) => (
          <Checkbox
            checked={
              table.getIsAllPageRowsSelected() ||
              (table.getIsSomePageRowsSelected() && 'indeterminate')
            }
            onCheckedChange={(value) =>
              table.toggleAllPageRowsSelected(!!value)
            }
            aria-label='全选'
          />
        ),
        cell: ({ row }) => (
          <Checkbox
            checked={row.getIsSelected()}
            onCheckedChange={(value) => row.toggleSelected(!!value)}
            aria-label='选择行'
          />
        ),
        enableSorting: false,
        enableHiding: false,
      },
      {
        id: 'searchText',
        accessorFn: (project) =>
          `${project.name} ${project.code} ${project.method} ${project.recommendedBidder}`,
        header: '查询',
        enableHiding: false,
        filterFn: 'includesString',
      },
      {
        id: 'project',
        accessorKey: 'name',
        header: '项目名称 / 编号',
        cell: ({ row }) => {
          const project = row.original
          return (
            <div className='flex min-w-0 items-center gap-3'>
              <ProjectIcon status={project.status} />
              <button
                type='button'
                className='min-w-0 text-left'
                onClick={() => onOpenProject(project.id)}
              >
                <div className='truncate font-medium'>{project.name}</div>
                <div className='mt-1 truncate text-xs text-muted-foreground'>
                  {project.code} · {project.bidderCount} 家投标方
                </div>
              </button>
            </div>
          )
        },
        meta: { label: '项目名称' },
      },
      {
        accessorKey: 'method',
        header: '评标办法',
        cell: ({ row }) => (
          <span className='text-muted-foreground'>{row.original.method}</span>
        ),
        meta: { label: '评标办法' },
      },
      {
        accessorKey: 'stage',
        header: '进度',
        cell: ({ row }) => {
          const project = row.original
          return (
            <div className='min-w-[190px] space-y-2'>
              <div className='flex justify-between text-xs text-muted-foreground'>
                <span>{project.stage}</span>
                <span className='font-medium text-foreground'>
                  {project.progress}%
                </span>
              </div>
              <div className='h-2 overflow-hidden rounded-full bg-muted'>
                <div
                  className={cn(
                    'h-full rounded-full',
                    progressToneClass[project.status]
                  )}
                  style={{ width: `${project.progress}%` }}
                />
              </div>
            </div>
          )
        },
        meta: { label: '进度' },
      },
      {
        accessorKey: 'riskCount',
        header: '待复核',
        cell: ({ row }) => (
          <span className='font-semibold'>{row.original.riskCount} 项</span>
        ),
        meta: { label: '待复核' },
      },
      {
        accessorKey: 'date',
        header: '日期',
        cell: ({ row }) => (
          <span className='text-muted-foreground'>{row.original.date}</span>
        ),
        meta: { label: '日期' },
      },
      {
        accessorKey: 'status',
        header: '状态',
        cell: ({ row }) => <StatusBadge status={row.original.status} />,
        filterFn: matchesSelectedValues,
        meta: { label: '状态' },
      },
      {
        id: 'actions',
        header: () => <div className='text-right'>操作</div>,
        // B②: 行内不再显示 重新审核/删除 按钮，只保留查看详情
        cell: ({ row }) => (
          <div className='text-right'>
            <Button
              variant='outline'
              size='sm'
              onClick={() => onOpenProject(row.original.id)}
            >
              {getProjectActionLabel(row.original.status)}
            </Button>
          </div>
        ),
        enableHiding: false,
      },
    ],
    [onOpenProject]
  )
  const [columnFilters, setColumnFilters] = useState<ColumnFiltersState>([])
  const [columnVisibility, setColumnVisibility] =
    useState<ColumnVisibilityState>({
      searchText: false,
    })
  const [pagination, setPagination] = useState<PaginationState>({
    pageIndex: 0,
    pageSize: 10,
  })
  const handleColumnFiltersChange: OnChangeFn<ColumnFiltersState> = (
    updater
  ) => {
    setColumnFilters((current) =>
      typeof updater === 'function' ? updater(current) : updater
    )
    setPagination((current) => ({ ...current, pageIndex: 0 }))
  }

  const table = useTable({
    features: appTableFeatures,
    data: projects,
    columns,
    state: {
      columnFilters,
      columnVisibility,
      pagination,
      rowSelection,
    },
    onColumnFiltersChange: handleColumnFiltersChange,
    onColumnVisibilityChange: setColumnVisibility,
    onPaginationChange: setPagination,
    onRowSelectionChange: setRowSelection,
  })

  const selectedProjects = table
    .getSelectedRowModel()
    .rows.map((row) => row.original)

  /** B⑤: batch delete — delegates to parent which has access to raw bid request_ids */
  async function handleBatchDelete() {
    if (selectedProjects.length === 0) return
    setIsBatchAction(true)
    try {
      await onBatchDelete(selectedProjects.map((project) => project.id))
      setRowSelection({})
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : '批量删除失败，请重试。'
      )
    } finally {
      setIsBatchAction(false)
    }
  }

  /** B⑤: batch retry — delegates to parent which has access to raw bid request_ids */
  async function handleBatchRetry() {
    if (selectedProjects.length === 0) return
    setIsBatchAction(true)
    try {
      await onBatchRetry(selectedProjects.map((project) => project.id))
      setRowSelection({})
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : '批量重新审核失败，请重试。'
      )
    } finally {
      setIsBatchAction(false)
    }
  }

  return (
    <Card>
      <CardHeader className='flex flex-row flex-wrap items-start justify-between gap-3'>
        <div>
          <CardTitle className='flex items-center gap-2'>
            <FileSearch className='size-5 text-primary' />
            项目列表
            <Badge variant='secondary'>{projects.length}</Badge>
          </CardTitle>
          <CardDescription>查询招投标项目并跟踪审核状态。</CardDescription>
        </div>

        {/* B③/B④/B⑤/B⑥: 操作区上移到标题右侧 */}
        <div className='flex flex-wrap items-center justify-end gap-2'>
          {selectedProjects.length > 0 ? (
            <span className='text-sm text-muted-foreground'>
              已选 {selectedProjects.length} 个项目
            </span>
          ) : null}

          {readOnly ? null : (
            <>
              <Button
                variant='outline'
                size='sm'
                disabled={selectedProjects.length === 0 || isBatchAction}
                onClick={handleBatchDelete}
              >
                <Trash2 className='size-4' />
                删除
              </Button>

              <Button
                variant='outline'
                size='sm'
                disabled={selectedProjects.length === 0 || isBatchAction}
                onClick={handleBatchRetry}
              >
                <RotateCcw className='size-4' />
                重新审核
              </Button>

              {selectedProjects.length === 1 ? (
                <AppendBidderDialog
                  projectId={selectedProjects[0]!.id}
                  onAppend={onAppendBidder}
                  onSuccess={() => setRowSelection({})}
                />
              ) : null}

              <Button size='sm' onClick={onCreateReview}>
                <Plus className='size-4' />
                创建评审
              </Button>
            </>
          )}
        </div>
      </CardHeader>
      <CardContent className='space-y-4'>
        {notice ? (
          <div className='rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800'>
            {notice}
          </div>
        ) : null}
        {projects.length === 0 && emptyMessage ? (
          <div className='rounded-md border border-dashed p-4 text-sm text-muted-foreground'>
            {emptyMessage}
          </div>
        ) : null}
        <DataTableToolbar
          table={table}
          searches={[
            {
              columnId: 'searchText',
              placeholder: '查询项目名称、招标编号或投标单位...',
              className: 'h-8 w-full sm:w-[300px] lg:w-[400px]',
            },
          ]}
          filters={[
            {
              columnId: 'status',
              title: '状态',
              options: projectStatusOptions,
            },
          ]}
        />
        <div className='overflow-hidden rounded-md border'>
          <Table>
            <TableHeader>
              {table.getHeaderGroups().map((headerGroup) => (
                <TableRow key={headerGroup.id} className='group/row'>
                  {headerGroup.headers.map((header) => (
                    <TableHead
                      key={header.id}
                      colSpan={header.colSpan}
                      className={cn(
                        'bg-background group-hover/row:bg-muted',
                        header.column.columnDef.meta?.className,
                        header.column.columnDef.meta?.thClassName
                      )}
                    >
                      {header.isPlaceholder
                        ? null
                        : flexRender(
                            header.column.columnDef.header,
                            header.getContext()
                          )}
                    </TableHead>
                  ))}
                </TableRow>
              ))}
            </TableHeader>
            <TableBody>
              {table.getRowModel().rows.length > 0 ? (
                table.getRowModel().rows.map((row) => (
                  <TableRow
                    key={row.id}
                    className='group/row'
                    data-state={row.getIsSelected() ? 'selected' : undefined}
                  >
                    {row.getVisibleCells().map((cell) => (
                      <TableCell
                        key={cell.id}
                        className={cn(
                          'bg-background group-hover/row:bg-muted',
                          cell.column.columnDef.meta?.className,
                          cell.column.columnDef.meta?.tdClassName
                        )}
                      >
                        {flexRender(
                          cell.column.columnDef.cell,
                          cell.getContext()
                        )}
                      </TableCell>
                    ))}
                  </TableRow>
                ))
              ) : (
                <TableRow>
                  <TableCell
                    colSpan={columns.length}
                    className='h-24 text-center text-muted-foreground'
                  >
                    暂无符合条件的项目。
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
        <DataTablePagination table={table} />
      </CardContent>
    </Card>
  )
}

/**
 * B⑥: Append-bidder dialog.
 * Calls POST /tender/projects/{id}/evaluate with mode=upload + files via onAppend.
 */
function AppendBidderDialog({
  projectId,
  onAppend,
  onSuccess,
}: {
  projectId: string
  onAppend: (
    projectId: string,
    bidderName: string | undefined,
    tenderFiles: File[],
    bidderFiles: File[]
  ) => Promise<void>
  onSuccess: () => void
}) {
  const [open, setOpen] = useState(false)
  const [bidderName, setBidderName] = useState('')
  const [tenderFiles, setTenderFiles] = useState<File[]>([])
  const [bidderFiles, setBidderFiles] = useState<File[]>([])
  const [submitting, setSubmitting] = useState(false)
  const tenderInputRef = useRef<HTMLInputElement>(null)
  const bidderInputRef = useRef<HTMLInputElement>(null)

  function handleClose() {
    setOpen(false)
    setBidderName('')
    setTenderFiles([])
    setBidderFiles([])
  }

  async function handleSubmit() {
    if (bidderFiles.length === 0) {
      toast.error('请至少上传一个投标文件。')
      return
    }
    setSubmitting(true)
    try {
      await onAppend(
        projectId,
        bidderName.trim() || undefined,
        tenderFiles,
        bidderFiles
      )
      toast.success('已追加投标人审核，任务已提交。')
      handleClose()
      onSuccess()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '追加失败，请重试。')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant='outline' size='sm'>
          <UploadCloud className='size-4' />
          追加公司审核
        </Button>
      </DialogTrigger>
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>追加公司审核</DialogTitle>
          <DialogDescription>
            为当前招标项目追加一家投标人的文件，提交后自动触发评标。
          </DialogDescription>
        </DialogHeader>
        <div className='space-y-4'>
          <div>
            <Label
              htmlFor='append-bidder-name'
              className='mb-2 block text-sm font-medium'
            >
              投标单位名称（选填）
            </Label>
            <Input
              id='append-bidder-name'
              value={bidderName}
              onChange={(event) => setBidderName(event.target.value)}
              placeholder='如：中铁五局'
            />
          </div>
          <div>
            <Label
              htmlFor='append-tender-files'
              className='mb-2 block text-sm font-medium'
            >
              招标文件（选填，已有可不再上传）
            </Label>
            <input
              id='append-tender-files'
              ref={tenderInputRef}
              multiple
              type='file'
              accept={ACCEPTED_DOCUMENT_FILE_TYPES}
              className='hidden'
              onChange={(event) =>
                setTenderFiles(Array.from(event.target.files ?? []))
              }
            />
            <Button
              type='button'
              variant='outline'
              size='sm'
              className='w-full'
              onClick={() => tenderInputRef.current?.click()}
            >
              <UploadCloud className='size-4' />
              {tenderFiles.length > 0
                ? `已选 ${tenderFiles.length} 个招标文件`
                : '选择招标文件'}
            </Button>
          </div>
          <div>
            <Label
              htmlFor='append-bidder-files'
              className='mb-2 block text-sm font-medium'
            >
              投标文件（必传）
            </Label>
            <input
              id='append-bidder-files'
              ref={bidderInputRef}
              multiple
              type='file'
              accept={ACCEPTED_DOCUMENT_FILE_TYPES}
              className='hidden'
              onChange={(event) =>
                setBidderFiles(Array.from(event.target.files ?? []))
              }
            />
            <Button
              type='button'
              variant='outline'
              size='sm'
              className='w-full'
              onClick={() => bidderInputRef.current?.click()}
            >
              <UploadCloud className='size-4' />
              {bidderFiles.length > 0
                ? `已选 ${bidderFiles.length} 个投标文件`
                : '选择投标文件'}
            </Button>
          </div>
        </div>
        <DialogFooter>
          <Button type='button' variant='outline' onClick={handleClose}>
            取消
          </Button>
          <Button type='button' disabled={submitting} onClick={handleSubmit}>
            {submitting ? '提交中...' : '提交审核'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function ProjectIcon({ status }: { status: TenderProject['status'] }) {
  const Icon = status === 'review' ? CircleAlert : Clock3
  const iconClass =
    status === 'review'
      ? 'bg-amber-100 text-amber-700'
      : 'bg-blue-100 text-blue-700'

  return (
    <span
      className={cn(
        'flex size-10 shrink-0 items-center justify-center rounded-lg',
        iconClass
      )}
    >
      <Icon className='size-5' />
    </span>
  )
}

function matchesSelectedValues<TData extends Record<string, unknown>>(
  row: Row<AppTableFeatures, TData>,
  columnId: string,
  filterValue: unknown
) {
  const selected = Array.isArray(filterValue) ? filterValue : []
  return selected.length === 0 || selected.includes(row.getValue(columnId))
}

function getProjectActionLabel(status: TenderProject['status']) {
  if (status === 'review') return '进入复核'
  if (status === 'doing') return '查看进度'
  return '查看详情'
}
