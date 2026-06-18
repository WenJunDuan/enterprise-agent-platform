'use client'

import { useEffect, useState } from 'react'
import { AxiosError } from 'axios'
import { useForm, useWatch } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { FolderPlus, Save, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import type { ApiResult } from '@/types/api'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { TreeView } from '@/components/ui/tree-view'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { Search } from '@/components/search'
import { SelectDropdown } from '@/components/select-dropdown'
import { DeptParentPicker } from './components/dept-parent-picker'
import {
  createDept,
  deleteDept,
  fetchDeptList,
  fetchDeptDetail,
  updateDept,
} from './api'
import {
  deptFormSchema,
  extractDeptServerErrors,
  type DeptForm,
  type DeptFormValues,
} from './form'
import {
  buildDeptFormDefaults,
  collectDeptBranchIds,
  buildDeptTreeViewItems,
  createDefaultExpandedDeptIds,
  ensureDeptPathExpanded,
  filterDeptTree,
  findDeptById,
  findFirstDeptId,
  type DeptFilterStatus,
  type DeptFormInput,
} from './model'

function RequiredFormLabel({ children }: { children: string }) {
  return (
    <FormLabel className='flex items-center gap-1'>
      <span className='text-destructive'>*</span>
      <span>{children}</span>
    </FormLabel>
  )
}

export function DepartmentManagementPage() {
  const queryClient = useQueryClient()
  const [selectedDeptId, setSelectedDeptId] = useState<string | null>(null)
  const [expandedDeptIds, setExpandedDeptIds] = useState<Set<string>>(
    new Set()
  )
  const [collapsedDeptIds, setCollapsedDeptIds] = useState<Set<string>>(
    new Set()
  )
  const [treeKeyword, setTreeKeyword] = useState('')
  const [statusFilter, setStatusFilter] = useState<DeptFilterStatus>('all')
  const [isCreating, setIsCreating] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [draftParentDeptId, setDraftParentDeptId] = useState('0')
  const [submitError, setSubmitError] = useState<string | null>(null)
  const form = useForm<DeptFormValues, undefined, DeptForm>({
    resolver: zodResolver(deptFormSchema),
    defaultValues: buildDeptFormDefaults(),
  })
  const parentIdValue = useWatch({
    control: form.control,
    name: 'parentId',
  })

  const deptTreeQuery = useQuery({
    queryKey: ['system', 'dept', 'list', statusFilter],
    queryFn: () => fetchDeptList({ status: statusFilter }),
  })
  const deptTreeData = deptTreeQuery.data
  const deptTree = deptTreeData ?? []
  const resolvedSelectedDeptId =
    selectedDeptId !== null && findDeptById(deptTree, selectedDeptId)
      ? selectedDeptId
      : findFirstDeptId(deptTree)

  const deptDetailQuery = useQuery({
    queryKey: ['system', 'dept', 'detail', resolvedSelectedDeptId],
    queryFn: () => fetchDeptDetail(resolvedSelectedDeptId!),
    enabled: resolvedSelectedDeptId !== null && !isCreating,
  })
  const selectedDept =
    resolvedSelectedDeptId === null
      ? undefined
      : findDeptById(deptTree, resolvedSelectedDeptId)

  useEffect(() => {
    if (deptTree.length > 0 || isCreating) {
      return
    }

    form.reset(buildDeptFormDefaults())
  }, [deptTree.length, form, isCreating])

  useEffect(() => {
    if (isCreating || !deptDetailQuery.data) {
      return
    }

    form.reset(buildDeptFormDefaults(deptDetailQuery.data, selectedDept?.parentId))
  }, [deptDetailQuery.data, form, isCreating, selectedDept?.parentId])

  const createMutation = useMutation({
    mutationFn: (values: DeptFormInput) => createDept(values),
    onSuccess: async (deptId) => {
      setSubmitError(null)
      toast.success('部门创建成功。')
      setIsCreating(false)
      setSelectedDeptId(deptId)
      await queryClient.invalidateQueries({
        queryKey: ['system', 'dept'],
      })
    },
  })

  const updateMutation = useMutation({
    mutationFn: (values: DeptFormInput) =>
      updateDept(values, resolvedSelectedDeptId!),
    onSuccess: async () => {
      setSubmitError(null)
      toast.success('部门信息已更新。')
      await queryClient.invalidateQueries({
        queryKey: ['system', 'dept'],
      })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: () => deleteDept(resolvedSelectedDeptId!),
    onSuccess: async () => {
      const parentId =
        resolvedSelectedDeptId === null
          ? null
          : (findDeptById(deptTree, resolvedSelectedDeptId)?.parentId ?? null)

      toast.success('部门已删除。')
      setDeleteOpen(false)
      setIsCreating(false)
      setSubmitError(null)
      setSelectedDeptId(parentId && parentId !== '0' ? parentId : null)
      await queryClient.invalidateQueries({
        queryKey: ['system', 'dept'],
      })
    },
  })

  const filteredTree = filterDeptTree(deptTree, treeKeyword)
  const treeViewItems = buildDeptTreeViewItems(filteredTree)
  const isSaving = createMutation.isPending || updateMutation.isPending
  const excludedIds =
    !isCreating && resolvedSelectedDeptId !== null
      ? collectDeptBranchIds(deptTree, resolvedSelectedDeptId)
      : new Set<string>()

  const selectedParentDeptId = selectedDept?.deptId ?? resolvedSelectedDeptId ?? '0'
  const createParentId =
    parentIdValue || draftParentDeptId || resolvedSelectedDeptId || '0'
  const defaultExpandedDeptIds = createDefaultExpandedDeptIds(deptTree)
  const effectiveExpandedDeptIds = ensureDeptPathExpanded(
    new Set([
      ...[...defaultExpandedDeptIds].filter(
        (deptId) => !collapsedDeptIds.has(deptId)
      ),
      ...expandedDeptIds,
    ]),
    deptTree,
    resolvedSelectedDeptId
  )

  function handleSaveError(error: unknown) {
    if (error instanceof AxiosError) {
      const responseData = error.response?.data as ApiResult<unknown> | undefined
      const { fieldErrors, generalErrors } = extractDeptServerErrors(
        responseData?.message
      )

      let hasFieldError = false

      for (const [field, message] of Object.entries(fieldErrors)) {
        if (!message) {
          continue
        }

        form.setError(field as keyof DeptFormValues, {
          type: 'server',
          message,
        })
        hasFieldError = true
      }

      if (generalErrors.length > 0) {
        setSubmitError(generalErrors[0])
        return
      }

      if (hasFieldError) {
        setSubmitError(null)
        return
      }
    }

    setSubmitError('保存失败，请重试。')
  }

  function handleSelectDept(deptId: string) {
    setSubmitError(null)
    form.clearErrors()
    setIsCreating(false)
    setSelectedDeptId(deptId)
  }

  function handleToggleExpand(deptId: string, isOpen: boolean) {
    setExpandedDeptIds((prev) => {
      const next = new Set(prev)

      if (isOpen) {
        next.add(deptId)
      } else {
        next.delete(deptId)
      }

      return next
    })

    setCollapsedDeptIds((prev) => {
      const next = new Set(prev)

      if (isOpen) {
        next.delete(deptId)
      } else if (defaultExpandedDeptIds.has(deptId)) {
        next.add(deptId)
      } else {
        next.delete(deptId)
      }

      return next
    })
  }

  function handleDeleteDeptFromTree(deptId: string) {
    setSubmitError(null)
    setIsCreating(false)
    setSelectedDeptId(deptId)
    setDeleteOpen(true)
  }

  function handleCreateDept() {
    const parentDeptId = selectedParentDeptId

    setSubmitError(null)
    form.clearErrors()
    setDraftParentDeptId(parentDeptId)
    form.reset(buildDeptFormDefaults(undefined, parentDeptId))
    form.setValue('parentId', parentDeptId, {
      shouldDirty: false,
      shouldTouch: false,
    })
    setIsCreating(true)
  }

  function handleCancelCreate() {
    setSubmitError(null)
    form.clearErrors()
    setDraftParentDeptId(selectedDept?.parentId ?? '0')
    setIsCreating(false)

    if (deptDetailQuery.data) {
      form.reset(buildDeptFormDefaults(deptDetailQuery.data, selectedDept?.parentId))
      return
    }

    form.reset(buildDeptFormDefaults())
  }

  async function handleSubmit(values: DeptForm) {
    form.clearErrors()
    setSubmitError(null)

    const payload: DeptFormInput = {
      parentId: values.parentId || draftParentDeptId || '0',
      deptName: values.deptName,
      orderNum: values.orderNum,
      leader: values.leader,
      phone: values.phone,
      email: values.email,
      status: values.status,
    }

    try {
      if (isCreating) {
        await createMutation.mutateAsync(payload)
        return
      }

      if (resolvedSelectedDeptId !== null) {
        await updateMutation.mutateAsync(payload)
      }
    } catch (error) {
      handleSaveError(error)
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

      <Main className='flex flex-1 flex-col gap-3 sm:gap-4'>
        <div>
          <h2 className='text-2xl font-bold tracking-tight'>部门管理</h2>
        </div>

        <div className='grid gap-4 xl:grid-cols-[360px_minmax(0,1fr)]'>
          <Card className='h-full overflow-hidden py-0'>
            <CardHeader className='border-b px-4 py-3'>
              <div className='grid min-h-10 grid-cols-[minmax(0,1fr)_100px] items-center gap-3'>
                <Input
                  value={treeKeyword}
                  onChange={(event) => setTreeKeyword(event.target.value)}
                  placeholder='搜索部门名称'
                />
                <SelectDropdown
                  isControlled
                  defaultValue={statusFilter}
                  onValueChange={(value) =>
                    setStatusFilter(value as DeptFilterStatus)
                  }
                  withFormControl={false}
                  items={[
                    { label: '全部状态', value: 'all' },
                    { label: '仅正常', value: 'active' },
                    { label: '仅禁用', value: 'inactive' },
                  ]}
                />
              </div>
            </CardHeader>
            <CardContent className='space-y-2 px-3 pt-1 pb-2'>
              <div className='no-scrollbar h-[calc(100vh-21rem)] min-h-[24rem] overflow-auto p-1'>
                {deptTreeQuery.isPending ? (
                  <div className='space-y-3'>
                    <Skeleton className='h-16 w-full' />
                    <Skeleton className='h-16 w-[92%]' />
                    <Skeleton className='h-16 w-[84%]' />
                  </div>
                ) : filteredTree.length > 0 ? (
                  <TreeView
                    data={treeViewItems}
                    selectedId={resolvedSelectedDeptId}
                    expandedIds={effectiveExpandedDeptIds}
                    indentation={20}
                    toggleOnSelect
                    onSelect={(item) => handleSelectDept(item.id)}
                    onToggleExpand={handleToggleExpand}
                    renderTrailing={(item) => {
                      const node =
                        findDeptById(filteredTree, item.id) ??
                        findDeptById(deptTree, item.id)
                      const hasChildren = (node?.children?.length ?? 0) > 0

                      if (hasChildren) {
                        return (
                          <span className='shrink-0 text-[11px] leading-5 text-muted-foreground'>
                            {node?.children.length} 个下级
                          </span>
                        )
                      }

                      return (
                        <Button
                          type='button'
                          size='icon'
                          variant='ghost'
                          className='size-6 text-muted-foreground hover:text-destructive'
                          onClick={(event) => {
                            event.stopPropagation()
                            handleDeleteDeptFromTree(item.id)
                          }}
                        >
                          <Trash2 />
                        </Button>
                      )
                    }}
                  />
                ) : (
                  <div className='flex h-40 items-center justify-center text-sm text-muted-foreground'>
                    未匹配到部门数据。
                  </div>
                )}
              </div>
            </CardContent>
          </Card>

          <Card className='h-full py-0'>
            <CardHeader className='border-b py-3'>
              <div className='flex min-h-10 flex-wrap items-center justify-between gap-3'>
                <div>
                  <CardTitle>
                    {isCreating
                      ? '创建部门'
                      : (selectedDept?.deptName ?? '部门信息维护')}
                  </CardTitle>
                </div>
                <div className='flex flex-wrap gap-2'>
                  <Button
                    type='button'
                    variant='outline'
                    onClick={handleCreateDept}
                  >
                    <FolderPlus />
                    创建部门
                  </Button>
                  <Button
                    type='button'
                    variant='destructive'
                    onClick={() => setDeleteOpen(true)}
                    disabled={resolvedSelectedDeptId === null || isCreating}
                  >
                    <Trash2 />
                    删除
                  </Button>
                </div>
              </div>
            </CardHeader>

            <CardContent className='flex flex-1 flex-col px-6 pt-2 pb-3'>
              {!isCreating && deptDetailQuery.isPending ? (
                <div className='space-y-4'>
                  <Skeleton className='h-24 w-full' />
                  <Skeleton className='h-56 w-full' />
                </div>
              ) : (
                <>

                  <Form {...form}>
                    <form
                      id='dept-form'
                      onSubmit={form.handleSubmit(handleSubmit)}
                      className='flex flex-1 flex-col gap-4'
                    >
                      <div className='grid gap-5 md:grid-cols-2'>
                        <FormField
                          control={form.control}
                          name='parentId'
                          render={({ field }) => (
                            <FormItem>
                              <RequiredFormLabel>上级部门</RequiredFormLabel>
                              <DeptParentPicker
                                value={field.value || createParentId}
                                onChange={field.onChange}
                                nodes={deptTree}
                                excludedIds={excludedIds}
                                disabled={isSaving}
                              />
                              <FormMessage />
                            </FormItem>
                          )}
                        />

                        <FormField
                          control={form.control}
                          name='deptName'
                          render={({ field }) => (
                            <FormItem>
                              <RequiredFormLabel>部门名称</RequiredFormLabel>
                              <FormControl>
                                <Input
                                  placeholder='例如：研发中心'
                                  disabled={isSaving}
                                  {...field}
                                />
                              </FormControl>
                              <FormMessage />
                            </FormItem>
                          )}
                        />

                        <FormField
                          control={form.control}
                          name='orderNum'
                          render={({ field }) => (
                            <FormItem>
                              <RequiredFormLabel>显示顺序</RequiredFormLabel>
                              <FormControl>
                                <Input
                                  inputMode='numeric'
                                  placeholder='0'
                                  disabled={isSaving}
                                  {...field}
                                />
                              </FormControl>
                              <FormMessage />
                            </FormItem>
                          )}
                        />

                        <FormField
                          control={form.control}
                          name='status'
                          render={({ field }) => (
                            <FormItem>
                              <RequiredFormLabel>部门状态</RequiredFormLabel>
                              <SelectDropdown
                                isControlled
                                defaultValue={field.value}
                                onValueChange={field.onChange}
                                items={[
                                  { label: '正常', value: '1' },
                                  { label: '禁用', value: '0' },
                                ]}
                                disabled={isSaving}
                                className='w-full'
                              />
                              <FormMessage />
                            </FormItem>
                          )}
                        />

                        <FormField
                          control={form.control}
                          name='leader'
                          render={({ field }) => (
                            <FormItem>
                              <RequiredFormLabel>部门负责人</RequiredFormLabel>
                              <FormControl>
                                <Input
                                  placeholder='请输入部门负责人'
                                  disabled={isSaving}
                                  {...field}
                                />
                              </FormControl>
                              <FormMessage />
                            </FormItem>
                          )}
                        />

                        <FormField
                          control={form.control}
                          name='phone'
                          render={({ field }) => (
                            <FormItem>
                              <RequiredFormLabel>联系电话</RequiredFormLabel>
                              <FormControl>
                                <Input
                                  placeholder='请输入 11 位手机号'
                                  disabled={isSaving}
                                  {...field}
                                />
                              </FormControl>
                              <FormMessage />
                            </FormItem>
                          )}
                        />

                        <FormField
                          control={form.control}
                          name='email'
                          render={({ field }) => (
                            <FormItem className='md:col-span-2'>
                              <FormLabel>邮箱</FormLabel>
                              <FormControl>
                                <Input
                                  placeholder='name@example.com'
                                  disabled={isSaving}
                                  {...field}
                                />
                              </FormControl>
                              <FormMessage />
                            </FormItem>
                          )}
                        />
                      </div>

                      <div className='mt-auto space-y-2 pt-4'>
                        <div className='flex flex-wrap justify-end gap-2'>
                          {isCreating ? (
                            <Button
                              type='button'
                              variant='outline'
                              onClick={handleCancelCreate}
                              disabled={isSaving}
                            >
                              取消创建
                            </Button>
                          ) : null}
                          <Button type='submit' disabled={isSaving}>
                            <Save />
                            {isCreating ? '创建部门' : '保存修改'}
                          </Button>
                        </div>
                        <p
                          className={cn(
                            'min-h-4 text-right text-xs text-destructive',
                            !submitError && 'select-none text-transparent'
                          )}
                        >
                          {submitError || '\u00A0'}
                        </p>
                      </div>
                    </form>
                  </Form>
                </>
              )}
            </CardContent>
          </Card>
        </div>
      </Main>

      <ConfirmDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        handleConfirm={() => deleteMutation.mutate()}
        isLoading={deleteMutation.isPending}
        destructive
        title='删除部门'
        confirmText='确认删除'
        desc={`删除“${selectedDept?.deptName ?? ''}”后不可恢复，请确认该部门下不存在被业务依赖的数据。`}
      />
    </>
  )
}
