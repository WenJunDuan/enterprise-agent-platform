import { useEffect, useMemo, useState } from 'react'
import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query'
import { getCoreRowModel, type ColumnDef, useReactTable } from '@tanstack/react-table'
import type { AxiosError } from 'axios'
import { RefreshCw, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { useAccess } from '@/app/auth/access'
import { type NavigateFn, useTableUrlState } from '@/hooks/use-table-url-state'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { DataTablePagination, SelectionBulkActions } from '@/components/data-table'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { Search } from '@/components/search'
import { Button } from '@/components/ui/button'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import {
  cleanOperLog,
  deleteOperLogs,
  fetchOperLogDetail,
  fetchOperLogPage,
} from './api'
import { OperLogDetailDrawer } from './components/oper-log-detail-drawer'
import {
  OperLogSearchForm,
  type OperLogSearchFormState,
} from './components/oper-log-search-form'
import { OperLogTable } from './components/oper-log-table'
import { type OperLog } from './model'
import {
  operLogSearchSchema,
  type OperLogSearchState,
} from './search-schema'

type Props = {
  search: Record<string, unknown>
  navigate: NavigateFn
}

const paginationColumns: ColumnDef<OperLog>[] = []

export function OperLogPage({ search, navigate }: Props) {
  const parsed = operLogSearchSchema.parse(search)
  const queryClient = useQueryClient()
  const canQueryDetail = useAccess({ permissions: ['monitor:operlog:query'] })
  const canRemoveLogs = useAccess({ permissions: ['monitor:operlog:remove'] })

  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [detailLog, setDetailLog] = useState<OperLog | null>(null)
  const [detailOpen, setDetailOpen] = useState(false)
  const [bulkDeleteOpen, setBulkDeleteOpen] = useState(false)
  const [cleanOpen, setCleanOpen] = useState(false)

  const [localFilters, setLocalFilters] = useState<OperLogSearchFormState>({
    title: parsed.title ?? '',
    operName: parsed.operName ?? '',
    businessType:
      parsed.businessType !== undefined ? String(parsed.businessType) : '',
    status: parsed.status !== undefined ? String(parsed.status) : '',
    beginTime: parsed.beginTime ?? '',
    endTime: parsed.endTime ?? '',
  })

  useEffect(() => {
    setLocalFilters({
      title: parsed.title ?? '',
      operName: parsed.operName ?? '',
      businessType:
        parsed.businessType !== undefined ? String(parsed.businessType) : '',
      status: parsed.status !== undefined ? String(parsed.status) : '',
      beginTime: parsed.beginTime ?? '',
      endTime: parsed.endTime ?? '',
    })
  }, [
    parsed.beginTime,
    parsed.businessType,
    parsed.endTime,
    parsed.operName,
    parsed.status,
    parsed.title,
  ])

  const { pagination, onPaginationChange, ensurePageInRange } = useTableUrlState({
    search: parsed,
    navigate,
    pagination: { defaultPage: 1, defaultPageSize: 10 },
    globalFilter: { enabled: false },
  })

  const query = useMemo(
    () => ({
      pageNum: parsed.page ?? 1,
      pageSize: parsed.pageSize ?? 10,
      title: parsed.title,
      operName: parsed.operName,
      businessType: parsed.businessType,
      status: parsed.status,
      beginTime: parsed.beginTime,
      endTime: parsed.endTime,
    }),
    [parsed]
  )

  const logsQuery = useQuery({
    queryKey: ['monitor', 'operlog', 'page', query],
    queryFn: () => fetchOperLogPage(query),
    placeholderData: keepPreviousData,
  })

  const deleteMutation = useMutation({
    mutationFn: (ids: string[]) => deleteOperLogs(ids),
    onSuccess: () => {
      toast.success('删除成功')
      setSelectedIds(new Set())
      queryClient.invalidateQueries({ queryKey: ['monitor', 'operlog'] })
    },
    onError: (err) => {
      const message =
        (err as AxiosError<{ msg?: string }>)?.response?.data?.msg ?? '删除失败'
      toast.error(message)
    },
  })

  const cleanMutation = useMutation({
    mutationFn: () => cleanOperLog(),
    onSuccess: () => {
      toast.success('已清空操作日志')
      setSelectedIds(new Set())
      queryClient.invalidateQueries({ queryKey: ['monitor', 'operlog'] })
    },
    onError: (err) => {
      const message =
        (err as AxiosError<{ msg?: string }>)?.response?.data?.msg ?? '清空失败'
      toast.error(message)
    },
  })

  const page = logsQuery.data ?? {
    pageNum: query.pageNum,
    pageSize: query.pageSize,
    total: 0,
    pages: 0,
    records: [] as OperLog[],
  }

  // eslint-disable-next-line react-hooks/incompatible-library
  const paginationTable = useReactTable({
    data: page.records,
    columns: paginationColumns,
    state: { pagination },
    manualPagination: true,
    pageCount: Math.max(page.pages, 1),
    rowCount: page.total,
    onPaginationChange,
    getCoreRowModel: getCoreRowModel(),
  })

  useEffect(() => {
    ensurePageInRange(Math.max(page.pages, 1))
  }, [ensurePageInRange, page.pages])

  function updateSearch(next: Partial<OperLogSearchState>) {
    navigate({
      search: (prev) => ({ ...prev, ...next }),
      replace: true,
    })
  }

  function applyFilters() {
    updateSearch({
      title: localFilters.title || undefined,
      operName: localFilters.operName || undefined,
      businessType:
        localFilters.businessType === ''
          ? undefined
          : Number(localFilters.businessType),
      status:
        localFilters.status === '' ? undefined : Number(localFilters.status),
      beginTime: localFilters.beginTime || undefined,
      endTime: localFilters.endTime || undefined,
      page: 1,
    })
  }

  function resetFilters() {
    setLocalFilters({
      title: '',
      operName: '',
      businessType: '',
      status: '',
      beginTime: '',
      endTime: '',
    })
    updateSearch({
      title: undefined,
      operName: undefined,
      businessType: undefined,
      status: undefined,
      beginTime: undefined,
      endTime: undefined,
      page: 1,
    })
  }

  function toggleSelectAll(checked: boolean) {
    if (!checked) {
      setSelectedIds(new Set())
      return
    }
    setSelectedIds(new Set(page.records.map((l) => l.operId)))
  }

  function toggleSelect(id: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  async function handleShowDetail(logId: string) {
    try {
      const detail = await fetchOperLogDetail(logId)
      setDetailLog(detail)
      setDetailOpen(true)
    } catch {
      toast.error('详情加载失败')
    }
  }

  return (
    <>
      <Header fixed>
        <div className='flex items-center space-x-4'>
          <Search />
          <ProfileDropdown />
        </div>
      </Header>

      <Main className='flex flex-1 flex-col gap-4 sm:gap-6'>
        <div className='flex flex-wrap items-end justify-between gap-3'>
          <h2 className='text-2xl font-bold tracking-tight'>操作日志</h2>
          <div className='flex items-center gap-2'>
            <Button
              variant='outline'
              size='sm'
              onClick={() => logsQuery.refetch()}
              disabled={logsQuery.isFetching}
            >
              <RefreshCw
                className={`mr-1 size-4 ${
                  logsQuery.isFetching ? 'animate-spin' : ''
                }`}
              />
              刷新
            </Button>
            {canRemoveLogs ? (
              <Button
                variant='destructive'
                size='sm'
                onClick={() => setCleanOpen(true)}
              >
                清空
              </Button>
            ) : null}
          </div>
        </div>

        <OperLogSearchForm
          value={localFilters}
          onChange={setLocalFilters}
          onSubmit={applyFilters}
          onReset={resetFilters}
        />

        <OperLogTable
          records={page.records}
          selectedIds={selectedIds}
          isLoading={logsQuery.isLoading}
          allowSelection={canRemoveLogs}
          canShowDetail={canQueryDetail}
          onToggleSelectAll={toggleSelectAll}
          onToggleSelect={toggleSelect}
          onShowDetail={handleShowDetail}
        />

        <DataTablePagination table={paginationTable} className='mt-auto' />

        {canRemoveLogs ? (
          <SelectionBulkActions
            selectedCount={selectedIds.size}
            entityName='操作日志'
            onClearSelection={() => setSelectedIds(new Set())}
          >
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant='destructive'
                  size='icon'
                  onClick={() => setBulkDeleteOpen(true)}
                  className='size-8'
                  aria-label='删除所选操作日志'
                  title='删除所选操作日志'
                >
                  <Trash2 />
                  <span className='sr-only'>删除所选操作日志</span>
                </Button>
              </TooltipTrigger>
              <TooltipContent>
                <p>删除所选操作日志</p>
              </TooltipContent>
            </Tooltip>
          </SelectionBulkActions>
        ) : null}
      </Main>

      <OperLogDetailDrawer
        log={detailLog}
        open={detailOpen}
        onOpenChange={(next) => {
          setDetailOpen(next)
          if (!next) setDetailLog(null)
        }}
      />

      <ConfirmDialog
        open={bulkDeleteOpen}
        onOpenChange={setBulkDeleteOpen}
        title='批量删除操作日志'
        desc={`确定删除选中的 ${selectedIds.size} 条日志吗?此操作不可撤销。`}
        confirmText='删除'
        destructive
        isLoading={deleteMutation.isPending}
        disabled={!canRemoveLogs || selectedIds.size === 0}
        handleConfirm={() => {
          deleteMutation.mutate(Array.from(selectedIds), {
            onSuccess: () => setBulkDeleteOpen(false),
          })
        }}
      />

      <ConfirmDialog
        open={cleanOpen}
        onOpenChange={setCleanOpen}
        title='清空操作日志'
        desc={`确定清空全部 ${page.total} 条操作日志吗?此操作不可撤销。`}
        confirmText='清空'
        destructive
        isLoading={cleanMutation.isPending}
        disabled={!canRemoveLogs}
        handleConfirm={() => {
          cleanMutation.mutate(undefined, {
            onSuccess: () => setCleanOpen(false),
          })
        }}
      />
    </>
  )
}
