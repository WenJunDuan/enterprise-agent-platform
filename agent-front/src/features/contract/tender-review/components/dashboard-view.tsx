import { useMemo, useState } from 'react'
import {
  type ColumnDef,
  type ColumnFiltersState,
  flexRender,
  getCoreRowModel,
  getFacetedRowModel,
  getFacetedUniqueValues,
  getFilteredRowModel,
  getPaginationRowModel,
  type OnChangeFn,
  type PaginationState,
  type Row,
  useReactTable,
  type VisibilityState,
} from '@tanstack/react-table'
import { CircleAlert, Clock3, FileSearch } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { DataTablePagination, DataTableToolbar } from '@/components/data-table'
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
}: {
  summary: DashboardSummary
  projects: TenderProject[]
  onOpenProject: () => void
}) {
  return (
    <div className='space-y-4'>
      <DashboardMetrics summary={summary} />
      <ProjectTable projects={projects} onOpenProject={onOpenProject} />
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
}: {
  projects: TenderProject[]
  onOpenProject: () => void
}) {
  const columns = useMemo<ColumnDef<TenderProject>[]>(
    () => [
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
                onClick={onOpenProject}
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
        accessorKey: 'score',
        header: '得分',
        cell: ({ row }) => (
          <span className='font-semibold'>{row.original.score}</span>
        ),
        meta: { label: '得分' },
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
        cell: ({ row }) => (
          <div className='text-right'>
            <Button variant='outline' size='sm' onClick={onOpenProject}>
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
  const [columnVisibility, setColumnVisibility] = useState<VisibilityState>({
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

  // eslint-disable-next-line react-hooks/incompatible-library
  const table = useReactTable({
    data: projects,
    columns,
    state: {
      columnFilters,
      columnVisibility,
      pagination,
    },
    onColumnFiltersChange: handleColumnFiltersChange,
    onColumnVisibilityChange: setColumnVisibility,
    onPaginationChange: setPagination,
    getCoreRowModel: getCoreRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    getFacetedRowModel: getFacetedRowModel(),
    getFacetedUniqueValues: getFacetedUniqueValues(),
  })

  return (
    <Card>
      <CardHeader>
        <CardTitle className='flex items-center gap-2'>
          <FileSearch className='size-5 text-primary' />
          项目列表
          <Badge variant='secondary'>{projects.length}</Badge>
        </CardTitle>
        <CardDescription>查询招投标项目并跟踪审核状态。</CardDescription>
      </CardHeader>
      <CardContent className='space-y-4'>
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

function matchesSelectedValues<TData>(
  row: Row<TData>,
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
