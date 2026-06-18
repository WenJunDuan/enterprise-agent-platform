import { useState } from 'react'
import { DotsHorizontalIcon } from '@radix-ui/react-icons'
import { type Row } from '@tanstack/react-table'
import { Pencil, ShieldCheck, ShieldOff, Trash2, Database } from 'lucide-react'
import { useAuthStore } from '@/stores/auth-store'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuShortcut,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { type Role } from '../model'
import {
  getRoleManagementAccess,
  isProtectedSystemRole,
} from '../role-management-access'
import { useRoles } from './roles-provider'
import { RolesDataScopeDialog } from './roles-data-scope-dialog'
import { RolesStatusDialog } from './roles-status-dialog'

type DataTableRowActionsProps = {
  row: Row<Role>
}

function runAfterMenuCloses(callback: () => void) {
  if (typeof window === 'undefined') {
    callback()
    return
  }

  window.setTimeout(callback, 0)
}

export function DataTableRowActions({ row }: DataTableRowActionsProps) {
  const { setOpen, setCurrentRow } = useRoles()
  const authUser = useAuthStore((state) => state.user)
  const [statusDialogOpen, setStatusDialogOpen] = useState(false)
  const [dataScopeDialogOpen, setDataScopeDialogOpen] = useState(false)
  const {
    canChangeRoleStatus,
    canChangeRoleDataScope,
    canDeleteRoles,
    canEditRoles,
    hasRowActions,
  } = getRoleManagementAccess(authUser)

  if (!hasRowActions) {
    return null
  }

  const currentRow = row.original
  const isProtected = isProtectedSystemRole(currentRow.id)
  const hasPrimaryActions =
    canEditRoles || canChangeRoleStatus || canChangeRoleDataScope

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
          {canEditRoles && (
            <DropdownMenuItem
              disabled={isProtected}
              onSelect={() => {
                runAfterMenuCloses(() => {
                  setCurrentRow(currentRow)
                  setOpen('edit')
                })
              }}
            >
              编辑角色
              <DropdownMenuShortcut>
                <Pencil size={16} />
              </DropdownMenuShortcut>
            </DropdownMenuItem>
          )}
          {canChangeRoleStatus && (
            <DropdownMenuItem
              disabled={isProtected}
              onSelect={() => {
                runAfterMenuCloses(() => {
                  setStatusDialogOpen(true)
                })
              }}
            >
              {currentRow.status === 1 ? '停用角色' : '启用角色'}
              <DropdownMenuShortcut>
                {currentRow.status === 1 ? (
                  <ShieldOff size={16} />
                ) : (
                  <ShieldCheck size={16} />
                )}
              </DropdownMenuShortcut>
            </DropdownMenuItem>
          )}
          {canChangeRoleDataScope && (
            <DropdownMenuItem
              disabled={isProtected}
              onSelect={() => {
                runAfterMenuCloses(() => {
                  setDataScopeDialogOpen(true)
                })
              }}
            >
              数据权限
              <DropdownMenuShortcut>
                <Database size={16} />
              </DropdownMenuShortcut>
            </DropdownMenuItem>
          )}
          {hasPrimaryActions && canDeleteRoles && <DropdownMenuSeparator />}
          {canDeleteRoles && (
            <DropdownMenuItem
              disabled={isProtected}
              onSelect={() => {
                runAfterMenuCloses(() => {
                  setCurrentRow(currentRow)
                  setOpen('delete')
                })
              }}
              className='text-red-500!'
            >
              删除角色
              <DropdownMenuShortcut>
                <Trash2 size={16} />
              </DropdownMenuShortcut>
            </DropdownMenuItem>
          )}
        </DropdownMenuContent>
      </DropdownMenu>

      {statusDialogOpen ? (
        <RolesStatusDialog
          open={statusDialogOpen}
          onOpenChange={setStatusDialogOpen}
          currentRow={currentRow}
        />
      ) : null}
      {dataScopeDialogOpen ? (
        <RolesDataScopeDialog
          open={dataScopeDialogOpen}
          onOpenChange={setDataScopeDialogOpen}
          currentRow={currentRow}
        />
      ) : null}
    </>
  )
}
