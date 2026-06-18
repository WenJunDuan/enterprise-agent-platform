import { useState } from 'react'
import { DotsHorizontalIcon } from '@radix-ui/react-icons'
import { type Row } from '@tanstack/react-table'
import { KeyRound, Trash2, UserCheck, UserPen, UserX } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuShortcut,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useAuthStore } from '@/stores/auth-store'
import { type User } from '../data/schema'
import { getUserManagementAccess } from '../user-management-access'
import { useUsers } from './users-provider'
import { UsersResetPasswordDialog } from './users-reset-password-dialog'
import { UsersStatusDialog } from './users-status-dialog'

type DataTableRowActionsProps = {
  row: Row<User>
}

function runAfterMenuCloses(callback: () => void) {
  if (typeof window === 'undefined') {
    callback()
    return
  }

  window.setTimeout(callback, 0)
}

export function DataTableRowActions({ row }: DataTableRowActionsProps) {
  const { setOpen, setCurrentRow } = useUsers()
  const authUser = useAuthStore((state) => state.user)
  const [statusDialogOpen, setStatusDialogOpen] = useState(false)
  const [resetPasswordOpen, setResetPasswordOpen] = useState(false)
  const {
    canChangeUserStatus,
    canDeleteUsers,
    canEditUsers,
    canResetPasswords,
    hasRowActions,
  } = getUserManagementAccess(authUser)

  if (!hasRowActions) {
    return null
  }

  const currentRow = row.original
  const hasPrimaryActions =
    canEditUsers || canChangeUserStatus || canResetPasswords

  return (
    <>
      <DropdownMenu modal={false}>
        <DropdownMenuTrigger asChild>
          <Button
            variant='ghost'
            className='flex h-8 w-8 p-0 data-[state=open]:bg-muted'
          >
            <DotsHorizontalIcon className='h-4 w-4' />
            <span className='sr-only'>打开菜单</span>
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align='end' className='w-[180px]'>
          {canEditUsers && (
            <DropdownMenuItem
              onSelect={() => {
                runAfterMenuCloses(() => {
                  setCurrentRow(currentRow)
                  setOpen('edit')
                })
              }}
            >
              编辑用户
              <DropdownMenuShortcut>
                <UserPen size={16} />
              </DropdownMenuShortcut>
              </DropdownMenuItem>
          )}
          {canChangeUserStatus && (
            <DropdownMenuItem
              onSelect={() => {
                runAfterMenuCloses(() => {
                  setStatusDialogOpen(true)
                })
              }}
            >
              {currentRow.status === 1 ? '停用用户' : '启用用户'}
              <DropdownMenuShortcut>
                {currentRow.status === 1 ? (
                  <UserX size={16} />
                ) : (
                  <UserCheck size={16} />
                )}
              </DropdownMenuShortcut>
              </DropdownMenuItem>
          )}
          {canResetPasswords && (
            <DropdownMenuItem
              onSelect={() => {
                runAfterMenuCloses(() => {
                  setResetPasswordOpen(true)
                })
              }}
            >
              重置密码
              <DropdownMenuShortcut>
                <KeyRound size={16} />
              </DropdownMenuShortcut>
              </DropdownMenuItem>
          )}
          {hasPrimaryActions && canDeleteUsers && <DropdownMenuSeparator />}
          {canDeleteUsers && (
            <DropdownMenuItem
              onSelect={() => {
                runAfterMenuCloses(() => {
                  setCurrentRow(currentRow)
                  setOpen('delete')
                })
              }}
              className='text-red-500!'
            >
              删除用户
              <DropdownMenuShortcut>
                <Trash2 size={16} />
              </DropdownMenuShortcut>
            </DropdownMenuItem>
          )}
        </DropdownMenuContent>
      </DropdownMenu>

      <UsersStatusDialog
        open={statusDialogOpen}
        onOpenChange={setStatusDialogOpen}
        currentRow={currentRow}
      />
      <UsersResetPasswordDialog
        open={resetPasswordOpen}
        onOpenChange={setResetPasswordOpen}
        currentRow={currentRow}
      />
    </>
  )
}
