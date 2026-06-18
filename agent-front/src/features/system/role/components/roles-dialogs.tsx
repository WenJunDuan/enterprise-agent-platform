import { useEffect, useRef } from 'react'
import { RolesActionDialog } from './roles-action-dialog'
import { RolesDeleteDialog } from './roles-delete-dialog'
import {
  ROLES_DIALOG_ROW_RESET_DELAY_MS,
  shouldClearRolesCurrentRow,
  syncRolesDialogOpenState,
  type RolesDialogType,
} from './roles-dialog-state'
import { useRoles } from './roles-provider'

export function RolesDialogs() {
  const { open, setOpen, currentRow, setCurrentRow } = useRoles()
  const rowResetTimeoutRef = useRef<number | null>(null)

  useEffect(() => {
    return () => {
      if (rowResetTimeoutRef.current !== null) {
        window.clearTimeout(rowResetTimeoutRef.current)
      }
    }
  }, [])

  const handleOpenChange = (dialog: RolesDialogType, nextOpen: boolean) => {
    if (rowResetTimeoutRef.current !== null) {
      window.clearTimeout(rowResetTimeoutRef.current)
      rowResetTimeoutRef.current = null
    }

    setOpen(syncRolesDialogOpenState(dialog, nextOpen))

    if (!shouldClearRolesCurrentRow(dialog, nextOpen)) {
      return
    }

    rowResetTimeoutRef.current = window.setTimeout(() => {
      setCurrentRow(null)
      rowResetTimeoutRef.current = null
    }, ROLES_DIALOG_ROW_RESET_DELAY_MS)
  }

  return (
    <>
      <RolesActionDialog
        key='role-add'
        open={open === 'add'}
        onOpenChange={(nextOpen) => handleOpenChange('add', nextOpen)}
      />

      {currentRow && (
        <>
          <RolesActionDialog
            key={`role-edit-${currentRow.id}`}
            open={open === 'edit'}
            onOpenChange={(nextOpen) => handleOpenChange('edit', nextOpen)}
            currentRow={currentRow}
          />

          <RolesDeleteDialog
            key={`role-delete-${currentRow.id}`}
            open={open === 'delete'}
            onOpenChange={(nextOpen) => handleOpenChange('delete', nextOpen)}
            currentRow={currentRow}
          />
        </>
      )}
    </>
  )
}
