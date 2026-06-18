import { useState } from 'react'
import { type Table } from '@tanstack/react-table'
import { Trash2 } from 'lucide-react'
import { useAccess } from '@/app/auth/access'
import { Button } from '@/components/ui/button'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { DataTableBulkActions as BulkActionsToolbar } from '@/components/data-table'
import { RolesMultiDeleteDialog } from './roles-multi-delete-dialog'

type DataTableBulkActionsProps<TData> = {
  table: Table<TData>
}

export function DataTableBulkActions<TData>({
  table,
}: DataTableBulkActionsProps<TData>) {
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const canDeleteRoles = useAccess({
    permissions: ['system:role:remove'],
  })

  if (!canDeleteRoles) {
    return null
  }

  return (
    <>
      <BulkActionsToolbar table={table} entityName='角色'>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant='destructive'
              size='icon'
              onClick={() => setShowDeleteConfirm(true)}
              className='size-8'
              aria-label='删除所选角色'
              title='删除所选角色'
            >
              <Trash2 />
              <span className='sr-only'>删除所选角色</span>
            </Button>
          </TooltipTrigger>
          <TooltipContent>
            <p>删除所选角色</p>
          </TooltipContent>
        </Tooltip>
      </BulkActionsToolbar>

      <RolesMultiDeleteDialog
        table={table}
        open={showDeleteConfirm}
        onOpenChange={setShowDeleteConfirm}
      />
    </>
  )
}
