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
import { ConfirmDialog } from '@/components/confirm-dialog'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { Search } from '@/components/search'
import { SelectDropdown } from '@/components/select-dropdown'
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
import {
  createMenu,
  deleteMenu,
  fetchMenuDetail,
  fetchMenuTree,
  updateMenu,
} from './api'
import {
  extractMenuServerErrors,
  menuFormSchema,
  type MenuForm,
  type MenuFormValues,
} from './form'
import { MenuIconPicker } from './components/menu-icon-picker'
import { MenuParentPicker } from './components/menu-parent-picker'
import { MenuTreePanel } from './components/menu-tree-panel'
import {
  buildMenuFormDefaults,
  collectMenuBranchIds,
  createDefaultExpandedMenuIds,
  ensureMenuPathExpanded,
  findFirstMenuId,
  findMenuById,
  findNextMenuOrderNum,
  type MenuFormInput,
  type MenuType,
  type MenuTypeFilter,
} from './model'

function RequiredFormLabel({ children }: { children: string }) {
  return (
    <FormLabel className='flex items-center gap-1'>
      <span className='text-destructive'>*</span>
      <span>{children}</span>
    </FormLabel>
  )
}

export function MenuManagementPage() {
  const queryClient = useQueryClient()
  const [selectedMenuId, setSelectedMenuId] = useState<string | null>(null)
  const [expandedMenuIds, setExpandedMenuIds] = useState<Set<string>>(new Set())
  const [collapsedMenuIds, setCollapsedMenuIds] = useState<Set<string>>(new Set())
  const [treeKeyword, setTreeKeyword] = useState('')
  const [menuTypeFilter, setMenuTypeFilter] = useState<MenuTypeFilter>('all')
  const [isCreating, setIsCreating] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [draftParentMenuId, setDraftParentMenuId] = useState('0')
  const [submitError, setSubmitError] = useState<string | null>(null)

  const form = useForm<MenuFormValues, undefined, MenuForm>({
    resolver: zodResolver(menuFormSchema),
    defaultValues: buildMenuFormDefaults(),
  })

  const parentIdValue = useWatch({
    control: form.control,
    name: 'parentId',
  })

  const menuTypeValue = useWatch({
    control: form.control,
    name: 'menuType',
  })

  const menuTreeQuery = useQuery({
    queryKey: ['system', 'menu', 'list'],
    queryFn: () => fetchMenuTree(),
  })

  const menuTree = menuTreeQuery.data ?? []
  const resolvedSelectedMenuId =
    selectedMenuId !== null && findMenuById(menuTree, selectedMenuId)
      ? selectedMenuId
      : findFirstMenuId(menuTree)

  const menuDetailQuery = useQuery({
    queryKey: ['system', 'menu', 'detail', resolvedSelectedMenuId],
    queryFn: () => fetchMenuDetail(resolvedSelectedMenuId!),
    enabled: resolvedSelectedMenuId !== null && !isCreating,
  })

  const selectedMenu =
    resolvedSelectedMenuId === null
      ? undefined
      : findMenuById(menuTree, resolvedSelectedMenuId)

  useEffect(() => {
    if (menuTree.length > 0 || isCreating) {
      return
    }

    form.reset(buildMenuFormDefaults())
  }, [form, isCreating, menuTree.length])

  useEffect(() => {
    if (isCreating || !menuDetailQuery.data) {
      return
    }

    form.reset(buildMenuFormDefaults(menuDetailQuery.data, selectedMenu?.parentId))
  }, [form, isCreating, menuDetailQuery.data, selectedMenu?.parentId])

  const createMutation = useMutation({
    mutationFn: (values: MenuFormInput) => createMenu(values),
    onSuccess: async (menuId) => {
      setSubmitError(null)
      toast.success('菜单创建成功。')
      setIsCreating(false)
      setSelectedMenuId(menuId || null)
      await queryClient.invalidateQueries({
        queryKey: ['system', 'menu'],
      })
    },
  })

  const updateMutation = useMutation({
    mutationFn: (values: MenuFormInput) =>
      updateMenu(values, resolvedSelectedMenuId!),
    onSuccess: async () => {
      setSubmitError(null)
      toast.success('菜单信息已更新。')
      await queryClient.invalidateQueries({
        queryKey: ['system', 'menu'],
      })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: () => deleteMenu(resolvedSelectedMenuId!),
    onSuccess: async () => {
      const parentId =
        resolvedSelectedMenuId === null
          ? null
          : (findMenuById(menuTree, resolvedSelectedMenuId)?.parentId ?? null)

      setDeleteOpen(false)
      setIsCreating(false)
      setSubmitError(null)
      setSelectedMenuId(parentId && parentId !== '0' ? parentId : null)
      toast.success('菜单已删除。')
      await queryClient.invalidateQueries({
        queryKey: ['system', 'menu'],
      })
    },
    onError: (error) => {
      if (error instanceof AxiosError) {
        const message = (error.response?.data as ApiResult<unknown> | undefined)
          ?.message

        toast.error(message || '菜单删除失败，请重试。')
        return
      }

      toast.error('菜单删除失败，请重试。')
    },
  })

  const isSaving = createMutation.isPending || updateMutation.isPending
  const excludedIds =
    !isCreating && resolvedSelectedMenuId !== null
      ? collectMenuBranchIds(menuTree, resolvedSelectedMenuId)
      : new Set<string>()
  const selectedBranchIds =
    resolvedSelectedMenuId !== null
      ? collectMenuBranchIds(menuTree, resolvedSelectedMenuId)
      : new Set<string>()
  const descendantCount = Math.max(selectedBranchIds.size - 1, 0)

  const selectedParentMenuId = selectedMenu?.menuId ?? resolvedSelectedMenuId ?? '0'
  const createParentId =
    parentIdValue || draftParentMenuId || resolvedSelectedMenuId || '0'
  const defaultExpandedMenuIds = createDefaultExpandedMenuIds(menuTree)
  const effectiveExpandedMenuIds = ensureMenuPathExpanded(
    new Set([
      ...[...defaultExpandedMenuIds].filter(
        (menuId) => !collapsedMenuIds.has(menuId)
      ),
      ...expandedMenuIds,
    ]),
    menuTree,
    resolvedSelectedMenuId
  )

  async function handleSaveError(error: unknown) {
    if (error instanceof AxiosError) {
      const responseData = error.response?.data as ApiResult<unknown> | undefined
      const serverMessage = responseData?.message
      const { fieldErrors, generalErrors } = extractMenuServerErrors(serverMessage)

      let hasFieldError = false

      for (const [field, message] of Object.entries(fieldErrors)) {
        if (!message) {
          continue
        }

        form.setError(field as keyof MenuFormValues, {
          type: 'server',
          message,
        })
        hasFieldError = true
      }

      if (generalErrors.some((message) => message.includes('菜单信息已变更'))) {
        toast.error('菜单信息已变更，请刷新后重试。')
        await queryClient.invalidateQueries({
          queryKey: ['system', 'menu'],
        })
        setSubmitError('菜单信息已变更，请刷新后重试。')
        return
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

  function handleSelectMenu(menuId: string) {
    setSubmitError(null)
    form.clearErrors()
    setIsCreating(false)
    setSelectedMenuId(menuId)
  }

  function handleToggleExpand(menuId: string, isOpen: boolean) {
    setExpandedMenuIds((prev) => {
      const next = new Set(prev)

      if (isOpen) {
        next.add(menuId)
      } else {
        next.delete(menuId)
      }

      return next
    })

    setCollapsedMenuIds((prev) => {
      const next = new Set(prev)

      if (isOpen) {
        next.delete(menuId)
      } else if (defaultExpandedMenuIds.has(menuId)) {
        next.add(menuId)
      } else {
        next.delete(menuId)
      }

      return next
    })
  }

  function handleDeleteMenuFromTree(menuId: string) {
    setSubmitError(null)
    setIsCreating(false)
    setSelectedMenuId(menuId)
    setDeleteOpen(true)
  }

  function handleCreateMenu() {
    const parentMenuId = selectedParentMenuId

    setSubmitError(null)
    form.clearErrors()
    setDraftParentMenuId(parentMenuId)
    form.reset(buildMenuFormDefaults(undefined, parentMenuId))
    form.setValue('parentId', parentMenuId, {
      shouldDirty: false,
      shouldTouch: false,
    })
    form.setValue('orderNum', String(findNextMenuOrderNum(menuTree, parentMenuId)), {
      shouldDirty: false,
      shouldTouch: false,
    })
    setIsCreating(true)
  }

  function handleCancelCreate() {
    setSubmitError(null)
    form.clearErrors()
    setDraftParentMenuId(selectedMenu?.parentId ?? '0')
    setIsCreating(false)

    if (menuDetailQuery.data) {
      form.reset(buildMenuFormDefaults(menuDetailQuery.data, selectedMenu?.parentId))
      return
    }

    form.reset(buildMenuFormDefaults())
  }

  function handleMenuTypeChange(nextMenuType: MenuType) {
    form.clearErrors([
      'path',
      'component',
      'queryParam',
      'isFrame',
      'isCache',
      'visible',
      'perms',
      'icon',
    ])

    form.setValue('menuType', nextMenuType, {
      shouldDirty: true,
      shouldTouch: true,
      shouldValidate: true,
    })

    if (nextMenuType === 'M') {
      form.resetField('component', { defaultValue: '' })
      form.resetField('queryParam', { defaultValue: '' })
      form.resetField('isFrame', { defaultValue: '1' })
      form.resetField('isCache', { defaultValue: '0' })
      form.resetField('perms', { defaultValue: '' })
      return
    }

    if (nextMenuType === 'F') {
      form.resetField('path', { defaultValue: '' })
      form.resetField('component', { defaultValue: '' })
      form.resetField('queryParam', { defaultValue: '' })
      form.resetField('isFrame', { defaultValue: '1' })
      form.resetField('isCache', { defaultValue: '0' })
      form.resetField('visible', { defaultValue: '1' })
      form.resetField('icon', { defaultValue: '' })
    }
  }

  async function handleSubmit(values: MenuForm) {
    form.clearErrors()
    setSubmitError(null)

    const payload: MenuFormInput = {
      parentId: values.parentId || draftParentMenuId || '0',
      menuName: values.menuName,
      orderNum: values.orderNum,
      path: values.path,
      component: values.component,
      queryParam: values.queryParam,
      isFrame: values.isFrame,
      isCache: values.isCache,
      menuType: values.menuType,
      visible: values.visible,
      perms: values.perms,
      icon: values.icon,
      status: values.status,
      remark: values.remark,
    }

    try {
      if (isCreating) {
        await createMutation.mutateAsync(payload)
        return
      }

      if (resolvedSelectedMenuId !== null) {
        await updateMutation.mutateAsync(payload)
      }
    } catch (error) {
      await handleSaveError(error)
    }
  }

  const showDirectoryFields = menuTypeValue === 'M'
  const showMenuFields = menuTypeValue === 'C'
  const showButtonFields = menuTypeValue === 'F'

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
          <h2 className='text-2xl font-bold tracking-tight'>菜单管理</h2>
        </div>

        <div className='grid gap-4 xl:grid-cols-[360px_minmax(0,1fr)]'>
          <MenuTreePanel
            tree={menuTree}
            isPending={menuTreeQuery.isPending}
            selectedMenuId={resolvedSelectedMenuId}
            expandedMenuIds={effectiveExpandedMenuIds}
            keyword={treeKeyword}
            typeFilter={menuTypeFilter}
            onKeywordChange={setTreeKeyword}
            onTypeFilterChange={setMenuTypeFilter}
            onSelectMenu={handleSelectMenu}
            onDeleteMenu={handleDeleteMenuFromTree}
            onToggleExpand={handleToggleExpand}
          />

          <Card className='h-full py-0'>
            <CardHeader className='border-b py-3'>
              <div className='flex min-h-10 flex-wrap items-center justify-between gap-3'>
                <div>
                  <CardTitle>
                    {isCreating ? '创建菜单' : (selectedMenu?.menuName ?? '菜单信息维护')}
                  </CardTitle>
                </div>
                <div className='flex flex-wrap gap-2'>
                  <Button
                    type='button'
                    variant='outline'
                    onClick={handleCreateMenu}
                  >
                    <FolderPlus />
                    创建菜单
                  </Button>
                  <Button
                    type='button'
                    variant='destructive'
                    onClick={() => setDeleteOpen(true)}
                    disabled={resolvedSelectedMenuId === null || isCreating}
                  >
                    <Trash2 />
                    删除
                  </Button>
                </div>
              </div>
            </CardHeader>

            <CardContent className='flex flex-1 flex-col px-6 pt-2 pb-3'>
              {!isCreating && menuDetailQuery.isPending ? (
                <div className='space-y-4'>
                  <Skeleton className='h-24 w-full' />
                  <Skeleton className='h-56 w-full' />
                </div>
              ) : (
                <Form {...form}>
                  <form
                    id='menu-form'
                    onSubmit={form.handleSubmit(handleSubmit)}
                    className='flex flex-1 flex-col gap-4'
                  >
                    <div className='grid gap-5 md:grid-cols-2'>
                      <FormField
                        control={form.control}
                        name='parentId'
                        render={({ field }) => (
                          <FormItem>
                            <RequiredFormLabel>上级菜单</RequiredFormLabel>
                            <MenuParentPicker
                              value={field.value || createParentId}
                              onChange={field.onChange}
                              nodes={menuTree}
                              excludedIds={excludedIds}
                              disabled={isSaving}
                            />
                            <FormMessage />
                          </FormItem>
                        )}
                      />

                      <FormField
                        control={form.control}
                        name='menuType'
                        render={({ field }) => (
                          <FormItem>
                            <RequiredFormLabel>菜单类型</RequiredFormLabel>
                            <SelectDropdown
                              isControlled
                              value={field.value}
                              onValueChange={(value) =>
                                handleMenuTypeChange(value as MenuType)
                              }
                              items={[
                                { label: '目录', value: 'M' },
                                { label: '菜单', value: 'C' },
                                { label: '按钮', value: 'F' },
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
                        name='menuName'
                        render={({ field }) => (
                          <FormItem>
                            <RequiredFormLabel>菜单名称</RequiredFormLabel>
                            <FormControl>
                              <Input
                                placeholder='例如：菜单管理'
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

                      {(showDirectoryFields || showMenuFields) && (
                        <FormField
                          control={form.control}
                          name='icon'
                          render={({ field }) => (
                            <FormItem>
                              <FormLabel>图标</FormLabel>
                              <MenuIconPicker
                                value={field.value}
                                onChange={field.onChange}
                                disabled={isSaving}
                              />
                              <FormMessage />
                            </FormItem>
                          )}
                        />
                      )}

                      {(showDirectoryFields || showMenuFields) && (
                        <FormField
                          control={form.control}
                          name='path'
                          render={({ field }) => (
                            <FormItem>
                              <RequiredFormLabel>路由地址</RequiredFormLabel>
                              <FormControl>
                                <Input
                                  placeholder='例如：menu'
                                  disabled={isSaving}
                                  {...field}
                                />
                              </FormControl>
                              <FormMessage />
                            </FormItem>
                          )}
                        />
                      )}

                      {showMenuFields && (
                        <FormField
                          control={form.control}
                          name='component'
                          render={({ field }) => (
                            <FormItem>
                              <RequiredFormLabel>组件路径</RequiredFormLabel>
                              <FormControl>
                                <Input
                                  placeholder='例如：system/menu/index'
                                  disabled={isSaving}
                                  {...field}
                                />
                              </FormControl>
                              <FormMessage />
                            </FormItem>
                          )}
                        />
                      )}

                      {showMenuFields && (
                        <FormField
                          control={form.control}
                          name='queryParam'
                          render={({ field }) => (
                            <FormItem>
                              <FormLabel>路由参数</FormLabel>
                              <FormControl>
                                <Input
                                  placeholder='例如：id=1&mode=edit'
                                  disabled={isSaving}
                                  {...field}
                                />
                              </FormControl>
                              <FormMessage />
                            </FormItem>
                          )}
                        />
                      )}

                      {showMenuFields && (
                        <FormField
                          control={form.control}
                          name='isFrame'
                          render={({ field }) => (
                            <FormItem>
                              <RequiredFormLabel>是否外链</RequiredFormLabel>
                              <SelectDropdown
                                isControlled
                                value={field.value}
                                onValueChange={field.onChange}
                                items={[
                                  { label: '否（站内）', value: '1' },
                                  { label: '是（外链）', value: '0' },
                                ]}
                                disabled={isSaving}
                                className='w-full'
                              />
                              <FormMessage />
                            </FormItem>
                          )}
                        />
                      )}

                      {showMenuFields && (
                        <FormField
                          control={form.control}
                          name='isCache'
                          render={({ field }) => (
                            <FormItem>
                              <RequiredFormLabel>是否缓存</RequiredFormLabel>
                              <SelectDropdown
                                isControlled
                                value={field.value}
                                onValueChange={field.onChange}
                                items={[
                                  { label: '否', value: '0' },
                                  { label: '是', value: '1' },
                                ]}
                                disabled={isSaving}
                                className='w-full'
                              />
                              <FormMessage />
                            </FormItem>
                          )}
                        />
                      )}

                      {(showMenuFields || showButtonFields) && (
                        <FormField
                          control={form.control}
                          name='perms'
                          render={({ field }) => (
                            <FormItem>
                              <RequiredFormLabel>权限标识</RequiredFormLabel>
                              <FormControl>
                                <Input
                                  placeholder='例如：system:menu:list'
                                  disabled={isSaving}
                                  {...field}
                                />
                              </FormControl>
                              <FormMessage />
                            </FormItem>
                          )}
                        />
                      )}

                      {(showDirectoryFields || showMenuFields) && (
                        <FormField
                          control={form.control}
                          name='visible'
                          render={({ field }) => (
                            <FormItem>
                              <RequiredFormLabel>显示状态</RequiredFormLabel>
                              <SelectDropdown
                                isControlled
                                value={field.value}
                                onValueChange={field.onChange}
                                items={[
                                  { label: '显示', value: '1' },
                                  { label: '隐藏', value: '0' },
                                ]}
                                disabled={isSaving}
                                className='w-full'
                              />
                              <FormMessage />
                            </FormItem>
                          )}
                        />
                      )}

                      <FormField
                        control={form.control}
                        name='status'
                        render={({ field }) => (
                          <FormItem>
                            <RequiredFormLabel>菜单状态</RequiredFormLabel>
                            <SelectDropdown
                              isControlled
                              value={field.value}
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
                        <Button
                          type='submit'
                          disabled={
                            isSaving ||
                            (!isCreating && resolvedSelectedMenuId === null)
                          }
                        >
                          <Save />
                          {isCreating ? '创建菜单' : '保存修改'}
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
        title='删除菜单'
        confirmText='确认删除'
        desc={
          selectedMenu
            ? `删除“${selectedMenu.menuName}”后将${
                descendantCount > 0
                  ? `级联删除其下 ${descendantCount} 个子菜单/按钮，并`
                  : ''
              }同步清理相关角色授权；受影响用户的菜单与权限会在后续请求中自动刷新，此操作不可恢复。`
            : '确认执行菜单删除后，关联授权会一并清理且不可恢复。'
        }
      />
    </>
  )
}
