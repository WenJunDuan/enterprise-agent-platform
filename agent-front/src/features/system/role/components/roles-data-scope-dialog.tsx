'use client'

import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { SelectDropdown } from '@/components/select-dropdown'
import { handleServerError } from '@/lib/handle-server-error'
import {
  fetchDeptTreeSelect,
  fetchRoleDeptIds,
  updateRoleDataScope,
} from '../api'
import {
  roleDataScopeOptions,
  type Role,
  type RoleDataScope,
} from '../model'
import { CheckableTree } from './roles-checkable-tree'

type RolesDataScopeDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  currentRow: Role
}

export function RolesDataScopeDialog({
  open,
  onOpenChange,
  currentRow,
}: RolesDataScopeDialogProps) {
  const queryClient = useQueryClient()
  const [dataScope, setDataScope] = useState<`${RoleDataScope}`>(
    String(currentRow.dataScope) as `${RoleDataScope}`
  )
  const [deptIds, setDeptIds] = useState<string[]>([])
  const [deptIdsDirty, setDeptIdsDirty] = useState(false)

  const isCustomScope = dataScope === '4'
  const isOriginallyCustomScope = currentRow.dataScope === 4

  const deptTreeQuery = useQuery({
    queryKey: ['system', 'dept', 'treeselect'],
    queryFn: fetchDeptTreeSelect,
    enabled: open && isCustomScope,
    staleTime: 60_000,
  })

  const roleDeptIdsQuery = useQuery({
    queryKey: ['system', 'role', 'depts', currentRow.id],
    queryFn: () => fetchRoleDeptIds(currentRow.id),
    enabled: open && isOriginallyCustomScope,
    staleTime: 0,
  })

  const selectedDeptIds =
    deptIdsDirty || !isOriginallyCustomScope
      ? deptIds
      : (roleDeptIdsQuery.data ?? [])

  const mutation = useMutation({
    mutationFn: updateRoleDataScope,
    onSuccess: async () => {
      toast.success(`角色“${currentRow.roleName}”的数据权限已更新。`)
      onOpenChange(false)
      await queryClient.invalidateQueries({
        queryKey: ['system', 'role', 'list'],
      })
    },
    onError: handleServerError,
  })

  const handleSubmit = () => {
    mutation.mutate({
      roleId: currentRow.id,
      dataScope: Number(dataScope) as RoleDataScope,
      deptIds: selectedDeptIds,
    })
  }

  const isDeptLoading =
    isCustomScope && (deptTreeQuery.isFetching || deptTreeQuery.isPending)
  const isRoleDeptsLoading =
    isCustomScope &&
    isOriginallyCustomScope &&
    !deptIdsDirty &&
    (roleDeptIdsQuery.isFetching || roleDeptIdsQuery.isPending)
  const hasDeptTreeError = isCustomScope && deptTreeQuery.isError
  const hasRoleDeptError = isCustomScope && isOriginallyCustomScope && roleDeptIdsQuery.isError

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-xl'>
        <DialogHeader className='text-start'>
          <DialogTitle>调整数据权限</DialogTitle>
          <DialogDescription>
            为角色 <span className='font-medium'>{currentRow.roleName}</span>{' '}
            配置数据访问范围。
          </DialogDescription>
        </DialogHeader>

        <div className='max-h-[60vh] space-y-3 overflow-y-auto py-1 pe-1'>
          <div className='space-y-1.5'>
            <Label>数据权限范围</Label>
            <SelectDropdown
              isControlled
              value={dataScope}
              onValueChange={(value) =>
                setDataScope(value as `${RoleDataScope}`)
              }
              withFormControl={false}
              items={roleDataScopeOptions.map(({ label, value }) => ({
                label,
                value,
              }))}
              disabled={mutation.isPending}
              className='w-full'
            />
          </div>

          {isCustomScope ? (
            <div className='space-y-1.5'>
              <Label>可访问部门</Label>
              {hasDeptTreeError ? (
                <div className='rounded-md border border-destructive/30 bg-destructive/5 px-3 py-4 text-sm text-destructive'>
                  当前账号无权读取部门树，无法配置自定义部门范围。
                </div>
              ) : hasRoleDeptError ? (
                <div className='rounded-md border border-destructive/30 bg-destructive/5 px-3 py-4 text-sm text-destructive'>
                  读取角色已有部门绑定失败，请关闭后重试。
                </div>
              ) : isDeptLoading || isRoleDeptsLoading ? (
                <Skeleton className='h-64 w-full' />
              ) : (
                <CheckableTree
                  nodes={deptTreeQuery.data ?? []}
                  selectedIds={selectedDeptIds}
                  onChange={(nextDeptIds) => {
                    setDeptIdsDirty(true)
                    setDeptIds(nextDeptIds)
                  }}
                  disabled={mutation.isPending}
                  emptyText='暂无可分配的部门。'
                />
              )}
              <p className='text-xs text-muted-foreground'>
                保存后会用当前勾选结果替换角色已有的部门绑定。
              </p>
            </div>
          ) : null}
        </div>

        <DialogFooter>
          <Button
            type='button'
            variant='outline'
            onClick={() => onOpenChange(false)}
            disabled={mutation.isPending}
          >
            取消
          </Button>
          <Button
            type='button'
            onClick={handleSubmit}
            disabled={
              mutation.isPending ||
              (isCustomScope && (isDeptLoading || hasDeptTreeError)) ||
              (isOriginallyCustomScope && (isRoleDeptsLoading || hasRoleDeptError))
            }
          >
            保存
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
