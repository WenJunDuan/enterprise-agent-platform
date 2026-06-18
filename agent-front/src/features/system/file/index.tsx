import { useEffect, useMemo, useState } from 'react'
import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query'
import { getCoreRowModel, type ColumnDef, useReactTable } from '@tanstack/react-table'
import type { AxiosError } from 'axios'
import { RefreshCw, Trash2, Upload as UploadIcon } from 'lucide-react'
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
import { deleteFiles, fetchBlob, fetchFilePage } from './api'
import { FilePreviewDialog } from './components/file-preview-dialog'
import {
  FileSearchForm,
  type FileSearchState,
} from './components/file-search-form'
import { FileTable } from './components/file-table'
import { FileUploadDialog } from './components/file-upload-dialog'
import { type SysFile } from './model'
import {
  fileManagementSearchSchema,
  type FileManagementSearchState,
} from './search-schema'

type Props = {
  search: Record<string, unknown>
  navigate: NavigateFn
}

const paginationColumns: ColumnDef<SysFile>[] = []

export function FileManagementPage({ search, navigate }: Props) {
  const parsed = fileManagementSearchSchema.parse(search)
  const queryClient = useQueryClient()
  const canUploadFiles = useAccess({ permissions: ['system:file:upload'] })
  const canDeleteFiles = useAccess({ permissions: ['system:file:remove'] })
  const canDownloadFiles = useAccess({ permissions: ['system:file:download'] })
  const [uploadOpen, setUploadOpen] = useState(false)
  const [previewFile, setPreviewFile] = useState<SysFile | null>(null)
  const [previewOpen, setPreviewOpen] = useState(false)
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [deleteTarget, setDeleteTarget] = useState<SysFile | null>(null)
  const [bulkDeleteOpen, setBulkDeleteOpen] = useState(false)

  const [localFilters, setLocalFilters] = useState<FileSearchState>({
    originalName: parsed.originalName ?? '',
    extension: parsed.extension ?? '',
    bizType: parsed.bizType ?? '',
  })

  useEffect(() => {
    setLocalFilters({
      originalName: parsed.originalName ?? '',
      extension: parsed.extension ?? '',
      bizType: parsed.bizType ?? '',
    })
  }, [parsed.bizType, parsed.extension, parsed.originalName])

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
      originalName: parsed.originalName,
      extension: parsed.extension,
      bizType: parsed.bizType,
    }),
    [parsed]
  )

  const filesQuery = useQuery({
    queryKey: ['system', 'files', 'page', query],
    queryFn: () => fetchFilePage(query),
    placeholderData: keepPreviousData,
  })

  const deleteMutation = useMutation({
    mutationFn: (ids: string[]) => deleteFiles(ids),
    onSuccess: (count) => {
      toast.success(`已删除 ${count} 个文件`)
      setSelectedIds(new Set())
      queryClient.invalidateQueries({
        queryKey: ['system', 'files', 'page'],
      })
    },
    onError: (err) => {
      const message =
        (err as AxiosError<{ msg?: string }>)?.response?.data?.msg ?? '删除失败'
      toast.error(message)
    },
  })

  const page = filesQuery.data ?? {
    pageNum: query.pageNum,
    pageSize: query.pageSize,
    total: 0,
    pages: 0,
    records: [] as SysFile[],
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

  function updateSearch(next: Partial<FileManagementSearchState>) {
    navigate({
      search: (prev) => ({ ...prev, ...next }),
      replace: true,
    })
  }

  function applyFilters() {
    updateSearch({
      originalName: localFilters.originalName || undefined,
      extension: localFilters.extension || undefined,
      bizType: localFilters.bizType || undefined,
      page: 1,
    })
  }

  function resetFilters() {
    setLocalFilters({ originalName: '', extension: '', bizType: '' })
    updateSearch({
      originalName: undefined,
      extension: undefined,
      bizType: undefined,
      page: 1,
    })
  }

  function toggleSelectAll(checked: boolean) {
    if (!checked) {
      setSelectedIds(new Set())
      return
    }
    setSelectedIds(new Set(page.records.map((f) => f.id)))
  }

  function toggleSelect(id: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  async function handleDownload(file: SysFile) {
    try {
      const blob = await fetchBlob(file.id, 'download')
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = file.originalName
      link.click()
      URL.revokeObjectURL(url)
    } catch {
      toast.error('下载失败')
    }
  }

  function handlePreview(file: SysFile) {
    setPreviewFile(file)
    setPreviewOpen(true)
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
          <h2 className='text-2xl font-bold tracking-tight'>文件管理</h2>
          <div className='flex items-center gap-2'>
            <Button
              variant='outline'
              size='sm'
              onClick={() => filesQuery.refetch()}
              disabled={filesQuery.isFetching}
            >
              <RefreshCw
                className={`mr-1 size-4 ${
                  filesQuery.isFetching ? 'animate-spin' : ''
                }`}
              />
              刷新
            </Button>
            {canUploadFiles ? (
              <Button size='sm' onClick={() => setUploadOpen(true)}>
                <UploadIcon className='mr-1 size-4' />
                上传文件
              </Button>
            ) : null}
          </div>
        </div>

        <FileSearchForm
          value={localFilters}
          onChange={setLocalFilters}
          onSubmit={applyFilters}
          onReset={resetFilters}
        />

        <FileTable
          records={page.records}
          selectedIds={selectedIds}
          isLoading={filesQuery.isLoading}
          allowSelection={canDeleteFiles}
          canDelete={canDeleteFiles}
          canDownload={canDownloadFiles}
          onToggleSelectAll={toggleSelectAll}
          onToggleSelect={toggleSelect}
          onPreview={handlePreview}
          onDownload={handleDownload}
          onDelete={setDeleteTarget}
        />

        <DataTablePagination table={paginationTable} className='mt-auto' />

        {canDeleteFiles ? (
          <SelectionBulkActions
            selectedCount={selectedIds.size}
            entityName='文件'
            onClearSelection={() => setSelectedIds(new Set())}
          >
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant='destructive'
                  size='icon'
                  onClick={() => setBulkDeleteOpen(true)}
                  className='size-8'
                  aria-label='删除所选文件'
                  title='删除所选文件'
                >
                  <Trash2 />
                  <span className='sr-only'>删除所选文件</span>
                </Button>
              </TooltipTrigger>
              <TooltipContent>
                <p>删除所选文件</p>
              </TooltipContent>
            </Tooltip>
          </SelectionBulkActions>
        ) : null}
      </Main>

      <FileUploadDialog
        open={uploadOpen}
        onOpenChange={setUploadOpen}
        onUploaded={() =>
          queryClient.invalidateQueries({
            queryKey: ['system', 'files', 'page'],
          })
        }
      />

      <FilePreviewDialog
        file={previewFile}
        open={previewOpen}
        onOpenChange={(next) => {
          setPreviewOpen(next)
          if (!next) setPreviewFile(null)
        }}
      />

      <ConfirmDialog
        open={deleteTarget !== null}
        onOpenChange={(next) => {
          if (!next) setDeleteTarget(null)
        }}
        title='删除文件'
        desc={
          deleteTarget
            ? `确定删除 "${deleteTarget.originalName}" 吗?此操作不可撤销。`
            : ''
        }
        confirmText='删除'
        destructive
        isLoading={deleteMutation.isPending}
        handleConfirm={() => {
          if (!deleteTarget) return
          deleteMutation.mutate([deleteTarget.id], {
            onSuccess: () => setDeleteTarget(null),
          })
        }}
      />

      <ConfirmDialog
        open={bulkDeleteOpen}
        onOpenChange={setBulkDeleteOpen}
        title='批量删除文件'
        desc={`确定删除选中的 ${selectedIds.size} 个文件吗?此操作不可撤销。`}
        confirmText='删除'
        destructive
        isLoading={deleteMutation.isPending}
        disabled={!canDeleteFiles || selectedIds.size === 0}
        handleConfirm={() => {
          deleteMutation.mutate(Array.from(selectedIds), {
            onSuccess: () => setBulkDeleteOpen(false),
          })
        }}
      />
    </>
  )
}
