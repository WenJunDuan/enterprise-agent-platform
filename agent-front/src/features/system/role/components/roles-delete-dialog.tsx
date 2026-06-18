'use client'

import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle } from 'lucide-react'
import { toast } from 'sonner'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { handleServerError } from '@/lib/handle-server-error'
import { deleteRoles } from '../api'
import { type Role } from '../model'

type RolesDeleteDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  currentRow: Role
}

export function RolesDeleteDialog({
  open,
  onOpenChange,
  currentRow,
}: RolesDeleteDialogProps) {
  const [value, setValue] = useState('')
  const queryClient = useQueryClient()

  const mutation = useMutation({
    mutationFn: () => deleteRoles([currentRow.id]),
    onSuccess: async () => {
      toast.success(`角色“${currentRow.roleName}”已删除。`)
      onOpenChange(false)
      setValue('')
      await queryClient.invalidateQueries({
        queryKey: ['system', 'role', 'list'],
      })
    },
    onError: handleServerError,
  })

  const handleDelete = () => {
    if (value.trim() !== currentRow.roleName) return
    mutation.mutate()
  }

  const handleOpenChange = (nextOpen: boolean) => {
    if (!nextOpen) {
      setValue('')
    }

    onOpenChange(nextOpen)
  }

  return (
    <ConfirmDialog
      open={open}
      onOpenChange={handleOpenChange}
      form='roles-delete-form'
      disabled={value.trim() !== currentRow.roleName || mutation.isPending}
      isLoading={mutation.isPending}
      title={
        <span className='text-destructive'>
          <AlertTriangle
            className='me-1 inline-block stroke-destructive'
            size={18}
          />{' '}
          删除角色
        </span>
      }
      desc={
        <form
          id='roles-delete-form'
          onSubmit={(event) => {
            event.preventDefault()
            handleDelete()
          }}
          className='space-y-4'
        >
          <p className='mb-2'>
            确认删除角色{' '}
            <span className='font-bold'>{currentRow.roleName}</span>（
            <code className='rounded bg-muted px-1 py-0.5 text-xs'>
              {currentRow.roleKey}
            </code>
            ）吗？
            <br />
            此操作会永久移除该角色及其菜单、数据权限关联，无法撤销。
          </p>

          <div className='my-2 flex items-center gap-3'>
            <Label
              htmlFor='roles-delete-confirm'
              className='shrink-0 whitespace-nowrap'
            >
              角色名称：
            </Label>
            <Input
              id='roles-delete-confirm'
              value={value}
              onChange={(event) => setValue(event.target.value)}
              placeholder='请输入角色名称以确认删除'
              autoFocus
              className='flex-1'
            />
          </div>

          <Alert variant='destructive'>
            <AlertTitle>警告</AlertTitle>
            <AlertDescription>
              若该角色已被用户引用，后端会拦截删除并返回提示，请先解除引用。
            </AlertDescription>
          </Alert>
        </form>
      }
      confirmText='删除'
      destructive
    />
  )
}
