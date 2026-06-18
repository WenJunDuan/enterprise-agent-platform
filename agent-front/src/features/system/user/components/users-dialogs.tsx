import { useEffect, useRef } from 'react'
import { UsersActionDialog } from './users-action-dialog'
import { UsersDeleteDialog } from './users-delete-dialog'
import { useUsers } from './users-provider'
import {
  shouldClearUsersCurrentRow,
  syncUsersDialogOpenState,
  USERS_DIALOG_ROW_RESET_DELAY_MS,
  type UsersDialogType,
} from './users-dialog-state'

export function UsersDialogs() {
  const { open, setOpen, currentRow, setCurrentRow } = useUsers()
  const rowResetTimeoutRef = useRef<number | null>(null)

  useEffect(() => {
    return () => {
      if (rowResetTimeoutRef.current !== null) {
        window.clearTimeout(rowResetTimeoutRef.current)
      }
    }
  }, [])

  const handleOpenChange = (dialog: UsersDialogType, nextOpen: boolean) => {
    if (rowResetTimeoutRef.current !== null) {
      window.clearTimeout(rowResetTimeoutRef.current)
      rowResetTimeoutRef.current = null
    }

    setOpen(syncUsersDialogOpenState(dialog, nextOpen))

    if (!shouldClearUsersCurrentRow(dialog, nextOpen)) {
      return
    }

    rowResetTimeoutRef.current = window.setTimeout(() => {
      setCurrentRow(null)
      rowResetTimeoutRef.current = null
    }, USERS_DIALOG_ROW_RESET_DELAY_MS)
  }

  return (
    <>
      <UsersActionDialog
        key='user-add'
        open={open === 'add'}
        onOpenChange={(nextOpen) => handleOpenChange('add', nextOpen)}
      />

      {currentRow && (
        <>
          <UsersActionDialog
            key={`user-edit-${currentRow.id}`}
            open={open === 'edit'}
            onOpenChange={(nextOpen) => handleOpenChange('edit', nextOpen)}
            currentRow={currentRow}
          />

          <UsersDeleteDialog
            key={`user-delete-${currentRow.id}`}
            open={open === 'delete'}
            onOpenChange={(nextOpen) => handleOpenChange('delete', nextOpen)}
            currentRow={currentRow}
          />
        </>
      )}
    </>
  )
}
