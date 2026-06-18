import { useMemo, useState } from 'react'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { AxiosError } from 'axios'
import { BookOpenText, Plus, RefreshCw } from 'lucide-react'
import { toast } from 'sonner'
import { useAccess } from '@/app/auth/access'
import type { ApiResult } from '@/types/api'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { Search } from '@/components/search'
import { SelectDropdown } from '@/components/select-dropdown'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  createDictData,
  createDictType,
  deleteDictData,
  deleteDictTypes,
  fetchDictDataList,
  fetchDictTypePage,
  refreshDictCache,
  updateDictData,
  updateDictType,
} from './api'
import { DictDataDialog } from './components/dict-data-dialog'
import { DictTypeDialog } from './components/dict-type-dialog'
import { formatDateTime, type DictData, type DictStatus, type DictType } from './model'

const statusOptions = [
  { label: '全部状态', value: 'all' },
  { label: '正常', value: '1' },
  { label: '停用', value: '0' },
] as const

function normalizeStatusFilter(value: string) {
  if (value === '0' || value === '1') {
    return Number(value) as DictStatus
  }

  return undefined
}

function getStatusBadge(status: DictStatus) {
  return status === 1
    ? {
        label: '正常',
        className:
          'border-emerald-300 bg-emerald-100 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950 dark:text-emerald-300',
      }
    : {
        label: '停用',
        className:
          'border-slate-300 bg-slate-100 text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300',
      }
}

function getDefaultBadge(isDefault: DictData['isDefault']) {
  return isDefault === 'Y'
    ? {
        label: '默认',
        className:
          'border-amber-300 bg-amber-100 text-amber-700 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-300',
      }
    : {
        label: '普通',
        className:
          'border-slate-300 bg-slate-100 text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300',
      }
}

export function DictManagementPage() {
  const queryClient = useQueryClient()
  const canAdd = useAccess({ permissions: ['system:dict:add'] })
  const canEdit = useAccess({ permissions: ['system:dict:edit'] })
  const canRemove = useAccess({ permissions: ['system:dict:remove'] })
  const canRefresh = useAccess({ permissions: ['system:dict:refreshCache'] })
  const canListData = useAccess({ permissions: ['system:dict:listData'] })

  const [typeKeyword, setTypeKeyword] = useState('')
  const [typeStatus, setTypeStatus] = useState('all')
  const [selectedTypeId, setSelectedTypeId] = useState<string | null>(null)
  const [dictTypeDialogOpen, setDictTypeDialogOpen] = useState(false)
  const [editingType, setEditingType] = useState<DictType | undefined>()
  const [deleteTypeTarget, setDeleteTypeTarget] = useState<DictType | null>(null)

  const [dataKeyword, setDataKeyword] = useState('')
  const [dataStatus, setDataStatus] = useState('all')
  const [dictDataDialogOpen, setDictDataDialogOpen] = useState(false)
  const [editingData, setEditingData] = useState<DictData | undefined>()
  const [deleteDataTarget, setDeleteDataTarget] = useState<DictData | null>(null)

  const typeQueryParams = useMemo(
    () => ({
      dictName: typeKeyword || undefined,
      status: normalizeStatusFilter(typeStatus),
    }),
    [typeKeyword, typeStatus]
  )

  const typePageQuery = useQuery({
    queryKey: ['system', 'dict', 'types', typeQueryParams],
    queryFn: () => fetchDictTypePage(typeQueryParams),
    placeholderData: keepPreviousData,
  })

  const dictTypes = typePageQuery.data?.records ?? []
  const resolvedSelectedTypeId =
    selectedTypeId && dictTypes.some((item) => item.id === selectedTypeId)
      ? selectedTypeId
      : dictTypes[0]?.id ?? null
  const selectedType =
    dictTypes.find((item) => item.id === resolvedSelectedTypeId) ?? null

  const dataQueryParams = useMemo(
    () =>
      selectedType
        ? {
            dictType: selectedType.dictType,
            dictLabel: dataKeyword || undefined,
            status: normalizeStatusFilter(dataStatus),
          }
        : null,
    [dataKeyword, dataStatus, selectedType]
  )

  const dictDataQuery = useQuery({
    queryKey: ['system', 'dict', 'data', dataQueryParams],
    queryFn: () => fetchDictDataList(dataQueryParams!),
    enabled: Boolean(dataQueryParams && canListData),
    placeholderData: keepPreviousData,
  })

  const dictData = dictDataQuery.data ?? []

  const createTypeMutation = useMutation({
    mutationFn: createDictType,
    onSuccess: async (nextId) => {
      toast.success('字典分组已创建。')
      setSelectedTypeId(nextId || null)
      await queryClient.invalidateQueries({ queryKey: ['system', 'dict', 'types'] })
    },
  })

  const updateTypeMutation = useMutation({
    mutationFn: updateDictType,
    onSuccess: async () => {
      toast.success('字典分组已更新。')
      await queryClient.invalidateQueries({ queryKey: ['system', 'dict', 'types'] })
      await queryClient.invalidateQueries({ queryKey: ['system', 'dict', 'data'] })
    },
  })

  const deleteTypeMutation = useMutation({
    mutationFn: (typeId: string) => deleteDictTypes([typeId]),
    onSuccess: async () => {
      toast.success('字典分组已删除。')
      setDeleteTypeTarget(null)
      await queryClient.invalidateQueries({ queryKey: ['system', 'dict', 'types'] })
      await queryClient.invalidateQueries({ queryKey: ['system', 'dict', 'data'] })
    },
    onError: (error) => {
      const message = (error as AxiosError<ApiResult<unknown>>)?.response?.data?.message
      toast.error(message || '删除字典分组失败，请重试。')
    },
  })

  const refreshCacheMutation = useMutation({
    mutationFn: refreshDictCache,
    onSuccess: () => {
      toast.success('字典缓存已刷新。')
    },
    onError: () => {
      toast.error('刷新字典缓存失败，请重试。')
    },
  })

  const createDataMutation = useMutation({
    mutationFn: createDictData,
    onSuccess: async () => {
      toast.success('字典项已创建。')
      await queryClient.invalidateQueries({ queryKey: ['system', 'dict', 'data'] })
    },
  })

  const updateDataMutation = useMutation({
    mutationFn: updateDictData,
    onSuccess: async () => {
      toast.success('字典项已更新。')
      await queryClient.invalidateQueries({ queryKey: ['system', 'dict', 'data'] })
    },
  })

  const deleteDataMutation = useMutation({
    mutationFn: (dataId: string) => deleteDictData([dataId]),
    onSuccess: async () => {
      toast.success('字典项已删除。')
      setDeleteDataTarget(null)
      await queryClient.invalidateQueries({ queryKey: ['system', 'dict', 'data'] })
    },
    onError: (error) => {
      const message = (error as AxiosError<ApiResult<unknown>>)?.response?.data?.message
      toast.error(message || '删除字典项失败，请重试。')
    },
  })

  function openCreateTypeDialog() {
    setEditingType(undefined)
    setDictTypeDialogOpen(true)
  }

  function openEditTypeDialog(type: DictType) {
    setEditingType(type)
    setDictTypeDialogOpen(true)
  }

  function openCreateDataDialog() {
    if (!selectedType) {
      return
    }
    setEditingData(undefined)
    setDictDataDialogOpen(true)
  }

  function openEditDataDialog(data: DictData) {
    setEditingData(data)
    setDictDataDialogOpen(true)
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
          <div>
            <h2 className='text-2xl font-bold tracking-tight'>字典管理</h2>
            <p className='text-sm text-muted-foreground'>
              左侧维护字典分组，右侧维护当前分组下的字典项。
            </p>
          </div>
          <div className='flex flex-wrap gap-2'>
            {canRefresh ? (
              <Button
                type='button'
                variant='outline'
                onClick={() => refreshCacheMutation.mutate()}
                disabled={refreshCacheMutation.isPending}
              >
                <RefreshCw
                  className={refreshCacheMutation.isPending ? 'animate-spin' : undefined}
                />
                刷新缓存
              </Button>
            ) : null}
          </div>
        </div>

        <div className='grid gap-4 xl:grid-cols-[380px_minmax(0,1fr)]'>
          <Card className='h-full overflow-hidden py-0'>
            <CardHeader className='border-b px-4 py-3'>
              <div className='space-y-3'>
                <div className='flex items-center justify-between gap-2'>
                  <CardTitle className='text-base'>字典分组</CardTitle>
                  {canAdd ? (
                    <Button type='button' size='sm' onClick={openCreateTypeDialog}>
                      <Plus />
                      添加分组
                    </Button>
                  ) : null}
                </div>
                <div className='grid grid-cols-[minmax(0,1fr)_112px] gap-2'>
                  <Input
                    value={typeKeyword}
                    onChange={(event) => setTypeKeyword(event.target.value)}
                    placeholder='搜索分组名称'
                  />
                  <SelectDropdown
                    isControlled
                    withFormControl={false}
                    value={typeStatus}
                    onValueChange={setTypeStatus}
                    items={statusOptions.map((option) => ({ ...option }))}
                  />
                </div>
              </div>
            </CardHeader>
            <CardContent className='p-0'>
              <div className='max-h-[calc(100vh-18rem)] overflow-auto'>
                {typePageQuery.isPending ? (
                  <div className='px-4 py-6 text-sm text-muted-foreground'>
                    字典分组加载中...
                  </div>
                ) : dictTypes.length === 0 ? (
                  <div className='px-4 py-8 text-center text-sm text-muted-foreground'>
                    当前没有可展示的字典分组。
                  </div>
                ) : (
                  <div className='divide-y'>
                    {dictTypes.map((item) => {
                      const statusMeta = getStatusBadge(item.status)
                      const isActive = item.id === resolvedSelectedTypeId

                      return (
                        <div
                          key={item.id}
                          role='button'
                          tabIndex={0}
                          className={`flex w-full items-start justify-between gap-3 px-4 py-3 text-left transition-colors ${
                            isActive
                              ? 'bg-primary/8'
                              : 'hover:bg-muted/40'
                          }`}
                          onClick={() => setSelectedTypeId(item.id)}
                          onKeyDown={(event) => {
                            if (event.key === 'Enter' || event.key === ' ') {
                              event.preventDefault()
                              setSelectedTypeId(item.id)
                            }
                          }}
                        >
                          <div className='min-w-0 space-y-1'>
                            <div className='flex items-center gap-2'>
                              <BookOpenText className='size-4 text-muted-foreground' />
                              <span className='truncate font-medium'>{item.dictName}</span>
                            </div>
                            <div className='flex min-w-0 items-center gap-2 text-xs text-muted-foreground'>
                              <span
                                className='max-w-[230px] truncate rounded-md bg-muted px-1.5 py-0.5 font-mono'
                                title={item.dictType}
                              >
                                {item.dictType}
                              </span>
                              <Badge
                                variant='outline'
                                className={`shrink-0 px-1.5 py-0 text-[10px] ${statusMeta.className}`}
                              >
                                {statusMeta.label}
                              </Badge>
                            </div>
                          </div>

                          {(canEdit || canRemove) && (
                            <div
                              className='flex shrink-0 self-center items-center gap-1'
                              onClick={(event) => event.stopPropagation()}
                            >
                              {canEdit ? (
                                <Button
                                  type='button'
                                  variant='ghost'
                                  size='sm'
                                  onClick={() => openEditTypeDialog(item)}
                                >
                                  编辑
                                </Button>
                              ) : null}
                              {canRemove ? (
                                <Button
                                  type='button'
                                  variant='ghost'
                                  size='sm'
                                  className='text-destructive hover:text-destructive'
                                  onClick={() => setDeleteTypeTarget(item)}
                                >
                                  删除
                                </Button>
                              ) : null}
                            </div>
                          )}
                        </div>
                      )
                    })}
                  </div>
                )}
              </div>
            </CardContent>
          </Card>

          <Card className='h-full overflow-hidden py-0'>
            <CardHeader className='flex min-h-[112px] items-center border-b px-6 py-3'>
              <div className='flex w-full flex-wrap items-center justify-between gap-3'>
                <div className='space-y-1'>
                  <CardTitle>
                    {selectedType ? `字典项：${selectedType.dictName}` : '字典项'}
                  </CardTitle>
                  <p className='text-sm text-muted-foreground'>
                    {selectedType
                      ? `分组编码：${selectedType.dictType}，创建时间：${formatDateTime(selectedType.createTime)}`
                      : '请选择左侧分组后维护字典项。'}
                  </p>
                </div>
                <div className='flex flex-wrap gap-2'>
                  {canAdd ? (
                    <Button
                      type='button'
                      onClick={openCreateDataDialog}
                      disabled={!selectedType}
                    >
                      <Plus />
                      添加字典项
                    </Button>
                  ) : null}
                </div>
              </div>
            </CardHeader>

            <CardContent className='space-y-3 px-6 pt-2 pb-5'>
              <div className='grid gap-2 md:grid-cols-[280px_140px] md:justify-start'>
                <Input
                  value={dataKeyword}
                  onChange={(event) => setDataKeyword(event.target.value)}
                  placeholder='按字典名称检索'
                  disabled={!selectedType}
                />
                <SelectDropdown
                  isControlled
                  withFormControl={false}
                  value={dataStatus}
                  onValueChange={setDataStatus}
                  items={statusOptions.map((option) => ({ ...option }))}
                  disabled={!selectedType}
                />
              </div>

              {!selectedType ? (
                <div className='rounded-xl border border-dashed px-6 py-10 text-center text-sm text-muted-foreground'>
                  左侧选择一个字典分组后，这里会显示对应的字典项列表。
                </div>
              ) : !canListData ? (
                <div className='rounded-xl border border-dashed px-6 py-10 text-center text-sm text-muted-foreground'>
                  当前账号没有查看字典项列表的权限。
                </div>
              ) : (
                <div className='overflow-hidden rounded-md border'>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className='w-28 text-center'>字典编码</TableHead>
                        <TableHead className='w-32 text-center'>字典名称</TableHead>
                        <TableHead className='w-16 text-center'>排序</TableHead>
                        <TableHead className='w-24 text-center'>默认项</TableHead>
                        <TableHead className='w-24 text-center'>状态</TableHead>
                        <TableHead className='text-center'>备注</TableHead>
                        <TableHead className='w-44 text-center'>创建时间</TableHead>
                        <TableHead className='w-28 text-center'>操作</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {dictDataQuery.isPending ? (
                        <TableRow>
                          <TableCell colSpan={8} className='h-24 text-center text-muted-foreground'>
                            字典项加载中...
                          </TableCell>
                        </TableRow>
                      ) : dictData.length === 0 ? (
                        <TableRow>
                          <TableCell colSpan={8} className='h-24 text-center text-muted-foreground'>
                            当前分组下暂无字典项。
                          </TableCell>
                        </TableRow>
                      ) : (
                        dictData.map((item) => {
                          const statusMeta = getStatusBadge(item.status)
                          const defaultMeta = getDefaultBadge(item.isDefault)
                          return (
                            <TableRow key={item.id}>
                              <TableCell className='text-center font-mono text-xs'>
                                {item.dictValue}
                              </TableCell>
                              <TableCell className='text-center'>{item.dictLabel}</TableCell>
                              <TableCell className='text-center'>{item.dictSort}</TableCell>
                              <TableCell>
                                <Badge
                                  variant='outline'
                                  className={`px-1.5 py-0 text-[10px] ${defaultMeta.className}`}
                                >
                                  {defaultMeta.label}
                                </Badge>
                              </TableCell>
                              <TableCell>
                                <Badge
                                  variant='outline'
                                  className={`px-1.5 py-0 text-[10px] ${statusMeta.className}`}
                                >
                                  {statusMeta.label}
                                </Badge>
                              </TableCell>
                              <TableCell>
                                <span className='line-clamp-2 text-sm text-muted-foreground'>
                                  {item.remark || '未填写'}
                                </span>
                              </TableCell>
                              <TableCell className='text-sm'>
                                {formatDateTime(item.createTime)}
                              </TableCell>
                              <TableCell className='text-left'>
                                <div className='flex justify-start gap-1'>
                                  {canEdit ? (
                                    <Button
                                      type='button'
                                      size='sm'
                                      variant='ghost'
                                      onClick={() => openEditDataDialog(item)}
                                    >
                                      编辑
                                    </Button>
                                  ) : null}
                                  {canRemove ? (
                                    <Button
                                      type='button'
                                      size='sm'
                                      variant='ghost'
                                      className='text-destructive hover:text-destructive'
                                      onClick={() => setDeleteDataTarget(item)}
                                    >
                                      删除
                                    </Button>
                                  ) : null}
                                </div>
                              </TableCell>
                            </TableRow>
                          )
                        })
                      )}
                    </TableBody>
                  </Table>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </Main>

      <DictTypeDialog
        open={dictTypeDialogOpen}
        onOpenChange={setDictTypeDialogOpen}
        initialData={editingType}
        isSaving={createTypeMutation.isPending || updateTypeMutation.isPending}
        onSubmit={async (values) => {
          if (editingType) {
            await updateTypeMutation.mutateAsync(values)
            return
          }

          await createTypeMutation.mutateAsync(values)
        }}
      />

      <DictDataDialog
        open={dictDataDialogOpen}
        onOpenChange={setDictDataDialogOpen}
        dictType={selectedType?.dictType ?? ''}
        initialData={editingData}
        isSaving={createDataMutation.isPending || updateDataMutation.isPending}
        onSubmit={async (values) => {
          if (editingData) {
            await updateDataMutation.mutateAsync(values)
            return
          }

          await createDataMutation.mutateAsync(values)
        }}
      />

      <ConfirmDialog
        open={Boolean(deleteTypeTarget)}
        onOpenChange={(nextOpen) => {
          if (!nextOpen) {
            setDeleteTypeTarget(null)
          }
        }}
        handleConfirm={() => {
          if (deleteTypeTarget) {
            deleteTypeMutation.mutate(deleteTypeTarget.id)
          }
        }}
        isLoading={deleteTypeMutation.isPending}
        destructive
        title='删除字典分组'
        confirmText='确认删除'
        desc={`删除“${deleteTypeTarget?.dictName ?? ''}”后不可恢复；该分组下的字典项会同步删除。`}
      />

      <ConfirmDialog
        open={Boolean(deleteDataTarget)}
        onOpenChange={(nextOpen) => {
          if (!nextOpen) {
            setDeleteDataTarget(null)
          }
        }}
        handleConfirm={() => {
          if (deleteDataTarget) {
            deleteDataMutation.mutate(deleteDataTarget.id)
          }
        }}
        isLoading={deleteDataMutation.isPending}
        destructive
        title='删除字典项'
        confirmText='确认删除'
        desc={`删除“${deleteDataTarget?.dictLabel ?? ''}”后不可恢复，请确认当前字典项未被业务引用。`}
      />
    </>
  )
}
