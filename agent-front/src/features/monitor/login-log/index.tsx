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
import { cleanLoginLog, deleteLoginLogs, fetchLoginLogPage } from './api'
import {
  LoginLogSearchForm,
  type LoginLogSearchFormState,
} from './components/login-log-search-form'
import { LoginLogTable } from './components/login-log-table'
import { type LoginLog } from './model'
import {
  loginLogSearchSchema,
  type LoginLogSearchState,
} from './search-schema'

type Props = {
  search: Record<string, unknown>
  navigate: NavigateFn
}

const paginationColumns: ColumnDef<LoginLog>[] = []

export function LoginLogPage({ search, navigate }: Props) {
  const parsed = loginLogSearchSchema.parse(search)
  const queryClient = useQueryClient()
  const canRemoveLogs = useAccess({ permissions: ['monitor:loginlog:remove'] })

  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [bulkDeleteOpen, setBulkDeleteOpen] = useState(false)
  const [cleanOpen, setCleanOpen] = useState(false)

  const [localFilters, setLocalFilters] = useState<LoginLogSearchFormState>({
    username: parsed.username ?? '',
    ipaddr: parsed.ipaddr ?? '',
    status: parsed.status !== undefined ? String(parsed.status) : '',
    beginTime: parsed.beginTime ?? '',
    endTime: parsed.endTime ?? '',
  })

  useEffect(() => {
    setLocalFilters({
      username: parsed.username ?? '',
      ipaddr: parsed.ipaddr ?? '',
      status: parsed.status !== undefined ? String(parsed.status) : '',
      beginTime: parsed.beginTime ?? '',
      endTime: parsed.endTime ?? '',
    })
  }, [parsed.beginTime, parsed.endTime, parsed.ipaddr, parsed.status, parsed.username])

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
      username: parsed.username,
      ipaddr: parsed.ipaddr,
      status: parsed.status,
      beginTime: parsed.beginTime,
      endTime: parsed.endTime,
    }),
    [parsed]
  )

  const logsQuery = useQuery({
    queryKey: ['monitor', 'loginlog', 'page', query],
    queryFn: () => fetchLoginLogPage(query),
    placeholderData: keepPreviousData,
  })

  const deleteMutation = useMutation({
    mutationFn: (ids: string[]) => deleteLoginLogs(ids),
    onSuccess: () => {
      toast.success('删除成功')
      setSelectedIds(new Set())
      queryClient.invalidateQueries({ queryKey: ['monitor', 'loginlog'] })
    },
    onError: (err) => {
      const message =
        (err as AxiosError<{ msg?: string }>)?.response?.data?.msg ?? '删除失败'
      toast.error(message)
    },
  })

  const cleanMutation = useMutation({
    mutationFn: () => cleanLoginLog(),
    onSuccess: () => {
      toast.success('已清空登录日志')
      setSelectedIds(new Set())
      queryClient.invalidateQueries({ queryKey: ['monitor', 'loginlog'] })
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
    records: [] as LoginLog[],
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

  function updateSearch(next: Partial<LoginLogSearchState>) {
    navigate({
      search: (prev) => ({ ...prev, ...next }),
      replace: true,
    })
  }

  function applyFilters() {
    updateSearch({
      username: localFilters.username || undefined,
      ipaddr: localFilters.ipaddr || undefined,
      status:
        localFilters.status === '' ? undefined : Number(localFilters.status),
      beginTime: localFilters.beginTime || undefined,
      endTime: localFilters.endTime || undefined,
      page: 1,
    })
  }

  function resetFilters() {
    setLocalFilters({
      username: '',
      ipaddr: '',
      status: '',
      beginTime: '',
      endTime: '',
    })
    updateSearch({
      username: undefined,
      ipaddr: undefined,
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
    setSelectedIds(new Set(page.records.map((l) => l.infoId)))
  }

  function toggleSelect(id: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
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
          <h2 className='text-2xl font-bold tracking-tight'>登录日志</h2>
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

        <LoginLogSearchForm
          value={localFilters}
          onChange={setLocalFilters}
          onSubmit={applyFilters}
          onReset={resetFilters}
        />

        <LoginLogTable
          records={page.records}
          selectedIds={selectedIds}
          isLoading={logsQuery.isLoading}
          allowSelection={canRemoveLogs}
          onToggleSelectAll={toggleSelectAll}
          onToggleSelect={toggleSelect}
        />

        <DataTablePagination table={paginationTable} className='mt-auto' />

        {canRemoveLogs ? (
          <SelectionBulkActions
            selectedCount={selectedIds.size}
            entityName='登录日志'
            onClearSelection={() => setSelectedIds(new Set())}
          >
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant='destructive'
                  size='icon'
                  onClick={() => setBulkDeleteOpen(true)}
                  className='size-8'
                  aria-label='删除所选登录日志'
                  title='删除所选登录日志'
                >
                  <Trash2 />
                  <span className='sr-only'>删除所选登录日志</span>
                </Button>
              </TooltipTrigger>
              <TooltipContent>
                <p>删除所选登录日志</p>
              </TooltipContent>
            </Tooltip>
          </SelectionBulkActions>
        ) : null}
      </Main>

      <ConfirmDialog
        open={bulkDeleteOpen}
        onOpenChange={setBulkDeleteOpen}
        title='批量删除登录日志'
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
        title='清空登录日志'
        desc={`确定清空全部 ${page.total} 条登录日志吗?此操作不可撤销。`}
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
