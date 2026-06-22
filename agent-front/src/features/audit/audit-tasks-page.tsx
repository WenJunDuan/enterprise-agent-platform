import { useCallback, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import {
  type ColumnDef,
  type ColumnFiltersState,
  flexRender,
  getCoreRowModel,
  getFacetedRowModel,
  getFacetedUniqueValues,
  getFilteredRowModel,
  type OnChangeFn,
  type PaginationState,
  type Row,
  useReactTable,
  type VisibilityState,
} from '@tanstack/react-table'
import { FileText, Plus, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import { Alert, AlertDescription } from '@/components/ui/alert'
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
import { DataTablePagination, DataTableToolbar } from '@/components/data-table'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { deleteTask, listTasks, retryTask } from './api'
import { formatDate, taskStatusLabels, truncateId } from './format'
import { formatAmount } from './lib/reimbursement-labels'
import { readSubmissionSummaries } from './lib/submission-summary'
import { TaskStatusBadge } from './status-badge'
import type { AuditTask, SubmissionSummary, TaskStatus } from './types'

const DEFAULT_PAGE_SIZE = 20

const taskStatusOptions = [
  { value: 'accepted', label: taskStatusLabels.accepted },
  { value: 'running', label: taskStatusLabels.running },
  { value: 'completed', label: taskStatusLabels.completed },
  { value: 'failed', label: taskStatusLabels.failed },
]

type AuditTaskRow = {
  task: AuditTask
  summary?: SubmissionSummary
  searchText: string
  displayId: string
  amountText: string
  submittedAtText: string
  status: TaskStatus
}

function TaskStats({ tasks }: { tasks: AuditTask[] }) {
  const stats = useMemo(() => {
    const total = tasks.length
    const active = tasks.filter(
      (task) => task.status === 'accepted' || task.status === 'running'
    ).length
    const completed = tasks.filter((task) => task.status === 'completed').length
    const failed = tasks.filter((task) => task.status === 'failed').length
    const completionRate = total > 0 ? Math.round((completed / total) * 100) : 0
    return { total, active, completed, failed, completionRate }
  }, [tasks])

  return (
    <div className='grid gap-3 md:grid-cols-4'>
      <Card>
        <CardHeader className='pb-2'>
          <CardDescription>当前页任务</CardDescription>
          <CardTitle className='text-2xl'>{stats.total}</CardTitle>
        </CardHeader>
      </Card>
      <Card>
        <CardHeader className='pb-2'>
          <CardDescription>待处理</CardDescription>
          <CardTitle className='text-2xl text-amber-600'>
            {stats.active}
          </CardTitle>
        </CardHeader>
      </Card>
      <Card>
        <CardHeader className='pb-2'>
          <CardDescription>已完成</CardDescription>
          <CardTitle className='text-2xl text-emerald-600'>
            {stats.completed}
          </CardTitle>
        </CardHeader>
      </Card>
      <Card>
        <CardHeader className='pb-2'>
          <CardDescription>完成率 / 失败</CardDescription>
          <CardTitle className='text-2xl'>
            {stats.completionRate}% / {stats.failed}
          </CardTitle>
        </CardHeader>
      </Card>
    </div>
  )
}

export function AuditTasksPage() {
  const [columnFilters, setColumnFilters] = useState<ColumnFiltersState>([])
  const [columnVisibility, setColumnVisibility] = useState<VisibilityState>({
    searchText: false,
  })
  const [pagination, setPagination] = useState<PaginationState>({
    pageIndex: 0,
    pageSize: DEFAULT_PAGE_SIZE,
  })
  const [actionId, setActionId] = useState<string | null>(null)
  const summaries = readSubmissionSummaries()
  const selectedStatuses = getSelectedStatuses(columnFilters)
  const serverStatus =
    selectedStatuses.length === 1 ? selectedStatuses[0] : undefined
  const offset = pagination.pageIndex * pagination.pageSize

  const tasksQuery = useQuery({
    queryKey: [
      'audit-tasks',
      serverStatus,
      pagination.pageIndex,
      pagination.pageSize,
      offset,
    ],
    queryFn: () =>
      listTasks({
        status: serverStatus,
        limit: pagination.pageSize + 1,
        offset,
      }),
  })

  const pageTasks = useMemo(
    () => (tasksQuery.data ?? []).slice(0, pagination.pageSize),
    [pagination.pageSize, tasksQuery.data]
  )
  const hasNextPage = (tasksQuery.data?.length ?? 0) > pagination.pageSize
  const rows = useMemo<AuditTaskRow[]>(
    () =>
      pageTasks.map((task) => {
        const summary = summaries[task.request_id]
        const displayId = summary?.form.case_id ?? task.claim_id ?? '-'
        const amountText = summary
          ? formatAmount(summary.form.total_amount, summary.form.currency)
          : '-'
        const submittedAtText = formatDate(task.submitted_at)
        return {
          task,
          summary,
          searchText: [
            displayId,
            task.request_id,
            amountText,
            task.progress_message,
            task.error_detail,
          ]
            .filter(Boolean)
            .join(' '),
          displayId,
          amountText,
          submittedAtText,
          status: task.status,
        }
      }),
    [pageTasks, summaries]
  )

  const refetchTasks = tasksQuery.refetch
  const runAction = useCallback(
    async (id: string, kind: 'retry' | 'delete') => {
      setActionId(id)
      try {
        if (kind === 'retry') {
          await retryTask(id)
          toast.success('已触发重新审核')
        } else {
          await deleteTask(id)
          toast.success('已删除任务')
        }
        await refetchTasks()
      } catch (error) {
        toast.error(
          error instanceof Error ? error.message : '操作失败，请重试。'
        )
      } finally {
        setActionId(null)
      }
    },
    [refetchTasks]
  )

  const columns = useMemo<ColumnDef<AuditTaskRow>[]>(
    () => [
      {
        id: 'searchText',
        accessorKey: 'searchText',
        header: '查询',
        enableHiding: false,
        filterFn: 'includesString',
      },
      {
        id: 'identity',
        accessorKey: 'displayId',
        header: '单号 / 请求 ID',
        cell: ({ row }) => {
          const { task, displayId } = row.original
          return (
            <div className='flex min-w-0 items-center gap-3'>
              <div className='rounded-md border bg-muted/40 p-2'>
                <FileText className='size-4 text-muted-foreground' />
              </div>
              <div className='min-w-0'>
                <div className='truncate font-medium'>{displayId}</div>
                <div className='font-mono text-xs text-muted-foreground'>
                  {truncateId(task.request_id)}
                </div>
              </div>
            </div>
          )
        },
        meta: { label: '单号' },
      },
      {
        accessorKey: 'status',
        header: '状态',
        cell: ({ row }) => <TaskStatusBadge status={row.original.status} />,
        filterFn: matchesSelectedValues,
        meta: { label: '状态' },
      },
      {
        accessorKey: 'amountText',
        header: '金额概要',
        cell: ({ row }) => (
          <span className='text-muted-foreground'>
            {row.original.amountText}
          </span>
        ),
        meta: { label: '金额概要' },
      },
      {
        accessorKey: 'submittedAtText',
        header: '提交时间',
        cell: ({ row }) => (
          <span className='text-muted-foreground'>
            {row.original.submittedAtText}
          </span>
        ),
        meta: { label: '提交时间' },
      },
      {
        id: 'actions',
        header: () => <div className='text-right'>操作</div>,
        cell: ({ row }) => {
          const task = row.original.task
          const canRetry =
            task.status === 'failed' || task.status === 'completed'
          return (
            <div className='flex justify-end gap-2'>
              <Button variant='ghost' size='sm' asChild>
                <Link
                  to='/audit/tasks/$taskId'
                  params={{ taskId: task.request_id }}
                >
                  详情
                </Link>
              </Button>
              {canRetry ? (
                <Button
                  variant='outline'
                  size='sm'
                  disabled={actionId === task.request_id}
                  onClick={() => runAction(task.request_id, 'retry')}
                >
                  重审
                </Button>
              ) : null}
              <Button
                variant='ghost'
                size='icon'
                disabled={actionId === task.request_id}
                onClick={() => runAction(task.request_id, 'delete')}
                aria-label='删除任务'
              >
                <Trash2 className='size-4' />
              </Button>
            </div>
          )
        },
        enableHiding: false,
      },
    ],
    [actionId, runAction]
  )

  const rowCount = estimateRowCount({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    loadedCount: pageTasks.length,
    hasNextPage,
  })

  const handleColumnFiltersChange: OnChangeFn<ColumnFiltersState> = (
    updater
  ) => {
    setColumnFilters((current) =>
      typeof updater === 'function' ? updater(current) : updater
    )
    setPagination((current) => ({ ...current, pageIndex: 0 }))
  }

  // eslint-disable-next-line react-hooks/incompatible-library
  const table = useReactTable({
    data: rows,
    columns,
    state: {
      columnFilters,
      columnVisibility,
      pagination,
    },
    manualPagination: true,
    pageCount: Math.max(1, Math.ceil(rowCount / pagination.pageSize)),
    rowCount,
    onColumnFiltersChange: handleColumnFiltersChange,
    onColumnVisibilityChange: setColumnVisibility,
    onPaginationChange: setPagination,
    getCoreRowModel: getCoreRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getFacetedRowModel: getFacetedRowModel(),
    getFacetedUniqueValues: getFacetedUniqueValues(),
  })

  return (
    <>
      <Header fixed />
      <Main className='space-y-5'>
        <div>
          <h1 className='text-2xl font-semibold tracking-tight'>报销审核</h1>
          <p className='text-sm text-muted-foreground'>
            管理报销审核任务、跟踪状态，并查看审核结论。
          </p>
        </div>

        <TaskStats tasks={pageTasks} />

        <Card>
          <CardHeader className='flex flex-row items-center justify-between gap-3'>
            <div>
              <CardTitle>报销审核记录</CardTitle>
              <CardDescription>查看已提交的审核记录。</CardDescription>
            </div>
            <Button asChild>
              <Link to='/audit/submit'>
                <Plus className='size-4' />
                新建报销审核
              </Link>
            </Button>
          </CardHeader>
          <CardContent className='space-y-4'>
            <DataTableToolbar
              table={table}
              searchKey='searchText'
              searchPlaceholder='查询单号、请求 ID 或审核摘要...'
              filters={[
                {
                  columnId: 'status',
                  title: '状态',
                  options: taskStatusOptions,
                },
              ]}
            />
            {tasksQuery.error ? (
              <Alert variant='destructive'>
                <AlertDescription>
                  {tasksQuery.error instanceof Error
                    ? tasksQuery.error.message
                    : '加载失败'}
                </AlertDescription>
              </Alert>
            ) : null}

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
                  {tasksQuery.isLoading ? (
                    <TableRow>
                      <TableCell
                        colSpan={table.getVisibleLeafColumns().length}
                        className='h-24 text-center text-muted-foreground'
                      >
                        报销审核记录加载中...
                      </TableCell>
                    </TableRow>
                  ) : table.getRowModel().rows.length > 0 ? (
                    table.getRowModel().rows.map((row) => (
                      <TableRow key={row.id} className='group/row'>
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
                        colSpan={table.getVisibleLeafColumns().length}
                        className='h-28 text-center text-muted-foreground'
                      >
                        暂无任务，可新建报销审核申请。
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </div>
            <DataTablePagination table={table} />
          </CardContent>
        </Card>
      </Main>
    </>
  )
}

function getSelectedStatuses(filters: ColumnFiltersState): TaskStatus[] {
  const value = filters.find((filter) => filter.id === 'status')?.value
  if (!Array.isArray(value)) return []
  return value.filter(isTaskStatus)
}

function isTaskStatus(value: unknown): value is TaskStatus {
  return (
    value === 'accepted' ||
    value === 'running' ||
    value === 'completed' ||
    value === 'failed'
  )
}

function matchesSelectedValues<TData>(
  row: Row<TData>,
  columnId: string,
  filterValue: unknown
) {
  const selected = Array.isArray(filterValue) ? filterValue : []
  return selected.length === 0 || selected.includes(row.getValue(columnId))
}

function estimateRowCount({
  pageIndex,
  pageSize,
  loadedCount,
  hasNextPage,
}: {
  pageIndex: number
  pageSize: number
  loadedCount: number
  hasNextPage: boolean
}) {
  const loadedThroughCurrentPage = pageIndex * pageSize + loadedCount
  if (hasNextPage) return loadedThroughCurrentPage + pageSize
  return Math.max(loadedThroughCurrentPage, 0)
}
