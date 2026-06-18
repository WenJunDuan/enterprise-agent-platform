'use client'

import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { type Table } from '@tanstack/react-table'
import { AlertTriangle } from 'lucide-react'
import { toast } from 'sonner'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { handleServerError } from '@/lib/handle-server-error'
import { deleteRoles } from '../api'
import { type Role } from '../model'

type RolesMultiDeleteDialogProps<TData> = {
  open: boolean
  onOpenChange: (open: boolean) => void
  table: Table<TData>
}

const CONFIRM_WORD = '删除'

export function RolesMultiDeleteDialog<TData>({
  open,
  onOpenChange,
  table,
}: RolesMultiDeleteDialogProps<TData>) {
  const [value, setValue] = useState('')
  const queryClient = useQueryClient()
  const selectedRows = table.getFilteredSelectedRowModel().rows
  const selectedRoles = selectedRows.map((row) => row.original as Role)

  const mutation = useMutation({
    mutationFn: () => deleteRoles(selectedRoles.map((role) => role.id)),
    onSuccess: async () => {
      toast.success(`已删除 ${selectedRoles.length} 个角色。`)
      onOpenChange(false)
      setValue('')
      table.resetRowSelection()
      await queryClient.invalidateQueries({
        queryKey: ['system', 'role', 'list'],
      })
    },
    onError: handleServerError,
  })

  const handleDelete = () => {
    if (value.trim() !== CONFIRM_WORD) {
      toast.error(`请输入“${CONFIRM_WORD}”以确认操作。`)
      return
    }

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
      form='roles-multi-delete-form'
      disabled={value.trim() !== CONFIRM_WORD || mutation.isPending}
      isLoading={mutation.isPending}
      title={
        <span className='text-destructive'>
          <AlertTriangle
            className='me-1 inline-block stroke-destructive'
            size={18}
          />{' '}
          删除 {selectedRoles.length} 个角色
        </span>
      }
      desc={
        <form
          id='roles-multi-delete-form'
          onSubmit={(event) => {
            event.preventDefault()
            handleDelete()
          }}
          className='space-y-4'
        >
          <p className='mb-2'>
            确认删除已选角色吗？
            <br />
            若任意一个角色已被用户引用，后端会中止整个删除操作。
          </p>

          <Label className='my-4 flex flex-col items-start gap-1.5'>
            <span>请输入“{CONFIRM_WORD}”确认：</span>
            <Input
              value={value}
              onChange={(event) => setValue(event.target.value)}
              placeholder={`请输入“${CONFIRM_WORD}”进行确认`}
              autoFocus
            />
          </Label>

          <Alert variant='destructive'>
            <AlertTitle>警告</AlertTitle>
            <AlertDescription>
              请谨慎操作，此步骤执行后无法回滚。
            </AlertDescription>
          </Alert>
        </form>
      }
      confirmText='删除'
      destructive
    />
  )
}
