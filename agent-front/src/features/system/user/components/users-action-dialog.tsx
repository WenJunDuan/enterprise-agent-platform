'use client'

import { useEffect } from 'react'
import { useForm, useWatch } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { handleServerError } from '@/lib/handle-server-error'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { PasswordInput } from '@/components/password-input'
import { SelectDropdown } from '@/components/select-dropdown'
import {
  createUser,
  fetchAllRoles,
  fetchDeptTree,
  fetchUserDetail,
  fetchUserRoleIds,
  updateUser,
} from '../api'
import { userSexOptions } from '../data/data'
import { type User, type UserEditDetail } from '../data/schema'
import { flattenDeptOptions, type FlattenOption } from '../model'
import {
  buildUserActionDefaultValues,
  userActionFormSchema,
  type UserActionForm,
} from './users-action-dialog-form'
import { UsersRoleMultiSelect } from './users-role-multi-select'

type UserActionDialogProps = {
  currentRow?: User
  open: boolean
  onOpenChange: (open: boolean) => void
}

function RequiredFormLabel({ children }: { children: string }) {
  return (
    <FormLabel className='flex items-center gap-1'>
      <span className='text-destructive'>*</span>
      <span>{children}</span>
    </FormLabel>
  )
}

function buildDeptSelectOptions(
  options: FlattenOption[],
  detail?: UserEditDetail,
  selectedDeptId?: string
) {
  const normalizedDeptId = selectedDeptId?.trim()
  if (!normalizedDeptId) {
    return options
  }

  if (options.some((option) => option.value === normalizedDeptId)) {
    return options
  }

  if (
    detail?.deptId != null &&
    String(detail.deptId) === normalizedDeptId &&
    detail.deptName?.trim()
  ) {
    return [
      {
        label: detail.deptName.trim(),
        value: normalizedDeptId,
      },
      ...options,
    ]
  }

  return options
}

export function UsersActionDialog({
  currentRow,
  open,
  onOpenChange,
}: UserActionDialogProps) {
  const isEdit = Boolean(currentRow)
  const queryClient = useQueryClient()
  const form = useForm<UserActionForm>({
    resolver: zodResolver(userActionFormSchema),
    defaultValues: buildUserActionDefaultValues(currentRow),
  })
  const selectedDeptId = useWatch({
    control: form.control,
    name: 'deptId',
  })

  const detailQuery = useQuery({
    queryKey: ['system', 'users', 'detail', currentRow?.id],
    queryFn: () => fetchUserDetail(currentRow!.id),
    enabled: open && isEdit && Boolean(currentRow?.id),
    staleTime: 0,
  })

  const roleIdsQuery = useQuery({
    queryKey: ['system', 'users', 'roles', currentRow?.id],
    queryFn: () => fetchUserRoleIds(currentRow!.id),
    enabled: open && isEdit && Boolean(currentRow?.id),
    staleTime: 0,
  })

  const rolesQuery = useQuery({
    queryKey: ['system', 'roles', 'all'],
    queryFn: fetchAllRoles,
    enabled: open,
  })

  const deptTreeQuery = useQuery({
    queryKey: ['system', 'dept', 'treeselect'],
    queryFn: fetchDeptTree,
    enabled: open,
  })

  const createMutation = useMutation({
    mutationFn: createUser,
    onSuccess: async () => {
      toast.success('用户创建成功。')
      form.reset(buildUserActionDefaultValues())
      onOpenChange(false)
      await queryClient.invalidateQueries({
        queryKey: ['system', 'users', 'list'],
      })
    },
    onError: handleServerError,
  })

  const updateMutation = useMutation({
    mutationFn: updateUser,
    onSuccess: async () => {
      toast.success(`用户“${currentRow?.username}”已更新。`)
      onOpenChange(false)
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: ['system', 'users', 'list'],
        }),
        queryClient.invalidateQueries({
          queryKey: ['system', 'users', 'detail', currentRow?.id],
        }),
        queryClient.invalidateQueries({
          queryKey: ['system', 'users', 'roles', currentRow?.id],
        }),
      ])
    },
    onError: handleServerError,
  })

  useEffect(() => {
    if (!open) {
      form.reset(buildUserActionDefaultValues(currentRow))
      return
    }

    if (isEdit && (detailQuery.isFetching || roleIdsQuery.isFetching)) {
      return
    }

    form.reset(
      buildUserActionDefaultValues(
        currentRow,
        detailQuery.data,
        roleIdsQuery.data ?? []
      )
    )
  }, [
    open,
    isEdit,
    currentRow,
    detailQuery.data,
    detailQuery.isFetching,
    deptTreeQuery.data,
    roleIdsQuery.data,
    roleIdsQuery.isFetching,
    form,
  ])

  const roleOptions =
    rolesQuery.data?.map((role) => ({
      label: role.status === 1 ? role.roleName : `${role.roleName}（已停用）`,
      value: String(role.id),
    })) ?? []

  const deptOptions = buildDeptSelectOptions(
    flattenDeptOptions(deptTreeQuery.data ?? []),
    detailQuery.data,
    selectedDeptId
  )
  const hasDependencyError = rolesQuery.isError || deptTreeQuery.isError
  const isDependencyLoading = rolesQuery.isFetching || deptTreeQuery.isFetching
  const isEditDataReady =
    !isEdit || (Boolean(detailQuery.data) && roleIdsQuery.data !== undefined)
  const isEditDataLoading =
    isEdit &&
    (!isEditDataReady || detailQuery.isFetching || roleIdsQuery.isFetching)
  const hasEditDataError =
    isEdit && (detailQuery.isError || roleIdsQuery.isError)
  const hasFormDataError = hasEditDataError || hasDependencyError
  const formErrorMessage = hasEditDataError
    ? '用户详情或角色分配加载失败，请关闭弹窗后重试。'
    : '角色或部门数据加载失败，请关闭弹窗后重试。'
  const isSaving = createMutation.isPending || updateMutation.isPending

  return (
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => {
        form.reset(buildUserActionDefaultValues(currentRow))
        onOpenChange(nextOpen)
      }}
    >
      <DialogContent className='sm:max-w-2xl'>
        <DialogHeader className='text-start'>
          <DialogTitle>{isEdit ? '编辑用户' : '新建用户'}</DialogTitle>
          <DialogDescription>
            {isEdit
              ? '更新用户的基础资料、所属部门、角色和账号状态。'
              : '创建新的系统用户，并为其分配所属部门和角色。'}
          </DialogDescription>
        </DialogHeader>

        <div className='max-h-[70vh] overflow-y-auto py-1 pe-2'>
          {hasFormDataError ? (
            <div className='rounded-md border border-destructive/30 bg-destructive/5 px-4 py-6 text-sm text-destructive'>
              {formErrorMessage}
            </div>
          ) : isEdit && !isEditDataReady ? (
            <div className='rounded-md border border-dashed px-4 py-10 text-center text-sm text-muted-foreground'>
              用户详情加载中...
            </div>
          ) : (
            <Form {...form}>
              <form
                id='user-form'
                onSubmit={form.handleSubmit(
                  (values) => {
                    if (isEdit) {
                      if (values.id === null || values.version === null) {
                        toast.error('用户版本信息缺失，请关闭弹窗后重试。')
                        return
                      }

                      updateMutation.mutate({
                        ...values,
                        id: values.id,
                        version: values.version,
                      })
                      return
                    }

                    createMutation.mutate(values)
                  },
                  () => {
                    if (typeof document === 'undefined') {
                      return
                    }

                    const firstInvalidField =
                      document.querySelector<HTMLElement>(
                        '#user-form [aria-invalid="true"]'
                      )

                    firstInvalidField?.scrollIntoView({
                      block: 'center',
                      behavior: 'smooth',
                    })
                    firstInvalidField?.focus()
                  }
                )}
                className='space-y-4 px-0.5'
              >
                <div className='grid gap-4 md:grid-cols-2'>
                  <FormField
                    control={form.control}
                    name='username'
                    render={({ field }) => (
                      <FormItem>
                        <RequiredFormLabel>用户名</RequiredFormLabel>
                        <FormControl>
                          <Input
                            placeholder='请输入用户名'
                            autoComplete='off'
                            disabled={isEdit}
                            {...field}
                          />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name='nickname'
                    render={({ field }) => (
                      <FormItem>
                        <RequiredFormLabel>昵称</RequiredFormLabel>
                        <FormControl>
                          <Input placeholder='请输入昵称' {...field} />
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
                        <RequiredFormLabel>手机号</RequiredFormLabel>
                        <FormControl>
                          <Input placeholder='13800000000' {...field} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name='email'
                    render={({ field }) => (
                      <FormItem>
                        <RequiredFormLabel>邮箱</RequiredFormLabel>
                        <FormControl>
                          <Input placeholder='请输入邮箱地址' {...field} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name='sex'
                    render={({ field }) => (
                      <FormItem>
                        <RequiredFormLabel>性别</RequiredFormLabel>
                        <SelectDropdown
                          value={field.value}
                          onValueChange={field.onChange}
                          placeholder='请选择性别'
                          items={userSexOptions.map(({ label, value }) => ({
                            label,
                            value,
                          }))}
                          className='w-full'
                          isControlled
                        />
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name='status'
                    render={({ field }) => (
                      <FormItem>
                        <RequiredFormLabel>账号状态</RequiredFormLabel>
                        <SelectDropdown
                          value={field.value}
                          onValueChange={field.onChange}
                          placeholder='请选择账号状态'
                          items={[
                            { label: '启用', value: '1' },
                            { label: '停用', value: '0' },
                          ]}
                          className='w-full'
                          isControlled
                        />
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </div>

                <FormField
                  control={form.control}
                  name='deptId'
                  render={({ field }) => (
                    <FormItem>
                      <RequiredFormLabel>所属部门</RequiredFormLabel>
                      <SelectDropdown
                        value={field.value}
                        onValueChange={field.onChange}
                        placeholder='请选择所属部门'
                        isPending={deptTreeQuery.isPending}
                        items={deptOptions}
                        className='w-full'
                        isControlled
                      />
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name='roleIds'
                  render={({ field }) => (
                    <FormItem>
                      <RequiredFormLabel>角色</RequiredFormLabel>
                      <FormControl>
                        <UsersRoleMultiSelect
                          value={field.value}
                          onChange={field.onChange}
                          options={roleOptions}
                          isPending={
                            rolesQuery.isPending ||
                            (isEdit && roleIdsQuery.isFetching)
                          }
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name='remark'
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>备注</FormLabel>
                      <FormControl>
                        <Textarea
                          placeholder='请输入备注信息'
                          className='min-h-24 resize-none'
                          {...field}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                {!isEdit && (
                  <div className='grid gap-4 md:grid-cols-2'>
                    <FormField
                      control={form.control}
                      name='password'
                      render={({ field }) => (
                        <FormItem>
                          <RequiredFormLabel>初始密码</RequiredFormLabel>
                          <FormControl>
                            <PasswordInput
                              placeholder='请输入初始密码'
                              {...field}
                            />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    <FormField
                      control={form.control}
                      name='confirmPassword'
                      render={({ field }) => (
                        <FormItem>
                          <RequiredFormLabel>确认密码</RequiredFormLabel>
                          <FormControl>
                            <PasswordInput
                              placeholder='请再次输入初始密码'
                              {...field}
                            />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  </div>
                )}
              </form>
            </Form>
          )}
        </div>

        <DialogFooter>
          <Button
            type='submit'
            form='user-form'
            disabled={
              isSaving ||
              isEditDataLoading ||
              isDependencyLoading ||
              hasFormDataError
            }
          >
            保存
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
