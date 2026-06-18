'use client'

import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle } from 'lucide-react'
import { toast } from 'sonner'
import { deleteUsers } from '../api'
import { type User } from '../data/schema'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ConfirmDialog } from '@/components/confirm-dialog'

type UserDeleteDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  currentRow: User
}

export function UsersDeleteDialog({
  open,
  onOpenChange,
  currentRow,
}: UserDeleteDialogProps) {
  const [value, setValue] = useState('')
  const queryClient = useQueryClient()

  const mutation = useMutation({
    mutationFn: () => deleteUsers([currentRow.id]),
    onSuccess: async () => {
      toast.success(`用户“${currentRow.username}”已删除。`)
      onOpenChange(false)
      setValue('')
      await queryClient.invalidateQueries({
        queryKey: ['system', 'users', 'list'],
      })
    },
  })

  const handleDelete = () => {
    if (value.trim() !== currentRow.username) return
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
      form='users-delete-form'
      disabled={value.trim() !== currentRow.username || mutation.isPending}
      isLoading={mutation.isPending}
      title={
        <span className='text-destructive'>
          <AlertTriangle
            className='me-1 inline-block stroke-destructive'
            size={18}
          />{' '}
          删除用户
        </span>
      }
      desc={
        <form
          id='users-delete-form'
          onSubmit={(event) => {
            event.preventDefault()
            handleDelete()
          }}
          className='space-y-4'
        >
          <p className='mb-2'>
            确认删除用户{' '}
            <span className='font-bold'>{currentRow.username}</span> 吗？
            <br />
            该操作会将此用户永久从系统中移除，且无法撤销。
          </p>

          <div className='my-2 flex items-center gap-3'>
            <Label htmlFor='users-delete-confirm' className='shrink-0 whitespace-nowrap'>
              用户名：
            </Label>
            <Input
              id='users-delete-confirm'
              value={value}
              onChange={(event) => setValue(event.target.value)}
              placeholder='请输入用户名以确认删除'
              autoFocus
              className='flex-1'
            />
          </div>

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
